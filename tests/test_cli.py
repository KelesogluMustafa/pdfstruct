"""CLI UX: what pdfjson / pdfhtml / ... process and where they write."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from pdfstruct import cli as pdf_cli
from pdfstruct import extract as pdf_to_json
from conftest import TOOL_DIR, make_text_pdf


def run(cwd: Path, *argv) -> int:
    command, *rest = (str(a) for a in argv)
    return pdf_cli.run(command, rest, cwd=cwd)


def raws(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.glob("*.raw.json"))


# 1 + 8: one file, output folder created next to it
def test_single_file(tmp_path, capsys):
    (tmp_path / "docs").mkdir()
    make_text_pdf(tmp_path / "docs" / "belge.pdf")
    make_text_pdf(tmp_path / "docs" / "other.pdf")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert run(elsewhere, "json", tmp_path / "docs" / "belge.pdf") == 0
    assert raws(tmp_path / "docs" / "output") == ["belge.raw.json"]  # only that file
    assert not (elsewhere / "output").exists()
    printed = capsys.readouterr().out
    assert "FILES FOUND: 1" in printed and "PROCESSED: 1" in printed and "FAILED: 0" in printed

    assert run(tmp_path / "docs", "json", "other.pdf") == 0  # relative to the current folder
    assert raws(tmp_path / "docs" / "output") == ["belge.raw.json", "other.raw.json"]


# 2: spaces, Turkish characters and parentheses in the path
def test_path_with_spaces_unicode_parentheses(tmp_path):
    folder = tmp_path / "PDF Dosyaları (yeni)"
    folder.mkdir()
    pdf = make_text_pdf(folder / "maaş bordrosu (1).pdf")
    assert run(tmp_path, "json", pdf) == 0
    raw = json.loads((folder / "output" / "maaş bordrosu (1).raw.json").read_text(encoding="utf-8"))
    assert raw["source"]["file_name"] == "maaş bordrosu (1).pdf"
    assert run(tmp_path, "txt", pdf) == 0
    assert (folder / "output" / "maaş bordrosu (1).txt").is_file()


# 3: folder argument, subfolders are not entered
def test_folder_argument(tmp_path, capsys):
    folder = tmp_path / "PDF Dosyaları"
    (folder / "sub").mkdir(parents=True)
    for name in ("a.pdf", "b.PDF", "sub/deep.pdf"):
        make_text_pdf(folder / name)
    assert run(tmp_path, "json", folder) == 0
    assert raws(folder / "output") == ["a.raw.json", "b.raw.json"]
    assert "FILES FOUND: 2" in capsys.readouterr().out
    assert run(tmp_path, "json", str(folder) + '"') == 0  # cmd's "C:\dir\" quirk


# 4 + 5: no argument -> every PDF in the current folder
@pytest.mark.parametrize("names", [["only.pdf"], ["a.pdf", "b.pdf", "c.pdf"]])
def test_no_argument_current_directory(tmp_path, capsys, names):
    for name in names:
        make_text_pdf(tmp_path / name)
    assert run(tmp_path, "json") == 0
    assert raws(tmp_path / "output") == [n[:-4] + ".raw.json" for n in names]
    assert f"FILES FOUND: {len(names)}" in capsys.readouterr().out


# 6 + 11: old layout, .\pdf -> .\output (json and a format command)
def test_old_pdf_folder_mode(tmp_path):
    (tmp_path / "pdf").mkdir()
    make_text_pdf(tmp_path / "pdf" / "doc.pdf")
    assert run(tmp_path, "json") == 0
    assert raws(tmp_path / "output") == ["doc.raw.json"]
    assert not (tmp_path / "pdf" / "output").exists()
    assert run(tmp_path, "md") == 0
    assert (tmp_path / "output" / "doc.md").is_file()


def test_current_directory_wins_over_pdf_folder(tmp_path):
    (tmp_path / "pdf").mkdir()
    make_text_pdf(tmp_path / "pdf" / "old.pdf")
    make_text_pdf(tmp_path / "here.pdf")
    assert run(tmp_path, "json") == 0
    assert raws(tmp_path / "output") == ["here.raw.json"]


# 7: nothing found -> clear message with usage, nothing created
def test_no_pdf_found(tmp_path, capsys):
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    assert run(tmp_path, "json") == 2
    printed = capsys.readouterr().out
    assert "PDF bulunamadı." in printed and "pdfjson belge.pdf" in printed
    assert not (tmp_path / "output").exists()
    assert run(tmp_path, "json", "missing.pdf") == 2
    (tmp_path / "notes.xyz").write_text("x", encoding="utf-8")
    assert run(tmp_path, "json", "notes.xyz") == 2  # unsupported type
    assert run(tmp_path, "html") == 2
    assert "pdfhtml belge.pdf" in capsys.readouterr().out


# 9: one broken PDF does not stop the batch
def test_failed_file_does_not_stop_batch(tmp_path, capsys):
    make_text_pdf(tmp_path / "a.pdf")
    (tmp_path / "bozuk.pdf").write_bytes(b"%PDF-1.4\nnot a pdf\n" + bytes(range(256)))
    make_text_pdf(tmp_path / "c.pdf")
    assert run(tmp_path, "json") == 1
    assert raws(tmp_path / "output") == ["a.raw.json", "c.raw.json"]
    printed = capsys.readouterr().out
    assert "FILES FOUND: 3" in printed and "PROCESSED: 2" in printed and "FAILED: 1" in printed
    assert "FAILED FILES:\n- bozuk.pdf" in printed
    assert len(printed) < 600


# 10: second run re-extracts nothing
def test_second_run_is_idempotent(tmp_path, capsys):
    make_text_pdf(tmp_path / "a.pdf")
    make_text_pdf(tmp_path / "b.pdf")
    assert run(tmp_path, "json") == 0
    mtimes = {p.name: p.stat().st_mtime_ns for p in (tmp_path / "output").glob("*.raw.json")}
    capsys.readouterr()
    assert run(tmp_path, "json") == 0
    printed = capsys.readouterr().out
    assert "PROCESSED: 0" in printed and "SKIPPED: 2" in printed
    assert {p.name: p.stat().st_mtime_ns for p in (tmp_path / "output").glob("*.raw.json")} == mtimes
    assert run(tmp_path, "json", "--overwrite") == 0
    assert "PROCESSED: 2" in capsys.readouterr().out


# 12: explicit --output wins in every mode
def test_output_override(tmp_path):
    make_text_pdf(tmp_path / "a.pdf")
    target = tmp_path / "custom out"
    assert run(tmp_path, "json", "--output", target) == 0
    assert run(tmp_path, "json", "a.pdf", "--output", "rel-out") == 0
    assert run(tmp_path, "csv", tmp_path, "--output", target) == 0
    assert raws(target) == ["a.raw.json"] and (target / "a.csv").is_file()
    assert raws(tmp_path / "rel-out") == ["a.raw.json"]
    assert not (tmp_path / "output").exists()


def test_options_pass_through(tmp_path, capsys):
    make_text_pdf(tmp_path / "a.pdf")
    parser = TOOL_DIR / "examples" / "example_parser.py"
    assert run(tmp_path, "json", "--native-only", "--parser", parser) == 0
    assert (tmp_path / "output" / "a.parsed.json").is_file()
    assert "PARSED: 1" in capsys.readouterr().out
    run_summary = json.loads((tmp_path / "output" / "_run_summary.json").read_text(encoding="utf-8"))
    assert run_summary["mode"] == "native-only"


def test_format_command_shares_input_rules(tmp_path, monkeypatch, capsys):
    make_text_pdf(tmp_path / "a.pdf")
    make_text_pdf(tmp_path / "b.pdf")
    assert run(tmp_path, "html", "a.pdf") == 0  # extracts just that file
    assert raws(tmp_path / "output") == ["a.raw.json"] and (tmp_path / "output" / "a.html").is_file()
    assert run(tmp_path, "txt") == 0  # all PDFs here; a.raw.json reused
    assert "RAW_REUSED: 1" in capsys.readouterr().out
    assert (tmp_path / "output" / "b.txt").is_file()

    # PDFs gone: format commands still work from output\*.raw.json
    (tmp_path / "a.pdf").unlink()
    (tmp_path / "b.pdf").unlink()
    monkeypatch.setattr(pdf_to_json, "process_pdf", None)
    assert run(tmp_path, "jsonl") == 0
    assert (tmp_path / "output" / "b.jsonl").is_file()


@pytest.mark.skipif(os.name != "nt" or not (TOOL_DIR / ".venv" / "Scripts" / "python.exe").is_file(),
                    reason="the .cmd wrappers need the repo venv on Windows")
def test_cmd_wrappers_with_awkward_path(tmp_path):
    folder = tmp_path / "Belgeler (2026) ğüş"
    folder.mkdir()
    pdf = make_text_pdf(folder / "maaş bordrosu (1).pdf")
    make_text_pdf(folder / "b.pdf")

    def cmd(name, *args, cwd):
        return subprocess.run([str(TOOL_DIR / f"{name}.cmd"), *map(str, args)], cwd=cwd,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")

    one = cmd("pdfjson", pdf, cwd=tmp_path)
    assert one.returncode == 0, one.stdout + one.stderr
    assert raws(folder / "output") == ["maaş bordrosu (1).raw.json"]
    everything = cmd("pdfjson", cwd=folder)
    assert everything.returncode == 0 and "FILES FOUND: 2" in everything.stdout
    assert "SKIPPED: 1" in everything.stdout
    sheet = cmd("pdfxlsx", folder, cwd=tmp_path)
    assert sheet.returncode == 0 and "EXTRACTED: 0" in sheet.stdout
    assert (folder / "output" / "maaş bordrosu (1).xlsx").is_file()
    assert cmd("pdfjson", cwd=tmp_path).returncode == 2
