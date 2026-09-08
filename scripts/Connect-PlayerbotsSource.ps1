[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB'
)

$ErrorActionPreference = 'Stop'

$core = Join-Path $LabRoot 'source\mangos-tbc'
$playerbots = Join-Path $LabRoot 'source\playerbots'
$modules = Join-Path $core 'src\modules'
$link = Join-Path $modules 'PlayerBots'

foreach ($required in @($core, $playerbots)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing required checkout: $required"
    }
}

New-Item -ItemType Directory -Force -Path $modules | Out-Null

if (Test-Path -LiteralPath $link) {
    $resolved = (Get-Item -LiteralPath $link -Force).Target
    if ($resolved -ne $playerbots) {
        throw "PlayerBots path already exists and points elsewhere: $link"
    }
    Write-Output "PlayerBots source already connected: $link"
    return
}

New-Item -ItemType Junction -Path $link -Target $playerbots | Out-Null
Write-Output "Connected pinned PlayerBots source: $link -> $playerbots"

