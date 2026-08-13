from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx

from ..db import Database

DAY_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def parse_bsuir_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def teacher_name(employees: list[dict[str, Any]]) -> str | None:
    names = []
    for person in employees or []:
        full = " ".join(filter(None, [person.get("lastName"), person.get("firstName"), person.get("middleName")]))
        if full:
            names.append(full)
    return ", ".join(names) or None


class BsuirScheduleClient:
    def __init__(self, base_url: str, db: Database, timeout: float = 12.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.db = db
        self.timeout = timeout

    async def fetch_group_schedule(self, group: str) -> tuple[dict[str, Any], str, bool]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/schedule", params={"studentGroup": group})
                response.raise_for_status()
                payload = response.json()
                update = await self.fetch_last_update(group, client)
                await self.db.save_cache(group, payload, update)
                return payload, "live", False
        except (httpx.HTTPError, ValueError):
            cached = await self.db.get_cache(group)
            if cached:
                return cached["schedule"], "cache", True
            raise

    async def fetch_last_update(self, group: str, client: httpx.AsyncClient) -> str | None:
        try:
            response = await client.get(f"{self.base_url}/last-update-date/student-group", params={"groupNumber": group})
            response.raise_for_status()
            data = response.json()
            return str(data) if data is not None else None
        except (httpx.HTTPError, ValueError):
            return None

    async def current_week(self) -> int | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/schedule/current-week")
                response.raise_for_status()
                return int(response.json())
        except (httpx.HTTPError, ValueError, TypeError):
            return None

    async def schedule_for_date(self, group: str, target: date, subgroup: int | None) -> dict[str, Any]:
        payload, source, stale = await self.fetch_group_schedule(group)
        week_number = await self.current_week()
        day_entries = payload.get("schedules", {}).get(DAY_NAMES[target.weekday()], [])
        items = []
        for entry in day_entries:
            if not self._applies(entry, target, week_number, subgroup):
                continue
            items.append(self._normalize(entry, target, group))
        items.sort(key=lambda item: item["startTime"])
        return {"date": target, "weekNumber": week_number, "groupNumber": group, "items": items,
                "source": source, "stale": stale,
                "message": "Показан сохранённый кэш: API БГУИР временно недоступен." if stale else None}

    @staticmethod
    def _applies(entry: dict[str, Any], target: date, week_number: int | None, subgroup: int | None) -> bool:
        exact = parse_bsuir_date(entry.get("dateLesson"))
        start = parse_bsuir_date(entry.get("startLessonDate"))
        end = parse_bsuir_date(entry.get("endLessonDate"))
        if exact and exact != target:
            return False
        if start and target < start:
            return False
        if end and target > end:
            return False
        weeks = entry.get("weekNumber") or []
        if week_number is not None and weeks and week_number not in weeks and not exact:
            return False
        entry_subgroup = entry.get("numSubgroup") or 0
        return subgroup is None or entry_subgroup == 0 or entry_subgroup == subgroup

    @staticmethod
    def _normalize(entry: dict[str, Any], target: date, group: str) -> dict[str, Any]:
        note = entry.get("note")
        changed = bool(entry.get("announcement") or entry.get("dateLesson") or note)
        return {"date": target, "startTime": entry.get("startLessonTime", ""), "endTime": entry.get("endLessonTime", ""),
                "subject": entry.get("subjectFullName") or entry.get("subject") or "Без названия",
                "lessonType": entry.get("lessonTypeAbbrev") or "Занятие", "room": ", ".join(entry.get("auditories") or []) or None,
                "teacher": teacher_name(entry.get("employees") or []), "subgroup": entry.get("numSubgroup") or None,
                "note": note, "changed": changed, "announcement": bool(entry.get("announcement")), "exam": False}

    async def exams(self, group: str, subgroup: int | None) -> list[dict[str, Any]]:
        payload, _, _ = await self.fetch_group_schedule(group)
        result = []
        for entry in payload.get("exams", []) or []:
            exact = parse_bsuir_date(entry.get("dateLesson"))
            if exact and (subgroup is None or (entry.get("numSubgroup") or 0) in (0, subgroup)):
                item = self._normalize(entry, exact, group)
                item["exam"] = True
                result.append(item)
        return sorted(result, key=lambda item: (item["date"], item["startTime"]))

