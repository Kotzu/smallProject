[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB',
    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = 'Stop'
$runtime = Join-Path $LabRoot 'runtime\core-playerbots'
$exe = Join-Path $runtime 'realmd.exe'
$config = Join-Path $runtime 'realmd.conf'
$pidPath = Join-Path $LabRoot 'runtime\realmd.pid'
$stdout = Join-Path $LabRoot 'logs\realmd.stdout.log'
$stderr = Join-Path $LabRoot 'logs\realmd.stderr.log'

foreach ($required in @($exe, $config)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing: $required" }
}

if (Test-Path -LiteralPath $pidPath) {
    $existingPid = [int](Get-Content -LiteralPath $pidPath -Raw)
    if (Get-Process -Id $existingPid -ErrorAction SilentlyContinue) {
        Write-Output "LAB_REALM_ALREADY_RUNNING:PID=$existingPid"
        return
    }
    Remove-Item -LiteralPath $pidPath -Force
}

$process = Start-Process -FilePath $exe -ArgumentList @('-c', $config) -WorkingDirectory $runtime `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    if ($process.HasExited) { throw "realmd exited with $($process.ExitCode); see $stdout and $stderr" }
    $listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 3724 -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        [System.IO.File]::WriteAllText($pidPath, [string]$process.Id)
        Write-Output "LAB_REALM_READY:PID=$($process.Id):127.0.0.1:3724"
        return
    }
    Start-Sleep -Milliseconds 250
}

Stop-Process -Id $process.Id -Force
throw 'realmd did not become ready in time'

