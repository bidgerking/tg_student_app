"""Add the bundled development students to the local hashed registry."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.security import hash_personal_number


TEST_STUDENTS = (
    ("123456789", "Тестовый Студент", 1),
    ("123456790", "Тестовый Друг 1", 2),
    ("123456791", "Тестовый Друг 2", 1),
)


def main() -> None:
    settings = get_settings()
    if not settings.student_registry_pepper or settings.student_registry_pepper == "change-me":
        raise SystemExit("Укажите STUDENT_REGISTRY_PEPPER в backend/.env перед заполнением реестра.")

    path = Path(settings.student_registry_path)
    records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    known_hashes = {record.get("personalNumberHash") for record in records}
    for personal_number, name, subgroup in TEST_STUDENTS:
        number_hash = hash_personal_number(personal_number, settings.student_registry_pepper)
        if number_hash in known_hashes:
            continue
        records.append(
            {
                "personalNumberHash": number_hash,
                "name": name,
                "faculty": "ФКСиС",
                "facultyId": 20026,
                "speciality": "Информатика и технологии программирования",
                "specialityId": 20021,
                "course": 3,
                "group": "053503",
                "subgroup": subgroup,
                "educationForm": "очная",
                "status": "active",
            }
        )
        known_hashes.add(number_hash)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"В реестре {len(records)} записей: {path}")


if __name__ == "__main__":
    main()
