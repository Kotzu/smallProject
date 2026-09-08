[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ClientRoot = 'E:\Games\WoW TBC 2.4.3',
    [string]$Account = 'ADMIN'
)

$ErrorActionPreference = 'Stop'
if (Get-Process -Name Wow -ErrorAction SilentlyContinue) {
    throw 'Wow.exe is running. Log out normally and stop the client before importing SavedVariables.'
}

$python = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
$input = Join-Path $ClientRoot "WTF\Account\$Account\SavedVariables\PerfectAssassinObserver.lua"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python environment is missing: $python"
}
if (-not (Test-Path -LiteralPath $input -PathType Leaf)) {
    throw "Observer export is not available yet: $input"
}

$sessionStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$telemetry = Join-Path $RepositoryRoot "data\telemetry\pa018-$sessionStamp.jsonl"
$journal = Join-Path $RepositoryRoot "data\runtime\journals\pa018-$sessionStamp.md"

& $python -m perfect_assassin import-tbc243-saved-variables `
    --input $input `
    --telemetry $telemetry `
    --journal $journal
if ($LASTEXITCODE -ne 0) {
    throw 'TBC 2.4.3 observer import failed'
}

Write-Output "PA018_CAPTURE_IMPORTED=$input"
Write-Output "PA018_TELEMETRY=$telemetry"
Write-Output "PA018_JOURNAL=$journal"
