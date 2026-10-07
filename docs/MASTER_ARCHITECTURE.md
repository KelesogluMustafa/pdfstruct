# PDFStruct — Master Architecture & Development Constitution

> **Status:** Active project source of truth  
> **Current public release:** v0.1.0  
> **Project:** PDFStruct  
> **Repository:** https://github.com/KelesogluMustafa/pdfstruct  
> **Website:** https://mustafakelesoglu.de/pdfstruct  
> **License:** MIT  
> **Primary rule:** Keep PDFStruct simple for users, modular for developers, local-first, and inexpensive to maintain.

---

## 1. Why this document exists

This file is the **master architectural source of truth** for PDFStruct.

It is not a one-time prompt and it is not a task checklist. It defines:

- what PDFStruct is,
- what it should become,
- what must not be broken,
- the architecture all future features must follow,
- the release roadmap,
- the rules for CLI, GUI, OCR, inputs and exports,
- the rules for testing and packaging,
- the rules an AI coding assistant must follow,
- the low-token workflow for future development.

Future work should use this document as context and then receive a **short, task-specific prompt**.

Do not rewrite or reread the whole repository for every task.

---

# 2. Product definition

PDFStruct is a **free, open-source, local-first document extraction and conversion tool**.

Its core job is:

```text
Input document
      ↓
Input adapter
      ↓
Native extraction where possible
      ↓
OCR only when required
      ↓
Normalized structured document data
      ↓
Export adapters
      ↓
JSON / HTML / TXT / Markdown / CSV / XLSX / DOCX / JSONL / SQLite / future formats
```

PDFStruct should remain useful to both:

1. **normal users**
   - GUI
   - drag & drop
   - simple selections
   - installers
   - no Python knowledge required

2. **technical users**
   - CLI
   - scripting
   - automation
   - deterministic commands
   - reusable Python core

---

# 3. Non-negotiable product principles

These rules are permanent unless the project owner explicitly changes them.

## 3.1 Free and open source

- Core functionality is free.
- MIT license.
- No Pro/Premium tier.
- No artificial usage quotas.
- No feature locking behind payment.
- Donations/support may exist, but never unlock core features.

## 3.2 Local-first privacy

By default:

- documents are processed on the user's own computer,
- no document upload to PDFStruct servers,
- no mandatory account,
- no telemetry by default,
- no hidden analytics,
- no cloud dependency for normal conversion.

Internet may be required for a legitimate one-time dependency/model download such as OCR models.

## 3.3 One core, many interfaces

There must be only **one conversion/extraction core**.

```text
                         ┌─ CLI
                         │
Input → PDFStruct Core ──┼─ Desktop GUI
                         │
                         └─ future API / integrations
```

Never create separate conversion logic for CLI and GUI.

## 3.4 Simple user experience

Users should not need to understand:

- native PDF text layers,
- OCR engines,
- Python environments,
- PaddleOCR internals,
- model paths,
- CUDA,
- internal schemas.

PDFStruct should choose sensible defaults automatically.

## 3.5 Low maintenance

Prefer:

- standard libraries,
- small mature dependencies,
- stable interfaces,
- reusable modules,
- additive schema evolution,
- one implementation of each behavior.

Avoid:

- duplicate package ecosystems,
- unnecessary frontend frameworks,
- unnecessary services,
- premature microservices,
- complex installers unless needed.

---

# 4. Current stable baseline — v0.1.0

v0.1.0 is the first public baseline and should remain reproducible.

## 4.1 Current capabilities

### Input

- PDF

### Extraction

- native PDF text extraction
- automatic text-quality evaluation
- automatic OCR fallback
- forced OCR option
- page/block bounding boxes
- OCR confidence
- native / OCR / mixed document method reporting

### OCR

- PaddleOCR 3.7
- PaddlePaddle CPU
- lazy initialization
- models are not stored in the repository
- model cache under the user's PDFStruct area
- no HermesOCR dependency

### Export formats

- JSON
- HTML
- TXT
- Markdown
- CSV
- XLSX
- DOCX
- JSONL
- SQLite

### CLI

Main command:

```bash
pdfstruct
```

Interactive mode supports:

- current-folder PDF discovery,
- multiple PDF selection,
- multiple output-format selection,
- select all,
- back,
- quit,
- conversion summary.

Scriptable commands remain available:

```bash
pdfstruct document.pdf --format xlsx
pdfjson document.pdf
pdfhtml document.pdf
pdftxt document.pdf
pdfmd document.pdf
pdfcsv document.pdf
pdfxlsx document.pdf
pdfdocx document.pdf
pdfjsonl document.pdf
pdfsqlite document.pdf
```

### Verified release platforms

Full native + CPU OCR verification exists for:

- Windows x86_64
- Linux x86_64
- macOS Apple Silicon

Do not advertise unsupported combinations as fully supported until actually verified.

## 4.2 Distribution

Public source:

```text
https://github.com/KelesogluMustafa/pdfstruct
```

Latest release:

```text
https://github.com/KelesogluMustafa/pdfstruct/releases/latest
```

Project page:

```text
https://mustafakelesoglu.de/pdfstruct
```

Hostinger is the **presentation layer**, not the binary/package store.

Release artifacts stay on GitHub Releases.

---

# 5. Architectural model

PDFStruct should gradually evolve toward the following structure:

```text
pdfstruct/
│
├── input/
│   ├── pdf.py
│   ├── docx.py          # future
│   ├── image.py         # future
│   ├── html.py          # future
│   ├── markdown.py      # future
│   └── text.py          # future
│
├── extraction/
│   ├── native.py
│   ├── quality.py
│   ├── ocr.py
│   ├── layout.py        # future
│   ├── tables.py        # future
│   └── images.py        # future
│
├── model/
│   └── document.py
│
├── export/
│   ├── json.py
│   ├── html.py
│   ├── txt.py
│   ├── markdown.py
│   ├── csv.py
│   ├── xlsx.py
│   ├── docx.py
│   ├── jsonl.py
│   ├── sqlite.py
│   └── pdf.py           # only when meaningful
│
├── cli/
│   ├── main.py
│   └── interactive.py
│
├── gui/                 # v0.2
│   ├── app.py
│   ├── window.py
│   ├── workers.py
│   └── widgets/
│
└── core/
    ├── pipeline.py
    ├── batch.py
    ├── progress.py
    └── errors.py
```

This is a target organization, not permission to refactor everything immediately.

**Rule:** restructure only when a real feature requires it.

---

# 6. Normalized document model

Future multi-input support requires a common intermediate representation.

The normalized model should be able to represent, as needed:

```text
Document
├── metadata
├── pages
│   ├── dimensions
│   ├── text blocks
│   ├── bounding boxes
│   ├── images
│   ├── tables
│   └── annotations
├── document-level paragraphs
├── headings
├── lists
├── tables
├── images
└── source information
```

Important rules:

- Preserve current raw JSON compatibility where practical.
- Prefer additive schema changes.
- Do not break old output merely for architectural cleanliness.
- Store source provenance when available.
- Do not invent structure that cannot be justified from the source.
- Exact visual reconstruction and semantic extraction are different problems.

---

# 7. Input adapter strategy

New input formats should enter through adapters.

```text
PDF ─────┐
DOCX ────┤
Image ───┤
HTML ────┤──→ Normalized Document Model → Exporters
MD ──────┤
TXT ─────┘
```

Each input adapter is responsible only for converting its source format into the normalized model.

It must not contain format-specific export logic.

---

# 8. PDF input

PDF remains a first-class input.

Pipeline:

```text
PDF
↓
native extraction
↓
quality evaluation
├── sufficient → native result
└── insufficient → OCR
↓
normalized structure
```

Future PDF improvements may include:

- better multi-column reading order,
- header/footer detection,
- table extraction,
- image extraction,
- footnotes,
- page-region selection,
- embedded metadata,
- annotations.

OCR should remain fallback, not the first choice when a usable text layer exists.

---

# 9. DOCX input — planned

DOCX is a natural next document input because it already contains structured XML.

Likely extraction targets:

- paragraphs,
- headings,
- lists,
- tables,
- basic styles,
- images,
- headers/footers,
- document properties.

Likely conversions:

```text
DOCX → JSON
DOCX → HTML
DOCX → TXT
DOCX → Markdown
DOCX → CSV
DOCX → XLSX
DOCX → SQLite
```

DOCX → PDF is a different class of problem because accurate layout rendering may require a real office/rendering engine.

Do not promise pixel-identical Word rendering unless a tested renderer exists.

---

# 10. Image input — planned

Candidate formats:

- PNG
- JPG/JPEG
- TIFF
- possibly WEBP

Pipeline:

```text
Image
↓
OCR
↓
layout/text blocks
↓
normalized document
↓
exports
```

Image input should reuse the existing OCR layer.

Do not build a separate OCR engine.

---

# 11. Future PDF utilities

Useful local utilities may include:

- merge PDFs,
- split PDFs,
- select pages,
- remove pages,
- rotate pages,
- reorder pages,
- extract pages,
- PDF → images,
- images → PDF.

These utilities should remain modular.

They should not force unrelated extraction code to become more complex.

---

# 12. Advanced extraction roadmap

High-value future extraction features:

## 12.1 Tables

Priority feature.

Goals:

- detect table regions,
- preserve row/column structure,
- export directly to:
  - XLSX
  - CSV
  - JSON
  - SQLite

Avoid pretending aligned text is a real table without sufficient evidence.

## 12.2 Images

Support extraction of embedded images.

Possible output:

```text
output/
├── document.json
├── images/
│   ├── image-001.png
│   └── image-002.jpg
└── tables/
    └── table-001.xlsx
```

## 12.3 Structural elements

Gradually improve:

- heading detection,
- paragraphs,
- lists,
- header/footer separation,
- footnotes,
- reading order,
- multi-column pages.

---

# 13. Selective extraction

Future GUI/CLI may allow:

```text
Extract:
[x] Text
[x] Tables
[ ] Images
[x] Metadata
```

This should call the same extraction pipeline with feature flags.

It should not create parallel engines.

---

# 14. Desktop GUI — v0.2 target

The desktop GUI is the next major planned user-facing feature.

Preferred toolkit:

```text
PySide6
```

Reason:

- Python-native integration,
- Windows support,
- macOS support,
- Linux compatibility,
- native desktop feel,
- drag & drop,
- HiDPI support,
- avoids browser/server architecture for a local utility.

PySide6 is a preference, not an absolute rule. If a better low-maintenance cross-platform option is clearly superior, evaluate it first.

## 14.1 GUI minimum scope

v0.2 should include:

- drag & drop PDFs,
- Select Files,
- multiple files,
- remove file from queue,
- select one or more output formats,
- Select All,
- output directory selector,
- Convert button,
- progress bar,
- current file,
- current phase:
  - native extraction
  - OCR
  - export
- cancel,
- success/failure summary,
- Open Output Folder.

## 14.2 GUI must not duplicate the core

Correct:

```text
GUI
↓
PDFStruct Core
↓
existing extraction/export functions
```

Wrong:

```text
GUI → new PDF converter
CLI → old PDF converter
```

## 14.3 Responsiveness

Long tasks must not freeze the window.

Use workers/threads/processes as appropriate.

GUI updates should be event-driven.

## 14.4 Theme

- clean,
- minimal,
- system-aware light/dark where practical,
- no unnecessary visual effects,
- HiDPI/Retina aware,
- Windows and macOS friendly.

---

# 15. Desktop packaging — v0.2 target

Normal users should not require Python.

## Windows

Desired release artifacts:

```text
PDFStruct-Setup-0.2.0.exe
PDFStruct-Portable-0.2.0.zip
```

Goals:

- normal installer,
- Start Menu entry,
- optional desktop shortcut,
- uninstall support,
- self-contained runtime,
- no separate Python install.

## macOS

Desired release artifact:

```text
PDFStruct-0.2.0.dmg
```

Goals:

- `.app` bundle,
- drag to Applications,
- no Python installation required,
- Apple Silicon as minimum verified target.

Intel macOS support must not be promised unless build/test evidence exists.

## Packaging rule

Use a practical packager such as PyInstaller only after verifying:

- Paddle/PaddleOCR bundling,
- Qt plugin bundling,
- model behavior,
- binary size,
- startup behavior,
- license obligations.

Do not hardcode the packager choice before a proof-of-build.

---

# 16. Preview — future

A future desktop mode may show:

```text
┌──────────────────────┬──────────────────────┐
│ Original document    │ Extracted structure  │
│                      │                      │
│ Page preview         │ text / tables / etc │
└──────────────────────┴──────────────────────┘
```

Possible uses:

- inspect extraction,
- verify OCR,
- choose pages,
- choose regions,
- selective export.

This is useful but not required for initial GUI v0.2.

---

# 17. Document comparison — future

Potential feature:

```text
document-v1.pdf
document-v2.pdf
        ↓
normalized extraction
        ↓
structural/text comparison
        ↓
changes
```

Possible results:

- additions,
- deletions,
- changed text,
- changed numbers,
- changed table cells.

Do not implement until normalized structure is mature enough.

---

# 18. Optional local AI — future, not core

Potential later capability:

```text
Document
↓
PDFStruct extraction
↓
optional local LLM
↓
summary / classification / field extraction
```

Rules:

- optional,
- local-first,
- never required for core conversion,
- no forced cloud API,
- no hidden document upload,
- no large AI dependency in default installation unless explicitly justified.

AI is an extension, not the conversion engine.

---

# 19. OCR architecture

Current strategy:

- lazy OCR import,
- CPU default,
- models downloaded only when OCR is actually needed,
- model cache reused,
- native processing does not initialize OCR.

Keep this behavior.

Future improvements may include:

- language selection,
- automatic language hints,
- optional GPU acceleration,
- model quality profiles.

Possible UX later:

```text
OCR:
Auto
Deutsch
English
Türkçe
French
...
```

But do not force users to choose a language when auto/default is adequate.

---

# 20. Performance rules

PDFStruct should optimize for:

1. avoid repeated extraction,
2. reuse raw/normalized data,
3. initialize OCR only when required,
4. process one input once and generate many exports from the same extracted data,
5. avoid loading an entire large document into memory unnecessarily,
6. process page-by-page where appropriate,
7. keep GUI responsive.

Example:

```text
3 PDFs × 5 export formats
```

must mean:

```text
3 extraction passes
```

not:

```text
15 extraction passes
```

---

# 21. Error handling

Errors should be:

- concise,
- actionable,
- non-destructive.

Batch rules:

- one broken file should not necessarily stop the whole batch,
- failures should be reported per file,
- successful outputs should remain,
- final summary should show:
  - succeeded,
  - failed,
  - skipped/review-required when relevant.

Never silently hide real failures.

---

# 22. Security and privacy

Public-release audit should check:

- secrets,
- tokens,
- `.env`,
- credentials,
- certificates,
- API keys,
- personal absolute paths,
- local caches,
- model files,
- user documents,
- outputs,
- backups.

Do not commit user documents.

Do not commit OCR models.

Do not log extracted personal document content unless a debug mode explicitly requires it.

---

# 23. Testing strategy

Tests should be layered.

## Unit tests

For:

- parsing,
- selection,
- format logic,
- schema handling,
- path resolution,
- config,
- stale-data detection,
- error handling.

## Integration tests

For:

- PDF native extraction,
- OCR,
- export formats,
- batch behavior,
- CLI.

## GUI tests

Keep focused:

- state transitions,
- file queue,
- selected formats,
- worker behavior,
- cancel,
- output summary.

Avoid enormous screenshot-driven test suites.

## Cross-platform CI

At least:

- Windows x86_64
- Linux x86_64
- macOS Apple Silicon

Only advertise support actually verified by CI or a real test machine.

---

# 24. Release policy

Use semantic versioning:

```text
MAJOR.MINOR.PATCH
```

Examples:

```text
0.1.0  initial public CLI
0.1.1  bugfix
0.2.0  desktop GUI
0.3.0  new major input support
1.0.0  stable public API/CLI contract
```

Do not bump versions merely because development started.

A release should occur only after release-critical tests are green.

Release artifacts should remain on GitHub Releases.

Website download links should point to:

```text
https://github.com/KelesogluMustafa/pdfstruct/releases/latest
```

so the website does not require editing for each version.

---

# 25. Roadmap

This roadmap is directional, not a command to implement everything now.

## v0.1 — complete

- PDF input
- native extraction
- automatic OCR
- nine exports
- interactive CLI
- batch handling
- cross-platform CI
- public GitHub release
- project website

## v0.2 — Desktop GUI

Primary target:

- Windows GUI
- macOS GUI
- drag & drop
- multi-file
- multi-format
- progress
- cancel
- output folder
- open output folder
- Setup.exe
- portable Windows package if practical
- macOS `.app` / `.dmg`

Owner decision (2026-10-07): v0.2 also carries the shared conversion service, the first
non-PDF inputs, PDF output, the local MCP server and the Agent Skill. See section 35.
Installers (Setup.exe, DMG, signing) stay optional proofs and must not block the core.

## v0.3 — More inputs

DOCX, image, TXT, Markdown and HTML inputs moved into v0.2 (section 35).

Remaining candidates: CSV/XLSX input, RTF/ODT, EPUB, HEIC. Reuse the common document model.

## v0.4 — PDF utilities

- merge
- split
- rotate
- page selection
- page extraction
- PDF ↔ image utilities

## v0.5 — Advanced structure

- improved tables
- image extraction
- headings/lists
- layout
- multi-column reading
- header/footer

## v0.6 — Preview & selective extraction

- document preview
- extracted-data preview
- select text/tables/images/metadata
- page/region selection where useful

## v0.7 — Comparison

- document diff
- changed text
- changed numbers
- table changes

## v0.8+ — Optional intelligence

- optional local AI
- summary
- classification
- structured field extraction

## v1.0

Only after:

- architecture stabilizes,
- CLI/API contracts stabilize,
- cross-platform installation is dependable,
- backward compatibility policy is clear.

---

# 26. What not to build yet

Unless explicitly requested, do not add:

- user accounts,
- hosted document storage,
- SaaS backend,
- cloud database,
- mandatory cloud API,
- payments,
- premium tier,
- analytics platform,
- Electron frontend,
- REST API merely because it is possible,
- Docker merely because it is possible,
- browser app duplicating desktop functionality,
- multiple OCR engines without a demonstrated need.

Every dependency and subsystem must solve a real user problem.

---

# 27. Repository rules

Keep the repository clean.

Never commit:

```text
.venv/
__pycache__/
OCR model caches
user PDFs
output/
*.raw.json generated from private documents
.env
credentials
private keys
local path backup files
temporary installers
```

Generated release artifacts should be attached to releases as appropriate, not casually committed.

---

# 28. Documentation rules

Keep documentation separated by purpose.

Recommended:

```text
README.md
    user-facing quick start

docs/MASTER_ARCHITECTURE.md
    this file / source of truth

CHANGELOG.md
    release history

THIRD_PARTY_NOTICES.md
    dependency notices

CONTRIBUTING.md
    only when external contributors need it
```

README should stay short.

Do not turn README into the entire architecture book.

---

# 29. AI / Claude development contract

This section exists specifically to minimize token usage, context pollution and unnecessary code churn.

## 29.1 Read order

For a new task:

1. Read this master architecture document.
2. Read only the files directly relevant to the task.
3. Check tests related to the task.
4. Make the smallest safe change.
5. Run deterministic local tests.
6. Report concise results.

Do not reread the entire repository unless necessary.

## 29.2 Token rule

**Bulk/deterministic work = local code/tools.  
Ambiguous/semantic decisions = LLM.**

Examples:

Use local Python for:

- file discovery,
- checksums,
- dependency inspection,
- test runs,
- PDF extraction,
- OCR,
- schema validation,
- large batch transformations,
- fixture generation.

Use the LLM for:

- architecture decisions,
- ambiguous parser logic,
- UX decisions,
- code review,
- error interpretation,
- naming,
- prioritization.

## 29.3 Never feed large data unnecessarily

Do not place into LLM context unless required:

- entire PDFs,
- OCR models,
- full raw JSON from large documents,
- package caches,
- large generated outputs,
- huge test logs,
- whole dependency trees.

Summarize local results instead.

## 29.4 Scope control

Each task should have one primary goal.

Example:

Good:

```text
Add Desktop GUI file selection and format selection.
Do not add DOCX support.
Do not change OCR.
Do not change release packaging.
```

Bad:

```text
Build GUI, DOCX support, AI, Docker, API and website at once.
```

## 29.5 Preserve working behavior

Before a change:

- verify working tree,
- identify baseline,
- run relevant tests.

After a change:

- run targeted tests,
- run broader CI only when appropriate,
- do not silently change unrelated behavior.

## 29.6 No speculative refactors

Do not refactor working code merely to make it "cleaner" unless:

- the task requires it,
- duplication is causing real maintenance cost,
- testability requires it,
- architecture would otherwise become unsafe.

---

# 30. Short task prompt template

Future prompts should be short because this document already holds project context.

Use:

```text
PDFStruct task: <ONE TASK>

Read:
docs/MASTER_ARCHITECTURE.md

Goal:
<exact desired result>

Scope:
- <required item>
- <required item>

Do not:
- redesign unrelated architecture
- read large PDFs/raw JSON into LLM context
- duplicate core logic
- change unrelated features
- bump version unless requested

Workflow:
1. inspect only relevant source/tests
2. propose a short plan
3. implement smallest safe change
4. run targeted tests
5. run local CI if release-critical
6. commit only if requested

Final report:
CHANGED:
TESTS:
KNOWN LIMITATIONS:
READY:
```

This template should be preferred over large repeated master prompts.

---

# 31. Example — GUI task prompt

```text
PDFStruct task: Start v0.2 Desktop GUI.

Read:
docs/MASTER_ARCHITECTURE.md

Goal:
Create the first cross-platform PySide6 GUI using the existing PDFStruct core.

Scope:
- Windows + macOS first
- drag/drop
- file list
- multi-format selection
- output folder
- Convert
- progress
- cancel
- Open Output Folder

Do not:
- rewrite extraction/export logic
- add DOCX yet
- add AI
- add API/Docker
- change OCR architecture
- package installer until GUI core tests pass

Workflow:
1. inspect only core public interfaces needed by GUI
2. create minimal GUI architecture
3. wire GUI to existing core
4. add focused tests
5. smoke-test Windows locally
6. prepare macOS CI-compatible code

Final report:
GUI:
CORE REUSE:
TESTS:
WINDOWS:
MACOS READINESS:
KNOWN LIMITATIONS:
NEXT:
```

---

# 32. Decision priorities

When two implementation options are both valid, choose in this order:

1. user simplicity,
2. correctness,
3. privacy,
4. cross-platform behavior,
5. maintainability,
6. low dependency burden,
7. performance,
8. developer convenience.

Do not sacrifice user simplicity merely for architectural elegance.

---

# 33. Current next planned milestone

The next planned major milestone is:

```text
PDFStruct v0.2
Desktop GUI
```

Primary target:

```text
Windows + macOS
```

Desired normal-user experience:

### Windows

```text
Download Setup.exe
→ Install
→ Open PDFStruct
→ Drag PDFs
→ Choose formats
→ Convert
```

### macOS

```text
Download DMG
→ Drag PDFStruct to Applications
→ Open
→ Drag PDFs
→ Choose formats
→ Convert
```

CLI must remain fully functional.

---

# 34. Final architectural principle

PDFStruct should grow by adding **adapters and interfaces**, not by multiplying engines.

The long-term shape should remain:

```text
                   INPUT ADAPTERS
        PDF / DOCX / Images / Text / ...
                         ↓
                PDFStruct Core
                         ↓
             Normalized Document
                         ↓
                  EXPORTERS
       JSON / XLSX / DOCX / HTML / ...
                         ↓
             CLI / GUI / future API
```

If a new feature cannot fit this model, first ask whether it truly belongs in PDFStruct.

---

# 35. v0.2 working decisions (2026-10-07)

These decisions refine sections 5-14 for the v0.2 work. They are part of the source of truth.

## 35.1 One callable service

```text
Input adapter -> raw document (schema 1.0 / 1.1) -> service.run_job -> exporters -> CLI / GUI / MCP
```

- `pdfstruct.service.run_job(request, on_event=None, cancel=None) -> JobResult` is the only
  conversion entry point for interfaces. CLI front ends, the GUI and the MCP server call it;
  none of them parses another one's terminal output or owns conversion logic.
- One input is extracted once per job; every selected format is written from that result.
- One `OcrEngine` lives for the whole job and is loaded only when a page needs OCR.
- Results carry status, counts, paths, at most five short warnings and a short error. Never text.
- Progress events are real steps (file, phase, page, export). No invented percentages.
- Cancel is cooperative: checked between files, pages and exports. A running native or OCR
  call finishes first.

## 35.2 Inputs and outputs

Inputs: PDF, DOCX, TXT, Markdown, HTML, JPG/JPEG, PNG, TIFF, BMP, WebP.
Outputs: JSON, HTML, TXT, Markdown, CSV, XLSX, DOCX, JSONL, SQLite and PDF.

- Adapters live in `pdfstruct/inputs/` and only produce raw page records. No adapter exports.
- PDF keeps its existing extraction and writes schema 1.0 unchanged. Other inputs write the
  additive schema 1.1: `input_format`, `paged`, block `kind`, optional `level`, optional `bbox`.
- Images go straight to the existing OCR layer (no intermediate PDF). Unpaged inputs carry no
  invented coordinates and exporters print no "Page 1" heading for them.
- File names: a PDF keeps `<stem>.<ext>`; every other input uses `<file name>.<ext>`
  (`report.docx.raw.json`), so `report.pdf` and `report.docx` never overwrite each other.
- A source file is never overwritten. PDF to PDF is reported as skipped (`already_pdf`).

## 35.3 Honest format limits

- CSV/XLSX are block listings, not reconstructed tables. DOCX/HTML tables are not marketed as
  semantic spreadsheets.
- Image to DOCX/Markdown/HTML is OCR text only. Text PDF output is a readable re-flow, not a
  pixel-faithful rendering of the source; DOCX to PDF layout fidelity is not promised.
- Same-format round trips (DOCX to DOCX, MD to MD, TXT to TXT, HTML to HTML) lose styling and are
  reported with a warning. OCR options on text inputs are reported, not silently ignored.

## 35.4 Interfaces and token-saving operation

- CLI: unchanged commands and aliases; `pdfstruct --format pdf` is the tenth format.
- GUI: PySide6, optional extra `[gui]`, entry point `pdfstruct-gui`. A normal CLI run never
  imports Qt, and opening the window never loads OCR.
- MCP: optional extra `[mcp]`, local stdio server. Conversions run in a short-lived child
  process so OCR output cannot corrupt the protocol and OCR memory is released afterwards.
  Tools return paths and counts; document text is returned only by `read_excerpt`/`search`,
  capped, on explicit request, and labelled as untrusted data.
- Agent Skill: `skills/pdfstruct/SKILL.md`. Instructions only (MCP first, CLI fallback); no
  engine, no models.

---

**End of master architecture.**
