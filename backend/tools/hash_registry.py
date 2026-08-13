"""Generate a registry hash without writing the personal number to the registry."""

from __future__ import annotations

import argparse
import hashlib


parser = argparse.ArgumentParser()
parser.add_argument("personal_number")
parser.add_argument("pepper")
args = parser.parse_args()
normalized = "".join(character for character in args.personal_number if character.isalnum()).upper()
print(hashlib.sha256(f"{args.pepper}:{normalized}".encode()).hexdigest())

