@echo off
rem Checks GitHub for a newer stable PDFStruct release and installs it after you confirm.
rem   update-windows.cmd            check, ask, update (the old version is kept)
rem   update-windows.cmd -Check     only show whether an update exists
rem   update-windows.cmd -Rollback  switch back to the previously active version
rem   update-windows.cmd -List      show installed versions
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update-windows.ps1" %*
exit /b %ERRORLEVEL%
