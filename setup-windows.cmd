@echo off
rem PDFStruct setup for Windows. Safe to run again: it only creates .venv in this folder
rem (if missing) and installs/updates PDFStruct with the desktop window and MCP server there.
rem It never touches the system Python packages, your documents or ~/.pdfstruct.
rem   setup-windows.cmd              install or update, then open the window
rem   setup-windows.cmd --no-launch  install or update only
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto install
echo Creating the Python environment in %CD%\.venv ...
where py >nul 2>nul
if %ERRORLEVEL%==0 (py -3 -m venv .venv) else (python -m venv .venv)
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo ERROR: could not create .venv. Install Python 3.10-3.13 from https://www.python.org/downloads/
    echo and run this file again.
    exit /b 1
)

:install
".venv\Scripts\python.exe" --version
echo Installing PDFStruct with the desktop window and MCP server (first run downloads packages) ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -e ".[gui,mcp]"
if errorlevel 1 (
    echo.
    echo ERROR: installation failed. See the messages above.
    exit /b 1
)
echo.
echo Installed:
".venv\Scripts\python.exe" -m pdfstruct --version
echo   Window:   pdfstruct-gui.cmd   (or .venv\Scripts\pdfstruct-gui.exe)
echo   Terminal: pdfstruct.cmd, pdfjson.cmd, ...
echo   Claude:   claude mcp add --scope user pdfstruct -- "%CD%\.venv\Scripts\pdfstruct-mcp.exe"
if /i "%~1"=="--no-launch" exit /b 0
start "" ".venv\Scripts\pythonw.exe" -m pdfstruct.gui.app
exit /b 0
