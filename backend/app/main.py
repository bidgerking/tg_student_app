from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import Database
from .models import (
    ConfirmVerificationRequest,
    FriendRequestCreate,
    LoginRequest,
    LogoutRequest,
    NotificationRequest,
    RegisterRequest,
    StudentVerificationRequest,
    TelegramAuthRequest,
)
from .security import (
    hash_password,
    hash_personal_number,
    new_session_token,
    validate_password,
    validate_telegram_init_data,
    verify_password,
)
from .services.bsuir import BsuirScheduleClient
from .services.registry import StudentRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()
db = Database(settings.database_path)
registry = StudentRegistry(settings.student_registry_path, settings.student_registry_pepper)
bsuir = BsuirScheduleClient(settings.bsuir_api_base_url, db)
app = FastAPI(title=settings.app_name, version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSION_COOKIE = "bsuir_session"
LOGOUT_COOKIE = "bsuir_logged_out"
attempts: dict[int, list[datetime]] = {}
login_attempts: dict[int, list[datetime]] = {}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name}


@app.on_event("startup")
async def startup() -> None:
    await db.init()


def public_profile(profile: dict | None) -> dict | None:
    if not profile:
        return None
    return {key: value for key, value in profile.items() if key not in {"personal_number_hash", "password_hash", "user_id", "id"}}


def public_friend(profile: dict) -> dict:
    return {
        "userId": profile["user_id"],
        "name": profile.get("name", ""),
        "faculty_name": profile.get("faculty_name", ""),
        "speciality_name": profile.get("speciality_name", ""),
        "course": profile.get("course"),
        "group_number": profile.get("group_number", ""),
        "subgroup": profile.get("subgroup"),
        "student_status": profile.get("student_status", "active"),
    }


def session_expiry(remember_me: bool) -> datetime:
    duration = timedelta(days=settings.session_remember_days) if remember_me else timedelta(minutes=settings.session_short_minutes)
    return datetime.now(timezone.utc) + duration


def profile_data_from_candidate(candidate: dict) -> dict:
    return {
        "personal_number_hash": candidate["personal_number_hash"],
        "faculty_id": candidate.get("facultyId"),
        "faculty_name": candidate.get("faculty", ""),
        "speciality_id": candidate.get("specialityId"),
        "speciality_name": candidate.get("speciality", ""),
        "course": candidate.get("course"),
        "group_number": candidate["group"],
        "subgroup": candidate.get("subgroup"),
        "education_form": candidate.get("educationForm"),
        "student_status": candidate.get("status", "active"),
        "verified_at": candidate["verified_at"],
        "name": candidate.get("name", ""),
    }


def generic_auth_error() -> HTTPException:
    return HTTPException(401, "Неверный личный номер или пароль")


def development_telegram_user(init_data: str):
    """Return one of three local-only identities used for friend-flow testing."""
    suffixes = {"dev-test-init-data": 1, "dev-test-init-data-2": 2, "dev-test-init-data-3": 3}
    test_user = suffixes.get(init_data)
    if test_user is None:
        return None
    return type(
        "DevTelegramUser",
        (),
        {
            "telegram_id": settings.dev_telegram_id + test_user - 1,
            "username": f"bsuir_test_user_{test_user}",
            "first_name": "Тестовый" if test_user == 1 else f"Тестовый Друг {test_user - 1}",
            "last_name": "Студент",
        },
    )()


def is_local_dev_request(request: Request) -> bool:
    host = request.headers.get("host", "").split(":", 1)[0].strip("[]").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


async def resolve_session(authorization: str | None, session_cookie: str | None) -> dict:
    token = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else session_cookie
    if not token:
        raise HTTPException(401, "Требуется авторизация Telegram Web App")
    session = await db.get_session(hashlib.sha256(token.encode()).hexdigest())
    if not session:
        raise HTTPException(401, "Сессия истекла, откройте приложение заново")
    session["token"] = token
    return session


async def current_session(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    return await resolve_session(authorization, session_cookie)


async def current_user(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> int:
    return int((await resolve_session(authorization, session_cookie))["user_id"])


async def issue_session(
    user_id: int,
    remember_me: bool,
    response: Response,
    request: Request,
    *,
    clear_logged_out: bool = True,
) -> str:
    token = new_session_token()
    expires = session_expiry(remember_me)
    await db.save_session(hashlib.sha256(token.encode()).hexdigest(), user_id, expires.isoformat(), remember_me)
    max_age = max(1, int((expires - datetime.now(timezone.utc)).total_seconds()))
    cookie_options = {
        "httponly": True,
        "secure": request_is_https(request),
        "samesite": "lax",
        "path": "/",
    }
    if remember_me:
        cookie_options["max_age"] = max_age
    response.set_cookie(SESSION_COOKIE, token, **cookie_options)
    if clear_logged_out:
        response.delete_cookie(LOGOUT_COOKIE, path="/")
    return token


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def request_is_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme).split(",", 1)[0].strip().lower() == "https"


def normalize_personal_number(value: str) -> str:
    return "".join(character for character in value if character.isalnum()).upper()


async def verify_candidate(personal_number: str) -> tuple[str, dict] | None:
    normalized = normalize_personal_number(personal_number)
    candidate = registry.verify(normalized)
    if candidate is None or candidate.get("status", "active") != "active":
        return None
    candidate.update(await bsuir.group_metadata(candidate["group"]))
    candidate["personal_number_hash"] = hash_personal_number(normalized, settings.student_registry_pepper)
    candidate["verified_at"] = datetime.now(timezone.utc).isoformat()
    return normalized, candidate


@app.post("/api/app/telegram/auth")
@app.post("/api/auth/telegram")
async def telegram_auth(
    payload: TelegramAuthRequest,
    request: Request,
    response: Response,
    logged_out: str | None = Cookie(default=None, alias=LOGOUT_COOKIE),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    try:
        tg_user = validate_telegram_init_data(payload.init_data, settings.bot_token, settings.telegram_init_data_max_age)
    except ValueError as exc:
        if not settings.dev_auth_enabled or not is_local_dev_request(request):
            raise HTTPException(401, str(exc)) from exc
        tg_user = development_telegram_user(payload.init_data)
        if tg_user is None:
            raise HTTPException(401, str(exc)) from exc
    user_id = await db.upsert_user(tg_user.telegram_id, tg_user.username, tg_user.first_name)
    credentials = await db.get_credentials(user_id)
    existing_session = None
    if logged_out != "1" and session_cookie:
        existing_session = await db.get_session(hashlib.sha256(session_cookie.encode()).hexdigest())
        if not existing_session or int(existing_session["user_id"]) != user_id:
            existing_session = None
    if existing_session:
        await db.delete_session(hashlib.sha256(session_cookie.encode()).hexdigest())
        token = await issue_session(user_id, bool(existing_session.get("remember_me")), response, request)
    else:
        token = await issue_session(user_id, False, response, request, clear_logged_out=logged_out != "1")
    profile = await db.get_profile(user_id) if credentials and existing_session else None
    return {
        "accessToken": token,
        "user": {"telegramId": tg_user.telegram_id, "firstName": tg_user.first_name, "username": tg_user.username},
        "profile": public_profile(profile),
        "hasAccount": credentials is not None,
    }


@app.post("/api/auth/register")
async def register_student(
    payload: RegisterRequest,
    user_id: int = Depends(current_user),
) -> dict:
    if payload.password != payload.password_confirmation:
        raise HTTPException(400, "Пароли не совпадают")
    password_error = validate_password(payload.password, normalize_personal_number(payload.personal_number))
    if password_error:
        raise HTTPException(400, password_error)
    candidate_result = await verify_candidate(payload.personal_number)
    if candidate_result is None:
        raise HTTPException(400, "Личный номер не найден или студент не имеет активного статуса")
    normalized, candidate = candidate_result
    number_hash = hash_personal_number(normalized, settings.student_registry_pepper)
    existing = await db.get_credentials_by_personal_hash(number_hash)
    if existing:
        raise HTTPException(409, "Для этого личного номера уже существует аккаунт")
    candidate["password_hash"] = hash_password(payload.password)
    pending_token = secrets.token_urlsafe(24)
    await db.save_pending(hashlib.sha256(pending_token.encode()).hexdigest(), user_id, candidate, (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
    return {
        "registered": False,
        "registrationToken": pending_token,
        "student": {key: value for key, value in candidate.items() if key not in {"personal_number_hash", "password_hash", "verified_at"}},
    }


@app.post("/api/auth/register/confirm")
async def confirm_registration(
    payload: ConfirmVerificationRequest,
    request: Request,
    response: Response,
    user_id: int = Depends(current_user),
) -> dict:
    candidate = await db.consume_pending(hashlib.sha256(payload.verification_token.encode()).hexdigest(), user_id)
    if not candidate or not candidate.get("password_hash"):
        raise HTTPException(400, "Данные регистрации истекли. Начните регистрацию ещё раз")
    try:
        await db.create_account(user_id, profile_data_from_candidate(candidate), candidate["password_hash"])
    except aiosqlite.IntegrityError as exc:
        raise HTTPException(409, "Для этого личного номера уже существует аккаунт") from exc
    token = await issue_session(user_id, False, response, request)
    return {"registered": True, "accessToken": token, "profile": public_profile(await db.get_profile(user_id))}


@app.post("/api/auth/login")
async def login_student(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: dict = Depends(current_session),
) -> dict:
    user_id = int(session["user_id"])
    now = datetime.now(timezone.utc)
    recent = [stamp for stamp in login_attempts.get(user_id, []) if now - stamp < timedelta(hours=1)]
    if len(recent) >= settings.login_attempts_per_hour:
        raise HTTPException(429, "Слишком много попыток входа. Повторите позже")
    login_attempts[user_id] = [*recent, now]
    number_hash = hash_personal_number(normalize_personal_number(payload.personal_number), settings.student_registry_pepper)
    credentials = await db.get_credentials_by_personal_hash(number_hash)
    if not credentials or int(credentials["user_id"]) != user_id or not verify_password(payload.password, credentials["password_hash"]):
        raise generic_auth_error()
    candidate_result = await verify_candidate(payload.personal_number)
    if candidate_result:
        _, candidate = candidate_result
        await db.save_profile(user_id, profile_data_from_candidate(candidate))
    await db.mark_login(user_id)
    token = await issue_session(user_id, payload.remember_me, response, request)
    return {"accessToken": token, "rememberMe": payload.remember_me, "profile": public_profile(await db.get_profile(user_id))}


@app.post("/api/auth/refresh")
async def refresh_session(request: Request, response: Response, session: dict = Depends(current_session)) -> dict:
    await db.delete_session(hashlib.sha256(session["token"].encode()).hexdigest())
    token = await issue_session(int(session["user_id"]), bool(session.get("remember_me")), response, request)
    return {"accessToken": token, "profile": public_profile(await db.get_profile(int(session["user_id"]))) }


@app.get("/api/auth/me")
async def auth_me(user_id: int = Depends(current_user)) -> dict:
    profile = await db.get_profile(user_id)
    return {"profile": public_profile(profile)}


@app.post("/api/auth/logout")
async def logout(
    payload: LogoutRequest,
    request: Request,
    response: Response,
    session: dict = Depends(current_session),
) -> dict:
    if payload.all_devices:
        await db.delete_user_sessions(int(session["user_id"]))
    else:
        await db.delete_session(hashlib.sha256(session["token"].encode()).hexdigest())
    clear_session_cookie(response)
    response.set_cookie(LOGOUT_COOKIE, "1", max_age=86400, httponly=True, secure=request_is_https(request), samesite="lax", path="/")
    return {"loggedOut": True, "allDevices": payload.all_devices}


@app.post("/api/app/student/verify")
async def verify_student(payload: StudentVerificationRequest, user_id: int = Depends(current_user)) -> dict:
    now = datetime.now(timezone.utc)
    recent = [stamp for stamp in attempts.get(user_id, []) if now - stamp < timedelta(hours=1)]
    if len(recent) >= settings.verification_attempts_per_hour:
        raise HTTPException(429, "Слишком много попыток. Повторите позже")
    attempts[user_id] = [*recent, now]
    candidate_result = await verify_candidate(payload.personal_number)
    if candidate_result is None:
        return {"verified": False, "error": "Номер не найден в доверенном реестре студентов"}
    _, candidate = candidate_result
    pending_token = secrets.token_urlsafe(24)
    await db.save_pending(hashlib.sha256(pending_token.encode()).hexdigest(), user_id, candidate, (now + timedelta(minutes=10)).isoformat())
    return {"verified": True, "verificationToken": pending_token, "student": {key: value for key, value in candidate.items() if key not in {"personal_number_hash", "verified_at"}}}


@app.post("/api/app/student/confirm")
async def confirm_student(payload: ConfirmVerificationRequest, user_id: int = Depends(current_user)) -> dict:
    candidate = await db.consume_pending(hashlib.sha256(payload.verification_token.encode()).hexdigest(), user_id)
    if not candidate:
        raise HTTPException(400, "Данные проверки истекли. Проверьте личный номер ещё раз")
    await db.save_profile(user_id, profile_data_from_candidate(candidate))
    return {"profile": public_profile(await db.get_profile(user_id))}


@app.get("/api/app/student/profile")
async def student_profile(user_id: int = Depends(current_user)) -> dict:
    profile = await db.get_profile(user_id)
    if not profile:
        raise HTTPException(404, "Профиль ещё не подтверждён")
    return {"profile": public_profile(profile)}


@app.delete("/api/app/student/profile")
async def delete_student_profile(user_id: int = Depends(current_user)) -> dict:
    await db.delete_profile(user_id)
    return {"deleted": True}


@app.get("/api/app/friends")
async def friends(user_id: int = Depends(current_user)) -> dict:
    await profile_or_403(user_id)
    return await db.list_friendships(user_id)


def friend_relationship(friendship: dict | None, user_id: int) -> tuple[str | None, int | None]:
    if not friendship:
        return None, None
    if friendship["status"] == "accepted":
        return "accepted", friendship["id"]
    return ("outgoing" if friendship["requested_by"] == user_id else "incoming"), friendship["id"]


@app.get("/api/app/friends/search")
async def search_friends(
    q: str = Query(min_length=2, max_length=120),
    user_id: int = Depends(current_user),
) -> dict:
    await profile_or_403(user_id)
    query = q.strip()
    if not query:
        raise HTTPException(400, "Введите студенческий номер или ФИО")

    matches: list[dict] = []
    normalized = normalize_personal_number(query)
    if len(normalized) >= 4 and normalized.isdigit():
        candidate_result = await verify_candidate(query)
        if candidate_result:
            _, candidate = candidate_result
            profile = await db.get_profile_by_personal_hash(candidate["personal_number_hash"])
            if profile and int(profile["user_id"]) != user_id:
                matches.append(profile)
    else:
        matches = await db.search_profiles(query, user_id)

    items = []
    for profile in matches:
        student_id = int(profile["user_id"])
        relationship, request_id = friend_relationship(await db.get_friendship(user_id, student_id), user_id)
        item = public_friend(profile)
        item["relationship"] = relationship
        if request_id is not None:
            item["requestId"] = request_id
        items.append(item)
    return {"items": items}


@app.post("/api/app/friends/requests")
async def create_friend_request(payload: FriendRequestCreate, user_id: int = Depends(current_user)) -> dict:
    await profile_or_403(user_id)
    if payload.user_id == user_id:
        raise HTTPException(400, "Нельзя добавить самого себя")
    target = await db.get_profile(payload.user_id)
    if not target or target.get("student_status") != "active":
        raise HTTPException(404, "Профиль студента не найден")
    existing = await db.get_friendship(user_id, payload.user_id)
    if existing:
        if existing["status"] == "accepted":
            raise HTTPException(409, "Этот студент уже в списке друзей")
        if existing["requested_by"] == user_id:
            raise HTTPException(409, "Заявка уже отправлена")
        raise HTTPException(409, "У вас уже есть входящая заявка от этого студента")
    request_row = await db.create_friend_request(user_id, payload.user_id)
    return {"created": True, "requestId": request_row["id"]}


@app.post("/api/app/friends/requests/{request_id}/accept")
async def accept_friend_request(request_id: int, user_id: int = Depends(current_user)) -> dict:
    if not await db.accept_friend_request(request_id, user_id):
        raise HTTPException(404, "Входящая заявка не найдена или уже обработана")
    return {"accepted": True, "requestId": request_id}


@app.delete("/api/app/friends/requests/{request_id}")
async def delete_friend_request(request_id: int, user_id: int = Depends(current_user)) -> dict:
    if not await db.delete_friend_request(request_id, user_id):
        raise HTTPException(404, "Заявка не найдена или уже обработана")
    return {"deleted": True, "requestId": request_id}


@app.delete("/api/app/friends/{student_id}")
async def remove_friend(student_id: int, user_id: int = Depends(current_user)) -> dict:
    if student_id == user_id or not await db.remove_friend(user_id, student_id):
        raise HTTPException(404, "Студент не найден среди друзей")
    return {"removed": True, "userId": student_id}


async def profile_or_403(user_id: int) -> dict:
    profile = await db.get_profile(user_id)
    if not profile:
        raise HTTPException(403, "Сначала подтвердите профиль студента")
    return profile


@app.get("/api/schedule/today")
@app.get("/api/app/schedule/today")
async def schedule_today(user_id: int = Depends(current_user)) -> dict:
    return await schedule_by_date(date.today(), user_id)


@app.get("/api/schedule")
@app.get("/api/app/schedule")
async def schedule_date(date_value: date = Query(alias="date"), user_id: int = Depends(current_user)) -> dict:
    return await schedule_by_date(date_value, user_id)


async def schedule_by_date(target: date, user_id: int) -> dict:
    profile = await profile_or_403(user_id)
    try:
        return await bsuir.schedule_for_date(profile["group_number"], target, profile["subgroup"])
    except Exception:
        raise HTTPException(503, "Расписание временно недоступно, а сохранённого кэша для группы нет")


@app.get("/api/schedule/week")
@app.get("/api/app/schedule/week")
async def schedule_week(user_id: int = Depends(current_user)) -> dict:
    monday = date.today() - timedelta(days=date.today().weekday())
    days = []
    for offset in range(7):
        try:
            days.append(await schedule_by_date(monday + timedelta(days=offset), user_id))
        except HTTPException:
            continue
    return {"weekStart": monday, "days": days}


@app.get("/api/exams")
@app.get("/api/app/exams")
async def exams(user_id: int = Depends(current_user)) -> dict:
    profile = await profile_or_403(user_id)
    try:
        return {"items": await bsuir.exams(profile["group_number"], profile["subgroup"])}
    except Exception:
        raise HTTPException(503, "Экзамены временно недоступны")


@app.post("/api/app/notifications/subscribe")
async def subscribe_notifications(payload: NotificationRequest, user_id: int = Depends(current_user)) -> dict:
    await db.set_notification(user_id, payload.type, True)
    return {"enabled": True, "type": payload.type}


@app.delete("/api/app/notifications/subscribe")
async def unsubscribe_notifications(payload: NotificationRequest, user_id: int = Depends(current_user)) -> dict:
    await db.set_notification(user_id, payload.type, False)
    return {"enabled": False, "type": payload.type}


frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
