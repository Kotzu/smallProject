[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB'
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$launcher = Join-Path $repositoryRoot 'scripts\launch_standalone_lab.py'

foreach ($required in @($python, $launcher)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing standalone LAB launcher dependency: $required"
    }
}

& $python $launcher --lab-root $LabRoot
if ($LASTEXITCODE -ne 0) {
    throw "Standalone LAB launcher failed with exit code $LASTEXITCODE"
}
