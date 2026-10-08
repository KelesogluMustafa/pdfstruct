<p align="center">
  <img src="docs/assets/pdfstruct-hero.png" alt="PDFStruct: PDF, DOCX and image files are converted on your computer into JSON, XLSX, PDF and other formats" width="820">
</p>

# PDFStruct

**PDFStruct converts documents on your computer into structured data and ten output formats, without uploading them.**

Your document stays on your computer. PDFStruct does the text extraction, OCR and conversion
there, and Claude can use the result without loading the whole document into the conversation.

[![Latest release](https://img.shields.io/github/v/release/KelesogluMustafa/pdfstruct)](https://github.com/KelesogluMustafa/pdfstruct/releases/latest)
[![CI](https://github.com/KelesogluMustafa/pdfstruct/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/KelesogluMustafa/pdfstruct/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.10 to 3.13](https://img.shields.io/badge/python-3.10%20to%203.13-blue.svg)

**[Download for Windows](https://github.com/KelesogluMustafa/pdfstruct/releases/latest)** ·
**[Download Portable](#portable-quick-start)** ·
**[View Website](https://mustafakelesoglu.de/en/pdfstruct)** ·
**[Add to Claude](#claude-desktop-setup)** ·
**[CLI Quick Start](#cli-quick-start)** ·
**[Documentation](#documentation)**

| | File on the [latest release](https://github.com/KelesogluMustafa/pdfstruct/releases/latest) |
|---|---|
| **Recommended** | `PDFStruct-Windows-Setup-0.2.1.zip` |
| **No Python** | `PDFStruct-Portable-0.2.1-win64.zip` |

## Contents

[Why PDFStruct](#why-pdfstruct) ·
[How it works](#how-it-works) ·
[Supported formats](#supported-formats) ·
[Choose your installation](#choose-your-installation) ·
[Windows Setup](#windows-setup-quick-start) ·
[Portable](#portable-quick-start) ·
[Claude Desktop](#claude-desktop-setup) ·
[Claude Code / Cowork](#claude-code--cowork-setup) ·
[CLI](#cli-quick-start) ·
[Privacy and tokens](#privacy-and-llm-context) ·
[Limitations](#important-limitations) ·
[Documentation](#documentation) ·
[Status](#platform-and-project-status) ·
[Contributing](#contributing-and-support) ·
[License](#license)

## Why PDFStruct

- **Nothing is uploaded.** Extraction, OCR and conversion run on your computer. No account,
  no payment, no telemetry, no usage limit.
- **Scans and mixed documents work.** Pages with real text are read directly; pages that are
  only a picture go through OCR.
- **One read, many formats.** Ask for XLSX, JSON and PDF together: the file is processed once.
- **Repeatable.** The same command gives the same result, for one file or a whole folder.
- **Built for Claude.** Claude starts the conversion and gets back a short status and the
  output paths, not the document.

It is for people who care where their documents go, developers building document workflows,
Claude Desktop, Claude Code and Cowork users, and anyone converting scanned or mixed files in
batches.

## How it works

```
Document
  -> native text, when the page has it
  -> OCR, when the page needs it
  -> one structured result
  -> the output formats you selected
```

- The decision between native text and OCR is made **per page**.
- A mixed PDF can therefore use both in the same document.
- Pages with low OCR confidence are listed for review instead of being passed off as good.
- Every format you ask for is written from that single result.

## Supported formats

| Inputs | Outputs |
|---|---|
| PDF | JSON |
| DOCX | HTML |
| TXT | TXT |
| Markdown | Markdown |
| HTML | CSV |
| JPG / JPEG | XLSX |
| PNG | DOCX |
| TIFF / TIF | JSONL |
| BMP | SQLite |
| WebP | PDF |

Any input can go to any output, with one exception: a PDF is not written again as PDF.
Each input is processed once, and all selected outputs come from that one result.

## Choose your installation

| Goal | Use |
|---|---|
| Recommended Windows installation | `PDFStruct-Windows-Setup-0.2.1.zip` |
| Desktop window and command line without Python | `PDFStruct-Portable-0.2.1-win64.zip` |
| Claude Desktop chat | Windows Setup + `pdfstruct-0.2.1.mcpb` (+ `pdfstruct-skill.zip` if you do not use the plugin) |
| Claude Code / Cowork | Windows Setup + `pdfstruct-plugin.zip` |
| Development, macOS, Linux | The wheel or a source checkout: see [Installation](docs/INSTALLATION.md) |

Good to know:

- Setup and Portable are alternatives for ordinary conversion. You need only one.
- **Claude integrations require Windows Setup.** Portable does not include the MCP server.
- The `.mcpb`, the plugin and the skill ZIP contain no PDFStruct runtime. They start the one
  that Windows Setup installed.
- The plugin already contains the skill and the MCP registration. If you use the plugin, do
  not install the skill ZIP or register the MCP server a second time.

## Windows Setup quick start

Needs Python 3.10, 3.11, 3.12 or 3.13 from [python.org](https://www.python.org/downloads/).

1. Open the [latest release](https://github.com/KelesogluMustafa/pdfstruct/releases/latest).
2. Download `PDFStruct-Windows-Setup-0.2.1.zip`.
3. Extract it.
4. Run `install-windows.cmd`.
5. Start the desktop window:

   ```
   %USERPROFILE%\.local\pdfstruct\current\Scripts\pdfstruct-gui.exe
   ```

The command line is in the same folder (`pdfstruct.exe`). The installer does not change your
PATH and does not touch your system Python packages.

- Your documents remain on your computer.
- The first OCR run downloads the OCR models once, about 13 MB with the default models.
- `update-windows.cmd` updates after asking you; `update-windows.cmd -Rollback` goes back.
  Details: [Installation](docs/INSTALLATION.md).

## Portable quick start

Python is not required.

1. Download `PDFStruct-Portable-0.2.1-win64.zip` from the
   [latest release](https://github.com/KelesogluMustafa/pdfstruct/releases/latest).
2. Extract it completely. Do not run it from inside the ZIP.
3. Run `PDFStruct.exe` (desktop window) or `pdfstruct-cli.exe` (command line).

- The package is large because Qt and the OCR runtime are included.
- The first OCR run may download the OCR models (about 13 MB with the default models).
- The build is unsigned, so Windows SmartScreen may warn on first start.
- Portable has no updater: download the next ZIP to update.
- Portable has no Claude or MCP integration. Claude users should use Windows Setup.

## Claude Desktop setup

1. Install [Windows Setup](#windows-setup-quick-start).
2. Download `pdfstruct-0.2.1.mcpb` and install it in Claude:
   **Settings → Extensions → Advanced settings → Install Extension**.
3. Skill: if you also install the [plugin](#claude-code--cowork-setup), you are done. If you
   use only the extension, add `pdfstruct-skill.zip` in Claude's skill settings so Claude
   knows the workflow.
4. Restart Claude.
5. Try it:

   ```
   Convert C:\Documents\scan.png to PDF and TXT. Do not place document text in the conversation; return only the result and output paths.
   ```

More: [Claude integration](docs/CLAUDE_INTEGRATION.md).

## Claude Code / Cowork setup

1. Install [Windows Setup](#windows-setup-quick-start).
2. Install `pdfstruct-plugin.zip` as a plugin. In Claude Code you can also unpack it and run
   `claude --plugin-dir <unpacked folder>`.
3. The plugin includes the skill and the MCP registration. Do not also install
   `pdfstruct-skill.zip` or add the MCP server by hand.
4. Verify: `claude mcp list` (or `/mcp`) shows `plugin:pdfstruct:pdfstruct` as connected.
5. Try the same prompt:

   ```
   Convert C:\Documents\scan.png to PDF and TXT. Do not place document text in the conversation; return only the result and output paths.
   ```

## CLI quick start

With Windows Setup the commands are in `%USERPROFILE%\.local\pdfstruct\current\Scripts`; in the
portable folder use `pdfstruct-cli.exe` in place of `pdfstruct`.

```
pdfstruct                                             interactive menu: pick files, then formats
pdfstruct report.docx --format pdf                    one file, one format
pdfstruct scan.png --format txt,docx,pdf              one file, several formats, one OCR pass
pdfstruct "C:\Documents" --format json --all-types    every supported file in a folder
pdfstruct report.pdf --format txt --force-ocr         run OCR on every page
pdfxlsx report.pdf                                    short alias for --format xlsx
```

Results go to an `output` folder next to each input. Source files are never overwritten.
All commands, flags and aliases: [CLI reference](docs/CLI_REFERENCE.md).

## Privacy and LLM context

- Extraction, OCR and conversion are deterministic work and run on your computer.
- Claude normally receives a compact status and the output paths, not the document.
- Document text is returned only when you explicitly ask Claude to read or search it.
- `read_excerpt` returns at most 2,000 characters per call.

This can reduce unnecessary LLM context and token use, because a long document does not have
to be loaded into the conversation just to be converted. How much it saves depends on what
you ask Claude to do with the content afterwards.

The only network access is the one-time download of the OCR models.

## Important limitations

- **CSV and XLSX** contain extracted text blocks, one per row. They are not reconstructed tables.
- **DOCX to PDF** is a readable reflow, not a pixel-perfect copy of the layout.
- **Same-format conversions** (DOCX to DOCX, Markdown to Markdown) keep the text, not the styling.
- PDFStruct does **not** summarize, understand meaning or extract fields such as invoice
  numbers. It produces reliable raw text and structure.
- **OCR runs on the CPU by default.** GPU use is not a ready, supported setup.
- The **first OCR use downloads models** (about 13 MB with the default models).
- **Non-Latin** OCR and PDF output are not ready defaults.
- **Not supported as input:** `.doc`, RTF, ODT, EPUB, PowerPoint, HEIC, CSV, XLSX.
- The desktop window was tested by hand **only on Windows 11**. It is unverified on macOS and
  Linux.
- **OCR is not available** on macOS Intel, Linux ARM64 and Windows ARM.

## Documentation

| Document | What is in it |
|---|---|
| [Installation](docs/INSTALLATION.md) | Windows Setup, update and rollback, portable, pip and source installs, uninstall |
| [Claude integration](docs/CLAUDE_INTEGRATION.md) | Extension, plugin, skill, MCP tools, manual configuration, rules for Claude |
| [CLI reference](docs/CLI_REFERENCE.md) | Commands, flags, aliases, output names, terminal output |
| [PDF pipeline reference](docs/PDF_PIPELINE_REFERENCE.md) | Native text or OCR, quality score, raw JSON, configuration, parsers |
| [Architecture](docs/MASTER_ARCHITECTURE.md) | Design, principles and rules for changes |
| [Changelog](CHANGELOG.md) | What changed in each version |

## Platform and project status

| | |
|---|---|
| Version | v0.2.1 |
| Stage | Alpha |
| License | MIT, free and open source |
| Repository | Public |
| PyPI | Not published; install from the release files |
| Windows | Windows Setup and a portable desktop/command-line package are available |
| Automated tests | GitHub Actions on Windows, Ubuntu and macOS |
| Desktop window | Tested by hand on Windows 11 |

## Contributing and support

- If PDFStruct is useful to you, star the repository.
- Report problems you can reproduce in
  [Issues](https://github.com/KelesogluMustafa/pdfstruct/issues); a small sample file helps.
- Contributions are welcome. Read the [architecture](docs/MASTER_ARCHITECTURE.md) first and
  run `python scripts/ci_local.py` before opening a pull request.
- More about the project: [mustafakelesoglu.de/en/pdfstruct](https://mustafakelesoglu.de/en/pdfstruct).

All core functionality is available without payment, accounts, usage limits or tracking.

## License

[MIT](LICENSE). Third-party components keep their own licenses: see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
