@echo off
rem Shared launcher for pdfhtml / pdftxt / pdfmd / pdfcsv / pdfxlsx / pdfdocx / pdfjsonl / pdfsqlite.
rem Same input rules as pdfjson; reuses output\*.raw.json and extracts only where it is missing.
"%~dp0.venv\Scripts\python.exe" "%~dp0pdf_cli.py" %*
