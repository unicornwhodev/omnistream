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

$budgetPath = Join-Path $WorkingDirectory 'omnistream-resource-budget.private.json'
if (Test-Path -LiteralPath $budgetPath -PathType Leaf) {
  # An operator-configured guard is mandatory for this runtime once present.
  # Never fall back to an unbounded launch after an admission or guard error.
  $budget = Get-Content -LiteralPath $budgetPath -Raw | ConvertFrom-Json
  if ($budget.schema -ne 'omnistream.local-resource-budget.v1' -or
      -not (Test-Path -LiteralPath $budget.python -PathType Leaf) -or
      -not (Test-Path -LiteralPath $budget.launcher -PathType Leaf)) {
    throw 'Invalid local resource guard configuration'
  }
  $guardOutput = $PidPath + '.budget'
  $requestPath = $PidPath + '.budget-request.private.json'
  $request = [ordered]@{
    budget = $budget; output = $guardOutput; executable = $KitExe
    argument_line = $kitArgumentList; working_directory = $WorkingDirectory
    stdout = $StdOutPath; stderr = $StdErrPath
  } | ConvertTo-Json -Depth 8
  [System.IO.File]::WriteAllText($requestPath, $request, (New-Object System.Text.UTF8Encoding($false)))
  $guard = Start-Process -FilePath $budget.python -WindowStyle Hidden -PassThru `
    -ArgumentList @(('"' + $budget.launcher + '"'), '--request', ('"' + $requestPath + '"')) `
    -RedirectStandardOutput ($PidPath + '.guard.out.log') `
    -RedirectStandardError ($PidPath + '.guard.err.log')
  $handoff = Join-Path $guardOutput 'process.json'
  $deadline = [DateTime]::UtcNow.AddSeconds(12)
  while (-not (Test-Path -LiteralPath $handoff -PathType Leaf)) {
    $guard.Refresh()
    if ($guard.HasExited -or [DateTime]::UtcNow -ge $deadline) {
      throw 'Resource guard did not admit a tracked Kit process'
    }
    Start-Sleep -Milliseconds 50
  }
  $admitted = Get-Content -LiteralPath $handoff -Raw | ConvertFrom-Json
  if ($admitted.job_commit_limit_bytes -gt 12000000000 -or
      $admitted.gpu_requested_ceiling_bytes -gt 15000000000) {
    throw 'Guard handoff exceeds authorized ceilings'
  }
  $kit = Get-Process -Id ([int]$admitted.pid) -ErrorAction Stop
} else {
  $kit = Start-Process `
  -FilePath $KitExe `
  -ArgumentList $kitArgumentList `
  -WorkingDirectory $WorkingDirectory `
  -WindowStyle Hidden `
  -RedirectStandardOutput $StdOutPath `
  -RedirectStandardError $StdErrPath `
    -PassThru
}

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
