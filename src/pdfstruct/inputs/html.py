"""Local HTML adapter (standard library only).

Reads the file as text. Nothing is executed, no network request is made and no
external asset is loaded: scripts, styles, templates and hidden elements are
dropped, links and images (including alt text and the page <title>, which are not shown
as page text) are ignored. Visible text that is not plain markup is kept: filled-in form
values (text inputs, text areas, the selected option) and tables inside table cells, read
as text of their cell.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from . import table_text, unpaged_page
from .text import decode

_SKIP = {"script", "style", "noscript", "template", "svg", "math", "head", "iframe", "object",
         "embed", "canvas", "button", "datalist"}
# <input> types whose value is text the user typed or a page shows
_TEXT_INPUTS = {"", "text", "email", "tel", "url", "search", "number", "date", "datetime-local",
                "month", "week", "time"}
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_BLOCKS = {"p", "div", "section", "article", "main", "header", "footer", "aside", "blockquote",
           "figure", "figcaption", "address", "dl", "dt", "dd", "form", "fieldset", "ul", "ol",
           "table", "thead", "tbody", "tfoot", "caption", "hr", "body", "html", "details",
           "summary"}
_VOID = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "source", "track",
         "wbr", "embed"}
_META_CHARSET = re.compile(rb"<meta[^>]+charset\s*=\s*[\"']?\s*([A-Za-z0-9_\-:.]+)", re.I)
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
_SPACE = re.compile(r"[ \t\r\f\v ]+")


def _decode(data: bytes) -> tuple[str, list[str]]:
    if not data.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
        declared = _META_CHARSET.search(data[:4096])
        if declared:
            name = declared.group(1).decode("ascii", "replace").lower()
            if name not in ("utf-8", "utf8"):
                try:
                    return data.decode(name), []
                except (LookupError, UnicodeDecodeError):
                    pass
    return decode(data)


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self.stack: list[tuple[str, bool]] = []  # (tag, hidden)
        self.skip: list[str] = []  # open tags whose content is dropped
        self.buffer: list[str] = []
        self.kind = "paragraph"
        self.level = None
        self.ordered = False
        self.lists: list[str] = []
        self.pre = 0
        self.table = -1
        self.tables: list[int] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.nested_tables = 0          # depth of tables inside the current cell
        self.nested_seen = False
        self.select: dict | None = None
        self.option: dict | None = None

    # -- helpers
    def _text(self, parts: list[str]) -> str:
        text = "".join(parts)
        if self.pre:
            return text.strip("\n")
        lines = [_SPACE.sub(" ", line).strip() for line in text.split("\n")]
        return "\n".join(line for line in lines if line)

    def _flush(self) -> None:
        text = self._text(self.buffer)
        self.buffer = []
        if not text:
            return
        block = {"text": text, "kind": self.kind}
        if self.kind == "heading":
            block["level"] = self.level
        elif self.kind == "list_item":
            block["level"] = max(1, len(self.lists))
            block["ordered"] = self.ordered
        self.blocks.append(block)

    def _reset_kind(self) -> None:
        self.kind, self.level = "paragraph", None

    def _inline(self, text: str) -> None:
        """A form value shown inside the running text."""
        text = text.strip()
        if text:
            (self.cell if self.cell is not None else self.buffer).append(f" {text} ")

    # -- parser events
    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        hidden = ("hidden" in attributes or attributes.get("aria-hidden") == "true"
                  or bool(_HIDDEN_STYLE.search(attributes.get("style") or "")))
        if tag in _VOID:
            if self.skip or hidden or self.row is not None and self.cell is None:
                return
            if tag == "input" and (attributes.get("type") or "").lower() in _TEXT_INPUTS:
                self._inline(attributes.get("value") or "")
            if tag == "br" and not self.skip:
                (self.cell if self.cell is not None else self.buffer).append("\n")
            elif tag == "hr" and not self.skip:
                self._flush()
            return
        if self.skip or tag in _SKIP or hidden:
            self.skip.append(tag)
            return
        if tag == "select":
            self.select = {"chosen": None, "first": None}
            return
        if tag == "option" and self.select is not None:
            self.option = {"text": [], "selected": "selected" in attributes}
            return
        if self.cell is not None and (tag == "table" or self.nested_tables):
            if tag == "table":  # a table inside a cell is read as text of that cell
                self.nested_tables += 1
                self.nested_seen = True
            if tag in ("table", "tr", "td", "th") or tag in _BLOCKS or tag == "li":
                self.cell.append(" ")
            return
        if tag == "textarea":
            self._flush()
            return
        if tag == "table":
            self._flush()
            self.table += 1
            self.tables.append(self.table)
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
        elif self.cell is not None:
            if tag in _BLOCKS or tag in _HEADINGS or tag == "li":
                self.cell.append("\n")
        elif tag in _HEADINGS:
            self._flush()
            self.kind, self.level = "heading", _HEADINGS[tag]
        elif tag in ("ul", "ol"):
            self._flush()
            self.lists.append(tag)
        elif tag == "li":
            self._flush()
            self.kind = "list_item"
            self.ordered = bool(self.lists) and self.lists[-1] == "ol"
        elif tag == "pre":
            self._flush()
            self.pre += 1
            self.kind = "code"
        elif tag in _BLOCKS:
            self._flush()

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if self.skip:
            if tag in self.skip:  # tolerate unclosed tags inside a dropped element
                del self.skip[len(self.skip) - 1 - self.skip[::-1].index(tag):]
            return
        if tag == "option" and self.option is not None and self.select is not None:
            text = self._text(self.option["text"]).replace("\n", " ")
            if self.select["first"] is None:
                self.select["first"] = text
            if self.option["selected"] and self.select["chosen"] is None:
                self.select["chosen"] = text
            self.option = None
            return
        if tag == "select":
            if self.select is not None:
                self._inline(self.select["chosen"] or self.select["first"] or "")
            self.select = self.option = None
            return
        if self.nested_tables:
            if tag == "table":
                self.nested_tables -= 1
            if tag in ("table", "tr", "td", "th") or tag in _BLOCKS or tag == "li":
                self.cell.append(" ")
            return
        if tag == "textarea":
            self._flush()
            return
        if tag in ("td", "th"):
            if self.cell is not None and self.row is not None:
                self.row.append(self._text(self.cell).replace("\n", " "))
            self.cell = None
        elif tag == "tr":
            if self.row and any(cell for cell in self.row):
                self.blocks.append({"text": table_text(self.row), "kind": "table_row",
                                    "cells": self.row,
                                    "table": self.tables[-1] if self.tables else 0})
            self.row = None
        elif tag == "table":
            self.row = self.cell = None
            if self.tables:
                self.tables.pop()
        elif self.cell is not None:
            return
        elif tag in _HEADINGS or tag == "li":
            self._flush()
            self._reset_kind()
        elif tag in ("ul", "ol"):
            self._flush()
            if self.lists:
                self.lists.pop()
            self._reset_kind()
        elif tag == "pre":
            self._flush()
            self.pre = max(0, self.pre - 1)
            self._reset_kind()
        elif tag in _BLOCKS:
            self._flush()

    def handle_data(self, data):
        if self.option is not None:
            self.option["text"].append(data)
            return
        if self.skip or self.select is not None:
            return
        if self.cell is not None:
            self.cell.append(data)
        elif self.row is None:
            self.buffer.append(data if self.pre else data.replace("\n", " "))


def read(path: Path) -> dict:
    text, warnings = _decode(path.read_bytes())
    parser = _Extractor()
    parser.feed("\n".join(text.splitlines()))
    parser.close()
    parser._flush()
    blocks = parser.blocks
    if parser.nested_seen:
        warnings.append("html_nested_tables_flattened: tables inside table cells are read as text")
    return {"pages": [unpaged_page(blocks)], "paged": False, "warnings": warnings,
            "coordinate_system": None}
