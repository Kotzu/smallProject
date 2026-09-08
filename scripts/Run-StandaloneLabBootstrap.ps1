[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryRoot,
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB'
)

$ErrorActionPreference = 'Stop'

$operatorRuntime = Join-Path $RepositoryRoot 'data\runtime\operator'
$statusPath = Join-Path $operatorRuntime 'standalone-lab-status.json'
$controlPidPath = Join-Path $operatorRuntime 'movement-engine-control-center.pid'
$pythonw = Join-Path $RepositoryRoot '.venv\Scripts\pythonw.exe'
$controlCenter = Join-Path $RepositoryRoot 'integrations\windows-input\run_movement_engine_client.py'

foreach ($required in @(
    (Join-Path $RepositoryRoot 'scripts\Start-LabDatabase.ps1'),
    (Join-Path $RepositoryRoot 'scripts\Start-LabRealm.ps1'),
    (Join-Path $RepositoryRoot 'scripts\Start-LabWorld.ps1'),
    $pythonw,
    $controlCenter
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing standalone LAB dependency: $required"
    }
}

New-Item -ItemType Directory -Path $operatorRuntime -Force | Out-Null

function Write-StandaloneStatus {
    param([string]$State, [string]$Detail, [int]$ControlCenterPid = 0)
    $record = [ordered]@{
        record_type = 'standalone_lab_status'
        schema_version = '1.0'
        observed_at = [DateTimeOffset]::UtcNow.ToString('o')
        state = $State
        detail = $Detail
        bootstrap_pid = $PID
        control_center_pid = if ($ControlCenterPid -gt 0) { $ControlCenterPid } else { $null }
    }
    $temporary = "$statusPath.$([Guid]::NewGuid()).tmp"
    [System.IO.File]::WriteAllText(
        $temporary,
        (($record | ConvertTo-Json -Compress) + [Environment]::NewLine),
        [System.Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporary -Destination $statusPath -Force
}

try {
    Write-StandaloneStatus -State 'STARTING_DATABASE' -Detail 'Starting standalone LAB database.'
    & (Join-Path $RepositoryRoot 'scripts\Start-LabDatabase.ps1') -LabRoot $LabRoot | Out-Null

    Write-StandaloneStatus -State 'STARTING_REALM' -Detail 'Starting standalone LAB realm.'
    & (Join-Path $RepositoryRoot 'scripts\Start-LabRealm.ps1') -LabRoot $LabRoot | Out-Null

    Write-StandaloneStatus -State 'STARTING_WORLD' -Detail 'Starting standalone LAB world.'
    & (Join-Path $RepositoryRoot 'scripts\Start-LabWorld.ps1') -LabRoot $LabRoot | Out-Null

    $controlCenterPid = 0
    if (Test-Path -LiteralPath $controlPidPath) {
        $candidatePid = [int](Get-Content -LiteralPath $controlPidPath -Raw)
        $candidate = Get-Process -Id $candidatePid -ErrorAction SilentlyContinue
        if ($candidate) {
            $controlCenterPid = $candidatePid
        }
        else {
            Remove-Item -LiteralPath $controlPidPath -Force
        }
    }

    if ($controlCenterPid -eq 0) {
        $control = Start-Process -FilePath $pythonw -ArgumentList @($controlCenter) `
            -WorkingDirectory $RepositoryRoot -PassThru
        $controlCenterPid = $control.Id
        [System.IO.File]::WriteAllText($controlPidPath, [string]$controlCenterPid)
    }

    Write-StandaloneStatus -State 'READY' `
        -Detail 'Database, realm, world and Control Center are independent from Codex.' `
        -ControlCenterPid $controlCenterPid
}
catch {
    Write-StandaloneStatus -State 'FAILED' -Detail $_.Exception.Message
    throw
}
