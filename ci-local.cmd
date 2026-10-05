@echo off
rem Local CI without activating the venv: ci-local
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\ci_local.py" %*
