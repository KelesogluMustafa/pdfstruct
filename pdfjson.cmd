@echo off
rem pdfjson [file.pdf ^| folder] [options] - no argument: all PDFs in this folder (else .\pdf).
rem Output: "output" next to the PDFs. Options pass through (--force-ocr, --output, --parser ...).
"%~dp0.venv\Scripts\python.exe" "%~dp0pdf_cli.py" json %*
