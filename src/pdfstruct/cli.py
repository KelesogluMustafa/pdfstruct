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

    pdfstruct-create --name NOTES --format docx,pdf --content-file notes.md
                                      text or Markdown (a file or standard input) -> documents
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

from . import __version__, export, extract, inputs

COMMANDS = ["json", *export.FORMATS]             # ten output formats
ALIAS_COMMANDS = [c for c in COMMANDS if c != "pdf"]  # pdfjson ... pdfsqlite (no "pdfpdf")


class InputError(Exception):
    pass


def find_pdfs(folder: Path) -> list[Path]:
    """PDFs directly inside folder (no subfolders)."""
    return extract.collect_pdfs(folder) if folder.is_dir() else []


def find_inputs(folder: Path, all_types: bool = False) -> list[Path]:
    """PDFs directly inside folder, or with all_types every supported input type."""
    return extract.collect_inputs(folder, all_types) if folder.is_dir() else []


def has_raw(folder: Path) -> bool:
    return folder.is_dir() and any(folder.glob("*" + export.RAW_SUFFIX))


def resolve_output(explicit: str | None, default: Path, cwd: Path) -> Path:
    return (cwd / Path(explicit).expanduser()).resolve() if explicit else default


def resolve_input(target: str | None, output: str | None, cwd: Path,
                  raw_ok: bool = False, all_types: bool = False) -> tuple[Path, Path]:
    """-> (input file or folder, output folder).

    raw_ok: a folder without PDFs is still fine when its output already holds
    .raw.json files (format commands can work from those alone).
    """
    cwd = cwd.resolve()
    if target:
        # cmd turns a quoted path ending in a backslash ("C:\dir\") into dir"
        path = (cwd / Path(target.rstrip('"')).expanduser()).resolve()
        if path.is_file():
            if not inputs.is_supported(path):
                raise InputError(f"Desteklenmeyen dosya türü: {path}\n"
                                 f"Desteklenen: {', '.join(sorted(inputs.EXTENSIONS))}")
            return path, resolve_output(output, path.parent / "output", cwd)
        if path.is_dir():
            out = resolve_output(output, path / "output", cwd)
            if find_inputs(path, all_types) or (raw_ok and has_raw(out)):
                return path, out
            raise InputError(f"PDF bulunamadı: {path}" if not all_types
                             else f"Desteklenen dosya bulunamadı: {path}")
        raise InputError(f"Dosya veya klasör bulunamadı: {path}")

    out = resolve_output(output, cwd / "output", cwd)
    if find_inputs(cwd, all_types):
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
    ap.add_argument("path", nargs="?",
                    help="input file (PDF, DOCX, TXT, MD, HTML, JPG, PNG, TIFF, BMP, WebP) or a "
                         "folder (default: PDFs in this folder)")
    ap.add_argument("--version", action="version", version=f"pdfstruct {__version__}")
    if prog == "pdfstruct":  # consumed earlier by main(); listed here for --help
        ap.add_argument("--format", action="append", metavar="FMT",
                        help="json, html, txt, md, csv, xlsx, docx, jsonl, sqlite or pdf; repeat or "
                             "comma-separate for several. Without it, pdfstruct shows menus.")
    ap.add_argument("--input", dest="input_option", help=argparse.SUPPRESS)  # old spelling
    ap.add_argument("--output", help="output folder (default: 'output' next to the PDFs)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--force-ocr", action="store_true")
    mode.add_argument("--native-only", action="store_true")
    ap.add_argument("--config")
    ap.add_argument("--all-types", action="store_true",
                    help="in a folder, take every supported input type, not only PDFs")
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
                                            cwd or Path.cwd(), raw_ok=command != "json",
                                            all_types=args.all_types)
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
    for flag in ("force_ocr", "native_only", "overwrite", "all_types"):
        if getattr(args, flag, False):
            rest.append("--" + flag.replace("_", "-"))
    for option in ("config", "parser"):
        if getattr(args, option, None):
            rest += ["--" + option, getattr(args, option)]
    return rest


def job_options(args) -> dict:
    """Extraction options of a parsed namespace as service.JobRequest fields."""
    mode = ("force-ocr" if getattr(args, "force_ocr", False)
            else "native-only" if getattr(args, "native_only", False) else "auto")
    return {"mode": mode, "overwrite": bool(getattr(args, "overwrite", False)),
            "config": getattr(args, "config", None), "parser": getattr(args, "parser", None)}


def convert(paths: list[Path], formats: list[str], out_dir: Path, options: dict | None = None,
            write=None) -> int:
    """N inputs x M formats through the shared service, one line per export.

    Each input is extracted at most once and every format is written from that same
    result. Returns the number of failed exports (a failed extraction counts once)."""
    from . import service

    write = write or (lambda text: print(text, end=""))
    failures = 0

    def on_event(event: dict) -> None:
        nonlocal failures
        kind = event["type"]
        if kind == "file_started":
            write(f"{event['name']}\n")
        elif kind == "export_done" and event.get("skipped"):
            write(f"  - {event['format'].upper()}  skipped ({event['skipped']})\n")
        elif kind == "export_done" and event["ok"]:
            write(f"  \u2713 {event['format'].upper()}\n")
        elif kind == "export_done":
            failures += 1
            write(f"  \u2717 {event['format'].upper()}  {event['error']}\n")
        elif kind == "file_finished" and event["status"] == "failed" and not event.get("exports_failed"):
            failures += 1
            write(f"  \u2717 {event['error']}\n")

    try:
        result = service.run_job(service.JobRequest(inputs=list(paths), formats=list(formats),
                                                    output_dir=out_dir, **(options or {})),
                                 on_event=on_event)
    except Exception as exc:  # bad request (format, mode, config, parser)
        write(f"ERROR: {exc}\n")
        return 1
    for item in result.files:
        for warning in item.warnings:
            write(f"  ! {Path(item.input_path).name}: {warning}\n")
    if result.ocr_unavailable_reason:
        write(f"\nOCR_UNAVAILABLE: {result.ocr_unavailable_reason}\n")
    return failures


def main(argv: list[str] | None = None, cwd: Path | None = None, **ui) -> int:
    """pdfstruct [path] [--format FORMAT ...] [options]

    With --format: non-interactive, exactly like the pdf<format> aliases
    (several formats run one after another). Without --format and on a real
    terminal: interactive menus. Without --format and without a terminal: usage."""
    from . import interactive

    for stream in (sys.stdout, sys.stderr):  # before any help/usage text (Windows code pages)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
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
    target = args.path or args.input_option
    out_dir = resolve_output(args.output, None, cwd) if args.output else None

    if known.format:  # several formats, non-interactive
        try:
            input_path, default_out = resolve_input(target, args.output, cwd,
                                                    all_types=args.all_types)
        except InputError as exc:
            print(f"{exc}\n\n{usage('pdfstruct')}")
            return 2
        pdfs = [input_path] if input_path.is_file() else find_inputs(input_path, args.all_types)
        failures = convert(pdfs, known.format, out_dir or default_out, job_options(args))
        print(f"\nOUTPUT: {out_dir or default_out}")
        return 1 if failures else 0

    path = (cwd / Path(target.rstrip('"')).expanduser()).resolve() if target else None
    if path is not None and not path.exists():
        print(f"Dosya veya klasör bulunamadı: {path}\n\n{usage('pdfstruct')}")
        return 2
    if path is not None and path.is_file() and not inputs.is_supported(path):
        print(f"Desteklenmeyen dosya türü: {path}\n\n{usage('pdfstruct')}")
        return 2
    if not ui and not interactive.is_tty():
        print("pdfstruct needs a terminal for its menus. In scripts use --format, e.g.\n"
              "  pdfstruct belge.pdf --format json,xlsx\n  pdfjson belge.pdf\n\n"
              + usage("pdfstruct"))
        return 2
    if not ui:
        interactive.enable_ansi()
    return interactive.session(cwd, path, out_dir, job_options(args), **ui)


def _alias(command: str):
    def entry_point() -> int:
        return run(command)
    entry_point.__name__ = f"pdf{command}"
    return entry_point


pdfjson, pdfhtml, pdftxt, pdfmd, pdfcsv, pdfxlsx, pdfdocx, pdfjsonl, pdfsqlite = (
    _alias(command) for command in ALIAS_COMMANDS)


CREATE_EXAMPLES = """examples:
  pdfstruct-create --name NOTES --content-file notes.md
  pdfstruct-create --name NOTES --format docx,pdf --output "C:\\Documents" --content-file notes.md
  type notes.md | pdfstruct-create --name NOTES --format docx"""


def build_create_parser() -> argparse.ArgumentParser:
    from . import create as creator

    ap = argparse.ArgumentParser(
        prog="pdfstruct-create", epilog=CREATE_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Create local documents from text or Markdown. The text comes from "
                    "--content-file or from standard input, never from an argument.")
    ap.add_argument("--version", action="version", version=f"pdfstruct {__version__}")
    ap.add_argument("--name", help="file name of the documents, without folder and extension "
                                   "(default: the name of --content-file)")
    ap.add_argument("--content-file", metavar="FILE",
                    help="UTF-8 text or Markdown file; without it the text is read from "
                         "standard input")
    ap.add_argument("--format", action="append", default=[], metavar="FMT",
                    help=f"{', '.join(creator.FORMATS)}; repeat or comma-separate for several "
                         "(default: docx)")
    ap.add_argument("--output", metavar="DIR", help="output folder (default: the current folder)")
    ap.add_argument("--type", choices=creator.CONTENT_TYPES, dest="content_type",
                    help="how to read the text (default: markdown; text for a .txt file)")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace existing files; without it they are kept and reported")
    return ap


def create(argv: list[str] | None = None, cwd: Path | None = None, stdin=None) -> int:
    """pdfstruct-create: text or Markdown -> DOCX, PDF, HTML, Markdown, TXT.

    Prints the created paths and short warnings, never the text. Exit code 0 when every
    file was created, 1 for a conflict or a failure, 2 for a request that cannot be used."""
    from . import create as creator
    from .inputs import text as text_input

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_create_parser().parse_args(sys.argv[1:] if argv is None else argv)
    cwd = (cwd or Path.cwd()).resolve()
    out_dir = resolve_output(args.output, cwd, cwd)
    most = 4 * creator.MAX_CONTENT_CHARS + 4  # bytes: UTF-8 or UTF-16 with a byte order mark
    source = None
    if args.content_file:
        source = (cwd / Path(args.content_file).expanduser()).resolve()
        try:
            with source.open("rb") as handle:
                data = handle.read(most + 1)
        except OSError:
            print(f"ERROR: cannot read {source}")
            return 2
    else:
        stream = stdin if stdin is not None else sys.stdin
        if stream is None or stream.isatty():
            print("ERROR: no text. Use --content-file FILE or pipe the text in.\n\n" + CREATE_EXAMPLES)
            return 2
        data = stream.buffer.read(most + 1)
    if len(data) > most:  # never load a huge file just to refuse it
        print(f"INVALID: the text is larger than {creator.MAX_CONTENT_CHARS} characters; "
              "convert the file with pdfstruct instead")
        return 2
    name = args.name or (source.stem if source else "")
    if not name:
        print("ERROR: --name is required when the text comes from standard input")
        return 2
    formats = [f for item in args.format for f in item.split(",") if f.strip()] or list(
        creator.DEFAULT_FORMATS)
    try:  # the text file itself is never replaced, not even with --overwrite
        stem = creator.safe_name(name)[0]
        written = {(stem + creator.FORMATS[f]).lower() for f in creator.normalize_formats(formats)}
        if source and source.parent == out_dir and source.name.lower() in written:
            print(f"ERROR: {source.name} is the text file itself; choose another --name or --output")
            return 2
    except creator.CreateError:
        pass  # reported by the service below, with its own message
    content, notes = text_input.decode(data)
    content_type = args.content_type or (
        "text" if source and source.suffix.lower() == ".txt" else "markdown")
    result = creator.create_document(creator.CreateRequest(
        name=name, content=content, formats=formats, output_dir=out_dir,
        content_type=content_type, overwrite=args.overwrite))
    for path in result.outputs:
        print(f"CREATED: {path}")
    for warning in [*notes, *result.warnings]:
        print(f"WARNING: {warning}")
    if not result.ok:
        print(f"{result.status.upper()}: {result.error}")
        return 2 if result.status == "invalid" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
