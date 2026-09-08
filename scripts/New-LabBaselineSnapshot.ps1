[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB',
    [string]$SnapshotName = 'LAB-baseline-001'
)

$ErrorActionPreference = 'Stop'
$snapshotRoot = Join-Path $LabRoot "snapshots\$SnapshotName"
$tempRoot = Join-Path $snapshotRoot '_database-dumps'
$archivePath = Join-Path $snapshotRoot 'databases.zip'
$manifestPath = Join-Path $snapshotRoot 'manifest.json'
$secretsPath = Join-Path $LabRoot 'database\secrets.local.json'
$dumpExe = Join-Path $LabRoot 'toolchain\mariadb-12.3.2\MariaDB 12.3\bin\mariadb-dump.exe'
$client = Join-Path $LabRoot 'toolchain\mariadb-12.3.2\MariaDB 12.3\bin\mariadb.exe'

foreach ($pidFile in 'runtime\mangosd.pid', 'runtime\realmd.pid') {
    if (Test-Path -LiteralPath (Join-Path $LabRoot $pidFile)) {
        throw "Stop LAB world and realm before snapshotting: $pidFile"
    }
}
foreach ($required in @($secretsPath, $dumpExe, $client)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing: $required" }
}
if (Test-Path -LiteralPath $snapshotRoot) { throw "Snapshot already exists: $snapshotRoot" }

New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$secrets = Get-Content -LiteralPath $secretsPath -Raw | ConvertFrom-Json
$previousDatabasePassword = $env:MYSQL_PWD
$env:MYSQL_PWD = $secrets.mangos_password
try {
    $databases = @('tbcrealmd', 'tbccharacters', 'tbcmangos', 'tbclogs')
    foreach ($database in $databases) {
        $target = Join-Path $tempRoot "$database.sql"
        & $dumpExe -h $secrets.host -P $secrets.port -u $secrets.mangos_user `
            --single-transaction --hex-blob --skip-lock-tables `
            "--result-file=$target" $database
        if ($LASTEXITCODE -ne 0) { throw "Database dump failed: $database" }
    }

    $operator = & $client -h $secrets.host -P $secrets.port -u $secrets.mangos_user --batch --skip-column-names `
        -e "SELECT CONCAT(id,':',username,':',gmlevel,':',expansion) FROM tbcrealmd.account WHERE username='PA_OPERATOR';"
    $botAccounts = & $client -h $secrets.host -P $secrets.port -u $secrets.mangos_user --batch --skip-column-names `
        -e "SELECT COUNT(*) FROM tbcrealmd.account WHERE username LIKE 'RNDBOT%';"
    $botCharacters = & $client -h $secrets.host -P $secrets.port -u $secrets.mangos_user --batch --skip-column-names `
        -e "SELECT COUNT(*) FROM tbccharacters.characters c JOIN tbcrealmd.account a ON a.id=c.account WHERE a.username LIKE 'RNDBOT%';"
}
finally {
    $env:MYSQL_PWD = $previousDatabasePassword
}

Compress-Archive -Path (Join-Path $tempRoot '*.sql') -DestinationPath $archivePath -CompressionLevel Optimal
$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
$dataCounts = [ordered]@{}
foreach ($name in 'dbc', 'maps', 'vmaps', 'mmaps') {
    $files = Get-ChildItem -LiteralPath (Join-Path $LabRoot "client-data\$name") -Recurse -File
    $dataCounts[$name] = [ordered]@{
        files = $files.Count
        bytes = [long](($files | Measure-Object Length -Sum).Sum)
    }
}

$manifest = [ordered]@{
    schema_version = '1.0'
    snapshot = $SnapshotName
    created_at_utc = [DateTime]::UtcNow.ToString('o')
    recovery_scope = 'databases plus immutable source/toolchain references'
    database_archive = [ordered]@{
        file = 'databases.zip'
        sha256 = $archiveHash
        bytes = (Get-Item -LiteralPath $archivePath).Length
        databases = @('tbcrealmd', 'tbccharacters', 'tbcmangos', 'tbclogs')
    }
    operator = $operator
    playerbots = [ordered]@{
        accounts = [int]$botAccounts
        characters_available = [int]$botCharacters
        max_active = 20
        autologin = $false
    }
    client_data = $dataCounts
    source_manifest = '..\..\source-manifest.json'
    toolchain_manifest = '..\..\toolchain-manifest.json'
}
[System.IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))

$resolvedSnapshot = (Resolve-Path -LiteralPath $snapshotRoot).Path
$resolvedTemp = (Resolve-Path -LiteralPath $tempRoot).Path
if (-not $resolvedTemp.StartsWith($resolvedSnapshot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing cleanup outside snapshot: $resolvedTemp"
}
Remove-Item -LiteralPath $resolvedTemp -Recurse -Force

$identity = "$env:USERDOMAIN\$env:USERNAME"
& icacls.exe $snapshotRoot '/inheritance:r' '/grant:r' "$identity`:(OI)(CI)(F)" 'SYSTEM:(OI)(CI)(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to restrict snapshot root ACL: $snapshotRoot" }
& icacls.exe $snapshotRoot '/grant:r' "$identity`:(F)" 'SYSTEM:(F)' '/T' | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to restrict snapshot ACL: $snapshotRoot" }

Write-Output "LAB_SNAPSHOT_READY:${SnapshotName}:SHA256=$archiveHash"
