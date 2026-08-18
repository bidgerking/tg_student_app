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
                    name TEXT NOT NULL DEFAULT '',
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
                CREATE TABLE IF NOT EXISTS friendships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    friend_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    requested_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'accepted')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, friend_id),
                    CHECK(user_id < friend_id)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    remember_me INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT '',
                    last_used_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS account_credentials (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    personal_number_hash TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT
                );
                CREATE TABLE IF NOT EXISTS pending_verifications (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    candidate_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                """
            )
            cursor = await db.execute("PRAGMA table_info(student_profiles)")
            columns = {row[1] for row in await cursor.fetchall()}
            if "name" not in columns:
                await db.execute("ALTER TABLE student_profiles ADD COLUMN name TEXT NOT NULL DEFAULT ''")
            cursor = await db.execute("PRAGMA table_info(sessions)")
            session_columns = {row[1] for row in await cursor.fetchall()}
            if "remember_me" not in session_columns:
                await db.execute("ALTER TABLE sessions ADD COLUMN remember_me INTEGER NOT NULL DEFAULT 0")
            if "created_at" not in session_columns:
                await db.execute("ALTER TABLE sessions ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
            if "last_used_at" not in session_columns:
                await db.execute("ALTER TABLE sessions ADD COLUMN last_used_at TEXT NOT NULL DEFAULT ''")
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

    async def save_session(self, token_hash: str, user_id: int, expires_at: str, remember_me: bool = False) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at, remember_me, created_at, last_used_at) VALUES (?, ?, ?, ?, ?, ?)",
                (token_hash, user_id, expires_at, int(remember_me), now, now),
            )
            await db.commit()

    async def get_user_id_by_session(self, token_hash: str) -> int | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT user_id, expires_at FROM sessions WHERE token_hash = ?", (token_hash,))
            row = await cursor.fetchone()
            if row:
                await db.execute("UPDATE sessions SET last_used_at = ? WHERE token_hash = ?", (datetime.now(timezone.utc).isoformat(), token_hash))
                await db.commit()
        if not row or datetime.fromisoformat(row[1]) <= datetime.now(timezone.utc):
            return None
        return int(row[0])

    async def get_session(self, token_hash: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM sessions WHERE token_hash = ?", (token_hash,))
            row = await cursor.fetchone()
        if not row or datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            return None
        return dict(row)

    async def delete_session(self, token_hash: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            await db.commit()

    async def delete_user_sessions(self, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            await db.commit()

    async def get_credentials_by_personal_hash(self, personal_number_hash: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM account_credentials WHERE personal_number_hash = ?", (personal_number_hash,))
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_credentials(self, user_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM account_credentials WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def create_account(self, user_id: int, profile: dict[str, Any], password_hash: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute("BEGIN")
            await db.execute(
                """INSERT INTO account_credentials (user_id, personal_number_hash, password_hash, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET personal_number_hash=excluded.personal_number_hash,
                password_hash=excluded.password_hash""",
                (user_id, profile["personal_number_hash"], password_hash, now),
            )
            await db.execute(
                """INSERT INTO student_profiles
                (user_id, name, personal_number_hash, faculty_id, faculty_name, speciality_id,
                speciality_name, course, group_number, subgroup, education_form, student_status, verified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET personal_number_hash=excluded.personal_number_hash,
                name=excluded.name, faculty_id=excluded.faculty_id, faculty_name=excluded.faculty_name,
                speciality_id=excluded.speciality_id, speciality_name=excluded.speciality_name,
                course=excluded.course, group_number=excluded.group_number, subgroup=excluded.subgroup,
                education_form=excluded.education_form, student_status=excluded.student_status,
                verified_at=excluded.verified_at""",
                (user_id, profile.get("name", ""), profile["personal_number_hash"], profile.get("faculty_id"), profile["faculty_name"],
                 profile.get("speciality_id"), profile["speciality_name"], profile.get("course"), profile["group_number"],
                 profile.get("subgroup"), profile.get("education_form"), profile["student_status"], profile["verified_at"]),
            )
            await db.commit()

    async def mark_login(self, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE account_credentials SET last_login_at = ? WHERE user_id = ?", (datetime.now(timezone.utc).isoformat(), user_id))
            await db.commit()

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
                (user_id, name, personal_number_hash, faculty_id, faculty_name, speciality_id,
                speciality_name, course, group_number, subgroup, education_form,
                student_status, verified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET personal_number_hash=excluded.personal_number_hash,
                name=excluded.name,
                faculty_id=excluded.faculty_id, faculty_name=excluded.faculty_name,
                speciality_id=excluded.speciality_id, speciality_name=excluded.speciality_name,
                course=excluded.course, group_number=excluded.group_number, subgroup=excluded.subgroup,
                education_form=excluded.education_form, student_status=excluded.student_status,
                verified_at=excluded.verified_at""",
                (user_id, data.get("name", ""), data["personal_number_hash"], data.get("faculty_id"), data["faculty_name"],
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

    @staticmethod
    def _friend_pair(user_id: int, friend_id: int) -> tuple[int, int]:
        return (user_id, friend_id) if user_id < friend_id else (friend_id, user_id)

    async def get_profile_by_personal_hash(self, personal_number_hash: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM student_profiles WHERE personal_number_hash = ?", (personal_number_hash,))
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def search_profiles(self, query: str, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        pattern = f"%{query.strip()}%"
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT user_id, name, faculty_name, speciality_name, course, group_number, subgroup, student_status
                   FROM student_profiles
                   WHERE user_id != ? AND student_status = 'active'
                     AND (name LIKE ? COLLATE NOCASE OR group_number LIKE ? COLLATE NOCASE)
                   ORDER BY name COLLATE NOCASE LIMIT ?""",
                (user_id, pattern, pattern, limit),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_friendship(self, user_id: int, friend_id: int) -> dict[str, Any] | None:
        first, second = self._friend_pair(user_id, friend_id)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM friendships WHERE user_id = ? AND friend_id = ?", (first, second))
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_friendships(self, user_id: int) -> dict[str, list[dict[str, Any]]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT f.id AS request_id, f.status, f.requested_by, f.created_at,
                          p.user_id AS student_id, p.name, p.faculty_name, p.speciality_name,
                          p.course, p.group_number, p.subgroup, p.student_status
                   FROM friendships f
                   JOIN student_profiles p ON p.user_id = CASE WHEN f.user_id = ? THEN f.friend_id ELSE f.user_id END
                   WHERE f.user_id = ? OR f.friend_id = ?
                   ORDER BY p.name COLLATE NOCASE""",
                (user_id, user_id, user_id),
            )
            rows = [dict(row) for row in await cursor.fetchall()]
        result = {"friends": [], "incoming": [], "outgoing": []}
        for row in rows:
            item = {
                "requestId": row["request_id"],
                "userId": row["student_id"],
                "name": row["name"],
                "faculty_name": row["faculty_name"],
                "speciality_name": row["speciality_name"],
                "course": row["course"],
                "group_number": row["group_number"],
                "subgroup": row["subgroup"],
                "student_status": row["student_status"],
                "createdAt": row["created_at"],
            }
            if row["status"] == "accepted":
                result["friends"].append(item)
            elif row["requested_by"] == user_id:
                result["outgoing"].append(item)
            else:
                result["incoming"].append(item)
        return result

    async def create_friend_request(self, user_id: int, friend_id: int) -> dict[str, Any]:
        first, second = self._friend_pair(user_id, friend_id)
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM friendships WHERE user_id = ? AND friend_id = ?", (first, second))
            existing = await cursor.fetchone()
            if existing:
                return dict(existing)
            await db.execute(
                "INSERT OR IGNORE INTO friendships (user_id, friend_id, requested_by, status, created_at, updated_at) VALUES (?, ?, ?, 'pending', ?, ?)",
                (first, second, user_id, now, now),
            )
            cursor = await db.execute("SELECT * FROM friendships WHERE user_id = ? AND friend_id = ?", (first, second))
            created = await cursor.fetchone()
            await db.commit()
        return dict(created)

    async def accept_friend_request(self, request_id: int, user_id: int) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "UPDATE friendships SET status = 'accepted', updated_at = ? WHERE id = ? AND (user_id = ? OR friend_id = ?) AND requested_by != ? AND status = 'pending'",
                (now, request_id, user_id, user_id, user_id),
            )
            await db.commit()
        return cursor.rowcount == 1

    async def delete_friend_request(self, request_id: int, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "DELETE FROM friendships WHERE id = ? AND (user_id = ? OR friend_id = ?) AND status = 'pending'",
                (request_id, user_id, user_id),
            )
            await db.commit()
        return cursor.rowcount == 1

    async def remove_friend(self, user_id: int, friend_id: int) -> bool:
        first, second = self._friend_pair(user_id, friend_id)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("DELETE FROM friendships WHERE user_id = ? AND friend_id = ? AND status = 'accepted'", (first, second))
            await db.commit()
        return cursor.rowcount == 1

    async def delete_profile(self, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM student_profiles WHERE user_id = ?", (user_id,))
            await db.commit()
