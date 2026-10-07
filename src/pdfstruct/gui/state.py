"""GUI state without Qt: the file queue, the chosen formats and the texts shown to the user.

Kept free of PySide6 so it can be tested everywhere and so importing it never loads Qt.
"""
from __future__ import annotations

from pathlib import Path

from .. import inputs, service

FORMAT_LABELS = {"json": "JSON", "html": "HTML", "txt": "TXT", "md": "Markdown", "csv": "CSV",
                 "xlsx": "XLSX", "docx": "DOCX", "jsonl": "JSONL", "sqlite": "SQLite", "pdf": "PDF"}
DEFAULT_FORMATS = ("json",)
FILE_DIALOG_FILTER = ("Supported files (" + " ".join(f"*{ext}" for ext in sorted(inputs.EXTENSIONS))
                      + ");;All files (*)")
PHASE_TEXT = {"extract": "Reading", "reuse": "Using existing extraction", "ocr": "OCR",
              "export": "Writing"}
STATUS_MARK = {"succeeded": "✓", "failed": "✗", "skipped": "–", "cancelled": "○"}


class Queue:
    """Ordered list of distinct, supported input files."""

    def __init__(self):
        self.files: list[Path] = []

    def add(self, paths) -> dict:
        """Add files (folders contribute their supported files, not recursively).
        -> {"added": [...], "duplicates": [...], "unsupported": [...], "missing": [...]}"""
        report = {"added": [], "duplicates": [], "unsupported": [], "missing": []}
        known = {self._key(p) for p in self.files}
        for item in paths:
            path = Path(item).expanduser()
            if path.is_dir():
                candidates = sorted((p for p in path.iterdir() if p.is_file() and inputs.is_supported(p)),
                                    key=lambda p: p.name.lower())
            elif path.is_file():
                candidates = [path]
            else:
                report["missing"].append(str(path))
                continue
            for candidate in candidates:
                candidate = candidate.resolve()
                if not inputs.is_supported(candidate):
                    report["unsupported"].append(str(candidate))
                elif self._key(candidate) in known:
                    report["duplicates"].append(str(candidate))
                else:
                    known.add(self._key(candidate))
                    self.files.append(candidate)
                    report["added"].append(str(candidate))
        return report

    @staticmethod
    def _key(path: Path) -> str:
        return str(Path(path).resolve()).casefold()

    def remove(self, indexes) -> None:
        for index in sorted(set(indexes), reverse=True):
            if 0 <= index < len(self.files):
                del self.files[index]

    def clear(self) -> None:
        self.files.clear()

    def __len__(self) -> int:
        return len(self.files)


def add_report_text(report: dict) -> str:
    parts = []
    if report["added"]:
        parts.append(f"{len(report['added'])} added")
    if report["duplicates"]:
        parts.append(f"{len(report['duplicates'])} already in the list")
    if report["unsupported"]:
        names = ", ".join(Path(p).name for p in report["unsupported"][:3])
        parts.append(f"{len(report['unsupported'])} unsupported ({names})")
    if report["missing"]:
        parts.append(f"{len(report['missing'])} not found")
    return "; ".join(parts) or "Nothing to add"


def build_request(files, formats, output_dir: str | None, force_ocr: bool = False) -> service.JobRequest:
    """Raises ValueError with a message for the user when nothing can be converted."""
    if not files:
        raise ValueError("Add at least one file.")
    chosen = service.normalize_formats(formats) if formats else []
    if not chosen:
        raise ValueError("Choose at least one output format.")
    return service.JobRequest(inputs=list(files), formats=chosen,
                              output_dir=(output_dir or "").strip() or None,
                              mode="force-ocr" if force_ocr else "auto")


class Progress:
    """Turns service events into what the window shows. Only real, measured steps."""

    def __init__(self):
        self.total = 0
        self.done = 0
        self.name = ""
        self.phase = ""
        self.detail = ""

    def update(self, event: dict) -> None:
        kind = event["type"]
        if kind == "job_started":
            self.total, self.done = event["files"], 0
        elif kind == "file_started":
            self.name, self.phase, self.detail = event["name"], "Starting", ""
        elif kind == "phase":
            self.phase = PHASE_TEXT.get(event["phase"], event["phase"])
            if event["phase"] == "ocr":
                self.detail = f"page {event['page']}"
            elif event["phase"] == "export":
                self.detail = FORMAT_LABELS.get(event["format"], event["format"])
            else:
                self.detail = ""
        elif kind == "page":
            self.detail = f"page {event['page']} of {event['pages']}"
        elif kind == "file_finished":
            self.done += 1

    @property
    def text(self) -> str:
        if not self.name:
            return ""
        position = f"File {min(self.done + 1, self.total)} of {self.total}: {self.name}"
        step = " – ".join(part for part in (self.phase, self.detail) if part)
        return f"{position}  ·  {step}" if step else position


def result_line(item: dict) -> str:
    """One row of the result list for a FileResult dict."""
    name = Path(item["input_path"]).name
    mark = STATUS_MARK.get(item["status"], "?")
    if item["status"] == "succeeded":
        written = ", ".join(label for key, label in FORMAT_LABELS.items() if key in item["outputs"])
        line = f"{mark} {name}  →  {written}"
        if item["skipped_formats"]:
            line += "  (skipped: " + ", ".join(f"{FORMAT_LABELS.get(f, f)} {reason}"
                                               for f, reason in item["skipped_formats"].items()) + ")"
        if item["review_pages"]:
            line += f"  ·  review pages: {', '.join(map(str, item['review_pages'][:8]))}"
        return line
    if item["status"] == "skipped":
        reasons = ", ".join(sorted(set(item["skipped_formats"].values()))) or "nothing to do"
        return f"{mark} {name}  skipped ({reasons})"
    if item["status"] == "cancelled":
        return f"{mark} {name}  cancelled"
    return f"{mark} {name}  {item.get('error') or 'failed'}"


def summary_text(result: dict) -> str:
    parts = [f"{result['succeeded']} converted"]
    if result["failed"]:
        parts.append(f"{result['failed']} failed")
    if result["skipped"]:
        parts.append(f"{result['skipped']} skipped")
    if result["cancelled_files"]:
        parts.append(f"{result['cancelled_files']} cancelled")
    text = ("Cancelled: " if result["cancelled"] else "Done: ") + ", ".join(parts)
    text += f"  ({result['seconds']} s)"
    if result.get("ocr_unavailable_reason"):
        text += "\n" + result["ocr_unavailable_reason"]
    return text


def output_folders(result: dict) -> list[str]:
    """Distinct folders that received files, in first-use order."""
    folders = []
    for item in result["files"]:
        for target in item["outputs"].values():
            folder = str(Path(target).parent)
            if folder not in folders:
                folders.append(folder)
    return folders
