from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    async def init(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    username TEXT,
                    first_name TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS student_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    personal_number_hash TEXT NOT NULL,
                    faculty_id INTEGER,
                    faculty_name TEXT NOT NULL,
                    speciality_id INTEGER,
                    speciality_name TEXT NOT NULL,
                    course INTEGER,
                    group_number TEXT NOT NULL,
                    subgroup INTEGER,
                    education_form TEXT,
                    student_status TEXT NOT NULL,
                    verified_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS schedule_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_number TEXT NOT NULL UNIQUE,
                    schedule_json TEXT NOT NULL,
                    last_update_date TEXT,
                    cached_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    type TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, type)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pending_verifications (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    candidate_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                """
            )
            await db.commit()

    async def upsert_user(self, telegram_id: int, username: str | None, first_name: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO users (telegram_id, username, first_name, created_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username,
                first_name=excluded.first_name, last_seen_at=excluded.last_seen_at""",
                (telegram_id, username, first_name, now, now),
            )
            cursor = await db.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
            row = await cursor.fetchone()
            await db.commit()
        return int(row[0])

    async def save_session(self, token_hash: str, user_id: int, expires_at: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token_hash, user_id, expires_at))
            await db.commit()

    async def get_user_id_by_session(self, token_hash: str) -> int | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT user_id, expires_at FROM sessions WHERE token_hash = ?", (token_hash,))
            row = await cursor.fetchone()
        if not row or datetime.fromisoformat(row[1]) <= datetime.now(timezone.utc):
            return None
        return int(row[0])

    async def get_profile(self, user_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM student_profiles WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
        if not row:
            return None
        return dict(row)

    async def save_profile(self, user_id: int, data: dict[str, Any]) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO student_profiles
                (user_id, personal_number_hash, faculty_id, faculty_name, speciality_id,
                speciality_name, course, group_number, subgroup, education_form,
                student_status, verified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET personal_number_hash=excluded.personal_number_hash,
                faculty_id=excluded.faculty_id, faculty_name=excluded.faculty_name,
                speciality_id=excluded.speciality_id, speciality_name=excluded.speciality_name,
                course=excluded.course, group_number=excluded.group_number, subgroup=excluded.subgroup,
                education_form=excluded.education_form, student_status=excluded.student_status,
                verified_at=excluded.verified_at""",
                (user_id, data["personal_number_hash"], data.get("faculty_id"), data["faculty_name"],
                 data.get("speciality_id"), data["speciality_name"], data.get("course"), data["group_number"],
                 data.get("subgroup"), data.get("education_form"), data["student_status"], data["verified_at"]),
            )
            await db.commit()

    async def save_pending(self, token_hash: str, user_id: int, candidate: dict[str, Any], expires_at: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO pending_verifications VALUES (?, ?, ?, ?)",
                             (token_hash, user_id, json.dumps(candidate, ensure_ascii=False), expires_at))
            await db.commit()

    async def consume_pending(self, token_hash: str, user_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT candidate_json, expires_at FROM pending_verifications WHERE token_hash=? AND user_id=?",
                                      (token_hash, user_id))
            row = await cursor.fetchone()
            await db.execute("DELETE FROM pending_verifications WHERE token_hash = ?", (token_hash,))
            await db.commit()
        if not row or datetime.fromisoformat(row[1]) <= datetime.now(timezone.utc):
            return None
        return json.loads(row[0])

    async def get_cache(self, group_number: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT schedule_json, last_update_date, cached_at FROM schedule_cache WHERE group_number=?", (group_number,))
            row = await cursor.fetchone()
        if not row:
            return None
        return {"schedule": json.loads(row[0]), "last_update_date": row[1], "cached_at": row[2]}

    async def save_cache(self, group_number: str, schedule: dict[str, Any], last_update_date: str | None) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""INSERT INTO schedule_cache (group_number, schedule_json, last_update_date, cached_at)
            VALUES (?, ?, ?, ?) ON CONFLICT(group_number) DO UPDATE SET schedule_json=excluded.schedule_json,
            last_update_date=excluded.last_update_date, cached_at=excluded.cached_at""",
                             (group_number, json.dumps(schedule, ensure_ascii=False), last_update_date,
                              datetime.now(timezone.utc).isoformat()))
            await db.commit()

    async def set_notification(self, user_id: int, kind: str, enabled: bool) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""INSERT INTO notifications (user_id, type, enabled, created_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, type) DO UPDATE SET enabled=excluded.enabled""",
                             (user_id, kind, int(enabled), datetime.now(timezone.utc).isoformat()))
            await db.commit()

    async def delete_profile(self, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM student_profiles WHERE user_id = ?", (user_id,))
            await db.commit()

