@echo off
rem Low-level extraction with explicit --input / --output.
"%~dp0.venv\Scripts\python.exe" -m pdfstruct.extract %*
