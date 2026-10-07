"""DOCX adapter (python-docx): paragraphs, headings, list items and simple tables in body order.

A .docx file has no stored page boundaries, so the result is one logical page.
Styling, images, headers/footers, text boxes and page layout are not read.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import InputError, table_text, unpaged_page

_HEADING = re.compile(r"^heading\s+(\d)$", re.I)
NOTE = "docx_layout_not_preserved: styling, images, headers/footers and page layout are not read"


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


def read(path: Path) -> dict:
    from docx import Document
    from docx.opc.exceptions import PackageNotFoundError
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = Document(str(path))
    except (PackageNotFoundError, KeyError, ValueError) as exc:
        raise InputError("invalid_docx", "not a readable .docx file (damaged, encrypted or "
                                         f"an old .doc renamed): {type(exc).__name__}") from exc

    blocks: list[dict] = []
    table_index = -1
    nested = False
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            block = _paragraph_block(Paragraph(child, document))
            if block:
                blocks.append(block)
        elif tag == "tbl":
            table_index += 1
            for row in Table(child, document).rows:
                cells, seen = [], set()
                for cell in row.cells:  # a merged cell is returned once per spanned column
                    if id(cell._tc) in seen:
                        continue
                    seen.add(id(cell._tc))
                    nested = nested or bool(cell.tables)
                    cells.append(" ".join(cell.text.split()))
                if any(cells):
                    blocks.append({"text": table_text(cells), "kind": "table_row",
                                   "cells": cells, "table": table_index})

    warnings = [NOTE]
    if document.inline_shapes:
        warnings.append(f"docx_images_skipped: {len(document.inline_shapes)} embedded image(s) not extracted")
    if nested:
        warnings.append("docx_nested_tables_flattened: tables inside table cells are read as text")
    return {"pages": [unpaged_page(blocks)], "paged": False, "warnings": warnings,
            "coordinate_system": None}
