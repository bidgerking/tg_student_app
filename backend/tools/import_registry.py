"""Import an administrator Excel roster without storing clear personal numbers."""

from __future__ import annotations

import argparse

from app.config import get_settings
from app.services.registry import import_excel_registry


parser = argparse.ArgumentParser()
parser.add_argument("input", help="Path to the administrator .xlsx file")
parser.add_argument("--output", default=None, help="Output JSON registry path")
args = parser.parse_args()
settings = get_settings()
if not settings.student_registry_pepper or settings.student_registry_pepper == "change-me":
    raise SystemExit("Configure STUDENT_REGISTRY_PEPPER before importing a roster.")
output_path = args.output or settings.student_registry_path
count = import_excel_registry(args.input, output_path, settings.student_registry_pepper)
print(f"Imported {count} validated student records into {output_path}.")
