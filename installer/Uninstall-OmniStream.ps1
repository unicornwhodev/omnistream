[CmdletBinding()]
param(
  [string]$InstallRoot = "",
  [switch]$RemoveConfiguration,
  [switch]$RemoveWorkspace,
  [switch]$Force
)
$ErrorActionPreference = "Stop"
$home = if ($env:OMNISTREAM_HOME) { [IO.Path]::GetFullPath($env:OMNISTREAM_HOME) } else { [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "OmniStream")) }
$configFile = Join-Path $home "config\omnistream.json"
$config = $null
if (Test-Path -LiteralPath $configFile -PathType Leaf) { try { $config = Get-Content -LiteralPath $configFile -Raw | ConvertFrom-Json } catch {} }
if (-not $InstallRoot) { $InstallRoot = Join-Path $home "plugin" }
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
if (-not $Force) {
  $answer = (Read-Host "Supprimer OmniStream de '$InstallRoot' ? Le runtime NVIDIA externe ne sera PAS supprimé. [O/N]").ToUpperInvariant()
  if ($answer -ne "O") { Write-Host "Désinstallation annulée."; exit 0 }
}
if ($config -and $RemoveWorkspace -and $config.workspaceRoot -and (Test-Path -LiteralPath ([string]$config.workspaceRoot))) {
  Remove-Item -LiteralPath ([string]$config.workspaceRoot) -Recurse -Force
}
if (Test-Path -LiteralPath $InstallRoot) { Remove-Item -LiteralPath $InstallRoot -Recurse -Force }
if ($RemoveConfiguration -and (Test-Path -LiteralPath $home)) {
  # Never recursively remove OmniStreamHome: Feature-mode NVIDIA checkouts live
  # under external\ and remain third-party/user-owned even during a full
  # OmniStream configuration cleanup.
  foreach ($ownedName in @("config", "logs", "state", "cache")) {
    $ownedPath = Join-Path $home $ownedName
    if (Test-Path -LiteralPath $ownedPath) { Remove-Item -LiteralPath $ownedPath -Recurse -Force }
  }
  [Environment]::SetEnvironmentVariable("OMNISTREAM_HOME", $null, "User")
} else {
  $stateDir = Join-Path $home "state"
  if (Test-Path -LiteralPath $stateDir) {
    $record = [ordered]@{ schemaVersion = 1; phase = "uninstalled"; updatedAt = (Get-Date).ToUniversalTime().ToString("o"); installRoot = $InstallRoot }
    [IO.File]::WriteAllText((Join-Path $stateDir "install-state.json"), ($record | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
  }
}
$externalPath = Join-Path $home "external"
Write-Host "OmniStream supprimé. Les composants NVIDIA/Kit externes n'ont pas été modifiés." -ForegroundColor Green
if (Test-Path -LiteralPath $externalPath) { Write-Host "Dépendances externes préservées: $externalPath" -ForegroundColor DarkGray }
