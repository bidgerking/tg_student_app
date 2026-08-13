from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..security import hash_personal_number


class StudentRegistry:
    """Trusted verification source backed by an admin-managed JSON registry."""

    def __init__(self, path: str, pepper: str) -> None:
        self.path = Path(path)
        self.pepper = pepper

    def verify(self, personal_number: str) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            records = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        target_hash = hash_personal_number(personal_number, self.pepper)
        for record in records:
            if record.get("personalNumberHash") == target_hash:
                return {
                    "name": record["name"],
                    "faculty": record.get("faculty", ""),
                    "facultyId": record.get("facultyId"),
                    "speciality": record.get("speciality", ""),
                    "specialityId": record.get("specialityId"),
                    "course": record.get("course"),
                    "group": record["group"],
                    "subgroup": record.get("subgroup"),
                    "educationForm": record.get("educationForm"),
                    "status": record.get("status", "active"),
                }
        return None

