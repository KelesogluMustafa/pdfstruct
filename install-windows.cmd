@echo off
rem Installs PDFStruct from a release wheel into %USERPROFILE%\.local\pdfstruct\v<version>.
rem Not linked to this folder; safe to run again. Options are passed on, e.g.
rem   install-windows.cmd -Wheel C:\Downloads\pdfstruct-0.2.1-py3-none-any.whl
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-windows.ps1" %*
exit /b %ERRORLEVEL%
