@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Diagnose-OmniStream.ps1" %*
exit /b %ERRORLEVEL%
