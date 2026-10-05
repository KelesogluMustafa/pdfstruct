"""Test fixtures: small PDFs generated on the fly (reportlab + Pillow)."""
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOL_DIR))

import pdf_to_json  # noqa: E402

UMLAUT_LINE = "Die Straße über den Fluss: ä ö ü Ä Ö Ü ß"


def make_text_pdf(path: Path, pages: int = 1, blank_pages: tuple = ()) -> Path:
    c = canvas.Canvas(str(path), pagesize=A4)
    for number in range(1, pages + 1):
        if number not in blank_pages:
            c.setFont("Helvetica", 12)
            c.drawString(72, 770, f"Seite {number} - Beispieltext")
            c.drawString(72, 750, UMLAUT_LINE)
            for row in range(8):
                c.drawString(72, 720 - row * 18, f"Zeile {row + 1}: Das ist ein normaler Satz mit Text.")
        c.showPage()
    c.save()
    return path


def _scan_image() -> Image.Image:
    image = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 44)
    except OSError:
        font = ImageFont.load_default(size=44)
    for row, line in enumerate(["Gescannte Seite", "Hallo Welt Beispiel", "Rechnung Nummer 12345"]):
        draw.text((120, 200 + row * 110), line, fill="black", font=font)
    return image


def make_scan_pdf(path: Path) -> Path:
    _scan_image().save(str(path), "PDF", resolution=150.0)
    return path


def make_mixed_pdf(path: Path) -> Path:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(72, 770, "Native Seite mit Textebene")
    c.drawString(72, 750, UMLAUT_LINE)
    c.showPage()
    c.drawImage(ImageReader(_scan_image()), 0, 0, width=A4[0], height=A4[1])
    c.showPage()
    c.save()
    return path


@pytest.fixture
def run_tool():
    def _run(*argv) -> int:
        return pdf_to_json.main([str(a) for a in argv])
    return _run


@pytest.fixture(scope="session")
def ocr_available() -> bool:
    cfg = pdf_to_json.load_config(None)
    return pdf_to_json.OcrClient(cfg["ocr"], Path("unused.log")).resolve_python() is not None
