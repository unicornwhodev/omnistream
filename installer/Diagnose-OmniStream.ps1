[CmdletBinding()]
param([string]$InstallRoot = "")
$ErrorActionPreference = "Stop"
if (-not $InstallRoot) { $InstallRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..")) }
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
Push-Location $InstallRoot
try {
  & node .\scripts\doctor.mjs --strict
  $code = $LASTEXITCODE
  $home = if ($env:OMNISTREAM_HOME) { $env:OMNISTREAM_HOME } else { Join-Path $env:LOCALAPPDATA "OmniStream" }
  $state = Join-Path $home "state\install-state.json"
  $validation = Join-Path $home "state\validation-report.json"
  Write-Host ""; Write-Host "État installation: $state" -ForegroundColor DarkGray
  Write-Host "Dernière validation: $validation" -ForegroundColor DarkGray
  exit $code
} finally { Pop-Location }
