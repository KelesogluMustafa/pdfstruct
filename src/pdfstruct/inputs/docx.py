"""DOCX adapter (python-docx + the document XML): text and structure in reading order.

Read in this order: page header(s), the body, footnotes, endnotes, then page footer(s). Text
boxes (floating frames such as a CV sidebar) are read right after the paragraph or table that
anchors them. Blocks outside the body carry `region` ("header", "footer", "textbox",
"footnote", "endnote"); body blocks have no region.

Paragraph text is read from the XML as Word shows it: runs inside hyperlinks, content
controls, smart tags, simple fields and tracked insertions are kept; tracked deletions and
field codes are not. Tables inside table cells are read as text of their cell. Comments are
not document text and are only counted. A .docx file has no stored page boundaries, so the
result is one logical page. Styling, images and page layout are not read; a layout-faithful
PDF comes from `pdfstruct.render`, not from this adapter.
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
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
_TXBX = f"{{{_W}}}txbxContent"
_FALLBACK = f"{{{_MC}}}Fallback"
_BLIP = f"{{{_A}}}blip"
_P, _TBL, _TC = f"{{{_W}}}p", f"{{{_W}}}tbl", f"{{{_W}}}tc"
# Subtrees that are not part of a paragraph's visible text (text boxes are read on their own).
_NOT_TEXT = {_TXBX, _FALLBACK, f"{{{_W}}}del", f"{{{_W}}}moveFrom", f"{{{_W}}}instrText",
             f"{{{_W}}}delInstrText", f"{{{_W}}}pPr", f"{{{_W}}}rPr"}
_CHARS = {f"{{{_W}}}tab": "\t", f"{{{_W}}}br": "\n", f"{{{_W}}}cr": "\n",
          f"{{{_W}}}noBreakHyphen": "-"}
_T = f"{{{_W}}}t"


def element_text(element) -> str:
    """Visible text of a paragraph (or any run container) as Word displays it."""
    parts: list[str] = []

    def walk(node) -> None:
        for child in node:
            tag = child.tag
            if not isinstance(tag, str) or tag in _NOT_TEXT:
                continue
            if tag == _T:
                parts.append(child.text or "")
            elif tag in _CHARS:
                parts.append(_CHARS[tag])
            else:
                walk(child)

    walk(element)
    return "".join(parts)


def _paragraph_block(paragraph) -> dict | None:
    text = element_text(paragraph._p).strip()
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


def _outside(element, stop_tags) -> bool:
    return not any(a.tag in stop_tags for a in element.iterancestors())


def _text_boxes(element) -> list:
    """Text box contents inside `element`, outermost only, each read once.

    Word stores a text box twice: the drawing (mc:Choice) and a VML copy for old readers
    (mc:Fallback). Only the first is read; nested text boxes are read by their parent."""
    return [box for box in element.iter(_TXBX) if _outside(box, {_FALLBACK, _TXBX})]


def _cell_text(tc) -> str:
    """All paragraphs of a cell, including those of tables nested in it (not text boxes)."""
    texts = (element_text(p) for p in tc.iter(_P) if _outside(p, {_TXBX, _FALLBACK}))
    return " ".join(" ".join(t for t in texts if t.strip()).split())


class _Reader:
    def __init__(self):
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        self._table_cls, self._paragraph_cls = Table, Paragraph
        self.blocks: list[dict] = []
        self.table_index = -1
        self.nested = False

    def container(self, element, parent, region: str | None) -> None:
        """Paragraphs and tables of a body, header, footer, note or text box, in order."""
        for child in element.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1] if isinstance(child.tag, str) else ""
            if tag == "p":
                self._add(_paragraph_block(self._paragraph_cls(child, parent)), region)
            elif tag == "tbl":
                self._table(self._table_cls(child, parent), region)
            elif tag in ("sdt", "customXml"):  # block-level content control / custom XML
                content = child.find(f"{{{_W}}}sdtContent") if tag == "sdt" else child
                if content is not None:
                    self.container(content, parent, region)
                continue
            else:
                continue
            for box in _text_boxes(child):
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
                self.nested = self.nested or cell._tc.find(f".//{_TBL}") is not None
                cells.append(_cell_text(cell._tc))
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


def _related_xml(document, reltype: str):
    """Root element of a part related to the main document (footnotes, endnotes, comments)."""
    from docx.oxml import parse_xml  # python-docx element classes (paragraph styles, numbering)

    for rel in document.part.rels.values():
        if rel.reltype == _REL + reltype and not rel.is_external:
            part = rel.target_part
            element = getattr(part, "element", None)
            return element if element is not None else parse_xml(part.blob)
    return None


def _notes(document, reader: _Reader, kind: str) -> None:
    """Footnotes or endnotes in the order the body refers to them; separators are skipped."""
    root = _related_xml(document, kind + "s")
    if root is None:
        return
    notes = {n.get(f"{{{_W}}}id"): n for n in root.iter(f"{{{_W}}}{kind}")
             if n.get(f"{{{_W}}}type") in (None, "normal")}
    order = [r.get(f"{{{_W}}}id") for r in document.element.body.iter(f"{{{_W}}}{kind}Reference")]
    for note_id in list(dict.fromkeys(order)) + [i for i in notes if i not in order]:
        if note_id in notes:
            reader.container(notes[note_id], document, kind)


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

    reader = _Reader()
    for item in _header_footer_parts(document, "header"):
        reader.container(item._element, item, "header")
    reader.container(document.element.body, document, None)
    warnings = [NOTE]
    for kind in ("footnote", "endnote"):
        try:
            _notes(document, reader, kind)
        except Exception as exc:  # a broken notes part never costs the body text
            warnings.append(f"docx_{kind}s_unreadable: {type(exc).__name__}")
    for item in _header_footer_parts(document, "footer"):
        reader.container(item._element, item, "footer")

    images = _image_count(document)
    if images:
        warnings.append(f"docx_images_skipped: {images} embedded image(s) not extracted")
    if reader.nested:
        warnings.append("docx_nested_tables_flattened: tables inside table cells are read as text")
    body = document.element.body
    if body.find(f".//{{{_W}}}ins") is not None or body.find(f".//{{{_W}}}del") is not None:
        warnings.append("docx_tracked_changes: read as if accepted (insertions kept, deletions dropped)")
    comments = _related_xml(document, "comments")
    count = 0 if comments is None else sum(1 for _ in comments.iter(f"{{{_W}}}comment"))
    if count:
        warnings.append(f"docx_comments_not_read: {count} comment(s) are not document text")
    return {"pages": [unpaged_page(reader.blocks)], "paged": False, "warnings": warnings,
            "coordinate_system": None}
