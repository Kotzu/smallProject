[CmdletBinding()]
param(
    [string]$LabRoot = 'E:\WoWserver\TBC-LAB'
)

$ErrorActionPreference = 'Stop'

$runtime = Join-Path $LabRoot 'runtime\core-playerbots'
$secretsPath = Join-Path $LabRoot 'database\secrets.local.json'
$secrets = Get-Content -LiteralPath $secretsPath -Raw | ConvertFrom-Json
$dataDir = (Join-Path $LabRoot 'client-data') -replace '\\', '/'
$logsDir = (Join-Path $LabRoot 'logs') -replace '\\', '/'
$connectionPrefix = "$($secrets.host);$($secrets.port);$($secrets.mangos_user);$($secrets.mangos_password)"

function Write-RestrictedConfig([string]$DistName, [string]$ConfigName, [scriptblock]$Transform) {
    $source = Join-Path $runtime $DistName
    $target = Join-Path $runtime $ConfigName
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing distribution config: $source" }
    $content = Get-Content -LiteralPath $source -Raw
    $content = & $Transform $content
    [System.IO.File]::WriteAllText($target, $content, [System.Text.UTF8Encoding]::new($false))
    & icacls.exe $target '/inheritance:r' '/grant:r' "$env:USERNAME`:(F)" 'SYSTEM:(F)' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to restrict ACL on $target" }
}

Write-RestrictedConfig 'mangosd.conf.dist' 'mangosd.conf' {
    param($content)
    $content = $content -replace '(?m)^DataDir\s*=.*$', "DataDir = `"$dataDir`""
    $content = $content -replace '(?m)^LogsDir\s*=.*$', "LogsDir = `"$logsDir`""
    $content = $content -replace '(?m)^BindIP\s*=.*$', 'BindIP = "127.0.0.1"'
    $content = $content -replace '(?m)^Console\.Enable\s*=.*$', 'Console.Enable = 0'
    $content = $content -replace '(?m)^Ra\.Enable\s*=.*$', 'Ra.Enable = 1'
    $content = $content -replace '(?m)^Ra\.IP\s*=.*$', 'Ra.IP = 127.0.0.1'
    $content = $content -replace '(?m)^Ra\.Restricted\s*=.*$', 'Ra.Restricted = 0'
    $afkDisconnectPattern = '(?m)^Player\.AFK\.DisconnectTimeout\s*=.*$'
    if ($content -notmatch $afkDisconnectPattern) {
        throw 'Player.AFK.DisconnectTimeout is missing from mangosd.conf.dist; rebuild/install the patched LAB core before writing runtime config.'
    }
    $content = $content -replace $afkDisconnectPattern, 'Player.AFK.DisconnectTimeout = 0'
    $overspeedPingPattern = '(?m)^MaxOverspeedPings\s*=.*$'
    if ($content -notmatch $overspeedPingPattern) {
        throw 'MaxOverspeedPings is missing from mangosd.conf.dist; refusing an ambiguous LAB network timeout policy.'
    }
    # The legacy 2.4.3 client can legitimately emit PING packets inside the
    # core's hard-coded 27 second window.  With the upstream default of 2 the
    # third such packet closes an otherwise healthy loopback session.
    $content = $content -replace $overspeedPingPattern, 'MaxOverspeedPings = 0'
    $content = $content -replace '(?m)^LoginDatabaseInfo\s*=.*$', "LoginDatabaseInfo = `"$connectionPrefix;tbcrealmd`""
    $content = $content -replace '(?m)^WorldDatabaseInfo\s*=.*$', "WorldDatabaseInfo = `"$connectionPrefix;tbcmangos`""
    $content = $content -replace '(?m)^CharacterDatabaseInfo\s*=.*$', "CharacterDatabaseInfo = `"$connectionPrefix;tbccharacters`""
    $content = $content -replace '(?m)^LogsDatabaseInfo\s*=.*$', "LogsDatabaseInfo = `"$connectionPrefix;tbclogs`""
    return $content
}

Write-RestrictedConfig 'realmd.conf.dist' 'realmd.conf' {
    param($content)
    $content = $content -replace '(?m)^LogsDir\s*=.*$', "LogsDir = `"$logsDir`""
    $content = $content -replace '(?m)^BindIP\s*=.*$', 'BindIP = "127.0.0.1"'
    $content = $content -replace '(?m)^LoginDatabaseInfo\s*=.*$', "LoginDatabaseInfo = `"$connectionPrefix;tbcrealmd`""
    return $content
}

Write-RestrictedConfig 'aiplayerbot.conf.dist' 'aiplayerbot.conf' {
    param($content)
    $content = $content -replace '(?m)^AiPlayerbot\.RandomBotAutologin\s*=.*$', 'AiPlayerbot.RandomBotAutologin = 0'
    $content = $content -replace '(?m)^AiPlayerbot\.RandomBotLoginAtStartup\s*=.*$', 'AiPlayerbot.RandomBotLoginAtStartup = 0'
    $content = $content -replace '(?m)^AiPlayerbot\.RandomBotJoinLfg\s*=.*$', 'AiPlayerbot.RandomBotJoinLfg = 0'
    $content = $content -replace '(?m)^AiPlayerbot\.RandomBotJoinBG\s*=.*$', 'AiPlayerbot.RandomBotJoinBG = 0'
    $content = $content -replace '(?m)^AiPlayerbot\.MinRandomBots\s*=.*$', 'AiPlayerbot.MinRandomBots = 20'
    $content = $content -replace '(?m)^AiPlayerbot\.MaxRandomBots\s*=.*$', 'AiPlayerbot.MaxRandomBots = 20'
    $content = $content -replace '(?m)^AiPlayerbot\.RandomBotAccountCount\s*=.*$', 'AiPlayerbot.RandomBotAccountCount = 5'
    return $content
}

if (Test-Path -LiteralPath (Join-Path $runtime 'anticheat.conf.dist')) {
    Write-RestrictedConfig 'anticheat.conf.dist' 'anticheat.conf' {
        param($content)
        $wardenEnablePattern = '(?m)^Warden\.Enable\s*=.*$'
        if ($content -notmatch $wardenEnablePattern) {
            throw 'Warden.Enable is missing from anticheat.conf.dist; refusing to write an ambiguous LAB anticheat config.'
        }
        $content = $content -replace $wardenEnablePattern, 'Warden.Enable = 0'
        return $content
    }
}

Write-Output 'LAB_RUNTIME_CONFIG_WRITTEN'
