#!/usr/bin/env python3
"""pdf_cli - shared front end of pdfjson / pdfhtml / pdftxt / ... / pdfsqlite.

Only decides WHAT to process and WHERE to write; extraction stays in pdf_to_json
and format generation in pdf_export.

    pdfjson belge.pdf        one file            -> <its folder>/output
    pdfjson "C:/Belgeler"    all PDFs in folder  -> <folder>/output
    pdfjson                  all PDFs here       -> ./output
                             else ./pdf/*.pdf    -> ./output   (old project layout)

Usage:
    python pdf_cli.py <json|html|txt|md|csv|xlsx|docx|jsonl|sqlite> [path] [options]
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import pdf_export
import pdf_to_json

COMMANDS = ["json", *pdf_export.FORMATS]


class InputError(Exception):
    pass


def find_pdfs(folder: Path) -> list[Path]:
    """PDFs directly inside folder (no subfolders)."""
    return pdf_to_json.collect_pdfs(folder) if folder.is_dir() else []


def has_raw(folder: Path) -> bool:
    return folder.is_dir() and any(folder.glob("*" + pdf_export.RAW_SUFFIX))


def resolve_output(explicit: str | None, default: Path, cwd: Path) -> Path:
    return (cwd / Path(explicit).expanduser()).resolve() if explicit else default


def resolve_input(target: str | None, output: str | None, cwd: Path,
                  raw_ok: bool = False) -> tuple[Path, Path]:
    """-> (input file or folder, output folder).

    raw_ok: a folder without PDFs is still fine when its output already holds
    .raw.json files (format commands can work from those alone).
    """
    cwd = cwd.resolve()
    if target:
        # cmd turns a quoted path ending in a backslash ("C:\dir\") into dir"
        path = (cwd / Path(target.rstrip('"')).expanduser()).resolve()
        if path.is_file():
            if path.suffix.lower() != ".pdf":
                raise InputError(f"PDF değil: {path}")
            return path, resolve_output(output, path.parent / "output", cwd)
        if path.is_dir():
            out = resolve_output(output, path / "output", cwd)
            if find_pdfs(path) or (raw_ok and has_raw(out)):
                return path, out
            raise InputError(f"PDF bulunamadı: {path}")
        raise InputError(f"Dosya veya klasör bulunamadı: {path}")

    out = resolve_output(output, cwd / "output", cwd)
    if find_pdfs(cwd):
        return cwd, out
    if find_pdfs(cwd / "pdf"):
        return cwd / "pdf", out
    if raw_ok and has_raw(out):
        return cwd, out
    raise InputError("PDF bulunamadı.")


def usage(command: str) -> str:
    name = f"pdf{command}"
    return f'Kullanım:\n  {name} belge.pdf\n  {name} "C:\\Belgeler"\n  {name}'


def build_arg_parser(command: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=f"pdf{command}", epilog=usage(command),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="PDF file or folder (default: PDFs in this folder)")
    ap.add_argument("--input", dest="input_option", help=argparse.SUPPRESS)  # old spelling
    ap.add_argument("--output", help="output folder (default: 'output' next to the PDFs)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--force-ocr", action="store_true")
    mode.add_argument("--native-only", action="store_true")
    ap.add_argument("--config")
    if command == "json":
        ap.add_argument("--overwrite", action="store_true")
        ap.add_argument("--parser")
    return ap


def run_json(argv: list[str], out_dir: Path) -> int:
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        code = pdf_to_json.main(argv)
    summary_path = out_dir / "_run_summary.json"
    if code == 2 or not summary_path.is_file():
        print(captured.getvalue().rstrip())
        return code
    run = json.loads(summary_path.read_text(encoding="utf-8"))
    totals, documents = run["totals"], run["documents"]
    failed = [d for d in documents if d.get("status") == "error"]
    parser_failed = [d for d in documents if d.get("parser_error")]
    if len(documents) == 1 and not failed:
        doc = documents[0]
        score = doc["text_layer_score"]
        print(f"METHOD: {doc['method']}")
        print(f"TEXT_LAYER_SCORE: {'n/a' if score is None else format(score, '.2f')}")
    print(f"FILES FOUND: {totals['files']}")
    print(f"PROCESSED: {totals['files'] - totals['skipped'] - totals['errors']}")
    print(f"SKIPPED: {totals['skipped']}")
    print(f"FAILED: {totals['errors']}")
    print(f"PAGES: {totals['pages']}")
    print(f"OCR FILES: {totals['ocr'] + totals['mixed']}")
    print(f"REVIEW_PAGES: {totals['review_pages']}")
    if run.get("ocr_unavailable_reason"):
        print(f"OCR_UNAVAILABLE: {run['ocr_unavailable_reason']}")
    if "--parser" in argv:
        print(f"PARSED: {totals['parsed']}")
        print(f"PARSER_ERRORS: {totals['parser_errors']}")
    print(f"OUTPUT: {out_dir}")
    if failed:
        print("\nFAILED FILES:")
        for doc in failed:
            print(f"- {doc['file']}")
    if parser_failed:
        print("\nPARSER FAILED:")
        for doc in parser_failed:
            print(f"- {doc['file']}: {doc['parser_error']}")
    return code


def main(argv: list[str] | None = None, cwd: Path | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        print(f"ERROR: first argument must be one of: {', '.join(COMMANDS)}")
        return 2
    command = argv[0]
    args = build_arg_parser(command).parse_args(argv[1:])
    try:
        input_path, out_dir = resolve_input(args.path or args.input_option, args.output,
                                            cwd or Path.cwd(), raw_ok=command != "json")
    except InputError as exc:
        print(f"{exc}\n\n{usage(command)}")
        return 2

    rest = ["--input", str(input_path), "--output", str(out_dir)]
    for flag in ("force_ocr", "native_only", "overwrite"):
        if getattr(args, flag, False):
            rest.append("--" + flag.replace("_", "-"))
    for option in ("config", "parser"):
        if getattr(args, option, None):
            rest += ["--" + option, getattr(args, option)]
    if command == "json":
        return run_json(rest, out_dir)
    return pdf_export.main(["--format", command, *rest])


if __name__ == "__main__":
    sys.exit(main())
