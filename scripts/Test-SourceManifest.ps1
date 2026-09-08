[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB'
)

$ErrorActionPreference = 'Stop'
$manifestPath = Join-Path $LabRoot 'source-manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

$failures = @()
foreach ($repo in $manifest.repositories) {
    $path = Join-Path $LabRoot ("source\{0}" -f $repo.name)
    if (-not (Test-Path -LiteralPath $path)) {
        $failures += "Missing $($repo.name)"
        continue
    }
    $actualCommit = git -C $path rev-parse HEAD
    $actualRemote = git -C $path remote get-url origin
    if ($actualCommit -ne $repo.commit) {
        $failures += "$($repo.name) commit mismatch: $actualCommit"
    }
    if ($actualRemote -ne $repo.url) {
        $failures += "$($repo.name) remote mismatch: $actualRemote"
    }
}

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Output 'SOURCE_MANIFEST_OK'

