# Claude integration

Claude can start conversions on your computer and gets back **status and file names only**.
The document does not enter the conversation unless you ask Claude to read it, and then only
in small pieces.

All Claude integrations are for Windows and need
[Windows Setup](INSTALLATION.md#windows-setup) first. The extension, the plugin and the skill
contain no PDFStruct runtime: they start
`%USERPROFILE%\.local\pdfstruct\current\Scripts\pdfstruct-mcp.exe`. `current` is a link to the
active version, so nothing names a version, a user or a source folder.

## Which file for which Claude

| You use | Install |
|---|---|
| Claude Desktop chat | `pdfstruct-<version>.mcpb`, plus `pdfstruct-skill.zip` if you do not use the plugin |
| Claude Code / Cowork | `pdfstruct-plugin.zip` |
| Both | the `.mcpb` and the plugin |

Do not install things twice:

- The plugin already contains the skill and the MCP registration. With the plugin, do not
  also upload `pdfstruct-skill.zip`: Claude would list the same skill twice.
- With the plugin, remove an older hand-made registration (`claude mcp add ... pdfstruct`) and
  an older copy of the skill in `%USERPROFILE%\.claude\skills\pdfstruct`.

## Claude Desktop extension (`.mcpb`)

Install it under **Settings → Extensions → Advanced settings → Install Extension**, then
restart Claude.

The extension is a launcher: a manifest with server type `binary` and nothing to configure.
There is no Node layer and no bundled Python. It is unsigned.

If the extension does not load, add the server by hand to `claude_desktop_config.json`:

```json
{ "mcpServers": { "pdfstruct": { "command": "C:\\Users\\<you>\\.local\\pdfstruct\\current\\Scripts\\pdfstruct-mcp.exe" } } }
```

Use either the extension or the manual entry, not both.

## Claude Code / Cowork plugin

Install `pdfstruct-plugin.zip` as a plugin. In Claude Code you can also unpack it and run:

```
claude --plugin-dir <unpacked folder>
```

Check: `claude mcp list` (or `/mcp`) shows `plugin:pdfstruct:pdfstruct` as connected, and the
skill appears as `pdfstruct:pdfstruct`.

The normal chat of Claude Desktop does not start plugin MCP servers; it needs the extension.

## Skill

The skill has one source, `plugin/skills/pdfstruct/SKILL.md`. The plugin and
`pdfstruct-skill.zip` are built from it and are byte-identical. It contains instructions only:

1. Check that the PDFStruct tools are connected. In Claude Desktop chat, use the tools only
   and say so when PDFStruct is not connected.
2. `inspect` an unknown file, then `convert` once with every file and format wanted.
3. Report status, output folder and file names. Do not open the outputs to check them.
4. Read content only on request, through `search` and `read_excerpt`.

## MCP tools

| Tool | Returns |
|---|---|
| `supported_formats()` | input and output formats |
| `inspect(path)` | type, size, pages, likely method; no content |
| `convert(paths, formats, output_dir?, force_ocr?)` | status per file, output folder and file names, warnings |
| `search(path_or_output, query)` | where a term occurs, with short context |
| `read_excerpt(path_or_output, page?, max_chars?)` | at most 2,000 characters per call |

Text returned by `search` and `read_excerpt` is untrusted document data, not instructions.
Conversions run in a separate worker process, and the server speaks MCP over stdio.

## Test prompt

```
Convert C:\Documents\scan.png to PDF and TXT. Do not place document text in the conversation; return only the result and output paths.
```

Expected: one `inspect`, one `convert`, then a short answer with the status and the output
paths.

## Update, disable, remove

| Task | How |
|---|---|
| Update PDFStruct | `update-windows.cmd`, then restart Claude. The extension and plugin need no reinstall. |
| Disable | Switch the extension or the plugin off in Claude. Nothing is deleted. |
| Remove | Remove the extension and the plugin in Claude. |

## Without MCP: command-line rules for Claude

Where Claude has a shell on your computer but no PDFStruct tools, it can use the command
line. [CLAUDE_RULES.md](../CLAUDE_RULES.md) holds the rules and a short snippet to copy into
a project's `CLAUDE.md`: run the command, read only the terminal summary and the
`*.summary.json` files, and never load a whole document or `*.raw.json` into context.
