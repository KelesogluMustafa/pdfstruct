"""pdfstruct.inputs - input adapters: one source format in, raw page records out.

An adapter only reads its format. It never exports and never decides output
names. PDF keeps its own extraction in `pdfstruct.extract`; every other format
is read here and written by `extract` as an additive schema 1.1 raw document:

    read(path, fmt, ...) -> {"pages": [...], "paged": bool, "warnings": [...],
                             "coordinate_system": dict | None}

Block kinds: paragraph, heading (with `level`), list_item (`level`, `ordered`),
table_row (`cells`, `table`), code, line (OCR / PDF text line with `bbox`).
Unpaged inputs have one logical page and no coordinates.
"""
from __future__ import annotations

from pathlib import Path

EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "md", ".markdown": "md",
    ".html": "html", ".htm": "html",
    ".jpg": "jpeg", ".jpeg": "jpeg",
    ".png": "png",
    ".tif": "tiff", ".tiff": "tiff",
    ".bmp": "bmp",
    ".webp": "webp",
}
IMAGE_FORMATS = ("jpeg", "png", "tiff", "bmp", "webp")
TEXT_FORMATS = ("docx", "txt", "md", "html")  # text is read directly; OCR never applies
INPUT_FORMATS = ("pdf", *TEXT_FORMATS, *IMAGE_FORMATS)


class InputError(Exception):
    """A problem the user can act on. `code` is a stable short identifier."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def input_format(path: Path) -> str | None:
    return EXTENSIONS.get(Path(path).suffix.lower())


def is_supported(path: Path) -> bool:
    return input_format(path) is not None


def is_image(fmt: str | None) -> bool:
    return fmt in IMAGE_FORMATS


def table_text(cells) -> str:
    return " | ".join(cell.replace("\n", " ").strip() for cell in cells)


def render_text(blocks: list[dict]) -> str:
    """Plain text of a block list: blank line between blocks, list items and table rows tight."""
    out: list[str] = []
    previous = None
    for block in blocks:
        kind = block.get("kind")
        text = block.get("text", "")
        if kind == "list_item":
            marker = "1." if block.get("ordered") else "-"
            text = "  " * (max(1, block.get("level") or 1) - 1) + f"{marker} {text}"
        tight = kind in ("list_item", "table_row") and previous == kind
        if out and not tight:
            out.append("")
        out.append(text)
        previous = kind
    return "\n".join(out)


def unpaged_page(blocks: list[dict], warnings: list[str] | None = None) -> dict:
    """The single logical page of a format without real pages."""
    for order, block in enumerate(blocks):
        block["order"] = order
    text = render_text(blocks)
    return {"page": 1, "width": None, "height": None, "rotation": None,
            "method": "native" if text.strip() else "none", "text_layer": None,
            "ocr_confidence": None, "needs_review": False, "warnings": list(warnings or []),
            "text": text, "blocks": blocks}


def read(path: Path, fmt: str, *, mode: str = "auto", cfg: dict | None = None, client=None,
         on_event=None, cancel=None) -> dict:
    """Read a non-PDF input. Raises InputError for problems the user can act on."""
    if fmt in IMAGE_FORMATS:
        from . import image
        return image.read(path, fmt, mode=mode, cfg=cfg or {}, client=client,
                          on_event=on_event, cancel=cancel)
    if fmt == "txt":
        from . import text
        document = text.read_txt(path)
    elif fmt == "md":
        from . import text
        document = text.read_markdown(path)
    elif fmt == "html":
        from . import html
        document = html.read(path)
    elif fmt == "docx":
        from . import docx
        document = docx.read(path)
    else:
        raise InputError("unsupported_input", f"unsupported input type: {path.suffix or path.name}")
    if mode != "auto":
        document["warnings"].append(
            f"ocr_mode_ignored: --{mode} has no effect on {fmt} input (text is read directly)")
    return document
