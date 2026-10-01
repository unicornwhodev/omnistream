@echo off
setlocal
rem Use Windows PowerShell's default modules when invoked from PowerShell 7.
set "PSModulePath="
cd /d "%~dp0.."
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-OmniStream.ps1" %*
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
  echo.
  echo OmniStream installation failed with exit code %EXITCODE%.
)
exit /b %EXITCODE%
