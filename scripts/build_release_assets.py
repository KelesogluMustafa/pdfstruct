#!/usr/bin/env python3
"""Build every release file for the Windows / Claude distribution, reproducibly.

    python scripts/build_release_assets.py            -> dist/release-<version>/
    python scripts/build_release_assets.py --stage    -> also copy the Claude files to
                                                         ~/.local/pdfstruct/claude-windows

    PDFStruct-Windows-Setup-<version>.zip   install/update scripts + the wheel + its checksum
    pdfstruct-<version>.mcpb                Claude Desktop extension (launcher only)
    pdfstruct-plugin.zip                    Claude Code / Cowork plugin (skill + MCP registration)
    pdfstruct-skill.zip                     the same skill alone, for users without the plugin
    pdfstruct-<version>-py3-none-any.whl    the package (the updater downloads this one)
    pdfstruct-<version>.tar.gz              source distribution
    SHA256SUMS.txt                          checksums of all files above

No archive contains a Python runtime, PDFStruct's dependencies or OCR models. The skill has
one source, plugin/skills/pdfstruct/SKILL.md; the plugin and the skill ZIP are both built from it.

The output folder is never emptied: the files listed above are written or replaced, and
anything else in it (a portable ZIP, an older checksum file) is left alone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugin"
SKILL = PLUGIN / "skills" / "pdfstruct"
BUNDLE = ROOT / "integrations" / "claude-desktop"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)
SOURCE_DATE_EPOCH = "1767225600"  # 2026-01-01T00:00:00Z, so wheel and sdist are reproducible
SETUP_FILES = ["install-windows.cmd", "update-windows.cmd", "scripts/install-windows.ps1",
               "scripts/update-windows.ps1", "scripts/runtime-common.ps1",
               "scripts/verify_runtime.py", "LICENSE"]
TEXT_SUFFIXES = {".md", ".json", ".py", ".txt", ""}

GUIDE = """PDFSTRUCT {version} - INSTALL GUIDE (WINDOWS)
============================================

Choose what you need. Step 1 is always required; steps 2 and 3 are independent of each other.

  1. PDFStruct itself          install-windows.cmd                 (this folder)
  2. Claude Desktop chat       pdfstruct-{version}.mcpb
  3. Claude Code / Cowork      pdfstruct-plugin.zip

Do not also upload pdfstruct-skill.zip when you install the plugin: the plugin already contains
the skill. The skill ZIP is only for people who do not use the plugin.


1. INSTALL PDFSTRUCT

  Needs Python 3.10 - 3.13 from https://www.python.org/downloads/ .
  Double-click install-windows.cmd (or run it in a terminal).

  It creates  %USERPROFILE%\\.local\\pdfstruct\\v{version}  with its own Python environment,
  installs the wheel from this folder, checks the result and then points
  %USERPROFILE%\\.local\\pdfstruct\\current  at it. It is not linked to any source folder and
  other installed versions are kept.


2. CLAUDE DESKTOP CHAT: THE EXTENSION

  1. Open Claude. Menu (top left) -> File -> Settings -> Extensions.
  2. "Advanced settings" -> "Install Extension...".
  3. Choose pdfstruct-{version}.mcpb.
  4. Claude says the extension is not signed. That is expected. Click "Install".
  5. Make sure the PDFStruct switch is ON, then quit Claude completely (tray icon -> Quit),
     open it again and start a NEW chat.

  The extension is a launcher: it starts current\\Scripts\\pdfstruct-mcp.exe from step 1 and
  contains no copy of PDFStruct.

  Skill for Desktop chat (optional but recommended): Settings -> Capabilities, switch on
  "Code execution and file creation"; then Customize -> Skills and upload pdfstruct-plugin.zip
  as a plugin if your Claude offers that, otherwise upload pdfstruct-skill.zip.


3. CLAUDE CODE / COWORK: THE PLUGIN

  Upload or install pdfstruct-plugin.zip as a plugin. It brings the skill and registers the
  same MCP server. In Claude Code you can also load the unpacked folder:
      claude --plugin-dir <folder with the unpacked plugin>

  If you registered PDFStruct by hand before (claude mcp add ... pdfstruct) or copied the skill
  to %USERPROFILE%\\.claude\\skills\\pdfstruct, remove those once the plugin works; otherwise
  Claude sees the tools and the skill twice:
      claude mcp remove pdfstruct --scope user


UPDATE        update-windows.cmd          asks before it downloads; keeps the old version
ROLL BACK     update-windows.cmd -Rollback
VERSIONS      update-windows.cmd -List
DISABLE       switch the extension / plugin off in Claude (nothing is deleted)
UNINSTALL     remove the extension and the plugin in Claude, then delete
              %USERPROFILE%\\.local\\pdfstruct  (delete "current" first; it is only a link)

The extension and the plugin start the "current" runtime, so a runtime update needs no new
extension. Install a newer .mcpb or plugin by hand only when a release says they changed.
"""


def run(*command, env=None) -> None:
    subprocess.run([str(c) for c in command], check=True, cwd=ROOT, env=env,
                   stdout=subprocess.DEVNULL)


def version() -> str:
    text = (ROOT / "src" / "pdfstruct" / "__init__.py").read_text(encoding="utf-8")
    return text.split('__version__ = "')[1].split('"')[0]


def write_zip(target: Path, entries: list[tuple[str, bytes]]) -> Path:
    """A ZIP with fixed timestamps and order, so the same input gives the same bytes."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return target


def read_normalized(path: Path) -> bytes:
    """Text files with LF endings (a checkout may have CRLF); .cmd/.ps1 keep CRLF for Windows."""
    data = path.read_bytes()
    if path.suffix.lower() in (".cmd", ".ps1"):
        return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if path.suffix.lower() in TEXT_SUFFIXES:
        return data.replace(b"\r\n", b"\n")
    return data


def tree(folder: Path, prefix: str = "") -> list[tuple[str, bytes]]:
    return [(prefix + path.relative_to(folder).as_posix(), read_normalized(path))
            for path in sorted(folder.rglob("*")) if path.is_file()]


def validate_skill(text: str) -> None:
    if not text.startswith("---\n"):
        raise SystemExit("SKILL.md must start with a YAML front matter block")
    fields = dict(line.partition(":")[::2] for line in text[4:text.index("\n---", 4)].splitlines())
    if fields.get("name", "").strip() != "pdfstruct":
        raise SystemExit("skill front matter 'name' must be pdfstruct")
    if not 20 <= len(fields.get("description", "").strip()) <= 1024:
        raise SystemExit("skill front matter 'description' must be 20-1024 characters")


def build_skill(out: Path) -> Path:
    """pdfstruct-skill.zip -> pdfstruct/SKILL.md (the plugin's skill folder, unchanged)."""
    validate_skill((SKILL / "SKILL.md").read_text(encoding="utf-8").replace("\r\n", "\n"))
    return write_zip(out / "pdfstruct-skill.zip", tree(SKILL, "pdfstruct/"))


def build_plugin(out: Path, release: str) -> Path:
    """pdfstruct-plugin.zip -> the plugin folder's content at the archive root."""
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    if manifest["version"] != release:
        raise SystemExit(f"plugin.json version {manifest['version']} != package version {release}")
    return write_zip(out / "pdfstruct-plugin.zip", tree(PLUGIN))


def build_mcpb(out: Path, release: str) -> Path:
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    if manifest["version"] != release:
        raise SystemExit(f"manifest.json version {manifest['version']} != package version {release}")
    if not (BUNDLE / manifest["server"]["entry_point"]).is_file():
        raise SystemExit("the .mcpb entry point is missing")
    return write_zip(out / f"pdfstruct-{release}.mcpb", tree(BUNDLE))


def build_package(out: Path, release: str) -> tuple[Path, Path]:
    work = out / "_build"
    shutil.rmtree(work, ignore_errors=True)
    run(sys.executable, "-m", "build", "--outdir", work,
        env=dict(os.environ, SOURCE_DATE_EPOCH=SOURCE_DATE_EPOCH))
    wheel = out / f"pdfstruct-{release}-py3-none-any.whl"
    sdist = out / f"pdfstruct-{release}.tar.gz"
    shutil.move(str(work / wheel.name), wheel)
    shutil.move(str(work / sdist.name), sdist)
    shutil.rmtree(work)
    return wheel, sdist


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_setup(out: Path, release: str, wheel: Path) -> Path:
    """PDFStruct-Windows-Setup-<version>.zip: scripts, the wheel and the wheel's checksum."""
    top = f"PDFStruct-Windows-Setup-{release}/"
    entries = [(top + name, read_normalized(ROOT / name)) for name in SETUP_FILES]
    entries.append((top + wheel.name, wheel.read_bytes()))
    entries.append((top + "SHA256SUMS.txt", f"{sha256(wheel)} *{wheel.name}\n".encode()))
    entries.append((top + "README-INSTALL.txt",
                    GUIDE.format(version=release).replace("\n", "\r\n").encode("utf-8")))
    return write_zip(out / f"PDFStruct-Windows-Setup-{release}.zip", entries)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", help="output folder (default: dist/release-<version>)")
    parser.add_argument("--wheel", help="use this already built wheel instead of building one")
    parser.add_argument("--stage", action="store_true",
                        help="also copy the Claude files to ~/.local/pdfstruct/claude-windows")
    args = parser.parse_args()
    release = version()
    out = Path(args.out).resolve() if args.out else ROOT / "dist" / f"release-{release}"
    out.mkdir(parents=True, exist_ok=True)

    if args.wheel:
        wheel = out / Path(args.wheel).name
        if Path(args.wheel).resolve() != wheel:
            shutil.copyfile(args.wheel, wheel)
        files = [wheel]
    else:
        files = list(build_package(out, release))
        wheel = files[0]
    files += [build_setup(out, release, wheel), build_mcpb(out, release),
              build_plugin(out, release), build_skill(out)]
    sums = out / "SHA256SUMS.txt"
    sums.write_text("".join(f"{sha256(path)} *{path.name}\n" for path in sorted(files, key=lambda p: p.name.lower())),
                    encoding="utf-8", newline="\n")
    (out / "README-INSTALL.txt").write_text(GUIDE.format(version=release), encoding="utf-8")

    for path in [*sorted(files, key=lambda p: p.name.lower()), sums]:
        print(f"{path.stat().st_size:>10}  {path.name}")
    print(f"OUT: {out}")
    if args.stage:
        stage = Path.home() / ".local" / "pdfstruct" / "claude-windows"
        stage.mkdir(parents=True, exist_ok=True)
        for name in (f"pdfstruct-{release}.mcpb", "pdfstruct-plugin.zip", "pdfstruct-skill.zip",
                     "README-INSTALL.txt"):
            shutil.copyfile(out / name, stage / name)
        print(f"STAGED: {stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
