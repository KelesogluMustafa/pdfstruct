@echo off
rem Main CLI without activating the venv: pdfstruct [--format FORMAT] [file.pdf ^| folder]
"%~dp0.venv\Scripts\python.exe" -m pdfstruct %*
