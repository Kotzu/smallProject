[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ClientRoot = 'E:\Games\WoW TBC 2.4.3',
    [switch]$UpgradeVerifiedPrevious,
    [switch]$RestoreLatestVerifiedPrevious,
    [switch]$AcknowledgeLiveHotReload
)

$ErrorActionPreference = 'Stop'
$expectedHashes = @{
    'PerfectAssassinObserver.toc' = 'C957167CD9299FB64793898ABEF7A847D8E27FD5A6E81F9979B8C2710E8CBD02'
    'PerfectAssassinObserver.lua' = 'E5FF1EFADBDDF5187ACCBCDE6A990C79FC3B38CB10EBEF3D9BF9075EB1BFE35C'
    'README.md' = 'F02EF1D31B6B570290664A5650AC6AFC2B76160C46CB9B3861C71A2E17F07653'
}
$previousStableHashes = @{
    'PerfectAssassinObserver.toc' = '574B1772464BEE479CD42FCA22F8ADB428CD99DD38DA781AEAE2BD03836BF9C6'
    'PerfectAssassinObserver.lua' = 'B0DC944A68B99F1315BFF84EEF947CF3B7B7F866BB56DE9DB502DF0064C3BFA5'
    'README.md' = '377EEFA79A9DEF2AE6370628CCE17D9850E70AF1F45781600999C0B590990451'
}
$expectedArtifactNames = @(
    'PerfectAssassinObserver.toc',
    'PerfectAssassinObserver.lua',
    'README.md'
)
# Only the exact immediately previous Stable artifact is upgradeable. Older
# snapshots are intentionally refused because this installer must always be
# able to restore the deployment predecessor it just replaced.
$verifiedPreviousHashSets = @($previousStableHashes)

if ($UpgradeVerifiedPrevious -and $RestoreLatestVerifiedPrevious) {
    throw '-UpgradeVerifiedPrevious and -RestoreLatestVerifiedPrevious are mutually exclusive.'
}

$wowProcesses = @(Microsoft.PowerShell.Management\Get-Process -Name Wow -ErrorAction SilentlyContinue)
if ($wowProcesses.Count -gt 0) {
    if (-not $AcknowledgeLiveHotReload) {
        throw 'Wow.exe is running. Stop the client before installing the observer addon.'
    }
    if (
        $wowProcesses.Count -ne 1 -or
        -not $UpgradeVerifiedPrevious -or
        $RestoreLatestVerifiedPrevious
    ) {
        throw 'Live hot-reload staging requires exactly one Wow.exe, -UpgradeVerifiedPrevious, and no restore operation.'
    }
}
elseif ($AcknowledgeLiveHotReload) {
    throw '-AcknowledgeLiveHotReload requires exactly one running Wow.exe.'
}

function Assert-ContainedPath {
    param([string]$Path, [string]$Root, [string]$Label)
    $fullPath = [IO.Path]::GetFullPath($Path)
    $fullRoot = [IO.Path]::GetFullPath($Root)
    $relative = [IO.Path]::GetRelativePath($fullRoot, $fullPath)
    if (
        [IO.Path]::IsPathRooted($relative) -or
        $relative -eq '..' -or
        $relative.StartsWith(('..' + [IO.Path]::DirectorySeparatorChar), [StringComparison]::Ordinal)
    ) {
        throw "$Label escaped its intended root: $fullPath"
    }
    return $fullPath
}

function Assert-NoReparsePointInExistingPath {
    param([string]$Path, [string]$Label)
    $fullPath = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($fullPath)
    $current = $root
    $relative = $fullPath.Substring($root.Length)
    foreach ($part in $relative.Split(@([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar), [StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path $current $part
        if (-not (Test-Path -LiteralPath $current)) {
            continue
        }
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Label contains a reparse point and is refused: $current"
        }
    }
}

function Assert-SafeFlatArtifactDirectory {
    param(
        [string]$Directory,
        [string]$Label,
        [switch]$AllowMissingArtifacts
    )
    Assert-NoReparsePointInExistingPath -Path $Directory -Label $Label
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
        throw "$Label directory is missing: $Directory"
    }
    $entries = @(Get-ChildItem -LiteralPath $Directory -Force)
    foreach ($item in $entries) {
        if (
            $item.PSIsContainer -or
            ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
            $item.Name -notin $expectedArtifactNames
        ) {
            throw "$Label contains an unexpected or unsafe entry: $($item.FullName)"
        }
    }
    if (-not $AllowMissingArtifacts) {
        $names = @($entries.Name | Sort-Object)
        $expectedNames = @($expectedArtifactNames | Sort-Object)
        if (
            $names.Count -ne $expectedNames.Count -or
            @(Compare-Object -ReferenceObject $expectedNames -DifferenceObject $names).Count -ne 0
        ) {
            throw "$Label does not contain exactly the expected observer artifacts."
        }
    }
}

function Copy-ExactArtifactSet {
    param([string]$From, [string]$To)
    foreach ($name in $expectedArtifactNames) {
        Copy-Item -LiteralPath (Join-Path $From $name) -Destination (Join-Path $To $name)
    }
}

function Remove-ExactArtifactDirectory {
    param([string]$Directory, [string]$Label)
    Assert-SafeFlatArtifactDirectory -Directory $Directory -Label $Label
    foreach ($name in $expectedArtifactNames) {
        Remove-Item -LiteralPath (Join-Path $Directory $name) -Force
    }
    Remove-Item -LiteralPath $Directory -Force
}

function Remove-PartialExactArtifactDirectory {
    param([string]$Directory, [string]$Label)
    Assert-SafeFlatArtifactDirectory -Directory $Directory -Label $Label -AllowMissingArtifacts
    foreach ($name in $expectedArtifactNames) {
        $artifact = Join-Path $Directory $name
        if (Test-Path -LiteralPath $artifact -PathType Leaf) {
            Remove-Item -LiteralPath $artifact -Force
        }
    }
    if (@(Get-ChildItem -LiteralPath $Directory -Force).Count -ne 0) {
        throw "$Label could not be emptied using the exact artifact allowlist."
    }
    Remove-Item -LiteralPath $Directory -Force
}

$source = [IO.Path]::GetFullPath((Join-Path $RepositoryRoot 'integrations\tbc243-addon\PerfectAssassinObserver'))
$client = [IO.Path]::GetFullPath($ClientRoot)
$addonsRoot = [IO.Path]::GetFullPath((Join-Path $client 'Interface\AddOns'))
$target = Assert-ContainedPath -Path (Join-Path $addonsRoot 'PerfectAssassinObserver') -Root $addonsRoot -Label 'Observer addon target'
if ($target -eq $addonsRoot) {
    throw 'Observer addon target cannot equal the AddOns root.'
}
if (-not (Test-Path -LiteralPath $source -PathType Container)) {
    throw "Observer source directory is missing: $source"
}
if (-not (Test-Path -LiteralPath $addonsRoot -PathType Container)) {
    throw "Client AddOns directory is missing: $addonsRoot"
}
Assert-NoReparsePointInExistingPath -Path $source -Label 'Observer source'
Assert-NoReparsePointInExistingPath -Path $client -Label 'Client root'
Assert-NoReparsePointInExistingPath -Path $addonsRoot -Label 'Client AddOns root'
Assert-SafeFlatArtifactDirectory -Directory $source -Label 'Observer source'

foreach ($entry in $expectedHashes.GetEnumerator()) {
    $sourceFile = Join-Path $source $entry.Key
    if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
        throw "Required observer artifact is missing: $sourceFile"
    }
    $actual = (Get-FileHash -LiteralPath $sourceFile -Algorithm SHA256).Hash
    if ($actual -ne $entry.Value) {
        throw "Source hash mismatch for $($entry.Key). Expected $($entry.Value), got $actual"
    }
}

function Test-HashSet([string]$Directory, [hashtable]$Hashes) {
    foreach ($entry in $Hashes.GetEnumerator()) {
        $file = Join-Path $Directory $entry.Key
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { return $false }
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.Value) { return $false }
    }
    return $true
}

function Get-LatestVerifiedPreviousBackup([string]$BackupRoot) {
    if (-not (Test-Path -LiteralPath $BackupRoot -PathType Container)) {
        throw "Observer backup root is missing: $BackupRoot"
    }
    Assert-NoReparsePointInExistingPath -Path $BackupRoot -Label 'Observer backup root'
    $verified = @()
    foreach ($item in @(Get-ChildItem -LiteralPath $BackupRoot -Force)) {
        if (
            -not $item.PSIsContainer -or
            ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
        ) {
            throw "Observer backup root contains an unexpected or unsafe entry: $($item.FullName)"
        }
        $previousNameMatch = [regex]::Match($item.Name, '^PerfectAssassinObserver-(\d{8}T\d{9})$')
        $currentNameMatch = [regex]::Match($item.Name, '^PerfectAssassinObserver-current-before-restore-(\d{8}T\d{9})$')
        if (-not $previousNameMatch.Success -and -not $currentNameMatch.Success) {
            throw "Observer backup root contains an unexpected backup name: $($item.FullName)"
        }
        $timestampText = if ($previousNameMatch.Success) { $previousNameMatch.Groups[1].Value } else { $currentNameMatch.Groups[1].Value }
        $backupTimestamp = [DateTime]::MinValue
        if (-not [DateTime]::TryParseExact(
            $timestampText,
            'yyyyMMddTHHmmssfff',
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::None,
            [ref]$backupTimestamp
        )) {
            throw "Observer backup name contains an invalid timestamp: $($item.FullName)"
        }
        $candidate = Assert-ContainedPath -Path $item.FullName -Root $BackupRoot -Label 'Observer backup candidate'
        Assert-SafeFlatArtifactDirectory -Directory $candidate -Label 'Observer backup candidate'
        if (
            $previousNameMatch.Success -and
            (Test-HashSet $candidate $previousStableHashes)
        ) {
            $verified += [PSCustomObject]@{
                Name = $item.Name
                Path = $candidate
                Timestamp = $backupTimestamp
            }
        }
    }
    if ($verified.Count -eq 0) {
        throw 'No exact verified 0.5.9 observer backup is available for restore.'
    }
    return ($verified | Sort-Object Timestamp, Name -Descending | Select-Object -First 1).Path
}

if ($RestoreLatestVerifiedPrevious) {
    if (-not (Test-Path -LiteralPath $target -PathType Container)) {
        throw "Current observer addon is not installed; refusing previous-stable restore: $target"
    }
    Assert-SafeFlatArtifactDirectory -Directory $target -Label 'Installed observer addon'
    if (-not (Test-HashSet $target $expectedHashes)) {
        throw 'Previous-stable restore requires the exact current 0.5.10 observer artifact to be installed.'
    }

    $backupRoot = [IO.Path]::GetFullPath((Join-Path $RepositoryRoot 'data\runtime\addon-backups'))
    $previousBackup = Get-LatestVerifiedPreviousBackup -BackupRoot $backupRoot
    $restoreStage = Assert-ContainedPath -Path (Join-Path $addonsRoot ('.PerfectAssassinObserver.restore-stage-' + [Guid]::NewGuid().ToString('N'))) -Root $addonsRoot -Label 'Observer restore staging path'
    $currentBackupPath = Assert-ContainedPath -Path (Join-Path $backupRoot ('PerfectAssassinObserver-current-before-restore-' + (Get-Date -Format 'yyyyMMddTHHmmssfff'))) -Root $backupRoot -Label 'Current observer backup path'
    $currentBackupComplete = $false

    try {
        New-Item -ItemType Directory -Path $restoreStage | Out-Null
        Copy-ExactArtifactSet -From $previousBackup -To $restoreStage
        Assert-SafeFlatArtifactDirectory -Directory $restoreStage -Label 'Previous-stable restore staging directory'
        if (-not (Test-HashSet $restoreStage $previousStableHashes)) {
            throw 'Previous-stable restore staging failed exact 0.5.9 hash validation.'
        }

        Assert-SafeFlatArtifactDirectory -Directory $target -Label 'Installed observer addon'
        if (-not (Test-HashSet $target $expectedHashes)) {
            throw 'Installed observer addon changed before current-version backup.'
        }
        New-Item -ItemType Directory -Path $currentBackupPath | Out-Null
        Assert-SafeFlatArtifactDirectory -Directory $currentBackupPath -Label 'Current observer backup staging directory' -AllowMissingArtifacts
        Copy-ExactArtifactSet -From $target -To $currentBackupPath
        Assert-SafeFlatArtifactDirectory -Directory $currentBackupPath -Label 'Current observer backup'
        if (-not (Test-HashSet $currentBackupPath $expectedHashes)) {
            throw 'Current 0.5.10 observer backup failed validation.'
        }
        $currentBackupComplete = $true

        Assert-SafeFlatArtifactDirectory -Directory $previousBackup -Label 'Selected previous-stable observer backup'
        if (-not (Test-HashSet $previousBackup $previousStableHashes)) {
            throw 'Selected previous-stable observer backup changed before restore.'
        }
        try {
            Remove-ExactArtifactDirectory -Directory $target -Label 'Installed observer addon'
            Move-Item -LiteralPath $restoreStage -Destination $target
            Assert-SafeFlatArtifactDirectory -Directory $target -Label 'Restored previous-stable observer addon'
            if (-not (Test-HashSet $target $previousStableHashes)) {
                throw 'Restored observer addon failed exact 0.5.9 hash validation.'
            }
        }
        catch {
            $restoreError = $_
            if (Test-Path -LiteralPath $target) {
                Remove-PartialExactArtifactDirectory -Directory $target -Label 'Failed previous-stable observer restore'
            }
            New-Item -ItemType Directory -Path $target | Out-Null
            Copy-ExactArtifactSet -From $currentBackupPath -To $target
            Assert-SafeFlatArtifactDirectory -Directory $target -Label 'Recovered current observer addon'
            if (-not (Test-HashSet $target $expectedHashes)) {
                throw 'Previous-stable restore failed and recovery of current 0.5.10 also failed.'
            }
            throw $restoreError
        }
    }
    finally {
        if (Test-Path -LiteralPath $restoreStage) {
            Remove-PartialExactArtifactDirectory -Directory $restoreStage -Label 'Observer restore staging cleanup'
        }
        if (
            -not $currentBackupComplete -and
            (Test-Path -LiteralPath $currentBackupPath)
        ) {
            Remove-PartialExactArtifactDirectory -Directory $currentBackupPath -Label 'Incomplete current observer backup cleanup'
        }
    }

    Write-Output "PA020_ADDON_RESTORED_FROM=$previousBackup"
    Write-Output "PA020_CURRENT_ADDON_BACKUP=$currentBackupPath"
    foreach ($entry in $previousStableHashes.GetEnumerator() | Sort-Object Key) {
        Write-Output "$($entry.Key)_SHA256=$($entry.Value)"
    }
    exit 0
}

$upgradeRequired = $false
$matchedPreviousHashes = $null
if (Test-Path -LiteralPath $target) {
    Assert-SafeFlatArtifactDirectory -Directory $target -Label 'Installed observer addon'
    if (Test-HashSet $target $expectedHashes) {
        Write-Output "PA020_ADDON_ALREADY_INSTALLED=$target"
        exit 0
    }
    foreach ($hashSet in $verifiedPreviousHashSets) {
        if (Test-HashSet $target $hashSet) {
            $matchedPreviousHashes = $hashSet
            break
        }
    }
    if ($null -eq $matchedPreviousHashes) {
        throw "Existing addon is neither the current nor the verified previous artifact; refusing overwrite: $target"
    }
    if (-not $UpgradeVerifiedPrevious) {
        throw 'A verified previous observer addon is installed. Re-run with -UpgradeVerifiedPrevious to create a backup and install the current artifact.'
    }
    $upgradeRequired = $true
}

$stage = Assert-ContainedPath -Path (Join-Path $addonsRoot ('.PerfectAssassinObserver.stage-' + [Guid]::NewGuid().ToString('N'))) -Root $addonsRoot -Label 'Observer staging path'

try {
    New-Item -ItemType Directory -Path $stage | Out-Null
    Copy-Item -LiteralPath (Join-Path $source 'PerfectAssassinObserver.toc') -Destination $stage
    Copy-Item -LiteralPath (Join-Path $source 'PerfectAssassinObserver.lua') -Destination $stage
    Copy-Item -LiteralPath (Join-Path $source 'README.md') -Destination $stage
    Assert-SafeFlatArtifactDirectory -Directory $stage -Label 'Observer staging directory'
    foreach ($entry in $expectedHashes.GetEnumerator()) {
        $stagedFile = Join-Path $stage $entry.Key
        $actual = (Get-FileHash -LiteralPath $stagedFile -Algorithm SHA256).Hash
        if ($actual -ne $entry.Value) {
            throw "Staged hash mismatch for $($entry.Key)"
        }
    }
    if ($upgradeRequired) {
        $backupRoot = [IO.Path]::GetFullPath((Join-Path $RepositoryRoot 'data\runtime\addon-backups'))
        $backupPath = Assert-ContainedPath -Path (Join-Path $backupRoot ('PerfectAssassinObserver-' + (Get-Date -Format 'yyyyMMddTHHmmssfff'))) -Root $backupRoot -Label 'Observer backup path'
        $previousBackupComplete = $false
        try {
            New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
            Assert-NoReparsePointInExistingPath -Path $backupRoot -Label 'Observer backup root'
            New-Item -ItemType Directory -Path $backupPath | Out-Null
            Assert-SafeFlatArtifactDirectory -Directory $backupPath -Label 'Observer backup staging directory' -AllowMissingArtifacts
            Assert-SafeFlatArtifactDirectory -Directory $target -Label 'Installed observer addon'
            if (-not (Test-HashSet $target $matchedPreviousHashes)) {
                throw 'Installed observer addon changed after verified-previous classification.'
            }
            Copy-ExactArtifactSet -From $target -To $backupPath
            Assert-SafeFlatArtifactDirectory -Directory $backupPath -Label 'Verified previous observer backup'
            if (-not (Test-HashSet $backupPath $matchedPreviousHashes)) {
                throw "Verified previous addon backup failed validation: $backupPath"
            }
            $previousBackupComplete = $true
        }
        finally {
            if (
                -not $previousBackupComplete -and
                (Test-Path -LiteralPath $backupPath)
            ) {
                Remove-PartialExactArtifactDirectory -Directory $backupPath -Label 'Incomplete previous observer backup cleanup'
            }
        }
        # Prove rollback discovery can select an exact previous Stable before
        # the installed target is touched. Any poisoned or malformed entry in
        # the backup root therefore blocks the upgrade non-destructively.
        [void](Get-LatestVerifiedPreviousBackup -BackupRoot $backupRoot)
        try {
            Remove-ExactArtifactDirectory -Directory $target -Label 'Installed observer addon'
            Move-Item -LiteralPath $stage -Destination $target
            Assert-SafeFlatArtifactDirectory -Directory $target -Label 'Installed observer addon'
            if (-not (Test-HashSet $target $expectedHashes)) {
                throw 'Installed current observer addon failed post-install hash validation.'
            }
        }
        catch {
            $installError = $_
            if (Test-Path -LiteralPath $target) {
                Remove-PartialExactArtifactDirectory -Directory $target -Label 'Failed current observer install'
            }
            New-Item -ItemType Directory -Path $target | Out-Null
            Copy-ExactArtifactSet -From $backupPath -To $target
            Assert-SafeFlatArtifactDirectory -Directory $target -Label 'Restored observer addon'
            if (-not (Test-HashSet $target $matchedPreviousHashes)) {
                throw 'Current addon install failed and recovery of the verified previous addon also failed.'
            }
            throw $installError
        }
        Write-Output "PA020_PREVIOUS_ADDON_BACKUP=$backupPath"
    }
    else {
        Move-Item -LiteralPath $stage -Destination $target
        Assert-SafeFlatArtifactDirectory -Directory $target -Label 'Installed observer addon'
        if (-not (Test-HashSet $target $expectedHashes)) {
            Remove-ExactArtifactDirectory -Directory $target -Label 'Failed fresh observer install'
            throw 'Installed current observer addon failed post-install hash validation.'
        }
    }
}
finally {
    if (Test-Path -LiteralPath $stage) {
        Assert-SafeFlatArtifactDirectory -Directory $stage -Label 'Observer staging cleanup' -AllowMissingArtifacts
        foreach ($name in $expectedArtifactNames) {
            $stagedArtifact = Join-Path $stage $name
            if (Test-Path -LiteralPath $stagedArtifact -PathType Leaf) {
                Remove-Item -LiteralPath $stagedArtifact -Force
            }
        }
        Remove-Item -LiteralPath $stage -Force
    }
}

Write-Output "PA020_ADDON_INSTALLED=$target"
foreach ($entry in $expectedHashes.GetEnumerator() | Sort-Object Key) {
    Write-Output "$($entry.Key)_SHA256=$($entry.Value)"
}
