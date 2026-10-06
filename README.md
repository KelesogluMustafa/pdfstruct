# PDFStruct

PDFStruct converts PDFs locally using native text extraction or OCR and exports
structured content to JSON, HTML, TXT, Markdown, CSV, XLSX, DOCX, JSONL and SQLite.

## Quick start

Local development install (not published on PyPI yet), from the repository folder:

```
pip install -e .
```

Usage:

```
pdfstruct belge.pdf
pdfstruct "C:\Belgeler"
pdfstruct --format xlsx belge.pdf
```

`--format` is one of `json` (default), `html`, `txt`, `md`, `csv`, `xlsx`, `docx`, `jsonl`,
`sqlite`. Each format also has a short alias that works exactly the same way:

```
pdfjson belge.pdf
pdfxlsx belge.pdf
```

Aliases: `pdfjson`, `pdfhtml`, `pdftxt`, `pdfmd`, `pdfcsv`, `pdfxlsx`, `pdfdocx`, `pdfjsonl`,
`pdfsqlite`.

PDFStruct automatically uses native PDF text when available and OCR when needed: each page
gets a text-layer quality score, and pages that fail it (scans, photos) go through OCR. You
never have to choose. `--force-ocr` runs OCR on every page, `--native-only` never runs it.

OCR runs inside the same Python environment (PaddleOCR, CPU by default; no CUDA, no GPU
and no separate installation needed). The OCR packages are installed together with
PDFStruct on platforms that have official PaddlePaddle CPU wheels: Windows x86_64,
Linux x86_64 and macOS Apple Silicon, with Python 3.9–3.13. On the first OCR run the two
models (about 70 MB) are downloaded once to `~/.pdfstruct/models` and reused afterwards;
you will see `Preparing OCR models for first use...`. Elsewhere PDFStruct still installs and
extracts native text; a page that would need OCR is reported as `OCR support is not
available on this platform` and listed under `REVIEW_PAGES`.

Verified so far: Windows 11 x86_64 with Python 3.13 (native extraction and CPU OCR).
Other platforms are covered by the published wheels but have not been tested yet.

## Project Principles

PDFStruct is free and open source.
All core functionality is available without payment, accounts, usage limits or tracking.
Voluntary donations may support future development, but never unlock features.

## Development

```
pip install -e ".[dev]"
python scripts/ci_local.py
```

`scripts/ci_local.py` (Windows shortcut: `ci-local`) runs the whole local CI in one go:
import and version check, test suite, wheel + sdist build and validation, a clean temporary
venv with the built wheel, `--help` / `--version` for all 10 console scripts, a small native
end-to-end run, and a targeted OCR check that reports `PASS`, `SKIPPED` (no OCR environment)
or `FAIL`. Output is one line per step; full logs appear only for failing steps.

---

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
C:\Users\musta\Projects\_tools\PDFStruct\pdf2json.cmd --input "C:\...\pdf" --output "C:\...\output"
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

```
cd C:\Users\musta\Projects\_tools\PDFStruct
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Bu klasördeki `.cmd` dosyaları (`pdfjson.cmd`, `pdfhtml.cmd`, ...) bu `.venv`'i kullanır ve
klasör USER PATH'te olduğu için venv'i aktive etmeden her yerden çalışır. Başka bir Python
ortamına `pip install -e .` ile kurulduğunda aynı komutlar o ortamın kendi console script'leri
olarak gelir (Windows/macOS/Linux).

Testler, derleme ve kurulum doğrulamasının tamamı tek komutla: `ci-local`
(= `.venv\Scripts\python.exe scripts\ci_local.py`). Yalnız testler:
`.venv\Scripts\python.exe -m pytest -q`.

## Claude ile kullanım

Kurallar: [CLAUDE_RULES.md](CLAUDE_RULES.md) (projelerin `CLAUDE.md` dosyasına
kopyalanacak kısa snippet de orada).

Özet: Claude PDF'i ve `.raw.json`'un tamamını context'ine **almaz**; yalnızca terminal özetini,
`*.summary.json` dosyalarını ve `review_pages` sayfalarını okur.

## Dosyalar

```
PDFStruct\
├── pyproject.toml          paket tanımı, bağımlılıklar, console script'ler
├── src\pdfstruct\
│   ├── __init__.py         sürüm (tek kaynak)
│   ├── cli.py              pdfstruct + alias komutları, girdi/çıktı yolu çözümleme
│   ├── extract.py          native çıkarım, kalite skoru, OCR istemcisi, parser hook
│   ├── export.py           raw.json → html/txt/md/csv/xlsx/docx/jsonl/sqlite
│   └── ocr.py              OCR backend (PaddleOCR, aynı süreçte, tembel yükleme)
├── pdfstruct.cmd, pdfjson.cmd … pdfsqlite.cmd   venv'i kendisi seçen Windows komutları
├── pdfexport.cmd, pdf2json.cmd                ortak başlatıcı / alt seviye komut
├── scripts\ci_local.py, ci-local.cmd         tek komutluk local CI
├── config.example.json     ayar örneği
├── schemas\raw_document.schema.json
├── examples\example_parser.py
├── tests\
├── README.md, CHANGELOG.md, LICENSE
└── CLAUDE_RULES.md
```
