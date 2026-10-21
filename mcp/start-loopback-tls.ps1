param(
    [string]$CertificateThumbprint,
    [int]$ListenPort = 49101,
    [int]$KitPort = 49100,
    [switch]$CompileOnly,
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
Add-Type -Path (Join-Path $PSScriptRoot 'LoopbackTlsRelay.cs') -ErrorAction Stop
if ($CompileOnly) { Write-Output 'PASS: local TLS relay compiled; no listener or trust change.'; exit 0 }
if ($CertificateThumbprint -notmatch '^[0-9a-fA-F]{40}$') { throw 'An explicit certificate thumbprint is required.' }
# Use the Windows store API directly. A Node parent can inherit a PowerShell 7
# module path, which prevents Windows PowerShell from mounting the Cert drive.
$relayStore = [System.Security.Cryptography.X509Certificates.X509Store]::new('My', [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser)
try {
    $relayStore.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadOnly)
    $relayMatches = $relayStore.Certificates.Find([System.Security.Cryptography.X509Certificates.X509FindType]::FindByThumbprint, $CertificateThumbprint, $false)
    if ($relayMatches.Count -ne 1) { throw 'The configured server certificate is unavailable.' }
    $relayCert = $relayMatches[0]
} finally { $relayStore.Close() }
if ($relayCert.Subject -ne 'CN=localhost' -or -not $relayCert.HasPrivateKey -or $relayCert.NotAfter -le (Get-Date) -or $relayCert.NotBefore -gt (Get-Date)) { throw 'Invalid localhost server certificate.' }
if ($relayCert.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::DnsName, $false) -ne 'localhost') { throw 'Certificate must identify localhost.' }
$relayEku = @($relayCert.Extensions | Where-Object { $_ -is [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension] })
$relayServerAuth = @($relayEku | ForEach-Object { $_.EnhancedKeyUsages } | Where-Object { $_.Value -eq '1.3.6.1.5.5.7.3.1' })
if (-not $relayServerAuth.Count) { throw 'Certificate requires serverAuth EKU.' }
$relayConstraints = @($relayCert.Extensions | Where-Object { $_ -is [System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension] })
if (-not $relayConstraints.Count -or $relayConstraints[0].CertificateAuthority) { throw 'A non-CA server certificate is required.' }
$relayChain = [System.Security.Cryptography.X509Certificates.X509Chain]::new()
try {
    if (-not $relayChain.Build($relayCert)) { throw 'Certificate is not trusted. This helper will never install trust or disable validation.' }
} finally { $relayChain.Dispose() }
if ($ValidateOnly) { Write-Output '{"valid":true}'; exit 0 }
$relay = [OmniStreamLoopbackTlsRelay]::new($relayCert, $ListenPort, $KitPort)
try {
    $relay.Start()
    [ordered]@{ ready=$true; host='localhost'; port=$ListenPort; targetHost='127.0.0.1'; targetPort=$KitPort; encrypted=$true; certificateThumbprint=$CertificateThumbprint } | ConvertTo-Json -Compress
    # Parent keeps stdin open. Closing its pipe ends this owned helper.
    [void][Console]::ReadLine()
} finally { $relay.Dispose() }
