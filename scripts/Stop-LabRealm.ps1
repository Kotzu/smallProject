[CmdletBinding()]
param([string]$LabRoot = 'E:\WoWserver\TBC-LAB')

$ErrorActionPreference = 'Stop'
$pidPath = Join-Path $LabRoot 'runtime\realmd.pid'
if (-not (Test-Path -LiteralPath $pidPath)) {
    Write-Output 'LAB_REALM_ALREADY_STOPPED'
    return
}
$processId = [int](Get-Content -LiteralPath $pidPath -Raw)
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if ($process) {
    Stop-Process -Id $processId
    $process.WaitForExit(10000) | Out-Null
}
Remove-Item -LiteralPath $pidPath -Force
Write-Output 'LAB_REALM_STOPPED'
