[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Resolve-Tool([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) { return $null }
    return $command.Source
}

$vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
$visualStudio = $null
if (Test-Path -LiteralPath $vswhere) {
    $visualStudio = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
}

$result = [ordered]@{
    checked_at = (Get-Date).ToUniversalTime().ToString('o')
    git = Resolve-Tool 'git'
    cmake = Resolve-Tool 'cmake'
    ninja = Resolve-Tool 'ninja'
    mysql = Resolve-Tool 'mysql'
    mariadb = Resolve-Tool 'mariadb'
    visual_studio_cpp = $visualStudio
    lab_root = 'E:\WoWserver\TBC-LAB'
    free_bytes_e = (Get-PSDrive E).Free
}

$result | ConvertTo-Json -Depth 3

