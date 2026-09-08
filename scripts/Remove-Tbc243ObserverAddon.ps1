[CmdletBinding(SupportsShouldProcess)]
param([string]$ClientRoot = 'E:\Games\WoW TBC 2.4.3')

$ErrorActionPreference = 'Stop'
if (Get-Process -Name Wow -ErrorAction SilentlyContinue) {
    throw 'Wow.exe is running. Stop the client before removing the observer addon.'
}

$client = [IO.Path]::GetFullPath($ClientRoot)
$addonsRoot = [IO.Path]::GetFullPath((Join-Path $client 'Interface\AddOns'))
$target = [IO.Path]::GetFullPath((Join-Path $addonsRoot 'PerfectAssassinObserver'))
$allowedPrefix = $addonsRoot.TrimEnd('\') + '\'
if (-not $target.StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Resolved addon target escaped the intended AddOns directory: $target"
}
if (-not (Test-Path -LiteralPath $target -PathType Container)) {
    Write-Output "PA018_ADDON_ALREADY_ABSENT=$target"
    exit 0
}

if ($PSCmdlet.ShouldProcess($target, 'Remove only the Perfect Assassin Observer addon directory')) {
    Remove-Item -LiteralPath $target -Recurse -Force
    Write-Output "PA018_ADDON_REMOVED=$target"
}
