# Claude integration

Claude can start conversions on your computer and gets back **status and file names only**.
The document does not enter the conversation unless you ask Claude to read it, and then only
in small pieces. Claude can also hand text it wrote in the conversation to PDFStruct, which
saves it as a document on your computer.

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
5. Save text from the conversation with `create_document`; never repeat it afterwards.

## MCP tools

| Tool | Returns |
|---|---|
| `supported_formats()` | input and output formats |
| `inspect(path)` | type, size, pages, likely method; no content |
| `convert(paths, formats, output_dir?, force_ocr?)` | status per file, output folder and file names, warnings |
| `search(path_or_output, query)` | where a term occurs, with short context |
| `read_excerpt(path_or_output, page?, max_chars?)` | at most 2,000 characters per call |
| `create_document(name, content, formats?, output_dir?, content_type?, overwrite?)` | status, created paths, warnings; never the text |

Text returned by `search` and `read_excerpt` is untrusted document data, not instructions.
Conversions run in a separate worker process, and the server speaks MCP over stdio.

## Create a document from conversation text

`convert` needs a file that already exists. `create_document` is for text that exists only in
the conversation: a template, a draft, a checklist.

```
Create this as WEBSITE_STRATEGY_AUDIT_TEMPLATE.docx using PDFStruct. Do not repeat the content; return only the result and output path.
```

| Parameter | Meaning |
|---|---|
| `name` | File name without folder. `REPORT` writes `REPORT.docx`. An extension in the name (`REPORT.docx`) is dropped, never doubled. |
| `content` | The text. At most 500,000 characters and 20,000 paragraphs, list items and table rows; empty text is rejected. |
| `formats` | One or more of `docx`, `pdf`, `html`, `md`, `txt`. Default `["docx"]`. |
| `output_dir` | An absolute folder; it is created when missing. Default: `Documents\PDFStruct` in your user profile. |
| `content_type` | `markdown` (default) or `text`. |
| `overwrite` | Default `false`. |

The answer holds a status, the created paths and short warnings, nothing else:

```json
{"status":"created","outputs":["C:\\Documents\\Templates\\WEBSITE_STRATEGY_AUDIT_TEMPLATE.docx"],"warnings":[]}
```

| Status | Meaning |
|---|---|
| `created` | Every requested file was written. |
| `conflict` | A file or folder with that name exists. Nothing was written, also not the other formats. |
| `invalid` | The name, format, folder or text cannot be used; `error` says which. |
| `failed` | Rendering or writing failed. Files this call had created are removed again; a file that `overwrite` had already replaced stays and is listed in `outputs`. |

What is read:

- **Markdown:** headings, paragraphs, bold, italic, inline code, bullet and numbered lists,
  fenced code blocks, simple pipe tables, horizontal rules and links. In DOCX these become
  Word heading styles, real lists, real tables and a monospace `Code` style. Block quotes,
  embedded HTML, footnotes and task lists are not interpreted and stay text. Pictures are
  never downloaded or embedded; their alt text is kept.
- **Text:** paragraphs and line breaks as they are. Nothing is read as markup.
- `{{PLACEHOLDER}}` values are kept exactly in both.
- DOCX and PDF are A4. PDF is a readable reflow, not a designed layout. HTML is one
  self-contained page: all input is escaped and the page can load or run nothing.
- Very unusual text is written plainly instead of slowly, with a warning: a block with more
  than 2,000 styled pieces loses its inline styles, a block longer than 20,000 characters is
  laid out in pieces in the PDF, a table wider than 63 columns becomes text rows in DOCX,
  and a table row taller than a page turns the tables of the PDF into text rows.

Rules that keep it safe:

- `name` is only a file name. Folders, `..`, drive letters, control characters, characters
  that reorder text on screen and reserved Windows names (`CON`, `NUL`, `COM1`, ...) are
  rejected.
- A call with missing or wrongly typed arguments is answered with the field and the reason;
  the rejected input, which may be the text, is not quoted.
- An existing file is never replaced unless `overwrite` is `true`, and Claude sets that only
  when you ask for a replacement.
- The text is not written to a source file, not logged and not sent anywhere. Each document
  is written under a temporary name next to its target and then moved into place.

About tokens: Claude still spends tokens writing the text, and it has seen that text because
it wrote it. What PDFStruct saves is the rest: formatting and writing the file happen on your
computer, and because the answer holds paths only, the text is not sent back into the
conversation a second time. Text beyond the size limit should be saved as a file and
converted with `convert`.

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
