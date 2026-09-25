param(
  [Parameter(Mandatory = $true)][string]$KitExe,
  [Parameter(Mandatory = $true)][string]$KitArgumentLine,
  [Parameter(Mandatory = $true)][string]$WorkingDirectory,
  [Parameter(Mandatory = $true)][string]$StdOutPath,
  [Parameter(Mandatory = $true)][string]$StdErrPath,
  [Parameter(Mandatory = $true)][string]$PidPath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $KitExe -PathType Leaf)) {
  throw "Kit executable was not found: $KitExe"
}

# `-WindowStyle Hidden` hides the PowerShell-created process window only.  Kit
# itself creates a main window unless its streaming runtime receives this native
# command-line switch.
$kitArgumentList = $KitArgumentLine.Trim() + " --no-window"

$kit = Start-Process `
  -FilePath $KitExe `
  -ArgumentList $kitArgumentList `
  -WorkingDirectory $WorkingDirectory `
  -WindowStyle Hidden `
  -RedirectStandardOutput $StdOutPath `
  -RedirectStandardError $StdErrPath `
  -PassThru

try {
  $identity = [ordered]@{
    pid = [int]$kit.Id
    startedAtUtc = $kit.StartTime.ToUniversalTime().ToString("o")
    startedAtFileTimeUtc = [string]$kit.StartTime.ToFileTimeUtc()
  } | ConvertTo-Json -Compress
  [System.IO.File]::WriteAllText(
    $PidPath,
    $identity,
    (New-Object System.Text.UTF8Encoding($false))
  )
} catch {
  # Preserve the exact identity on stdout even if the optional handoff file
  # cannot be written. Node can then track and later terminate the same
  # process through its verified native handle instead of an unsafe PID-only
  # cleanup attempt here.
  [Console]::Out.WriteLine($identity)
  throw
}

[Console]::Out.WriteLine($identity)
