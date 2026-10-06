"""pdfstruct.interactive - the menu shown by a bare `pdfstruct`.

Pure terminal, no extra dependency: a tiny key reader (msvcrt on Windows,
termios elsewhere) and ANSI redraws. Everything that decides something is a
plain function that takes `read_key` / `write` so tests can drive it with a
scripted key list instead of a keyboard. Conversion itself goes through
`cli.convert`, the same code path as `pdfstruct file.pdf --format ...`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FORMAT_LABELS = {"json": "JSON", "html": "HTML", "txt": "TXT", "md": "Markdown", "csv": "CSV",
                 "xlsx": "XLSX", "docx": "DOCX", "jsonl": "JSONL", "sqlite": "SQLite"}


# ---------------------------------------------------------------- terminal

def is_tty() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def enable_ansi() -> None:
    """Windows consoles need virtual terminal processing for cursor movement."""
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def read_key() -> str:
    """One key press as a name: up, down, enter, space, esc, or the lowercase character."""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            code = msvcrt.getwch()
            return {"H": "up", "P": "down"}.get(code, "")
        if ch == "\x03":
            raise KeyboardInterrupt
        return {"\r": "enter", "\n": "enter", " ": "space", "\x1b": "esc"}.get(ch, ch.lower())
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2) if select_ready() else ""
            return {"[A": "up", "[B": "down"}.get(seq, "esc")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    if ch == "\x03":
        raise KeyboardInterrupt
    return {"\r": "enter", "\n": "enter", " ": "space"}.get(ch, ch.lower())


def select_ready() -> bool:
    import select
    return bool(select.select([sys.stdin], [], [], 0.05)[0])


# ---------------------------------------------------------------- menu

class Menu:
    """Multi-select list. run() -> ("ok", [chosen indexes]) | ("back", None) | ("quit", None)."""

    def __init__(self, title: str, items: list[str], selected=(), confirm: str = "Continue",
                 allow_back: bool = False):
        self.title = title
        self.items = items
        self.selected = set(selected)
        self.cursor = 0
        self.confirm = confirm
        self.allow_back = allow_back
        self._drawn = 0

    def render(self) -> str:
        lines = [self.title, ""]
        for index, item in enumerate(self.items):
            mark = "x" if index in self.selected else " "
            pointer = ">" if index == self.cursor else " "
            lines.append(f"{pointer} [{mark}] {item}")
        lines += ["", "↑ ↓     Move", "SPACE   Select / deselect", "A       Select all / deselect all",
                  f"ENTER   {self.confirm}"]
        if self.allow_back:
            lines.append("B       Back")
        lines.append("Q       Quit")
        return "\n".join(lines) + "\n"

    def draw(self, write) -> None:
        if self._drawn:
            write(f"\x1b[{self._drawn}A\x1b[J")  # cursor up, clear to end of screen
        text = self.render()
        write(text)
        self._drawn = text.count("\n")

    def handle(self, key: str) -> tuple | None:
        if key == "up":
            self.cursor = (self.cursor - 1) % len(self.items)
        elif key == "down":
            self.cursor = (self.cursor + 1) % len(self.items)
        elif key == "space":
            self.selected ^= {self.cursor}
        elif key == "a":
            self.selected = set() if len(self.selected) == len(self.items) else set(range(len(self.items)))
        elif key == "enter":
            if self.selected:
                return ("ok", sorted(self.selected))
        elif key == "b" and self.allow_back:
            return ("back", None)
        elif key in ("q", "esc"):
            return ("quit", None)
        return None

    def run(self, read_key=read_key, write=None) -> tuple:
        write = write or _write
        self.draw(write)
        while True:
            try:
                key = read_key()
            except KeyboardInterrupt:
                write("\n")
                return ("quit", None)
            result = self.handle(key)
            if result is not None:
                return result
            self.draw(write)


def _write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


# ---------------------------------------------------------------- session

def find_pdfs(folder: Path) -> list[Path]:
    from .cli import find_pdfs as _find
    return _find(folder)


def choose_pdfs(folder: Path, read_key, write, read_line) -> tuple[str, Path, list[Path]]:
    """Loop until the user picked files, chose another folder, or quit.
    -> ("ok", folder, files) | ("quit", folder, [])"""
    while True:
        pdfs = find_pdfs(folder)
        if not pdfs:
            write(f"No PDF files found in:\n{folder}\n\n[P] Choose another folder\n[Q] Quit\n")
            while True:
                key = read_key()
                if key in ("q", "esc"):
                    return ("quit", folder, [])
                if key == "p":
                    break
            write("Folder path: ")
            typed = (read_line() or "").strip().strip('"')
            candidate = (folder / typed).resolve() if typed else folder
            if candidate.is_dir():
                folder = candidate
            else:
                write(f"Not a folder: {candidate}\n\n")
            continue
        menu = Menu(f"Current folder:\n{folder}\n\nSelect PDF files:",
                    [p.name for p in pdfs], selected=range(len(pdfs)) if len(pdfs) == 1 else ())
        status, picked = menu.run(read_key, write)
        if status == "quit":
            return ("quit", folder, [])
        return ("ok", folder, [pdfs[i] for i in picked])


def choose_formats(count: int, read_key, write, allow_back: bool) -> tuple[str, list[str]]:
    keys = list(FORMAT_LABELS)
    menu = Menu(f"Selected: {count} PDF{'s' if count != 1 else ''}\n\nSelect output formats:",
                [FORMAT_LABELS[k] for k in keys], selected=[0], confirm="Convert", allow_back=allow_back)
    status, picked = menu.run(read_key, write)
    return (status, [keys[i] for i in picked] if picked else [])


def session(cwd: Path, target: Path | None, out_dir: Path | None, options: list[str],
            read_key=read_key, write=None, read_line=None) -> int:
    """The whole interactive flow. Returns an exit code."""
    from . import __version__
    from .cli import convert

    write = write or _write
    read_line = read_line or sys.stdin.readline
    write(f"PDFStruct {__version__}\n\n")
    pdfs: list[Path] = []
    folder = cwd
    if target is not None and target.is_file():
        pdfs = [target]
        folder = target.parent
    elif target is not None:
        folder = target

    while True:
        if not (target is not None and target.is_file()):
            status, folder, pdfs = choose_pdfs(folder, read_key, write, read_line)
            if status == "quit":
                write("Cancelled.\n")
                return 1
        status, formats = choose_formats(len(pdfs), read_key, write,
                                         allow_back=not (target is not None and target.is_file()))
        if status == "back":
            write("\n")
            continue
        if status == "quit":
            write("Cancelled.\n")
            return 1
        break

    write("\nProcessing...\n\n")
    failures = convert(pdfs, formats, out_dir or folder / "output", options, write)
    write(f"\n{'Done.' if not failures else f'{failures} export(s) failed.'}\n\nOutput:\n"
          f"{out_dir or folder / 'output'}\n")
    return 1 if failures else 0
