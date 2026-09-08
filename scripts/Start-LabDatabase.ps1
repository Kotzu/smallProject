[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB',
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = 'Stop'

$bin = Join-Path $LabRoot 'toolchain\mariadb-12.3.2\MariaDB 12.3\bin'
$server = Join-Path $bin 'mariadbd.exe'
$dataDir = Join-Path $LabRoot 'database\data'
$config = Join-Path $dataDir 'my.ini'
$secretsPath = Join-Path $LabRoot 'database\secrets.local.json'
$pidPath = Join-Path $LabRoot 'database\mariadb.pid'
$stdout = Join-Path $LabRoot 'logs\mariadb.stdout.log'
$stderr = Join-Path $LabRoot 'logs\mariadb.stderr.log'

foreach ($required in @($server, $config, $secretsPath)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing: $required" }
}

$secrets = Get-Content -LiteralPath $secretsPath -Raw | ConvertFrom-Json

if (Test-Path -LiteralPath $pidPath) {
    $existingPid = [int](Get-Content -LiteralPath $pidPath -Raw)
    if (Get-Process -Id $existingPid -ErrorAction SilentlyContinue) {
        Write-Output "LAB_DATABASE_ALREADY_RUNNING:PID=$existingPid"
        return
    }
    Remove-Item -LiteralPath $pidPath -Force
}

$arguments = @(
    "--defaults-file=$config",
    "--datadir=$dataDir",
    "--port=$($secrets.port)",
    "--bind-address=$($secrets.host)",
    '--console'
)

$process = Start-Process -FilePath $server -ArgumentList $arguments -WorkingDirectory $bin `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$ready = $false
while ((Get-Date) -lt $deadline) {
    if ($process.HasExited) {
        throw "LAB MariaDB exited early with code $($process.ExitCode). See $stderr"
    }
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $client.Connect($secrets.host, [int]$secrets.port)
        $ready = $true
        break
    } catch {
        Start-Sleep -Milliseconds 250
    } finally {
        $client.Dispose()
    }
}

if (-not $ready) {
    Stop-Process -Id $process.Id -Force
    throw "LAB MariaDB did not open port $($secrets.port) within $TimeoutSeconds seconds"
}

[System.IO.File]::WriteAllText($pidPath, [string]$process.Id)
Write-Output "LAB_DATABASE_READY:PID=$($process.Id):$($secrets.host):$($secrets.port)"

