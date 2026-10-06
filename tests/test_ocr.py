"""Self-contained OCR: no external Python, lazy loading, graceful fallback."""
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from conftest import TOOL_DIR, make_scan_pdf, make_text_pdf
from pdfstruct import extract, ocr

SCHEMA = json.loads((TOOL_DIR / "schemas" / "raw_document.schema.json").read_text(encoding="utf-8"))


# 1 + 7: nothing in the shipped code or config points at the old external OCR environment
def test_no_hardcoded_external_ocr_paths():
    files = [*(TOOL_DIR / "src").rglob("*.py"), TOOL_DIR / "pyproject.toml",
             TOOL_DIR / "config.example.json", *TOOL_DIR.glob("*.cmd")]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "HermesOCR" not in text and "paddlex_cache" not in text, path
    cfg = extract.load_config(None)
    for key in ocr.LEGACY_KEYS:
        assert key not in cfg["ocr"]
    assert not any(":\\" in str(v) for v in cfg["ocr"].values())


# 7: an old config that still carries the legacy keys is accepted and cleaned
def test_legacy_config_keys_are_dropped(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"ocr": {"python": r"C:\old\python.exe",
                                          "python_candidates": [r"C:\old\python.exe"],
                                          "dpi": 150}}), encoding="utf-8")
    cfg = extract.load_config(config)
    assert cfg["ocr"]["dpi"] == 150
    assert "python" not in cfg["ocr"] and "python_candidates" not in cfg["ocr"]


# 6: model cache is a per-user path, configurable, never a fixed drive path
def test_model_cache_path_is_user_relative(tmp_path):
    default = ocr.model_cache_dir(extract.DEFAULT_CONFIG["ocr"])
    assert default == Path.home() / ".pdfstruct" / "models"
    assert ocr.model_cache_dir({"model_cache_dir": str(tmp_path)}) == tmp_path
    assert not ocr.models_cached({"model_cache_dir": str(tmp_path),
                                  "det_model": "x", "rec_model": "y"})


# 2 + 8: a native PDF is processed without importing the OCR stack at all
def test_native_extraction_does_not_import_ocr(tmp_path):
    pdf = make_text_pdf(tmp_path / "native.pdf", pages=3)
    code = ("import sys, json\n"
            "from pdfstruct import extract\n"
            f"rc = extract.main(['--input', {str(pdf)!r}, '--output', {str(tmp_path / 'out')!r}])\n"
            "print(json.dumps({'rc': rc, 'ocr': sorted(m for m in sys.modules "
            "if m.split('.')[0] in ('paddle', 'paddleocr', 'paddlex', 'cv2'))}))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            encoding="utf-8")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report == {"rc": 0, "ocr": []}
    raw = json.loads((tmp_path / "out" / "native.raw.json").read_text(encoding="utf-8"))
    assert raw["extraction_method"] == "native" and raw["ocr_engine"] is None


# 3: availability detection is a cheap spec lookup, and the package imports without OCR
def test_availability_detection(monkeypatch):
    assert isinstance(ocr.available(), bool)
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert ocr.available() is False
    assert "OCR support" in ocr.unavailable_reason()


# 5: OCR needed but not installed -> native text kept, page flagged, clear message
def test_graceful_error_when_ocr_unavailable(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ocr, "available", lambda: False)
    pdf = make_scan_pdf(tmp_path / "scan.pdf")
    out = tmp_path / "out"
    assert extract.main(["--input", str(pdf), "--output", str(out)]) == 0
    raw = json.loads((out / "scan.raw.json").read_text(encoding="utf-8"))
    jsonschema.validate(raw, SCHEMA)
    assert raw["ocr_used"] is False and raw["review_pages"] == [1]
    assert "ocr_needed_but_unavailable" in raw["warnings"]
    assert any("OCR support" in w for w in raw["pages"][0]["warnings"])
    printed = capsys.readouterr().out
    assert "OCR_UNAVAILABLE: OCR support" in printed
    run = json.loads((out / "_run_summary.json").read_text(encoding="utf-8"))
    assert "OCR support" in run["ocr_unavailable_reason"]


# 4 + 9 + 10: real OCR on a tiny generated scan, with PDFStruct's own engine
def test_force_ocr_uses_in_process_engine(tmp_path, ocr_available):
    if not ocr_available:
        pytest.skip("OCR packages not installed on this platform")
    pdf = make_text_pdf(tmp_path / "text.pdf")  # has a text layer: OCR only because forced
    out = tmp_path / "out"
    assert extract.main(["--input", str(pdf), "--output", str(out), "--force-ocr"]) == 0
    raw = json.loads((out / "text.raw.json").read_text(encoding="utf-8"))
    jsonschema.validate(raw, SCHEMA)
    assert raw["extraction_method"] == "ocr" and raw["ocr_used"] is True
    engine = raw["ocr_engine"]
    assert engine["engine"].startswith("paddleocr ") and engine["device"] in ("cpu", "gpu:0")
    assert "python" not in engine  # no external interpreter any more
    assert Path(engine["model_cache_dir"]) == ocr.model_cache_dir(extract.DEFAULT_CONFIG["ocr"])
    page = raw["pages"][0]
    assert page["method"] == "ocr" and page["ocr_confidence"] > 0.5
    assert "Beispieltext" in page["text"]
    assert all("confidence" in b and len(b["bbox"]) == 4 for b in page["blocks"])
    assert [b["order"] for b in page["blocks"]] == list(range(len(page["blocks"])))
    assert raw["method_counts"] == {"native": 0, "ocr": 1, "none": 0, "error": 0}
