from __future__ import annotations

import json
import os
import tempfile
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


ALLOWED_STATUSES = {"active", "inactive", "academic_leave", "graduated", "expelled"}


def import_excel_registry(input_path: str, output_path: str, pepper: str) -> int:
    """Validate an administrator workbook and write only hashed identifiers to JSON."""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("Установите зависимость openpyxl перед импортом Excel.") from exc

    workbook = load_workbook(input_path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    raw_headers = next(rows, None)
    if not raw_headers:
        raise ValueError("Excel-файл пуст.")
    aliases = {
        "personal_number": "personal_number", "personalnumber": "personal_number", "личный номер": "personal_number",
        "full_name": "full_name", "name": "full_name", "фио": "full_name",
        "faculty": "faculty", "факультет": "faculty", "speciality": "speciality", "specialty": "speciality",
        "специальность": "speciality", "course": "course", "курс": "course",
        "group_number": "group_number", "group": "group_number", "группа": "group_number",
        "subgroup": "subgroup", "подгруппа": "subgroup", "status": "status", "статус": "status",
        "faculty_id": "faculty_id", "speciality_id": "speciality_id", "education_form": "education_form",
    }
    headers = [aliases.get(str(value or "").strip().casefold().replace(" ", "_"), "") for value in raw_headers]
    required = {"personal_number", "group_number", "status"}
    if not required.issubset(set(headers)):
        missing = ", ".join(sorted(required - set(headers)))
        raise ValueError(f"В Excel отсутствуют обязательные поля: {missing}.")
    index = {header: position for position, header in enumerate(headers) if header}
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    errors: list[str] = []
    for row_number, values in enumerate(rows, start=2):
        if not any(value not in (None, "") for value in values):
            continue
        raw_number = str(values[index["personal_number"]] or "").strip()
        normalized = "".join(character for character in raw_number if character.isalnum()).upper()
        group = str(values[index["group_number"]] or "").strip()
        status = str(values[index["status"]] or "").strip().casefold()
        if not normalized or not group or status not in ALLOWED_STATUSES:
            errors.append(f"строка {row_number}: пустое обязательное поле или некорректный статус")
            continue
        number_hash = hash_personal_number(normalized, pepper)
        if number_hash in seen:
            errors.append(f"строка {row_number}: дубликат личного номера")
            continue
        seen.add(number_hash)
        record = {
            "personalNumberHash": number_hash,
            "name": str(values[index["full_name"]] or "").strip() if "full_name" in index else "",
            "faculty": str(values[index["faculty"]] or "").strip() if "faculty" in index else "",
            "speciality": str(values[index["speciality"]] or "").strip() if "speciality" in index else "",
            "course": values[index["course"]] if "course" in index else None,
            "group": group,
            "subgroup": values[index["subgroup"]] if "subgroup" in index else None,
            "status": status,
        }
        for optional in ("faculty_id", "speciality_id", "education_form"):
            if optional in index:
                record_key = {"faculty_id": "facultyId", "speciality_id": "specialityId", "education_form": "educationForm"}[optional]
                record[record_key] = values[index[optional]]
        records.append(record)
    workbook.close()
    if errors:
        raise ValueError("Импорт отменён: " + "; ".join(errors[:5]))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="registry-", suffix=".json", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(records, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return len(records)
