# Changelog

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
