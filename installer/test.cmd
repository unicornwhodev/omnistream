@echo off
setlocal
set "PSModulePath="
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Test-OmniStream.ps1" %*
exit /b %ERRORLEVEL%
