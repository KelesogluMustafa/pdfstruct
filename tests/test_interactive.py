"""Interactive `pdfstruct`: menus driven by scripted keys, conversion through the core."""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import make_text_pdf
from pdfstruct import cli, extract, interactive

FORMAT_KEYS = list(interactive.FORMAT_LABELS)  # json html txt md csv xlsx docx jsonl sqlite


class Keys:
    """Scripted key presses; the test fails loudly if the UI asks for more than planned."""

    def __init__(self, *keys):
        self.keys = list(keys)
        self.lines = []

    def __call__(self):
        if not self.keys:
            raise AssertionError("UI asked for a key but the script is exhausted")
        return self.keys.pop(0)

    def read_line(self):
        return self.lines.pop(0) if self.lines else ""


def drive(cwd, *keys, argv=(), lines=()):
    keys = Keys(*keys)
    keys.lines = list(lines)
    out = io.StringIO()
    code = cli.main(list(argv), cwd=cwd, read_key=keys, write=out.write, read_line=keys.read_line)
    return code, out.getvalue(), keys


def outputs(folder: Path) -> set[str]:
    return {p.name for p in (folder / "output").iterdir() if not p.name.startswith("_")
            and not p.name.endswith(".summary.json")}


# ---------------------------------------------------------------- Menu unit tests

def test_menu_navigation_and_selection():
    menu = interactive.Menu("T", ["a", "b", "c"])
    assert menu.handle("enter") is None  # nothing selected yet -> stays
    menu.handle("down"); menu.handle("space")
    assert menu.selected == {1}
    menu.handle("up"); menu.handle("up")  # wraps to the last item
    assert menu.cursor == 2
    menu.handle("space")
    assert menu.handle("enter") == ("ok", [1, 2])
    menu.handle("a")
    assert menu.selected == {0, 1, 2}
    menu.handle("a")
    assert menu.selected == set()
    assert menu.handle("q") == ("quit", None)
    assert menu.handle("b") is None  # back only where allowed
    assert interactive.Menu("T", ["a"], allow_back=True).handle("b") == ("back", None)


def test_menu_render_and_redraw():
    menu = interactive.Menu("Select:", ["one.pdf", "two.pdf"], selected=[1], allow_back=True)
    text = menu.render()
    assert "> [ ] one.pdf" in text and "  [x] two.pdf" in text
    for hint in ("SPACE", "ENTER   Continue", "B       Back", "Q       Quit"):
        assert hint in text
    out = io.StringIO()
    menu.draw(out.write)
    menu.draw(out.write)
    assert "\x1b[" in out.getvalue()  # second draw moves the cursor up instead of appending


# ---------------------------------------------------------------- full flows

def test_no_argument_lists_pdfs_and_converts_one(tmp_path):
    for name in ("invoice.pdf", "report.pdf", "contract.pdf"):
        make_text_pdf(tmp_path / name)
    (tmp_path / "sub").mkdir()
    make_text_pdf(tmp_path / "sub" / "deep.pdf")
    # pick the 2nd PDF, then formats: JSON (preselected) + XLSX
    code, text, keys = drive(tmp_path, "down", "space", "enter",
                             "down", "down", "down", "down", "down", "space", "enter")
    assert code == 0 and not keys.keys
    assert "contract.pdf" in text and "invoice.pdf" in text and "deep.pdf" not in text
    assert "Selected: 1 PDF" in text and "✓ JSON" in text and "✓ XLSX" in text and "Done." in text
    assert outputs(tmp_path) == {"invoice.raw.json", "invoice.xlsx"}  # sorted: contract, invoice, report


def test_multiple_pdfs_and_select_all_formats_extract_once(tmp_path, monkeypatch):
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        make_text_pdf(tmp_path / name)
    calls = []
    real = extract.process_pdf

    def counting(*args, **kwargs):
        calls.append(args[0].name)
        return real(*args, **kwargs)
    monkeypatch.setattr(extract, "process_pdf", counting)
    # select all PDFs, then all formats
    code, text, _ = drive(tmp_path, "a", "enter", "a", "enter")
    assert code == 0
    assert sorted(calls) == ["a.pdf", "b.pdf", "c.pdf"]  # once per PDF, not per format
    assert text.count("✓") == 3 * len(FORMAT_KEYS)
    assert len(outputs(tmp_path)) == 3 * len(FORMAT_KEYS)
    assert "Selected: 3 PDFs" in text


def test_single_pdf_is_preselected_and_json_only(tmp_path):
    make_text_pdf(tmp_path / "only.pdf")
    code, text, _ = drive(tmp_path, "enter", "enter")
    assert code == 0 and outputs(tmp_path) == {"only.raw.json"}


def test_file_argument_skips_file_menu(tmp_path):
    make_text_pdf(tmp_path / "doc.pdf")
    make_text_pdf(tmp_path / "other.pdf")
    # straight to formats: deselect JSON, choose TXT and Markdown
    code, text, _ = drive(tmp_path, "space", "down", "down", "space", "down", "space", "enter",
                          argv=["doc.pdf"])
    assert code == 0
    assert "Select PDF files" not in text and "B       Back" not in text
    assert outputs(tmp_path) == {"doc.raw.json", "doc.txt", "doc.md"}


def test_directory_argument_opens_file_menu(tmp_path):
    folder = tmp_path / "Belgeler"
    folder.mkdir()
    make_text_pdf(folder / "x.pdf")
    make_text_pdf(folder / "y.pdf")
    code, text, _ = drive(tmp_path, "down", "space", "enter", "enter", argv=[str(folder)])
    assert code == 0 and "Select PDF files" in text
    assert outputs(folder) == {"y.raw.json"}
    assert not (tmp_path / "output").exists()


def test_back_and_quit(tmp_path):
    make_text_pdf(tmp_path / "a.pdf")
    make_text_pdf(tmp_path / "b.pdf")
    # formats menu -> back -> file menu again -> quit
    code, text, keys = drive(tmp_path, "space", "enter", "b", "q")
    assert code == 1 and "Cancelled." in text and not keys.keys
    assert text.rindex("Select PDF files") > text.index("Select output formats")  # back worked
    assert not (tmp_path / "output").exists()
    code, text, _ = drive(tmp_path, "esc")
    assert code == 1 and "Cancelled." in text


def test_no_pdfs_offers_other_folder_or_quit(tmp_path):
    (tmp_path / "docs").mkdir()
    make_text_pdf(tmp_path / "docs" / "d.pdf")
    code, text, _ = drive(tmp_path, "q")
    assert code == 1 and "No PDF files found in:" in text and str(tmp_path) in text
    code, text, _ = drive(tmp_path, "p", "p", "enter", "enter", lines=["nope", "docs"])
    assert code == 0 and "Not a folder" in text
    assert outputs(tmp_path / "docs") == {"d.raw.json"}


def test_output_override_in_interactive_mode(tmp_path):
    make_text_pdf(tmp_path / "a.pdf")
    target = tmp_path / "custom"
    code, text, _ = drive(tmp_path, "enter", "enter", argv=["--output", str(target)])
    assert code == 0 and (target / "a.raw.json").is_file() and str(target) in text


# ---------------------------------------------------------------- non-interactive paths

def test_explicit_format_bypasses_menus(tmp_path):
    make_text_pdf(tmp_path / "a.pdf")
    keys = Keys()  # any key request would fail
    assert cli.main(["a.pdf", "--format", "json,xlsx", "--format", "docx"], cwd=tmp_path,
                    read_key=keys, write=lambda t: None) == 0
    assert outputs(tmp_path) == {"a.raw.json", "a.xlsx", "a.docx"}
    assert cli.main(["--format", "txt", "a.pdf"], cwd=tmp_path, read_key=keys,
                    write=lambda t: None) == 0


def test_multi_format_folder_is_n_times_m(tmp_path, capsys, monkeypatch):
    for name in ("a.pdf", "b.pdf"):
        make_text_pdf(tmp_path / name)
    calls = []
    real = extract.process_pdf
    monkeypatch.setattr(extract, "process_pdf",
                        lambda *a, **k: calls.append(a[0].name) or real(*a, **k))
    assert cli.main(["--format", "json,html,csv"], cwd=tmp_path) == 0
    assert len(calls) == 2 and len(outputs(tmp_path)) == 6
    printed = capsys.readouterr().out
    assert printed.count("✓") == 6 and "OUTPUT:" in printed


def test_aliases_never_prompt(tmp_path):
    make_text_pdf(tmp_path / "a.pdf")
    make_text_pdf(tmp_path / "b.pdf")
    assert cli.run("json", [], cwd=tmp_path) == 0  # no argument: all PDFs, no menu
    assert cli.run("txt", [], cwd=tmp_path) == 0
    assert outputs(tmp_path) == {"a.raw.json", "b.raw.json", "a.txt", "b.txt"}


def test_non_tty_does_not_hang(tmp_path):
    make_text_pdf(tmp_path / "a.pdf")
    result = subprocess.run([sys.executable, "-m", "pdfstruct"], cwd=tmp_path, input="",
                            capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert result.returncode == 2
    assert "--format" in result.stdout and "pdfstruct belge.pdf" in result.stdout
    assert not (tmp_path / "output").exists()
    result = subprocess.run([sys.executable, "-m", "pdfstruct", "a.pdf"], cwd=tmp_path,
                            input="", capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert result.returncode == 2


def test_missing_path_argument(tmp_path, capsys):
    assert cli.main(["nope.pdf"], cwd=tmp_path) == 2
    assert "bulunamadı" in capsys.readouterr().out
