"""Add the bundled development students to the local hashed registry."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.security import hash_personal_number


TEST_STUDENTS = (
    {"personal_number": "123456789", "name": "Тестовый Студент", "group": "624401", "subgroup": 1},
    {"personal_number": "123456790", "name": "Тестовый Друг 1", "group": "053503", "subgroup": 2},
    {"personal_number": "123456791", "name": "Тестовый Друг 2", "group": "053503", "subgroup": 1},
)


def main() -> None:
    settings = get_settings()
    if not settings.student_registry_pepper or settings.student_registry_pepper == "change-me":
        raise SystemExit("Укажите STUDENT_REGISTRY_PEPPER в backend/.env перед заполнением реестра.")

    path = Path(settings.student_registry_path)
    records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    records_by_hash = {record.get("personalNumberHash"): record for record in records}
    for student in TEST_STUDENTS:
        number_hash = hash_personal_number(student["personal_number"], settings.student_registry_pepper)
        record = records_by_hash.get(number_hash)
        if record is None:
            record = {
                "personalNumberHash": number_hash,
                "name": student["name"],
                "faculty": "ФКСиС",
                "facultyId": 20026,
                "speciality": "Информатика и технологии программирования",
                "specialityId": 20021,
                "course": 3,
                "educationForm": "очная",
                "status": "active",
            }
            records.append(record)
            records_by_hash[number_hash] = record
        record.update({"name": student["name"], "group": student["group"], "subgroup": student["subgroup"]})

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"В реестре {len(records)} записей: {path}")


if __name__ == "__main__":
    main()
