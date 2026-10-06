@echo off
rem Legacy shared launcher for pdfhtml / pdftxt / ... / pdfsqlite: pdfexport <format> [args]
"%~dp0.venv\Scripts\python.exe" -m pdfstruct --format %*
