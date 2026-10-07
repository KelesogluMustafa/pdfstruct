"""GUI logic that needs no Qt: queue, format selection, progress text, result rows."""
import json
import os
import subprocess
import sys

import pytest

from conftest import make_text_pdf
from pdfstruct.gui import state


def test_queue_rejects_duplicates_and_unsupported_files(tmp_path):
    make_text_pdf(tmp_path / "a.pdf")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    (tmp_path / "c.xyz").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.md").write_text("x", encoding="utf-8")
    queue = state.Queue()
    report = queue.add([tmp_path / "a.pdf", tmp_path / "c.xyz", tmp_path / "nope.pdf"])
    assert [len(report[k]) for k in ("added", "duplicates", "unsupported", "missing")] == [1, 0, 1, 1]
    again = queue.add([str(tmp_path / "a.pdf").upper() if os.name == "nt" else tmp_path / "a.pdf",
                       tmp_path])  # a folder adds its supported files, not its subfolders
    assert len(again["duplicates"]) == 2 and [p.name for p in queue.files] == ["a.pdf", "b.txt"]
    assert "already in the list" in state.add_report_text(again)
    assert "1 unsupported (c.xyz)" in state.add_report_text(report)
    queue.remove([0, 0, 7])
    assert [p.name for p in queue.files] == ["b.txt"]
    queue.clear()
    assert len(queue) == 0 and state.add_report_text(queue.add([])) == "Nothing to add"


def test_request_needs_files_and_formats(tmp_path):
    with pytest.raises(ValueError, match="Add at least one file"):
        state.build_request([], ["json"], None)
    with pytest.raises(ValueError, match="at least one output format"):
        state.build_request([tmp_path / "a.pdf"], [], None)
    request = state.build_request([tmp_path / "a.pdf"], ["pdf", "json"], "  ", force_ocr=True)
    assert request.formats == ["json", "pdf"] and request.output_dir is None and request.mode == "force-ocr"
    assert state.build_request([tmp_path / "a.pdf"], ["txt"], str(tmp_path)).output_dir == str(tmp_path)


def test_ten_formats_and_dialog_filter():
    assert list(state.FORMAT_LABELS) == ["json", "html", "txt", "md", "csv", "xlsx", "docx", "jsonl",
                                         "sqlite", "pdf"]
    for extension in (".pdf", ".docx", ".webp", ".tiff", ".md"):
        assert f"*{extension}" in state.FILE_DIALOG_FILTER


def test_progress_text_reports_only_real_steps():
    progress = state.Progress()
    assert progress.text == ""
    for event in [{"type": "job_started", "files": 2, "formats": ["json"]},
                  {"type": "file_started", "index": 1, "files": 2, "name": "scan.pdf", "path": "x"},
                  {"type": "phase", "phase": "extract"},
                  {"type": "page", "page": 3, "pages": 12, "method": "native"}]:
        progress.update(event)
    assert progress.text == "File 1 of 2: scan.pdf  ·  Reading – page 3 of 12"
    progress.update({"type": "phase", "phase": "ocr", "page": 4})
    assert progress.text.endswith("OCR – page 4")
    progress.update({"type": "phase", "phase": "export", "format": "xlsx"})
    assert progress.text.endswith("Writing – XLSX")
    progress.update({"type": "file_finished", "status": "succeeded"})
    assert (progress.done, progress.total) == (1, 2) and "%" not in progress.text


def test_result_rows_and_summary():
    ok = {"input_path": "C:/d/a.pdf", "status": "succeeded", "outputs": {"json": "C:/d/output/a.raw.json",
          "xlsx": "C:/d/output/a.xlsx"}, "skipped_formats": {"pdf": "already_pdf"}, "review_pages": [2, 5],
          "warnings": [], "error": None}
    assert state.result_line(ok) == "✓ a.pdf  →  JSON, XLSX  (skipped: PDF already_pdf)  ·  review pages: 2, 5"
    failed = dict(ok, status="failed", outputs={}, skipped_formats={}, review_pages=[], error="file not found")
    assert state.result_line(failed) == "✗ a.pdf  file not found"
    skipped = dict(failed, status="skipped", skipped_formats={"pdf": "already_pdf"}, error=None)
    assert state.result_line(skipped) == "– a.pdf  skipped (already_pdf)"
    assert state.result_line(dict(failed, status="cancelled")) == "○ a.pdf  cancelled"
    result = {"succeeded": 1, "failed": 1, "skipped": 1, "cancelled_files": 0, "cancelled": False,
              "seconds": 1.5, "ocr_unavailable_reason": None, "files": [ok, failed, skipped]}
    assert state.summary_text(result) == "Done: 1 converted, 1 failed, 1 skipped  (1.5 s)"
    assert [f.replace("\\", "/") for f in state.output_folders(result)] == ["C:/d/output"]


def test_cli_and_service_never_import_qt():
    code = ("import sys, json, pdfstruct.cli, pdfstruct.service, pdfstruct.mcp_server, pdfstruct.gui.state;"
            "print(json.dumps(sorted({m.split('.')[0] for m in sys.modules} & {'PySide6', 'shiboken6',"
            " 'paddle', 'paddleocr', 'mcp'})))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []
