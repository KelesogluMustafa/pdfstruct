"""pdfstruct.cli - the pdfstruct command and its aliases (pdfjson, pdfhtml, ...).

Only decides WHAT to process and WHERE to write; extraction stays in
pdfstruct.extract and format generation in pdfstruct.export.

    pdfstruct belge.pdf               one file            -> <its folder>/output
    pdfstruct "C:/Belgeler"           all PDFs in folder  -> <folder>/output
    pdfstruct                         all PDFs here       -> ./output
                                      else ./pdf/*.pdf    -> ./output   (old project layout)
    pdfstruct --format xlsx belge.pdf another format (default: json)

pdfjson, pdfhtml, pdftxt, pdfmd, pdfcsv, pdfxlsx, pdfdocx, pdfjsonl and pdfsqlite
are the same command with the format fixed.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

from . import __version__, export, extract

COMMANDS = ["json", *export.FORMATS]


class InputError(Exception):
    pass


def find_pdfs(folder: Path) -> list[Path]:
    """PDFs directly inside folder (no subfolders)."""
    return extract.collect_pdfs(folder) if folder.is_dir() else []


def has_raw(folder: Path) -> bool:
    return folder.is_dir() and any(folder.glob("*" + export.RAW_SUFFIX))


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


def usage(prog: str) -> str:
    return f'Kullanım:\n  {prog} belge.pdf\n  {prog} "C:\\Belgeler"\n  {prog}'


def build_arg_parser(command: str, prog: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=prog, epilog=usage(prog),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="PDF file or folder (default: PDFs in this folder)")
    ap.add_argument("--version", action="version", version=f"pdfstruct {__version__}")
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
        code = extract.main(argv)
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


def run(command: str, argv: list[str] | None = None, cwd: Path | None = None,
        prog: str | None = None) -> int:
    """One format command: resolve input/output, then extract or export."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    prog = prog or f"pdf{command}"
    args = build_arg_parser(command, prog).parse_args(sys.argv[1:] if argv is None else argv)
    try:
        input_path, out_dir = resolve_input(args.path or args.input_option, args.output,
                                            cwd or Path.cwd(), raw_ok=command != "json")
    except InputError as exc:
        print(f"{exc}\n\n{usage(prog)}")
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
    return export.main(["--format", command, *rest])


def main(argv: list[str] | None = None, cwd: Path | None = None) -> int:
    """pdfstruct [--format FORMAT] [path] [options]; FORMAT defaults to json."""
    pre = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    pre.add_argument("--format", choices=COMMANDS, default="json")
    known, rest = pre.parse_known_args(sys.argv[1:] if argv is None else argv)
    return run(known.format, rest, cwd, prog="pdfstruct")


def _alias(command: str):
    def entry_point() -> int:
        return run(command)
    entry_point.__name__ = f"pdf{command}"
    return entry_point


pdfjson, pdfhtml, pdftxt, pdfmd, pdfcsv, pdfxlsx, pdfdocx, pdfjsonl, pdfsqlite = (
    _alias(command) for command in COMMANDS)


if __name__ == "__main__":
    sys.exit(main())
