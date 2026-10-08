# PDF pipeline reference

How PDFStruct reads a document, how it decides between native text and OCR, what the raw
JSON contains and how to configure and extend it.

```
DETERMINISTIC / BULK WORK      = code on your computer
AMBIGUOUS / SEMANTIC DECISION  = a person or an LLM
```

PDFStruct does not interpret a document: it does not decide what a word means or which line
is the invoice date. It produces reliable raw data: pages, text, line blocks, bounding boxes,
method and quality score.

## How each input is read

| Input | Read as |
|---|---|
| PDF | native text per page; OCR only for pages without a usable text layer |
| JPG/JPEG, PNG, TIFF/TIF, BMP, WebP | OCR (multi-page TIFF: one page per frame, EXIF orientation applied) |
| DOCX | paragraphs, headings, list items, simple tables, in document order |
| TXT, Markdown (`.md`, `.markdown`) | text; Markdown headings, lists and code blocks |
| HTML (`.html`, `.htm`) | visible text of the file on disk; no scripts, no network |

Every input is read once; all requested formats come from that one result.

## Native text or OCR

```
Native PDF (a real text layer)        -> text extraction (pypdfium2, CPU, very fast)
Scanned or photographed page          -> OCR (PaddleOCR)
```

The decision is made in code, **per page**. In a mixed PDF some pages are native and others
OCR (`extraction_method: "mixed"`).

### Quality score (text layer score)

Each page gets a score from 0 to 1: the **weakest** of three components.

| Component | Meaning |
|---|---|
| `density` | If a large image covers the page (a likely scan), is there enough text? Without such an image: 1.0 |
| `unicode` | Share of broken characters (U+FFFD, control characters, private use). 0 % gives 1.0; 10 % or more gives 0.0 |
| `bbox` | Share of blocks whose box is valid and inside the page |

Rules:

- No text and no objects on the page: an **empty page** (`method: "none"`). OCR does not run
  and the page does not count toward the score.
- No text, but images or objects: score 0.0, so **OCR**.
- Score below `min_page_score` (default 0.5): **OCR**.

The document score (`text_layer_score`) is the average of the non-empty pages. All components
are written page by page to `<name>.summary.json`, so every decision can be explained.

Known limit: if another tool added a text layer to a scan that *looks fine but is wrong*, the
score cannot detect it. When in doubt, use `--force-ocr`.

## Output files

| File | Content | Safe to read into an LLM? |
|---|---|---|
| `<name>.raw.json` | Full raw data: pages, text, blocks, boxes | No; single pages only |
| `<name>.summary.json` | Method, score and warnings per page; no text | Yes |
| `_run_summary.json` | Totals of the run, one line per document | Yes |
| `<name>.parsed.json` | Output of `--parser` | Depends on the parser |

### Raw JSON

Full schema: [schemas/raw_document.schema.json](../schemas/raw_document.schema.json)
(schema 1.0 for PDF inputs, 1.1 for the other inputs).

```json
{
  "schema_version": "1.0",
  "source": { "path": "C:\\...\\document.pdf", "file_name": "document.pdf", "sha256": "...", "size_bytes": 12345 },
  "source_file": "C:\\...\\document.pdf",
  "extraction_method": "native",
  "text_layer_score": 0.97,
  "ocr_used": false,
  "coordinate_system": { "unit": "pt", "origin": "top-left", "bbox": "[x1, y1, x2, y2]" },
  "page_count": 24,
  "review_pages": [],
  "pages": [
    {
      "page": 1, "width": 595.28, "height": 841.89, "rotation": 0,
      "method": "native",
      "text_layer": { "score": 1.0, "components": { "density": 1.0, "unicode": 1.0, "bbox": 1.0 }, "chars": 1830 },
      "ocr_confidence": null, "needs_review": false, "warnings": [],
      "text": "...",
      "blocks": [ { "text": "...", "bbox": [72.0, 61.2, 310.4, 73.9], "order": 0 } ]
    }
  ]
}
```

- `bbox` is in points (1/72 inch), origin **top left**, page rotation applied. Native and OCR
  pages use the same coordinate system.
- `blocks` are lines, in extraction order (`order`). OCR blocks carry a `confidence`.
- `review_pages` lists pages that need a person or an LLM: low OCR confidence, OCR needed but
  unavailable, and similar.

### Repeat runs

If the source file (SHA-256) and the settings did not change, the document is skipped
(`SKIPPED`). If either changed, it is extracted again. The output is deterministic: the same
input gives a byte-identical raw JSON.

## What the output formats do not do

- `csv` and `xlsx` list text blocks, one per row. They are not reconstructed tables, also when
  the source is a DOCX or HTML table.
- `pdf` from DOCX, TXT, Markdown or HTML is a readable reflow on A4 (headings, paragraphs,
  lists, simple tables), not the layout of the source.
- `pdf` from an image is the picture fitted to the page with the recognised text placed
  invisibly on top, so it can be searched.
- Image to DOCX, Markdown or HTML contains the recognised text only.
- Same-format round trips keep the text and lose the styling; PDFStruct says so in a warning.
- DOCX has no stored page breaks: it is one logical page, and images, headers, footers and
  text boxes are not read. Markdown tables and inline markup stay literal text.
- PDF text uses the Bitstream Vera fonts (Latin, including Turkish and German). Other scripts
  are reported as missing glyphs.

## Configuration

Copy `config.example.json` to `~/.pdfstruct/config.json`, or pass a file with `--config`, or
set `PDFSTRUCT_CONFIG`. Without a file the built-in defaults apply.

```json
{
  "quality": {
    "min_page_score": 0.5,
    "scan_image_coverage": 0.5,
    "min_chars_over_image": 100,
    "bad_char_ratio_fail": 0.10,
    "ocr_review_confidence": 0.60
  },
  "ocr": {
    "model_cache_dir": "",
    "det_model": "PP-OCRv5_mobile_det",
    "rec_model": "latin_PP-OCRv5_mobile_rec",
    "device": "auto",
    "enable_mkldnn": false,
    "dpi": 200,
    "max_side_px": 4000
  }
}
```

## OCR

OCR runs in PDFStruct's own Python environment: `paddleocr` and `paddlepaddle` (CPU) come with
the installation on supported platforms. No separate OCR setup, other Python or CUDA is
needed.

- On native pages the OCR library is **never imported**; it is loaded on the first page that
  needs OCR, so start time and memory are unchanged for native use.
- Models are downloaded on the first OCR run to `~/.pdfstruct/models` (change with
  `ocr.model_cache_dir`) and read from that cache afterwards. No model files are in the
  package.
- Default models: `PP-OCRv5_mobile_det` and `latin_PP-OCRv5_mobile_rec` (Latin alphabets,
  including German, Turkish and English; roughly 1 to 2 seconds per page on a CPU). For
  another script set `ocr.rec_model`; for stronger detection set
  `ocr.det_model: "PP-OCRv6_medium_det"`. Other scripts are not a tested default.
- Device: `ocr.device: "auto"` means CPU. A GPU is used only with a CUDA build of paddlepaddle
  and a visible GPU; that is not a supported, ready setup at this stage.
- `ocr.enable_mkldnn` defaults to `false`: the oneDNN path fails in current paddlepaddle 3.x
  CPU builds.
- Without the OCR packages PDFStruct does not crash: native text is kept, the pages go to
  `review_pages`, and the terminal prints `OCR_UNAVAILABLE`. To try a platform the dependency
  markers do not cover: `pip install "pdfstruct[ocr]"`.
- The old settings `ocr.python` and `ocr.python_candidates` are no longer used and are ignored.

## Project parsers

The general tool and a project-specific parser are connected by one function:

```python
# my_parser.py  (lives in your project)
OUTPUT_SUFFIX = ".a2_master.json"      # optional; default ".parsed.json"

def parse(raw: dict, context: dict):
    # raw     = the loaded <name>.raw.json
    # context = {"raw_path", "output_dir", "stem", "source_file"}
    ...
    return {"entries": [...]}          # written as <name>.a2_master.json (None: nothing written)
```

```
pdfjson --parser tools\my_parser.py
```

```
document.pdf -> document.raw.json -> (vocabulary parser) -> document.a2_master.json
invoice.pdf  -> invoice.raw.json  -> (invoice parser)    -> invoice.parsed.json
```

The parser also runs when extraction is skipped, so the PDF is not processed again while you
develop the parser. Example: [examples/example_parser.py](../examples/example_parser.py).
