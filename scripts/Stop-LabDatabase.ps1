[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB',
    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = 'Stop'

$bin = Join-Path $LabRoot 'toolchain\mariadb-12.3.2\MariaDB 12.3\bin'
$admin = Join-Path $bin 'mariadb-admin.exe'
$secretsPath = Join-Path $LabRoot 'database\secrets.local.json'
$pidPath = Join-Path $LabRoot 'database\mariadb.pid'

if (-not (Test-Path -LiteralPath $pidPath)) {
    Write-Output 'LAB_DATABASE_ALREADY_STOPPED'
    return
}

$processId = [int](Get-Content -LiteralPath $pidPath -Raw)
$secrets = Get-Content -LiteralPath $secretsPath -Raw | ConvertFrom-Json

& $admin "--host=$($secrets.host)" "--port=$($secrets.port)" "--user=$($secrets.root_user)" "--password=$($secrets.root_password)" shutdown
if ($LASTEXITCODE -ne 0) { throw 'Graceful LAB MariaDB shutdown failed' }

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    if (-not (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
        Remove-Item -LiteralPath $pidPath -Force
        Write-Output 'LAB_DATABASE_STOPPED'
        return
    }
    Start-Sleep -Milliseconds 250
}

throw "LAB MariaDB PID $processId did not stop within $TimeoutSeconds seconds"
