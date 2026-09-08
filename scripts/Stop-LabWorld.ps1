[CmdletBinding()]
param([string]$LabRoot = 'E:\WoWserver\TBC-LAB')

$ErrorActionPreference = 'Stop'
$pidPath = Join-Path $LabRoot 'runtime\mangosd.pid'
if (-not (Test-Path -LiteralPath $pidPath)) {
    Write-Output 'LAB_WORLD_ALREADY_STOPPED'
    return
}

$processId = [int](Get-Content -LiteralPath $pidPath -Raw)
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if (-not $process) {
    Remove-Item -LiteralPath $pidPath -Force
    Write-Output 'LAB_WORLD_ALREADY_STOPPED'
    return
}

$invoke = Join-Path $PSScriptRoot 'Invoke-LabRemoteCommand.ps1'
$operatorSecret = Join-Path $LabRoot 'database\operator.local.json'
if (Test-Path -LiteralPath $operatorSecret) {
    $credential = Get-Content -LiteralPath $operatorSecret -Raw | ConvertFrom-Json
    & $invoke -Username $credential.username -Password $credential.password -Command 'server shutdown 1' | Out-Null
}
else {
    & $invoke -Username 'ADMINISTRATOR' -Password 'ADMINISTRATOR' -Command 'server shutdown 1' | Out-Null
}

if (-not $process.WaitForExit(15000)) {
    throw "mangosd PID $processId did not stop gracefully"
}
Remove-Item -LiteralPath $pidPath -Force
Write-Output 'LAB_WORLD_STOPPED_GRACEFULLY'
