@echo off
rem Desktop window without activating the venv: pdfstruct-gui [files or folders]
start "" "%~dp0.venv\Scripts\pythonw.exe" -m pdfstruct.gui.app %*
