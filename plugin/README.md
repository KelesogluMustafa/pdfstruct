# PDFStruct plugin for Claude Code / Cowork

Brings two things:

- the **PDFStruct skill** (`skills/pdfstruct/SKILL.md`): when and how Claude uses PDFStruct
  without reading documents into the conversation;
- the **MCP server registration** (`.mcp.json`): starts the PDFStruct you installed, with the
  tools `convert`, `inspect`, `supported_formats`, `search` and `read_excerpt`.

The plugin contains no PDFStruct code, no Python and no OCR models.

## Requirement

Install PDFStruct first with `install-windows.cmd` from `PDFStruct-Windows-Setup-<version>.zip`.
The plugin starts

    %USERPROFILE%\.local\pdfstruct\current\Scripts\pdfstruct-mcp.exe

`current` always points at the active version, so the plugin keeps working after
`update-windows.cmd` without being reinstalled. Windows only for now.

## Claude Desktop chat

The normal chat in Claude Desktop does not start plugin MCP servers. Install the extension
`pdfstruct-<version>.mcpb` there (Settings, Extensions). It starts the same server.

## Do not install twice

If you use this plugin, do not also upload `pdfstruct-skill.zip`, do not keep a copy of the skill
in `%USERPROFILE%\.claude\skills\pdfstruct`, and remove a hand-made registration
(`claude mcp remove pdfstruct --scope user`). Otherwise Claude lists the skill and the five
tools twice.

## Disable or remove

Switch the plugin off or remove it in Claude's plugin settings (Claude Code:
`claude plugin disable pdfstruct`). Nothing on disk is deleted; PDFStruct itself stays in
`%USERPROFILE%\.local\pdfstruct`.
