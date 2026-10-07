#!/usr/bin/env python3
"""Build the Windows portable folder and zip (PyInstaller proof of build).

    pip install -e ".[gui,packaging]"
    python packaging/windows/build_portable.py [--out DIR] [--no-zip]

Result: <out>/PDFStruct/ with PDFStruct.exe (window) and pdfstruct-cli.exe (command line),
plus <out>/PDFStruct-Portable-<version>-win64.zip and its SHA256. No Python is needed on the
target machine. OCR models are not bundled; they are downloaded on first OCR use.

The folder bundles Qt for Python (LGPL-3.0) and other third-party packages, so the script puts
their license texts next to the programs and stops if it cannot obtain the LGPL/GPL texts.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import sysconfig
import urllib.request
import zipfile
from importlib import metadata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SPDX = "https://raw.githubusercontent.com/spdx/license-list-data/main/text/"
LICENSE_TEXTS = {"LGPL-3.0.txt": [SPDX + "LGPL-3.0-only.txt", "https://www.gnu.org/licenses/lgpl-3.0.txt"],
                 "GPL-3.0.txt": [SPDX + "GPL-3.0-only.txt", "https://www.gnu.org/licenses/gpl-3.0.txt"]}
BUNDLED_WITH_LICENSES = ["PySide6_Essentials", "shiboken6", "paddlepaddle", "paddleocr", "paddlex",
                         "reportlab", "pypdfium2", "opencv-contrib-python", "numpy", "pillow",
                         "python-docx", "openpyxl", "shapely", "pyclipper"]
README = """PDFStruct {version} - portable build for Windows x64

  PDFStruct.exe        the desktop window
  pdfstruct-cli.exe    the command line, e.g.  pdfstruct-cli.exe report.pdf --format xlsx

No installation and no Python needed: unpack the folder anywhere and start PDFStruct.exe.
Keep the "_internal" folder next to the programs.

- Unsigned build: Windows SmartScreen may ask for confirmation on first start.
- OCR models are not included. The first OCR run downloads them once (about 70 MB) to
  %USERPROFILE%\\.pdfstruct\\models; that step needs an internet connection.
- The MCP server for Claude is not part of this folder; use the pip installation for it.
- Built and tested on a single Windows 11 x64 machine.

PDFStruct is MIT licensed (LICENSE.txt). Third-party components keep their own licenses:
see THIRD_PARTY_NOTICES.md and the "licenses" folder. Qt for Python (PySide6) is used under
the LGPL-3.0; it is dynamically linked and its libraries in "_internal" can be replaced.
Source code: https://github.com/KelesogluMustafa/pdfstruct
"""


def run(*command) -> None:
    print("$", " ".join(str(c) for c in command), flush=True)
    subprocess.run([str(c) for c in command], check=True, cwd=ROOT)


def collect_licenses(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, urls in LICENSE_TEXTS.items():  # required by the LGPL for the bundled Qt libraries
        text = b""
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    text = response.read()
            except OSError:
                continue
            if b"GNU" in text and len(text) > 5000:
                break
        else:
            raise SystemExit(f"could not obtain {name}; the bundle must not ship without it")
        (target / name).write_bytes(text)
    site = Path(sysconfig.get_path("purelib"))
    for package in BUNDLED_WITH_LICENSES:
        try:
            dist = metadata.distribution(package)
        except metadata.PackageNotFoundError:
            continue
        files = [f for f in (dist.files or [])
                 if any(key in f.name.upper() for key in ("LICEN", "COPYING", "NOTICE"))
                 and "Commercial" not in f.name
                 and Path(f.name).suffix.lower() in ("", ".txt", ".md", ".rst")]
        for item in files:
            source = Path(dist.locate_file(item))
            if source.is_file():
                shutil.copyfile(source, target / f"{dist.metadata['Name']}-{source.name}")
    vera = site / "reportlab" / "fonts" / "bitstream-vera-license.txt"
    if vera.is_file():
        shutil.copyfile(vera, target / "bitstream-vera-license.txt")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "dist" / "portable"))
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("this script builds the Windows folder; run it on Windows")
    version = metadata.version("pdfstruct")
    out = Path(args.out).resolve()
    folder = out / "PDFStruct"
    shutil.rmtree(folder, ignore_errors=True)
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--log-level", "WARN",
        "--distpath", out, "--workpath", out / "work", HERE / "pdfstruct.spec")

    shutil.copyfile(ROOT / "LICENSE", folder / "LICENSE.txt")
    shutil.copyfile(ROOT / "THIRD_PARTY_NOTICES.md", folder / "THIRD_PARTY_NOTICES.md")
    (folder / "README.txt").write_text(README.format(version=version), encoding="utf-8")
    collect_licenses(folder / "licenses")

    size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
    print(f"FOLDER: {folder}  ({size / 1e6:.0f} MB, {len(list((folder / 'licenses').iterdir()))} license files)")
    if args.no_zip:
        return 0
    archive = out / f"PDFStruct-Portable-{version}-win64.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                bundle.write(path, Path("PDFStruct") / path.relative_to(folder))
    print(f"ZIP: {archive}  ({archive.stat().st_size / 1e6:.0f} MB)")
    print(f"SHA256: {sha256(archive)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
