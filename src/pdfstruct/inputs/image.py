"""Image adapter: JPG, PNG, TIFF, BMP and WebP go straight to the existing OCR engine.

Every frame of a multi-page TIFF is one logical page. EXIF orientation is applied
first, so coordinates are pixels of the upright image, origin top-left.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from . import InputError

COORDINATES = {"unit": "px", "origin": "top-left", "bbox": "[x1, y1, x2, y2]",
               "note": "pixels of the upright image (EXIF orientation applied)"}


def frame_count(path: Path) -> int:
    from PIL import Image
    with Image.open(path) as image:
        return int(getattr(image, "n_frames", 1) or 1)


def upright_frames(path: Path, fmt: str):
    """Yield (number, total, RGB image) for each logical page, EXIF orientation applied."""
    from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

    try:
        image = Image.open(path)
    except (UnidentifiedImageError, OSError) as exc:
        raise InputError("invalid_image", f"not a readable image: {type(exc).__name__}") from exc
    with image:
        total = int(getattr(image, "n_frames", 1) or 1) if fmt == "tiff" else 1
        frames = ImageSequence.Iterator(image) if total > 1 else [image]
        for number, frame in enumerate(frames, start=1):
            if number > total:
                break
            upright = ImageOps.exif_transpose(frame)
            if upright.mode in ("RGBA", "LA", "P"):
                rgba = upright.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.split()[-1])
                upright = background
            elif upright.mode != "RGB":
                upright = upright.convert("RGB")
            yield number, total, upright


def read(path: Path, fmt: str, *, mode: str, cfg: dict, client, on_event=None, cancel=None) -> dict:
    from .. import extract, ocr

    if mode == "native-only":
        raise InputError("native_only_unsupported",
                         "an image has no text layer: --native-only cannot produce text from "
                         f"{path.name}; run without it to use OCR")
    if client is None or not (client.ocr is not None or ocr.available()):
        raise InputError("ocr_unavailable", ocr.unavailable_reason())
    ocfg = cfg.get("ocr") or extract.DEFAULT_CONFIG["ocr"]
    review_below = (cfg.get("quality") or extract.DEFAULT_CONFIG["quality"])["ocr_review_confidence"]
    warnings: list[str] = []
    pages: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="pdfstruct_img_") as tmp:
        target = Path(tmp) / "frame.png"
        for number, total, frame in upright_frames(path, fmt):
            if cancel is not None and cancel():
                raise extract.Cancelled()
            width, height = frame.size
            scale = min(1.0, ocfg["max_side_px"] / max(width, height))
            work = frame if scale == 1.0 else frame.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))))
            work.save(target)
            if on_event is not None:
                on_event({"type": "phase", "phase": "ocr", "page": number})
            try:
                lines = client.ocr_image(target)
            except ocr.OcrUnavailable as exc:
                raise InputError("ocr_unavailable", str(exc)) from exc
            finally:
                target.unlink(missing_ok=True)
            blocks, scores = [], []
            for line in lines:
                text = (line.get("text") or "").strip()
                if not text:
                    continue
                block = {"text": text, "bbox": [round(v / scale, 2) for v in line["bbox"]],
                         "kind": "line", "order": len(blocks)}
                if line.get("score") is not None:
                    block["confidence"] = round(float(line["score"]), 4)
                    scores.append(float(line["score"]))
                blocks.append(block)
            confidence = round(sum(scores) / len(scores), 4) if scores else None
            page_warnings = []
            if confidence is not None and confidence < review_below:
                page_warnings.append("low_ocr_confidence")
            pages.append({"page": number, "width": width, "height": height, "rotation": 0,
                          "method": "ocr" if blocks else "none", "text_layer": None,
                          "ocr_confidence": confidence, "needs_review": bool(page_warnings),
                          "warnings": page_warnings,
                          "text": "\n".join(b["text"] for b in blocks), "blocks": blocks})
            if on_event is not None:
                on_event({"type": "page", "page": number, "pages": total,
                          "method": pages[-1]["method"]})
    if fmt == "webp" and frame_count(path) > 1:
        warnings.append("animation_first_frame_only: only the first frame was read")
    if not any(page["blocks"] for page in pages):
        warnings.append("no_text_found: OCR did not find text in this image")
    return {"pages": pages, "paged": True, "warnings": warnings, "coordinate_system": COORDINATES}
