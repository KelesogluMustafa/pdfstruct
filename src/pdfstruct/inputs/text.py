"""Plain text and Markdown adapters (standard library only)."""
from __future__ import annotations

import re
from pathlib import Path

from . import table_text, unpaged_page

_LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$")
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:\s+(.*?))?(?:\s+#+)?\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_RULE = re.compile(r"^ {0,3}([-*_])(?:\s*\1){2,}\s*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)\s*$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
_CELL_SPLIT = re.compile(r"(?<!\\)\|")
LINK_SCHEMES = ("http://", "https://", "mailto:")
# {{PLACEHOLDER}} comes first: template placeholders are never read as markup.
_INLINE = re.compile(r"""
    (?P<placeholder>\{\{.*?\}\})
  | \\(?P<escaped>[\\`*_{}\[\]()\#+\-.!|<>~])
  | (?P<tick>`+)(?P<code>.+?)(?P=tick)(?!`)
  | !\[(?P<alt>[^\]]*)\]\((?P<src>[^()\s]*)(?:\s+"[^"]*")?\)
  | \[(?P<label>[^\]]+)\]\((?P<href>[^()\s]+)(?:\s+"[^"]*")?\)
  | <(?P<auto>(?:https?://|mailto:)[^<>\s]+)>
  | \*\*\*(?=\S)(?P<bold_italic>.+?)(?<=\S)\*\*\*
  | \*\*(?=\S)(?P<bold>.+?)(?<=\S)\*\*
  | (?<!\w)__(?=\S)(?P<bold_u>.+?)(?<=\S)__(?!\w)
  | \*(?=\S)(?P<italic>[^*]+?)(?<=\S)\*
  | (?<!\w)_(?=\S)(?P<italic_u>[^_]+?)(?<=\S)_(?!\w)
""", re.VERBOSE)


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


def split_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _lines(path: Path) -> tuple[list[str], list[str]]:
    text, warnings = decode(path.read_bytes())
    return split_lines(text), warnings


def text_blocks(lines: list[str]) -> list[dict]:
    """Paragraphs are separated by blank lines; line breaks inside a paragraph are kept."""
    blocks, current = [], []
    for line in [*lines, ""]:
        if line.strip():
            current.append(line.rstrip())
        elif current:
            blocks.append({"text": "\n".join(current), "kind": "paragraph"})
            current = []
    return blocks


def read_txt(path: Path) -> dict:
    lines, warnings = _lines(path)
    return {"pages": [unpaged_page(text_blocks(lines))], "paged": False, "warnings": warnings,
            "coordinate_system": None}


def inline_spans(text: str, bold: bool = False, italic: bool = False,
                 href: str | None = None) -> list[dict]:
    """Inline Markdown as styled pieces: {"text", "bold", "italic", "code", "href"}.

    Bold, italic, code spans, links and backslash escapes are read. Embedded HTML stays
    literal text, an image becomes its alt text, and only http, https and mailto links
    keep their target; any other target is written out as text.
    """
    spans: list[dict] = []

    def add(piece: str, **style) -> None:
        if piece:
            spans.append({"text": piece, "bold": bold, "italic": italic, "code": False,
                          "href": href, **style})

    position = 0
    for match in _INLINE.finditer(text):
        add(text[position:match.start()])
        position = match.end()
        found = match.groupdict()
        if found["placeholder"] is not None:
            add(found["placeholder"])
        elif found["escaped"] is not None:
            add(found["escaped"])
        elif found["code"] is not None:
            add(found["code"].strip() or found["code"], code=True)
        elif found["src"] is not None:
            add(found["alt"] or found["src"])
        elif found["href"] is not None:
            if found["href"].lower().startswith(LINK_SCHEMES):
                spans += inline_spans(found["label"], bold, italic, found["href"])
            else:
                spans += inline_spans(found["label"], bold, italic, href)
                add(f" ({found['href']})")
        elif found["auto"] is not None:
            add(found["auto"], href=found["auto"])
        elif found["bold_italic"] is not None:
            spans += inline_spans(found["bold_italic"], True, True, href)
        elif found["bold"] is not None or found["bold_u"] is not None:
            spans += inline_spans(found["bold"] or found["bold_u"], True, italic, href)
        else:
            spans += inline_spans(found["italic"] or found["italic_u"], bold, True, href)
    add(text[position:])
    return spans


def spans_text(spans: list[dict]) -> str:
    """Plain text of styled pieces; a link target that the text does not show is appended."""
    out, index = [], 0
    while index < len(spans):
        target = spans[index]["href"]
        label = ""
        while index < len(spans) and spans[index]["href"] == target:
            label += spans[index]["text"]
            index += 1
        shown = target and target not in (label, "mailto:" + label)
        out.append(f"{label} ({target})" if shown else label)
    return "".join(out)


def _table_cells(line: str) -> list[str]:
    body = line.strip()
    body = body[1:] if body.startswith("|") else body
    body = body[:-1] if body.endswith("|") and not body.endswith("\\|") else body
    return [cell.strip().replace("\\|", "|") for cell in _CELL_SPLIT.split(body)]


def _join_soft(lines: list[str]) -> str:
    """Markdown line endings: two spaces or a backslash break the line, anything else is a space."""
    out = ""
    for line in lines:
        body = line.strip()
        hard = line.endswith("  ") or body.endswith("\\")
        out += (body[:-1].rstrip() if body.endswith("\\") else body) + ("\n" if hard else " ")
    return out.strip()


def markdown_blocks(lines: list[str], rich: bool = False) -> list[dict]:
    """Headings, paragraphs, list items and fenced code, deterministically.

    Tables, block quotes, embedded HTML and inline markup stay as literal text:
    nothing is interpreted, rendered or executed.

    rich=True (documents created from text, never file inputs) also reads simple pipe
    tables as table_row blocks, horizontal rules as "rule" blocks and inline markup as
    `spans` next to the plain `text`. Embedded HTML still stays literal text.
    """
    blocks: list[dict] = []
    paragraph: list[str] = []
    fence = None
    code: list[str] = []
    table = None
    tables = 0

    def flush() -> None:
        if paragraph:
            blocks.append({"text": _join_soft(paragraph) if rich else "\n".join(paragraph),
                           "kind": "paragraph"})
            paragraph.clear()

    def table_row(line: str) -> None:
        cells = _table_cells(line)
        blocks.append({"text": table_text(cells), "kind": "table_row", "cells": cells,
                       "table": table})

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
        if table is not None:
            if "|" in line:
                table_row(line)
                continue
            table = None
        if not line.strip():
            flush()
            continue
        if (rich and len(paragraph) == 1 and "|" in paragraph[0] + line and _TABLE_RULE.match(line)
                and len(_table_cells(line)) == len(_table_cells(paragraph[0]))):
            table = tables = tables + 1
            table_row(paragraph.pop())
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
            if rich:
                blocks.append({"text": "", "kind": "rule"})
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
            blocks[-1]["text"] += ("\n", " ")[rich] + line.strip()  # continuation of a list item
            continue
        paragraph.append(line if rich else line.rstrip())
    if fence is not None:  # unclosed fence: keep the text, do not guess
        blocks.append({"text": "\n".join(code), "kind": "code"})
    flush()
    for block in blocks if rich else []:
        if block["kind"] == "table_row":
            block["cell_spans"] = [inline_spans(cell) for cell in block["cells"]]
            block["cells"] = [spans_text(spans) for spans in block["cell_spans"]]
            block["text"] = table_text(block["cells"])
        elif block["kind"] not in ("code", "rule"):
            block["spans"] = inline_spans(block["text"])
            block["text"] = spans_text(block["spans"])
    return blocks


def read_markdown(path: Path) -> dict:
    lines, warnings = _lines(path)
    return {"pages": [unpaged_page(markdown_blocks(lines))], "paged": False, "warnings": warnings,
            "coordinate_system": None}
