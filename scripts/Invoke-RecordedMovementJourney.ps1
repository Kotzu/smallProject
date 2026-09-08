[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z0-9][a-z0-9:_-]{2,79}$')]
    [string]$SemanticDestinationId,

    [Parameter(Mandatory)]
    [string]$ResultFile,

    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),

    [ValidateSet(25, 26)]
    [int]$ExpectedZoneIndex = 25,

    [double]$StartWorldZHint = 100.0,

    [ValidateRange(1, 20000)]
    [int]$MaxControlFrames = 4000,

    [ValidateRange(1, 32)]
    [int]$MaximumNavigationCycles = 8,

    [ValidateSet('geometric_predictive_v1', 'continuous_trajectory_v1', 'adaptive_trajectory_v1', 'pa_mppi_v1')]
    [string]$SteeringController = 'continuous_trajectory_v1',

    [ValidateRange(32, 20000)]
    [int]$MppiBatchSize = 1000,

    [ValidateRange(12, 160)]
    [int]$MppiTimeSteps = 56,

    [ValidateRange(0, 15)]
    [int]$InitialFocusDelaySeconds = 3
)

$ErrorActionPreference = 'Stop'
$operator = Join-Path $RepositoryRoot 'scripts\Invoke-LabClientOperator.ps1'
$python = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
$supervisor = Join-Path $RepositoryRoot 'integrations\windows-input\run_journey_combat_supervisor.py'
$authorization = Join-Path $RepositoryRoot 'data\runtime\operator\tbc_243_lab.active.json'
$continuousAuthorization = Join-Path $RepositoryRoot 'data\runtime\navigation-f3b\continuous-motion-authorization.json'
$continuousArm = Join-Path $RepositoryRoot 'data\runtime\navigation-f3b\continuous-motion-arm.json'
$movementRevalidation = Join-Path $RepositoryRoot 'data\runtime\operator\movement-realm-revalidation.json'
$structureGraph = Join-Path $RepositoryRoot 'data\runtime\client-catalog\tbc243-8606\azeroth-full-v3-structure-access-graph-v1.json'
$operatorControl = Join-Path $RepositoryRoot 'data\runtime\operator\movement-engine-control.json'
$recordingStarted = $false
$runnerExitCode = 1

foreach ($required in @(
    $operator, $python, $supervisor, $authorization,
    $continuousAuthorization, $structureGraph, $operatorControl
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Recorded movement prerequisite is missing: $required"
    }
}

# The bounded arm and realm revalidation are intentionally allowed to appear
# while the supervisor performs its read-only preflight. Requiring stale files
# here either starts with expired authority or prevents the documented
# runtime-arm wait from working at all.

try {
    if ($InitialFocusDelaySeconds -gt 0) {
        Start-Sleep -Seconds $InitialFocusDelaySeconds
    }
    & $operator `
        -Action ToggleVideoRecording `
        -RepositoryRoot $RepositoryRoot `
        -AuthorizationFile $authorization `
        -ConfirmedVisualState InWorldChatClosed
    $recordingStarted = $true

    & $python $supervisor `
        --session-authorization-file $authorization `
        --continuous-motion-authorization-file $continuousAuthorization `
        --continuous-motion-arm-file $continuousArm `
        --continuous-motion-revalidation-file $movementRevalidation `
        --runtime-arm-wait-seconds 45 `
        --structure-access-graph $structureGraph `
        --semantic-destination-id $SemanticDestinationId `
        --expected-zone-index $ExpectedZoneIndex `
        --start-world-z-hint $StartWorldZHint `
        --operator-control-file $operatorControl `
        --max-control-frames $MaxControlFrames `
        --steering-controller $SteeringController `
        --mppi-batch-size $MppiBatchSize `
        --mppi-time-steps $MppiTimeSteps `
        --maximum-navigation-cycles $MaximumNavigationCycles `
        --maximum-combat-handoffs 0 `
        --result-file $ResultFile `
        --acknowledge-autonomous-journey-combat
    $runnerExitCode = $LASTEXITCODE
}
finally {
    if ($recordingStarted) {
        & $operator `
            -Action ToggleVideoRecording `
            -RepositoryRoot $RepositoryRoot `
            -AuthorizationFile $authorization `
            -ConfirmedVisualState InWorldChatClosed
    }
}

if ($runnerExitCode -ne 0) {
    throw "Recorded movement journey failed with exit code $runnerExitCode."
}

Write-Output "RECORDED_MOVEMENT_JOURNEY_RESULT=$ResultFile"
