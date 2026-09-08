[CmdletBinding()]
param(
    [ValidateRange(120, 1200)] [int]$IdleSeconds = 240,
    [ValidateRange(1, 24)] [int]$MaxHours = 12,
    [switch]$AcknowledgeStayOnline,
    [string]$RepositoryRoot = ''
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
}
if (-not $AcknowledgeStayOnline) {
    throw 'Start-LabStayOnlineGuard requires -AcknowledgeStayOnline.'
}

$runtimeRoot = Join-Path $RepositoryRoot 'data\runtime\stay-online'
$statePath = Join-Path $runtimeRoot 'state.json'
$stopPath = Join-Path $runtimeRoot 'stop.request'
$stdoutPath = Join-Path $runtimeRoot 'guard.stdout.log'
$stderrPath = Join-Path $runtimeRoot 'guard.stderr.log'
$receiptPath = Join-Path $RepositoryRoot 'data\runtime\operator\lab-client-launch-receipt.json'
$runnerPath = Join-Path $RepositoryRoot 'integrations\windows-input\run_stay_online_guard.py'
$pythonPath = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Project Python runtime is missing; refusing a different interpreter.'
}

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    $previous = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ($previous.status -eq 'RUNNING') {
        $existing = Get-Process -Id ([int]$previous.pid) -ErrorAction SilentlyContinue
        if ($null -ne $existing) {
            Write-Output "LAB_STAY_ONLINE_GUARD_ALREADY_RUNNING:PID=$($existing.Id)"
            return
        }
    }
}
Remove-Item -LiteralPath $stopPath -Force -ErrorAction SilentlyContinue

$arguments = @(
    $runnerPath,
    '--receipt', $receiptPath,
    '--state-file', $statePath,
    '--stop-file', $stopPath,
    '--idle-seconds', $IdleSeconds,
    '--max-hours', $MaxHours,
    '--acknowledge-stay-online'
)
$process = Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $RepositoryRoot `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru

$deadline = [DateTimeOffset]::UtcNow.AddSeconds(10)
do {
    Start-Sleep -Milliseconds 200
    if ($process.HasExited) {
        $detail = if (Test-Path -LiteralPath $stderrPath) {
            Get-Content -LiteralPath $stderrPath -Raw
        } else { 'no stderr was produced' }
        throw "LAB stay-online guard exited during startup: $detail"
    }
    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if ($state.status -eq 'RUNNING') {
            $worker = Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue
            if ($null -ne $worker) {
                Write-Output "LAB_STAY_ONLINE_GUARD_STARTED:PID=$($worker.Id):CLIENT_PID=$($state.client_pid)"
                return
            }
        }
    }
} while ([DateTimeOffset]::UtcNow -lt $deadline)

throw 'LAB stay-online guard did not publish a RUNNING state in time.'
