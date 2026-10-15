"""DOCX adapter (python-docx): paragraphs, headings, list items and simple tables in reading order.

Read in this order: page header(s), then the body, then page footer(s). Text boxes (floating
frames such as a CV sidebar) are read right after the paragraph or table that anchors them.
Header, footer and text box blocks carry `region` ("header", "footer", "textbox"); body
blocks have no region. A .docx file has no stored page boundaries, so the result is one
logical page. Styling, images and page layout are not read; a layout-faithful PDF comes from
`pdfstruct.render`, not from this adapter.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import InputError, table_text, unpaged_page

_HEADING = re.compile(r"^heading\s+(\d)$", re.I)
NOTE = ("docx_layout_not_preserved: the raw document and its text outputs carry no styling, "
        "images or page layout")

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_TXBX = f"{{{_W}}}txbxContent"
_FALLBACK = f"{{{_MC}}}Fallback"
_BLIP = f"{{{_A}}}blip"


def _paragraph_block(paragraph) -> dict | None:
    text = paragraph.text.strip()
    if not text:
        return None
    style = (paragraph.style.name if paragraph.style is not None else "") or ""
    heading = _HEADING.match(style)
    if heading:
        return {"text": text, "kind": "heading", "level": int(heading.group(1))}
    if style.lower() == "title":
        return {"text": text, "kind": "heading", "level": 1}
    properties = paragraph._p.pPr
    numbering = properties.numPr if properties is not None else None
    if numbering is not None or style.lower().startswith("list"):
        level = 1
        if numbering is not None and numbering.ilvl is not None:
            level = int(numbering.ilvl.val) + 1
        return {"text": text, "kind": "list_item", "level": min(level, 6),
                "ordered": "number" in style.lower()}
    return {"text": text, "kind": "paragraph"}


def _text_boxes(element) -> list:
    """Text box contents inside `element`, outermost only, each read once.

    Word stores a text box twice: the drawing (mc:Choice) and a VML copy for old readers
    (mc:Fallback). Only the first is read; nested text boxes are read by their parent."""
    found = []
    for box in element.iter(_TXBX):
        ancestors = list(box.iterancestors())
        if any(a.tag == _FALLBACK for a in ancestors):
            continue
        if any(a.tag == _TXBX for a in ancestors):
            continue
        found.append(box)
    return found


class _Reader:
    def __init__(self, document):
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        self._table_cls, self._paragraph_cls = Table, Paragraph
        self.blocks: list[dict] = []
        self.table_index = -1
        self.nested = False
        self.text_boxes = 0

    def container(self, element, parent, region: str | None) -> None:
        """Paragraphs and tables of a body, header, footer or text box, in document order."""
        for child in element.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                self._add(_paragraph_block(self._paragraph_cls(child, parent)), region)
            elif tag == "tbl":
                self._table(self._table_cls(child, parent), region)
            elif tag == "sdt":  # content control: its paragraphs live in sdtContent
                content = child.find(f"{{{_W}}}sdtContent")
                if content is not None:
                    self.container(content, parent, region)
                continue
            else:
                continue
            for box in _text_boxes(child):
                self.text_boxes += 1
                self.container(box, parent, "textbox")

    def _table(self, table, region: str | None) -> None:
        self.table_index += 1
        index = self.table_index
        for row in table.rows:
            cells, seen = [], set()
            for cell in row.cells:  # a merged cell is returned once per spanned column
                if id(cell._tc) in seen:
                    continue
                seen.add(id(cell._tc))
                self.nested = self.nested or bool(cell.tables)
                cells.append(" ".join(cell.text.split()))
            if any(cells):
                self._add({"text": table_text(cells), "kind": "table_row", "cells": cells,
                           "table": index}, region)

    def _add(self, block: dict | None, region: str | None) -> None:
        if block is None:
            return
        if region:
            block["region"] = region
        self.blocks.append(block)


def _header_footer_parts(document, attribute: str) -> list:
    """Distinct header (or footer) parts of all sections, in section order."""
    parts, seen = [], set()
    for section in document.sections:
        for name in (f"first_page_{attribute}", attribute, f"even_page_{attribute}"):
            item = getattr(section, name)
            if item.is_linked_to_previous:
                continue
            key = id(item.part)
            if key not in seen:
                seen.add(key)
                parts.append(item)
    return parts


def _image_count(document) -> int:
    count = sum(1 for _ in document.element.body.iter(_BLIP))
    for attribute in ("header", "footer"):
        for item in _header_footer_parts(document, attribute):
            count += sum(1 for _ in item._element.iter(_BLIP))
    return count


def read(path: Path) -> dict:
    from docx import Document
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = Document(str(path))
    except (PackageNotFoundError, KeyError, ValueError) as exc:
        raise InputError("invalid_docx", "not a readable .docx file (damaged, encrypted or "
                                         f"an old .doc renamed): {type(exc).__name__}") from exc

    reader = _Reader(document)
    for item in _header_footer_parts(document, "header"):
        reader.container(item._element, item, "header")
    reader.container(document.element.body, document, None)
    for item in _header_footer_parts(document, "footer"):
        reader.container(item._element, item, "footer")

    warnings = [NOTE]
    images = _image_count(document)
    if images:
        warnings.append(f"docx_images_skipped: {images} embedded image(s) not extracted")
    if reader.nested:
        warnings.append("docx_nested_tables_flattened: tables inside table cells are read as text")
    return {"pages": [unpaged_page(reader.blocks)], "paged": False, "warnings": warnings,
            "coordinate_system": None}
