@echo off
rem Runs pdf_to_json.py with the tool's own venv, from any folder.
"%~dp0.venv\Scripts\python.exe" "%~dp0pdf_to_json.py" %*
