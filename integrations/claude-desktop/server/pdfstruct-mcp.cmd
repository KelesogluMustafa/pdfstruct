@echo off
rem PDFStruct launcher: starts the 0.2.1 runtime installed by scripts\install-windows.ps1.
rem Claude starts the same executable directly (see manifest.json); this file is for manual checks.
set "PS_EXE=%USERPROFILE%\.local\pdfstruct\v0.2.1\Scripts\pdfstruct-mcp.exe"
if not exist "%PS_EXE%" (
  echo PDFStruct runtime not found: %PS_EXE% 1>&2
  exit /b 1
)
"%PS_EXE%" %*
