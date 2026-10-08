# Installation

PDFStruct is not on PyPI. Everything is installed from the files of a
[GitHub release](https://github.com/KelesogluMustafa/pdfstruct/releases/latest) or from a
source checkout.

| You want | Use |
|---|---|
| The normal Windows installation, with updates and Claude | [Windows Setup](#windows-setup) |
| The desktop window and command line without Python | [Windows portable](#windows-portable) |
| macOS, Linux, or your own Python environment | [pip](#pip-any-platform) |
| To work on the code | [Source checkout](#source-checkout-development) |

## Windows Setup

Requires Python 3.10, 3.11, 3.12 or 3.13 from [python.org](https://www.python.org/downloads/).

1. Download `PDFStruct-Windows-Setup-<version>.zip` and extract it.
2. Run `install-windows.cmd`.

What the installer does:

- Creates `%USERPROFILE%\.local\pdfstruct\v<version>` with its own Python environment.
- Installs the wheel from the ZIP after verifying its SHA-256 checksum.
- Checks the result: import, command line, and a real MCP handshake.
- Only then points `%USERPROFILE%\.local\pdfstruct\current` at the new version.

The installation is not linked to any source folder. Other installed versions are kept, your
PATH is not changed and your system Python packages are not touched. If a check fails, the
previously active version stays active.

Programs, all in `%USERPROFILE%\.local\pdfstruct\current\Scripts`:

| Program | Purpose |
|---|---|
| `pdfstruct-gui.exe` | desktop window |
| `pdfstruct.exe` | command line |
| `pdfjson.exe`, `pdfxlsx.exe`, ... | per-format aliases |
| `pdfstruct-create.exe` | text or Markdown to documents |
| `pdfstruct-mcp.exe` | MCP server that Claude starts |

Add that folder to your PATH yourself if you want to type `pdfstruct` from anywhere.

### Update, check, list, roll back

Run these from the extracted setup folder:

| Task | Command |
|---|---|
| Update | `update-windows.cmd` shows the active and the latest stable version and asks before it downloads. |
| Only check | `update-windows.cmd -Check` |
| List installed versions | `update-windows.cmd -List` |
| Go back | `update-windows.cmd -Rollback` switches to the previously active version. |

An update is downloaded from GitHub Releases, verified against its SHA-256 checksum,
installed next to the old version, checked, and only then made active. The old version is
kept. Nothing runs in the background: there is no service and no scheduled task.

After an update, restart Claude. The Claude extension and plugin follow `current` and do not
need to be reinstalled. Install a newer `.mcpb` or plugin by hand only when a release says
they changed.

To reinstall the files of a version that is already installed, close Claude first (a running
MCP server keeps its files in use) and run
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-windows.ps1 -Repair`.

### Uninstall

1. Remove the PDFStruct extension and plugin in Claude, if you installed them.
2. Remove the link: `rmdir "%USERPROFILE%\.local\pdfstruct\current"`
3. Delete the folder `%USERPROFILE%\.local\pdfstruct`.

OCR models are stored separately in `%USERPROFILE%\.pdfstruct\models`.

## Windows portable

`PDFStruct-Portable-<version>-win64.zip` needs no Python and installs nothing.

1. Extract the ZIP completely. Do not start the programs from inside the ZIP.
2. Run `PDFStruct.exe` (desktop window) or `pdfstruct-cli.exe` (command line). Keep the
   `_internal` folder next to them.

Notes:

- It is large (several hundred MB unpacked) because it carries Qt and the OCR runtime.
- OCR models are not included; the first OCR run downloads them once (about 13 MB with the default models).
- The build is unsigned. Windows SmartScreen may ask for confirmation on first start.
- There is no updater. To update, download the next ZIP.
- The MCP server, Claude extension, plugin and skill are not part of it. For Claude, use
  Windows Setup.
- Built and tested on one Windows 11 x64 machine.

Build it yourself:

```
pip install -e ".[gui,packaging]"
python packaging/windows/build_portable.py
```

## pip (any platform)

```
python -m venv .venv
.venv\Scripts\activate            (macOS/Linux: source .venv/bin/activate)
pip install "pdfstruct-<version>-py3-none-any.whl[gui,mcp]"
```

`[gui]` adds the desktop window (PySide6), `[mcp]` the MCP server. Leave them out for the
command line only.

The OCR packages are installed automatically on Windows x86_64, Linux x86_64 and macOS Apple
Silicon. On macOS Intel, Linux ARM64 and Windows ARM, PDFStruct installs and reads native
text, but OCR is not available because PaddlePaddle publishes no wheels for them.

## Source checkout (development)

Windows: `setup-windows.cmd` creates `.venv` inside the repository, installs PDFStruct in
editable mode and opens the window. The `.cmd` files in the repository root (`pdfstruct.cmd`,
`pdfjson.cmd`, `pdfstruct-gui.cmd`, ...) use that `.venv` without activating it.

Any platform:

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,gui,mcp]"
```

Do not point Claude at a development environment: a running MCP server keeps its files
locked and follows whatever the working tree contains. Use Windows Setup for Claude.

### Local CI and release files

```
python scripts/ci_local.py
```

`scripts/ci_local.py` (Windows shortcut: `ci-local`) runs the whole local CI: import and
version check, test suite, wheel and sdist build, a clean temporary environment with the
built wheel, every console script, native and OCR conversions, the desktop window without a
display, the MCP server over stdio and the skill archives. Tests only:
`python -m pytest -q`.

`python scripts/build_release_assets.py` writes the release files reproducibly to
`dist/release-<version>/`. The architecture and the rules for changes are in
[MASTER_ARCHITECTURE.md](MASTER_ARCHITECTURE.md).

### Repository layout

```
pyproject.toml              package definition, dependencies, extras, console scripts
src/pdfstruct/
  __init__.py               version (single source)
  service.py                run_job: the conversion service shared by CLI, window and MCP
  inputs/                   input adapters: text (txt, md), html, docx, image
  extract.py                PDF extraction, quality score, raw JSON, parser hook
  ocr.py                    OCR backend (PaddleOCR, in-process, loaded lazily)
  export.py                 raw JSON -> html/txt/md/csv/xlsx/docx/jsonl/sqlite/pdf
  pdfwriter.py              PDF output (reportlab)
  create.py                 create_document: text in memory -> docx/pdf/html/md/txt files
  docwriter.py              DOCX and HTML content for created documents
  cli.py                    pdfstruct, the alias commands and pdfstruct-create
  interactive.py            terminal menus
  mcp_server.py             MCP server (pdfstruct-mcp)
  gui/                      desktop window (pdfstruct-gui)
plugin/                     Claude Code / Cowork plugin and the single skill source
integrations/claude-desktop/  Claude Desktop extension (.mcpb launcher)
packaging/windows/          PyInstaller spec and build_portable.py
scripts/                    installer, updater, runtime check, local CI, release build
schemas/                    raw JSON schema
examples/                   example project parser
tests/
```
