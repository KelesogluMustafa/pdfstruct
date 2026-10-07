"""pdfstruct.service - the one conversion entry point shared by CLI, GUI and MCP.

    result = run_job(JobRequest(inputs=[...], formats=["json", "xlsx"]))

Each input is extracted once (or its up-to-date raw JSON is reused) and every
requested format is written from that same result. One OCR engine lives for the
whole job and is only loaded when a page really needs OCR. Results never carry
document text: only status, counts, paths, short warnings and short errors.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import export, extract, ocr

MODES = ("auto", "force-ocr", "native-only")
OUTPUT_FORMATS = ["json", *export.FORMATS]
MAX_WARNINGS = 5
MAX_MESSAGE_CHARS = 200


@dataclass
class JobRequest:
    inputs: list
    formats: list
    output_dir: Path | str | None = None  # None: "output" next to each input
    mode: str = "auto"                    # auto | force-ocr | native-only
    overwrite: bool = False               # re-extract even if an up-to-date raw JSON exists
    config: Path | str | None = None
    parser: Path | str | None = None      # optional project parser (parse(raw, context))


@dataclass
class FileResult:
    input_path: str
    status: str = "failed"                # succeeded | failed | skipped | cancelled
    input_format: str | None = None
    method: str | None = None             # native | ocr | mixed | none
    pages: int | None = None              # logical pages / frames
    ocr_used: bool = False
    review_pages: list = field(default_factory=list)
    raw_reused: bool = False              # extraction skipped: up-to-date raw JSON found
    outputs: dict = field(default_factory=dict)          # format -> path
    skipped_formats: dict = field(default_factory=dict)  # format -> reason
    warnings: list = field(default_factory=list)         # at most MAX_WARNINGS, short
    error_code: str | None = None
    error: str | None = None              # short and actionable; never document text


@dataclass
class JobResult:
    files: list = field(default_factory=list)
    cancelled: bool = False
    seconds: float = 0.0
    ocr_engine: dict | None = None
    ocr_unavailable_reason: str | None = None

    def count(self, status: str) -> int:
        return sum(1 for f in self.files if f.status == status)

    @property
    def ok(self) -> bool:
        return not self.cancelled and self.count("failed") == 0 and self.count("cancelled") == 0

    def to_dict(self) -> dict:
        return {"ok": self.ok, "cancelled": self.cancelled, "seconds": self.seconds,
                "succeeded": self.count("succeeded"), "failed": self.count("failed"),
                "skipped": self.count("skipped"), "cancelled_files": self.count("cancelled"),
                "ocr_unavailable_reason": self.ocr_unavailable_reason,
                "files": [asdict(f) for f in self.files]}


def short(message, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = " ".join(str(message).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def normalize_formats(formats) -> list[str]:
    """Lower-case, de-duplicated, in canonical order (json first). Raises ValueError."""
    wanted = [str(f).strip().lower() for f in formats if str(f).strip()]
    unknown = [f for f in wanted if f not in OUTPUT_FORMATS]
    if unknown:
        raise ValueError(f"unknown format: {', '.join(unknown)} "
                         f"(choose from {', '.join(OUTPUT_FORMATS)})")
    if not wanted:
        raise ValueError("no output format given")
    return [f for f in OUTPUT_FORMATS if f in wanted]


def _collect_warnings(summary_path: Path, doc_warnings) -> list[str]:
    """Document warnings plus distinct page warnings from the (text-free) summary file."""
    found = list(doc_warnings or [])
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        for page in summary.get("pages") or []:
            for warning in page.get("warnings") or []:
                found.append(f"page {page.get('page')}: {warning}")
    except (OSError, ValueError):
        pass
    unique = list(dict.fromkeys(short(w) for w in found))
    if len(unique) > MAX_WARNINGS:
        unique = unique[:MAX_WARNINGS - 1] + [f"... and {len(unique) - MAX_WARNINGS + 1} more warnings"]
    return unique


def run_job(request: JobRequest, on_event=None, cancel=None) -> JobResult:
    """Convert every input into every requested format.

    on_event(dict) receives real, measurable steps only:
      job_started, file_started, phase (extract | reuse | ocr | export), page,
      export_done, file_finished, job_finished
    cancel() -> bool is polled between files, pages and exports. A native or OCR call
    that is already running finishes first; nothing partial is left on disk.
    """
    emit = on_event or (lambda event: None)
    is_cancelled = cancel or (lambda: False)
    started = time.time()
    result = JobResult()
    formats = normalize_formats(request.formats)
    if request.mode not in MODES:
        raise ValueError(f"unknown mode: {request.mode} (choose from {', '.join(MODES)})")
    cfg = extract.load_config(Path(request.config) if request.config else None)
    parser_module = extract.load_parser(Path(request.parser).resolve()) if request.parser else None
    inputs = [Path(p).expanduser().resolve() for p in request.inputs]
    opts_key = extract.options_key(request.mode, cfg)
    client = ocr.OcrEngine(cfg["ocr"])
    claimed: dict[Path, Path] = {}  # output base path -> input that owns it in this job

    emit({"type": "job_started", "files": len(inputs), "formats": formats})
    try:
        for index, path in enumerate(inputs):
            item = FileResult(input_path=str(path))
            result.files.append(item)
            if result.cancelled or is_cancelled():
                result.cancelled = True
                item.status = "cancelled"
                continue
            emit({"type": "file_started", "index": index + 1, "files": len(inputs),
                  "path": str(path), "name": path.name})
            try:
                _convert_one(path, item, request, formats, cfg, client, opts_key,
                             parser_module, claimed, emit, is_cancelled)
            except extract.Cancelled:
                result.cancelled = True
                item.status = "cancelled"
            except Exception as exc:  # one broken file never stops the batch
                item.status = "failed"
                item.error_code = item.error_code or "internal_error"
                item.error = short(f"{type(exc).__name__}: {exc}")
            emit({"type": "file_finished", "index": index + 1, "files": len(inputs),
                  "path": str(path), "name": path.name, "status": item.status,
                  "error": item.error,
                  "exports_failed": item.error_code == "export_failed"})
    finally:
        client.close()
    result.ocr_engine = client.info
    result.ocr_unavailable_reason = client.failed_reason
    result.seconds = round(time.time() - started, 2)
    emit({"type": "job_finished", "ok": result.ok, "cancelled": result.cancelled,
          "succeeded": result.count("succeeded"), "failed": result.count("failed"),
          "skipped": result.count("skipped")})
    return result


def _fail(item: FileResult, code: str, message: str) -> None:
    item.status, item.error_code, item.error = "failed", code, short(message)


def _convert_one(path, item, request, formats, cfg, client, opts_key, parser_module,
                 claimed, emit, is_cancelled) -> None:
    if not path.is_file():
        return _fail(item, "not_found", f"file not found: {path}")
    if path.suffix.lower() != ".pdf":
        return _fail(item, "unsupported_input", f"unsupported input type: {path.suffix or path.name}")
    item.input_format = "pdf"

    out_dir = (Path(request.output_dir).expanduser().resolve() if request.output_dir
               else path.parent / "output")
    key = extract.output_key(path)
    base = out_dir / key
    if claimed.setdefault(base, path) != path:
        return _fail(item, "output_name_collision",
                     f"{claimed[base].name} in this job already writes {key}.* to {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    entry = extract.extract_one(path, out_dir, request.mode, cfg, client, opts_key,
                                overwrite=request.overwrite, on_event=emit, cancel=is_cancelled)
    if entry["status"] == "error":
        return _fail(item, "extraction_failed", entry["error"])
    raw_path = out_dir / entry["raw_file"]
    item.raw_reused = entry["status"] == "skipped"
    if item.raw_reused:
        emit({"type": "phase", "phase": "reuse"})
    item.method = entry["method"]
    item.pages = entry["pages"]
    item.ocr_used = bool(entry["ocr_used"])
    item.review_pages = list(entry["review_pages"])
    item.warnings = _collect_warnings(out_dir / f"{key}.summary.json", entry["warnings"])

    if parser_module is not None:
        try:
            extract.run_parser(parser_module, raw_path, out_dir, key)
        except Exception as exc:
            item.warnings = (item.warnings + [short(f"parser failed: {type(exc).__name__}: {exc}")])[:MAX_WARNINGS]

    raw = None
    failed = []
    for fmt in formats:
        if is_cancelled():
            raise extract.Cancelled()
        emit({"type": "phase", "phase": "export", "format": fmt})
        try:
            if fmt == "json":
                target = raw_path
            else:
                target = out_dir / (key + export.FORMATS[fmt])
                if target == path:
                    raise ValueError("output would overwrite the source file")
                if raw is None:
                    raw = json.loads(raw_path.read_text(encoding="utf-8"))
                export.EXPORTERS[fmt](raw, target)
            item.outputs[fmt] = str(target)
            emit({"type": "export_done", "format": fmt, "ok": True, "path": str(target)})
        except Exception as exc:
            failed.append(fmt)
            (out_dir / (key + export.FORMATS.get(fmt, "") + ".tmp")).unlink(missing_ok=True)
            message = short(f"{type(exc).__name__}: {exc}")
            emit({"type": "export_done", "format": fmt, "ok": False, "error": message})
            item.error = message
    if failed:
        item.status = "failed"
        item.error_code = "export_failed"
        item.error = short(f"{', '.join(failed)} failed: {item.error}")
    else:
        item.status = "succeeded"
