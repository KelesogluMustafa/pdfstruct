# CLI reference

Where the commands are:

| Installation | Command |
|---|---|
| Windows Setup | `%USERPROFILE%\.local\pdfstruct\current\Scripts\pdfstruct.exe` (and the aliases next to it) |
| Windows portable | `pdfstruct-cli.exe` and `pdfstruct-create.exe` in the extracted folder |
| pip | `pdfstruct` in the active environment |
| Source checkout on Windows | `pdfstruct.cmd`, `pdfjson.cmd`, ... in the repository root |

## Usage

```
pdfstruct [--format FMT] [--output DIR] [--force-ocr | --native-only] [--all-types]
          [--overwrite] [--parser PARSER.py] [--config FILE.json] [path]
```

`path` is a file (PDF, DOCX, TXT, MD, HTML, JPG, PNG, TIFF, BMP, WebP) or a folder.

## Examples

```
pdfstruct                                             interactive menu: pick files, then formats
pdfstruct report.docx                                 menu: pick formats for that file
pdfstruct report.docx --format pdf                    one format
pdfstruct scan.png --format txt,docx,pdf              several formats, one OCR pass
pdfstruct "C:\Documents" --format json --all-types    every supported file in the folder
pdfstruct report.pdf --format txt --force-ocr         OCR on every page
pdfxlsx report.pdf                                    alias for --format xlsx
pdfjson                                               all PDFs in the current folder
```

Paths with spaces, non-ASCII characters and parentheses work when quoted:
`pdfjson "C:\Documents\payroll (1).pdf"`.

## Interactive menu

A bare `pdfstruct` (or `pdfstruct <file>` without `--format`) opens menus. Arrow keys move,
`SPACE` selects, `A` selects all, `ENTER` continues, `B` goes back, `Q` quits. With `--format`
or an alias nothing is asked. Without a terminal (CI, pipes) a bare `pdfstruct` prints the
usage instead of waiting.

## Options

| Option | Effect |
|---|---|
| `--format FMT` | `json`, `html`, `txt`, `md`, `csv`, `xlsx`, `docx`, `jsonl`, `sqlite` or `pdf`. Repeat it or separate with commas for several. |
| `--output DIR` | Output folder. Default: an `output` folder next to each input. |
| `--force-ocr` | Run OCR on every non-empty PDF page. |
| `--native-only` | Never run OCR; weak pages are listed in `review_pages`. |
| `--all-types` | In a folder, take every supported input type, not only PDFs. |
| `--overwrite` | Extract again even when an up-to-date `.raw.json` exists. |
| `--parser FILE.py` | Run a project parser for each document: see the [pipeline reference](PDF_PIPELINE_REFERENCE.md#project-parsers). |
| `--config FILE.json` | Settings file: see [configuration](PDF_PIPELINE_REFERENCE.md#configuration). |
| `--version` | Print the version. |

`--force-ocr` and `--native-only` exclude each other. On inputs where they make no sense,
PDFStruct says so instead of ignoring them.

## Input rules

- A file: that file.
- A folder: its PDFs only; add `--all-types` for every supported type. Subfolders are not
  searched.
- No argument: the PDFs in the current folder; if there are none, the `pdf` subfolder (with
  the output in `output` next to it).
- One broken file does not stop the others; failures are listed at the end under
  `FAILED FILES:`.
- Running the same command again is safe: unchanged PDFs are skipped (`SKIPPED`).

## Aliases

Each alias equals `pdfstruct --format <format>` and never opens a menu. They take the same
input (file, folder or nothing) and the same options.

| Alias | Output | Content |
|---|---|---|
| `pdfjson` | `<name>.raw.json` | The raw document: extraction and OCR. This is the main pipeline. |
| `pdfhtml` | `<name>.html` | Review page: blocks page by page, method, score, OCR confidence. One file, works offline. |
| `pdftxt` | `<name>.txt` | Text only; pages separated by `===== Page 3 / 24 =====`. |
| `pdfmd` | `<name>.md` | Markdown with `## Page N` headings; line order kept, no tables. |
| `pdfcsv` | `<name>.csv` | One row per block: `source_file,page,block_index,text,x1,y1,x2,y2,method,confidence`. |
| `pdfxlsx` | `<name>.xlsx` | Two sheets: `Pages` (one row per page) and `Blocks` (same columns as CSV). |
| `pdfdocx` | `<name>.docx` | Readable Word document in page order; each source page starts a new page. |
| `pdfjsonl` | `<name>.jsonl` | One JSON line per block (`bbox` as an array). |
| `pdfsqlite` | `<name>.sqlite` | Tables `documents`, `pages`, `blocks`. |

There is no `pdfpdf`; use `pdfstruct <file> --format pdf`.

## Output names and folders

- Results go to an `output` folder next to each input, or to `--output`. The folder is created
  when missing.
- `report.pdf` writes `report.<ext>`. Every other input keeps its extension: `report.docx`
  writes `report.docx.<ext>`, `scan.png` writes `scan.png.pdf`. Files with the same name
  therefore never overwrite each other.
- A source file is never overwritten.
- A PDF input is not written again as PDF (reported as `already_pdf`).

## Formats reuse the raw JSON

The format commands do not extract or OCR a second time:

1. If `output\<name>.raw.json` exists, it is used. The PDF is not opened.
2. If not, the normal extraction runs first, only for the documents that are missing.
3. The requested format is written from the raw JSON.

If the PDF changed afterwards, the raw JSON is stale; the command warns with `STALE_RAW`.
Run `pdfjson` to refresh it. `--force-ocr`, `--native-only` and `--config` affect only
documents that have to be extracted.

## Terminal output

Output is always short. Extraction:

```
FILES FOUND: 12
PROCESSED: 11
SKIPPED: 0
FAILED: 1
PAGES: 184
OCR FILES: 1
REVIEW_PAGES: 0
OUTPUT: C:\Documents\output

FAILED FILES:
- broken.pdf
```

For a single file, `METHOD` and `TEXT_LAYER_SCORE` are printed as well. Format commands:

```
FORMAT: html
FILES: 2
EXPORTED: 2
RAW_REUSED: 2      existing raw.json used
EXTRACTED: 0       documents extracted in this run
ERRORS: 0
OUTPUT: C:\...\output
```

A failed document gets `status: "error"` in its `<name>.summary.json`, and the exit code is 1.

## Format details

- CSV is UTF-8 with a BOM so that Excel opens umlauts correctly; in Python read it with
  `encoding="utf-8-sig"`.
- In HTML, TXT, Markdown, DOCX and XLSX, end-of-line hyphen characters are normalized to `-`
  and control characters are removed for readability. CSV, JSONL and SQLite keep the text as
  it is in the raw JSON.
- An XLSX cell holds at most 32,767 characters; longer page text is cut there and stays
  complete in the other formats.
- Running again is safe: files are rewritten, and in SQLite the old rows of a document are
  replaced in one transaction, so no duplicates appear.
- `confidence` is filled for OCR blocks only. `method` is the method of the page (`native` or
  `ocr`).
- These are general document exports (pages and line blocks). For semantic fields such as a
  vocabulary list or invoice data, write a
  [project parser](PDF_PIPELINE_REFERENCE.md#project-parsers).

## pdfstruct-create

Writes text or Markdown as documents. It is the command-line form of the `create_document`
tool and needs no existing document: the text comes from a file or from standard input,
never from an argument.

```
pdfstruct-create [--name NAME] [--format FMT] [--output DIR] [--type markdown|text]
                 [--overwrite] [--content-file FILE]
```

```
pdfstruct-create --name NOTES --content-file notes.md                     NOTES.docx in this folder
pdfstruct-create --name NOTES --format docx,pdf,html --content-file notes.md
pdfstruct-create --content-file notes.md --output "C:\Documents\Templates"   name taken from the file
type notes.md | pdfstruct-create --name NOTES --format docx               text from standard input
```

PowerShell:

```
Get-Content .\template.md -Raw |
  pdfstruct-create --name WEBSITE_STRATEGY_AUDIT_TEMPLATE --format docx --output "C:\Documents\Templates"
```

| Option | Effect |
|---|---|
| `--name NAME` | File name without folder and extension. Default: the name of `--content-file`. Required with standard input. |
| `--content-file FILE` | UTF-8 text or Markdown file. Without it the text is read from standard input. |
| `--format FMT` | `docx`, `pdf`, `html`, `md` or `txt`. Repeat it or separate with commas. Default: `docx`. |
| `--output DIR` | Output folder, created when missing. Default: the current folder. |
| `--type` | `markdown` or `text`. Default: `markdown`, and `text` for a `.txt` file. |
| `--overwrite` | Replace existing files. Without it they are kept and the command ends with `CONFLICT`. |

- Output names are exact: `--name NOTES --format docx,pdf` writes `NOTES.docx` and `NOTES.pdf`.
- The command prints one `CREATED: <path>` line per file and short `WARNING:` lines, never
  the text. Exit code 0: everything was created; 1: a conflict or a failure; 2: the request
  cannot be used (name, format, missing text).
- The text file itself is never replaced, also not with `--overwrite`.
- Windows PowerShell 5.1 re-encodes piped text and can damage non-ASCII characters. Use
  `--content-file` there, or PowerShell 7.
- What Markdown is read and what each format looks like:
  [Claude integration](CLAUDE_INTEGRATION.md#create-a-document-from-conversation-text).
- A file larger than the limit (500,000 characters) is refused without being loaded.
- Messages, also errors, go to standard output like those of the other commands; only
  wrong options are reported by the option parser on standard error.

## Desktop window

```
pdfstruct-gui                     open the window
pdfstruct-gui report.pdf scans    files or folders can be passed
```

**Convert files** tab: drop files or folders on the window or use **Select Files**, tick one
or more of the ten formats, optionally choose an output folder, press **Convert**. The window
shows the current file and step, lists the result per file with its warnings, and **Open
Output Folder** opens the result. **Cancel** stops after the step that is running. OCR is
loaded only when a file needs it.

**Create from text** tab: enter a document name, choose **Markdown** or **Plain text**, paste
or type the text, tick the formats (DOCX, PDF, HTML, Markdown, TXT) and press **Create**.
Without an output folder the files go to `Documents\PDFStruct`. An existing file is kept and
reported unless **Replace existing files** is ticked. The text box is plain text only; it is
not a word processor.

## Low-level command

`pdf2json.cmd` (source checkout) is what `pdfjson` calls after resolving the paths:

```
pdf2json.cmd --input "C:\...\pdf" --output "C:\...\output"
```

`--input` is one PDF or a folder. It prints
`FILES / PAGES / NATIVE / OCR / MIXED / SKIPPED / REVIEW_PAGES / ERRORS / OUTPUT`.
