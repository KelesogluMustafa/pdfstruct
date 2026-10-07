"""The PySide6 window, driven offscreen: queue, formats, worker thread, cancel, results."""
import json
import os
import subprocess
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from conftest import make_docx, make_image, make_text_pdf  # noqa: E402
from pdfstruct import service  # noqa: E402
from pdfstruct.gui import worker  # noqa: E402
from pdfstruct.gui.window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    win = MainWindow()
    win.show()
    yield win
    win.close()
    win.deleteLater()
    app.processEvents()


def wait_until(app, condition, seconds=180) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def rows(window) -> list[str]:
    return [window.result_list.item(i).text() for i in range(window.result_list.count())]


def test_window_opens_without_loading_ocr():
    """A fresh process: the window appears, shows ten formats, closes, and OCR was never imported."""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run([sys.executable, "-m", "pdfstruct.gui.app", "--smoke-test"],
                            capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1].removeprefix("GUI_SMOKE "))
    assert report["visible"] and report["closed"] and report["ocr_loaded"] is False
    assert report["formats"][-1] == "PDF" and len(report["formats"]) == 10
    assert report["convert_enabled"] is False  # empty queue


def test_queue_buttons_drop_and_format_selection(window, tmp_path, app):
    make_text_pdf(tmp_path / "a.pdf")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    (tmp_path / "c.xyz").write_text("x", encoding="utf-8")
    assert not window.convert_button.isEnabled() and window.drop_hint.isVisible()
    report = window.add_paths([tmp_path / "a.pdf", tmp_path / "c.xyz"])
    assert len(report["added"]) == 1 and len(report["unsupported"]) == 1
    assert "unsupported (c.xyz)" in window.status_label.text()

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "a.pdf")), QUrl.fromLocalFile(str(tmp_path / "b.txt"))])
    window.dropEvent(QDropEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
    assert [p.name for p in window.queue.files] == ["a.pdf", "b.txt"]  # the duplicate was not added
    assert window.file_list.count() == 2 and window.file_list.item(0).text().startswith("a.pdf")
    assert window.convert_button.isEnabled() and not window.drop_hint.isVisible()

    assert window.selected_formats() == ["json"]
    window.toggle_all_formats()
    assert len(window.selected_formats()) == 10 and window.select_all_button.text() == "Select None"
    window.toggle_all_formats()
    assert window.selected_formats() == [] and not window.convert_button.isEnabled()
    window.start_conversion()
    assert not window.is_running()

    window.file_list.item(0).setSelected(True)
    app.processEvents()
    assert window.remove_button.isEnabled()
    window.remove_selected()
    assert [p.name for p in window.queue.files] == ["b.txt"]
    window.clear_queue()
    assert len(window.queue) == 0 and not window.clear_button.isEnabled()


def test_conversion_through_the_window(window, tmp_path, app, ocr_available):
    make_text_pdf(tmp_path / "bericht.pdf", pages=3)
    make_docx(tmp_path / "notiz.docx")
    (tmp_path / "text.txt").write_text("Merhaba dünya", encoding="utf-8")
    expected = ["bericht.pdf", "notiz.docx", "text.txt"]
    if ocr_available:
        make_image(tmp_path / "bild.png")
        expected = sorted([*expected, "bild.png"])
    window.add_paths([tmp_path])
    assert [p.name for p in window.queue.files] == expected
    for key in ("json", "txt", "pdf"):
        window.format_boxes[key].setChecked(True)
    seen = []
    window.start_conversion()
    assert window.is_running() and not window.convert_button.isEnabled() and window.cancel_button.isEnabled()
    window.worker.event.connect(seen.append)
    assert wait_until(app, lambda: not window.is_running()), "conversion did not finish"

    result = window.last_result
    assert result["ok"] and result["succeeded"] == len(expected) and not result["cancelled"]
    out = tmp_path / "output"
    assert (out / "bericht.raw.json").is_file() and (out / "bericht.txt").is_file()
    assert not (out / "bericht.pdf").exists()                      # PDF to PDF is skipped
    assert (out / "notiz.docx.pdf").stat().st_size > 1000 and (out / "text.txt.pdf").is_file()
    if ocr_available:
        assert (out / "bild.png.pdf").is_file() and "Hallo" in (out / "bild.png.txt").read_text(encoding="utf-8")
    listed = rows(window)
    assert any(r.startswith("✓ bericht.pdf  →  JSON, TXT  (skipped: PDF already_pdf)") for r in listed)
    assert any(r.startswith("✓ text.txt  →  JSON, TXT, PDF") for r in listed)
    assert window.summary_label.text().startswith(f"Done: {len(expected)} converted")
    assert window.open_button.isEnabled() and window.convert_button.isEnabled()
    assert window.progress_bar.maximum() == 1 and window.progress_bar.value() == 1
    assert {"job_started", "file_started", "phase", "page", "export_done", "file_finished",
            "job_finished"} <= {e["type"] for e in seen}
    assert window.progress.done == len(expected)


def test_failed_file_is_listed_and_the_rest_continues(window, tmp_path, app):
    make_text_pdf(tmp_path / "gut.pdf")
    (tmp_path / "weg.txt").write_text("x", encoding="utf-8")
    window.add_paths([tmp_path / "gut.pdf", tmp_path / "weg.txt"])
    (tmp_path / "weg.txt").unlink()  # disappears between queueing and converting
    window.start_conversion()
    assert wait_until(app, lambda: not window.is_running())
    assert window.last_result["succeeded"] == 1 and window.last_result["failed"] == 1
    assert any(r.startswith("✗ weg.txt  file not found") for r in rows(window))
    assert window.summary_label.text().startswith("Done: 1 converted, 1 failed")


def test_worker_cancel_is_cooperative(tmp_path, app):
    paths = []
    for n in range(6):
        path = tmp_path / f"n{n}.txt"
        path.write_text(f"Inhalt {n}", encoding="utf-8")
        paths.append(path)
    job = worker.JobWorker(service.JobRequest(inputs=paths, formats=["json", "txt"]))
    finished, events = [], []
    job.finished.connect(finished.append)
    job.event.connect(lambda e: (events.append(e), e["type"] == "file_finished" and job.cancel()))
    job.run()  # same thread: signals are delivered directly, so the cancel point is exact
    result = finished[0]
    assert result["cancelled"] and result["succeeded"] == 1 and result["cancelled_files"] == 5
    assert [f["status"] for f in result["files"]] == ["succeeded"] + ["cancelled"] * 5
    assert sum(1 for e in events if e["type"] == "file_started") == 1


def test_cancel_button_and_invalid_request(window, tmp_path, app):
    for n in range(40):
        (tmp_path / f"n{n:02d}.txt").write_text("Inhalt " * 50, encoding="utf-8")
    window.add_paths([tmp_path])
    window.format_boxes["pdf"].setChecked(True)
    window.start_conversion()
    window.cancel_conversion()
    assert not window.cancel_button.isEnabled() and "Cancelling" in window.status_label.text()
    assert wait_until(app, lambda: not window.is_running())
    result = window.last_result
    assert result["cancelled"] and result["cancelled_files"] >= 1
    assert window.summary_label.text().startswith("Cancelled:")
    assert any(r.endswith("cancelled") for r in rows(window))
    assert window.convert_button.isEnabled() and not window.cancel_button.isEnabled()

    failed = []
    job = worker.JobWorker(service.JobRequest(inputs=[tmp_path / "n00.txt"], formats=["exe"]))
    job.failed.connect(failed.append)
    job.run()
    assert failed and "unknown format" in failed[0]
