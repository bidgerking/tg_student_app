from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


PASSWORD_HASHER = PasswordHasher()


@dataclass(frozen=True)
class TelegramUser:
    telegram_id: int
    username: str | None
    first_name: str
    last_name: str | None


def validate_telegram_init_data(init_data: str, bot_token: str, max_age: int) -> TelegramUser:
    """Validate Telegram Web App initData according to Telegram's HMAC protocol."""
    if not bot_token:
        raise ValueError("BOT_TOKEN is not configured")
    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop("hash", None)
    if not received_hash:
        raise ValueError("Telegram initData has no hash")

    check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid Telegram initData signature")

    auth_date = int(values.get("auth_date", "0"))
    if time.time() - auth_date > max_age:
        raise ValueError("Telegram initData has expired")

    try:
        user = json.loads(values["user"])
        return TelegramUser(
            telegram_id=int(user["id"]),
            username=user.get("username"),
            first_name=user.get("first_name", ""),
            last_name=user.get("last_name"),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Telegram initData does not contain a valid user") from exc


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def validate_password(password: str, personal_number: str) -> str | None:
    if len(password) < 10:
        return "Пароль должен содержать минимум 10 символов."
    if password != password.strip():
        return "Пароль не должен начинаться или заканчиваться пробелом."
    if personal_number and personal_number.casefold() in password.casefold():
        return "Пароль не должен совпадать с личным номером."
    return None


def hash_personal_number(personal_number: str, pepper: str) -> str:
    """Hash a personal number; the clear value never reaches logs or storage."""
    normalized = "".join(character for character in personal_number if character.isalnum()).upper()
    return hashlib.sha256(f"{pepper}:{normalized}".encode()).hexdigest()
