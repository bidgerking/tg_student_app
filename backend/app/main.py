from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import Database
from .models import ConfirmVerificationRequest, NotificationRequest, StudentVerificationRequest, TelegramAuthRequest
from .security import hash_personal_number, new_session_token, validate_telegram_init_data
from .services.bsuir import BsuirScheduleClient
from .services.registry import StudentRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()
db = Database(settings.database_path)
registry = StudentRegistry(settings.student_registry_path, settings.student_registry_pepper)
bsuir = BsuirScheduleClient(settings.bsuir_api_base_url, db)
app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

attempts: dict[int, list[datetime]] = {}


def public_profile(profile: dict | None) -> dict | None:
    if not profile:
        return None
    return {key: value for key, value in profile.items() if key not in {"personal_number_hash", "user_id", "id"}}


@app.on_event("startup")
async def startup() -> None:
    await db.init()


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Требуется авторизация Telegram Web App")
    return authorization[7:].strip()


async def current_user(authorization: str | None = Header(default=None)) -> int:
    token = bearer_token(authorization)
    user_id = await db.get_user_id_by_session(hashlib.sha256(token.encode()).hexdigest())
    if not user_id:
        raise HTTPException(401, "Сессия истекла, откройте приложение заново")
    return user_id


@app.post("/api/app/telegram/auth")
async def telegram_auth(payload: TelegramAuthRequest) -> dict:
    try:
        tg_user = validate_telegram_init_data(payload.init_data, settings.bot_token, settings.telegram_init_data_max_age)
    except ValueError as exc:
        if not settings.dev_auth_enabled or payload.init_data != "dev-test-init-data":
            raise HTTPException(401, str(exc)) from exc
        tg_user = type("DevTelegramUser", (), {"telegram_id": settings.dev_telegram_id, "username": "bsuir_test_user", "first_name": "Тестовый", "last_name": "Студент"})()
    user_id = await db.upsert_user(tg_user.telegram_id, tg_user.username, tg_user.first_name)
    token = new_session_token()
    await db.save_session(hashlib.sha256(token.encode()).hexdigest(), user_id, (datetime.now(timezone.utc) + timedelta(days=7)).isoformat())
    profile = await db.get_profile(user_id)
    return {"accessToken": token, "user": {"telegramId": tg_user.telegram_id, "firstName": tg_user.first_name, "username": tg_user.username}, "profile": public_profile(profile)}


@app.post("/api/app/student/verify")
async def verify_student(payload: StudentVerificationRequest, user_id: int = Depends(current_user)) -> dict:
    now = datetime.now(timezone.utc)
    recent = [timestamp for timestamp in attempts.get(user_id, []) if now - timestamp < timedelta(hours=1)]
    if len(recent) >= settings.verification_attempts_per_hour:
        raise HTTPException(429, "Слишком много попыток. Повторите позже.")
    attempts[user_id] = [*recent, now]
    normalized = "".join(character for character in payload.personal_number if character.isalnum()).upper()
    candidate = registry.verify(normalized)
    if candidate is None:
        return {"verified": False, "error": "Номер не найден в доверенном реестре студентов."}
    token = secrets.token_urlsafe(24)
    candidate["personal_number_hash"] = hash_personal_number(normalized, settings.student_registry_pepper)
    candidate["verified_at"] = now.isoformat()
    await db.save_pending(hashlib.sha256(token.encode()).hexdigest(), user_id, candidate, (now + timedelta(minutes=10)).isoformat())
    public_candidate = {key: value for key, value in candidate.items() if key not in {"personal_number_hash", "verified_at"}}
    return {"verified": True, "verificationToken": token, "student": public_candidate}


@app.post("/api/app/student/confirm")
async def confirm_student(payload: ConfirmVerificationRequest, user_id: int = Depends(current_user)) -> dict:
    candidate = await db.consume_pending(hashlib.sha256(payload.verification_token.encode()).hexdigest(), user_id)
    if not candidate:
        raise HTTPException(400, "Данные проверки истекли. Проверьте личный номер ещё раз.")
    profile_data = {
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
    await db.save_profile(user_id, profile_data)
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


async def profile_or_403(user_id: int) -> dict:
    profile = await db.get_profile(user_id)
    if not profile:
        raise HTTPException(403, "Сначала подтвердите профиль студента")
    return profile


@app.get("/api/app/schedule/today")
async def schedule_today(user_id: int = Depends(current_user)) -> dict:
    return await schedule_by_date(date.today(), user_id)


@app.get("/api/app/schedule")
async def schedule_date(date_value: date = Query(alias="date"), user_id: int = Depends(current_user)) -> dict:
    return await schedule_by_date(date_value, user_id)


async def schedule_by_date(target: date, user_id: int) -> dict:
    profile = await profile_or_403(user_id)
    try:
        return await bsuir.schedule_for_date(profile["group_number"], target, profile["subgroup"])
    except Exception:
        raise HTTPException(503, "Расписание временно недоступно, а сохранённого кэша для группы нет.")


@app.get("/api/app/schedule/week")
async def schedule_week(user_id: int = Depends(current_user)) -> dict:
    target = date.today()
    monday = target - timedelta(days=target.weekday())
    items = []
    for offset in range(7):
        try:
            items.append(await schedule_by_date(monday + timedelta(days=offset), user_id))
        except HTTPException:
            continue
    return {"weekStart": monday, "days": items}


@app.get("/api/app/exams")
async def exams(user_id: int = Depends(current_user)) -> dict:
    profile = await profile_or_403(user_id)
    try:
        return {"items": await bsuir.exams(profile["group_number"], profile["subgroup"])}
    except Exception:
        raise HTTPException(503, "Экзамены временно недоступны.")


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
