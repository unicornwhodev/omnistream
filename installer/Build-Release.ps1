[CmdletBinding()]
param(
  [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$package = Get-Content -LiteralPath (Join-Path $ProjectRoot "package.json") -Raw | ConvertFrom-Json
$version = [string]$package.version
if (-not $OutputRoot) { $OutputRoot = Join-Path $ProjectRoot "release" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$stageName = "omnistream-for-codex-$version"
$stage = Join-Path $OutputRoot $stageName
$zip = Join-Path $OutputRoot ("$stageName.zip")

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

$excludeDirs = @(
  (Join-Path $ProjectRoot ".git"),
  (Join-Path $ProjectRoot "release"),
  $OutputRoot,
  (Join-Path $ProjectRoot "web\node_modules"),
  (Join-Path $ProjectRoot "web\dist"),
  (Join-Path $ProjectRoot "mcp\web-dist"),
  (Join-Path $ProjectRoot ".playwright-cli"),
  (Join-Path $ProjectRoot "test-results"),
  (Join-Path $ProjectRoot "tests\__pycache__"),
  (Join-Path $ProjectRoot "playwright-report"),
  (Join-Path $ProjectRoot "runtime\bridge\omnistream.codex.bridge\omnistream\codex\bridge\__pycache__")
)
$excludeFiles = @("npm-debug.log", "*.log", "*.pid", "*.pyc")
& robocopy $ProjectRoot $stage /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD @excludeDirs /XF @excludeFiles | Out-Null
$copyExit = $LASTEXITCODE
if ($copyExit -ge 8) { throw "Release copy failed (robocopy $copyExit)." }

$forbiddenNames = @("node_modules", "web-dist", "_build", "extscache", "deps", "packman", "__pycache__")
$forbiddenExtensions = @(".exe", ".dll", ".pdb", ".so", ".dylib", ".lib", ".pyc")
$failures = @()
Get-ChildItem -LiteralPath $stage -Recurse -Force | ForEach-Object {
  if ($_.PSIsContainer -and $_.Name -in $forbiddenNames) { $failures += $_.FullName }
  if (-not $_.PSIsContainer -and $_.Extension.ToLowerInvariant() -in $forbiddenExtensions) { $failures += $_.FullName }
}
if ($failures.Count -gt 0) {
  Remove-Item -LiteralPath $stage -Recurse -Force
  throw ("Release boundary violation:`n" + ($failures -join "`n"))
}

Push-Location $stage
try {
  & node .\scripts\publication-audit.mjs
  if ($LASTEXITCODE -ne 0) { throw "Public publication audit failed in the clean release stage." }
} finally { Pop-Location }

$manifestFiles = Get-ChildItem -LiteralPath $stage -Recurse -File -Force | Where-Object { $_.Name -ne "release-manifest.json" } | Sort-Object FullName
$manifestEntries = @()
foreach ($file in $manifestFiles) {
  $relative = $file.FullName.Substring($stage.Length).TrimStart([char[]]"\/").Replace("\", "/")
  $fileHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  $manifestEntries += [ordered]@{ path = $relative; size = [int64]$file.Length; sha256 = $fileHash }
}
$releaseManifest = [ordered]@{
  schemaVersion = 1
  product = "omnistream-for-codex"
  version = $version
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  files = $manifestEntries
}
[IO.File]::WriteAllText((Join-Path $stage "release-manifest.json"), ($releaseManifest | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))

# Use .NET directly so hidden files (including plugin metadata) are never omitted.
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($stage, $zip, [IO.Compression.CompressionLevel]::Optimal, $true)
$archive = [IO.Compression.ZipFile]::OpenRead($zip)
try {
  foreach ($required in @(".codex-plugin/plugin.json", ".mcp.json", "release-manifest.json")) {
    $entry = $archive.GetEntry("$stageName/$required")
    if (-not $entry) { throw "The release archive is missing a required entry: $required" }
  }
} finally { $archive.Dispose() }
$hash = Get-FileHash -LiteralPath $zip -Algorithm SHA256
$hashPath = "$zip.sha256"
[IO.File]::WriteAllText($hashPath, ($hash.Hash.ToLowerInvariant() + "  " + [IO.Path]::GetFileName($zip) + "`r`n"), (New-Object Text.UTF8Encoding($false)))
Write-Host "Release: $zip" -ForegroundColor Green
Write-Host "SHA256:  $($hash.Hash.ToLowerInvariant())" -ForegroundColor DarkGray
