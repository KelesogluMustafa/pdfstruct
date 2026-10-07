# Changelog

## Unreleased

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

## 0.1.0

- Initial packaged version of PDFStruct
- Interactive `pdfstruct` terminal menu: multi-PDF and multi-format selection
- Native PDF extraction
- Automatic OCR fallback (PaddleOCR, in-process, CPU by default, models cached per user)
- Multi-format exports
- Batch/file/folder CLI support
