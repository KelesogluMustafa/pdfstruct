"""Claude for Windows bundle (.mcpb): a launcher for the versioned runtime, nothing bundled."""
import importlib.util
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

import pdfstruct
from conftest import TOOL_DIR

BUNDLE = TOOL_DIR / "integrations" / "claude-desktop"
VERSION = pdfstruct.__version__


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOL_DIR / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_points_at_the_versioned_runtime():
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "0.3" and manifest["name"] == "pdfstruct"
    assert manifest["version"] == VERSION  # bumped together with the package
    server = manifest["server"]
    assert server["type"] == "binary" and server["entry_point"] == "server/pdfstruct-mcp.cmd"
    config = server["mcp_config"]
    assert config["command"] == ("${HOME}${/}.local${/}pdfstruct${/}v" + VERSION
                                 + "${/}Scripts${/}pdfstruct-mcp.exe")
    assert config["args"] == [] and config["env"] == {}
    assert "user_config" not in manifest                      # nothing to configure
    assert manifest["compatibility"] == {"platforms": ["win32"]}
    assert sorted(tool["name"] for tool in manifest["tools"]) == [
        "convert", "inspect", "read_excerpt", "search", "supported_formats"]
    assert f"v{VERSION}" in manifest["long_description"]


def test_bundle_is_a_launcher_only():
    files = sorted(p.relative_to(BUNDLE).as_posix() for p in BUNDLE.rglob("*") if p.is_file())
    assert files == ["manifest.json", "server/pdfstruct-mcp.cmd"]  # no Node, no engine, no models
    launcher = (BUNDLE / "server" / "pdfstruct-mcp.cmd").read_text(encoding="ascii")
    assert f"\\.local\\pdfstruct\\v{VERSION}\\Scripts\\pdfstruct-mcp.exe" in launcher
    assert "%USERPROFILE%" in launcher and "node" not in launcher.lower()
    text = json.dumps(json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8")))
    for forbidden in ("node", "Projects", ".venv", "C:\\\\Users"):
        assert forbidden not in text, forbidden  # no dev checkout, no machine-specific path


def test_build_writes_mcpb_skill_snippet_and_guide(tmp_path, monkeypatch):
    builder = load("build_claude_windows")
    monkeypatch.setattr(builder.build_skill_zip, "TARGET", tmp_path / "skill-build" / "pdfstruct-skill.zip")
    monkeypatch.setattr("sys.argv", ["build_claude_windows.py", "--out", str(tmp_path / "out")])
    assert builder.main() == 0
    out = tmp_path / "out"
    mcpb = out / "mcp" / f"pdfstruct-{VERSION}.mcpb"
    with zipfile.ZipFile(mcpb) as archive:
        assert sorted(archive.namelist()) == ["manifest.json", "server/pdfstruct-mcp.cmd"]
        assert json.loads(archive.read("manifest.json"))["server"]["type"] == "binary"
    assert mcpb.stat().st_size < 10_000
    snippet = json.loads((out / "mcp" / "claude_desktop_config.snippet.json").read_text(encoding="utf-8"))
    command = Path(snippet["mcpServers"]["pdfstruct"]["command"])
    assert command.parts[-4:] == ("pdfstruct", f"v{VERSION}", "Scripts", "pdfstruct-mcp.exe")
    with zipfile.ZipFile(out / "skill" / "pdfstruct-skill.zip") as archive:
        assert archive.namelist() == ["pdfstruct/SKILL.md"]
    guide = (out / "README-INSTALL.txt").read_text(encoding="utf-8")
    assert f"pdfstruct-{VERSION}.mcpb" in guide and "Install Extension" in guide and "Customize -> Skills" in guide
    first = mcpb.read_bytes()
    assert builder.build_mcpb(tmp_path / "again.mcpb").read_bytes() == first  # reproducible


@pytest.mark.skipif(os.name != "nt", reason="the installer is for Windows")
def test_installer_dry_run_targets_the_versioned_folder(tmp_path):
    wheel = tmp_path / f"pdfstruct-{VERSION}-py3-none-any.whl"
    wheel.write_bytes(b"not a real wheel; the dry run only reads the name")
    script = TOOL_DIR / "scripts" / "install-windows.ps1"

    def run(*args):
        return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                               str(script), *args], capture_output=True, text=True, timeout=120)

    done = run("-Wheel", str(wheel), "-Root", str(tmp_path / "root"), "-DryRun")
    assert done.returncode == 0, done.stdout + done.stderr
    assert f"PDFStruct {VERSION}" in done.stdout and "DRY RUN" in done.stdout
    assert str(tmp_path / "root" / f"v{VERSION}") in done.stdout
    assert not (tmp_path / "root").exists()  # a dry run creates nothing
    default = run("-Wheel", str(wheel), "-DryRun")
    assert str(Path.home() / ".local" / "pdfstruct" / f"v{VERSION}") in default.stdout
    bad = tmp_path / "pdfstruct-dev.whl"
    bad.write_bytes(b"x")
    refused = run("-Wheel", str(bad), "-DryRun")
    assert refused.returncode == 1 and "not a PDFStruct release wheel" in refused.stdout
    text = script.read_text(encoding="utf-8")
    assert " -e " not in text and "--editable" not in text  # never linked to a source folder
