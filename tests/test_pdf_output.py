"""PDF output: readable re-flow for text inputs, fitted picture + searchable text for images."""
import json
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from conftest import UNICODE_LINE, make_docx, make_image, make_tiff
from pdfstruct import pdfwriter
from pdfstruct.service import JobRequest, run_job


def convert(path, formats=("pdf",), **options):
    return run_job(JobRequest(inputs=[path], formats=list(formats), **options)).files[0]


def read_pdf(path) -> tuple[int, list[str], list[tuple]]:
    """(page count, text per page, (width, height) per page) - proves the file really opens."""
    assert Path(path).read_bytes().startswith(b"%PDF-")
    document = pdfium.PdfDocument(str(path))
    try:
        texts, sizes = [], []
        for page in document:
            textpage = page.get_textpage()
            texts.append(textpage.get_text_range())
            sizes.append(page.get_size())
            textpage.close()
            page.close()
        return len(document), texts, sizes
    finally:
        document.close()


def test_docx_to_pdf_keeps_unicode_and_structure(tmp_path):
    item = convert(make_docx(tmp_path / "bericht.docx"))
    assert item.status == "succeeded" and Path(item.outputs["pdf"]).name == "bericht.docx.pdf"
    count, texts, sizes = read_pdf(item.outputs["pdf"])
    text = " ".join(" ".join(texts).split())
    assert count == 1 and round(sizes[0][0]) == 595 and round(sizes[0][1]) == 842  # A4
    for expected in ("Quartalsbericht", UNICODE_LINE, "Erster Punkt", "Schritt eins", "Apfel", "1,20",
                     "Schlussabsatz nach der Tabelle."):
        assert expected in text, expected
    assert text.index("Quartalsbericht") < text.index("Aufgaben") < text.index("Apfel") \
        < text.index("Schlussabsatz")
    assert not any(w.startswith("pdf_missing_glyphs") for w in item.warnings)
    assert (tmp_path / "bericht.docx").is_file()  # source untouched, output in output/


@pytest.mark.parametrize("name,content,expected", [
    ("tr.txt", "Çağrı Öğretmen İstanbul ığüşöç ĞÜŞÖÇ", "Çağrı Öğretmen İstanbul ığüşöç ĞÜŞÖÇ"),
    ("de.md", "# Größe\n\nÄrger über Maßstäbe – „Zitat“ €", "Ärger über Maßstäbe"),
    ("seite.html", "<h1>Başlık</h1><ul><li>Eins</li><li>Zwei</li></ul><p>Fuß</p>", "Başlık"),
])
def test_text_inputs_to_pdf(tmp_path, name, content, expected):
    source = tmp_path / name
    source.write_text(content, encoding="utf-8")
    item = convert(source)
    count, texts, _ = read_pdf(item.outputs["pdf"])
    assert count == 1 and expected in " ".join(texts[0].split())
    assert not any(w.startswith("pdf_missing_glyphs") for w in item.warnings)


def test_long_paragraph_flows_over_pages_and_empty_document_is_valid(tmp_path):
    long_source = tmp_path / "lang.txt"
    long_source.write_text(" ".join(f"Wort{n}" for n in range(6000)) + "\n\n" + "x" * 900, encoding="utf-8")
    item = convert(long_source)
    count, texts, sizes = read_pdf(item.outputs["pdf"])
    assert count >= 3 and "Wort0" in texts[0] and "Wort5999" in "".join(texts)
    assert all(round(w) == 595 for w, _ in sizes)

    empty = tmp_path / "leer.txt"
    empty.write_bytes(b"")
    blank = convert(empty)
    count, texts, _ = read_pdf(blank.outputs["pdf"])
    assert blank.status == "succeeded" and count == 1 and texts[0].strip() == ""


def test_pdf_output_is_deterministic_and_reports_missing_glyphs(tmp_path):
    source = tmp_path / "a.txt"
    source.write_text("Gleicher Inhalt", encoding="utf-8")
    first = Path(convert(source).outputs["pdf"]).read_bytes()
    assert Path(convert(source).outputs["pdf"]).read_bytes() == first
    cjk = tmp_path / "cjk.txt"
    cjk.write_text("Latin und 漢字", encoding="utf-8")
    item = convert(cjk)
    assert any(w.startswith("pdf_missing_glyphs") for w in item.warnings)
    assert read_pdf(item.outputs["pdf"])[0] == 1  # still a valid PDF


def test_wide_table_falls_back_to_text_rows(tmp_path):
    cells = "".join(f"<td>c{n}</td>" for n in range(12))
    source = tmp_path / "breit.html"
    source.write_text(f"<table><tr>{cells}</tr></table>", encoding="utf-8")
    _, texts, _ = read_pdf(convert(source).outputs["pdf"])
    assert "c0 | c1" in " ".join(texts[0].split()) and "c11" in texts[0]


def test_image_to_pdf_fits_the_page_and_is_searchable(tmp_path, ocr_available):
    if not ocr_available:
        pytest.skip("OCR packages not installed on this platform")
    item = convert(make_image(tmp_path / "foto.png"), formats=("pdf", "json"))
    assert item.status == "succeeded" and Path(item.outputs["pdf"]).name == "foto.png.pdf"
    count, texts, sizes = read_pdf(item.outputs["pdf"])
    assert count == 1 and sizes[0][0] > sizes[0][1]  # landscape picture -> landscape page
    assert "Hallo" in texts[0] and "12345" in texts[0]  # invisible OCR layer
    document = pdfium.PdfDocument(item.outputs["pdf"])
    page = document[0]
    try:
        import pypdfium2.raw as raw_api
        images = list(page.get_objects(filter=[raw_api.FPDF_PAGEOBJ_IMAGE]))
        assert len(images) == 1
        left, bottom, right, top = images[0].get_bounds()
        assert 0 <= left and right <= sizes[0][0] + 0.5 and 0 <= bottom and top <= sizes[0][1] + 0.5
        assert abs((right - left) / (top - bottom) - 1240 / 700) < 0.02  # aspect ratio kept
    finally:
        page.close()
        document.close()

    tiff = convert(make_tiff(tmp_path / "mehr.tif"))
    count, texts, _ = read_pdf(tiff.outputs["pdf"])
    assert count == 2 and "Alpha" in texts[0] and "Beta" in texts[1]


def test_image_pdf_without_the_source_file_says_so(tmp_path):
    raw = {"schema_version": "1.1", "input_format": "png", "paged": True, "page_count": 1,
           "source": {"path": str(tmp_path / "weg.png"), "file_name": "weg.png"},
           "pages": [{"page": 1, "text": "Erkannter Text",
                      "blocks": [{"text": "Erkannter Text", "kind": "line", "bbox": [1, 2, 3, 4]}]}]}
    warnings = pdfwriter.write_pdf(raw, tmp_path / "weg.png.pdf")
    assert warnings and warnings[0].startswith("pdf_text_only")
    assert "Erkannter Text" in read_pdf(tmp_path / "weg.png.pdf")[1][0]
    assert not list(tmp_path.glob("*.tmp"))


def test_raw_result_never_carries_text_for_pdf_output(tmp_path):
    source = tmp_path / "geheim.txt"
    source.write_text("STRENG VERTRAULICHER INHALT", encoding="utf-8")
    result = run_job(JobRequest(inputs=[source], formats=["pdf", "json"]))
    assert "VERTRAULICH" not in json.dumps(result.to_dict(), ensure_ascii=False)
