"""pdfstruct.create - text held in memory -> document files on this computer.

    result = create_document(CreateRequest(name="NOTES", content="# Title\n...",
                                           formats=["docx", "pdf"]))

The entry point shared by the command line (pdfstruct-create), the window and the MCP
tool. It needs no source file, no OCR, no network and no LLM: the text is parsed into
the block model of pdfstruct.inputs and every format is rendered in memory. No
source file is written. Every file is first written under a temporary name next to its
target and only then moved into place, so a document never appears half written.

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
MAX_BLOCKS = 20_000  # paragraphs, headings, list items, table rows; a 300-page book has fewer
MAX_NAME_CHARS = 120
MAX_TITLE_CHARS = 200  # document title in the file's metadata: the first heading, shortened
NAME_EXTENSIONS = (*FORMATS.values(), ".htm", ".markdown")
# Path syntax, control characters, lone surrogates and the characters that reorder text
# on screen (they can make "exe.docx" look like something else).
_FORBIDDEN_IN_NAME = re.compile('[<>:"/\\\\|?*\x00-\x1f\x7f-\x9f\ud800-\udfff\u202a-\u202e\u2066-\u2069]')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
                   *(f"{port}{number}" for port in ("COM", "LPT") for number in "0123456789\u00b9\u00b2\u00b3")}
_IMAGE = re.compile(r"!\[[^\]\n]{0,200}\]\(")  # bounded: only decides about a warning


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
    if not isinstance(formats, (list, tuple)):
        raise CreateError("unsupported_format", "formats must be a list of format names")
    wanted = [str(item).strip().lower().lstrip(".") for item in formats if str(item).strip()]
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
        if request.output_dir and re.search(r"[\x00-\x1f]", str(request.output_dir)):
            raise ValueError("control character in the folder path")
        out_dir = (Path(request.output_dir).expanduser().resolve() if request.output_dir
                   else default_output_dir())
    except (OSError, ValueError, RuntimeError, TypeError):
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


def _stage(target: Path, data: bytes) -> Path:
    """Write `data` next to `target` under a temporary name. The caller removes that file."""
    partial = target.with_name(f".{target.name}.{secrets.token_hex(4)}.tmp")
    try:
        with partial.open("xb") as out:
            out.write(data)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return partial


def _publish(partial: Path, target: Path, overwrite: bool) -> bool:
    """Move a staged file into place -> True when `target` did not exist before.

    Raises FileExistsError instead of replacing a file when `overwrite` is off, also when
    the file appeared after the first check."""
    if overwrite:
        existed = target.exists()
        os.replace(partial, target)
        return not existed
    try:
        os.link(partial, target)  # atomic, and fails when the target exists
    except FileExistsError:
        raise
    except OSError:               # a file system without hard links
        if target.exists():
            raise FileExistsError(str(target)) from None
        os.replace(partial, target)
    return True


def create_document(request: CreateRequest) -> CreateResult:
    """Write `request.content` as one file per format, named exactly <name>.<format>.

    All or nothing: every format is rendered, then every file is written under a
    temporary name, and only then are the files moved into place. If that last step fails
    part-way, the files this call had created are removed again; a file that `overwrite`
    had already replaced stays and is listed in `outputs`. Existing files are reported as
    a conflict and stay untouched unless `overwrite` is set. Never raises: see
    CreateResult.status."""
    try:
        stem, formats, content, out_dir, notes = _checked(request)
    except CreateError as exc:
        return CreateResult("invalid", error_code=exc.code, error=short(exc))

    targets = {fmt: out_dir / (stem + FORMATS[fmt]) for fmt in formats}
    folders = [target.name for target in targets.values() if target.is_dir()]
    if folders:  # never replaced, whatever `overwrite` says
        return CreateResult("conflict", error_code="already_exists", error=short(
            f"a folder with that name exists, nothing was written: {', '.join(folders)}"))
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
        if any(block.get("styles_dropped") for block in blocks):
            notes.append(f"inline_styles_dropped: a block with more than {text_input.MAX_SPANS} "
                         "styled pieces is written as plain text")
        if len(blocks) > MAX_BLOCKS:  # the writers need seconds per ten thousand blocks
            return CreateResult("invalid", error_code="content_too_large", error=(
                f"content has {len(blocks)} paragraphs, list items and table rows; the limit is "
                f"{MAX_BLOCKS}. Save it as a file and convert that file instead"))
        first = blocks[0] if blocks else {}
        title = first["text"] if first.get("kind") == "heading" and first.get("level") == 1 else stem
        title = " ".join(title.split())[:MAX_TITLE_CHARS]
        for fmt in formats:
            rendered[fmt], produced = _render(fmt, blocks, content, request.content_type, title)
            notes += produced
    except Exception as exc:  # the message of a writer may quote the text: report the type only
        return CreateResult("failed", error_code="render_failed",
                            error=f"{fmt} could not be created ({type(exc).__name__})")

    result = CreateResult("created", warnings=list(dict.fromkeys(short(n) for n in notes))[:MAX_WARNINGS])
    staged: dict[Path, Path] = {}  # target -> its complete file under a temporary name
    created: list[Path] = []       # targets that did not exist before this call
    target = out_dir
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for fmt, target in targets.items():   # a full disk or a read-only folder shows up
            staged[target] = _stage(target, rendered[fmt])  # here, before any target changes
        for target, partial in staged.items():
            if _publish(partial, target, bool(request.overwrite)):
                created.append(target)
            result.outputs.append(str(target))
    except Exception as exc:
        for path in created:  # all or nothing: take back what this call added
            path.unlink(missing_ok=True)
        result.outputs = [path for path in result.outputs if Path(path) not in created]
        if isinstance(exc, FileExistsError):
            result.status, result.error_code = "conflict", "already_exists"
            result.error = short(f"{target.name} already exists and was not replaced")
        else:  # the message may hold a path of the user; the type is enough
            result.status, result.error_code = "failed", "write_failed"
            result.error = short(f"could not write {target.name} ({type(exc).__name__})")
    finally:
        for partial in staged.values():
            partial.unlink(missing_ok=True)
    return result
