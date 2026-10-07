"""pdfstruct.pdfwriter - the PDF exporter (reportlab, fully local).

Text inputs become a readable re-flow: headings, paragraphs, list items and simple
tables on A4. It is not a rendering of the source layout. Image inputs become one
page per frame with the picture fitted to the page and the recognised text placed
invisibly on top, so the PDF is searchable.

Fonts are the Bitstream Vera faces shipped inside reportlab (Latin incl. Turkish and
German). Characters they lack are reported, not silently dropped.
"""
from __future__ import annotations

import os
from pathlib import Path
from xml.sax.saxutils import escape

from . import inputs

FONT, FONT_BOLD = "Vera", "VeraBd"
MARGIN = 56.7          # 2 cm
IMAGE_MARGIN = 18.0
MAX_IMAGE_SIDE = 3508  # A4 at 300 dpi; larger pictures are downscaled inside the PDF
MAX_TABLE_COLUMNS = 8


def _fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, "Vera.ttf"))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, "VeraBd.ttf"))
        pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT,
                                      boldItalic=FONT_BOLD)
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
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer

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
            story.append(Paragraph(_markup(text), styles[f"h{min(max(block.get('level') or 1, 1), 6)}"]))
        elif kind == "list_item":
            level = max(1, block.get("level") or 1)
            for deeper in [key for key in counters if key > level]:
                del counters[deeper]
            counters[level] = counters.get(level, 0) + 1
            bullet = f"{counters[level]}." if block.get("ordered") else "•"
            style = ParagraphStyle(f"li{level}", parent=styles["body"], leftIndent=18 * level,
                                   bulletIndent=18 * level - 14, spaceAfter=3)
            story.append(Paragraph(_markup(text), style, bulletText=bullet))
        elif kind == "code":
            story.append(Paragraph(_markup(text).replace(" ", "&nbsp;"), styles["code"]))
        elif text.strip():
            story.append(Paragraph(_markup(text), styles["body"]))
        index += 1
    return story


def _text_pdf(raw: dict, path: Path, title: str) -> list[str]:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer

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
    if not story:
        story.append(Spacer(1, 1))  # an empty document is still one valid page
    tmp = path.with_name(path.name + ".tmp")
    document = SimpleDocTemplate(str(tmp), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                                 topMargin=MARGIN, bottomMargin=MARGIN, title=title,
                                 author="PDFStruct", invariant=1)
    document.build(story)
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
