@echo off
setlocal
set "PSModulePath="
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-OmniStream.ps1" -RuntimeChannel Existing -SkipNvidiaRuntimeSetup %*
exit /b %ERRORLEVEL%
