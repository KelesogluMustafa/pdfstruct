# Third-party notices

PDFStruct itself is released under the MIT License (see LICENSE). It does not bundle any
third-party source code or model files; the packages below are installed as dependencies
from PyPI, and OCR models are downloaded by PaddleX at first use from PaddlePaddle's
official model repository.

| Package | Used for | License |
|---|---|---|
| pypdfium2 (incl. PDFium) | native text extraction, page rendering | BSD-3-Clause / Apache-2.0 |
| Pillow | image handling | MIT-CMU (HPND) |
| openpyxl | XLSX export | MIT |
| python-docx | DOCX input and export | MIT |
| reportlab | PDF export | BSD-3-Clause |
| Bitstream Vera fonts (shipped inside reportlab) | text in PDF output | Bitstream Vera Fonts license (permissive) |
| paddleocr | OCR pipeline | Apache-2.0 |
| paddlepaddle | OCR inference runtime (CPU build) | Apache-2.0 |
| paddlex | model management used by paddleocr | Apache-2.0 |
| PP-OCRv5 models (PaddleOCR) | text detection and recognition | Apache-2.0 |
| PySide6-Essentials / Qt 6 (optional extra `gui`) | desktop window | LGPL-3.0-only (also GPL) |
| mcp (optional extra `mcp`) | Model Context Protocol server SDK | MIT |

Each package keeps its own license text inside its distribution.

## PDF output and fonts

PDF files written by PDFStruct embed subsets of the Bitstream Vera Sans faces that are
distributed inside the `reportlab` package (`reportlab/fonts`, with their license file
`bitstream-vera-license.txt`). PDFStruct does not ship font files of its own. The Vera license
permits embedding and redistribution; anyone who repackages PDFStruct together with reportlab
(for example a frozen desktop build) must keep that license file in the package.

## Desktop window (Qt for Python)

The optional desktop window uses PySide6 / Qt 6 under the LGPL-3.0. PDFStruct only imports it as
an installed dependency. Anyone who distributes a bundled build (for example a frozen
executable) must meet the LGPL terms: include the LGPL text and the Qt notices, state that Qt
is used, and keep Qt replaceable (dynamic linking, as PySide6 wheels already do).
