@echo off
rem Text or Markdown to documents without activating the venv: pdfstruct-create --name NAME --content-file FILE
"%~dp0.venv\Scripts\python.exe" -c "import sys; from pdfstruct.cli import create; sys.exit(create())" %*
