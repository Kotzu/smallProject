[CmdletBinding()]
param(
    [string]$RepositoryRoot = ''
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
}
$runtimeRoot = Join-Path $RepositoryRoot 'data\runtime\stay-online'
$statePath = Join-Path $runtimeRoot 'state.json'
$stopPath = Join-Path $runtimeRoot 'stop.request'
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
Set-Content -LiteralPath $stopPath -Value ([DateTimeOffset]::UtcNow.ToString('o')) -Encoding utf8

if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    Write-Output 'LAB_STAY_ONLINE_GUARD_STOP_REQUESTED:NO_STATE'
    return
}
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$process = Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue
if ($null -eq $process) {
    Write-Output 'LAB_STAY_ONLINE_GUARD_STOPPED:PROCESS_ALREADY_EXITED'
    return
}
if (-not $process.WaitForExit(10000)) {
    throw 'LAB stay-online guard did not stop cooperatively in time.'
}
Write-Output "LAB_STAY_ONLINE_GUARD_STOPPED:PID=$($process.Id)"
