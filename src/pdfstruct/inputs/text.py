"""Plain text and Markdown adapters (standard library only)."""
from __future__ import annotations

import re
from pathlib import Path

from . import unpaged_page

_LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$")
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:\s+(.*?))?(?:\s+#+)?\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_RULE = re.compile(r"^ {0,3}([-*_])(?:\s*\1){2,}\s*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)\s*$")


def decode(data: bytes) -> tuple[str, list[str]]:
    """Bytes -> text. UTF-8 (with or without BOM) first; a fallback is reported, never hidden."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), []
    try:
        return data.decode("utf-8-sig"), []
    except UnicodeDecodeError:
        pass
    for encoding in ("cp1252", "latin-1"):
        try:
            return data.decode(encoding), [
                f"encoding_fallback: not valid UTF-8, decoded as {encoding} (a guess; "
                "characters may be wrong)"]
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), ["encoding_fallback: undecodable bytes replaced"]


def _lines(path: Path) -> tuple[list[str], list[str]]:
    text, warnings = decode(path.read_bytes())
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), warnings


def read_txt(path: Path) -> dict:
    """Paragraphs are separated by blank lines; line breaks inside a paragraph are kept."""
    lines, warnings = _lines(path)
    blocks, current = [], []
    for line in [*lines, ""]:
        if line.strip():
            current.append(line.rstrip())
        elif current:
            blocks.append({"text": "\n".join(current), "kind": "paragraph"})
            current = []
    return {"pages": [unpaged_page(blocks)], "paged": False, "warnings": warnings,
            "coordinate_system": None}


def read_markdown(path: Path) -> dict:
    """Headings, paragraphs, list items and fenced code, deterministically.

    Tables, block quotes, embedded HTML and inline markup stay as literal text:
    nothing is interpreted, rendered or executed.
    """
    lines, warnings = _lines(path)
    blocks: list[dict] = []
    paragraph: list[str] = []
    fence = None
    code: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append({"text": "\n".join(paragraph), "kind": "paragraph"})
            paragraph.clear()

    for line in lines:
        if fence is not None:
            if line.strip().startswith(fence) and not line.strip().strip(fence[0]):
                blocks.append({"text": "\n".join(code), "kind": "code"})
                fence, code = None, []
            else:
                code.append(line.rstrip("\n"))
            continue
        opened = _FENCE.match(line)
        if opened:
            flush()
            fence = opened.group(1)
            continue
        if not line.strip():
            flush()
            continue
        heading = _ATX.match(line)
        if heading:
            flush()
            if (heading.group(2) or "").strip():
                blocks.append({"text": heading.group(2).strip(), "kind": "heading",
                               "level": len(heading.group(1))})
            continue
        if paragraph and len(paragraph) == 1 and _SETEXT.match(line):
            blocks.append({"text": paragraph[0].strip(), "kind": "heading",
                           "level": 1 if line.strip().startswith("=") else 2})
            paragraph.clear()
            continue
        if _RULE.match(line):
            flush()
            continue
        item = _LIST_ITEM.match(line)
        if item:
            flush()
            indent = len(item.group(1).expandtabs(4))
            blocks.append({"text": item.group(3).strip(), "kind": "list_item",
                           "level": min(indent // 2 + 1, 6),
                           "ordered": item.group(2)[0].isdigit()})
            continue
        if not paragraph and blocks and blocks[-1]["kind"] == "list_item" and line[:1] in " \t":
            blocks[-1]["text"] += "\n" + line.strip()  # indented continuation of a list item
            continue
        paragraph.append(line.rstrip())
    if fence is not None:  # unclosed fence: keep the text, do not guess
        blocks.append({"text": "\n".join(code), "kind": "code"})
    flush()
    return {"pages": [unpaged_page(blocks)], "paged": False, "warnings": warnings,
            "coordinate_system": None}
