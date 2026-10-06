@echo off
rem Legacy wrapper (works without activating the venv). Same as: pdfstruct --format json
"%~dp0.venv\Scripts\python.exe" -m pdfstruct --format json %*
