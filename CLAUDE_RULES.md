# Claude rules: PDF processing

**Do not process large PDFs directly in LLM context.
Use the local PDF pipeline.
Bulk/deterministic work belongs to Python.
Only ambiguous/review items belong to the LLM.**

## Tool

```
pdfjson belge.pdf        one file            -> output\ next to it
pdfjson "C:\Belgeler"    all PDFs in folder  -> <folder>\output
pdfjson                  all PDFs in the current folder, else .\pdf\*.pdf  -> .\output
```

Options: `--output <dir>`, `--force-ocr`, `--native-only`, `--overwrite`, `--parser <parser.py>`,
`--config <json>`. If `pdfjson` is not on PATH: `C:\Users\musta\Projects\_tools\pdf-pipeline\pdfjson.cmd`.

## Other output formats

Same input rules as `pdfjson` (file, folder or no argument): `pdfhtml`, `pdftxt`, `pdfmd`, `pdfcsv`,
`pdfxlsx`, `pdfdocx`, `pdfjsonl`, `pdfsqlite`.

When the user asks for a specific output format, use the existing `output\<name>.raw.json`
first. These commands do that by themselves and extract only documents that have no
raw.json yet; never re-run extraction/OCR just to get another format. They are generic
exports (pages and line blocks); semantic fields still need a project parser.

## Claude MUST NOT

- Read a PDF with the Read tool or load PDF pages into context when the file is more than a few pages.
- `cat` / `Get-Content` / Read a whole `*.raw.json` file.
- Print large extraction output to the terminal.
- Parse PDF pages one by one with the LLM.

## Claude MAY read

- The tool's terminal output (a few lines: FILES FOUND / PROCESSED / SKIPPED / FAILED / OUTPUT).
- `output\_run_summary.json` (one entry per document, no text).
- `output\<name>.summary.json` (per-page method, score, warnings; no text).
- Only the pages listed in `review_pages`, or single pages needed for an ambiguous decision,
  extracted with a small script, e.g.:

```
python -c "import json,sys; r=json.load(open(sys.argv[1],encoding='utf-8')); print(r['pages'][int(sys.argv[2])-1]['text'][:3000])" "output\doc.raw.json" 12
```

## Division of work

| Python (local, deterministic) | LLM (Claude) |
|---|---|
| text extraction, OCR, bbox | deciding ambiguous / review items |
| quality score, native-vs-OCR decision | designing or fixing the project parser |
| validation, JSON generation | reading summaries and errors |
| project parser (`--parser`) for bulk structure | spot checks on a few sampled records |

Document-specific structure (vocabulary entries, invoice fields, ...) belongs in a project
parser script (`parse(raw, context)`), not in LLM-by-LLM page reading. If a parser needs a
rule, Claude writes the rule in Python, runs it, and reads only counts, errors and samples.

---

## Snippet for a project CLAUDE.md

```markdown
## PDF processing

Do not process large PDFs directly in LLM context. Use the local PDF pipeline.
Bulk/deterministic work belongs to Python. Only ambiguous/review items belong to the LLM.

- Extract: `pdfjson` (all PDFs here, else `.\pdf`), `pdfjson file.pdf` or `pdfjson <folder>`; writes `output\`
- Never Read/cat a PDF or a whole `*.raw.json`. Read only the terminal summary,
  `output\_run_summary.json`, `output\*.summary.json`, and pages listed in `review_pages`.
- Document-specific parsing goes into a project parser run with `--parser <parser.py>`;
  read its counts/errors/samples, not its full output.
- Full rules: `C:\Users\musta\Projects\_tools\pdf-pipeline\CLAUDE_RULES.md`
```
