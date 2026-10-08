"""pdfstruct.pdfwriter - the PDF exporter (reportlab, fully local).

Text inputs become a readable re-flow: headings, paragraphs, list items and simple
tables on A4. It is not a rendering of the source layout. Image inputs become one
page per frame with the picture fitted to the page and the recognised text placed
invisibly on top, so the PDF is searchable.

Fonts are the Bitstream Vera faces shipped inside reportlab (Latin incl. Turkish and
German). Characters they lack are reported, not silently dropped.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from . import inputs

FONT, FONT_BOLD, FONT_ITALIC, FONT_BOLD_ITALIC = "Vera", "VeraBd", "VeraIt", "VeraBI"
MARGIN = 56.7          # 2 cm
IMAGE_MARGIN = 18.0
MAX_IMAGE_SIDE = 3508  # A4 at 300 dpi; larger pictures are downscaled inside the PDF
MAX_TABLE_COLUMNS = 8
MAX_KEPT_HEADING_CHARS = 300  # a longer heading is not tied to the block that follows it
MAX_BLOCK_CHARS = 20_000  # created documents: a longer block is laid out in pieces
MAX_TABLE_ROWS = 400      # created documents: a longer table is laid out in pieces


def _fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, "Vera.ttf"))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, "VeraBd.ttf"))
        pdfmetrics.registerFont(TTFont(FONT_ITALIC, "VeraIt.ttf"))
        pdfmetrics.registerFont(TTFont(FONT_BOLD_ITALIC, "VeraBI.ttf"))
        pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT_ITALIC,
                                      boldItalic=FONT_BOLD_ITALIC)
    return pdfmetrics.getFont(FONT)


def _missing_glyphs(font, texts) -> list[str]:
    known = font.face.charToGlyph
    missing = {ch for text in texts for ch in text
               if not ch.isspace() and ord(ch) > 0x20 and ord(ch) not in known}
    if not missing:
        return []
    sample = "".join(sorted(missing)[:8])
    return [f"pdf_missing_glyphs: {len(missing)} character(s) are not in the PDF font and show "
            f"as boxes (e.g. {sample})"]


def _markup(text: str) -> str:
    from .export import clean
    return escape(clean(text)).replace("\n", "<br/>")


def _block_markup(block: dict) -> str:
    """Escaped text of a block. Only documents created from text carry inline `spans`."""
    if "spans" not in block:
        return _markup(block.get("text", ""))
    out = []
    for span in block["spans"]:
        piece = _markup(span["text"])
        if span.get("italic"):
            piece = f"<i>{piece}</i>"
        if span.get("bold"):
            piece = f"<b>{piece}</b>"
        if span.get("href"):
            piece = f'<a href={quoteattr(span["href"])} color="#0563c1">{piece}</a>'
        out.append(piece)
    return "".join(out)


def _styles():
    from reportlab.lib.styles import ParagraphStyle

    body = ParagraphStyle("body", fontName=FONT, fontSize=10.5, leading=15, spaceAfter=7)
    styles = {"body": body,
              "code": ParagraphStyle("code", parent=body, fontSize=9, leading=12.5, leftIndent=12),
              "cell": ParagraphStyle("cell", parent=body, fontSize=9, leading=12, spaceAfter=0)}
    for level, size in {1: 18, 2: 15, 3: 13, 4: 11.5, 5: 10.5, 6: 10.5}.items():
        styles[f"h{level}"] = ParagraphStyle(f"h{level}", parent=body, fontName=FONT_BOLD,
                                             fontSize=size, leading=size * 1.3,
                                             spaceBefore=size * 0.6, spaceAfter=size * 0.4,
                                             keepWithNext=1)
    return styles


def _table(rows: list[list[str]], width: float, styles):
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle

    columns = max(len(row) for row in rows)
    data = [[Paragraph(_markup(cell), styles["cell"]) for cell in row + [""] * (columns - len(row))]
            for row in rows]
    table = Table(data, colWidths=[width / columns] * columns, hAlign="LEFT")
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 4),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
    return table


def _flowables(blocks: list[dict], width: float, styles) -> list:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import HRFlowable, Paragraph, Spacer

    story, counters = [], {}
    index = 0
    while index < len(blocks):
        block = blocks[index]
        kind = block.get("kind") or "paragraph"
        text = block.get("text", "")
        if kind != "list_item":
            counters.clear()
        if kind == "table_row":
            rows = []
            while (index < len(blocks) and blocks[index].get("kind") == "table_row"
                   and blocks[index].get("table") == block.get("table")):
                rows.append(list(blocks[index].get("cells") or [blocks[index].get("text", "")]))
                index += 1
            if max(len(row) for row in rows) <= MAX_TABLE_COLUMNS:
                story += [_table(rows, width, styles), Spacer(1, 8)]
            else:  # too wide to lay out safely: keep every cell as text
                story += [Paragraph(_markup(" | ".join(row)), styles["body"]) for row in rows]
            continue
        if kind == "heading":
            style = styles[f"h{min(max(block.get('level') or 1, 1), 6)}"]
            if len(text) > MAX_KEPT_HEADING_CHARS:
                # a heading about a page tall that must stay with its successor makes
                # reportlab look for a page it fits on forever
                style = ParagraphStyle(style.name + "-long", parent=style, keepWithNext=0)
            story.append(Paragraph(_block_markup(block), style))
        elif kind == "list_item":
            level = max(1, block.get("level") or 1)
            for deeper in [key for key in counters if key > level]:
                del counters[deeper]
            counters[level] = counters.get(level, 0) + 1
            bullet = f"{counters[level]}." if block.get("ordered") else "•"
            style = ParagraphStyle(f"li{level}", parent=styles["body"], leftIndent=18 * level,
                                   bulletIndent=18 * level - 14, spaceAfter=3)
            story.append(Paragraph(_block_markup(block), style, bulletText=bullet))
        elif kind == "code":
            story.append(Paragraph(_markup(text).replace(" ", "&nbsp;"), styles["code"]))
        elif kind == "rule":
            story.append(HRFlowable(width="100%", thickness=0.6, color=colors.grey,
                                    spaceBefore=4, spaceAfter=10))
        elif text.strip():
            story.append(Paragraph(_block_markup(block), styles["body"]))
        index += 1
    return story


def _build(target, story: list, title: str) -> None:
    """One A4 document from a story. `target` is a file name or a binary file object."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Spacer

    document = SimpleDocTemplate(target, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                                 topMargin=MARGIN, bottomMargin=MARGIN, title=title,
                                 author="PDFStruct", invariant=1)
    document.build(story or [Spacer(1, 1)])  # an empty document is still one valid page


def _in_pieces(blocks: list[dict]) -> tuple[list[dict], bool]:
    """Blocks reportlab can lay out in reasonable time -> (blocks, True when one was cut).

    Its paragraph and table layout need quadratic time for one very long paragraph or one
    table with thousands of rows. Such a block is cut at a space or line end into pieces
    that follow each other (their inline styles are dropped), and a long table continues
    as several tables. Nothing a person writes by hand comes near these sizes."""
    out, cut, table, rows = [], False, None, 0
    for block in blocks:
        text = block.get("text", "")
        if block.get("kind") == "table_row":
            rows = rows + 1 if block.get("table") == table else 0
            table = block.get("table")
            out.append({**block, "table": (table, rows // MAX_TABLE_ROWS)})
        elif len(text) > MAX_BLOCK_CHARS:
            cut, start, kind = True, 0, block.get("kind")
            plain = {key: value for key, value in block.items() if key != "spans"}
            while start < len(text):
                end = min(start + MAX_BLOCK_CHARS, len(text))
                if end < len(text):
                    space = max(text.rfind("\n", start, end), text.rfind(" ", start, end))
                    end = space + 1 if space > start else end
                out.append({**plain, "text": text[start:end], "kind": kind})
                kind = kind if kind == "code" else "paragraph"  # one bullet, one heading
                start = end
        else:
            out.append(block)
    return out, cut


def render_blocks(blocks: list[dict], title: str) -> tuple[bytes, list[str]]:
    """PDF bytes for one unpaged block list (documents created from text) and its warnings."""
    from reportlab.lib.pagesizes import A4

    from reportlab.platypus.doctemplate import LayoutError

    font = _fonts()
    buffer = io.BytesIO()
    pieces, cut = _in_pieces(blocks)
    notes = [f"pdf_long_block_split: a block longer than {MAX_BLOCK_CHARS} characters was laid "
             "out in pieces, without bold, italic or links"] if cut else []
    try:
        _build(buffer, _flowables(pieces, A4[0] - 2 * MARGIN, _styles()), title)
    except LayoutError:  # a table row taller than a page cannot be split: keep the cells as text
        pieces = [{"text": block.get("text", ""), "kind": "paragraph"}
                  if block.get("kind") == "table_row" else block for block in pieces]
        buffer = io.BytesIO()
        _build(buffer, _flowables(pieces, A4[0] - 2 * MARGIN, _styles()), title)
        notes.append("pdf_tables_as_text: a table row is taller than a page, so the tables are "
                     "written as text rows in the PDF")
    texts = [text for block in blocks for text in (block.get("text", ""), *(block.get("cells") or []))]
    return buffer.getvalue(), notes + _missing_glyphs(font, texts)


def _text_pdf(raw: dict, path: Path, title: str) -> list[str]:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import PageBreak

    font = _fonts()
    styles = _styles()
    width = A4[0] - 2 * MARGIN
    story = []
    pages = raw.get("pages") or []
    for position, page in enumerate(pages):
        blocks = page.get("blocks") or []
        if not any(block.get("kind") for block in blocks):  # PDF / OCR lines: use the page text
            blocks = [{"text": part, "kind": "paragraph"}
                      for part in (page.get("text") or "").split("\n\n") if part.strip()]
        story += _flowables(blocks, width, styles)
        if position < len(pages) - 1:
            story.append(PageBreak())
    tmp = path.with_name(path.name + ".tmp")
    _build(str(tmp), story, title)
    os.replace(tmp, path)
    return _missing_glyphs(font, (page.get("text") or "" for page in pages))


def _image_pdf(raw: dict, path: Path, source: Path, title: str) -> list[str]:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfgen import canvas

    from .inputs import image as image_input

    font = _fonts()
    tmp = path.with_name(path.name + ".tmp")
    sheet = canvas.Canvas(str(tmp), invariant=1)
    sheet.setTitle(title)
    sheet.setAuthor("PDFStruct")
    pages = {page["page"]: page for page in raw.get("pages") or []}
    for number, _total, frame in image_input.upright_frames(source, raw["input_format"]):
        width, height = frame.size
        page_width, page_height = (A4[1], A4[0]) if width > height else A4
        scale = min((page_width - 2 * IMAGE_MARGIN) / width, (page_height - 2 * IMAGE_MARGIN) / height)
        left = (page_width - width * scale) / 2
        bottom = (page_height - height * scale) / 2
        sheet.setPageSize((page_width, page_height))
        shrink = min(1.0, MAX_IMAGE_SIDE / max(width, height))
        picture = frame if shrink == 1.0 else frame.resize(
            (max(1, round(width * shrink)), max(1, round(height * shrink))))
        sheet.drawImage(ImageReader(picture), left, bottom, width * scale, height * scale)
        for block in (pages.get(number) or {}).get("blocks") or []:  # invisible, searchable text
            text, box = block.get("text") or "", block.get("bbox")
            if not text.strip() or not box:
                continue
            x1, y1, x2, y2 = box
            size = max(4.0, (y2 - y1) * scale * 0.8)
            natural = pdfmetrics.stringWidth(text, FONT, size)
            layer = sheet.beginText(left + x1 * scale, bottom + (height - y2) * scale + size * 0.2)
            layer.setFont(FONT, size)
            layer.setTextRenderMode(3)
            if natural > 0:
                layer.setHorizScale(max(1.0, 100.0 * (x2 - x1) * scale / natural))
            layer.textOut(text)
            sheet.drawText(layer)
        sheet.showPage()
    sheet.save()
    os.replace(tmp, path)
    return _missing_glyphs(font, (page.get("text") or "" for page in pages.values()))


def write_pdf(raw: dict, path: Path) -> list[str]:
    """Write `path`; returns short warnings (missing glyphs, missing source image)."""
    from .export import source_name

    title = source_name(raw)
    if inputs.is_image(raw.get("input_format")):
        source = Path((raw.get("source") or {}).get("path") or "")
        if source.is_file():
            return _image_pdf(raw, path, source, title)
        return ["pdf_text_only: the source image is no longer at its original path; the PDF "
                "contains the recognised text only", *_text_pdf(raw, path, title)]
    return _text_pdf(raw, path, title)
