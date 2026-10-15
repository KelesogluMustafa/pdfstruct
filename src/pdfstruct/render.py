"""pdfstruct.render - layout-faithful PDF from office documents through a real office engine.

The raw document holds text and structure only, so `pdfwriter` can only re-flow it. A DOCX
keeps its layout (text boxes, headers, images, fonts, columns) only when an office program
draws it. This module finds one and lets it export the PDF:

  1. Microsoft Word (Windows, COM through pywin32)
  2. LibreOffice (soffice --headless; Windows, Linux, macOS)

Every run happens in a separate process with a time limit, on a private copy of the source in
a temporary folder: the source is never opened in place, no lock or temporary file appears
next to it, and a renderer that hangs on a dialog is stopped. Word runs as its own hidden
instance (never the user's open Word) with macros disabled; only the Word process this run
started is stopped on a timeout. The PDF is written under a temporary name and moved into
place only after it opens and has at least one page.

    engine = render_pdf(source, target)   # -> "word" | "libreoffice"

Raises RenderUnavailable when no engine is installed and RenderFailed when every installed
engine failed. `PDFSTRUCT_RENDERER` = word | libreoffice | none limits the choice.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PDF_MODES = ("auto", "layout", "reflow")  # auto: layout when an engine exists, else re-flow
RENDERABLE = ("docx",)
ENGINES = ("word", "libreoffice")
TIMEOUT_SECONDS = int(os.environ.get("PDFSTRUCT_RENDER_TIMEOUT", "180"))
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_WD_EXPORT_PDF = 17
_WD_DO_NOT_SAVE = 0
_MSO_AUTOMATION_FORCE_DISABLE = 3
# Given to every document Word opens: ignored by unprotected files, while a password-protected
# file fails at once instead of waiting for a password dialog nobody can see.
_NO_PASSWORD = "pdfstruct-no-password"


class RenderUnavailable(Exception):
    """No layout engine is installed (or PDFSTRUCT_RENDERER=none)."""


class RenderFailed(Exception):
    """Every installed engine failed; the message names each engine and its reason."""


# ---------------------------------------------------------------- discovery

def _word_installed() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import win32com.client  # noqa: F401  (pywin32)
        import winreg
    except ImportError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID"):
            return True
    except OSError:
        return False


def soffice_path() -> str | None:
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return found
    candidates = []
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if base:
                candidates.append(Path(base) / "LibreOffice" / "program" / "soffice.exe")
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"))
    else:
        candidates += [Path("/usr/bin/soffice"), Path("/usr/lib/libreoffice/program/soffice"),
                       Path("/opt/libreoffice/program/soffice")]
    return next((str(c) for c in candidates if c.is_file()), None)


def available_engines() -> list[str]:
    """Installed engines in the order they are tried."""
    wanted = os.environ.get("PDFSTRUCT_RENDERER", "").strip().lower()
    if wanted == "none":
        return []
    engines = [e for e, ok in (("word", _word_installed()), ("libreoffice", soffice_path() is not None))
               if ok]
    return [e for e in engines if e == wanted] if wanted in ENGINES else engines


# ---------------------------------------------------------------- public entry point

def render_pdf(source: Path, target: Path, engines: list[str] | None = None,
               timeout: int = TIMEOUT_SECONDS) -> str:
    """Draw `source` with an office engine and write `target`. -> engine name."""
    source, target = Path(source), Path(target)
    order = available_engines() if engines is None else list(engines)
    if not order:
        raise RenderUnavailable("no layout renderer found (Microsoft Word or LibreOffice)")
    reasons = []
    for engine in order:
        try:
            _render_with(engine, source, target, timeout)
            return engine
        except RenderFailed as exc:
            reasons.append(f"{engine}: {exc}")
    raise RenderFailed("; ".join(reasons))


def layout_pdf(source: Path, target: Path, pdf_mode: str = "auto") -> tuple[str | None, str | None]:
    """The one pdf-mode decision, shared by the service and the export command.

    -> (engine, None) when an office engine wrote `target`, or (None, warning) when the
    caller must write the re-flow instead. pdf_mode "layout" raises RuntimeError rather
    than falling back; "reflow" never tries an engine."""
    if pdf_mode not in PDF_MODES:
        raise ValueError(f"unknown pdf mode: {pdf_mode} (choose from {', '.join(PDF_MODES)})")
    if pdf_mode == "reflow":
        return None, None
    try:
        return render_pdf(source, target), None
    except RenderUnavailable as exc:
        if pdf_mode == "layout":
            raise RuntimeError(f"{exc}; install one or use pdf mode 'reflow'") from None
        return None, f"pdf_layout_unavailable: {exc}; the PDF is a readable re-flow"
    except RenderFailed as exc:
        if pdf_mode == "layout":
            raise RuntimeError(f"layout rendering failed: {exc}") from None
        return None, f"pdf_layout_failed: {exc}; the PDF is a readable re-flow"


def _render_with(engine: str, source: Path, target: Path, timeout: int) -> None:
    with tempfile.TemporaryDirectory(prefix="pdfstruct_render_") as tmp:
        work = Path(tmp)
        copy = work / ("input" + source.suffix.lower())  # ASCII name, private copy
        shutil.copyfile(source, copy)
        produced = work / "input.pdf"
        if engine == "word":
            _run_word(copy, produced, work, timeout)
        elif engine == "libreoffice":
            _run_libreoffice(copy, work, timeout)
        else:
            raise RenderFailed(f"unknown engine {engine!r}")
        _check_pdf(produced)
        partial = target.with_name(target.name + ".tmp")
        shutil.copyfile(produced, partial)
        os.replace(partial, target)


def _check_pdf(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RenderFailed("no PDF was produced")
    import pypdfium2 as pdfium
    try:
        document = pdfium.PdfDocument(str(path))
        try:
            pages = len(document)
        finally:
            document.close()
    except Exception as exc:
        raise RenderFailed(f"the produced PDF does not open: {type(exc).__name__}") from exc
    if pages < 1:
        raise RenderFailed("the produced PDF has no pages")


# ---------------------------------------------------------------- Microsoft Word

def _word_pids() -> set[int]:
    try:
        listing = subprocess.run(["tasklist", "/FI", "IMAGENAME eq WINWORD.EXE", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, timeout=30,
                                 creationflags=_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    pids = set()
    for line in listing.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


def _kill(pids) -> None:
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       timeout=30, creationflags=_NO_WINDOW)


def _run_word(copy: Path, produced: Path, work: Path, timeout: int) -> None:
    pid_file, error_file = work / "word.pid", work / "word.error"
    command = [sys.executable, "-m", "pdfstruct.render", "word", str(copy), str(produced),
               str(pid_file), str(error_file)]
    try:
        subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=timeout, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        if pid_file.is_file():  # only the Word this run started, never the user's
            _kill(int(p) for p in pid_file.read_text().split() if p.isdigit())
        raise RenderFailed(f"Word did not finish within {timeout} s and was stopped") from None
    if error_file.is_file():
        raise RenderFailed(error_file.read_text(encoding="utf-8", errors="replace")[:200])


def _word_child(copy: str, produced: str, pid_file: str, error_file: str) -> int:
    """Runs in its own process: open `copy` in a private hidden Word and export `produced`."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    app = None
    try:
        before = _word_pids()
        app = win32com.client.DispatchEx("Word.Application")  # own instance, not the user's
        Path(pid_file).write_text(" ".join(str(p) for p in sorted(_word_pids() - before)))
        app.Visible = False
        app.DisplayAlerts = 0
        app.AutomationSecurity = _MSO_AUTOMATION_FORCE_DISABLE
        # FileName, ConfirmConversions, ReadOnly, AddToRecentFiles, PasswordDocument
        document = app.Documents.Open(copy, False, True, False, _NO_PASSWORD)
        try:
            document.ExportAsFixedFormat(OutputFileName=produced, ExportFormat=_WD_EXPORT_PDF,
                                         OpenAfterExport=False, OptimizeFor=0,
                                         IncludeDocProps=True, CreateBookmarks=1,
                                         DocStructureTags=True, BitmapMissingFonts=True)
        finally:
            document.Close(_WD_DO_NOT_SAVE)
        return 0
    except Exception as exc:
        Path(error_file).write_text(f"{type(exc).__name__}: {exc}"[:200], encoding="utf-8")
        return 1
    finally:
        if app is not None:
            try:
                app.Quit(_WD_DO_NOT_SAVE)
            except Exception:
                pass
        pythoncom.CoUninitialize()


# ---------------------------------------------------------------- LibreOffice

def _run_libreoffice(copy: Path, work: Path, timeout: int) -> None:
    soffice = soffice_path()
    if soffice is None:
        raise RenderFailed("LibreOffice (soffice) not found")
    profile = (work / "profile").as_uri()  # private profile: no clash with an open LibreOffice
    command = [soffice, f"-env:UserInstallation={profile}", "--headless", "--norestore",
               "--nolockcheck", "--nodefault", "--convert-to", "pdf", "--outdir", str(work), str(copy)]
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            _kill([process.pid])  # soffice.exe starts soffice.bin; /T stops both
        process.kill()
        process.wait()
        raise RenderFailed(f"LibreOffice did not finish within {timeout} s and was stopped") from None
    if process.returncode != 0:
        raise RenderFailed(f"LibreOffice ended with code {process.returncode}")


def main(argv: list[str] | None = None) -> int:
    """python -m pdfstruct.render word <copy.docx> <out.pdf> <pid file> <error file>"""
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 5 and args[0] == "word":
        return _word_child(*args[1:])
    print("usage: python -m pdfstruct.render word <copy.docx> <out.pdf> <pid file> <error file>",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
