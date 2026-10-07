#!/usr/bin/env python3
"""Build the Claude for Windows files: the .mcpb launcher extension and the Skill ZIP.

    python scripts/build_claude_windows.py            -> dist/claude-windows/
    python scripts/build_claude_windows.py --stage    -> also copy to ~/.local/pdfstruct/claude-windows

The .mcpb is a launcher only (manifest + a .cmd for manual checks): it starts
%USERPROFILE%\\.local\\pdfstruct\\v<version>\\Scripts\\pdfstruct-mcp.exe, which
scripts/install-windows.ps1 installs from the release wheel. It bundles no runtime.
An .mcpb file is a ZIP archive; it is written here directly and reproducibly.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "integrations" / "claude-desktop"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_skill_zip  # noqa: E402

GUIDE = """PDFSTRUCT v{version} - CLAUDE FOR WINDOWS (CHAT) INSTALL GUIDE
================================================================

What is in this folder

  mcp\\pdfstruct-{version}.mcpb                 the extension (connects Claude to PDFStruct)
  mcp\\claude_desktop_config.snippet.json    manual alternative, only if the extension fails
  skill\\pdfstruct-skill.zip                  the Skill (teaches Claude when and how to use it)

Requirement: PDFStruct v{version} is installed at
  {runtime}
(scripts\\install-windows.ps1 from the release wheel does that). The extension only starts that
program. It contains no copy of it and needs no key or password.


A. INSTALL THE EXTENSION (MCP)

  1. Open Claude for Windows.
  2. Menu (top left) -> File -> Settings -> Extensions.
  3. Click "Advanced settings", then "Install Extension...".
  4. Choose:  {stage}\\mcp\\pdfstruct-{version}.mcpb
  5. Claude shows the extension details and says it is not signed. That is expected: it was
     built on this computer. Click "Install".
  6. Make sure the PDFStruct switch is ON.


B. INSTALL THE SKILL

  1. In Claude: Settings -> Capabilities. Make sure "Code execution and file creation" is ON.
     Skills need it.
  2. Open Customize -> Skills.
  3. Upload:  {stage}\\skill\\pdfstruct-skill.zip
  4. Turn the "pdfstruct" skill ON.


C. RESTART

  Close Claude completely (right-click the Claude icon in the system tray -> Quit), open it
  again and start a NEW chat.


D. HOW TO SEE THAT IT IS CONNECTED

  - Settings -> Extensions: PDFStruct is listed and switched ON, with no error.
  - In a new chat the tools menu lists PDFStruct with five tools:
    convert, inspect, supported_formats, search, read_excerpt.


E. IF THE EXTENSION DOES NOT LOAD

  Remove it again and add the content of mcp\\claude_desktop_config.snippet.json to
  %APPDATA%\\Claude\\claude_desktop_config.json (merge it into an existing "mcpServers" block),
  then restart Claude.
"""


def manifest() -> dict:
    return json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))


def build_mcpb(target: Path) -> Path:
    """Write the launcher bundle. The manifest version decides the runtime folder it starts."""
    data = manifest()
    entry = BUNDLE / data["server"]["entry_point"]
    if not entry.is_file():
        raise SystemExit(f"entry point missing: {entry}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in BUNDLE.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(path.relative_to(BUNDLE).as_posix(), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "dist" / "claude-windows"))
    parser.add_argument("--stage", action="store_true",
                        help="also copy the result to ~/.local/pdfstruct/claude-windows")
    args = parser.parse_args()
    version = manifest()["version"]
    out = Path(args.out).resolve()
    stage = Path.home() / ".local" / "pdfstruct" / "claude-windows"
    runtime = Path.home() / ".local" / "pdfstruct" / f"v{version}"

    shutil.rmtree(out, ignore_errors=True)
    mcpb = build_mcpb(out / "mcp" / f"pdfstruct-{version}.mcpb")
    snippet = {"mcpServers": {"pdfstruct": {
        "command": str(runtime / "Scripts" / "pdfstruct-mcp.exe"), "args": []}}}
    (out / "mcp" / "claude_desktop_config.snippet.json").write_text(
        json.dumps(snippet, indent=2) + "\n", encoding="utf-8")
    skill = build_skill_zip.build()
    build_skill_zip.check(skill)
    (out / "skill").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(skill, out / "skill" / "pdfstruct-skill.zip")
    where = stage if args.stage else out
    (out / "README-INSTALL.txt").write_text(
        GUIDE.format(version=version, runtime=runtime, stage=where), encoding="utf-8")

    print(f"MCPB: {mcpb}  ({mcpb.stat().st_size} bytes)")
    print(f"SKILL: {out / 'skill' / 'pdfstruct-skill.zip'}")
    print(f"RUNTIME EXPECTED AT: {runtime}  (exists: {(runtime / 'Scripts' / 'pdfstruct-mcp.exe').is_file()})")
    if args.stage:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.copytree(out, stage)
        print(f"STAGED: {stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
