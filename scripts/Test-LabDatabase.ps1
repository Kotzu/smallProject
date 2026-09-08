[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB'
)

$ErrorActionPreference = 'Stop'
$bin = Join-Path $LabRoot 'toolchain\mariadb-12.3.2\MariaDB 12.3\bin'
$client = Join-Path $bin 'mariadb.exe'
$secrets = Get-Content -LiteralPath (Join-Path $LabRoot 'database\secrets.local.json') -Raw | ConvertFrom-Json

$result = & $client "--host=$($secrets.host)" "--port=$($secrets.port)" "--user=$($secrets.root_user)" "--password=$($secrets.root_password)" --batch --skip-column-names --execute "SELECT VERSION(), @@port, @@hostname;"
if ($LASTEXITCODE -ne 0) { throw 'LAB MariaDB query failed' }
Write-Output "LAB_DATABASE_QUERY_OK:$result"

