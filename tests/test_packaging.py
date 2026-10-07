"""Packaging: import name, single version source, console entry points."""
import os
import subprocess
import sys
import sysconfig
from importlib import metadata
from pathlib import Path

import pytest

import pdfstruct
from conftest import make_text_pdf
from pdfstruct import cli, export, extract

ALIASES = ["pdfjson", "pdfhtml", "pdftxt", "pdfmd", "pdfcsv", "pdfxlsx", "pdfdocx",
           "pdfjsonl", "pdfsqlite"]
SCRIPTS_DIR = Path(sysconfig.get_path("scripts"))  # venv: next to python; system: <prefix>/Scripts or bin


def test_import_and_single_version():
    assert pdfstruct.__version__ == "0.1.0"
    assert metadata.version("pdfstruct") == pdfstruct.__version__  # package is installed
    assert extract.TOOL_VERSION == pdfstruct.__version__
    assert extract.TOOL_NAME == "pdfstruct"
    assert (Path(extract.__file__).parent / "ocr.py").is_file()


def test_console_entry_points_declared():
    scripts = {ep.name: ep.value for ep in metadata.distribution("pdfstruct").entry_points
               if ep.group == "console_scripts"}
    assert scripts.pop("pdfstruct") == "pdfstruct.cli:main"
    assert scripts.pop("pdfstruct-mcp") == "pdfstruct.mcp_server:main"
    assert scripts == {name: f"pdfstruct.cli:{name}" for name in ALIASES}
    assert [f"pdf{c}" for c in cli.ALIAS_COMMANDS] == ALIASES  # no alias for --format pdf
    for name in ALIASES:
        assert callable(getattr(cli, name))


@pytest.mark.parametrize("name", ["pdfstruct", *ALIASES])
def test_installed_scripts_run(name):
    # not shutil.which(): on Windows it would also look in the cwd and find the repo's .cmd
    script = SCRIPTS_DIR / (name + (".exe" if os.name == "nt" else ""))
    assert script.is_file(), f"{name} not installed next to {sys.executable}"
    result = subprocess.run([script, "--help"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    assert result.returncode == 0 and f"{name} belge.pdf" in result.stdout
    version = subprocess.run([script, "--version"], capture_output=True, text=True)
    assert version.stdout.strip() == f"pdfstruct {pdfstruct.__version__}"


def test_pdfstruct_main_cli(tmp_path, capsys):
    make_text_pdf(tmp_path / "belge.pdf")
    assert cli.main(["belge.pdf", "--format", "json"], cwd=tmp_path) == 0
    assert (tmp_path / "output" / "belge.raw.json").is_file()
    assert "FILES FOUND: 1" in capsys.readouterr().out
    assert cli.main(["--format", "xlsx", "belge.pdf"], cwd=tmp_path) == 0
    assert cli.main(["belge.pdf", "--format", "md"], cwd=tmp_path) == 0
    assert "RAW_REUSED: 1" in capsys.readouterr().out
    for suffix in (".xlsx", ".md"):
        assert (tmp_path / "output" / f"belge{suffix}").is_file()
    assert cli.main(["--format", "txt"], cwd=tmp_path / "output") == 2  # no PDF there
    assert "pdfstruct belge.pdf" in capsys.readouterr().out
    assert set(cli.COMMANDS) == {"json", *export.FORMATS}


def test_python_dash_m(tmp_path):
    make_text_pdf(tmp_path / "a.pdf")
    result = subprocess.run([sys.executable, "-m", "pdfstruct", "--format", "txt"],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0 and "FORMAT: txt" in result.stdout
    assert (tmp_path / "output" / "a.txt").is_file()
