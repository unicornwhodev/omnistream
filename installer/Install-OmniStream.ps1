[CmdletBinding()]
param(
  [string]$InstallRoot = "",
  [string]$OmniStreamHome = "",
  [string]$KitRoot = "",
  [string]$WorkspaceRoot = "",
  [string]$AssetRoot = "",
  [ValidateSet("Auto", "Production", "Feature", "Existing")]
  [string]$RuntimeChannel = "Auto",
  [switch]$SkipNvidiaRuntimeSetup,
  [switch]$SkipValidation,
  [switch]$SkipRuntimeSmoke
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PackageRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OmniStreamHome) { $OmniStreamHome = Join-Path $env:LOCALAPPDATA "OmniStream" }
$OmniStreamHome = [IO.Path]::GetFullPath($OmniStreamHome)
$ConfigDir = Join-Path $OmniStreamHome "config"
$ConfigFile = Join-Path $ConfigDir "omnistream.json"
$StateDir = Join-Path $OmniStreamHome "state"
$StateFile = Join-Path $StateDir "install-state.json"
$ExternalRoot = Join-Path $OmniStreamHome "external"

$Official = @{
  Node = "https://nodejs.org/en/download"
  Git = "https://git-scm.com/download/win"
  Driver = "https://www.nvidia.com/Download/index.aspx"
  KitFeatureRepo = "https://github.com/NVIDIA-Omniverse/kit-app-template"
  KitGuide = "https://docs.omniverse.nvidia.com/kit/docs/kit-app-template/latest/docs/intro.html"
  KitProduction = "https://catalog.ngc.nvidia.com/orgs/nvidia/omniverse/resources/kit-sdk-windows-pb26h1/-"
  KitProductionInfo = "https://docs.omniverse.nvidia.com/dev-overview/latest/branches/production.html"
}

function Get-ObjectProperty($Object, [string]$Name) {
  if ($null -eq $Object) { return $null }
  $property = $Object.PSObject.Properties[$Name]
  if ($null -eq $property) { return $null }
  return $property.Value
}

function Read-JsonFile([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
  try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { return $null }
}

$ExistingConfig = Read-JsonFile $ConfigFile
$ExistingState = Read-JsonFile $StateFile

function Get-RecoveredValue([string]$ConfigName, [string]$StateName = "") {
  $fromConfig = Get-ObjectProperty $ExistingConfig $ConfigName
  if ($fromConfig) { return $fromConfig }
  if (-not $StateName) { $StateName = $ConfigName }
  return Get-ObjectProperty $ExistingState $StateName
}

if (-not $PSBoundParameters.ContainsKey("InstallRoot")) {
  $recoveredInstallRoot = Get-ObjectProperty $ExistingState "installRoot"
  if ($recoveredInstallRoot) { $InstallRoot = [string]$recoveredInstallRoot }
}
if (-not $PSBoundParameters.ContainsKey("KitRoot")) {
  $recoveredKitRoot = Get-RecoveredValue "kitRoot"
  if ($recoveredKitRoot) { $KitRoot = [string]$recoveredKitRoot }
}
if (-not $PSBoundParameters.ContainsKey("WorkspaceRoot")) {
  $recoveredWorkspaceRoot = Get-RecoveredValue "workspaceRoot"
  if ($recoveredWorkspaceRoot) { $WorkspaceRoot = [string]$recoveredWorkspaceRoot }
}
if (-not $PSBoundParameters.ContainsKey("AssetRoot")) {
  $existingAssetRoots = Get-ObjectProperty $ExistingConfig "assetRoots"
  if ($existingAssetRoots -and @($existingAssetRoots).Count -gt 0) {
    $AssetRoot = [string]@($existingAssetRoots)[0]
  } else {
    $recoveredAssetRoot = Get-ObjectProperty $ExistingState "assetRoot"
    if ($recoveredAssetRoot) { $AssetRoot = [string]$recoveredAssetRoot }
  }
}
$existingStreamKit = Get-RecoveredValue "streamKitRelativePath"
$script:StreamKitRelativePath = if ($existingStreamKit) { [string]$existingStreamKit } else { $null }
if (-not $PSBoundParameters.ContainsKey("RuntimeChannel")) {
  $recoveredRuntimeChannel = Get-RecoveredValue "runtimeChannel"
  if ($recoveredRuntimeChannel -in @("Production", "Feature", "Existing")) { $RuntimeChannel = [string]$recoveredRuntimeChannel }
}

if (-not $InstallRoot) { $InstallRoot = Join-Path $OmniStreamHome "plugin" }
if (-not $WorkspaceRoot) { $WorkspaceRoot = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "OmniStream\Workspace" }
if (-not $AssetRoot) { $AssetRoot = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "OmniStream\Assets" }

$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$WorkspaceRoot = [IO.Path]::GetFullPath($WorkspaceRoot)
$AssetRoot = [IO.Path]::GetFullPath($AssetRoot)
if ($KitRoot) { $KitRoot = [IO.Path]::GetFullPath($KitRoot) }

function Write-Step([string]$Title, [string]$Detail = "") {
  Write-Host ""
  Write-Host ("==> " + $Title) -ForegroundColor Green
  if ($Detail) { Write-Host $Detail -ForegroundColor DarkGray }
}

function Save-InstallState([string]$Phase, [string]$Detail = "") {
  New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
  $state = [ordered]@{
    schemaVersion = 1
    phase = $Phase
    detail = $Detail
    updatedAt = (Get-Date).ToUniversalTime().ToString("o")
    installRoot = $InstallRoot
    kitRoot = $KitRoot
    workspaceRoot = $WorkspaceRoot
    assetRoot = $AssetRoot
    streamKitRelativePath = $script:StreamKitRelativePath
    runtimeChannel = $RuntimeChannel
  }
  [IO.File]::WriteAllText($StateFile, ($state | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding($false)))
}

function Refresh-ProcessPath {
  $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
  $user = [Environment]::GetEnvironmentVariable("Path", "User")
  $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ";"
}

function Get-VersionTuple([string]$Text) {
  $match = [regex]::Match($Text, '(\d+)\.(\d+)\.(\d+)')
  if (-not $match.Success) { return $null }
  return [Version]("{0}.{1}.{2}" -f $match.Groups[1].Value, $match.Groups[2].Value, $match.Groups[3].Value)
}

function Test-Tool([string]$Name, [string[]]$CommandArguments, [Version]$Minimum) {
  Refresh-ProcessPath
  $cmd = Get-Command $Name -ErrorAction SilentlyContinue
  if (-not $cmd) { return $false }
  try {
    $raw = (& $Name @CommandArguments 2>&1 | Out-String).Trim()
    if (-not $Minimum) { return $true }
    $version = Get-VersionTuple $raw
    return ($version -and $version -ge $Minimum)
  } catch { return $false }
}

function Wait-ForExternalInstall([string]$Name, [string]$Url, [scriptblock]$Probe) {
  Save-InstallState "waiting-external-dependency" $Name
  Write-Warning "$Name est requis mais n'est pas disponible. OmniStream ne redistribue pas cet installateur."
  Start-Process $Url | Out-Null
  while ($true) {
    Refresh-ProcessPath
    if (& $Probe) { break }
    $answer = Read-Host "Installez $Name depuis la source officielle ouverte, puis [R] revalider, [O] rouvrir, [Q] quitter"
    switch ($answer.ToUpperInvariant()) {
      "O" { Start-Process $Url | Out-Null }
      "Q" { throw "Installation interrompue: $Name reste requis." }
      default { }
    }
  }
  Write-Host "$Name détecté. Reprise de l'installation OmniStream." -ForegroundColor Green
}

function Test-PackageIntegrity {
  $manifestPath = Join-Path $PackageRoot "release-manifest.json"
  if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    Write-Host "Manifest d'intégrité absent (arbre source/dev)." -ForegroundColor DarkGray
    return
  }
  Write-Step "Intégrité du package" $manifestPath
  $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
  if ([int]$manifest.schemaVersion -ne 1) { throw "Version de release-manifest.json non prise en charge." }
  $expected = @{}
  foreach ($entry in @($manifest.files)) {
    $relative = [string]$entry.path
    $segments = @($relative -split '[\\/]')
    if (-not $relative -or [IO.Path]::IsPathRooted($relative) -or $segments -contains "..") { throw "Chemin invalide dans release-manifest.json: $relative" }
    $normalized = $relative.Replace("\", "/")
    if ($expected.ContainsKey($normalized)) { throw "Entrée dupliquée dans release-manifest.json: $relative" }
    $expected[$normalized] = $true
    $full = [IO.Path]::GetFullPath((Join-Path $PackageRoot ($relative.Replace("/", "\"))))
    if (-not $full.StartsWith(($PackageRoot.TrimEnd("\") + "\"), [StringComparison]::OrdinalIgnoreCase)) { throw "Le manifest tente de sortir du package: $relative" }
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "Fichier du package manquant: $relative" }
    $file = Get-Item -LiteralPath $full
    if ([int64]$file.Length -ne [int64]$entry.size) { throw "Taille invalide pour $relative" }
    $hash = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne ([string]$entry.sha256).ToLowerInvariant()) { throw "SHA-256 invalide pour $relative" }
  }

  # A release archive must not silently acquire executable source files that are
  # outside the signed manifest. Generated local build/dependency directories are
  # tolerated only when the installer is rerun from an already-installed tree.
  $allowedGeneratedPrefixes = @("web/node_modules/", "web/dist/", "mcp/web-dist/")
  $unexpected = @()
  Get-ChildItem -LiteralPath $PackageRoot -Recurse -File -Force | ForEach-Object {
    $relative = $_.FullName.Substring($PackageRoot.Length).TrimStart([char[]]"\/").Replace("\", "/")
    if ($relative -eq "release-manifest.json") { return }
    if ($expected.ContainsKey($relative)) { return }
    foreach ($prefix in $allowedGeneratedPrefixes) { if ($relative.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { return } }
    $unexpected += $relative
  }
  if ($unexpected.Count -gt 0) { throw ("Fichier(s) non signé(s) dans le package: `n" + ($unexpected -join "`n")) }
  Write-Host "Package vérifié: $(@($manifest.files).Count) fichier(s), aucun fichier source inattendu." -ForegroundColor Green
}

function Ensure-Prerequisites {
  Write-Step "Pré-vol système"
  if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw "L'installateur OmniStream cible Windows 10/11." }
  if (-not (Test-Tool "node" @("--version") ([Version]"20.18.1"))) {
    Wait-ForExternalInstall "Node.js 20.18.1+" $Official.Node { Test-Tool "node" @("--version") ([Version]"20.18.1") }
  }
  if (-not (Test-Tool "npm" @("--version") ([Version]"10.2.3"))) {
    Wait-ForExternalInstall "npm 10.2.3+" $Official.Node { Test-Tool "npm" @("--version") ([Version]"10.2.3") }
  }
  if (-not (Test-Tool "git" @("--version") ([Version]"2.40.0"))) {
    Wait-ForExternalInstall "Git" $Official.Git { Test-Tool "git" @("--version") ([Version]"2.40.0") }
  }
  if (-not (Get-Command "nvidia-smi" -ErrorAction SilentlyContinue)) {
    Wait-ForExternalInstall "pilote NVIDIA / nvidia-smi" $Official.Driver { [bool](Get-Command "nvidia-smi" -ErrorAction SilentlyContinue) }
  }
  try {
    $gpu = (& nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>$null | Select-Object -First 1)
    if ($gpu) { Write-Host "GPU: $gpu" -ForegroundColor DarkGray }
  } catch { }
  Save-InstallState "prerequisites-valid"
}

function Copy-OmniStreamSource {
  Write-Step "Installation atomique des sources OmniStream" $InstallRoot
  if ([string]::Equals($PackageRoot.TrimEnd('\'), $InstallRoot.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
    Write-Host "Le script s'exécute déjà depuis InstallRoot; aucune recopie nécessaire." -ForegroundColor DarkGray
    Save-InstallState "omnistream-sources-installed" "in-place"
    return
  }
  # Keep staging beside the destination so final Move-Item operations stay on
  # the same volume even when InstallRoot is customized to another drive.
  $installParent = Split-Path $InstallRoot -Parent
  New-Item -ItemType Directory -Force -Path $installParent | Out-Null
  $staging = Join-Path $installParent ".omnistream-plugin-staging"
  $backup = Join-Path $installParent ".omnistream-plugin-backup"
  foreach ($old in @($staging, $backup)) { if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Recurse -Force } }
  New-Item -ItemType Directory -Force -Path $staging | Out-Null
  $excludeDirs = @(
    (Join-Path $PackageRoot ".git"),
    (Join-Path $PackageRoot "web\node_modules"),
    (Join-Path $PackageRoot "web\dist"),
    (Join-Path $PackageRoot "mcp\web-dist"),
    (Join-Path $PackageRoot ".playwright-cli"),
    (Join-Path $PackageRoot "test-results"),
    (Join-Path $PackageRoot "tests\__pycache__"),
    (Join-Path $PackageRoot "playwright-report"),
    (Join-Path $PackageRoot "release"),
    (Join-Path $PackageRoot "runtime\bridge\omnistream.codex.bridge\omnistream\codex\bridge\__pycache__")
  )
  $excludeFiles = @("npm-debug.log", "*.pid", "*.log", "*.pyc")
  & robocopy $PackageRoot $staging /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP /XD @excludeDirs /XF @excludeFiles | Out-Null
  $code = $LASTEXITCODE
  if ($code -ge 8) { throw "La copie staging des sources OmniStream a échoué (robocopy $code)." }
  if (-not (Test-Path -LiteralPath (Join-Path $staging "package.json") -PathType Leaf)) { throw "Le staging OmniStream est incomplet." }
  if (Test-Path -LiteralPath $InstallRoot) { Move-Item -LiteralPath $InstallRoot -Destination $backup }
  try {
    Move-Item -LiteralPath $staging -Destination $InstallRoot
  } catch {
    if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $InstallRoot }
    throw
  }
  if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
  Save-InstallState "omnistream-sources-installed"
}

function Get-StreamingKitSource([string]$Root) {
  $apps = Join-Path $Root "source\apps"
  if (-not (Test-Path -LiteralPath $apps -PathType Container)) { return $null }
  $preferred = Get-ChildItem -LiteralPath $apps -Filter "omnistream*.kit" -File -ErrorAction SilentlyContinue | Where-Object { $_.BaseName -match 'stream' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($preferred) { return $preferred }
  return Get-ChildItem -LiteralPath $apps -Filter "*.kit" -File -ErrorAction SilentlyContinue | Where-Object { $_.BaseName -match 'stream' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

function Patch-StreamingKit([string]$StreamingKitPath) {
  $content = Get-Content -LiteralPath $StreamingKitPath -Raw
  $dependencyLine = '"omnistream.codex.bridge" = {}'
  if ($content -notmatch '"omnistream\.codex\.bridge"\s*=') {
    if ($content -match '(?m)^\[dependencies\]\s*$') {
      $content = [regex]::Replace($content, '(?m)^\[dependencies\]\s*$', "[dependencies]`r`n$dependencyLine", 1)
    } else {
      $content += "`r`n`r`n[dependencies]`r`n$dependencyLine`r`n"
    }
    [IO.File]::WriteAllText($StreamingKitPath, $content, (New-Object Text.UTF8Encoding($false)))
  }
}

function Read-KitRootFromUser([string]$Prompt) {
  while ($true) {
    $candidate = (Read-Host $Prompt).Trim('"').Trim()
    if (-not $candidate) { continue }
    try { $candidate = [IO.Path]::GetFullPath($candidate) } catch { continue }
    if (Test-Path -LiteralPath (Join-Path $candidate "repo.bat") -PathType Leaf) { return $candidate }
    Write-Warning "Ce dossier ne contient pas repo.bat: $candidate"
  }
}

function Resolve-RuntimeChannel {
  if ($RuntimeChannel -ne "Auto") { return }
  if ($KitRoot -and (Test-Path -LiteralPath (Join-Path $KitRoot "repo.bat") -PathType Leaf)) {
    $script:RuntimeChannel = "Existing"
    return
  }
  Write-Host "" 
  Write-Host "Canal NVIDIA Omniverse Kit" -ForegroundColor Green
  Write-Host "[P] Production Branch PB 26h1 via NGC (recommandé pour une installation stable)" -ForegroundColor White
  Write-Host "[D] Feature Branch kit-app-template via GitHub (développement / prototypage)" -ForegroundColor DarkGray
  Write-Host "[E] Projet Kit existant contenant repo.bat" -ForegroundColor DarkGray
  while ($true) {
    $answer = (Read-Host "Choisissez P, D ou E").ToUpperInvariant()
    if ($answer -eq "P") { $script:RuntimeChannel = "Production"; return }
    if ($answer -eq "D") { $script:RuntimeChannel = "Feature"; return }
    if ($answer -eq "E") { $script:RuntimeChannel = "Existing"; return }
  }
}

function Ensure-ProductionKitProject {
  if ($KitRoot -and (Test-Path -LiteralPath (Join-Path $KitRoot "repo.bat") -PathType Leaf)) { return }
  if ($SkipNvidiaRuntimeSetup) { throw "-SkipNvidiaRuntimeSetup exige un -KitRoot existant contenant repo.bat." }

  Save-InstallState "waiting-nvidia-production-kit" "PB 26h1"
  Write-Host "OmniStream ne redistribue pas le Kit SDK NVIDIA." -ForegroundColor Yellow
  Write-Host "Téléchargez et extrayez 'Kit SDK Windows (PB 26h1)' depuis NGC, puis créez un projet avec new_project.bat." -ForegroundColor White
  Write-Host "Le script NVIDIA peut demander l'acceptation de ses conditions. OmniStream attend cette étape puis reprend." -ForegroundColor DarkGray
  Start-Process $Official.KitProduction | Out-Null
  Start-Process $Official.KitProductionInfo | Out-Null

  while ($true) {
    $candidate = (Read-Host "Chemin du Kit SDK extrait (new_project.bat) OU d'un projet Kit déjà créé (repo.bat), Q pour quitter").Trim('"').Trim()
    if ($candidate.ToUpperInvariant() -eq "Q") { throw "Installation interrompue avant la préparation du Kit Production Branch." }
    if (-not $candidate) { continue }
    try { $candidate = [IO.Path]::GetFullPath($candidate) } catch { continue }
    if (Test-Path -LiteralPath (Join-Path $candidate "repo.bat") -PathType Leaf) {
      $script:KitRoot = $candidate
      return
    }
    $newProject = Join-Path $candidate "new_project.bat"
    if (Test-Path -LiteralPath $newProject -PathType Leaf) {
      Write-Host "Lancement de new_project.bat NVIDIA. Créez le projet OmniStream dans un chemin court (ex. C:\OmniStreamKit)." -ForegroundColor Yellow
      & $newProject
      if ($LASTEXITCODE -ne 0) { Write-Warning "new_project.bat a quitté avec le code $LASTEXITCODE." }
      $script:KitRoot = Read-KitRootFromUser "Chemin du projet Kit créé (dossier contenant repo.bat)"
      return
    }
    Write-Warning "Aucun repo.bat ni new_project.bat détecté dans $candidate"
  }
}

function Ensure-FeatureKitProject {
  if ($KitRoot -and (Test-Path -LiteralPath (Join-Path $KitRoot "repo.bat") -PathType Leaf)) { return }
  if ($SkipNvidiaRuntimeSetup) { throw "-SkipNvidiaRuntimeSetup exige un -KitRoot existant contenant repo.bat." }
  if (-not $KitRoot) { $script:KitRoot = [IO.Path]::GetFullPath((Join-Path $ExternalRoot "kit-app-template-feature")) }
  Write-Warning "Feature Branch: NVIDIA indique que cette branche est destinée au développement/prototypage et ne garantit pas la stabilité API d'une Production Branch."
  Start-Process $Official.KitFeatureRepo | Out-Null
  New-Item -ItemType Directory -Force -Path (Split-Path $KitRoot -Parent) | Out-Null
  & git clone --depth 1 https://github.com/NVIDIA-Omniverse/kit-app-template.git $KitRoot
  if ($LASTEXITCODE -ne 0) { throw "Le clone officiel NVIDIA kit-app-template a échoué." }
  if (-not (Test-Path -LiteralPath (Join-Path $KitRoot "repo.bat") -PathType Leaf)) { throw "Le dépôt NVIDIA récupéré ne contient pas repo.bat." }
}

function Ensure-KitTemplateRoot {
  Resolve-RuntimeChannel
  if ($KitRoot) { $script:KitRoot = [IO.Path]::GetFullPath($KitRoot) }
  if ($RuntimeChannel -eq "Production") { Ensure-ProductionKitProject; return }
  if ($RuntimeChannel -eq "Feature") { Ensure-FeatureKitProject; return }
  if ($RuntimeChannel -eq "Existing") {
    if (-not $KitRoot) { $script:KitRoot = Read-KitRootFromUser "Chemin du projet Kit existant (repo.bat)" }
    if (-not (Test-Path -LiteralPath (Join-Path $KitRoot "repo.bat") -PathType Leaf)) { throw "Le KitRoot existant ne contient pas repo.bat." }
    return
  }
  throw "Canal runtime NVIDIA non reconnu: $RuntimeChannel"
}

function Ensure-StreamingLayer {
  $streaming = Get-StreamingKitSource $KitRoot
  if ($streaming) { return $streaming }
  if ($SkipNvidiaRuntimeSetup) { throw "Aucune couche .kit de streaming n'existe sous source\apps dans le KitRoot fourni." }

  Write-Host "" 
  Write-Host "Le wizard officiel NVIDIA va maintenant s'exécuter dans ce terminal." -ForegroundColor Yellow
  Write-Host "Choisissez Application -> USD Viewer (recommandé) ou Kit Base Editor, puis ajoutez la couche 'Omniverse Kit App Streaming (Default)'." -ForegroundColor Yellow
  Write-Host "Au premier lancement, NVIDIA peut demander l'acceptation de ses conditions. OmniStream attend la fin du wizard et reprend ensuite." -ForegroundColor DarkGray
  Start-Process $Official.KitGuide | Out-Null
  Save-InstallState "waiting-nvidia-kit-template" "repo.bat template new"
  $wizardExit = -1
  Push-Location $KitRoot
  try {
    & .\repo.bat template new
    $wizardExit = $LASTEXITCODE
  } finally { Pop-Location }
  if ($wizardExit -ne 0) { throw "Le wizard officiel NVIDIA n'a pas abouti." }
  $streaming = Get-StreamingKitSource $KitRoot
  if (-not $streaming) { throw "Aucune couche *_streaming.kit n'a été détectée après le wizard NVIDIA." }
  return $streaming
}

function Setup-NvidiaRuntime {
  Write-Step "Runtime NVIDIA officiel" "Aucun binaire Kit/Omniverse n'est inclus dans OmniStream. Le canal Production Branch NGC est recommandé; Feature Branch reste disponible explicitement pour le développement."
  Ensure-KitTemplateRoot
  $streaming = Ensure-StreamingLayer
  Write-Host "Streaming layer: $($streaming.FullName)" -ForegroundColor DarkGray

  $bridgeSource = Join-Path $InstallRoot "runtime\bridge\omnistream.codex.bridge"
  $bridgeTarget = Join-Path $KitRoot "source\extensions\omnistream.codex.bridge"
  if (-not (Test-Path -LiteralPath $bridgeSource -PathType Container)) { throw "Le bridge OmniStream source est absent: $bridgeSource" }
  if (Test-Path -LiteralPath $bridgeTarget) { Remove-Item -LiteralPath $bridgeTarget -Recurse -Force }
  Copy-Item -LiteralPath $bridgeSource -Destination $bridgeTarget -Recurse -Force
  Patch-StreamingKit $streaming.FullName
  Save-InstallState "nvidia-template-configured" $streaming.Name

  Write-Host "Build Kit officiel: repo.bat récupère lui-même le Kit SDK et les extensions NVIDIA nécessaires." -ForegroundColor Yellow
  Save-InstallState "building-nvidia-runtime" $streaming.Name
  $buildExit = -1
  Push-Location $KitRoot
  try {
    & .\repo.bat build
    $buildExit = $LASTEXITCODE
  } finally { Pop-Location }
  if ($buildExit -ne 0) { throw "Le build Kit officiel a échoué." }

  $releaseRoot = Join-Path $KitRoot "_build\windows-x86_64\release"
  $kitExe = Join-Path $releaseRoot "kit\kit.exe"
  $builtKit = Join-Path $releaseRoot ("apps\" + $streaming.Name)
  if (-not (Test-Path -LiteralPath $kitExe -PathType Leaf)) { throw "kit.exe n'a pas été produit: $kitExe" }
  if (-not (Test-Path -LiteralPath $builtKit -PathType Leaf)) { throw "La couche de streaming n'a pas été produite: $builtKit" }
  $script:StreamKitRelativePath = "apps/$($streaming.Name)"
  Save-InstallState "nvidia-runtime-built" $builtKit
}

function Install-WebDependencies {
  Write-Step "Client WebRTC NVIDIA" "@nvidia/ov-web-rtc est téléchargé depuis le registre NVIDIA configuré dans web/.npmrc; il n'est pas fourni dans le package OmniStream."
  Push-Location $InstallRoot
  try {
    & npm --prefix .\web ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci a échoué." }
    & npm run build:web
    if ($LASTEXITCODE -ne 0) { throw "Le build du panneau Codex a échoué." }
  } finally { Pop-Location }
  Save-InstallState "web-client-built"
}

function Resolve-StreamKitRelativePath {
  if ($script:StreamKitRelativePath) { return }
  $releaseApps = Join-Path $KitRoot "_build\windows-x86_64\release\apps"
  $existing = Get-ChildItem -LiteralPath $releaseApps -Filter "*stream*.kit" -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $existing) { throw "Impossible de déterminer la couche de streaming Kit construite." }
  $script:StreamKitRelativePath = "apps/$($existing.Name)"
}

function Save-Configuration {
  Write-Step "Configuration normalisée" $ConfigFile
  Resolve-StreamKitRelativePath
  foreach ($dir in @($OmniStreamHome, $ConfigDir, (Join-Path $OmniStreamHome "logs"), $StateDir, (Join-Path $OmniStreamHome "cache"), $ExternalRoot, $WorkspaceRoot, $AssetRoot)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }
  $config = [ordered]@{
    schemaVersion = 2
    kitRoot = [IO.Path]::GetFullPath($KitRoot)
    workspaceRoot = $WorkspaceRoot
    assetRoots = @($AssetRoot)
    streamKitRelativePath = $script:StreamKitRelativePath
    signalingPort = 49100
    mediaPort = 47998
    runtimeChannel = $RuntimeChannel
  }
  [IO.File]::WriteAllText($ConfigFile, ($config | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
  # Public install never seeds the user's workspace. Test assets stay under tests/fixtures.
  [Environment]::SetEnvironmentVariable("OMNISTREAM_HOME", $OmniStreamHome, "User")
  $env:OMNISTREAM_HOME = $OmniStreamHome
  Save-InstallState "configuration-saved" $ConfigFile
}

function Validate-Installation {
  if ($SkipValidation) {
    Save-InstallState "installed-unverified" "Validation explicitement ignorée."
    return
  }
  Write-Step "Validation produit"
  $testScript = Join-Path $InstallRoot "installer\Test-OmniStream.ps1"
  if (-not (Test-Path -LiteralPath $testScript -PathType Leaf)) { throw "Script de validation absent: $testScript" }
  $arguments = @("-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $testScript, "-InstallRoot", $InstallRoot)
  if ($SkipRuntimeSmoke) { $arguments += "-SkipRuntimeSmoke" }
  & powershell.exe @arguments
  if ($LASTEXITCODE -ne 0) { throw "La validation produit OmniStream a échoué. Consultez state\validation-report.json et les logs avant utilisation." }
  $validationPhase = if ($SkipRuntimeSmoke) { "validated-without-runtime-smoke" } else { "validated" }
  Save-InstallState $validationPhase
}

function Finish-Install {
  Save-InstallState "complete"
  Write-Step "Installation terminée"
  Write-Host "OmniStream:  $InstallRoot"
  Write-Host "Config:      $ConfigFile"
  Write-Host "Kit NVIDIA:  $KitRoot"
  Write-Host "Workspace:   $WorkspaceRoot"
  Write-Host "Assets:      $AssetRoot"
  Write-Host ""
  if ($SkipValidation -or $SkipRuntimeSmoke) {
    Write-Warning "Installation présente mais la qualification RTX/Kit/WebRTC complète n'a pas été exécutée. Lancez installer\test.cmd avant de qualifier cette installation de stable."
  } else {
    Write-Host "Contrôles automatiques source/Kit/signaling réussis. Vidéo décodée, entrée Codex et test physique restent des validations distinctes." -ForegroundColor Green
  }
  Write-Host "Étape Codex: chargez/importez le plugin local depuis le dossier OmniStream ci-dessus, puis ouvrez 'OmniStream for Codex'." -ForegroundColor Green
  Write-Host "Aucun runtime NVIDIA n'a été copié dans le package OmniStream; les dépendances NVIDIA présentes sur cette machine proviennent des outils/registries officiels." -ForegroundColor DarkGray
}

try {
  Test-PackageIntegrity
  Ensure-Prerequisites
  Copy-OmniStreamSource
  Setup-NvidiaRuntime
  Install-WebDependencies
  Save-Configuration
  Validate-Installation
  Finish-Install
} catch {
  Save-InstallState "interrupted" $_.Exception.Message
  Write-Host ""
  Write-Host "Installation OmniStream interrompue: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "Relancez installer\install.cmd. Les chemins déjà enregistrés et les composants déjà valides seront redétectés; l'installation reprendra sans redistribuer les dépendances NVIDIA." -ForegroundColor Yellow
  exit 1
}
