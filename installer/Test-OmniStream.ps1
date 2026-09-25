[CmdletBinding()]
param(
  [string]$InstallRoot = "",
  [switch]$SkipRuntimeSmoke,
  [switch]$SkipKitTests
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (-not $InstallRoot) { $InstallRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..")) }
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$OmniStreamHome = if ($env:OMNISTREAM_HOME) { [IO.Path]::GetFullPath($env:OMNISTREAM_HOME) } else { [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "OmniStream")) }
$ConfigFile = Join-Path $OmniStreamHome "config\omnistream.json"
$StateDir = Join-Path $OmniStreamHome "state"
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$ReportFile = Join-Path $StateDir "validation-report.json"
$checks = New-Object System.Collections.Generic.List[object]
$startedAt = (Get-Date).ToUniversalTime().ToString("o")

function Invoke-Check([string]$Name, [scriptblock]$Action) {
  Write-Host ""; Write-Host "==> $Name" -ForegroundColor Green
  $start = Get-Date
  try {
    $global:LASTEXITCODE = 0
    & $Action
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "$Name a quitté avec le code $LASTEXITCODE." }
    $checks.Add([ordered]@{ name = $Name; ok = $true; durationMs = [int]((Get-Date) - $start).TotalMilliseconds; detail = "OK" })
  } catch {
    $checks.Add([ordered]@{ name = $Name; ok = $false; durationMs = [int]((Get-Date) - $start).TotalMilliseconds; detail = $_.Exception.Message })
    throw
  }
}

function Save-Report([bool]$Ok, [string]$Detail = "") {
  $report = [ordered]@{
    schemaVersion = 1
    ok = $Ok
    startedAt = $startedAt
    finishedAt = (Get-Date).ToUniversalTime().ToString("o")
    installRoot = $InstallRoot
    runtimeSmokeSkipped = [bool]$SkipRuntimeSmoke
    kitTestsSkipped = [bool]$SkipKitTests
    visualWebRtcVerified = $false
    codexHostVerified = $false
    productionReady = $false
    detail = $Detail
    checks = @($checks)
  }
  [IO.File]::WriteAllText($ReportFile, ($report | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
}

try {
  if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot "package.json") -PathType Leaf)) { throw "InstallRoot OmniStream invalide: $InstallRoot" }
  if (-not (Test-Path -LiteralPath $ConfigFile -PathType Leaf)) { throw "Configuration OmniStream absente: $ConfigFile" }
  $config = Get-Content -LiteralPath $ConfigFile -Raw | ConvertFrom-Json
  $kitRoot = [string]$config.kitRoot
  if (-not $kitRoot) { throw "kitRoot n'est pas configuré." }

  Push-Location $InstallRoot
  try {
    Invoke-Check "Contrats source / TypeScript" { & npm run check }
    Invoke-Check "Tests MCP et sécurité" { & npm test }
    Invoke-Check "Build et contrats du panneau" { & npm run test:web }
    Invoke-Check "Reconstruction finale du panneau" { & npm run build:web }
    Invoke-Check "Diagnostic strict" { & node .\scripts\doctor.mjs --strict }

    if (-not $SkipKitTests) {
      $repoBat = Join-Path $kitRoot "repo.bat"
      if (-not (Test-Path -LiteralPath $repoBat -PathType Leaf)) { throw "repo.bat absent dans le KitRoot: $kitRoot" }
      Invoke-Check "Tests NVIDIA Kit project" {
        Push-Location $kitRoot
        try { & .\repo.bat test } finally { Pop-Location }
      }
    }

    if (-not $SkipRuntimeSmoke) {
      Invoke-Check "Smoke-test RTX / Kit / WebRTC / bridge / USD" { & npm run test:runtime }
    }
  } finally { Pop-Location }

  Save-Report $true "Contrôles automatiques terminés. Décodage WebRTC réel et hôte Codex à valider séparément."
  Write-Host ""; Write-Host "VALIDATION OMNISTREAM: PASS" -ForegroundColor Green
  Write-Host "Rapport: $ReportFile" -ForegroundColor DarkGray
  exit 0
} catch {
  Save-Report $false $_.Exception.Message
  Write-Host ""; Write-Host "VALIDATION OMNISTREAM: FAIL" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  Write-Host "Rapport: $ReportFile" -ForegroundColor DarkGray
  exit 1
}
