[CmdletBinding()]
param([string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot))

$ErrorActionPreference = 'Stop'
$python = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing isolated Python environment: $python"
}

& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Python dependency check failed' }
& $python -m unittest discover -s (Join-Path $RepositoryRoot 'tests') -v
if ($LASTEXITCODE -ne 0) { throw 'PA-017 test suite failed' }
& $python -m compileall -q (Join-Path $RepositoryRoot 'src') (Join-Path $RepositoryRoot 'tests')
if ($LASTEXITCODE -ne 0) { throw 'Python compile check failed' }

Write-Output 'PA017_TBC243_OFFLINE_INTAKE_OK'
