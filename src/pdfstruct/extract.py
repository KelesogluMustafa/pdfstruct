#!/usr/bin/env python3
"""pdfstruct.extract - general-purpose local PDF -> raw JSON pipeline.

Deterministic bulk work only: native text extraction (pypdfium2) with an
automatic, per-page OCR fallback (PaddleOCR, loaded lazily in this process).
No semantic parsing happens here; project-specific parsers plug in via --parser.

Usage:
    python -m pdfstruct.extract --input <pdf file or folder> --output <folder>
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from . import __version__, ocr
from .ocr import OcrUnavailable  # noqa: F401  (re-exported for callers and tests)

TOOL_NAME = "pdfstruct"
TOOL_VERSION = __version__
SCHEMA_VERSION = "1.0"
PACKAGE_DIR = Path(__file__).resolve().parent

DEFAULT_CONFIG = {
    "quality": {
        # A page goes to OCR when its text layer score is below this value.
        "min_page_score": 0.5,
        # An image covering at least this share of the page marks a possible scan.
        "scan_image_coverage": 0.5,
        # Characters needed on such a page before the text layer is fully trusted.
        "min_chars_over_image": 100,
        # Share of broken characters (U+FFFD, controls, private use) that zeroes the score.
        "bad_char_ratio_fail": 0.10,
        # OCR pages with a mean confidence below this value are listed for review.
        "ocr_review_confidence": 0.60,
    },
    "ocr": {
        # Where PaddleX downloads and keeps the models. Empty = ~/.pdfstruct/models
        "model_cache_dir": "",
        "det_model": "PP-OCRv5_mobile_det",
        "rec_model": "latin_PP-OCRv5_mobile_rec",
        "device": "auto",  # auto (GPU when a CUDA build of paddlepaddle sees one) | cpu | gpu:0
        "enable_mkldnn": False,
        "dpi": 200,
        "max_side_px": 4000,
    },
}

# pdfium marks a hyphen at a line break with one of these; they are not damage.
_HYPHEN_MARKERS = {"\ufffe", "\x02"}


# ---------------------------------------------------------------- config

def default_config_path() -> Path:
    """$PDFSTRUCT_CONFIG if set, else ~/.pdfstruct/config.json (both optional)."""
    override = os.environ.get("PDFSTRUCT_CONFIG")
    return Path(override) if override else Path.home() / ".pdfstruct" / "config.json"


def load_config(path: Path | None) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    candidate = path or default_config_path()
    if candidate.is_file():
        user = json.loads(candidate.read_text(encoding="utf-8"))
        for section, values in user.items():
            if isinstance(values, dict) and isinstance(cfg.get(section), dict):
                cfg[section].update(values)
            else:
                cfg[section] = values
        # older configs pointed at a separate OCR Python; OCR now runs in-process
        for key in ocr.LEGACY_KEYS:
            cfg["ocr"].pop(key, None)
    elif path is not None:
        raise FileNotFoundError(f"config not found: {path}")
    return cfg


# ---------------------------------------------------------------- helpers

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, data) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def is_bad_char(ch: str) -> bool:
    if ch in _HYPHEN_MARKERS or ch in "\t\n\r":
        return False
    code = ord(ch)
    return (
        code == 0xFFFD
        or code < 0x20
        or 0x7F <= code <= 0x9F
        or 0xE000 <= code <= 0xF8FF
    )


# ---------------------------------------------------------------- native extraction

def _to_display_bbox(page, width, height, left, bottom, right, top):
    """PDF user space (origin bottom-left) -> display space in points
    (origin top-left, page rotation and crop box applied)."""
    scale = 100
    dx, dy = ctypes.c_int(), ctypes.c_int()
    xs, ys = [], []
    for x, y in ((left, bottom), (right, top)):
        pdfium_c.FPDF_PageToDevice(
            page.raw, 0, 0, int(round(width * scale)), int(round(height * scale)), 0,
            x, y, ctypes.byref(dx), ctypes.byref(dy),
        )
        xs.append(dx.value / scale)
        ys.append(dy.value / scale)
    return [min(xs), min(ys), max(xs), max(ys)]


def _image_coverage(page, page_area: float) -> float:
    """Largest single image on the page as a share of the page area."""
    best = 0.0
    try:
        for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=3):
            get_bounds = getattr(obj, "get_bounds", None) or getattr(obj, "get_pos")
            left, bottom, right, top = get_bounds()
            best = max(best, abs((right - left) * (top - bottom)))
    except Exception:
        return 0.0
    return min(1.0, best / page_area) if page_area > 0 else 0.0


def extract_native(page) -> dict:
    width, height = page.get_size()
    textpage = page.get_textpage()
    try:
        text = textpage.get_text_range().replace("\r\n", "\n").replace("\r", "\n")
        blocks = []
        for index in range(textpage.count_rects()):
            left, bottom, right, top = textpage.get_rect(index)
            block_text = textpage.get_text_bounded(
                left=left, bottom=bottom, right=right, top=top
            ).replace("\r\n", "\n").strip()
            if not block_text:
                continue
            bbox = _to_display_bbox(page, width, height, left, bottom, right, top)
            blocks.append({"text": block_text, "bbox": [round(v, 2) for v in bbox]})
    finally:
        textpage.close()
    return {
        "width": round(width, 2),
        "height": round(height, 2),
        "rotation": int(page.get_rotation()),
        "text": text,
        "blocks": blocks,
        "object_count": int(pdfium_c.FPDFPage_CountObjects(page.raw)),
        "image_coverage": round(_image_coverage(page, width * height), 3),
    }


# ---------------------------------------------------------------- quality score

def score_text_layer(native: dict, qcfg: dict) -> dict:
    """Explainable text layer score for one page.

    score = min(density, unicode, bbox), each in [0, 1]:
      density  1.0 unless a large image covers the page (possible scan); then
               chars / min_chars_over_image, so stray text on a scan scores low
      unicode  1.0 with no broken characters, 0.0 at bad_char_ratio_fail
      bbox     share of text blocks whose box is well-formed and on the page
    A page without text and without any page object is "blank" (score null).
    A page without text but with objects scores 0.0 (image/scan -> OCR).
    """
    text = native["text"]
    visible = [ch for ch in text if not ch.isspace()]
    chars = len(visible)
    bad = sum(1 for ch in visible if is_bad_char(ch))
    bad_ratio = bad / chars if chars else 0.0

    width, height = native["width"], native["height"]
    tol_x, tol_y = width * 0.05, height * 0.05
    blocks = native["blocks"]
    valid = sum(
        1 for b in blocks
        if b["bbox"][0] < b["bbox"][2] and b["bbox"][1] < b["bbox"][3]
        and b["bbox"][0] >= -tol_x and b["bbox"][1] >= -tol_y
        and b["bbox"][2] <= width + tol_x and b["bbox"][3] <= height + tol_y
    )

    quality = {
        "chars": chars,
        "bad_char_ratio": round(bad_ratio, 4),
        "block_count": len(blocks),
        "valid_bbox_ratio": round(valid / len(blocks), 3) if blocks else 0.0,
        "image_coverage": native["image_coverage"],
        "object_count": native["object_count"],
    }
    if chars == 0:
        blank = native["object_count"] == 0
        quality.update(blank=blank, components=None, score=None if blank else 0.0)
        return quality

    if native["image_coverage"] >= qcfg["scan_image_coverage"]:
        density = min(1.0, chars / qcfg["min_chars_over_image"])
    else:
        density = 1.0
    unicode_ok = max(0.0, 1.0 - bad_ratio / qcfg["bad_char_ratio_fail"])
    bbox_ok = valid / len(blocks) if blocks else 0.0
    components = {
        "density": round(density, 3),
        "unicode": round(unicode_ok, 3),
        "bbox": round(bbox_ok, 3),
    }
    quality.update(blank=False, components=components, score=min(components.values()))
    return quality


# ---------------------------------------------------------------- OCR

def ocr_page(page, native: dict, client: ocr.OcrEngine, ocfg: dict, tmp_dir: Path) -> dict:
    scale = ocfg["dpi"] / 72.0
    longest = max(native["width"], native["height"]) * scale
    if longest > ocfg["max_side_px"]:
        scale *= ocfg["max_side_px"] / longest
    image_path = tmp_dir / "page.png"
    bitmap = page.render(scale=scale)
    try:
        bitmap.to_pil().save(image_path)
    finally:
        bitmap.close()
    try:
        lines = client.ocr_image(image_path)
    finally:
        image_path.unlink(missing_ok=True)
    blocks, scores = [], []
    for line in lines:
        text = (line.get("text") or "").strip()
        if not text:
            continue
        block = {"text": text, "bbox": [round(v / scale, 2) for v in line["bbox"]]}
        if line.get("score") is not None:
            block["confidence"] = round(float(line["score"]), 4)
            scores.append(float(line["score"]))
        blocks.append(block)
    return {
        "text": "\n".join(b["text"] for b in blocks),
        "blocks": blocks,
        "confidence": round(sum(scores) / len(scores), 4) if scores else None,
    }


# ---------------------------------------------------------------- one document

def process_page(page, number: int, mode: str, cfg: dict, client: ocr.OcrEngine, tmp_dir: Path) -> dict:
    qcfg = cfg["quality"]
    native = extract_native(page)
    quality = score_text_layer(native, qcfg)
    warnings = []

    if quality["blank"]:
        wants_ocr = False
    elif mode == "force-ocr":
        wants_ocr = True
    else:
        wants_ocr = quality["score"] < qcfg["min_page_score"]

    method = "none" if quality["chars"] == 0 else "native"
    text, blocks = native["text"], native["blocks"]
    ocr_confidence = None
    needs_review = False

    if wants_ocr and mode == "native-only":
        warnings.append("low_text_layer_quality_native_only")
        needs_review = True
    elif wants_ocr:
        try:
            result = ocr_page(page, native, client, cfg["ocr"], tmp_dir)
            if not result["blocks"] and quality["chars"] > 0 and mode != "force-ocr":
                warnings.append("ocr_returned_nothing_kept_native")
                needs_review = True
            else:
                method, text, blocks = "ocr", result["text"], result["blocks"]
                ocr_confidence = result["confidence"]
                if ocr_confidence is not None and ocr_confidence < qcfg["ocr_review_confidence"]:
                    warnings.append("low_ocr_confidence")
                    needs_review = True
        except OcrUnavailable as exc:
            warnings.append(f"ocr_needed_but_unavailable: {exc}")
            needs_review = True
        except Exception as exc:
            warnings.append(f"ocr_failed: {exc}")
            needs_review = True

    for order, block in enumerate(blocks):
        block["order"] = order
    quality_out = {k: quality[k] for k in (
        "score", "components", "chars", "bad_char_ratio", "block_count",
        "valid_bbox_ratio", "image_coverage", "object_count", "blank")}
    return {
        "page": number,
        "width": native["width"],
        "height": native["height"],
        "rotation": native["rotation"],
        "method": method,
        "text_layer": quality_out,
        "ocr_confidence": ocr_confidence,
        "needs_review": needs_review,
        "warnings": warnings,
        "text": text,
        "blocks": blocks,
    }


def process_pdf(pdf_path: Path, raw_path: Path, summary_path: Path, mode: str,
                cfg: dict, client: ocr.OcrEngine, fingerprint: str, source: dict) -> dict:
    pages_tmp = raw_path.with_name(raw_path.name + ".pages.tmp")
    raw_tmp = raw_path.with_name(raw_path.name + ".tmp")
    page_summaries, doc_warnings = [], []
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page_count = len(pdf)
        with tempfile.TemporaryDirectory(prefix="pdfpipe_") as tmp, \
                pages_tmp.open("w", encoding="utf-8") as pages_out:
            for index in range(page_count):
                try:
                    page = pdf[index]
                    try:
                        record = process_page(page, index + 1, mode, cfg, client, Path(tmp))
                    finally:
                        page.close()
                except Exception as exc:
                    record = {
                        "page": index + 1, "width": None, "height": None, "rotation": None,
                        "method": "error", "text_layer": None, "ocr_confidence": None,
                        "needs_review": True, "warnings": [f"page_failed: {exc}"],
                        "text": "", "blocks": [],
                    }
                pages_out.write(("  " if index == 0 else ",\n  ")
                                + json.dumps(record, ensure_ascii=False))
                page_summaries.append({k: v for k, v in record.items()
                                       if k not in ("text", "blocks")}
                                      | {"chars_out": len(record["text"]),
                                         "blocks_out": len(record["blocks"])})
    finally:
        pdf.close()

    methods = [p["method"] for p in page_summaries]
    counts = {m: methods.count(m) for m in ("native", "ocr", "none", "error")}
    if counts["ocr"] and counts["native"]:
        doc_method = "mixed"
    elif counts["ocr"]:
        doc_method = "ocr"
    elif counts["native"]:
        doc_method = "native"
    else:
        doc_method = "none"
    scores = [p["text_layer"]["score"] for p in page_summaries
              if p["text_layer"] and p["text_layer"]["score"] is not None]
    text_layer_score = round(sum(scores) / len(scores), 3) if scores else None
    review_pages = [p["page"] for p in page_summaries if p["needs_review"]]
    if any("ocr_needed_but_unavailable" in w for p in page_summaries for w in p["warnings"]):
        doc_warnings.append("ocr_needed_but_unavailable")

    header = {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "fingerprint": fingerprint,
        "source": source,
        "source_file": source["path"],
        "extraction_method": doc_method,
        "text_layer_score": text_layer_score,
        "ocr_used": counts["ocr"] > 0,
        "ocr_engine": client.info if counts["ocr"] else None,
        "coordinate_system": {"unit": "pt", "origin": "top-left",
                              "bbox": "[x1, y1, x2, y2]", "note": "page rotation applied"},
        "page_count": page_count,
        "method_counts": counts,
        "review_pages": review_pages,
        "warnings": doc_warnings,
    }

    head = json.dumps(header, ensure_ascii=False, indent=1)
    with raw_tmp.open("w", encoding="utf-8") as out, pages_tmp.open("r", encoding="utf-8") as pages_in:
        out.write(head[:-2] + ',\n "pages": [\n')
        for chunk in iter(lambda: pages_in.read(1 << 20), ""):
            out.write(chunk)
        out.write("\n ]\n}\n")
    pages_tmp.unlink()
    os.replace(raw_tmp, raw_path)

    summary = dict(header, status="ok", raw_file=raw_path.name,
                   raw_size_bytes=raw_path.stat().st_size, pages=page_summaries)
    write_json_atomic(summary_path, summary)
    return summary


# ---------------------------------------------------------------- parser hook

def load_parser(path: Path):
    spec = importlib.util.spec_from_file_location(f"pdfpipe_parser_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "parse", None)):
        raise AttributeError(f"{path} must define parse(raw, context)")
    return module


def run_parser(module, raw_path: Path, out_dir: Path, stem: str) -> Path | None:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    context = {"raw_path": str(raw_path), "output_dir": str(out_dir),
               "stem": stem, "source_file": raw.get("source_file")}
    result = module.parse(raw, context)
    if result is None:
        return None
    target = out_dir / (stem + getattr(module, "OUTPUT_SUFFIX", ".parsed.json"))
    write_json_atomic(target, result)
    return target


# ---------------------------------------------------------------- CLI

def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Local PDF -> raw JSON (native text first, automatic OCR fallback).")
    ap.add_argument("--input", required=True, help="PDF file or folder containing PDFs")
    ap.add_argument("--output", required=True, help="output folder (created if missing)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--force-ocr", action="store_true", help="OCR every non-blank page")
    mode.add_argument("--native-only", action="store_true", help="never run OCR")
    ap.add_argument("--overwrite", action="store_true",
                    help="re-extract even if an up-to-date .raw.json exists")
    ap.add_argument("--parser", help="project parser .py defining parse(raw, context)")
    ap.add_argument("--config",
                    help="config JSON (default: $PDFSTRUCT_CONFIG or ~/.pdfstruct/config.json)")
    return ap


def collect_pdfs(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted((p for p in input_path.iterdir()
                   if p.is_file() and p.suffix.lower() == ".pdf"),
                  key=lambda p: p.name.lower())


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_arg_parser().parse_args(argv)
    input_path = Path(args.input).resolve()
    out_dir = Path(args.output).resolve()
    if not input_path.exists():
        print(f"ERROR: input not found: {input_path}")
        return 2
    try:
        cfg = load_config(Path(args.config) if args.config else None)
        parser_module = load_parser(Path(args.parser).resolve()) if args.parser else None
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2

    mode = "force-ocr" if args.force_ocr else "native-only" if args.native_only else "auto"
    pdfs = collect_pdfs(input_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    client = ocr.OcrEngine(cfg["ocr"])
    options_key = json.dumps({"mode": mode, "quality": cfg["quality"], "ocr": cfg["ocr"],
                              "tool": TOOL_VERSION}, sort_keys=True)

    started = time.time()
    totals = {"files": len(pdfs), "pages": 0, "native": 0, "ocr": 0, "mixed": 0, "none": 0,
              "skipped": 0, "errors": 0, "review_pages": 0, "parsed": 0, "parser_errors": 0}
    documents = []
    try:
        for pdf_path in pdfs:
            stem = pdf_path.stem
            raw_path = out_dir / f"{stem}.raw.json"
            summary_path = out_dir / f"{stem}.summary.json"
            entry = {"file": pdf_path.name}
            try:
                stat = pdf_path.stat()
                sha = sha256_file(pdf_path)
                fingerprint = hashlib.sha256((sha + options_key).encode()).hexdigest()[:16]
                summary = None
                if not args.overwrite and raw_path.is_file() and summary_path.is_file():
                    try:
                        previous = json.loads(summary_path.read_text(encoding="utf-8"))
                        if previous.get("status") == "ok" and previous.get("fingerprint") == fingerprint:
                            summary = previous
                            totals["skipped"] += 1
                            entry["status"] = "skipped"
                    except ValueError:
                        pass
                if summary is None:
                    source = {"path": str(pdf_path), "file_name": pdf_path.name,
                              "sha256": sha, "size_bytes": stat.st_size}
                    summary = process_pdf(pdf_path, raw_path, summary_path, mode, cfg,
                                          client, fingerprint, source)
                    entry["status"] = "ok"
                totals["pages"] += summary["page_count"]
                totals[summary["extraction_method"]] += 1
                totals["review_pages"] += len(summary["review_pages"])
                entry.update(method=summary["extraction_method"],
                             text_layer_score=summary["text_layer_score"],
                             ocr_used=summary["ocr_used"], pages=summary["page_count"],
                             review_pages=summary["review_pages"],
                             warnings=summary["warnings"], raw_file=raw_path.name)
            except Exception as exc:
                totals["errors"] += 1
                entry.update(status="error", error=f"{type(exc).__name__}: {exc}")
                for leftover in (raw_path.with_name(raw_path.name + ".pages.tmp"),
                                 raw_path.with_name(raw_path.name + ".tmp")):
                    leftover.unlink(missing_ok=True)
                write_json_atomic(summary_path, {
                    "status": "error", "source_file": str(pdf_path), "error": entry["error"],
                    "traceback": traceback.format_exc(limit=5)})
            if parser_module is not None and entry.get("status") in ("ok", "skipped"):
                try:
                    target = run_parser(parser_module, raw_path, out_dir, stem)
                    if target is not None:
                        totals["parsed"] += 1
                        entry["parsed_file"] = target.name
                except Exception as exc:
                    totals["parser_errors"] += 1
                    entry["parser_error"] = f"{type(exc).__name__}: {exc}"
            documents.append(entry)
    finally:
        client.close()

    run_summary = {"tool": {"name": TOOL_NAME, "version": TOOL_VERSION}, "mode": mode,
                   "input": str(input_path), "output": str(out_dir),
                   "seconds": round(time.time() - started, 2),
                   "ocr_engine": client.info, "ocr_unavailable_reason": client.failed_reason,
                   "totals": totals, "documents": documents}
    write_json_atomic(out_dir / "_run_summary.json", run_summary)

    if len(documents) == 1 and documents[0].get("status") in ("ok", "skipped"):
        doc = documents[0]
        score = doc["text_layer_score"]
        print(f"METHOD: {doc['method']}")
        print(f"TEXT_LAYER_SCORE: {'n/a' if score is None else format(score, '.2f')}")
        print(f"OCR_USED: {str(doc['ocr_used']).lower()}")
    print(f"FILES: {totals['files']}")
    print(f"PAGES: {totals['pages']}")
    print(f"NATIVE: {totals['native']}")
    print(f"OCR: {totals['ocr']}")
    print(f"MIXED: {totals['mixed']}")
    if totals["none"]:
        print(f"EMPTY: {totals['none']}")
    print(f"SKIPPED: {totals['skipped']}")
    print(f"REVIEW_PAGES: {totals['review_pages']}")
    if parser_module is not None:
        print(f"PARSED: {totals['parsed']}")
        print(f"PARSER_ERRORS: {totals['parser_errors']}")
    print(f"ERRORS: {totals['errors']}")
    if client.failed_reason:
        print(f"OCR_UNAVAILABLE: {client.failed_reason}")
    print(f"OUTPUT: {out_dir}")
    return 1 if totals["errors"] or totals["parser_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
