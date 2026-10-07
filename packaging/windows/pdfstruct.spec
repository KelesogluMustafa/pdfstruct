# PyInstaller spec: PDFStruct portable folder for Windows (proof of build).
#   pyinstaller --noconfirm --distpath <out> --workpath <work> pdfstruct.spec
# One folder, two programs that share everything:
#   PDFStruct.exe       the desktop window (no console)
#   pdfstruct-cli.exe   the command line (pdfstruct ... --format ...)
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

HERE = os.path.dirname(os.path.abspath(SPEC))

datas, binaries, hiddenimports = [], [], []
for package in ("paddle", "paddleocr", "paddlex", "pypdfium2", "pypdfium2_raw"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
datas += collect_data_files("reportlab")   # Vera fonts used by the PDF output
datas += collect_data_files("docx")        # default .docx template
for package in ("paddlex", "paddleocr"):   # paddlex checks its dependencies through metadata
    datas += copy_metadata(package, recursive=True)
datas += copy_metadata("pdfstruct")

# paddlex verifies its "ocr-core" extra at run time through importlib.metadata and imports
# these packages lazily, so both the metadata and the modules must be named explicitly.
PADDLEX_DEPS = ["PyYAML", "aistudio-sdk", "chardet", "colorlog", "filelock", "huggingface-hub",
                "imagesize", "modelscope", "numpy", "opencv-contrib-python", "packaging", "pandas",
                "pillow", "prettytable", "py-cpuinfo", "pyclipper", "pydantic", "pypdfium2",
                "python-bidi", "requests", "ruamel.yaml", "shapely", "typing-extensions", "ujson",
                "paddlepaddle"]
for package in PADDLEX_DEPS:
    datas += copy_metadata(package)
for package in ("shapely", "pyclipper", "bidi", "imagesize", "cv2"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += ["pdfstruct.inputs.text", "pdfstruct.inputs.html", "pdfstruct.inputs.docx",
                  "pdfstruct.inputs.image", "pdfstruct.pdfwriter", "pdfstruct.gui.window",
                  "pdfstruct.gui.worker"]

EXCLUDES = ["tkinter", "pytest", "PyInstaller", "mcp", "IPython", "matplotlib"]


def analysis(script):
    return Analysis([os.path.join(HERE, script)], pathex=[], binaries=binaries, datas=datas,
                    hiddenimports=hiddenimports, excludes=EXCLUDES, noarchive=False)


gui = analysis("entry_gui.py")
cli = analysis("entry_cli.py")

gui_pyz = PYZ(gui.pure)
cli_pyz = PYZ(cli.pure)
gui_exe = EXE(gui_pyz, gui.scripts, [], exclude_binaries=True, name="PDFStruct", console=False)
cli_exe = EXE(cli_pyz, cli.scripts, [], exclude_binaries=True, name="pdfstruct-cli", console=True)

COLLECT(gui_exe, gui.binaries, gui.datas, cli_exe, cli.binaries, cli.datas, name="PDFStruct")
