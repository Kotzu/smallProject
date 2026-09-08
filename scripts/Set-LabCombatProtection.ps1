[CmdletBinding()]
param(
    [ValidateSet('On', 'Off')] [string]$State = 'On',
    [ValidatePattern('^[A-Za-z][A-Za-z0-9]{1,11}$')] [string]$PlayerName = 'Predator',
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB'
)

$ErrorActionPreference = 'Stop'
$operatorPath = Join-Path $LabRoot 'database\operator.local.json'
$invoke = Join-Path $PSScriptRoot 'Invoke-LabRemoteCommand.ps1'

if (-not (Test-Path -LiteralPath $operatorPath -PathType Leaf)) {
    throw "LAB operator secret is missing: $operatorPath"
}
if (-not (Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 3443 -State Listen -ErrorAction SilentlyContinue)) {
    throw 'LAB remote administration is not listening on 127.0.0.1:3443'
}

$operator = Get-Content -LiteralPath $operatorPath -Raw | ConvertFrom-Json
$normalizedState = $State.ToLowerInvariant()
$response = & $invoke `
    -Username $operator.username `
    -Password $operator.password `
    -Command "labgod $PlayerName $normalizedState"
$expected = "LAB damage protection for $PlayerName is now $($State.ToUpperInvariant())."

if (-not $response.Contains($expected)) {
    throw "LAB combat protection was not confirmed by the world server: $response"
}

Write-Output "LAB_COMBAT_PROTECTION_$($State.ToUpperInvariant()):PLAYER=$PlayerName"
