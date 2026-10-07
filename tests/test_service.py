"""The shared conversion service: one extraction per input, structured results, events, cancel."""
import json
from pathlib import Path

import pytest

from conftest import make_text_pdf
from pdfstruct import extract, ocr, service
from pdfstruct.service import JobRequest, run_job


def count_extractions(monkeypatch) -> list:
    calls = []
    real = extract.process_pdf
    monkeypatch.setattr(extract, "process_pdf",
                        lambda *a, **k: calls.append(a[0].name) or real(*a, **k))
    return calls


def test_one_extraction_per_input_and_text_free_result(tmp_path, monkeypatch):
    for name in ("a.pdf", "b.pdf"):
        make_text_pdf(tmp_path / name, pages=2)
    calls = count_extractions(monkeypatch)
    engines = []
    real_engine = ocr.OcrEngine
    monkeypatch.setattr(ocr, "OcrEngine", lambda cfg: engines.append(1) or real_engine(cfg))

    result = run_job(JobRequest(inputs=[tmp_path / "a.pdf", tmp_path / "b.pdf"],
                                formats=["xlsx", "json", "txt", "JSON"]))
    assert result.ok and not result.cancelled
    assert sorted(calls) == ["a.pdf", "b.pdf"]  # once per input, not once per format
    assert len(engines) == 1                     # one OCR engine for the whole job
    assert result.ocr_engine is None             # ...and it was never loaded for native PDFs
    for item in result.files:
        assert item.status == "succeeded" and item.input_format == "pdf"
        assert item.method == "native" and item.pages == 2 and item.ocr_used is False
        assert list(item.outputs) == ["json", "txt", "xlsx"]  # canonical order, de-duplicated
        for path in item.outputs.values():
            assert Path(path).is_file() and Path(path).parent == tmp_path / "output"
        assert item.raw_reused is False and item.error is None
    dumped = json.dumps(result.to_dict(), ensure_ascii=False)
    assert "Beispieltext" not in dumped and "Zeile 1" not in dumped  # never document text
    assert result.to_dict()["succeeded"] == 2


def test_second_run_reuses_raw(tmp_path, monkeypatch):
    make_text_pdf(tmp_path / "a.pdf")
    request = JobRequest(inputs=[tmp_path / "a.pdf"], formats=["json", "md"])
    assert run_job(request).files[0].raw_reused is False
    calls = count_extractions(monkeypatch)
    events = []
    second = run_job(request, on_event=events.append)
    assert calls == [] and second.files[0].raw_reused is True and second.ok
    assert {"type": "phase", "phase": "reuse"} in events
    request.overwrite = True
    assert run_job(request).files[0].raw_reused is False and calls == ["a.pdf"]


def test_events_are_real_steps(tmp_path):
    make_text_pdf(tmp_path / "a.pdf", pages=3)
    events = []
    run_job(JobRequest(inputs=[tmp_path / "a.pdf"], formats=["json", "csv"]), on_event=events.append)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "job_started" and kinds[-1] == "job_finished"
    assert kinds.index("file_started") < kinds.index("page") < kinds.index("export_done")
    pages = [e for e in events if e["type"] == "page"]
    assert [(e["page"], e["pages"]) for e in pages] == [(1, 3), (2, 3), (3, 3)]
    assert [e["format"] for e in events if e["type"] == "export_done"] == ["json", "csv"]
    assert not any("percent" in e for e in events)  # no invented percentages
    assert events[-1]["succeeded"] == 1


def test_broken_file_does_not_stop_the_batch(tmp_path):
    make_text_pdf(tmp_path / "a.pdf")
    (tmp_path / "bozuk.pdf").write_bytes(b"%PDF-1.4\nnot a pdf\n" + bytes(range(256)))
    make_text_pdf(tmp_path / "c.pdf")
    result = run_job(JobRequest(inputs=sorted(tmp_path.glob("*.pdf")), formats=["json", "txt"]))
    assert [f.status for f in result.files] == ["succeeded", "failed", "succeeded"]
    broken = result.files[1]
    assert broken.error_code == "extraction_failed" and broken.error and len(broken.error) <= 200
    assert broken.outputs == {} and result.ok is False
    assert not list((tmp_path / "output").glob("*.tmp"))


def test_missing_and_unsupported_inputs(tmp_path):
    (tmp_path / "notes.xyz").write_text("x", encoding="utf-8")
    result = run_job(JobRequest(inputs=[tmp_path / "nope.pdf", tmp_path / "notes.xyz"],
                                formats=["json"]))
    assert [f.error_code for f in result.files] == ["not_found", "unsupported_input"]
    assert not (tmp_path / "output").exists()


def test_bad_request_raises_before_any_work(tmp_path):
    make_text_pdf(tmp_path / "a.pdf")
    with pytest.raises(ValueError, match="unknown format"):
        run_job(JobRequest(inputs=[tmp_path / "a.pdf"], formats=["json", "exe"]))
    with pytest.raises(ValueError, match="no output format"):
        run_job(JobRequest(inputs=[tmp_path / "a.pdf"], formats=[]))
    with pytest.raises(ValueError, match="unknown mode"):
        run_job(JobRequest(inputs=[tmp_path / "a.pdf"], formats=["json"], mode="fast"))
    assert not (tmp_path / "output").exists()


def test_output_dir_and_name_collision(tmp_path):
    for folder in ("one", "two"):
        (tmp_path / folder).mkdir()
        make_text_pdf(tmp_path / folder / "same.pdf")
    out = tmp_path / "all out"
    result = run_job(JobRequest(inputs=[tmp_path / "one" / "same.pdf", tmp_path / "two" / "same.pdf"],
                                formats=["json"], output_dir=out))
    assert result.files[0].status == "succeeded"
    assert result.files[1].error_code == "output_name_collision"
    raw = json.loads((out / "same.raw.json").read_text(encoding="utf-8"))
    assert Path(raw["source"]["path"]).parent.name == "one"  # the first input kept its output


def test_cancel_between_files(tmp_path):
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        make_text_pdf(tmp_path / name)
    finished = []
    result = run_job(JobRequest(inputs=sorted(tmp_path.glob("*.pdf")), formats=["json", "txt"]),
                     on_event=lambda e: finished.append(e) if e["type"] == "file_finished" else None,
                     cancel=lambda: len(finished) >= 1)
    assert result.cancelled and result.ok is False
    assert [f.status for f in result.files] == ["succeeded", "cancelled", "cancelled"]
    assert sorted(p.name for p in (tmp_path / "output").glob("*.raw.json")) == ["a.raw.json"]


def test_cancel_between_pages_leaves_nothing_partial(tmp_path):
    make_text_pdf(tmp_path / "long.pdf", pages=10)
    pages = []
    result = run_job(JobRequest(inputs=[tmp_path / "long.pdf"], formats=["json", "txt"]),
                     on_event=lambda e: pages.append(e) if e["type"] == "page" else None,
                     cancel=lambda: len(pages) >= 3)
    assert result.cancelled and result.files[0].status == "cancelled"
    assert len(pages) == 3  # stopped at the next safe point, not mid-page
    assert list((tmp_path / "output").iterdir()) == []


def test_warnings_are_capped_and_short(tmp_path):
    summary = tmp_path / "x.summary.json"
    summary.write_text(json.dumps({"pages": [
        {"page": n, "warnings": [f"low_ocr_confidence {'x' * 400} {n}"]} for n in range(1, 12)]}),
        encoding="utf-8")
    warnings = service._collect_warnings(summary, ["doc_level"])
    assert len(warnings) == service.MAX_WARNINGS and warnings[0] == "doc_level"
    assert all(len(w) <= service.MAX_MESSAGE_CHARS for w in warnings)
    assert warnings[-1].startswith("... and ")
