# PDFStruct

PDFStruct converts documents locally: PDF, DOCX, TXT, Markdown, HTML and images go in;
JSON, HTML, TXT, Markdown, CSV, XLSX, DOCX, JSONL, SQLite and PDF come out. It reads native
text when it exists and uses OCR when a page needs it. Nothing is uploaded.

One engine, four ways to use it:

| | Start with | For |
|---|---|---|
| Desktop window | `pdfstruct-gui` | drag files in, tick formats, Convert |
| Terminal menu | `pdfstruct` | pick files and formats with the keyboard |
| Scripts | `pdfstruct file --format xlsx`, `pdfjson file` | automation, no prompts |
| Claude | local MCP server + Agent Skill | conversions without the document entering the chat |

## Install

Not on PyPI yet. Install from a checkout or from the wheel of a
[GitHub release](https://github.com/KelesogluMustafa/pdfstruct/releases/latest).

**Windows, for daily use (and for Claude).** Download `pdfstruct-<version>-py3-none-any.whl`
from the release, then run `install-windows.cmd -Wheel <path to the wheel>` from this repository
(or `powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 -Wheel ...`). It creates
`%USERPROFILE%\.local\pdfstruct\v<version>` with its own Python environment and installs the
wheel there, with the desktop window and the MCP server. The result is not linked to any source
folder, the system Python packages are not touched, and running it again only repairs or
updates that folder. It needs Python 3.10–3.13 from python.org.

**Windows, for working on the code.** `setup-windows.cmd` creates `.venv` inside the repository
and installs it in editable mode, then opens the window. Do not point Claude at that
environment: a running MCP server keeps its files locked and follows whatever the working tree
contains.

**Any platform, with pip** (Windows, macOS, Linux):

```
python -m venv .venv
.venv\Scripts\activate            (macOS/Linux: source .venv/bin/activate)
pip install -e ".[gui,mcp]"       (from a release: pip install "pdfstruct-<version>-py3-none-any.whl[gui,mcp]")
```

`[gui]` adds the desktop window (PySide6), `[mcp]` the MCP server. Leave them out for the
command line only. The OCR packages are installed automatically on Windows x86_64,
Linux x86_64 and macOS Apple Silicon with Python 3.9–3.13; the first OCR run downloads the two
models once (about 70 MB) to `~/.pdfstruct/models`.

## Formats

| Input | Read as |
|---|---|
| PDF | native text per page; OCR only for pages without a usable text layer |
| JPG/JPEG, PNG, TIFF/TIF, BMP, WebP | OCR (multi-page TIFF: one page per frame, EXIF orientation applied) |
| DOCX | paragraphs, headings, list items, simple tables, in document order |
| TXT, Markdown (`.md`, `.markdown`) | text; Markdown headings, lists and code blocks |
| HTML (`.html`, `.htm`) | visible text of the local file; no scripts, no network |

Outputs: `json` (the raw document), `html`, `txt`, `md`, `csv`, `xlsx`, `docx`, `jsonl`,
`sqlite`, `pdf`. Every input is read once; all formats you ask for come from that one result.

Files go to an `output` folder next to each input (or to `--output`). `report.pdf` writes
`report.<ext>` as before; every other input keeps its extension (`report.docx` writes
`report.docx.<ext>`), so files with the same name never overwrite each other. A source file is
never overwritten.

### What the formats do not do

- `csv` and `xlsx` list text blocks, one per row. They are not reconstructed tables, also when
  the source is a DOCX or HTML table.
- `pdf` from DOCX, TXT, Markdown or HTML is a readable re-flow on A4 (headings, paragraphs,
  lists, simple tables), not the layout of the source. Pixel-faithful DOCX to PDF is not a goal.
- `pdf` from an image is the picture fitted to the page with the recognised text placed
  invisibly on top, so it can be searched. A PDF input is not written again as PDF
  (reported as `already_pdf`).
- Image to DOCX/Markdown/HTML contains the recognised text only.
- Same-format round trips (DOCX to DOCX, Markdown to Markdown, ...) keep the text and lose the
  styling; PDFStruct says so in a warning.
- DOCX has no stored page breaks: it is one logical page, and images, headers/footers and
  text boxes are not read. Markdown tables and inline markup stay literal text.
- PDF text uses the Bitstream Vera fonts (Latin incl. Turkish and German). Other scripts are
  reported as missing glyphs.
- Not supported: CSV/XLSX input, legacy `.doc`, RTF, ODT, EPUB, PowerPoint, HEIC.

## Desktop window

```
pdfstruct-gui                     (Windows without activating anything: setup-windows.cmd)
pdfstruct-gui report.pdf scans    files or folders can be passed
```

Drop files or folders on the window or use **Select Files**, tick one or more of the ten
formats, optionally choose an output folder, press **Convert**. The window shows the current
file and step (reading, OCR page, writing), lists the result per file with its warnings, and
**Open Output Folder** opens the result. **Cancel** stops after the step that is running.
OCR is loaded only when a file needs it, never when the window opens.

## Terminal

```
pdfstruct                                  menu: pick files here, then formats
pdfstruct report.docx                      menu: pick formats for that file
pdfstruct report.docx --format pdf         one format
pdfstruct scan.png --format txt,docx,pdf   several formats, one OCR pass
pdfstruct "C:\Documents" --format json --all-types    every supported file in the folder
pdfxlsx report.pdf                         aliases: pdfjson pdfhtml pdftxt pdfmd pdfcsv pdfxlsx
                                           pdfdocx pdfjsonl pdfsqlite
pdfjson                                    all PDFs in the current folder
```

In the menu: arrow keys move, `SPACE` selects, `A` selects all, `ENTER` continues, `B` goes
back, `Q` quits. With `--format` (or an alias) nothing is asked. A folder given to a
non-interactive command takes its PDFs only, as before; add `--all-types` for every supported
type. `--force-ocr` runs OCR on every PDF page, `--native-only` never runs it; on inputs where
these make no sense PDFStruct says so instead of ignoring them. Without a terminal (CI, pipes)
a bare `pdfstruct` prints usage instead of waiting.

## Claude: MCP server and Agent Skill

The MCP server lets Claude start conversions on your computer and get back **status and file
names only**. The document does not enter the conversation unless you ask Claude to read it,
and then only in small pieces.

Tools: `convert(paths, formats, output_dir?, force_ocr?)`, `inspect(path)`,
`supported_formats()`, `search(path_or_output, query)`, `read_excerpt(path_or_output, page?,
max_chars?)` (at most 2000 characters per call, returned as untrusted document text).

Both Claude apps start the same program: the `pdfstruct-mcp.exe` of the versioned install above.

**Claude Code:**

```
claude mcp add --scope user pdfstruct -- "%USERPROFILE%\.local\pdfstruct\v<version>\Scripts\pdfstruct-mcp.exe"
```

(macOS/Linux: the `pdfstruct-mcp` of the environment you installed into.)

**Claude for Windows (chat): the `.mcpb` extension.** `pdfstruct-<version>.mcpb` is a launcher,
not a standalone app: it contains a manifest and nothing else to run, and starts
`%USERPROFILE%\.local\pdfstruct\v<version>\Scripts\pdfstruct-mcp.exe`. Install PDFStruct with
`install-windows.cmd` first; installing only the `.mcpb` on another computer does not work.
Then in Claude: Settings, Extensions, Advanced settings, Install Extension, choose the file.
`python scripts/build_claude_windows.py --stage` builds the extension, the Skill ZIP and a
step-by-step `README-INSTALL.txt` into `%USERPROFILE%\.local\pdfstruct\claude-windows`.
If the extension does not load, add the server by hand to `claude_desktop_config.json`:

```json
{ "mcpServers": { "pdfstruct": { "command": "C:\\Users\\<you>\\.local\\pdfstruct\\v<version>\\Scripts\\pdfstruct-mcp.exe" } } }
```

The Agent Skill teaches Claude to use the MCP tools and not to read documents into the chat for
a conversion. Where Claude can run commands on your own computer (Claude Code) it may use the
command line instead; in Claude for Windows chat there is no such access, so the Skill tells
Claude to use the MCP tools only and to say so when the extension is not connected. It
contains instructions only. A Skill installed in Claude Code is not carried over to Claude for
Windows: upload the ZIP there separately (Customize, Skills). Build `dist/pdfstruct-skill.zip` with `python scripts/build_skill_zip.py`, or take it
from a release, then either upload the ZIP in Claude's skill settings or unpack it to
`~/.claude/skills/pdfstruct/` for Claude Code.

## Windows portable folder (no Python needed)

`PDFStruct-Portable-<version>-win64.zip` from a release unpacks to a folder with
`PDFStruct.exe` (the window) and `pdfstruct-cli.exe` (the command line). Nothing is installed.
It is about 800 MB unpacked because it carries the OCR runtime and Qt; the OCR models are still
downloaded on first use. The build is unsigned, so SmartScreen may ask once, and it has been
built and tried on one Windows 11 x64 machine only. The MCP server is not part of it.

Build it yourself with `pip install -e ".[gui,packaging]"` and
`python packaging/windows/build_portable.py`.

## Platforms

Tested by the automated suite on GitHub Actions with Python 3.13: Windows x86_64,
Linux x86_64 and macOS Apple Silicon (extraction, OCR, all formats; the desktop window is
checked there without a display). The window was opened and used by hand on Windows 11 only.
On macOS and Linux the window is expected to work after `pip install ".[gui]"` but has not
been tried on a real desktop: treat it as unverified. There is no installer, `.app` or DMG yet;
the Windows portable folder above is the only packaged build.
macOS Intel, Linux ARM64 and Windows ARM install and read native text; OCR is not available
there because PaddlePaddle publishes no wheels for them.

## Project Principles

PDFStruct is free and open source.
All core functionality is available without payment, accounts, usage limits or tracking.
Voluntary donations may support future development, but never unlock features.

## Development

```
pip install -e ".[dev,gui,mcp]"
python scripts/ci_local.py
```

`scripts/ci_local.py` (Windows shortcut: `ci-local`) runs the whole local CI in one go:
import and version check, test suite, wheel + sdist build and validation, a clean temporary
venv with the built wheel and its extras, every console script, native and OCR conversions,
the desktop window without a display, the MCP server over stdio and the skill archive. Output
is one line per step; full logs appear only for failing steps. The architecture and the rules
for changes are in [docs/MASTER_ARCHITECTURE.md](docs/MASTER_ARCHITECTURE.md).

---

## PDF extraction reference (Turkish)

The sections below are the detailed reference for the PDF pipeline (quality score, raw JSON,
options, project parsers). They predate the other input types and describe PDF inputs.

Genel amaçlı, projeden bağımsız, tamamen local **PDF → ham JSON** aracı.

```
DETERMINISTIC / BULK WORK   = PYTHON / LAPTOP
AMBIGUOUS / SEMANTIC DECISION = LLM
```

Araç belgeyi **anlamlandırmaz** (kelime, fatura tarihi, müşteri adı vb. kararı vermez).
Yalnızca güvenilir ham veri üretir: sayfa, metin, satır blokları, bbox, yöntem, kalite skoru.

## En basit kullanım

Tek dosya:

```
pdfjson belge.pdf
```

Bulunduğun klasördeki tüm PDF'ler:

```
pdfjson
```

Başka klasördeki tüm PDF'ler:

```
pdfjson "C:\Belgeler"
```

Çıktı her zaman PDF'lerin yanındaki `output` klasörüne yazılır (yoksa oluşturulur):
`C:\Belgeler\belge.pdf` → `C:\Belgeler\output\belge.raw.json`. Başka yere yazmak için
`--output "D:\hedef"` ekle.

- Boşluk, Türkçe karakter ve parantez içeren yollar çalışır; tırnak içine alman yeterli:
  `pdfjson "C:\Belgeler\maaş bordrosu (1).pdf"`.
- Klasörde alt klasörlere inilmez.
- Bir PDF bozuksa diğerleri işlenmeye devam eder; sonda `FAILED FILES:` altında listelenir.
- Aynı komutu tekrar çalıştırmak güvenlidir: değişmemiş PDF'ler atlanır (`SKIPPED`).
- `pdfhtml`, `pdftxt`, `pdfmd`, `pdfcsv`, `pdfxlsx`, `pdfdocx`, `pdfjsonl`, `pdfsqlite` aynı
  şekilde kullanılır (`pdfhtml belge.pdf`, `pdfxlsx`, `pdftxt "C:\Belgeler"`).
- `pdfstruct` komutu `--format` verilmezse menü açar (yukarıdaki *Easy usage*); alias'lar hiç menü açmaz.

Argüman verilmediğinde sıra: (1) bulunduğun klasördeki `*.pdf`, (2) orada PDF yoksa `.\pdf\`
alt klasörü (çıktı `.\output\`). `pdf\` klasörü **zorunlu değildir**; yalnız eski kullanımla
uyumluluk ve düzenli proje yapısı (`proje\pdf` → `proje\output`) isteyenler için duruyor.

Terminal çıktısı her zaman kısadır:

```
FILES FOUND: 12
PROCESSED: 11
SKIPPED: 0
FAILED: 1
PAGES: 184
OCR FILES: 1
REVIEW_PAGES: 0
OUTPUT: C:\Belgeler\output

FAILED FILES:
- bozuk.pdf
```

Tek dosyada ayrıca `METHOD` ve `TEXT_LAYER_SCORE` satırları basılır.

### Alt seviye komut (`pdf2json.cmd`)

`pdfjson` yolları çözüp bu komutu çağırır. Yolları kendin vermek istersen:

```
<repo>\pdf2json.cmd --input "C:\...\pdf" --output "C:\...\output"
```

Aracın kendi venv'ini kullanır. `--input` tek bir PDF veya klasör olabilir. Çıktısı
`FILES / PAGES / NATIVE / OCR / MIXED / SKIPPED / REVIEW_PAGES / ERRORS / OUTPUT` satırlarıdır.

## Native mi, OCR mı?

```
Native PDF (gerçek metin katmanı var)   →  text extraction (pypdfium2, CPU, çok hızlı)
Scanned / photo PDF (sayfa bir resim)   →  OCR (PaddleOCR, GPU varsa GPU)
```

Kararı Python verir, **sayfa bazında**. Bu yüzden karışık PDF'lerde bazı sayfalar native,
bazıları OCR olabilir (`extraction_method: "mixed"`).

### Kalite skoru (text layer score)

Her sayfa için 0–1 arası skor = üç bileşenin **en zayıfı**:

| Bileşen | Anlamı |
|---|---|
| `density` | Sayfayı büyük bir resim kaplıyorsa (olası tarama) metin miktarı yeterli mi? Resim yoksa 1.0 |
| `unicode` | Bozuk karakter oranı (U+FFFD, kontrol karakterleri, private-use). %0 → 1.0, %10 ve üzeri → 0.0 |
| `bbox` | Bloklardan kaçının kutusu geçerli ve sayfa içinde |

- Metin yok + sayfada hiç nesne yok → **boş sayfa** (`method: "none"`, OCR çalışmaz, skora girmez).
- Metin yok + sayfada resim/nesne var → skor 0.0 → **OCR**.
- Skor `min_page_score` (varsayılan 0.5) altındaysa → **OCR**.

Belge skoru (`text_layer_score`) = boş olmayan sayfaların ortalaması. Bütün bileşenler
`.summary.json` içinde sayfa sayfa yazılır; karar her zaman açıklanabilir.
Eşikler ayar dosyasıyla değiştirilebilir: `config.example.json` dosyasını
`~/.pdfstruct/config.json` olarak kopyala (veya `--config` / `PDFSTRUCT_CONFIG` ile yol ver).

Bilinen sınır: taranmış bir PDF'e daha önce başka bir araçla *düzgün görünen ama yanlış*
bir metin katmanı eklenmişse skor bunu yakalayamaz. Şüphe varsa `--force-ocr` kullan.

## Çıktı dosyaları

| Dosya | İçerik | Claude okuyabilir mi? |
|---|---|---|
| `<ad>.raw.json` | Tam ham veri: sayfalar, metin, bloklar, bbox | **Hayır** (yalnız tek tek sayfa) |
| `<ad>.summary.json` | Sayfa başına yöntem, skor, uyarı; metin yok | Evet |
| `_run_summary.json` | Çalıştırmanın toplamı, belge başına bir satır | Evet |
| `<ad>.parsed.json` | `--parser` çıktısı | Parser'a bağlı |

### raw.json biçimi (özet)

Tam şema: [schemas/raw_document.schema.json](schemas/raw_document.schema.json)

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

- `bbox` birimi punto (1/72 inç), orijin **sol üst**, sayfa döndürmesi uygulanmış. Native ve
  OCR sayfalarında aynı koordinat sistemi kullanılır.
- `blocks` satır düzeyindedir, çıkarım sırasıyla (`order`). OCR bloklarında `confidence` vardır.
- `review_pages`: insan/LLM gözü gereken sayfalar (düşük OCR güveni, OCR gerekip çalışamadı vb.).

## Kısa komutlar ve ek çıktı formatları

Bu klasör USER PATH'te olduğu için komutlar her yerden çalışır. Hepsi `pdfjson` ile aynı
girdi kurallarını kullanır (dosya, klasör veya argümansız).

| Komut | Çıktı | İçerik |
|---|---|---|
| `pdfjson` | `<ad>.raw.json` | Çıkarım + OCR (asıl pipeline). Seçenekler aynen geçer: `pdfjson --force-ocr` |
| `pdfhtml` | `<ad>.html` | Tarayıcıda kontrol: sayfa sayfa bloklar, yöntem, skor, OCR güveni. Tek dosya, internet gerekmez |
| `pdftxt` | `<ad>.txt` | Yalnız metin; sayfalar `===== Page 3 / 24 =====` ile ayrılır |
| `pdfmd` | `<ad>.md` | `## Page N` başlıklı Markdown; satır sırası korunur, tablo üretilmez |
| `pdfcsv` | `<ad>.csv` | Blok başına satır: `source_file,page,block_index,text,x1,y1,x2,y2,method,confidence` |
| `pdfxlsx` | `<ad>.xlsx` | İki sheet: `Pages` (sayfa başına satır) ve `Blocks` (CSV ile aynı kolonlar) |
| `pdfdocx` | `<ad>.docx` | Sayfa sırasıyla okunabilir Word belgesi; her PDF sayfası yeni sayfada |
| `pdfjsonl` | `<ad>.jsonl` | Blok başına bir JSON satırı (`bbox` dizi olarak) |
| `pdfsqlite` | `<ad>.sqlite` | `documents`, `pages`, `blocks` tabloları |
| `pdfstruct <dosya> --format pdf` | `<ad>.<uzantı>.pdf` | PDF çıktısı (DOCX/TXT/MD/HTML ve görseller için; PDF girdide atlanır) |

**Format komutları PDF'i yeniden çıkarmaz / OCR'lamaz:**

1. `output\<ad>.raw.json` varsa o kullanılır (PDF açılmaz; PDF silinmiş olsa bile çalışır).
2. Yoksa önce normal `pdfjson` pipeline'ı **yalnız eksik belgeler için** çalışır.
3. Hedef format raw JSON'dan üretilir.

Terminal çıktısı:

```
FORMAT: html
FILES: 2
EXPORTED: 2
RAW_REUSED: 2      (mevcut raw.json kullanıldı)
EXTRACTED: 0       (bu çalıştırmada çıkarılan belge)
ERRORS: 0
OUTPUT: C:\...\output
```

Notlar:

- Tekrar çalıştırmak güvenlidir: dosyalar yeniden yazılır, SQLite'ta belgenin eski satırları
  aynı transaction içinde silinip yeniden eklenir (çift kayıt oluşmaz).
- PDF sonradan değiştiyse raw.json eski kalır; komut `STALE_RAW` satırıyla uyarır. Yenilemek
  için `pdfjson` çalıştır.
- `--force-ocr`, `--native-only`, `--config` yalnız çıkarılması gereken belgeleri etkiler.
- `confidence` yalnız OCR bloklarında doludur. `method` sayfanın yöntemidir (`native` / `ocr`).
- CSV, UTF-8 **BOM**'ludur (Excel umlautları doğru açsın diye); Python'da `encoding="utf-8-sig"`.
- HTML/TXT/MD/DOCX/XLSX'te okunabilirlik için satır sonu tire işaretleri `-` yapılır, kontrol
  karakterleri atılır. CSV/JSONL/SQLite metni raw.json'daki gibi saklar.
- XLSX'te bir hücre en çok 32.767 karakter alır; daha uzun sayfa metni kesilir (tam metin
  diğer formatlarda durur).
- Bunlar **genel belge exportudur** (sayfa + satır blokları). Kelime listesi, fatura, bordro
  gibi semantik alanlar için project parser kullan (aşağıda).

## Seçenekler

| Seçenek | Ne yapar |
|---|---|
| `--output <klasör>` | Çıktı klasörü (varsayılan: PDF'lerin yanındaki `output`) |
| `--force-ocr` | Boş olmayan her sayfayı OCR'dan geçirir |
| `--native-only` | OCR'ı hiç çalıştırmaz; zayıf sayfalar `review_pages`'e düşer |
| `--overwrite` | Güncel `.raw.json` olsa bile yeniden çıkarır |
| `--parser <dosya.py>` | Her belge için project parser çalıştırır |
| `--config <dosya.json>` | Ayar dosyası (varsayılan: `PDFSTRUCT_CONFIG` veya `~/.pdfstruct/config.json`; yoksa gömülü varsayılanlar) |

**İkinci çalıştırma (idempotent):** kaynak PDF (sha256) ve ayarlar değişmediyse belge atlanır
(`SKIPPED`). PDF veya ayar değişirse otomatik yeniden çıkarılır. Çıktı deterministiktir
(aynı girdi → byte-byte aynı raw.json).

**Hatalı PDF:** diğer dosyalar işlenmeye devam eder; bozuk dosya için
`<ad>.summary.json` içinde `status: "error"` yazılır, çıkış kodu 1 olur.

## Project parser (hook)

Genel araç ile projeye özel parser birbirine yalnızca tek bir fonksiyonla bağlıdır:

```python
# my_parser.py  (kendi projende durur)
OUTPUT_SUFFIX = ".a2_master.json"      # isteğe bağlı; varsayılan ".parsed.json"

def parse(raw: dict, context: dict):
    # raw     = yüklenmiş <ad>.raw.json
    # context = {"raw_path", "output_dir", "stem", "source_file"}
    ...
    return {"entries": [...]}          # <ad>.a2_master.json olarak yazılır (None → yazılmaz)
```

```
pdfjson --parser tools\my_parser.py
```

```
document.pdf → document.raw.json → (Goethe parser)  → document.a2_master.json
invoice.pdf  → invoice.raw.json  → (invoice parser) → invoice.parsed.json
```

Parser, çıkarım atlansa (SKIPPED) bile çalışır; yani parser'ı geliştirirken PDF yeniden
işlenmez. Örnek: [examples/example_parser.py](examples/example_parser.py).

## OCR ortamı

OCR, PDFStruct'ın kendi Python ortamında çalışır: `paddleocr` + `paddlepaddle` (CPU) paketleri
desteklenen platformlarda `pip install` ile birlikte gelir; ayrı bir OCR kurulumu, başka bir
Python yolu veya CUDA gerekmez.

- Native sayfalarda OCR kütüphanesi **hiç import edilmez**; yalnız OCR gereken ilk sayfada
  yüklenir (başlangıç süresi ve RAM native kullanımda değişmez).
- Modeller ilk OCR'da `~/.pdfstruct/models` altına indirilir (`ocr.model_cache_dir` ile
  değiştirilebilir), sonraki çalıştırmalarda önbellekten okunur. Model dosyaları pakette yoktur.
- Varsayılan modeller: `PP-OCRv5_mobile_det` + `latin_PP-OCRv5_mobile_rec` (Almanca/Türkçe/
  İngilizce dahil Latin alfabeleri; CPU'da sayfa başına yaklaşık 1–2 s). Başka alfabe için
  ayar dosyası → `ocr.rec_model`; daha güçlü algılama için `ocr.det_model: "PP-OCRv6_medium_det"`.
- Cihaz: `ocr.device: "auto"` → CPU. GPU yalnız CUDA'lı bir paddlepaddle kurulumu ve bir GPU
  görüldüğünde kullanılır; bu aşamada desteklenen/hazır bir kurulum yolu değildir.
- `ocr.enable_mkldnn` varsayılan `false`: güncel paddlepaddle 3.x CPU derlemelerinde oneDNN
  yolu hata veriyor.
- OCR paketleri yoksa araç çökmez: native metin korunur, sayfalar `review_pages`'e yazılır,
  terminalde `OCR_UNAVAILABLE` satırı çıkar. Marker'ların kapsamadığı bir platformda denemek
  için: `pip install "pdfstruct[ocr]"`.
- Eski ayar anahtarları `ocr.python` ve `ocr.python_candidates` artık kullanılmaz; ayar
  dosyasında dursalar bile yok sayılır.

## Kurulum (yeniden kurmak gerekirse)

En kolayı: repo klasöründe `setup-windows.cmd`. Elle:

```
cd <repo>
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,gui,mcp]"
```

Bu klasördeki `.cmd` dosyaları (`pdfjson.cmd`, `pdfstruct-gui.cmd`, `pdfstruct-mcp.cmd`, ...)
bu `.venv`'i kullanır; klasör USER PATH'te olduğu için venv'i aktive etmeden her yerden çalışır.
Başka bir Python ortamına `pip install` ile kurulduğunda aynı komutlar o ortamın kendi
script'leri olarak gelir (Windows/macOS/Linux).

Testler, derleme ve kurulum doğrulamasının tamamı tek komutla: `ci-local`
(= `.venv\Scripts\python.exe scripts\ci_local.py`). Yalnız testler:
`.venv\Scripts\python.exe -m pytest -q`.

## Claude ile kullanım

Önerilen yol: yerel MCP sunucusu + Agent Skill (yukarıda, *Claude: MCP server and Agent Skill*).
MCP yoksa komut satırı kuralları: [CLAUDE_RULES.md](CLAUDE_RULES.md) (projelerin `CLAUDE.md`
dosyasına kopyalanacak kısa snippet de orada).

Özet: Claude belgeyi ve `.raw.json`'un tamamını context'ine **almaz**; dönüşümde yalnız durum ve
dosya adları, analiz istenirse `search` / `read_excerpt` ile küçük bir parça okunur.

## Dosyalar

```
PDFStruct\
├── pyproject.toml          paket tanımı, bağımlılıklar, extra'lar ([gui], [mcp]), script'ler
├── src\pdfstruct\
│   ├── __init__.py         sürüm (tek kaynak)
│   ├── service.py          run_job: CLI, GUI ve MCP'nin ortak dönüştürme servisi
│   ├── inputs\             girdi adapter'ları: text (txt, md), html, docx, image
│   ├── extract.py          PDF çıkarımı, kalite skoru, raw JSON yazımı, parser hook
│   ├── ocr.py              OCR backend (PaddleOCR, aynı süreçte, tembel yükleme)
│   ├── export.py           raw.json → html/txt/md/csv/xlsx/docx/jsonl/sqlite/pdf
│   ├── pdfwriter.py        PDF çıktısı (reportlab)
│   ├── cli.py              pdfstruct + alias komutları, girdi/çıktı yolu çözümleme
│   ├── interactive.py      terminal menüleri (bare pdfstruct)
│   ├── mcp_server.py       yerel MCP sunucusu (pdfstruct-mcp)
│   └── gui\                masaüstü penceresi (pdfstruct-gui): state, worker, window, app
├── skills\pdfstruct\SKILL.md   Agent Skill (yalnız talimat)
├── integrations\claude-desktop\   Claude for Windows .mcpb başlatıcısı (manifest + .cmd; runtime içermez)
├── packaging\windows\     PyInstaller spec + build_portable.py (Windows portable klasör)
├── install-windows.cmd     wheel'den %USERPROFILE%\.local\pdfstruct\v<sürüm> kurulumu (Claude bunu kullanır)
├── setup-windows.cmd       geliştirme kurulumu: repo içi .venv (editable) + pencereyi açma
├── pdfstruct.cmd, pdfjson.cmd … pdfsqlite.cmd, pdfstruct-gui.cmd, pdfstruct-mcp.cmd
│                           venv'i kendisi seçen Windows komutları
├── pdfexport.cmd, pdf2json.cmd   ortak başlatıcı / alt seviye komut
├── scripts\ci_local.py, ci-local.cmd, scripts\build_skill_zip.py
├── scripts\install-windows.ps1, scripts\build_claude_windows.py
├── config.example.json     ayar örneği
├── schemas\raw_document.schema.json   raw JSON şeması (1.0 PDF, 1.1 diğer girdiler)
├── examples\example_parser.py
├── docs\MASTER_ARCHITECTURE.md
├── tests\
├── README.md, CHANGELOG.md, LICENSE, THIRD_PARTY_NOTICES.md
└── CLAUDE.md, CLAUDE_RULES.md
```
