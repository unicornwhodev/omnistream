[CmdletBinding()]
param(
  [string]$InstallRoot = "",
  [switch]$RemoveConfiguration,
  [switch]$RemoveWorkspace,
  [switch]$Force
)
$ErrorActionPreference = "Stop"
$OmniStreamHome = if ($env:OMNISTREAM_HOME) { [IO.Path]::GetFullPath($env:OMNISTREAM_HOME) } else { [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "OmniStream")) }
$configFile = Join-Path $OmniStreamHome "config\omnistream.json"
$config = $null
if (Test-Path -LiteralPath $configFile -PathType Leaf) { try { $config = Get-Content -LiteralPath $configFile -Raw | ConvertFrom-Json } catch {} }
if (-not $InstallRoot) { $InstallRoot = Join-Path $OmniStreamHome "plugin" }
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
function Test-PathOverlap([string]$First, [string]$Second) {
  $a = [IO.Path]::GetFullPath($First).TrimEnd('\', '/')
  $b = [IO.Path]::GetFullPath($Second).TrimEnd('\', '/')
  return $a.Equals($b, [StringComparison]::OrdinalIgnoreCase) -or $a.StartsWith($b + '\', [StringComparison]::OrdinalIgnoreCase) -or $b.StartsWith($a + '\', [StringComparison]::OrdinalIgnoreCase)
}
function Assert-RemovalTarget([string]$Target, [string[]]$ProtectedPaths) {
  $absolute = [IO.Path]::GetFullPath($Target)
  if ($absolute.TrimEnd('\', '/') -eq [IO.Path]::GetPathRoot($absolute).TrimEnd('\', '/')) { throw "Refusing to remove a drive root: $absolute" }
  if (Test-Path -LiteralPath $absolute) {
    if ((Get-Item -LiteralPath $absolute -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing to remove a linked directory: $absolute" }
  }
  foreach ($protected in $ProtectedPaths) {
    if ($protected -and (Test-PathOverlap $absolute $protected)) { throw "Removal target overlaps a preserved path: $absolute / $protected" }
  }
}
$preservedPaths = @((Join-Path $OmniStreamHome "external"))
if ($config) {
  if ($config.PSObject.Properties['kitRoot'] -and $config.kitRoot) { $preservedPaths += [string]$config.kitRoot }
  if ($config.PSObject.Properties['assetRoots']) { $preservedPaths += @($config.assetRoots) }
}
Assert-RemovalTarget $InstallRoot $preservedPaths
if (Test-Path -LiteralPath $InstallRoot) {
  $packageFile = Join-Path $InstallRoot "package.json"
  $pluginFile = Join-Path $InstallRoot ".codex-plugin\plugin.json"
  if (-not (Test-Path -LiteralPath $packageFile -PathType Leaf) -or -not (Test-Path -LiteralPath $pluginFile -PathType Leaf)) { throw "InstallRoot is not an OmniStream installation: $InstallRoot" }
  if ((Get-Content -LiteralPath $packageFile -Raw | ConvertFrom-Json).name -ne 'omnistream-for-codex' -or (Get-Content -LiteralPath $pluginFile -Raw | ConvertFrom-Json).name -ne 'omnistream-for-codex') { throw "InstallRoot belongs to another product: $InstallRoot" }
}
if ($RemoveWorkspace -and $config -and $config.workspaceRoot) {
  Assert-RemovalTarget ([string]$config.workspaceRoot) ($preservedPaths + @($OmniStreamHome, $InstallRoot))
}
if ($RemoveConfiguration) {
  foreach ($ownedName in @("config", "logs", "state", "cache")) {
    Assert-RemovalTarget (Join-Path $OmniStreamHome $ownedName) $preservedPaths
  }
}
if (-not $Force) {
  $answer = (Read-Host "Supprimer OmniStream de '$InstallRoot' ? Le runtime NVIDIA externe ne sera PAS supprimé. [O/N]").ToUpperInvariant()
  if ($answer -ne "O") { Write-Host "Désinstallation annulée."; exit 0 }
}
if ($config -and $RemoveWorkspace -and $config.workspaceRoot -and (Test-Path -LiteralPath ([string]$config.workspaceRoot))) {
  Remove-Item -LiteralPath ([string]$config.workspaceRoot) -Recurse -Force
}
if (Test-Path -LiteralPath $InstallRoot) { Remove-Item -LiteralPath $InstallRoot -Recurse -Force }
if ($RemoveConfiguration -and (Test-Path -LiteralPath $OmniStreamHome)) {
  # Never recursively remove OmniStreamHome: Feature-mode NVIDIA checkouts live
  # under external\ and remain third-party/user-owned even during a full
  # OmniStream configuration cleanup.
  foreach ($ownedName in @("config", "logs", "state", "cache")) {
    $ownedPath = Join-Path $OmniStreamHome $ownedName
    if (Test-Path -LiteralPath $ownedPath) { Remove-Item -LiteralPath $ownedPath -Recurse -Force }
  }
  $userOmniStreamHome = [Environment]::GetEnvironmentVariable("OMNISTREAM_HOME", "User")
  if ($userOmniStreamHome -and [string]::Equals([IO.Path]::GetFullPath($userOmniStreamHome), $OmniStreamHome, [StringComparison]::OrdinalIgnoreCase)) {
    [Environment]::SetEnvironmentVariable("OMNISTREAM_HOME", $null, "User")
  }
} else {
  $stateDir = Join-Path $OmniStreamHome "state"
  if (Test-Path -LiteralPath $stateDir) {
    $record = [ordered]@{ schemaVersion = 1; phase = "uninstalled"; updatedAt = (Get-Date).ToUniversalTime().ToString("o"); installRoot = $InstallRoot }
    [IO.File]::WriteAllText((Join-Path $stateDir "install-state.json"), ($record | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
  }
}
$externalPath = Join-Path $OmniStreamHome "external"
Write-Host "OmniStream supprimé. Les composants NVIDIA/Kit externes n'ont pas été modifiés." -ForegroundColor Green
if (Test-Path -LiteralPath $externalPath) { Write-Host "Dépendances externes préservées: $externalPath" -ForegroundColor DarkGray }
