[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB',
    [string]$Username = 'ADMIN'
)

$ErrorActionPreference = 'Stop'
$secretPath = Join-Path $LabRoot 'database\observer-account.local.json'
$operatorPath = Join-Path $LabRoot 'database\operator.local.json'
$invoke = Join-Path $PSScriptRoot 'Invoke-LabRemoteCommand.ps1'

if (-not (Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 3443 -State Listen -ErrorAction SilentlyContinue)) {
    throw 'LAB remote administration is not listening on 127.0.0.1:3443'
}
if (-not (Test-Path -LiteralPath $operatorPath -PathType Leaf)) {
    throw "LAB operator secret is missing: $operatorPath"
}

$operator = Get-Content -LiteralPath $operatorPath -Raw | ConvertFrom-Json

$alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
function New-RandomPassword([int]$Length = 14) {
    $chars = for ($index = 0; $index -lt $Length; $index++) {
        $alphabet[[Security.Cryptography.RandomNumberGenerator]::GetInt32($alphabet.Length)]
    }
    return -join $chars
}

if (Test-Path -LiteralPath $secretPath -PathType Leaf) {
    $existing = Get-Content -LiteralPath $secretPath -Raw | ConvertFrom-Json
    if ($existing.username -ne $Username -or $existing.gmlevel -ne 0 -or $existing.expansion -ne 1) {
        throw "Existing observer account manifest does not match the requested boundary: $secretPath"
    }
    if ($existing.password.Length -le 16) {
        Write-Output "LAB_OBSERVER_ACCOUNT_ALREADY_READY:USERNAME=$($existing.username):SECRET=$secretPath"
        exit 0
    }
    Write-Output 'LAB_OBSERVER_ACCOUNT_PASSWORD_ROTATION_REQUIRED:LEGACY_MAX=16'
}

$password = New-RandomPassword
$create = & $invoke -Username $operator.username -Password $operator.password -Command "account create $Username $password 1"
if ($create -match 'already exist') {
    & $invoke -Username $operator.username -Password $operator.password -Command "account set password $Username $password $password" | Out-Null
}
elseif ($create -notmatch 'created') {
    throw "Could not create LAB observer account: $create"
}

& $invoke -Username $operator.username -Password $operator.password -Command "account set gmlevel $Username 0" | Out-Null
& $invoke -Username $operator.username -Password $operator.password -Command "account set addon $Username 1" | Out-Null

$secret = [ordered]@{
    username = $Username
    password = $password
    expansion = 1
    gmlevel = 0
    purpose = 'bounded_addon_observer_probe_not_champion'
    created_at_utc = [DateTime]::UtcNow.ToString('o')
}
[IO.File]::WriteAllText(
    $secretPath,
    ($secret | ConvertTo-Json),
    [Text.UTF8Encoding]::new($false)
)
$identity = "$env:USERDOMAIN\$env:USERNAME"
& icacls.exe $secretPath '/inheritance:r' '/grant:r' "$identity`:(F)" 'SYSTEM:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to restrict ACL on $secretPath"
}

Write-Output "LAB_OBSERVER_ACCOUNT_READY:USERNAME=${Username}:GMLEVEL=0:EXPANSION=1:SECRET=${secretPath}"
