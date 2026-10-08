"""Claude integration files: one skill source, the plugin, the .mcpb launcher, the release assets."""
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path, PureWindowsPath

import pytest

import pdfstruct
from conftest import TOOL_DIR
from pdfstruct import mcp_server

VERSION = pdfstruct.__version__
PLUGIN = TOOL_DIR / "plugin"
SKILL = PLUGIN / "skills" / "pdfstruct" / "SKILL.md"
BUNDLE = TOOL_DIR / "integrations" / "claude-desktop"
TOOLS = ["convert", "create_document", "inspect", "read_excerpt", "search", "supported_formats"]
STABLE_EXE = ("current", "Scripts", "pdfstruct-mcp.exe")


def assets():
    spec = importlib.util.spec_from_file_location("build_release_assets",
                                                  TOOL_DIR / "scripts" / "build_release_assets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8").replace("\r\n", "\n")


# ---------------------------------------------------------------- one skill source

def test_there_is_exactly_one_skill_source():
    found = [p.relative_to(TOOL_DIR).as_posix() for p in TOOL_DIR.rglob("SKILL.md")
             if not {".venv", "dist", "node_modules"} & set(p.relative_to(TOOL_DIR).parts)]
    assert found == ["plugin/skills/pdfstruct/SKILL.md"]
    assert not (TOOL_DIR / "skills").exists()
    assert sorted(p.name for p in SKILL.parent.iterdir()) == ["SKILL.md"]  # instructions only


def test_skill_is_short_and_teaches_the_token_saving_workflow():
    text = skill_text()
    assets().validate_skill(text)
    assert len(text) < 5200, "the skill is loaded into context: keep it short"
    description = text.split("description:")[1].split("\n---")[0].strip()
    assert len(description) <= 1024 and "MCP tools" in description
    for name in TOOLS:  # the real tool names of the server, nothing else
        assert f"`{name}" in text, name
    for rule in ("inspect(path)", "convert(paths, formats)", "at most 2000 characters",
                 "Do not try a command line there", "PDFStruct is not connected",
                 "only uploaded into the chat", "untrusted", "do not open the\n   outputs",
                 "Never load a whole document", "retry once", "already_pdf", "not_converted",
                 "create_document(name, content, formats)", "already a file\ngoes through `convert`",
                 "{{PROJECT_NAME}}", "Do not\n  write a temporary TXT or Markdown file",
                 "`overwrite: true` only when the user asked", "Do not repeat the content",
                 "500,000 characters", "content_too_large", "ask only when the place matters"):
        assert rule in text, rule
    assert text.index("inspect(path)") < text.index("convert(paths, formats)") < text.index("read_excerpt(path")
    for claude_code_only in ("Read tool", "Bash", "claude mcp"):
        assert claude_code_only not in text


# ---------------------------------------------------------------- plugin

def test_plugin_manifest_and_mcp_registration():
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "pdfstruct" and manifest["version"] == VERSION
    assert manifest["mcpServers"] == "./.mcp.json"
    servers = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert list(servers) == ["pdfstruct"]  # the existing server, registered once
    command = servers["pdfstruct"]["command"]
    assert command == "${USERPROFILE}\\.local\\pdfstruct\\current\\Scripts\\pdfstruct-mcp.exe"
    assert servers["pdfstruct"]["args"] == []
    files = sorted(p.relative_to(PLUGIN).as_posix() for p in PLUGIN.rglob("*") if p.is_file())
    assert files == [".claude-plugin/plugin.json", ".mcp.json", "README.md", "skills/pdfstruct/SKILL.md"]
    readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
    assert ".mcpb" in readme and "install-windows.cmd" in readme and "twice" in readme


def test_nothing_shipped_to_claude_is_tied_to_a_machine_or_checkout():
    shipped = [*PLUGIN.rglob("*"), *BUNDLE.rglob("*")]
    for path in (p for p in shipped if p.is_file()):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("musta", "Projects", ".venv", "C:\\Users", "C:/Users", "node "):
            assert forbidden not in text, (path.name, forbidden)
        assert not re.search(r"pdfstruct[\\/${}]+v\d+\.\d+\.\d+", text), f"{path.name} names a version folder"


@pytest.mark.skipif(shutil.which("claude") is None, reason="Claude Code is not installed")
def test_claude_code_validates_the_plugin():
    done = subprocess.run([shutil.which("claude"), "plugin", "validate", str(PLUGIN), "--strict"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr


# ---------------------------------------------------------------- .mcpb

def test_mcpb_manifest_starts_the_active_runtime():
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "0.3" and manifest["version"] == VERSION
    server = manifest["server"]
    assert server["type"] == "binary" and server["entry_point"] == "server/pdfstruct-mcp.cmd"
    assert server["mcp_config"] == {
        "command": "${HOME}${/}.local${/}pdfstruct${/}current${/}Scripts${/}pdfstruct-mcp.exe",
        "args": [], "env": {}}
    assert server["mcp_config"]["command"].endswith(".exe")  # never a .cmd as the binary command
    assert "user_config" not in manifest and manifest["compatibility"] == {"platforms": ["win32"]}
    assert sorted(tool["name"] for tool in manifest["tools"]) == TOOLS
    files = sorted(p.relative_to(BUNDLE).as_posix() for p in BUNDLE.rglob("*") if p.is_file())
    assert files == ["manifest.json", "server/pdfstruct-mcp.cmd"]  # no Node, no engine, no models
    launcher = (BUNDLE / "server" / "pdfstruct-mcp.cmd").read_text(encoding="ascii")
    assert "%USERPROFILE%\\.local\\pdfstruct\\current\\Scripts\\pdfstruct-mcp.exe" in launcher


def test_plugin_and_extension_start_the_same_server():
    plugin = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["pdfstruct"]["command"]
    extension = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))["server"]["mcp_config"]["command"]
    home = "C:\\Users\\someone"
    resolved_plugin = PureWindowsPath(plugin.replace("${USERPROFILE}", home))
    resolved_extension = PureWindowsPath(extension.replace("${HOME}", home).replace("${/}", "\\"))
    assert resolved_plugin == resolved_extension
    assert resolved_plugin.parts[-3:] == STABLE_EXE
    # and the names both advertise are the names the server really has
    assert sorted(mcp_server.supported_formats()["outputs"])  # server module importable
    server = mcp_server.build_server()
    import asyncio
    assert sorted(tool.name for tool in asyncio.run(server.list_tools())) == TOOLS


# ---------------------------------------------------------------- release assets

def test_release_assets_are_complete_reproducible_and_small(tmp_path):
    builder = assets()
    wheel = tmp_path / f"pdfstruct-{VERSION}-py3-none-any.whl"
    wheel.write_bytes(b"stand-in for the wheel; building the real one is the job of the local CI")

    def build(folder: Path) -> dict:
        import sys
        argv, sys.argv = sys.argv, ["build_release_assets.py", "--out", str(folder), "--wheel", str(wheel)]
        try:
            assert builder.main() == 0
        finally:
            sys.argv = argv
        return {p.name: p.read_bytes() for p in folder.iterdir()}

    first = build(tmp_path / "a")
    assert sorted(first) == sorted([
        f"PDFStruct-Windows-Setup-{VERSION}.zip", f"pdfstruct-{VERSION}.mcpb", "pdfstruct-plugin.zip",
        "pdfstruct-skill.zip", wheel.name, "SHA256SUMS.txt", "README-INSTALL.txt"])
    assert build(tmp_path / "b") == first  # same input, same bytes

    out = tmp_path / "a"
    listed = dict(reversed(line.split(" *")) for line in
                  (out / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines())
    for name, digest in listed.items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest, name
    assert set(listed) == set(first) - {"SHA256SUMS.txt", "README-INSTALL.txt"}

    source = skill_text().encode("utf-8")
    with zipfile.ZipFile(out / "pdfstruct-skill.zip") as archive:
        assert archive.namelist() == ["pdfstruct/SKILL.md"]
        assert archive.read("pdfstruct/SKILL.md") == source
    with zipfile.ZipFile(out / "pdfstruct-plugin.zip") as archive:  # plugin content at the root
        assert sorted(archive.namelist()) == [".claude-plugin/plugin.json", ".mcp.json", "README.md",
                                              "skills/pdfstruct/SKILL.md"]
        assert archive.read("skills/pdfstruct/SKILL.md") == source  # the same skill, byte for byte
    with zipfile.ZipFile(out / f"pdfstruct-{VERSION}.mcpb") as archive:
        assert sorted(archive.namelist()) == ["manifest.json", "server/pdfstruct-mcp.cmd"]
    top = f"PDFStruct-Windows-Setup-{VERSION}/"
    with zipfile.ZipFile(out / f"PDFStruct-Windows-Setup-{VERSION}.zip") as archive:
        names = sorted(archive.namelist())
        assert names == sorted(top + n for n in [
            "install-windows.cmd", "update-windows.cmd", "scripts/install-windows.ps1",
            "scripts/update-windows.ps1", "scripts/runtime-common.ps1", "scripts/verify_runtime.py",
            "LICENSE", wheel.name, "SHA256SUMS.txt", "README-INSTALL.txt"])
        inner = archive.read(top + "SHA256SUMS.txt").decode()
        assert inner == f"{hashlib.sha256(wheel.read_bytes()).hexdigest()} *{wheel.name}\n"
        assert b"\r\n" in archive.read(top + "install-windows.cmd")
        guide = archive.read(top + "README-INSTALL.txt").decode("utf-8")
    for step in ("1. PDFStruct itself", "2. Claude Desktop chat", "3. Claude Code / Cowork",
                 "Do not also upload pdfstruct-skill.zip", "update-windows.cmd -Rollback"):
        assert step in guide, step
    for name in ("pdfstruct-plugin.zip", "pdfstruct-skill.zip", f"pdfstruct-{VERSION}.mcpb"):
        assert len(first[name]) < 20_000, f"{name} must not carry a runtime"


def test_building_release_files_never_empties_the_release_folder(tmp_path):
    builder = assets()
    out = tmp_path / "release-9.9.9"
    out.mkdir()
    wheel = out / f"pdfstruct-{VERSION}-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    keep = {"PDFStruct-Portable-9.9.9-win64.zip": b"324 MB of portable build", "notes.txt": b"mine"}
    for name, data in keep.items():
        (out / name).write_bytes(data)
    import sys
    argv, sys.argv = sys.argv, ["build_release_assets.py", "--out", str(out), "--wheel", str(wheel)]
    try:
        assert builder.main() == 0
    finally:
        sys.argv = argv
    for name, data in keep.items():
        assert (out / name).read_bytes() == data, name
    assert (out / "pdfstruct-plugin.zip").is_file() and wheel.read_bytes() == b"wheel"


def test_local_ci_builds_into_its_own_folder_and_never_touches_dist(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("ci_local", TOOL_DIR / "scripts" / "ci_local.py")
    ci = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ci)
    assert not hasattr(ci, "DIST")
    source = (TOOL_DIR / "scripts" / "ci_local.py").read_text(encoding="utf-8")
    assert "rmtree" not in source and "import shutil" not in source  # it deletes nothing

    repo = tmp_path / "repo"
    release = repo / "dist" / "release-0.0.1"
    release.mkdir(parents=True)
    (release / "PDFStruct-Portable-0.0.1-win64.zip").write_bytes(b"old release")
    monkeypatch.setattr(ci, "ROOT", repo)
    built = []

    def fake_build(*command, cwd=None, timeout=900):
        out = Path(command[command.index("--outdir") + 1])
        built.append(out)
        with zipfile.ZipFile(out / f"pdfstruct-{VERSION}-py3-none-any.whl", "w") as wheel:
            for path in sorted((TOOL_DIR / "src" / "pdfstruct").rglob("*.py")):
                wheel.writestr(path.relative_to(TOOL_DIR / "src").as_posix(), "")
            wheel.writestr(f"pdfstruct-{VERSION}.dist-info/entry_points.txt", "\n".join(
                [f"{name} = pdfstruct.cli:{name}" for name in ci.ALIASES]
                + ["pdfstruct = pdfstruct.cli:main", "pdfstruct-mcp = pdfstruct.mcp_server:main",
                   "pdfstruct-create = pdfstruct.cli:create", "pdfstruct-gui = pdfstruct.gui.app:main"]))
        import tarfile
        with tarfile.open(out / f"pdfstruct-{VERSION}.tar.gz", "w:gz") as sdist:
            for name in ("pyproject.toml", "src/pdfstruct/__init__.py", "README.md", "LICENSE"):
                sdist.add(TOOL_DIR / name, arcname=f"pdfstruct-{VERSION}/{name}")
        return ""
    monkeypatch.setattr(ci, "sh", fake_build)

    for inside_dist in (repo / "dist", repo / "dist" / "ci", release):
        with pytest.raises(ci.StepFailed, match="holds release files"):
            ci.step_build(VERSION, inside_dist)
    wheel, sdist = ci.step_build(VERSION, tmp_path / "run" / "dist")
    assert built == [tmp_path / "run" / "dist"] and wheel.parent == sdist.parent == tmp_path / "run" / "dist"
    assert [p.name for p in release.iterdir()] == ["PDFStruct-Portable-0.0.1-win64.zip"]
    assert (release / "PDFStruct-Portable-0.0.1-win64.zip").read_bytes() == b"old release"
    with pytest.raises(FileExistsError):  # an existing folder is an error, never emptied
        ci.step_build(VERSION, tmp_path / "run" / "dist")
