import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from conftest import TOOL_DIR, UMLAUT_LINE, make_mixed_pdf, make_scan_pdf, make_text_pdf

SCHEMA = json.loads((TOOL_DIR / "schemas" / "raw_document.schema.json").read_text(encoding="utf-8"))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_raw(out: Path, stem: str) -> dict:
    raw = load(out / f"{stem}.raw.json")
    jsonschema.validate(raw, SCHEMA)
    return raw


# 1 + 5: real text layer, umlauts
def test_native_text_and_umlauts(tmp_path, run_tool):
    pdf = make_text_pdf(tmp_path / "text.pdf")
    out = tmp_path / "out"
    assert run_tool("--input", pdf, "--output", out) == 0
    raw = load_raw(out, "text")
    assert raw["extraction_method"] == "native"
    assert raw["ocr_used"] is False
    assert raw["text_layer_score"] >= 0.9
    page = raw["pages"][0]
    assert UMLAUT_LINE in page["text"]
    for ch in "äöüÄÖÜß":
        assert ch in page["text"]
    assert any(UMLAUT_LINE in b["text"] for b in page["blocks"])
    for block in page["blocks"]:
        x1, y1, x2, y2 = block["bbox"]
        assert 0 <= x1 < x2 <= page["width"] and 0 <= y1 < y2 <= page["height"]
    # top-left origin: the first line drawn near the top has a small y
    assert page["blocks"][0]["bbox"][1] < 100
    assert [b["order"] for b in page["blocks"]] == list(range(len(page["blocks"])))


# 2: scan / image-only PDF
def test_scan_pdf_uses_ocr(tmp_path, run_tool, ocr_available):
    if not ocr_available:
        pytest.skip("no OCR python available")
    pdf = make_scan_pdf(tmp_path / "scan.pdf")
    out = tmp_path / "out"
    assert run_tool("--input", pdf, "--output", out) == 0
    raw = load_raw(out, "scan")
    assert raw["extraction_method"] == "ocr"
    assert raw["ocr_used"] is True
    assert raw["text_layer_score"] == 0.0
    page = raw["pages"][0]
    assert page["method"] == "ocr"
    assert "Hallo" in page["text"] and "12345" in page["text"]
    for block in page["blocks"]:
        x1, y1, x2, y2 = block["bbox"]
        assert 0 <= x1 < x2 <= page["width"] + 1 and 0 <= y1 < y2 <= page["height"] + 1
        assert "confidence" in block


def test_scan_pdf_native_only_flags_review(tmp_path, run_tool):
    pdf = make_scan_pdf(tmp_path / "scan.pdf")
    out = tmp_path / "out"
    assert run_tool("--input", pdf, "--output", out, "--native-only") == 0
    raw = load_raw(out, "scan")
    assert raw["ocr_used"] is False
    assert raw["review_pages"] == [1]
    assert raw["pages"][0]["method"] == "none"


# 3: mixed PDF, decided per page
def test_mixed_pdf(tmp_path, run_tool, ocr_available):
    if not ocr_available:
        pytest.skip("no OCR python available")
    pdf = make_mixed_pdf(tmp_path / "mixed.pdf")
    out = tmp_path / "out"
    assert run_tool("--input", pdf, "--output", out) == 0
    raw = load_raw(out, "mixed")
    assert raw["extraction_method"] == "mixed"
    assert [p["method"] for p in raw["pages"]] == ["native", "ocr"]
    assert UMLAUT_LINE in raw["pages"][0]["text"]
    assert "Hallo" in raw["pages"][1]["text"]


# 4 + 6: blank page inside a multi-page PDF
def test_blank_page_and_multipage(tmp_path, run_tool):
    pdf = make_text_pdf(tmp_path / "multi.pdf", pages=40, blank_pages=(7,))
    out = tmp_path / "out"
    assert run_tool("--input", pdf, "--output", out) == 0
    raw = load_raw(out, "multi")
    assert raw["page_count"] == 40 and len(raw["pages"]) == 40
    assert [p["page"] for p in raw["pages"]] == list(range(1, 41))
    assert raw["extraction_method"] == "native"
    blank = raw["pages"][6]
    assert blank["method"] == "none" and blank["text_layer"]["blank"] is True
    assert blank["blocks"] == [] and blank["needs_review"] is False
    assert raw["method_counts"] == {"native": 39, "ocr": 0, "none": 1, "error": 0}
    assert "Seite 40" in raw["pages"][39]["text"]


# 7 + 8 + 9: folder input, output folder created, corrupt PDF isolated
def test_folder_with_corrupt_pdf(tmp_path, run_tool, capsys):
    src = tmp_path / "pdf"
    src.mkdir()
    make_text_pdf(src / "a.pdf")
    make_text_pdf(src / "b.pdf", pages=3)
    (src / "broken.pdf").write_bytes(b"%PDF-1.4\nthis is not a real pdf\n" + bytes(range(256)))
    (src / "notes.txt").write_text("ignored", encoding="utf-8")
    out = tmp_path / "deep" / "nested" / "out"
    assert run_tool("--input", src, "--output", out) == 1
    assert (out / "a.raw.json").is_file() and (out / "b.raw.json").is_file()
    assert not (out / "broken.raw.json").exists()
    assert load(out / "broken.summary.json")["status"] == "error"
    assert not list(out.glob("*.tmp"))
    run = load(out / "_run_summary.json")
    assert run["totals"]["files"] == 3 and run["totals"]["errors"] == 1
    assert run["totals"]["pages"] == 4 and run["totals"]["native"] == 2
    printed = capsys.readouterr().out
    assert "FILES: 3" in printed and "ERRORS: 1" in printed
    assert len(printed) < 600  # terminal output stays short


# 10: idempotent second run, --overwrite re-extracts
def test_second_run_is_idempotent(tmp_path, run_tool):
    pdf = make_text_pdf(tmp_path / "text.pdf", pages=2)
    out = tmp_path / "out"
    assert run_tool("--input", pdf, "--output", out) == 0
    raw_file = out / "text.raw.json"
    first_bytes, first_mtime = raw_file.read_bytes(), raw_file.stat().st_mtime_ns
    assert run_tool("--input", pdf, "--output", out) == 0
    assert load(out / "_run_summary.json")["totals"]["skipped"] == 1
    assert raw_file.stat().st_mtime_ns == first_mtime
    assert run_tool("--input", pdf, "--output", out, "--overwrite") == 0
    assert load(out / "_run_summary.json")["totals"]["skipped"] == 0
    assert raw_file.read_bytes() == first_bytes  # deterministic output


def test_summary_has_no_text(tmp_path, run_tool):
    pdf = make_text_pdf(tmp_path / "text.pdf", pages=5)
    out = tmp_path / "out"
    assert run_tool("--input", pdf, "--output", out) == 0
    summary_text = (out / "text.summary.json").read_text(encoding="utf-8")
    summary = json.loads(summary_text)
    assert summary["status"] == "ok" and len(summary["pages"]) == 5
    assert "text" not in summary["pages"][0] and "blocks" not in summary["pages"][0]
    assert "Beispieltext" not in summary_text


def test_parser_hook(tmp_path, run_tool):
    pdf = make_text_pdf(tmp_path / "text.pdf", pages=2)
    out = tmp_path / "out"
    parser = TOOL_DIR / "examples" / "example_parser.py"
    assert run_tool("--input", pdf, "--output", out, "--parser", parser) == 0
    parsed = load(out / "text.parsed.json")
    assert [p["page"] for p in parsed["pages"]] == [1, 2] and parsed["pages"][0]["words"] > 10
    # parser also runs when extraction is skipped
    (out / "text.parsed.json").unlink()
    assert run_tool("--input", pdf, "--output", out, "--parser", parser) == 0
    assert (out / "text.parsed.json").is_file()

    bad = tmp_path / "bad_parser.py"
    bad.write_text("def parse(raw, context):\n    raise ValueError('boom')\n", encoding="utf-8")
    assert run_tool("--input", pdf, "--output", out, "--parser", bad) == 1
    assert load(out / "_run_summary.json")["totals"]["parser_errors"] == 1


def test_broken_unicode_lowers_score():
    import pdf_to_json
    qcfg = pdf_to_json.DEFAULT_CONFIG["quality"]
    base = {"width": 595, "height": 842, "object_count": 3, "image_coverage": 0.0,
            "blocks": [{"text": "x", "bbox": [10, 10, 100, 30]}]}
    good = pdf_to_json.score_text_layer(dict(base, text="Guten Tag, schöne Grüße " * 10), qcfg)
    bad = pdf_to_json.score_text_layer(dict(base, text="G�t�n T�g " * 20), qcfg)
    stray = pdf_to_json.score_text_layer(dict(base, text="Scan 01", image_coverage=0.98), qcfg)
    assert good["score"] == 1.0
    assert bad["score"] < qcfg["min_page_score"] and bad["components"]["unicode"] == 0.0
    assert stray["score"] < qcfg["min_page_score"] and stray["components"]["density"] < 0.1


def test_cli_subprocess_missing_input(tmp_path):
    result = subprocess.run(
        [sys.executable, str(TOOL_DIR / "pdf_to_json.py"),
         "--input", str(tmp_path / "nope"), "--output", str(tmp_path / "out")],
        capture_output=True, text=True)
    assert result.returncode == 2 and "ERROR" in result.stdout
