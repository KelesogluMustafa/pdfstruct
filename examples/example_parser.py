"""Example project parser for pdfjson --parser.

Contract (the only coupling between the general tool and a project parser):

    parse(raw: dict, context: dict) -> dict | list | None

    raw      one loaded *.raw.json document (see schemas/raw_document.schema.json)
    context  {"raw_path", "output_dir", "stem", "source_file"}
    return   JSON-serialisable result, written to <stem><OUTPUT_SUFFIX>;
             return None to write nothing (e.g. the parser writes its own files)

Copy this file into your project and replace the body of parse(). This sample
only counts words per page; real parsers do the document-specific work
(vocabulary entries, invoice fields, ...).
"""

OUTPUT_SUFFIX = ".parsed.json"  # optional; default is ".parsed.json"


def parse(raw: dict, context: dict) -> dict:
    return {
        "source_file": raw["source_file"],
        "extraction_method": raw["extraction_method"],
        "pages": [
            {"page": page["page"], "words": len(page["text"].split())}
            for page in raw["pages"]
        ],
    }
