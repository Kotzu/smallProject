[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB',
    [int]$Port = 3307
)

$ErrorActionPreference = 'Stop'

$installRoot = Join-Path $LabRoot 'toolchain\mariadb-12.3.2\MariaDB 12.3'
$installer = Join-Path $installRoot 'bin\mariadb-install-db.exe'
$dataDir = Join-Path $LabRoot 'database\data'
$secretsPath = Join-Path $LabRoot 'database\secrets.local.json'

if (-not (Test-Path -LiteralPath $installer)) {
    throw "MariaDB installer not found: $installer"
}
if (Test-Path -LiteralPath $secretsPath) {
    throw "Database secrets already exist; refusing to reinitialize: $secretsPath"
}
if ((Test-Path -LiteralPath $dataDir) -and (Get-ChildItem -LiteralPath $dataDir -Force | Select-Object -First 1)) {
    throw "Database data directory is not empty: $dataDir"
}

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

$passwordBytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(24)
$rootPassword = [Convert]::ToHexString($passwordBytes)

$arguments = @(
    "--datadir=$dataDir",
    "--password=$rootPassword",
    "--port=$Port",
    '--silent'
)

$process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
if ($process.ExitCode -ne 0) {
    throw "MariaDB initialization failed with exit code $($process.ExitCode)"
}

$secretDocument = [ordered]@{
    schema_version = '1.0'
    host = '127.0.0.1'
    port = $Port
    root_user = 'root'
    root_password = $rootPassword
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
}

[System.IO.File]::WriteAllText(
    $secretsPath,
    ($secretDocument | ConvertTo-Json -Depth 3),
    [System.Text.UTF8Encoding]::new($false)
)

& icacls.exe $secretsPath '/inheritance:r' '/grant:r' "$env:USERNAME`:(F)" 'SYSTEM:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to restrict ACL on $secretsPath"
}

$rootPassword = $null
[Array]::Clear($passwordBytes, 0, $passwordBytes.Length)

Write-Output "LAB_DATABASE_INITIALIZED:127.0.0.1:$Port"
Write-Output "SECRETS_STORED:$secretsPath"

