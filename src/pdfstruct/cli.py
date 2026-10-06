"""pdfstruct.cli - the pdfstruct command and its aliases (pdfjson, pdfhtml, ...).

Only decides WHAT to process and WHERE to write; extraction stays in
pdfstruct.extract and format generation in pdfstruct.export.

    pdfstruct                         menus: pick PDFs here, then formats
    pdfstruct belge.pdf               menu: pick formats for that file
    pdfstruct "C:/Belgeler"           menus for the PDFs in that folder
    pdfstruct belge.pdf --format xlsx non-interactive, one or more formats
    pdfjson belge.pdf | pdfjson       aliases: always non-interactive (no args = all PDFs
                                      here, else ./pdf/*.pdf) -> output/ next to the PDFs

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
    if prog == "pdfstruct":  # consumed earlier by main(); listed here for --help
        ap.add_argument("--format", action="append", metavar="FMT",
                        help="json, html, txt, md, csv, xlsx, docx, jsonl or sqlite; repeat or "
                             "comma-separate for several. Without it, pdfstruct shows menus.")
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

    rest = ["--input", str(input_path), "--output", str(out_dir), *_passthrough(args)]
    if command == "json":
        return run_json(rest, out_dir)
    return export.main(["--format", command, *rest])


def _passthrough(args) -> list[str]:
    """Extraction/export options of a parsed namespace as argv again."""
    rest = []
    for flag in ("force_ocr", "native_only", "overwrite"):
        if getattr(args, flag, False):
            rest.append("--" + flag.replace("_", "-"))
    for option in ("config", "parser"):
        if getattr(args, option, None):
            rest += ["--" + option, getattr(args, option)]
    return rest


def convert(pdfs: list[Path], formats: list[str], out_dir: Path, options: list[str],
            write=None) -> int:
    """N PDFs x M formats through the normal single-format path, one line per export.

    Each PDF is extracted at most once: the first format creates <name>.raw.json
    (json directly, any other format through export's missing-raw step) and the
    remaining formats reuse it. Returns the number of failed exports."""
    write = write or (lambda text: print(text, end=""))
    ordered = [f for f in COMMANDS if f in formats]  # json first, so extraction happens once
    failures = 0
    for pdf in pdfs:
        write(f"{pdf.name}\n")
        for fmt in ordered:
            argv = ["--input", str(pdf), "--output", str(out_dir), *options]
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                try:
                    code = extract.main(argv) if fmt == "json" else export.main(["--format", fmt, *argv])
                except Exception as exc:  # keep going with the other exports
                    captured.write(f"{type(exc).__name__}: {exc}\n")
                    code = 1
            if code == 0:
                write(f"  \u2713 {fmt.upper()}\n")
            else:
                failures += 1
                tail = captured.getvalue().strip().splitlines()
                write(f"  \u2717 {fmt.upper()}  {tail[-1] if tail else 'failed'}\n")
    return failures


def main(argv: list[str] | None = None, cwd: Path | None = None, **ui) -> int:
    """pdfstruct [path] [--format FORMAT ...] [options]

    With --format: non-interactive, exactly like the pdf<format> aliases
    (several formats run one after another). Without --format and on a real
    terminal: interactive menus. Without --format and without a terminal: usage."""
    from . import interactive

    pre = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    pre.add_argument("--format", action="append", default=[],
                     help="repeat or comma-separate for several: --format json --format xlsx")
    known, rest = pre.parse_known_args(sys.argv[1:] if argv is None else argv)
    cwd = (cwd or Path.cwd()).resolve()
    formats = [f.strip().lower() for item in known.format for f in item.split(",") if f.strip()]
    unknown = [f for f in formats if f not in COMMANDS]
    if unknown:
        print(f"unknown format: {', '.join(unknown)} (choose from {', '.join(COMMANDS)})")
        return 2
    known.format = list(dict.fromkeys(formats))
    if len(known.format) == 1:
        return run(known.format[0], rest, cwd, prog="pdfstruct")

    args = build_arg_parser("json", "pdfstruct").parse_args(rest)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    target = args.path or args.input_option
    out_dir = resolve_output(args.output, None, cwd) if args.output else None

    if known.format:  # several formats, non-interactive
        try:
            input_path, default_out = resolve_input(target, args.output, cwd)
        except InputError as exc:
            print(f"{exc}\n\n{usage('pdfstruct')}")
            return 2
        pdfs = [input_path] if input_path.is_file() else find_pdfs(input_path)
        failures = convert(pdfs, known.format, out_dir or default_out, _passthrough(args))
        print(f"\nOUTPUT: {out_dir or default_out}")
        return 1 if failures else 0

    path = (cwd / Path(target.rstrip('"')).expanduser()).resolve() if target else None
    if path is not None and not path.exists():
        print(f"Dosya veya klasör bulunamadı: {path}\n\n{usage('pdfstruct')}")
        return 2
    if path is not None and path.is_file() and path.suffix.lower() != ".pdf":
        print(f"PDF değil: {path}\n\n{usage('pdfstruct')}")
        return 2
    if not ui and not interactive.is_tty():
        print("pdfstruct needs a terminal for its menus. In scripts use --format, e.g.\n"
              "  pdfstruct belge.pdf --format json xlsx\n  pdfjson belge.pdf\n\n"
              + usage("pdfstruct"))
        return 2
    if not ui:
        interactive.enable_ansi()
    return interactive.session(cwd, path, out_dir, _passthrough(args), **ui)


def _alias(command: str):
    def entry_point() -> int:
        return run(command)
    entry_point.__name__ = f"pdf{command}"
    return entry_point


pdfjson, pdfhtml, pdftxt, pdfmd, pdfcsv, pdfxlsx, pdfdocx, pdfjsonl, pdfsqlite = (
    _alias(command) for command in COMMANDS)


if __name__ == "__main__":
    sys.exit(main())
