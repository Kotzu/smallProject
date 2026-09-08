[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB',
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$runtime = Join-Path $LabRoot 'runtime\core-playerbots'
$exe = Join-Path $runtime 'mangosd.exe'
$config = Join-Path $runtime 'mangosd.conf'
$pidPath = Join-Path $LabRoot 'runtime\mangosd.pid'
$stdout = Join-Path $LabRoot 'logs\mangosd.stdout.log'
$stderr = Join-Path $LabRoot 'logs\mangosd.stderr.log'

foreach ($required in @($exe, $config, (Join-Path $runtime 'legacy.dll'))) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing: $required" }
}

if (Test-Path -LiteralPath $pidPath) {
    $existingPid = [int](Get-Content -LiteralPath $pidPath -Raw)
    if (Get-Process -Id $existingPid -ErrorAction SilentlyContinue) {
        Write-Output "LAB_WORLD_ALREADY_RUNNING:PID=$existingPid"
        return
    }
    Remove-Item -LiteralPath $pidPath -Force
}

Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
$previousModules = $env:OPENSSL_MODULES
$env:OPENSSL_MODULES = $runtime
try {
    $process = Start-Process -FilePath $exe -ArgumentList @('-c', $config) -WorkingDirectory $runtime `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
}
finally {
    $env:OPENSSL_MODULES = $previousModules
}
[System.IO.File]::WriteAllText($pidPath, [string]$process.Id)

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    if ($process.HasExited) {
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
        $tail = if (Test-Path -LiteralPath $stdout) { (Get-Content -LiteralPath $stdout -Tail 20) -join [Environment]::NewLine } else { '' }
        throw "mangosd exited with $($process.ExitCode). Last output:`n$tail"
    }

    $worldPort = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8085 -State Listen -ErrorAction SilentlyContinue
    $raPort = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 3443 -State Listen -ErrorAction SilentlyContinue
    $initialized = (Test-Path -LiteralPath $stdout) -and (Select-String -LiteralPath $stdout -SimpleMatch 'CMANGOS: World initialized' -Quiet)
    if ($worldPort -and $raPort -and $initialized) {
        Write-Output "LAB_WORLD_READY:PID=$($process.Id):127.0.0.1:8085:RA=127.0.0.1:3443"
        return
    }
    Start-Sleep -Milliseconds 500
}

Stop-Process -Id $process.Id -Force
Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
throw "mangosd did not become ready in $TimeoutSeconds seconds; see $stdout and $stderr"
