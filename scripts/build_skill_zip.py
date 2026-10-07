#!/usr/bin/env python3
"""Build dist/pdfstruct-skill.zip from skills/pdfstruct (instructions only, no engine).

    python scripts/build_skill_zip.py            -> dist/pdfstruct-skill.zip
    python scripts/build_skill_zip.py --check    -> also verify an existing zip

The archive has exactly one top-level folder: pdfstruct/SKILL.md. It is a release
artifact and is not committed.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "pdfstruct"
TARGET = ROOT / "dist" / "pdfstruct-skill.zip"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)  # reproducible archive
MAX_SKILL_BYTES = 64 * 1024


def frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with a YAML front matter block")
    block = text[4:text.index("\n---", 4)]
    fields = {}
    for line in block.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def validate(text: str) -> dict:
    fields = frontmatter(text)
    if fields.get("name") != "pdfstruct":
        raise ValueError("front matter 'name' must be pdfstruct (same as the folder)")
    description = fields.get("description", "")
    if not 20 <= len(description) <= 1024:
        raise ValueError("front matter 'description' must be 20-1024 characters")
    return fields


def build() -> Path:
    files = sorted(p for p in SKILL_DIR.rglob("*") if p.is_file())
    validate((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            info = zipfile.ZipInfo(f"pdfstruct/{path.relative_to(SKILL_DIR).as_posix()}", FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes().replace(b"\r\n", b"\n"))
    return TARGET


def check(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if "pdfstruct/SKILL.md" not in names:
            raise ValueError("pdfstruct/SKILL.md missing from the archive")
        if any(not name.startswith("pdfstruct/") for name in names):
            raise ValueError(f"unexpected top-level entries: {names}")
        heavy = [n for n in names if n.lower().endswith((".py", ".exe", ".dll", ".pdmodel", ".onnx", ".whl"))]
        if heavy or sum(i.file_size for i in archive.infolist()) > MAX_SKILL_BYTES:
            raise ValueError("the skill must contain instructions only (no engine, no models)")
        validate(archive.read("pdfstruct/SKILL.md").decode("utf-8"))
        return names


def main() -> int:
    target = build()
    names = check(target)
    print(f"SKILL_ZIP: {target}")
    print(f"ENTRIES: {', '.join(names)}")
    print(f"SIZE: {target.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
