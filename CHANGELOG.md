# Changelog

## 0.3.0

- New: text to local document. Text that exists only in a conversation, a terminal pipe or the
  window is written as DOCX, PDF, HTML, Markdown or TXT on this computer, without a source file
- MCP tool `create_document(name, content, formats, output_dir, content_type, overwrite)`, the
  sixth tool. It returns a status, the created paths and short warnings, never the text. The
  five existing tools are unchanged
- Markdown is read with headings, paragraphs, bold, italic, inline code, bullet and numbered
  lists, fenced code, simple tables, horizontal rules and links; plain text keeps its
  paragraphs and line breaks. `{{PLACEHOLDER}}` values are kept exactly in both
- DOCX output uses Word heading styles, real lists, real tables and a monospace `Code` style;
  PDF is a readable A4 re-flow; HTML is escaped and can load or run nothing
- Command `pdfstruct-create` (text from `--content-file` or standard input)
- Desktop window: a second tab, "Create from text"
- Safe by default: the name is a file name only (no folder, no traversal, no reserved Windows
  name), existing files are kept and reported unless overwriting was asked for, and a call
  writes all of its files or none: each is written under a temporary name and then moved
  into place
- Limits: 500,000 characters and 20,000 paragraphs, list items and table rows per document.
  Malformed Markdown is parsed in linear time
- Portable package: `pdfstruct-create.exe` next to the window and the command line
- Everything runs locally: no upload, no network access, no LLM call. Writing the text still
  costs tokens; formatting and saving it does not
- No change to file conversion, OCR, the existing commands or the existing MCP tools, with
  two fixes that also reach file conversion: a Markdown heading with a long run of spaces no
  longer takes quadratic time to read, and a heading about a page tall no longer makes the
  PDF writer hang
- Updating from 0.2.1: run `install-windows.cmd` from the 0.3.0 Setup ZIP. `update-windows.cmd`
  of 0.2.1 rejects 0.3.0 because its runtime check expects exactly five MCP tools; it leaves
  0.2.1 active. The check now accepts additional tools, so later updates are not affected
- Local CI builds into a temporary folder and never deletes `dist/`; the release builder no
  longer empties its output folder

## 0.2.1

- Windows: `install-windows.cmd` installs a release wheel into its own versioned folder
  (`%USERPROFILE%\.local\pdfstruct\v<version>`), checks it (import, command line, MCP server)
  and only then points `...\pdfstruct\current` at it. Not linked to a source checkout
- `update-windows.cmd`: user-confirmed update from GitHub Releases with checksum verification;
  the old version is kept; `-Rollback`, `-Check`, `-List`. No background updater
- Claude Code / Cowork plugin (`pdfstruct-plugin.zip`): the skill plus the registration of the
  existing MCP server
- Claude Desktop extension (`.mcpb`) is a plain launcher for the active runtime: `binary` server
  type, no Node launcher, nothing to configure. It needs PDFStruct installed first
- One skill source (`plugin/skills/pdfstruct/SKILL.md`); the plugin and `pdfstruct-skill.zip` are
  built from it. The skill is shorter and uses the MCP tools only in Claude Desktop chat
- `PDFStruct-Windows-Setup-<version>.zip` bundles the install/update scripts and the wheel
- No change to conversion, the command line, the desktop window, the MCP tools or their limits

## 0.2.0

- Inputs: DOCX, TXT, Markdown, HTML and images (JPG, PNG, TIFF, BMP, WebP) next to PDF
- Output: PDF as the tenth format (readable re-flow for text inputs, picture with searchable
  text for images)
- Desktop window `pdfstruct-gui` (PySide6, optional extra `[gui]`)
- Local MCP server `pdfstruct-mcp` (optional extra `[mcp]`) and an Agent Skill for Claude
- One shared conversion service behind CLI, window and MCP: one extraction per input, one OCR
  engine per job, progress events, cooperative cancel
- Raw schema 1.1 for non-PDF inputs (additive); PDF raw documents are unchanged
- `--all-types` to take every supported file of a folder; folders stay PDF-only by default
- Non-PDF inputs keep their extension in output names (`report.docx.txt`)
- Optional: Windows portable folder (PyInstaller) and a Claude Desktop `.mcpb` connector
- Verified by CI on Windows x86_64, Linux x86_64 and macOS Apple Silicon; the desktop window was
  used by hand on Windows 11 only

## 0.1.0

- Initial packaged version of PDFStruct
- Interactive `pdfstruct` terminal menu: multi-PDF and multi-format selection
- Native PDF extraction
- Automatic OCR fallback (PaddleOCR, in-process, CPU by default, models cached per user)
- Multi-format exports
- Batch/file/folder CLI support
