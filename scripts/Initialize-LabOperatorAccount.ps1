[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB',
    [string]$Username = 'PA_OPERATOR'
)

$ErrorActionPreference = 'Stop'
$secretPath = Join-Path $LabRoot 'database\operator.local.json'
$invoke = Join-Path $PSScriptRoot 'Invoke-LabRemoteCommand.ps1'

if (Test-Path -LiteralPath $secretPath) {
    $existing = Get-Content -LiteralPath $secretPath -Raw | ConvertFrom-Json
    & $invoke -Username $existing.username -Password $existing.password -Command 'server info' | Out-Null
    Write-Output "LAB_OPERATOR_ALREADY_READY:USERNAME=$($existing.username):SECRET=$secretPath"
    return
}

$alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
function New-RandomPassword([int]$Length = 24) {
    $chars = for ($i = 0; $i -lt $Length; $i++) {
        $alphabet[[System.Security.Cryptography.RandomNumberGenerator]::GetInt32($alphabet.Length)]
    }
    return -join $chars
}

$password = New-RandomPassword
$bootstrapUser = 'ADMINISTRATOR'
$bootstrapPassword = 'ADMINISTRATOR'
$create = & $invoke -Username $bootstrapUser -Password $bootstrapPassword -Command "account create $Username $password 1"
if ($create -match 'already exist') {
    & $invoke -Username $bootstrapUser -Password $bootstrapPassword -Command "account set password $Username $password $password" | Out-Null
}
elseif ($create -notmatch 'created') {
    throw "Could not create LAB operator account: $create"
}

& $invoke -Username $bootstrapUser -Password $bootstrapPassword -Command "account set gmlevel $Username 3" | Out-Null
& $invoke -Username $bootstrapUser -Password $bootstrapPassword -Command "account set addon $Username 1" | Out-Null
& $invoke -Username $Username -Password $password -Command 'server info' | Out-Null

$secret = [ordered]@{
    username = $Username
    password = $password
    expansion = 1
    gmlevel = 3
    created_at_utc = [DateTime]::UtcNow.ToString('o')
}
[System.IO.File]::WriteAllText($secretPath, ($secret | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
$identity = "$env:USERDOMAIN\$env:USERNAME"
& icacls.exe $secretPath '/inheritance:r' '/grant:r' "$identity`:(F)" 'SYSTEM:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to restrict ACL on $secretPath" }

# The stock CMaNGOS administrator credential is public. Rotate it only after the
# dedicated operator credential has been verified through RA.
$disabledBootstrapPassword = New-RandomPassword 32
& $invoke -Username $bootstrapUser -Password $bootstrapPassword -Command "account set password $bootstrapUser $disabledBootstrapPassword $disabledBootstrapPassword" | Out-Null

Write-Output "LAB_OPERATOR_READY:USERNAME=${Username}:SECRET=${secretPath}:DEFAULT_ADMIN_ROTATED"
