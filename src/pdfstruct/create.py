"""pdfstruct.create - text held in memory -> document files on this computer.

    result = create_document(CreateRequest(name="NOTES", content="# Title\n...",
                                           formats=["docx", "pdf"]))

The entry point shared by the command line (pdfstruct-create), the window and the MCP
tool. It needs no source file, no OCR, no network and no LLM: the text is parsed into
the block model of pdfstruct.inputs and every format is rendered in memory. A file
only appears on disk complete; nothing else is written, not even temporarily.

Results never carry the text: only a status, the paths that were created and short
warnings.
"""
from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from . import docwriter, export
from .inputs import text as text_input
from .service import MAX_WARNINGS, short

FORMATS = {"docx": ".docx", "pdf": ".pdf", "html": ".html", "md": ".md", "txt": ".txt"}
CONTENT_TYPES = ("markdown", "text")
DEFAULT_FORMATS = ("docx",)
MAX_CONTENT_CHARS = 500_000  # far above what one conversation turn produces; larger: use a file
MAX_NAME_CHARS = 120
NAME_EXTENSIONS = (*FORMATS.values(), ".htm", ".markdown")
_FORBIDDEN_IN_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
                   *(f"{port}{number}" for port in ("COM", "LPT") for number in "0123456789")}
_IMAGE = re.compile(r"!\[[^\]]*\]\(")


@dataclass
class CreateRequest:
    name: str                                # file name without folder; an extension is optional
    content: str
    formats: list | tuple | str = DEFAULT_FORMATS
    output_dir: Path | str | None = None     # None: default_output_dir()
    content_type: str = "markdown"           # markdown | text
    overwrite: bool = False                  # replace existing files only when asked to


@dataclass
class CreateResult:
    status: str                              # created | conflict | invalid | failed
    outputs: list = field(default_factory=list)   # paths written by this call
    warnings: list = field(default_factory=list)  # at most MAX_WARNINGS, short
    error_code: str | None = None
    error: str | None = None                 # short and actionable; never the text

    @property
    def ok(self) -> bool:
        return self.status == "created"

    def to_dict(self) -> dict:
        data = {"status": self.status, "outputs": list(self.outputs), "warnings": list(self.warnings)}
        if self.error_code:
            data.update(error_code=self.error_code, error=self.error)
        return data


class CreateError(ValueError):
    """A request that cannot be carried out. `code` is a stable short identifier."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def default_output_dir() -> Path:
    """Where documents go when no folder is given: Documents/PDFStruct of the current user."""
    documents = Path.home() / "Documents"
    return (documents if documents.is_dir() else Path.home()) / "PDFStruct"


def normalize_formats(formats) -> list[str]:
    """Lower-case and without repeats, in the order asked for. Raises CreateError."""
    if isinstance(formats, str):
        formats = formats.replace(",", " ").split()
    wanted = [str(item).strip().lower().lstrip(".") for item in formats or [] if str(item).strip()]
    unknown = [item for item in wanted if item not in FORMATS]
    if unknown:
        raise CreateError("unsupported_format", f"unsupported format: {', '.join(unknown)} "
                                                f"(choose from {', '.join(FORMATS)})")
    if not wanted:
        raise CreateError("unsupported_format", f"no format given (choose from {', '.join(FORMATS)})")
    return list(dict.fromkeys(wanted))


def safe_name(name) -> tuple[str, str | None]:
    """A file name stem that is safe on Windows, macOS and Linux -> (stem, dropped extension).

    Folders, drive letters, traversal, control characters and reserved device names are
    rejected, never repaired. One trailing extension of a format this module writes is
    dropped, so "NOTES.docx" and "NOTES" name the same document."""
    if not isinstance(name, str) or not name.strip():
        raise CreateError("invalid_name", "name is empty")
    stem = name.strip()
    if _FORBIDDEN_IN_NAME.search(stem):
        raise CreateError("invalid_name", "name must be a plain file name: no folder, drive, "
                                          'control character or any of < > : " / \\ | ? *')
    dropped = next((ext for ext in NAME_EXTENSIONS if stem.lower().endswith(ext)), None)
    if dropped:
        stem = stem[:-len(dropped)]
    if not stem or stem.startswith(".") or stem.endswith((".", " ")):
        raise CreateError("invalid_name", "name must not be empty, start with a dot or end "
                                          "with a dot or space")
    if stem.split(".")[0].strip().upper() in _RESERVED_NAMES:
        raise CreateError("invalid_name", "name is a reserved Windows device name")
    if len(stem) > MAX_NAME_CHARS:
        raise CreateError("invalid_name", f"name is longer than {MAX_NAME_CHARS} characters")
    return stem, dropped


def _checked(request: CreateRequest) -> tuple[str, list[str], str, Path, list[str]]:
    stem, dropped = safe_name(request.name)
    formats = normalize_formats(request.formats)
    if request.content_type not in CONTENT_TYPES:
        raise CreateError("invalid_content_type",
                          f"content_type must be one of: {', '.join(CONTENT_TYPES)}")
    if not isinstance(request.content, str) or not request.content.strip():
        raise CreateError("empty_content", "content is empty")
    if len(request.content) > MAX_CONTENT_CHARS:
        raise CreateError("content_too_large",
                          f"content has {len(request.content)} characters; the limit is "
                          f"{MAX_CONTENT_CHARS}. Save it as a file and convert that file instead")
    content = export.clean("\n".join(text_input.split_lines(request.content.lstrip("﻿"))))
    try:
        out_dir = (Path(request.output_dir).expanduser().resolve() if request.output_dir
                   else default_output_dir())
    except (OSError, ValueError, RuntimeError):
        raise CreateError("invalid_output_dir", "output_dir is not a usable folder path") from None
    if out_dir.exists() and not out_dir.is_dir():
        raise CreateError("invalid_output_dir", "output_dir is a file, not a folder")
    notes = []
    if dropped and {".htm": "html", ".markdown": "md"}.get(dropped, dropped[1:]) not in formats:
        notes.append(f'name_extension_ignored: "{dropped}" in the name was dropped; '
                     "the formats decide the file types")
    return stem, formats, content, out_dir, notes


def _render(fmt: str, blocks: list[dict], content: str, content_type: str,
            title: str) -> tuple[bytes, list[str]]:
    """One format as file content -> (bytes, warnings). Nothing is written here."""
    if fmt == "docx":
        return docwriter.docx_bytes(blocks, title), []
    if fmt == "pdf":
        from . import pdfwriter
        return pdfwriter.render_blocks(blocks, title)
    if fmt == "html":
        return docwriter.html_text(blocks, title).encode("utf-8"), []
    if fmt == "md":  # Markdown stays as written; plain text is escaped so it stays literal
        text = content if content_type == "markdown" else "\n".join(export._md_blocks(blocks))
    else:            # plain text stays as written; Markdown loses its markup, not its text
        text = content if content_type == "text" else _plain_text(blocks)
    return (text.strip("\n") + "\n").encode("utf-8"), []


def _plain_text(blocks: list[dict]) -> str:
    """Markdown blocks as readable text: numbered lists count, table rows and items stay tight."""
    out: list[str] = []
    counters: dict[int, int] = {}
    previous = None
    for block in blocks:
        kind, text = block["kind"], block["text"]
        if kind != "list_item":
            counters.clear()
        if kind == "list_item":
            level = max(1, block.get("level") or 1)
            for deeper in [key for key in counters if key > level]:
                del counters[deeper]
            counters[level] = counters.get(level, 0) + 1 if block.get("ordered") else 0
            marker = f"{counters[level]}." if block.get("ordered") else "-"
            text = "  " * (level - 1) + f"{marker} {text}"
        elif kind == "rule":
            text = "-" * 40
        if out and not (kind in ("list_item", "table_row") and previous == kind):
            out.append("")
        out.append(text)
        previous = kind
    return "\n".join(out)


def _publish(target: Path, data: bytes, overwrite: bool) -> None:
    """Write `target` completely or not at all. Raises FileExistsError instead of replacing
    a file when `overwrite` is off, also when the file appeared after the first check."""
    partial = target.with_name(f".{target.name}.{secrets.token_hex(4)}.tmp")
    try:
        with partial.open("xb") as out:
            out.write(data)
        if overwrite:
            os.replace(partial, target)
            return
        try:
            os.link(partial, target)  # atomic, and fails when the target exists
        except FileExistsError:
            raise
        except OSError:               # a file system without hard links
            if target.exists():
                raise FileExistsError(str(target)) from None
            os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def create_document(request: CreateRequest) -> CreateResult:
    """Write `request.content` as one file per format, named exactly <name>.<format>.

    Every format is rendered before the first file is written, so a failure leaves
    nothing behind. Existing files are reported as a conflict and stay untouched unless
    `overwrite` is set. Never raises for a bad request: see CreateResult.status."""
    try:
        stem, formats, content, out_dir, notes = _checked(request)
    except CreateError as exc:
        return CreateResult("invalid", error_code=exc.code, error=short(exc))

    targets = {fmt: out_dir / (stem + FORMATS[fmt]) for fmt in formats}
    existing = [target.name for target in targets.values() if target.exists()]
    if existing and not request.overwrite:
        return CreateResult("conflict", error_code="already_exists", error=short(
            f"already exists, nothing was written: {', '.join(existing)}. Choose another name "
            "or folder, or allow overwriting"))

    rendered: dict[str, bytes] = {}
    fmt = formats[0]
    try:
        lines = text_input.split_lines(content)
        if request.content_type == "markdown":
            blocks = text_input.markdown_blocks(lines, rich=True)
            if _IMAGE.search(content):
                notes.append("images_not_embedded: pictures are not loaded; their alt text is kept")
        else:
            blocks = text_input.text_blocks(lines)
        first = blocks[0] if blocks else {}
        title = first["text"] if first.get("kind") == "heading" and first.get("level") == 1 else stem
        for fmt in formats:
            rendered[fmt], produced = _render(fmt, blocks, content, request.content_type, title)
            notes += produced
    except Exception as exc:  # the message of a writer may quote the text: report the type only
        return CreateResult("failed", error_code="render_failed",
                            error=f"{fmt} could not be created ({type(exc).__name__})")

    result = CreateResult("created", warnings=list(dict.fromkeys(short(n) for n in notes))[:MAX_WARNINGS])
    target = out_dir
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for fmt, target in targets.items():
            _publish(target, rendered[fmt], bool(request.overwrite))
            result.outputs.append(str(target))
    except FileExistsError:
        result.status, result.error_code = "conflict", "already_exists"
        result.error = short(f"{target.name} already exists and was not replaced")
    except OSError as exc:
        result.status, result.error_code = "failed", "write_failed"
        result.error = short(f"could not write to {out_dir} ({type(exc).__name__})")
    return result
