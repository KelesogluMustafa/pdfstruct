# PDFStruct — Claude Project Instructions

## Source of truth

The project architecture, product principles, roadmap and development rules are defined in:

`docs/MASTER_ARCHITECTURE.md`

For architectural changes, new features, releases or significant refactors:
1. Read `docs/MASTER_ARCHITECTURE.md` first.
2. Follow it as the project source of truth.
3. Inspect only files directly relevant to the current task.
4. Do not reread the entire repository unnecessarily.
5. Do not read large PDFs, OCR models, raw JSON dumps or generated outputs into context unless strictly necessary.

For small bug fixes or trivial edits, do not reread the entire master document if the relevant rule is already known.

## Core rule

Bulk/deterministic work = local code/tools.
Ambiguous/semantic decisions = LLM.

## Architecture rule

Never duplicate the PDFStruct conversion engine.

CLI, Desktop GUI and any future interfaces must use the same PDFStruct core.

## Scope rule

Implement only the current requested task.
Do not automatically start future roadmap items.

## Related rules

PDF-processing rules for Claude sessions in other projects (do not read PDFs or whole raw JSON into context, which files may be read) stay in `CLAUDE_RULES.md`; this file and `docs/MASTER_ARCHITECTURE.md` do not replace it.
