"""Plain text and Markdown adapters (standard library only)."""
from __future__ import annotations

import re
from pathlib import Path

from . import table_text, unpaged_page

_LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_RULE = re.compile(r"^ {0,3}([-*_])(?:\s*\1){2,}\s*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)\s*$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
_CELL_SPLIT = re.compile(r"(?<!\\)\|")
LINK_SCHEMES = ("http://", "https://", "mailto:")
_SPECIAL = re.compile(r"[\\`*_\[!<{]")  # every inline construct starts with one of these
_ESCAPABLE = frozenset("\\`*_{}[]()#+-.!|<>~")
_LINK_TAIL = re.compile(r'\]\((?P<target>[^()\s]+)(?:\s+"[^"]{0,500}")?\)')
_IMAGE_TAIL = re.compile(r'\]\((?P<target>[^()\s]*)(?:\s+"[^"]{0,500}")?\)')
_AUTOLINK = re.compile(r"<((?:https?://|mailto:)[^<>\s]+)>")
_WORD = re.compile(r"\w")
MAX_TICKS = 16  # longest backtick run read as a code delimiter
MAX_SPANS = 2000  # a block with more styled pieces than this is kept as plain text
_STYLE_KEYS = ("bold", "italic", "code", "href")


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


def atx_heading(line: str) -> tuple[int, str] | None:
    """`## Title ##` -> (2, "Title"); None when the line is no heading. The text may be empty.

    Written out instead of one regular expression: that one needed quadratic time on a
    heading with a long run of spaces."""
    body = line.lstrip(" ")
    if len(line) - len(body) > 3:
        return None
    level = len(body) - len(body.lstrip("#"))
    rest = body[level:]
    if not 1 <= level <= 6 or (rest and not rest[0].isspace()):
        return None
    text = rest.strip()
    opening = text.rstrip("#")
    if opening != text:  # closing hashes count only after whitespace, and never alone
        text = opening.rstrip() if opening and opening[-1].isspace() else text
    return level, text


def inline_spans(text: str, bold: bool = False, italic: bool = False,
                 href: str | None = None) -> list[dict]:
    """Inline Markdown as styled pieces: {"text", "bold", "italic", "code", "href"}.

    Bold, italic, code spans, links and backslash escapes are read. Embedded HTML stays
    literal text, an image becomes its alt text, and only http, https and mailto links
    keep their target; any other target is written out as text. A {{PLACEHOLDER}} is
    template text and is never read as markup.

    One pass from left to right. A delimiter whose closing partner was searched for once
    and not found is not searched for again, so malformed text (thousands of unclosed
    `**` or `[`) costs linear time, not quadratic.
    """
    spans: list[dict] = []
    size = len(text)

    def add(piece: str, **style) -> None:
        if piece:
            spans.append({"text": piece, "bold": bold, "italic": italic, "code": False,
                          "href": href, **style})

    def nested(piece: str, **style) -> None:
        spans.extend(inline_spans(piece, style.get("bold", bold), style.get("italic", italic),
                                  style.get("href", href)))

    dead: dict[str, int] = {}     # delimiter -> no closing partner starts before this index
    line_end = -1                 # end of the line the scanner is in (most spans stay in one line)
    bracket_from, bracket_at = 0, -2  # cache: first "]" at or after bracket_from
    tails: dict[tuple, re.Match | None] = {}

    def word(index: int) -> bool:
        return 0 <= index < size and _WORD.match(text, index) is not None

    def closer(mark: str, start: int, limit: int, tight: bool = True, after_word: bool = True,
               no_tick: bool = False) -> int:
        """First index >= start where `mark` closes a span, or -1 (and remember that)."""
        if start <= dead.get(mark, -1):
            return -1
        index = text.find(mark, start, limit)
        while index != -1:
            if not ((tight and text[index - 1].isspace())
                    or (not after_word and word(index + len(mark)))
                    or (no_tick and text.startswith("`", index + len(mark)))):
                return index
            index = text.find(mark, index + 1, limit)
        dead[mark] = limit
        return -1

    def bracket(start: int) -> int:
        nonlocal bracket_from, bracket_at
        if not bracket_from <= start <= bracket_at:
            bracket_from, bracket_at = start, text.find("]", start)
            if bracket_at == -1:
                bracket_at = size  # none left: every later question has the same answer
        return -1 if bracket_at == size else bracket_at

    def tail(pattern: re.Pattern, index: int) -> re.Match | None:
        if (pattern, index) not in tails:
            tails[pattern, index] = pattern.match(text, index)
        return tails[pattern, index]

    done = position = 0  # text before `done` is already in spans
    while True:
        special = _SPECIAL.search(text, position)
        if special is None:
            break
        at = special.start()
        char = text[at]
        if at > line_end:
            line_end = text.find("\n", at)
            line_end = size if line_end == -1 else line_end
        tight = at + 1 < size and not text[at + 1].isspace()  # something follows the delimiter
        end = None  # set to the index after the construct that starts at `at`
        emit = None
        if char == "{":
            close = closer("}}", at + 2, line_end, tight=False) if text.startswith("{{", at) else -1
            if close != -1:
                end, emit = close + 2, (add, text[at:close + 2], {})
        elif char == "\\":
            if at + 1 < size and text[at + 1] in _ESCAPABLE:
                end, emit = at + 2, (add, text[at + 1], {})
        elif char == "`":
            run = 1
            while run < MAX_TICKS and text.startswith("`", at + run):
                run += 1
            for length in range(run, 0, -1):
                close = closer("`" * length, at + length + 1, line_end, tight=False, no_tick=True)
                if close != -1:
                    code = text[at + length:close]
                    end, emit = close + length, (add, code.strip() or code, {"code": True})
                    break
        elif char == "!":
            close = bracket(at + 2) if text.startswith("![", at) else -1
            found = tail(_IMAGE_TAIL, close) if close != -1 else None
            if found:
                end, emit = found.end(), (add, text[at + 2:close] or found["target"], {})
        elif char == "[":
            close = bracket(at + 1)
            found = tail(_LINK_TAIL, close) if close > at + 1 else None
            if found:
                end = found.end()
                if found["target"].lower().startswith(LINK_SCHEMES):
                    emit = (nested, text[at + 1:close], {"href": found["target"]})
                else:
                    emit = (nested, text[at + 1:close], {}, f" ({found['target']})")
        elif char == "<":
            found = _AUTOLINK.match(text, at)
            if found:
                end, emit = found.end(), (add, found[1], {"href": found[1]})
        elif char == "*":
            for mark, style in (("***", {"bold": True, "italic": True}), ("**", {"bold": True})):
                length = len(mark)
                if (text.startswith(mark, at) and at + length < size
                        and not text[at + length].isspace()):
                    close = closer(mark, at + length + 1, line_end)
                    if close != -1:
                        end, emit = close + length, (nested, text[at + length:close], style)
                        break
            if end is None and tight and text[at + 1] != "*":
                close = text.find("*", at + 2) if at > dead.get("*", -1) else -1
                if close == -1:
                    dead["*"] = size
                elif not text[close - 1].isspace():
                    end, emit = close + 1, (nested, text[at + 1:close], {"italic": True})
        elif not word(at - 1):  # "_": only at the start of a word
            if text.startswith("__", at) and at + 2 < size and not text[at + 2].isspace():
                close = closer("__", at + 3, line_end, after_word=False)
                if close != -1:
                    end, emit = close + 2, (nested, text[at + 2:close], {"bold": True})
            if end is None and tight and text[at + 1] != "_":
                close = text.find("_", at + 2) if at > dead.get("_", -1) else -1
                if close == -1:
                    dead["_"] = size
                elif not text[close - 1].isspace() and not word(close + 1):
                    end, emit = close + 1, (nested, text[at + 1:close], {"italic": True})
        if end is None:
            position = at + 1
            continue
        add(text[done:at])
        emit[0](emit[1], **emit[2])
        for extra in emit[3:]:
            add(extra)
        done = position = end
    add(text[done:])
    merged: list[dict] = []  # neighbours with the same style become one piece
    for span in spans:
        if merged and all(merged[-1][key] == span[key] for key in _STYLE_KEYS):
            merged[-1]["parts"].append(span["text"])
        else:
            merged.append({**span, "parts": [span["text"]]})
    return [{"text": "".join(span["parts"]), **{key: span[key] for key in _STYLE_KEYS}}
            for span in merged]


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
        heading = atx_heading(line)
        if heading:
            flush()
            if heading[1]:
                blocks.append({"text": heading[1], "kind": "heading", "level": heading[0]})
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
            if sum(len(spans) for spans in block["cell_spans"]) > MAX_SPANS:
                block["cell_spans"] = [[{"text": cell}] for cell in block["cells"]]
                block["styles_dropped"] = True
        elif block["kind"] not in ("code", "rule"):
            spans = inline_spans(block["text"])
            block["text"] = spans_text(spans)
            if len(spans) > MAX_SPANS:  # the text stays, its inline styles go
                block["styles_dropped"] = True
            else:
                block["spans"] = spans
    return blocks


def read_markdown(path: Path) -> dict:
    lines, warnings = _lines(path)
    return {"pages": [unpaged_page(markdown_blocks(lines))], "paged": False, "warnings": warnings,
            "coordinate_system": None}
