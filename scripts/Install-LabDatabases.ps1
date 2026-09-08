[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB'
)

$ErrorActionPreference = 'Stop'

$installerRoot = Join-Path $LabRoot 'integration\tbc-db-install'
$installScript = Join-Path $installerRoot 'InstallFullDB.sh'
$configPath = Join-Path $installerRoot 'InstallFullDB.config'
$secretsPath = Join-Path $LabRoot 'database\secrets.local.json'
$mariaBinWindows = Join-Path $LabRoot 'toolchain\mariadb-12.3.2\MariaDB 12.3\bin'
$bash = 'C:\Program Files\Git\bin\bash.exe'
$logPath = Join-Path $LabRoot 'logs\database-install.log'

foreach ($required in @($installScript, $secretsPath, $bash, (Join-Path $mariaBinWindows 'mariadb.exe'))) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing: $required" }
}

$secrets = Get-Content -LiteralPath $secretsPath -Raw | ConvertFrom-Json -AsHashtable
if (-not $secrets.ContainsKey('mangos_user')) {
    $passwordBytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(24)
    $secrets['mangos_user'] = 'predator_lab'
    $secrets['mangos_password'] = [Convert]::ToHexString($passwordBytes)
    [Array]::Clear($passwordBytes, 0, $passwordBytes.Length)
    [System.IO.File]::WriteAllText(
        $secretsPath,
        ($secrets | ConvertTo-Json -Depth 4),
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Convert-ToGitBashPath([string]$Path) {
    return ($Path -replace '\\', '/')
}

$mysqlPath = Convert-ToGitBashPath (Join-Path $mariaBinWindows 'mariadb.exe')
$dumpPath = Convert-ToGitBashPath (Join-Path $mariaBinWindows 'mariadb-dump.exe')
$corePath = Convert-ToGitBashPath (Join-Path $LabRoot 'source\mangos-tbc')

$config = @"
MYSQL_HOST="$($secrets.host)"
MYSQL_PORT="$($secrets.port)"
MYSQL_USERNAME="$($secrets.mangos_user)"
MYSQL_PASSWORD="$($secrets.mangos_password)"
MYSQL_USERIP="localhost"
MYSQL_COLSTAT=""
WORLD_DB_NAME="tbcmangos"
REALM_DB_NAME="tbcrealmd"
CHAR_DB_NAME="tbccharacters"
LOGS_DB_NAME="tbclogs"
MYSQL_PATH="$mysqlPath"
CORE_PATH="$corePath"
MYSQL_DUMP_PATH="$dumpPath"
LOCALES="YES"
DEV_UPDATES="NO"
AHBOT="NO"
PLAYERBOTS_DB="YES"
FORCE_WAIT="NO"
"@

[System.IO.File]::WriteAllText($configPath, $config, [System.Text.UTF8Encoding]::new($false))
& icacls.exe $configPath '/inheritance:r' '/grant:r' "$env:USERNAME`:(F)" 'SYSTEM:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to restrict ACL on $configPath" }

$env:LAB_DB_ROOT_PASSWORD = [string]$secrets.root_password
try {
    Push-Location -LiteralPath $installerRoot
    $command = './InstallFullDB.sh -InstallAll root "$LAB_DB_ROOT_PASSWORD" DeleteAll'
    & $bash -lc $command 2>&1 | Tee-Object -FilePath $logPath
    if ($LASTEXITCODE -ne 0) { throw "TBC database installation failed. See $logPath" }
} finally {
    Pop-Location
    Remove-Item Env:LAB_DB_ROOT_PASSWORD -ErrorAction SilentlyContinue
}

Write-Output 'LAB_DATABASES_INSTALLED'
