@echo off
setlocal
set "PSModulePath="
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Uninstall-OmniStream.ps1" %*
exit /b %ERRORLEVEL%
