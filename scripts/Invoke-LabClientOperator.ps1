[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('Status', 'Launch', 'BindOperatorLaunch', 'AdoptSession', 'RenewSessionIdentity', 'IssueMovementRealmRevalidation', 'IssueCombatRealmRevalidation', 'ArmSession', 'DisarmSession', 'Login', 'InspectAddons', 'EnterWorld', 'AcknowledgeLoginError', 'AcknowledgeDisconnect', 'ReleaseSpirit', 'RetrieveCorpse', 'ToggleEnemyNameplates', 'OpenWorldMap', 'CloseWorldMap', 'DismissGameMenu', 'SetDnd', 'ClearTarget', 'ToggleVideoRecording', 'ReloadUi', 'ApplyPredatorUiProfile', 'RestorePredatorUiProfile', 'SnapshotPredatorUiProfile', 'SetUiScale80', 'SetUiScale100', 'RestoreUiScaleDefault', 'ResizeWindowCompact', 'ResizeWindowBaseline', 'Capture', 'SaveShadowReplay', 'Logout', 'Close', 'Import')]
    [string]$Action,

    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ClientRoot = 'E:\Games\WoW TBC 2.4.3',
    [string]$CredentialPath = 'E:\WoWserver\TBC-LAB\database\predator-login.local.json',
    [string]$AuthorizationFile = '',
    [string]$MovementAuthorizationFile = '',
    [string]$CombatAuthorizationFile = '',
    [ValidateRange(1, 60)]
    [int]$TimeoutSeconds = 30,
    [ValidateSet('LoginScreen', 'CharacterSelect', 'InWorld', 'InWorldChatClosed', 'InWorldPanelOpen', 'WorldMapOpen', 'GameMenuOpen', 'DisconnectedDialog', 'DeadInWorld', 'GhostAtCorpse')]
    [string]$ConfirmedVisualState,
    [switch]$AcknowledgeClientRisk,
    [switch]$AcknowledgeSessionIdentity,
    [switch]$AcknowledgeWindowRebind,
    [switch]$AcknowledgeAuthorizationRebind,
    [switch]$AcknowledgeRuntimeArm,
    [switch]$AcknowledgeSinglePulse,
    [switch]$AcknowledgeContinuousMotion,
    [switch]$AcknowledgeControlledCombat
)

function Assert-JsonSchema {
    param([string]$Json, [string]$SchemaPath, [string]$RecordName)
    if (-not (Test-Path -LiteralPath $SchemaPath -PathType Leaf)) {
        throw "$RecordName schema is missing: $SchemaPath"
    }
    if (-not (Get-Command Test-Json -ErrorAction SilentlyContinue)) {
        throw "Test-Json is unavailable; $RecordName validation is refused."
    }
    if (-not (Test-Json -Json $Json -SchemaFile $SchemaPath -ErrorAction Stop)) {
        throw "$RecordName does not match its versioned schema."
    }
}

function Get-ByteArraySha256 {
    param([byte[]]$Bytes)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha256.ComputeHash($Bytes))).Replace('-', '')
    }
    finally {
        $sha256.Dispose()
    }
}

function ConvertFrom-StrictJson {
    param(
        [Parameter(Mandatory)][string]$Json,
        [Parameter(Mandatory)][string]$RecordName,
        [switch]$IncludeToken
    )
    try {
        if (-not (Test-Json -Json $Json -ErrorAction Stop)) {
            throw "$RecordName is not standards-compliant JSON."
        }
        $loadSettings = [Newtonsoft.Json.Linq.JsonLoadSettings]::new()
        $loadSettings.DuplicatePropertyNameHandling = [Newtonsoft.Json.Linq.DuplicatePropertyNameHandling]::Error
        [void][Newtonsoft.Json.Linq.JToken]::Parse($Json, $loadSettings)
        $stringReader = [System.IO.StringReader]::new($Json)
        $jsonReader = [Newtonsoft.Json.JsonTextReader]::new($stringReader)
        try {
            $jsonReader.DateParseHandling = [Newtonsoft.Json.DateParseHandling]::None
            $token = [Newtonsoft.Json.Linq.JToken]::ReadFrom($jsonReader, $loadSettings)
        }
        finally {
            $jsonReader.Dispose()
            $stringReader.Dispose()
        }
        $record = $Json | ConvertFrom-Json -DateKind String
        if ($IncludeToken) {
            return [pscustomobject]@{
                Record = $record
                Token = $token
            }
        }
        return $record
    }
    catch {
        throw "$RecordName is not strict JSON: $($_.Exception.Message)"
    }
}

function ConvertTo-CanonicalJsonNode {
    param($Value, [string]$Path = '')
    if ($null -eq $Value) {
        return $null
    }
    if ($Value -is [System.Management.Automation.PSCustomObject]) {
        $record = [ordered]@{}
        foreach ($property in @($Value.PSObject.Properties | Sort-Object Name)) {
            if (
                $Path -eq 'approval' -and
                $property.Name -in @(
                    'recorded_at', 'expires_at',
                    'renews_authorization_sha256', 'renewal_scope'
                )
            ) {
                continue
            }
            $childPath = if ([string]::IsNullOrEmpty($Path)) {
                $property.Name
            }
            else {
                "$Path.$($property.Name)"
            }
            $record[$property.Name] = ConvertTo-CanonicalJsonNode -Value $property.Value -Path $childPath
        }
        return [pscustomobject]$record
    }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
        $items = [System.Collections.Generic.List[object]]::new()
        foreach ($item in $Value) {
            [void]$items.Add((ConvertTo-CanonicalJsonNode -Value $item -Path "$Path[]"))
        }
        return ,$items.ToArray()
    }
    return $Value
}

function Get-AuthorizationSemanticSha256 {
    param($Authorization)
    $canonical = ConvertTo-CanonicalJsonNode -Value $Authorization
    $canonicalJson = $canonical | ConvertTo-Json -Compress -Depth 100
    return Get-ByteArraySha256 -Bytes ([System.Text.UTF8Encoding]::new($false).GetBytes($canonicalJson))
}

$ErrorActionPreference = 'Stop'
$clientExecutable = Join-Path $ClientRoot 'Wow.exe'
$runtimeRoot = Join-Path $RepositoryRoot 'data\runtime\operator'
$auditPath = Join-Path $runtimeRoot 'lab-client-operator.jsonl'
$launchReceiptPath = Join-Path $runtimeRoot 'lab-client-launch-receipt.json'
$runtimeArmPath = Join-Path $runtimeRoot 'lab-client-runtime-arm.json'
$identityLockPath = Join-Path $runtimeRoot 'lab-client-identity.lock'
$identityIssuanceRoot = Join-Path $runtimeRoot 'identity-issuances'
$requiredPorts = @(3307, 3443, 3724, 8085)
$authorizationPath = if ([string]::IsNullOrWhiteSpace($AuthorizationFile)) {
    Join-Path $RepositoryRoot 'config\execution-targets\tbc_243_lab.json'
}
else {
    [System.IO.Path]::GetFullPath($AuthorizationFile)
}
$authorizationSchemaPath = Join-Path $RepositoryRoot 'contracts\execution-target-authorization.schema.json'
$launchReceiptSchemaPath = Join-Path $RepositoryRoot 'contracts\lab-client-launch-receipt.schema.json'
$identityIssuanceSchemaPath = Join-Path $RepositoryRoot 'contracts\lab-client-identity-issuance.schema.json'
$runtimeArmSchemaPath = Join-Path $RepositoryRoot 'contracts\lab-client-runtime-arm.schema.json'
$movementRevalidationPath = Join-Path $runtimeRoot 'movement-realm-revalidation.json'
$combatRevalidationPath = Join-Path $runtimeRoot 'combat-realm-revalidation.json'
$preferredWindowProfilePath = Join-Path $RepositoryRoot 'config\movement-lab\client-window-profile.json'
$expectedWindowTitle = 'World of Warcraft'
$expectedWindowClass = 'GxWindowClassD3d'
$expectedAccount = 'ADMIN'
$expectedCharacter = 'Predator'
$inputActions = @(
    'Login', 'InspectAddons', 'EnterWorld', 'AcknowledgeLoginError', 'AcknowledgeDisconnect', 'ReleaseSpirit', 'RetrieveCorpse', 'ToggleEnemyNameplates', 'OpenWorldMap', 'CloseWorldMap', 'DismissGameMenu',
    'SetDnd', 'ClearTarget', 'ToggleVideoRecording', 'ReloadUi',
    'ApplyPredatorUiProfile', 'RestorePredatorUiProfile', 'SnapshotPredatorUiProfile',
    'SetUiScale80', 'SetUiScale100', 'RestoreUiScaleDefault',
    'ResizeWindowCompact', 'ResizeWindowBaseline', 'SaveShadowReplay', 'Logout', 'Close'
)
$expectedFixedUiCapabilities = @(
    'SCREEN_CAPTURE_READ_ONLY',
    'VISIBLE_COORDINATE_HUD_READ_ONLY',
    'LAB_OPERATOR_FIXED_UI'
)
$expectedFixedUiRestrictions = @(
    'bounded_course_only',
    'no_combat_until_pa024f3',
    'no_gathering_or_economy_loops',
    'manual_takeover_required',
    'no_memory_or_kernel_access'
)
$expectedApprovalEvidenceRefs = @(
    'adr:0013',
    'conversation:2026-08-22-executor-scope'
)
$maxObserverAccountLength = 32
$maxObserverPasswordLength = 64
$maxClientTextLength = 128
$maxInputActionSeconds = 30
$script:activeInputLease = $null

if (-not (Test-Path -LiteralPath $authorizationPath -PathType Leaf)) {
    throw "LAB target authorization is missing: $authorizationPath"
}
$authorizationBytes = [System.IO.File]::ReadAllBytes($authorizationPath)
$authorizationSha256 = Get-ByteArraySha256 -Bytes $authorizationBytes
$authorizationJson = [System.Text.UTF8Encoding]::new($false, $true).GetString(
    $authorizationBytes
)
$targetAuthorization = ConvertFrom-StrictJson -Json $authorizationJson -RecordName 'LAB target authorization'
Assert-JsonSchema -Json $authorizationJson -SchemaPath $authorizationSchemaPath -RecordName 'LAB target authorization'
$authorizationSemanticSha256 = Get-AuthorizationSemanticSha256 -Authorization $targetAuthorization
if (
    $targetAuthorization.record_type -ne 'execution_target_authorization' -or
    $targetAuthorization.schema_version -ne '2.0' -or
    $targetAuthorization.target_profile -ne 'tbc_243_lab' -or
    $targetAuthorization.environment_scope -ne 'emulator_local' -or
    $targetAuthorization.status -ne 'approved_bounded' -or
    $targetAuthorization.realm_match.server_kind -ne 'emulator' -or
    $targetAuthorization.actor_binding.schema_version -ne '1.0' -or
    $targetAuthorization.actor_binding.actor_role -ne 'lab_clone' -or
    $targetAuthorization.actor_binding.decision_context -ne 'lab_clone' -or
    $targetAuthorization.actor_binding.expected_character_name -ne $expectedCharacter -or
    $targetAuthorization.actor_binding.credential_alias -ne 'credential:lab:pa_observer' -or
    $targetAuthorization.actor_binding.binding_assurance.state -ne 'configured_expected_only' -or
    @($targetAuthorization.actor_binding.binding_assurance.evidence_refs).Count -lt 1 -or
    [string]::IsNullOrWhiteSpace($targetAuthorization.actor_binding.instance_id) -or
    [string]::IsNullOrWhiteSpace($targetAuthorization.actor_binding.actor_id) -or
    [string]::IsNullOrWhiteSpace($targetAuthorization.actor_binding.memory_namespace) -or
    @($targetAuthorization.permitted_modes).Count -ne 0 -or
    @($targetAuthorization.permitted_capabilities).Count -ne $expectedFixedUiCapabilities.Count -or
    @(Compare-Object -ReferenceObject $expectedFixedUiCapabilities -DifferenceObject @($targetAuthorization.permitted_capabilities)).Count -ne 0 -or
    @($targetAuthorization.restrictions).Count -ne $expectedFixedUiRestrictions.Count -or
    @(Compare-Object -ReferenceObject $expectedFixedUiRestrictions -DifferenceObject @($targetAuthorization.restrictions)).Count -ne 0 -or
    $targetAuthorization.purpose -ne 'education_research_content' -or
    $targetAuthorization.approval.granted_by -ne 'operator' -or
    @($targetAuthorization.approval.evidence_refs).Count -ne $expectedApprovalEvidenceRefs.Count -or
    @(Compare-Object -ReferenceObject $expectedApprovalEvidenceRefs -DifferenceObject @($targetAuthorization.approval.evidence_refs)).Count -ne 0 -or
    -not $targetAuthorization.runtime_arm_required -or
    [string]::IsNullOrWhiteSpace($targetAuthorization.client_match.client_build) -or
    [string]::IsNullOrWhiteSpace($targetAuthorization.client_match.build_signature) -or
    [string]::IsNullOrWhiteSpace($targetAuthorization.realm_match.expected_realm_fingerprint) -or
    $targetAuthorization.realm_match.realmlist_relative_path -ne 'realmlist.wtf' -or
    $targetAuthorization.realm_match.realmlist_directive -ne 'set realmlist 127.0.0.1' -or
    [string]::IsNullOrWhiteSpace($targetAuthorization.realm_match.realmlist_sha256) -or
    $targetAuthorization.realm_match.routing_probe.host -ne '127.0.0.1' -or
    [int]$targetAuthorization.realm_match.routing_probe.port -ne 3307 -or
    $targetAuthorization.realm_match.routing_probe.database -ne 'tbcrealmd' -or
    [string]::IsNullOrWhiteSpace($targetAuthorization.realm_match.routing_probe.database_client_path) -or
    [string]::IsNullOrWhiteSpace($targetAuthorization.realm_match.routing_probe.database_client_sha256) -or
    [string]::IsNullOrWhiteSpace($targetAuthorization.realm_match.routing_probe.secrets_path) -or
    @($targetAuthorization.realm_match.expected_routing_records).Count -lt 1 -or
    [string]::IsNullOrWhiteSpace($targetAuthorization.realm_match.expected_routing_sha256) -or
    $targetAuthorization.approval.max_session_minutes -lt 1 -or
    $targetAuthorization.approval.max_session_minutes -gt 60 -or
    [string]::IsNullOrWhiteSpace($targetAuthorization.client_match.executable_sha256)
) {
    throw 'LAB target authorization is not an approved exact local-emulator identity.'
}
$authorizationTemporalState = 'invalid'
$authorizationTemporalDetail = $null
$approvalRecordedAt = $null
$authorizationExpiresAt = $null
$configuredAuthorizationExpiresAt = $null
$authorizationHasExplicitExpiry = -not [string]::IsNullOrWhiteSpace(
    [string]$targetAuthorization.approval.expires_at
)
try {
    $approvalRecordedAt = [DateTimeOffset]::Parse([string]$targetAuthorization.approval.recorded_at)
    $authorizationNow = [DateTimeOffset]::UtcNow
    if ($approvalRecordedAt -gt $authorizationNow) {
        throw 'approval.recorded_at is in the future.'
    }
    $authorizationBound = $approvalRecordedAt.AddMinutes(
        [int]$targetAuthorization.approval.max_session_minutes
    )
    if (-not $authorizationHasExplicitExpiry) {
        $authorizationExpiresAt = $authorizationBound
    }
    else {
        $configuredAuthorizationExpiresAt = [DateTimeOffset]::Parse(
            [string]$targetAuthorization.approval.expires_at
        )
        if ($configuredAuthorizationExpiresAt -le $approvalRecordedAt) {
            throw 'approval.expires_at is not after approval.recorded_at.'
        }
        if ($configuredAuthorizationExpiresAt -gt $authorizationBound) {
            throw 'approval interval exceeds approval.max_session_minutes.'
        }
        $authorizationExpiresAt = $configuredAuthorizationExpiresAt
    }
    if ($authorizationExpiresAt -le $authorizationNow) {
        $authorizationTemporalState = 'expired'
        $authorizationTemporalDetail = 'effective approval expiry is not in the future.'
    }
    else {
        $authorizationTemporalState = 'active'
    }
}
catch {
    $authorizationTemporalState = 'invalid'
    $authorizationTemporalDetail = $_.Exception.Message
}
$expectedClientSha256 = [string]$targetAuthorization.client_match.executable_sha256
$expectedClientBuild = [string]$targetAuthorization.client_match.client_build
$expectedBuildSignature = "{0}:sha256:{1}" -f $targetAuthorization.client_match.build_signature, $expectedClientSha256
$maxSessionMinutes = [int]$targetAuthorization.approval.max_session_minutes
$expectedRealmFingerprint = [string]$targetAuthorization.realm_match.expected_realm_fingerprint
$instanceId = [string]$targetAuthorization.actor_binding.instance_id
$actorId = [string]$targetAuthorization.actor_binding.actor_id
$actorRole = [string]$targetAuthorization.actor_binding.actor_role
$decisionContext = [string]$targetAuthorization.actor_binding.decision_context
$memoryNamespace = [string]$targetAuthorization.actor_binding.memory_namespace
$actorBindingEvidenceRefs = @($targetAuthorization.actor_binding.binding_assurance.evidence_refs)
$expectedRealmlistRelativePath = [string]$targetAuthorization.realm_match.realmlist_relative_path
$expectedRealmlistSha256 = [string]$targetAuthorization.realm_match.realmlist_sha256
$expectedRealmlistDirective = [string]$targetAuthorization.realm_match.realmlist_directive
$expectedListenerBindings = @($targetAuthorization.realm_match.listener_bindings)
$routingProbe = $targetAuthorization.realm_match.routing_probe
$expectedRoutingRecords = @($targetAuthorization.realm_match.expected_routing_records)
$expectedRoutingSha256 = [string]$targetAuthorization.realm_match.expected_routing_sha256
if (
    $expectedListenerBindings.Count -ne $requiredPorts.Count -or
    @($expectedListenerBindings.port | Sort-Object -Unique).Count -ne $requiredPorts.Count -or
    @(Compare-Object -ReferenceObject ($requiredPorts | Sort-Object) -DifferenceObject ($expectedListenerBindings.port | Sort-Object)).Count -ne 0
) {
    throw 'LAB target authorization does not pin exactly the required listener ports.'
}

if (-not ('PerfectAssassinLabClientNative' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class PerfectAssassinLabClientNative {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    public struct POINT { public int X; public int Y; }
    [StructLayout(LayoutKind.Sequential)]
    public struct FILETIME { public uint LowDateTime; public uint HighDateTime; }
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr handle);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr handle, IntPtr processId);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint first, uint second, bool attach);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr handle);
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr handle, int command);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr handle, out RECT rect);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassNameW(IntPtr handle, System.Text.StringBuilder className, int maxCount);
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr handle, int x, int y, int width, int height, bool repaint);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT point);
    [DllImport("user32.dll", SetLastError = true)] public static extern bool SetProcessDpiAwarenessContext(IntPtr awarenessContext);
    [DllImport("user32.dll", SetLastError = true)] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr awarenessContext);
    [DllImport("user32.dll")] public static extern IntPtr GetThreadDpiAwarenessContext();
    [DllImport("user32.dll")] public static extern bool AreDpiAwarenessContextsEqual(IntPtr first, IntPtr second);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern IntPtr CommandLineToArgvW(string commandLine, out int argumentCount);
    [DllImport("kernel32.dll")] private static extern IntPtr LocalFree(IntPtr memory);
    [DllImport("kernel32.dll", SetLastError = true)] public static extern IntPtr OpenProcess(uint access, bool inheritHandle, int processId);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] public static extern bool QueryFullProcessImageNameW(IntPtr process, uint flags, System.Text.StringBuilder path, ref uint size);
    [DllImport("kernel32.dll", SetLastError = true)] public static extern bool GetProcessTimes(IntPtr process, out FILETIME creation, out FILETIME exit, out FILETIME kernel, out FILETIME user);
    [DllImport("kernel32.dll", SetLastError = true)] public static extern bool ProcessIdToSessionId(uint processId, out uint sessionId);
    [DllImport("kernel32.dll", SetLastError = true)] public static extern bool CloseHandle(IntPtr handle);
    public static string[] ParseCommandLine(string commandLine) {
        int argumentCount;
        IntPtr argumentVector = CommandLineToArgvW(commandLine, out argumentCount);
        if (argumentVector == IntPtr.Zero) {
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        }
        try {
            string[] arguments = new string[argumentCount];
            for (int index = 0; index < argumentCount; index++) {
                IntPtr argument = Marshal.ReadIntPtr(argumentVector, index * IntPtr.Size);
                arguments[index] = Marshal.PtrToStringUni(argument);
            }
            return arguments;
        }
        finally {
            LocalFree(argumentVector);
        }
    }
}
'@
}
$perMonitorAwareV2 = [IntPtr](-4)
if (-not [PerfectAssassinLabClientNative]::SetProcessDpiAwarenessContext([IntPtr](-4))) {
    # PowerShell may have fixed the process default through its manifest before this
    # script starts. Windows explicitly supports overriding that default per thread.
    if ([PerfectAssassinLabClientNative]::SetThreadDpiAwarenessContext($perMonitorAwareV2) -eq [IntPtr]::Zero) {
        throw 'Could not set thread Per-Monitor-Aware V2 before resolving client geometry.'
    }
}
$activeDpiContext = [PerfectAssassinLabClientNative]::GetThreadDpiAwarenessContext()
if (
    $activeDpiContext -eq [IntPtr]::Zero -or
    -not [PerfectAssassinLabClientNative]::AreDpiAwarenessContextsEqual($activeDpiContext, $perMonitorAwareV2)
) {
    throw 'Could not verify Per-Monitor-Aware V2 before resolving client geometry.'
}
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

function Write-OperatorAudit {
    param([string]$Name, [string]$Result, [hashtable]$Details = @{})
    New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
    $entry = [ordered]@{
        occurred_at = [DateTime]::UtcNow.ToString('o')
        actor = 'external_lab_operator_harness'
        action = $Name
        result = $Result
        expected_account = $expectedAccount
        expected_character = $expectedCharacter
        instance_id = $instanceId
        actor_id = $actorId
        actor_role = $actorRole
        decision_context = $decisionContext
        memory_namespace = $memoryNamespace
        predator_execution_mode = 'OBSERVE_ONLY'
        details = $Details
    }
    Add-Content -LiteralPath $auditPath -Value ($entry | ConvertTo-Json -Compress -Depth 5) -Encoding UTF8
}

function Write-OperatorObservationSafely {
    param([string]$Name, [string]$Result, [hashtable]$Details = @{})
    try {
        Write-OperatorAudit -Name $Name -Result $Result -Details $Details
    }
    catch {
        Write-Warning "Observational operator audit could not be appended: $($_.Exception.Message)"
    }
}

function Get-LabListenerStatus {
    $listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue
    foreach ($port in $requiredPorts) {
        $matches = @($listeners | Where-Object { $_.LocalPort -eq $port })
        $loopbackOnly = $matches.Count -gt 0 -and @(
            $matches | Where-Object { $_.LocalAddress -notin @('127.0.0.1', '::1') }
        ).Count -eq 0
        [pscustomobject]@{
            port = $port
            listening = $matches.Count -gt 0
            loopback_only = $loopbackOnly
        }
    }
}

function Assert-LabReady {
    [void](Assert-ExactLabRealm)
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue)
    foreach ($binding in $expectedListenerBindings) {
        $port = [int]$binding.port
        $matches = @($listeners | Where-Object { $_.LocalPort -eq $port })
        if (
            $matches.Count -eq 0 -or
            @($matches | Where-Object { $_.LocalAddress -notin @('127.0.0.1', '::1') }).Count -gt 0
        ) {
            throw "LAB listener $port is missing or is not loopback-only."
        }
        $ownerPids = @($matches.OwningProcess | Sort-Object -Unique)
        if ($ownerPids.Count -ne 1) {
            throw "LAB listener $port does not have one exact owning process."
        }
        $owner = Get-Process -Id $ownerPids[0] -ErrorAction Stop
        if ($owner.ProcessName -ne [string]$binding.process_name) {
            throw "LAB listener $port process name does not match authorization."
        }
        try {
            $ownerInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($owner.Id)"
        }
        catch {
            $ownerInfo = $null
        }
        try {
            $ownerPath = [string]$owner.MainModule.FileName
        }
        catch {
            $ownerPath = $null
        }
        if ([string]::IsNullOrWhiteSpace($ownerPath)) {
            $ownerPath = [string]$ownerInfo.ExecutablePath
        }
        if ([string]::IsNullOrWhiteSpace($ownerPath)) {
            throw "LAB listener $port owner image cannot be verified."
        }
        $actualOwnerPath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $ownerPath).Path)
        $expectedOwnerPath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath ([string]$binding.executable_path)).Path)
        if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals($actualOwnerPath, $expectedOwnerPath)) {
            throw "LAB listener $port owner path does not match authorization."
        }
        $ownerHash = (Get-FileHash -LiteralPath $actualOwnerPath -Algorithm SHA256).Hash
        if ($ownerHash -ne [string]$binding.executable_sha256) {
            throw "LAB listener $port owner hash does not match authorization."
        }
        if ($null -eq $ownerInfo -or [string]::IsNullOrWhiteSpace([string]$ownerInfo.CommandLine)) {
            throw "LAB listener $port owner command line cannot be verified."
        }
        $parsedCommandLine = @(
            [PerfectAssassinLabClientNative]::ParseCommandLine([string]$ownerInfo.CommandLine)
        )
        $expectedArguments = @($binding.command_line_arguments)
        if ($parsedCommandLine.Count -ne ($expectedArguments.Count + 1)) {
            throw "LAB listener $port owner arguments do not match authorization."
        }
        $commandExecutable = [System.IO.Path]::GetFullPath($parsedCommandLine[0])
        if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals($commandExecutable, $actualOwnerPath)) {
            throw "LAB listener $port command executable differs from its running image."
        }
        for ($index = 0; $index -lt $expectedArguments.Count; $index++) {
            if (-not [System.StringComparer]::Ordinal.Equals(
                [string]$parsedCommandLine[$index + 1],
                [string]$expectedArguments[$index]
            )) {
                throw "LAB listener $port owner arguments do not match authorization."
            }
        }
        $expectedConfigPath = [System.IO.Path]::GetFullPath(
            (Resolve-Path -LiteralPath ([string]$binding.config_path)).Path
        )
        $configReferenced = $false
        foreach ($argument in $parsedCommandLine[1..($parsedCommandLine.Count - 1)]) {
            if (
                [System.StringComparer]::OrdinalIgnoreCase.Equals([string]$argument, $expectedConfigPath) -or
                [System.StringComparer]::OrdinalIgnoreCase.Equals([string]$argument, "--defaults-file=$expectedConfigPath")
            ) {
                $configReferenced = $true
            }
        }
        if (-not $configReferenced) {
            throw "LAB listener $port command line does not reference its pinned config file."
        }
        $configHash = (Get-FileHash -LiteralPath $expectedConfigPath -Algorithm SHA256).Hash
        if ($configHash -ne [string]$binding.config_sha256) {
            throw "LAB listener $port config hash does not match authorization."
        }
    }
    [void](Assert-ExactRealmRoutingRecord)
}

function Assert-LocalInteractiveSession {
    if ([System.Windows.Forms.SystemInformation]::TerminalServerSession) {
        throw 'The legacy TBC 2.4.3 client refuses Remote Desktop sessions. Disconnect RDP and run the client from the local console session.'
    }
}

function Assert-ClientExecutableIdentity {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Client executable is missing: $Path"
    }
    $expectedPath = [System.IO.Path]::GetFullPath(
        (Resolve-Path -LiteralPath $clientExecutable).Path
    )
    $actualPath = [System.IO.Path]::GetFullPath(
        (Resolve-Path -LiteralPath $Path).Path
    )
    if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals($actualPath, $expectedPath)) {
        throw 'Running WoW process path does not match the configured LAB client.'
    }
    $actualHash = (Get-FileHash -LiteralPath $actualPath -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedClientSha256) {
        throw 'WoW executable SHA-256 does not match the LAB target authorization.'
    }
    return $actualPath
}

function Assert-ExactLabRealm {
    if (-not (Test-Path -LiteralPath $ClientRoot -PathType Container)) {
        throw 'Configured LAB client root is missing.'
    }
    $canonicalClientRoot = [System.IO.Path]::GetFullPath(
        (Resolve-Path -LiteralPath $ClientRoot).Path
    )
    $configuredRealmlistPath = Join-Path $canonicalClientRoot $expectedRealmlistRelativePath
    if (-not (Test-Path -LiteralPath $configuredRealmlistPath -PathType Leaf)) {
        throw 'The exact LAB realmlist file is missing.'
    }
    $canonicalRealmlistPath = [System.IO.Path]::GetFullPath(
        (Resolve-Path -LiteralPath $configuredRealmlistPath).Path
    )
    $requiredRealmlistPath = [System.IO.Path]::GetFullPath(
        (Join-Path $canonicalClientRoot 'realmlist.wtf')
    )
    if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals($canonicalRealmlistPath, $requiredRealmlistPath)) {
        throw 'LAB realmlist path escapes or differs from the exact client-root binding.'
    }
    $actualBytes = [System.IO.File]::ReadAllBytes($canonicalRealmlistPath)
    $canonicalBytes = [System.Text.UTF8Encoding]::new($false).GetBytes($expectedRealmlistDirective)
    if (
        $actualBytes.Length -ne $canonicalBytes.Length -or
        [Convert]::ToBase64String($actualBytes) -ne [Convert]::ToBase64String($canonicalBytes)
    ) {
        throw 'LAB realmlist must contain only the canonical 127.0.0.1 directive.'
    }
    $actualHash = (Get-FileHash -LiteralPath $canonicalRealmlistPath -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedRealmlistSha256) {
        throw 'LAB realmlist SHA-256 does not match the exact target authorization.'
    }
    return [pscustomobject]@{
        RelativePath = $expectedRealmlistRelativePath
        Sha256 = $actualHash
        Directive = $expectedRealmlistDirective
    }
}

function Get-Utf8Sha256 {
    param([string]$Value)
    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Value)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha256.ComputeHash($bytes))).Replace('-', '')
    }
    finally {
        $sha256.Dispose()
    }
}

function ConvertTo-RealmRoutingCanonicalText {
    param([object[]]$Records)
    $rows = @()
    foreach ($record in @($Records | Sort-Object { [int]$_.realm_id })) {
        $clientBuilds = @($record.client_builds)
        if ($clientBuilds.Count -lt 1) {
            throw 'Realm routing record has no client build.'
        }
        $stringFields = @([string]$record.name, [string]$record.address) + @($clientBuilds | ForEach-Object { [string]$_ })
        if (@($stringFields | Where-Object { $_ -match '[\x00-\x1F\x7F]' }).Count -gt 0) {
            throw 'Realm routing record contains unsupported control characters.'
        }
        $fields = @(
            ([int]$record.realm_id).ToString([Globalization.CultureInfo]::InvariantCulture),
            [string]$record.name,
            [string]$record.address,
            ([int]$record.port).ToString([Globalization.CultureInfo]::InvariantCulture),
            ([int]$record.icon).ToString([Globalization.CultureInfo]::InvariantCulture),
            ([int]$record.realm_flags).ToString([Globalization.CultureInfo]::InvariantCulture),
            ([int]$record.timezone).ToString([Globalization.CultureInfo]::InvariantCulture),
            ([int]$record.allowed_security_level).ToString([Globalization.CultureInfo]::InvariantCulture),
            [string]::Join(',', $clientBuilds)
        )
        $rows += [string]::Join("`t", $fields)
    }
    return [string]::Join("`n", $rows)
}

function Assert-ExactRealmRoutingRecord {
    $expectedCanonical = ConvertTo-RealmRoutingCanonicalText -Records $expectedRoutingRecords
    $configuredCanonicalSha256 = Get-Utf8Sha256 -Value $expectedCanonical
    if ($configuredCanonicalSha256 -ne $expectedRoutingSha256) {
        throw 'Authorized realm routing records do not match their canonical SHA-256.'
    }

    foreach ($path in @([string]$routingProbe.database_client_path, [string]$routingProbe.secrets_path)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw 'Exact LAB realm routing probe dependency is missing.'
        }
    }
    $databaseClientPath = [System.IO.Path]::GetFullPath(
        (Resolve-Path -LiteralPath ([string]$routingProbe.database_client_path)).Path
    )
    $databaseClientSha256 = (Get-FileHash -LiteralPath $databaseClientPath -Algorithm SHA256).Hash
    if ($databaseClientSha256 -ne [string]$routingProbe.database_client_sha256) {
        throw 'LAB realm routing database client SHA-256 does not match authorization.'
    }
    $secretsPath = [System.IO.Path]::GetFullPath(
        (Resolve-Path -LiteralPath ([string]$routingProbe.secrets_path)).Path
    )
    $secretsJson = Get-Content -LiteralPath $secretsPath -Raw
    $secrets = ConvertFrom-StrictJson -Json $secretsJson -RecordName 'LAB routing secrets'
    $databaseHost = [string]$secrets.host
    $databasePort = [int]$secrets.port
    $databaseUser = [string]$secrets.mangos_user
    $databasePassword = [string]$secrets.mangos_password
    if (
        $databaseHost -ne [string]$routingProbe.host -or
        $databasePort -ne [int]$routingProbe.port -or
        $databaseUser -notmatch '^[A-Za-z0-9_]{1,64}$' -or
        [string]::IsNullOrWhiteSpace($databasePassword) -or
        $databasePassword.Length -gt 512 -or
        $databasePassword -match '[\x00-\x1F\x7F]'
    ) {
        throw 'LAB realm routing database credential metadata does not match the authorized local probe.'
    }

    $query = 'SELECT id, name, address, port, icon, realmflags, timezone, allowedSecurityLevel, TRIM(realmbuilds) FROM realmlist ORDER BY id;'
    $databaseArguments = @(
        "--host=$databaseHost",
        "--port=$databasePort",
        "--user=$databaseUser",
        '--protocol=TCP',
        '--connect-timeout=3',
        '--batch',
        '--skip-column-names',
        '--raw',
        '--silent',
        "--database=$([string]$routingProbe.database)",
        "--execute=$query"
    )
    $previousDatabasePassword = [Environment]::GetEnvironmentVariable('MYSQL_PWD', 'Process')
    try {
        $env:MYSQL_PWD = $databasePassword
        $rawRows = @(& $databaseClientPath @databaseArguments 2>$null)
        $databaseExitCode = $LASTEXITCODE
    }
    finally {
        if ($null -eq $previousDatabasePassword) {
            Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
        }
        else {
            $env:MYSQL_PWD = $previousDatabasePassword
        }
        $databasePassword = $null
        $secrets = $null
    }
    if ($databaseExitCode -ne 0) {
        throw 'Exact LAB realm routing query failed.'
    }
    $rawRows = @($rawRows | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
    if ($rawRows.Count -ne $expectedRoutingRecords.Count) {
        throw 'LAB realm routing record count differs from authorization.'
    }
    $actualRecords = @()
    foreach ($rawRow in $rawRows) {
        $fields = ([string]$rawRow).Split([char]9)
        if ($fields.Count -ne 9) {
            throw 'LAB realm routing query returned a malformed sanitized record.'
        }
        $clientBuilds = @($fields[8].Trim() -split '\s+' | Where-Object { $_ -match '^[0-9]+$' })
        if ($clientBuilds.Count -lt 1) {
            throw 'LAB realm routing query returned no valid client build.'
        }
        $actualRecords += [pscustomobject]@{
            realm_id = [int]$fields[0]
            name = [string]$fields[1]
            address = [string]$fields[2]
            port = [int]$fields[3]
            icon = [int]$fields[4]
            realm_flags = [int]$fields[5]
            timezone = [int]$fields[6]
            allowed_security_level = [int]$fields[7]
            client_builds = $clientBuilds
        }
    }
    $actualCanonical = ConvertTo-RealmRoutingCanonicalText -Records $actualRecords
    $actualRoutingSha256 = Get-Utf8Sha256 -Value $actualCanonical
    if (
        -not [System.StringComparer]::Ordinal.Equals($actualCanonical, $expectedCanonical) -or
        $actualRoutingSha256 -ne $expectedRoutingSha256
    ) {
        throw 'LAB realm routing record differs from the exact authorized endpoint.'
    }
    return [pscustomobject]@{
        Sha256 = $actualRoutingSha256
        RecordCount = $actualRecords.Count
    }
}

function Write-DurableUtf8Text {
    param([string]$Path, [string]$Text, [System.IO.FileMode]$Mode)
    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Text)
    $stream = [System.IO.FileStream]::new(
        $Path,
        $Mode,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::None,
        4096,
        [System.IO.FileOptions]::WriteThrough
    )
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    }
    finally {
        $stream.Dispose()
    }
}

function Write-AtomicJsonRecord {
    param([string]$Path, [string]$Json, [string]$Nonce)
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    $temporaryPath = "$Path.$Nonce.tmp"
    try {
        Write-DurableUtf8Text -Path $temporaryPath -Text $Json -Mode ([System.IO.FileMode]::CreateNew)
        [System.IO.File]::Move($temporaryPath, $Path, $true)
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Write-AtomicImmutableJsonRecord {
    param([string]$Path, [string]$Json, [string]$Nonce)
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    $expectedBytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Json)
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $existingBytes = [System.IO.File]::ReadAllBytes($Path)
        if (
            $existingBytes.Length -eq $expectedBytes.Length -and
            [Convert]::ToBase64String($existingBytes) -eq [Convert]::ToBase64String($expectedBytes)
        ) {
            return
        }
        throw 'Immutable LAB identity issuance marker already exists with different bytes.'
    }
    $temporaryPath = "$Path.$Nonce.tmp"
    try {
        Write-DurableUtf8Text -Path $temporaryPath -Text $Json -Mode ([System.IO.FileMode]::CreateNew)
        try {
            [System.IO.File]::Move($temporaryPath, $Path)
        }
        catch [System.IO.IOException] {
            if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
                throw
            }
            $existingBytes = [System.IO.File]::ReadAllBytes($Path)
            if (
                $existingBytes.Length -ne $expectedBytes.Length -or
                [Convert]::ToBase64String($existingBytes) -ne [Convert]::ToBase64String($expectedBytes)
            ) {
                throw 'Immutable LAB identity issuance marker collision was detected.'
            }
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Get-ClientWindowClass {
    param([IntPtr]$Handle)
    $builder = [System.Text.StringBuilder]::new(256)
    if ([PerfectAssassinLabClientNative]::GetClassNameW($Handle, $builder, $builder.Capacity) -le 0) {
        throw 'Could not resolve the World of Warcraft window class.'
    }
    return $builder.ToString()
}

function Assert-ExactClientWindowBinding {
    param(
        [System.Diagnostics.Process]$Process,
        [Nullable[long]]$ExpectedHwnd
    )
    $Process.Refresh()
    if ($Process.HasExited -or $Process.MainWindowHandle -eq [IntPtr]::Zero) {
        throw 'The receipt-bound World of Warcraft process has no live window.'
    }
    $actualHwnd = $Process.MainWindowHandle.ToInt64()
    if ($null -ne $ExpectedHwnd -and $actualHwnd -ne [long]$ExpectedHwnd) {
        throw 'World of Warcraft HWND does not match the launch receipt.'
    }
    if ($Process.MainWindowTitle -ne $expectedWindowTitle) {
        throw 'Unexpected client window title; identity is refused.'
    }
    $actualClass = Get-ClientWindowClass -Handle $Process.MainWindowHandle
    if ($actualClass -ne $expectedWindowClass) {
        throw 'Unexpected client window class; identity is refused.'
    }
    return [pscustomobject]@{
        Hwnd = $actualHwnd
        HwndHex = '0x{0:X}' -f $actualHwnd
        Title = $Process.MainWindowTitle
        Class = $actualClass
    }
}

function Get-BoundedExpiry {
    param([DateTimeOffset]$IssuedAt, [Nullable[DateTimeOffset]]$AdditionalLimit)
    $expiresAt = $IssuedAt.AddMinutes($maxSessionMinutes)
    if ($authorizationExpiresAt -lt $expiresAt) {
        $expiresAt = $authorizationExpiresAt
    }
    if ($null -ne $AdditionalLimit) {
        $additionalExpiry = [DateTimeOffset]$AdditionalLimit
        if ($additionalExpiry -lt $expiresAt) {
            $expiresAt = $additionalExpiry
        }
    }
    if ($expiresAt -le $IssuedAt) {
        throw 'The bounded authorization has no remaining session time.'
    }
    return $expiresAt
}

function Assert-ActiveTargetAuthorization {
    if ($authorizationTemporalState -ne 'active') {
        $detail = if ([string]::IsNullOrWhiteSpace($authorizationTemporalDetail)) {
            $authorizationTemporalState
        }
        else {
            $authorizationTemporalDetail
        }
        throw "LAB target authorization has no active bounded approval window: $detail"
    }
    $now = [DateTimeOffset]::UtcNow
    if (
        $null -eq $approvalRecordedAt -or
        $null -eq $authorizationExpiresAt -or
        $approvalRecordedAt -gt $now -or
        $authorizationExpiresAt -le $now -or
        $authorizationExpiresAt -gt $approvalRecordedAt.AddMinutes($maxSessionMinutes)
    ) {
        throw 'LAB target authorization active-window recheck failed.'
    }
}

function Read-ActiveMovementAuthorization {
    if (-not $AcknowledgeSinglePulse -and -not $AcknowledgeContinuousMotion) {
        throw 'Movement realm revalidation requires -AcknowledgeSinglePulse or -AcknowledgeContinuousMotion.'
    }
    if ($AcknowledgeSinglePulse -and $AcknowledgeContinuousMotion) {
        throw 'Movement realm revalidation accepts exactly one movement acknowledgement.'
    }
    if ([string]::IsNullOrWhiteSpace($MovementAuthorizationFile)) {
        throw 'Movement realm revalidation requires -MovementAuthorizationFile.'
    }
    $movementPath = [System.IO.Path]::GetFullPath($MovementAuthorizationFile)
    if (-not (Test-Path -LiteralPath $movementPath -PathType Leaf)) {
        throw 'Movement authorization snapshot is missing.'
    }
    $movementBytes = [System.IO.File]::ReadAllBytes($movementPath)
    if ($movementBytes.Length -lt 2 -or $movementBytes.Length -gt 2097152) {
        throw 'Movement authorization snapshot size is outside its bound.'
    }
    $movementSha256 = Get-ByteArraySha256 -Bytes $movementBytes
    $movementJson = [System.Text.UTF8Encoding]::new($false, $true).GetString($movementBytes)
    $movement = ConvertFrom-StrictJson -Json $movementJson -RecordName 'Movement authorization'
    Assert-JsonSchema -Json $movementJson -SchemaPath $authorizationSchemaPath -RecordName 'Movement authorization'

    $isContinuous = [bool]$AcknowledgeContinuousMotion
    $expectedAuthorizationId = if ($isContinuous) {
        'execution:tbc243-lab:movement-f4a-continuous-navmesh'
    } else {
        'execution:tbc243-lab:movement-f3a-single-pulse'
    }
    $expectedControls = if ($isContinuous) {
        @('MOVE_FORWARD', 'MOVE_BACKWARD', 'STRAFE_LEFT', 'STRAFE_RIGHT')
    } else {
        @('MOVE_FORWARD')
    }
    $expectedMaxHold = if ($isContinuous) { 450 } else { 100 }
    $expectedMaxEnvelope = if ($isContinuous) { 500 } else { 150 }
    $expectedMaxPrimitives = if ($isContinuous) { 4096 } else { 1 }
    $expectedMaxMinutes = if ($isContinuous) { 10 } else { 1 }
    $expectedAcknowledgement = if ($isContinuous) {
        'operator_ack:pa024f4a:continuous_navmesh'
    } else {
        'operator_ack:pa024f3a:single_forward_pulse'
    }
    $expectedCapabilities = @(
        'SCREEN_CAPTURE_READ_ONLY',
        'VISIBLE_COORDINATE_HUD_READ_ONLY',
        'MOVEMENT_EXECUTION'
    )
    $recordedAt = [DateTimeOffset]::Parse([string]$movement.approval.recorded_at)
    $expiresAt = [DateTimeOffset]::Parse([string]$movement.approval.expires_at)
    $now = [DateTimeOffset]::UtcNow
    $actorIdentityFields = @(
        'schema_version',
        'instance_id',
        'actor_role',
        'actor_id',
        'decision_context',
        'memory_namespace',
        'expected_character_name',
        'credential_alias'
    )
    $actorIdentityMismatch = $false
    foreach ($field in $actorIdentityFields) {
        if ([string]$movement.actor_binding.$field -ne [string]$targetAuthorization.actor_binding.$field) {
            $actorIdentityMismatch = $true
            break
        }
    }
    if (
        [string]$movement.actor_binding.binding_assurance.state -ne
        [string]$targetAuthorization.actor_binding.binding_assurance.state
    ) {
        $actorIdentityMismatch = $true
    }
    if (
        $movement.record_type -ne 'execution_target_authorization' -or
        $movement.schema_version -ne '2.0' -or
        $movement.authorization_id -ne $expectedAuthorizationId -or
        $movement.target_profile -ne $targetAuthorization.target_profile -or
        $movement.environment_scope -ne 'emulator_local' -or
        $movement.status -ne 'approved_bounded' -or
        @($movement.permitted_modes).Count -ne 1 -or
        $movement.permitted_modes[0] -ne 'MOVEMENT_ONLY' -or
        @($movement.permitted_capabilities).Count -ne $expectedCapabilities.Count -or
        @(Compare-Object -ReferenceObject $expectedCapabilities -DifferenceObject @($movement.permitted_capabilities)).Count -ne 0 -or
        @($movement.movement_policy.allowed_controls).Count -ne $expectedControls.Count -or
        @(Compare-Object -ReferenceObject $expectedControls -DifferenceObject @($movement.movement_policy.allowed_controls)).Count -ne 0 -or
        [int]$movement.movement_policy.max_hold_duration_ms -ne $expectedMaxHold -or
        [int]$movement.movement_policy.max_execution_envelope_ms -ne $expectedMaxEnvelope -or
        [int]$movement.movement_policy.max_primitives -ne $expectedMaxPrimitives -or
        $movement.movement_policy.manual_takeover_required -ne $true -or
        $movement.movement_policy.release_all_required -ne $true -or
        $movement.movement_policy.combat_authorized -ne $false -or
        $movement.movement_policy.economy_authorized -ne $false -or
        $expectedAcknowledgement -notin @($movement.approval.evidence_refs) -or
        [int]$movement.approval.max_session_minutes -ne $expectedMaxMinutes -or
        $recordedAt -gt $now -or
        $expiresAt -le $now -or
        $expiresAt -gt $recordedAt.AddMinutes($expectedMaxMinutes) -or
        $actorIdentityMismatch -or
        $movement.client_match.client_build -ne $targetAuthorization.client_match.client_build -or
        $movement.client_match.build_signature -ne $targetAuthorization.client_match.build_signature -or
        $movement.client_match.executable_path -ne $targetAuthorization.client_match.executable_path -or
        $movement.client_match.executable_sha256 -ne $targetAuthorization.client_match.executable_sha256 -or
        $movement.realm_match.server_kind -ne 'emulator' -or
        $movement.realm_match.expected_realm_fingerprint -ne $targetAuthorization.realm_match.expected_realm_fingerprint -or
        $movement.realm_match.expected_routing_sha256 -ne $targetAuthorization.realm_match.expected_routing_sha256 -or
        $movement.realm_match.realmlist_relative_path -ne $targetAuthorization.realm_match.realmlist_relative_path -or
        $movement.realm_match.realmlist_sha256 -ne $targetAuthorization.realm_match.realmlist_sha256 -or
        $movement.realm_match.realmlist_directive -ne $targetAuthorization.realm_match.realmlist_directive
    ) {
        throw "Movement authorization is not the exact active $(if ($isContinuous) { 'F4a continuous-navmesh' } else { 'F3a single-pulse' }) profile."
    }
    return [pscustomobject]@{
        Record = $movement
        Sha256 = $movementSha256
        ExpiresAt = $expiresAt
    }
}

function Read-ActiveCombatAuthorization {
    if (-not $AcknowledgeControlledCombat) {
        throw 'Combat realm revalidation requires -AcknowledgeControlledCombat.'
    }
    if ([string]::IsNullOrWhiteSpace($CombatAuthorizationFile)) {
        throw 'Combat realm revalidation requires -CombatAuthorizationFile.'
    }
    $combatPath = [System.IO.Path]::GetFullPath($CombatAuthorizationFile)
    if (-not (Test-Path -LiteralPath $combatPath -PathType Leaf)) {
        throw 'Combat authorization snapshot is missing.'
    }
    $combatBytes = [System.IO.File]::ReadAllBytes($combatPath)
    if ($combatBytes.Length -lt 2 -or $combatBytes.Length -gt 2097152) {
        throw 'Combat authorization snapshot size is outside its bound.'
    }
    $combatSha256 = Get-ByteArraySha256 -Bytes $combatBytes
    $combatJson = [System.Text.UTF8Encoding]::new($false, $true).GetString($combatBytes)
    $combat = ConvertFrom-StrictJson -Json $combatJson -RecordName 'Combat authorization'
    Assert-JsonSchema -Json $combatJson -SchemaPath $authorizationSchemaPath -RecordName 'Combat authorization'

    $expectedCapabilities = @(
        'SCREEN_CAPTURE_READ_ONLY',
        'VISIBLE_COMBAT_HUD_READ_ONLY',
        'COMBAT_EXECUTION'
    )
    $expectedControls = @(
        'TARGET_VISIBLE_HOSTILE',
        'TARGET_NEAREST_HOSTILE',
        'TARGET_EXACT_NAME',
        'TARGET_LAST_HOSTILE',
        'INTERACT_TARGET',
        'ACTION_SLOT_1',
        'ACTION_SLOT_2',
        'ACTION_SLOT_3',
        'MOVE_FORWARD',
        'STRAFE_LEFT',
        'STRAFE_RIGHT',
        'TURN_LEFT',
        'TURN_RIGHT'
    )
    $recordedAt = [DateTimeOffset]::Parse([string]$combat.approval.recorded_at)
    $expiresAt = [DateTimeOffset]::Parse([string]$combat.approval.expires_at)
    $now = [DateTimeOffset]::UtcNow
    $actorIdentityFields = @(
        'schema_version', 'instance_id', 'actor_role', 'actor_id',
        'decision_context', 'memory_namespace', 'expected_character_name',
        'credential_alias'
    )
    $actorIdentityMismatch = $false
    foreach ($field in $actorIdentityFields) {
        if ([string]$combat.actor_binding.$field -ne [string]$targetAuthorization.actor_binding.$field) {
            $actorIdentityMismatch = $true
            break
        }
    }
    if (
        [string]$combat.actor_binding.binding_assurance.state -ne
        [string]$targetAuthorization.actor_binding.binding_assurance.state
    ) {
        $actorIdentityMismatch = $true
    }
    if (
        $combat.record_type -ne 'execution_target_authorization' -or
        $combat.schema_version -ne '2.0' -or
        $combat.authorization_id -ne 'execution:tbc243-lab:combat-f4a-bounded' -or
        $combat.target_profile -ne $targetAuthorization.target_profile -or
        $combat.environment_scope -ne 'emulator_local' -or
        $combat.status -ne 'approved_bounded' -or
        @($combat.permitted_modes).Count -ne 1 -or
        $combat.permitted_modes[0] -ne 'COMBAT_ONLY' -or
        @($combat.permitted_capabilities).Count -ne $expectedCapabilities.Count -or
        @(Compare-Object -ReferenceObject $expectedCapabilities -DifferenceObject @($combat.permitted_capabilities)).Count -ne 0 -or
        @($combat.combat_policy.allowed_controls).Count -ne $expectedControls.Count -or
        @(Compare-Object -ReferenceObject $expectedControls -DifferenceObject @($combat.combat_policy.allowed_controls)).Count -ne 0 -or
        [int]$combat.combat_policy.max_actions -ne 64 -or
        [int]$combat.combat_policy.max_encounter_seconds -ne 90 -or
        [int]$combat.combat_policy.max_acquisition_seconds -ne 25 -or
        [int]$combat.combat_policy.max_combat_seconds -ne 60 -or
        [int]$combat.combat_policy.max_recovery_seconds -ne 5 -or
        [int]$combat.combat_policy.max_approach_pulses -ne 10 -or
        [int]$combat.combat_policy.approach_hold_duration_ms -ne 250 -or
        [int]$combat.combat_policy.orbit_hold_duration_ms -ne 90 -or
        [int]$combat.combat_policy.max_turn_pulses -ne 12 -or
        [int]$combat.combat_policy.max_facing_turn_pulses -ne 24 -or
        [int]$combat.combat_policy.search_turn_hold_duration_ms -ne 200 -or
        [int]$combat.combat_policy.search_turn_mouse_delta_x -ne 24 -or
        [int]$combat.combat_policy.turn_near_hold_duration_ms -ne 25 -or
        [int]$combat.combat_policy.turn_near_mouse_delta_x -ne 4 -or
        [int]$combat.combat_policy.turn_medium_hold_duration_ms -ne 35 -or
        [int]$combat.combat_policy.turn_medium_mouse_delta_x -ne 14 -or
        [int]$combat.combat_policy.turn_far_hold_duration_ms -ne 50 -or
        [int]$combat.combat_policy.turn_far_mouse_delta_x -ne 28 -or
        [double]$combat.combat_policy.turn_medium_offset_threshold -ne 0.25 -or
        [double]$combat.combat_policy.turn_far_offset_threshold -ne 0.60 -or
        [int]$combat.combat_policy.turn_execution_slack_ms -ne 150 -or
        [int]$combat.combat_policy.action_key_hold_ms -ne 25 -or
        [int]$combat.combat_policy.max_target_level_delta -ne 1 -or
        [int]$combat.combat_policy.retreat_health_pct -ne 25 -or
        $combat.combat_policy.manual_takeover_required -ne $true -or
        $combat.combat_policy.release_all_required -ne $true -or
        $combat.combat_policy.player_targets_authorized -ne $false -or
        $combat.combat_policy.economy_authorized -ne $false -or
        'operator_ack:pa024f4a:controlled_lab_combat' -notin @($combat.approval.evidence_refs) -or
        [int]$combat.approval.max_session_minutes -ne 2 -or
        $recordedAt -gt $now -or
        $expiresAt -le $now -or
        $expiresAt -gt $recordedAt.AddMinutes(2) -or
        $actorIdentityMismatch -or
        $combat.client_match.client_build -ne $targetAuthorization.client_match.client_build -or
        $combat.client_match.build_signature -ne $targetAuthorization.client_match.build_signature -or
        $combat.client_match.executable_sha256 -ne $targetAuthorization.client_match.executable_sha256 -or
        $combat.realm_match.server_kind -ne 'emulator' -or
        $combat.realm_match.expected_realm_fingerprint -ne $targetAuthorization.realm_match.expected_realm_fingerprint -or
        $combat.realm_match.expected_routing_sha256 -ne $targetAuthorization.realm_match.expected_routing_sha256 -or
        $combat.realm_match.realmlist_relative_path -ne $targetAuthorization.realm_match.realmlist_relative_path -or
        $combat.realm_match.realmlist_sha256 -ne $targetAuthorization.realm_match.realmlist_sha256 -or
        $combat.realm_match.realmlist_directive -ne $targetAuthorization.realm_match.realmlist_directive
    ) {
        throw 'Combat authorization is not the exact active F4a controlled-LAB profile.'
    }
    return [pscustomobject]@{
        Record = $combat
        Sha256 = $combatSha256
        ExpiresAt = $expiresAt
    }
}

function ConvertFrom-HexHwnd {
    param([string]$Value)
    if ($Value -notmatch '^0x[A-F0-9]+$') {
        throw 'Receipt HWND is not canonical hexadecimal.'
    }
    return [Convert]::ToInt64($Value.Substring(2), 16)
}

function Get-SingleWowProcess {
    param([switch]$AllowNone)
    $processes = @(Get-Process -Name Wow -ErrorAction SilentlyContinue)
    if ($processes.Count -gt 1) {
        throw 'More than one Wow.exe process is running; exact session identity is ambiguous.'
    }
    if ($processes.Count -eq 0) {
        if ($AllowNone) {
            return $null
        }
        throw 'No Wow.exe process is running.'
    }
    return $processes[0]
}

function Get-ExactClientProcessMetadata {
    param([System.Diagnostics.Process]$Process)
    # Metadata-only query rights: image identity, creation time and session.
    # No VM read/write/operation right is requested or permitted here.
    $processHandle = [PerfectAssassinLabClientNative]::OpenProcess(0x00101000, $false, $Process.Id)
    if ($processHandle -eq [IntPtr]::Zero) {
        $limitedQueryError = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
        if ($limitedQueryError -ne 5) {
            throw "Could not open the running client for read-only identity metadata (Win32 $limitedQueryError)."
        }
        # Some legacy clients deny QUERY_LIMITED_INFORMATION but allow the older
        # metadata-only QUERY_INFORMATION + SYNCHRONIZE combination.
        $processHandle = [PerfectAssassinLabClientNative]::OpenProcess(0x00100400, $false, $Process.Id)
    }
    if ($processHandle -eq [IntPtr]::Zero) {
        throw 'Could not open the running client for read-only identity metadata.'
    }
    try {
        $pathBuilder = [System.Text.StringBuilder]::new(32768)
        [uint32]$pathLength = $pathBuilder.Capacity
        if (-not [PerfectAssassinLabClientNative]::QueryFullProcessImageNameW(
            $processHandle, 0, $pathBuilder, [ref]$pathLength
        )) {
            throw 'Could not resolve the running client image path.'
        }
        $creation = [PerfectAssassinLabClientNative+FILETIME]::new()
        $exit = [PerfectAssassinLabClientNative+FILETIME]::new()
        $kernel = [PerfectAssassinLabClientNative+FILETIME]::new()
        $user = [PerfectAssassinLabClientNative+FILETIME]::new()
        if (-not [PerfectAssassinLabClientNative]::GetProcessTimes(
            $processHandle, [ref]$creation, [ref]$exit, [ref]$kernel, [ref]$user
        )) {
            throw 'Could not resolve the running client creation time.'
        }
        [uint32]$sessionId = 0
        $nativeSessionResolved = [PerfectAssassinLabClientNative]::ProcessIdToSessionId(
            [uint32]$Process.Id, [ref]$sessionId
        )
        $Process.Refresh()
        $managedSessionId = [int]$Process.SessionId
        if ($managedSessionId -lt 0) {
            throw 'Could not resolve the running client Windows session.'
        }
        if ($nativeSessionResolved -and [int]$sessionId -ne $managedSessionId) {
            throw 'Native and managed Windows session identity disagree.'
        }
        $sessionId = [uint32]$managedSessionId
        [int64]$creationFileTime = (([int64]$creation.HighDateTime -shl 32) -bor [int64]$creation.LowDateTime)
        $creationUtc = [DateTime]::FromFileTimeUtc($creationFileTime)
        $canonicalPath = Assert-ClientExecutableIdentity -Path ($pathBuilder.ToString())
        return [pscustomobject]@{
            ExecutablePath = $canonicalPath
            ProcessCreatedAtUtc = $creationUtc
            ProcessCreationFileTimeUtc = $creationFileTime.ToString([System.Globalization.CultureInfo]::InvariantCulture)
            WindowsSessionId = [int]$sessionId
        }
    }
    finally {
        [void][PerfectAssassinLabClientNative]::CloseHandle($processHandle)
    }
}

function Assert-ExactPropertySet {
    param($Record, [string[]]$ExpectedNames, [string]$RecordName)
    if ($null -eq $Record) {
        throw "$RecordName is missing."
    }
    $actualNames = @($Record.PSObject.Properties.Name | Sort-Object)
    $expectedSorted = @($ExpectedNames | Sort-Object)
    if (
        $actualNames.Count -ne $expectedSorted.Count -or
        @(Compare-Object -ReferenceObject $expectedSorted -DifferenceObject $actualNames).Count -ne 0
    ) {
        throw "$RecordName has missing or unexpected properties."
    }
}

function Get-ExactJsonTokenType {
    param([Newtonsoft.Json.Linq.JToken]$Token)
    if ($null -eq $Token) {
        return [Newtonsoft.Json.Linq.JTokenType]::None
    }
    return [Newtonsoft.Json.Linq.JToken].GetProperty('Type').GetValue($Token)
}

function Get-RequiredJsonPropertyToken {
    param(
        [Newtonsoft.Json.Linq.JToken]$ObjectToken,
        [string]$PropertyName,
        [string]$RecordName
    )
    if (
        $null -eq $ObjectToken -or
        (Get-ExactJsonTokenType -Token $ObjectToken) -ne [Newtonsoft.Json.Linq.JTokenType]::Object
    ) {
        throw "$RecordName is not a JSON object."
    }
    $property = ([Newtonsoft.Json.Linq.JObject]$ObjectToken).Property($PropertyName)
    if ($null -eq $property) {
        throw "$RecordName.$PropertyName is missing."
    }
    return ,$property.Value
}

function Assert-JsonPropertyTokenType {
    param(
        [Newtonsoft.Json.Linq.JToken]$ObjectToken,
        [string]$PropertyName,
        [Newtonsoft.Json.Linq.JTokenType]$ExpectedType,
        [string]$RecordName
    )
    $valueToken = Get-RequiredJsonPropertyToken `
        -ObjectToken $ObjectToken `
        -PropertyName $PropertyName `
        -RecordName $RecordName
    $actualType = Get-ExactJsonTokenType -Token $valueToken
    if ($actualType -ne $ExpectedType) {
        throw "$RecordName.$PropertyName is not an exact JSON $ExpectedType value (actual $actualType)."
    }
    return ,$valueToken
}

function Assert-JsonStringArrayToken {
    param(
        [Newtonsoft.Json.Linq.JToken]$ObjectToken,
        [string]$PropertyName,
        [string]$RecordName
    )
    $arrayToken = Assert-JsonPropertyTokenType `
        -ObjectToken $ObjectToken `
        -PropertyName $PropertyName `
        -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::Array) `
        -RecordName $RecordName
    foreach ($item in $arrayToken.Children()) {
        if ((Get-ExactJsonTokenType -Token $item) -ne [Newtonsoft.Json.Linq.JTokenType]::String) {
            throw "$RecordName.$PropertyName contains a non-string JSON value."
        }
    }
}

function Assert-LegacyV01LaunchReceiptShape {
    param($Receipt, [Newtonsoft.Json.Linq.JToken]$Token)
    $rootNames = @(
        'record_type', 'schema_version', 'receipt_nonce', 'pid', 'hwnd',
        'window_title', 'window_class', 'executable_path', 'executable_sha256',
        'client_build', 'build_signature', 'target_profile', 'authorization_id',
        'authorization_sha256', 'actor_binding', 'environment_scope', 'server_kind',
        'expected_realm_fingerprint', 'realm_assurance', 'realm_routing_sha256',
        'realmlist_relative_path', 'realmlist_sha256', 'realmlist_directive',
        'decision_context', 'created_at', 'expires_at', 'scope', 'execution_authority'
    )
    Assert-ExactPropertySet -Record $Receipt -ExpectedNames $rootNames -RecordName 'Legacy LAB launch receipt'
    Assert-ExactPropertySet -Record $Receipt.actor_binding -ExpectedNames @(
        'schema_version', 'instance_id', 'actor_role', 'actor_id', 'decision_context',
        'memory_namespace', 'expected_character_name', 'credential_alias', 'binding_assurance'
    ) -RecordName 'Legacy LAB launch receipt actor binding'
    Assert-ExactPropertySet -Record $Receipt.actor_binding.binding_assurance -ExpectedNames @(
        'state', 'evidence_refs'
    ) -RecordName 'Legacy LAB launch receipt actor assurance'
    Assert-ExactPropertySet -Record $Receipt.realm_assurance -ExpectedNames @(
        'state', 'method', 'verified_at'
    ) -RecordName 'Legacy LAB launch receipt realm assurance'
    foreach ($stringField in @(
        'record_type', 'schema_version', 'receipt_nonce', 'hwnd', 'window_title',
        'window_class', 'executable_path', 'executable_sha256', 'client_build',
        'build_signature', 'target_profile', 'authorization_id', 'authorization_sha256',
        'environment_scope', 'server_kind', 'expected_realm_fingerprint',
        'realm_routing_sha256', 'realmlist_relative_path', 'realmlist_sha256',
        'realmlist_directive', 'decision_context', 'created_at', 'expires_at', 'scope'
    )) {
        [void](Assert-JsonPropertyTokenType -ObjectToken $Token -PropertyName $stringField `
            -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::String) -RecordName 'Legacy LAB launch receipt')
    }
    [void](Assert-JsonPropertyTokenType -ObjectToken $Token -PropertyName 'pid' `
        -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::Integer) -RecordName 'Legacy LAB launch receipt')
    [void](Assert-JsonPropertyTokenType -ObjectToken $Token -PropertyName 'execution_authority' `
        -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::Boolean) -RecordName 'Legacy LAB launch receipt')
    $actorToken = Assert-JsonPropertyTokenType -ObjectToken $Token -PropertyName 'actor_binding' `
        -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::Object) -RecordName 'Legacy LAB launch receipt'
    foreach ($stringField in @(
        'schema_version', 'instance_id', 'actor_role', 'actor_id', 'decision_context',
        'memory_namespace', 'expected_character_name', 'credential_alias'
    )) {
        [void](Assert-JsonPropertyTokenType -ObjectToken $actorToken -PropertyName $stringField `
            -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::String) -RecordName 'Legacy LAB launch receipt.actor_binding')
    }
    $bindingToken = Assert-JsonPropertyTokenType -ObjectToken $actorToken -PropertyName 'binding_assurance' `
        -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::Object) -RecordName 'Legacy LAB launch receipt.actor_binding'
    [void](Assert-JsonPropertyTokenType -ObjectToken $bindingToken -PropertyName 'state' `
        -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::String) -RecordName 'Legacy LAB launch receipt.actor_binding.binding_assurance')
    Assert-JsonStringArrayToken -ObjectToken $bindingToken -PropertyName 'evidence_refs' `
        -RecordName 'Legacy LAB launch receipt.actor_binding.binding_assurance'
    $realmToken = Assert-JsonPropertyTokenType -ObjectToken $Token -PropertyName 'realm_assurance' `
        -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::Object) -RecordName 'Legacy LAB launch receipt'
    foreach ($stringField in @('state', 'method', 'verified_at')) {
        [void](Assert-JsonPropertyTokenType -ObjectToken $realmToken -PropertyName $stringField `
            -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::String) -RecordName 'Legacy LAB launch receipt.realm_assurance')
    }
    if (
        $Receipt.record_type -ne 'lab_client_launch_receipt' -or
        $Receipt.schema_version -ne '0.1' -or
        [string]$Receipt.receipt_nonce -notmatch '^[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}$' -or
        [long]$Receipt.pid -lt 1 -or
        [string]$Receipt.hwnd -notmatch '^0x[A-F0-9]+$' -or
        [string]$Receipt.executable_sha256 -notmatch '^[A-F0-9]{64}$' -or
        [string]$Receipt.authorization_sha256 -notmatch '^[A-F0-9]{64}$' -or
        [string]$Receipt.realm_routing_sha256 -notmatch '^[A-F0-9]{64}$' -or
        [string]$Receipt.realmlist_sha256 -notmatch '^[A-F0-9]{64}$' -or
        $Receipt.window_title -ne $expectedWindowTitle -or
        $Receipt.window_class -ne $expectedWindowClass -or
        $Receipt.environment_scope -ne 'emulator_local' -or
        $Receipt.server_kind -ne 'emulator' -or
        $Receipt.decision_context -ne 'lab_clone' -or
        $Receipt.scope -ne 'lab_evaluation_only' -or
        $Receipt.execution_authority -ne $false
    ) {
        throw 'Legacy LAB launch receipt has an invalid v0.1 shape or scope.'
    }
    [void][DateTimeOffset]::Parse([string]$Receipt.created_at)
    [void][DateTimeOffset]::Parse([string]$Receipt.expires_at)
    [void](ConvertFrom-HexHwnd -Value ([string]$Receipt.hwnd))
    Assert-ExpectedActorBindingRecord -ActorBinding $Receipt.actor_binding
}

function Read-LabLaunchReceiptSnapshot {
    param([switch]$AllowLegacyV01)
    if (-not (Test-Path -LiteralPath $launchReceiptPath -PathType Leaf)) {
        throw 'Running legacy client has no operator launch receipt.'
    }
    try {
        $receiptBytes = [System.IO.File]::ReadAllBytes($launchReceiptPath)
        if ($receiptBytes.Length -lt 2 -or $receiptBytes.Length -gt 1048576) {
            throw 'LAB launch receipt size is outside the accepted bound.'
        }
        $receiptSha256 = Get-ByteArraySha256 -Bytes $receiptBytes
        $receiptJson = [System.Text.UTF8Encoding]::new($false, $true).GetString($receiptBytes)
        $strictReceipt = ConvertFrom-StrictJson -Json $receiptJson -RecordName 'LAB launch receipt' -IncludeToken
        $receipt = $strictReceipt.Record
        if ($receipt.schema_version -eq '1.0') {
            Assert-JsonSchema -Json $receiptJson -SchemaPath $launchReceiptSchemaPath -RecordName 'LAB launch receipt'
        }
        elseif ($AllowLegacyV01 -and $receipt.schema_version -eq '0.1') {
            Assert-LegacyV01LaunchReceiptShape -Receipt $receipt -Token $strictReceipt.Token
        }
        else {
            throw 'LAB launch receipt schema version is not accepted for this action.'
        }
    }
    catch {
        throw "LAB launch receipt snapshot cannot be read and validated atomically: $($_.Exception.Message)"
    }
    return [pscustomobject]@{
        Record = $receipt
        Sha256 = $receiptSha256
        Bytes = $receiptBytes
    }
}

function Remove-LabLaunchReceipt {
    if (Test-Path -LiteralPath $launchReceiptPath -PathType Leaf) {
        Remove-Item -LiteralPath $launchReceiptPath -Force
    }
}

function Remove-LabRuntimeArm {
    if (Test-Path -LiteralPath $runtimeArmPath -PathType Leaf) {
        Remove-Item -LiteralPath $runtimeArmPath -Force
    }
}

function Enter-LabIdentityMutationLock {
    New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
    try {
        return [System.IO.File]::Open(
            $identityLockPath,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    }
    catch {
        throw 'Another LAB session identity mutation is already in progress.'
    }
}

function New-ExpectedActorBindingRecord {
    return [ordered]@{
        schema_version = '1.0'
        instance_id = $instanceId
        actor_role = $actorRole
        actor_id = $actorId
        decision_context = $decisionContext
        memory_namespace = $memoryNamespace
        expected_character_name = $expectedCharacter
        credential_alias = 'credential:lab:pa_observer'
        binding_assurance = [ordered]@{
            state = 'configured_expected_only'
            evidence_refs = @($actorBindingEvidenceRefs)
        }
    }
}

function Assert-ExpectedActorBindingRecord {
    param($ActorBinding)
    $actualEvidenceRefs = @($ActorBinding.binding_assurance.evidence_refs)
    if (
        $ActorBinding.schema_version -ne '1.0' -or
        $ActorBinding.instance_id -ne $instanceId -or
        $ActorBinding.actor_role -ne $actorRole -or
        $ActorBinding.actor_id -ne $actorId -or
        $ActorBinding.decision_context -ne $decisionContext -or
        $ActorBinding.memory_namespace -ne $memoryNamespace -or
        $ActorBinding.expected_character_name -ne $expectedCharacter -or
        $ActorBinding.credential_alias -ne 'credential:lab:pa_observer' -or
        $ActorBinding.binding_assurance.state -ne 'configured_expected_only' -or
        @(Compare-Object -ReferenceObject $actorBindingEvidenceRefs -DifferenceObject $actualEvidenceRefs).Count -ne 0
    ) {
        throw 'Runtime artifact actor binding does not match the configured expected actor.'
    }
}

function Assert-AuthorizationContinuity {
    param($Receipt)
    $parentAuthorizationSha256 = [string]$Receipt.authorization_sha256
    if ($parentAuthorizationSha256 -notmatch '^[A-F0-9]{64}$') {
        throw 'Parent receipt authorization hash is malformed.'
    }
    if ($Receipt.schema_version -eq '1.0') {
        if ([string]$Receipt.authorization_semantic_sha256 -ne $authorizationSemanticSha256) {
            throw 'Parent receipt authorization semantics differ from the active authorization.'
        }
    }
    if ($parentAuthorizationSha256 -ne $authorizationSha256) {
        if (
            [string]$targetAuthorization.approval.renewal_scope -ne 'temporal_only' -or
            [string]$targetAuthorization.approval.renews_authorization_sha256 -ne $parentAuthorizationSha256
        ) {
            throw 'Authorization hash rollover is not an explicit temporal-only renewal of the parent authorization.'
        }
    }
}

function New-LocalRealmAssuranceRecord {
    param(
        [DateTimeOffset]$VerifiedAt,
        [ValidateSet('local_process_config_verified_at_launch', 'local_process_config_revalidated_at_arm')]
        [string]$State
    )
    return [ordered]@{
        state = $State
        method = 'exact_realmlist_listener_process_config_and_realm_route'
        verified_at = $VerifiedAt.ToString('o')
    }
}

function Assert-LocalRealmAssuranceRecord {
    param(
        $RealmAssurance,
        [string]$ExpectedState,
        [DateTimeOffset]$NotBefore,
        [DateTimeOffset]$NotAfter
    )
    if (
        $RealmAssurance.state -ne $ExpectedState -or
        $RealmAssurance.method -ne 'exact_realmlist_listener_process_config_and_realm_route'
    ) {
        throw 'Runtime artifact does not carry the required local realm assurance.'
    }
    $verifiedAt = [DateTimeOffset]::Parse([string]$RealmAssurance.verified_at)
    if ($verifiedAt -lt $NotBefore -or $verifiedAt -gt $NotAfter) {
        throw 'Runtime artifact realm assurance timestamp is outside its valid interval.'
    }
}

function Get-LabIdentityIssuancePath {
    param([string]$ReceiptNonce)
    if ($ReceiptNonce -notmatch '^[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}$') {
        throw 'LAB identity issuance nonce is malformed.'
    }
    return Join-Path $identityIssuanceRoot ("{0}.json" -f $ReceiptNonce.ToLowerInvariant())
}

function Read-LabIdentityIssuanceSnapshot {
    param([string]$ReceiptNonce)
    $path = Get-LabIdentityIssuancePath -ReceiptNonce $ReceiptNonce
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw 'LAB identity issuance commit is missing.'
    }
    $markerBytes = [System.IO.File]::ReadAllBytes($path)
    if ($markerBytes.Length -lt 2 -or $markerBytes.Length -gt 2097152) {
        throw 'LAB identity issuance commit size is outside the accepted bound.'
    }
    $markerJson = [System.Text.UTF8Encoding]::new($false, $true).GetString($markerBytes)
    $marker = ConvertFrom-StrictJson -Json $markerJson -RecordName 'LAB identity issuance commit'
    Assert-JsonSchema -Json $markerJson -SchemaPath $identityIssuanceSchemaPath -RecordName 'LAB identity issuance commit'
    if (
        [string]$marker.issuance_nonce -ne $ReceiptNonce -or
        [string]$marker.new_receipt_nonce -ne $ReceiptNonce
    ) {
        throw 'LAB identity issuance commit nonce does not match its immutable filename.'
    }
    try {
        $receiptBytes = [Convert]::FromBase64String([string]$marker.receipt_utf8_base64)
    }
    catch {
        throw 'LAB identity issuance commit contains invalid receipt bytes.'
    }
    if (
        $receiptBytes.Length -lt 2 -or
        $receiptBytes.Length -gt 1048576 -or
        ($receiptBytes.Length -ge 3 -and $receiptBytes[0] -eq 0xEF -and $receiptBytes[1] -eq 0xBB -and $receiptBytes[2] -eq 0xBF)
    ) {
        throw 'LAB identity issuance embedded receipt bytes are outside the canonical bound.'
    }
    $receiptSha256 = Get-ByteArraySha256 -Bytes $receiptBytes
    if ($receiptSha256 -ne [string]$marker.new_receipt_sha256) {
        throw 'LAB identity issuance embedded receipt hash does not match its commit.'
    }
    $receiptJson = [System.Text.UTF8Encoding]::new($false, $true).GetString($receiptBytes)
    $receipt = ConvertFrom-StrictJson -Json $receiptJson -RecordName 'LAB identity issuance embedded receipt'
    Assert-JsonSchema -Json $receiptJson -SchemaPath $launchReceiptSchemaPath -RecordName 'LAB identity issuance embedded receipt'
    $expectedAction = switch ([string]$receipt.identity_origin) {
        'operator_launch' { 'Launch' }
        'legacy_v0_1_continuity_adoption' { 'AdoptSession' }
        'verified_receipt_renewal' { 'RenewSessionIdentity' }
        default { throw 'LAB identity issuance embedded receipt origin is not recognized.' }
    }
    if (
        [string]$marker.action -ne $expectedAction -or
        [string]$marker.identity_origin -ne [string]$receipt.identity_origin -or
        [string]$marker.parent_receipt_nonce -ne [string]$receipt.parent_receipt_nonce -or
        [string]$marker.parent_receipt_sha256 -ne [string]$receipt.parent_receipt_sha256 -or
        [string]$marker.parent_authorization_sha256 -ne [string]$receipt.parent_authorization_sha256 -or
        [string]$marker.new_receipt_nonce -ne [string]$receipt.receipt_nonce -or
        [string]$marker.new_authorization_sha256 -ne [string]$receipt.authorization_sha256 -or
        [string]$marker.new_authorization_semantic_sha256 -ne [string]$receipt.authorization_semantic_sha256 -or
        [int]$marker.pid -ne [int]$receipt.pid -or
        [string]$marker.hwnd -ne [string]$receipt.hwnd -or
        [string]$marker.process_creation_filetime_utc -ne [string]$receipt.process_creation_filetime_utc -or
        [int]$marker.windows_session_id -ne [int]$receipt.windows_session_id -or
        [string]$marker.issued_at -ne [string]$receipt.created_at -or
        $marker.execution_authority -ne $false
    ) {
        throw 'LAB identity issuance commit does not exactly bind its embedded receipt.'
    }
    return [pscustomobject]@{
        Record = $marker
        Sha256 = Get-ByteArraySha256 -Bytes $markerBytes
        Bytes = $markerBytes
        Path = $path
        ReceiptSnapshot = [pscustomobject]@{
            Record = $receipt
            Sha256 = $receiptSha256
            Bytes = $receiptBytes
        }
    }
}

function Get-LabIdentityIssuanceSnapshots {
    if (-not (Test-Path -LiteralPath $identityIssuanceRoot -PathType Container)) {
        return @()
    }
    $files = @(Get-ChildItem -LiteralPath $identityIssuanceRoot -File -Filter '*.json')
    if ($files.Count -gt 4096) {
        throw 'LAB identity issuance commit count exceeds its accepted bound.'
    }
    $snapshots = @()
    foreach ($file in $files) {
        if ($file.BaseName -notmatch '^[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}$') {
            throw 'LAB identity issuance directory contains a non-canonical commit filename.'
        }
        $snapshots += Read-LabIdentityIssuanceSnapshot -ReceiptNonce $file.BaseName
    }
    $consumedParents = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($candidate in @($snapshots | Where-Object { $null -ne $_.Record.parent_receipt_nonce })) {
        $parentKey = '{0}:{1}' -f (
            [string]$candidate.Record.parent_receipt_nonce
        ), ([string]$candidate.Record.parent_receipt_sha256)
        if (-not $consumedParents.Add($parentKey)) {
            throw 'Immutable LAB identity issuance history contains a forked parent transition.'
        }
    }
    return @($snapshots)
}

function Assert-V1ReceiptIssuanceCommit {
    param($Receipt, [string]$ReceiptSha256)
    $snapshot = Read-LabIdentityIssuanceSnapshot -ReceiptNonce ([string]$Receipt.receipt_nonce)
    if ([string]$snapshot.ReceiptSnapshot.Sha256 -ne $ReceiptSha256) {
        throw 'LAB v1.0 receipt bytes do not match their immutable issuance commit.'
    }
    return $snapshot
}

function New-LabLaunchReceipt {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$CanonicalExecutablePath,
        [ValidateSet('operator_launch', 'legacy_v0_1_continuity_adoption', 'verified_receipt_renewal')]
        [string]$IdentityOrigin = 'operator_launch',
        [AllowNull()]$ParentReceiptNonce,
        [AllowNull()]$ParentReceiptSha256,
        [AllowNull()]$ParentAuthorizationSha256,
        [AllowNull()]$LegacyLaunchAuditFileSha256,
        [AllowNull()]$LegacyLaunchAuditEntrySha256
    )
    Assert-ActiveTargetAuthorization
    $window = Assert-ExactClientWindowBinding -Process $Process
    $metadata = Get-ExactClientProcessMetadata -Process $Process
    if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals($metadata.ExecutablePath, $CanonicalExecutablePath)) {
        throw 'Running client metadata path changed before receipt creation.'
    }
    if ($metadata.WindowsSessionId -ne [System.Diagnostics.Process]::GetCurrentProcess().SessionId) {
        throw 'Running client is not in the operator Windows session.'
    }
    if ($IdentityOrigin -eq 'operator_launch') {
        if (
            -not [string]::IsNullOrEmpty($ParentReceiptNonce) -or
            -not [string]::IsNullOrEmpty($ParentReceiptSha256) -or
            -not [string]::IsNullOrEmpty($ParentAuthorizationSha256)
        ) {
            throw 'An operator launch receipt cannot have a parent receipt.'
        }
        $ParentReceiptNonce = $null
        $ParentReceiptSha256 = $null
        $ParentAuthorizationSha256 = $null
    }
    elseif (
        [string]::IsNullOrWhiteSpace($ParentReceiptNonce) -or
        $ParentReceiptSha256 -notmatch '^[A-F0-9]{64}$' -or
        $ParentAuthorizationSha256 -notmatch '^[A-F0-9]{64}$'
    ) {
        throw 'An adopted or renewed identity requires an exact parent receipt nonce and hash.'
    }
    if ($IdentityOrigin -eq 'legacy_v0_1_continuity_adoption') {
        if (
            $LegacyLaunchAuditFileSha256 -notmatch '^[A-F0-9]{64}$' -or
            $LegacyLaunchAuditEntrySha256 -notmatch '^[A-F0-9]{64}$'
        ) {
            throw 'Legacy continuity adoption requires exact immutable audit migration evidence.'
        }
    }
    elseif (
        -not [string]::IsNullOrEmpty($LegacyLaunchAuditFileSha256) -or
        -not [string]::IsNullOrEmpty($LegacyLaunchAuditEntrySha256)
    ) {
        throw 'Only legacy continuity adoption may bind legacy audit migration evidence.'
    }
    else {
        $LegacyLaunchAuditFileSha256 = $null
        $LegacyLaunchAuditEntrySha256 = $null
    }
    Assert-LabReady
    $realm = Assert-ExactLabRealm
    $routing = Assert-ExactRealmRoutingRecord
    $currentHash = (Get-FileHash -LiteralPath $CanonicalExecutablePath -Algorithm SHA256).Hash
    if ($currentHash -ne $expectedClientSha256) {
        throw 'WoW executable changed between launch and receipt creation.'
    }
    $createdAt = [DateTimeOffset]::UtcNow
    $expiresAt = Get-BoundedExpiry -IssuedAt $createdAt
    $nonce = [Guid]::NewGuid().ToString('D')
    $receipt = [ordered]@{
        record_type = 'lab_client_launch_receipt'
        schema_version = '1.0'
        receipt_nonce = $nonce
        pid = $Process.Id
        hwnd = $window.HwndHex
        process_created_at_utc = $metadata.ProcessCreatedAtUtc.ToString('o')
        process_creation_filetime_utc = $metadata.ProcessCreationFileTimeUtc
        windows_session_id = $metadata.WindowsSessionId
        identity_origin = $IdentityOrigin
        parent_receipt_nonce = $ParentReceiptNonce
        parent_receipt_sha256 = $ParentReceiptSha256
        parent_authorization_sha256 = $ParentAuthorizationSha256
        window_title = $window.Title
        window_class = $window.Class
        executable_path = $CanonicalExecutablePath
        executable_sha256 = $expectedClientSha256
        client_build = $expectedClientBuild
        build_signature = $expectedBuildSignature
        target_profile = [string]$targetAuthorization.target_profile
        authorization_id = [string]$targetAuthorization.authorization_id
        authorization_sha256 = $authorizationSha256
        authorization_semantic_sha256 = $authorizationSemanticSha256
        actor_binding = New-ExpectedActorBindingRecord
        environment_scope = [string]$targetAuthorization.environment_scope
        server_kind = [string]$targetAuthorization.realm_match.server_kind
        expected_realm_fingerprint = $expectedRealmFingerprint
        realm_assurance = New-LocalRealmAssuranceRecord -VerifiedAt $createdAt -State 'local_process_config_verified_at_launch'
        realm_routing_sha256 = $routing.Sha256
        realmlist_relative_path = $realm.RelativePath
        realmlist_sha256 = $realm.Sha256
        realmlist_directive = $realm.Directive
        decision_context = $decisionContext
        created_at = $createdAt.ToString('o')
        expires_at = $expiresAt.ToString('o')
        scope = 'lab_evaluation_only'
        execution_authority = $false
    }
    $json = $receipt | ConvertTo-Json -Depth 5
    Assert-JsonSchema -Json $json -SchemaPath $launchReceiptSchemaPath -RecordName 'LAB launch receipt'
    $receiptBytes = [System.Text.UTF8Encoding]::new($false).GetBytes($json)
    $receiptSha256 = Get-ByteArraySha256 -Bytes $receiptBytes
    $actionName = switch ($IdentityOrigin) {
        'operator_launch' { 'Launch' }
        'legacy_v0_1_continuity_adoption' { 'AdoptSession' }
        'verified_receipt_renewal' { 'RenewSessionIdentity' }
    }
    $issuance = [ordered]@{
        record_type = 'lab_client_identity_issuance'
        schema_version = '1.0'
        issuance_nonce = $nonce
        action = $actionName
        identity_origin = $IdentityOrigin
        parent_receipt_nonce = $ParentReceiptNonce
        parent_receipt_sha256 = $ParentReceiptSha256
        parent_authorization_sha256 = $ParentAuthorizationSha256
        new_receipt_nonce = $nonce
        new_receipt_sha256 = $receiptSha256
        new_authorization_sha256 = $authorizationSha256
        new_authorization_semantic_sha256 = $authorizationSemanticSha256
        pid = $Process.Id
        hwnd = $window.HwndHex
        process_creation_filetime_utc = $metadata.ProcessCreationFileTimeUtc
        windows_session_id = $metadata.WindowsSessionId
        issued_at = $createdAt.ToString('o')
        receipt_utf8_base64 = [Convert]::ToBase64String($receiptBytes)
        legacy_launch_audit_file_sha256 = $LegacyLaunchAuditFileSha256
        legacy_launch_audit_entry_sha256 = $LegacyLaunchAuditEntrySha256
        scope = 'lab_identity_issuance_commit'
        execution_authority = $false
    }
    $issuanceJson = $issuance | ConvertTo-Json -Depth 5
    Assert-JsonSchema -Json $issuanceJson -SchemaPath $identityIssuanceSchemaPath -RecordName 'LAB identity issuance commit'
    if ($IdentityOrigin -ne 'operator_launch') {
        Assert-ParentReceiptUnused `
            -ParentReceiptNonce $ParentReceiptNonce `
            -ParentReceiptSha256 $ParentReceiptSha256
    }
    # Receipt replacement always revokes any fixed-UI arm tied to the parent identity.
    Remove-LabRuntimeArm
    # The immutable marker is the commit point. The receipt is a recoverable projection.
    $issuancePath = Get-LabIdentityIssuancePath -ReceiptNonce $nonce
    Write-AtomicImmutableJsonRecord -Path $issuancePath -Json $issuanceJson -Nonce $nonce
    Write-AtomicJsonRecord -Path $launchReceiptPath -Json $json -Nonce $nonce
    $result = [pscustomobject]$receipt
    $result | Add-Member -NotePropertyName ReceiptSha256 -NotePropertyValue $receiptSha256
    $result | Add-Member -NotePropertyName IssuancePath -NotePropertyValue $issuancePath
    return $result
}

function Assert-ExactProcessCreationBinding {
    param($Receipt, $Metadata, [DateTimeOffset]$ReceiptCreatedAt)
    $receiptProcessCreatedAt = [DateTimeOffset]::Parse([string]$Receipt.process_created_at_utc)
    $receiptFileTime = [string]$Receipt.process_creation_filetime_utc
    $roundTripFileTime = $receiptProcessCreatedAt.UtcDateTime.ToFileTimeUtc().ToString(
        [System.Globalization.CultureInfo]::InvariantCulture
    )
    if ($roundTripFileTime -ne $receiptFileTime -or $receiptProcessCreatedAt -gt $ReceiptCreatedAt) {
        throw 'LAB launch receipt process creation fields are inconsistent.'
    }
    if ($receiptFileTime -ne [string]$Metadata.ProcessCreationFileTimeUtc) {
        throw 'LAB launch receipt native creation FILETIME does not match the running process.'
    }
}

function Assert-LabLaunchReceiptSnapshot {
    param(
        $Snapshot,
        [System.Diagnostics.Process]$Process,
        [switch]$AllowExpired,
        [switch]$AllowWindowRebind,
        [switch]$AllowAuthorizationRebind
    )
    Assert-ActiveTargetAuthorization
    $receipt = $Snapshot.Record
    $createdAt = [DateTimeOffset]::Parse([string]$receipt.created_at)
    $expiresAt = [DateTimeOffset]::Parse([string]$receipt.expires_at)
    $now = [DateTimeOffset]::UtcNow
    if (
        $createdAt -gt $now -or
        ((-not $AllowExpired) -and $expiresAt -le $now) -or
        $expiresAt -le $createdAt
    ) {
        throw 'LAB launch receipt is expired or not yet valid.'
    }
    if (($expiresAt - $createdAt).TotalMinutes -gt $maxSessionMinutes) {
        throw 'LAB launch receipt exceeds approval.max_session_minutes.'
    }
    Assert-LabReady
    $realm = Assert-ExactLabRealm
    $routing = Assert-ExactRealmRoutingRecord
    Assert-ExpectedActorBindingRecord -ActorBinding $receipt.actor_binding
    if ($AllowAuthorizationRebind) {
        if ([string]$receipt.authorization_sha256 -notmatch '^[A-F0-9]{64}$') {
            throw 'Authorization rebind parent hash is malformed.'
        }
    }
    else {
        Assert-AuthorizationContinuity -Receipt $receipt
    }
    Assert-LocalRealmAssuranceRecord -RealmAssurance $receipt.realm_assurance -ExpectedState 'local_process_config_verified_at_launch' -NotBefore $createdAt -NotAfter $now
    if ($expiresAt -gt $authorizationExpiresAt) {
        throw 'LAB launch receipt exceeds the active authorization expiry.'
    }
    $receiptHwnd = ConvertFrom-HexHwnd -Value ([string]$receipt.hwnd)
    $metadata = Get-ExactClientProcessMetadata -Process $Process
    Assert-ExactProcessCreationBinding -Receipt $receipt -Metadata $metadata -ReceiptCreatedAt $createdAt
    if (
        [int]$receipt.pid -ne $Process.Id -or
        [int]$receipt.windows_session_id -ne $metadata.WindowsSessionId -or
        [int]$receipt.windows_session_id -ne [System.Diagnostics.Process]::GetCurrentProcess().SessionId -or
        $receipt.executable_sha256 -ne $expectedClientSha256 -or
        $receipt.client_build -ne $expectedClientBuild -or
        $receipt.build_signature -ne $expectedBuildSignature -or
        $receipt.target_profile -ne $targetAuthorization.target_profile -or
        $receipt.authorization_id -ne $targetAuthorization.authorization_id -or
        ((-not $AllowAuthorizationRebind) -and
            $receipt.authorization_semantic_sha256 -ne $authorizationSemanticSha256) -or
        $receipt.environment_scope -ne 'emulator_local' -or
        $receipt.server_kind -ne 'emulator' -or
        $receipt.expected_realm_fingerprint -ne $expectedRealmFingerprint -or
        $receipt.realm_routing_sha256 -ne $routing.Sha256 -or
        $receipt.realmlist_relative_path -ne $realm.RelativePath -or
        $receipt.realmlist_sha256 -ne $realm.Sha256 -or
        $receipt.realmlist_directive -ne $realm.Directive -or
        $receipt.decision_context -ne $decisionContext -or
        $receipt.scope -ne 'lab_evaluation_only' -or
        $receipt.execution_authority -ne $false
    ) {
        throw 'LAB launch receipt does not match the active exact authorization.'
    }
    $canonicalPath = Assert-ClientExecutableIdentity -Path ([string]$receipt.executable_path)
    if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals($canonicalPath, $metadata.ExecutablePath)) {
        throw 'LAB launch receipt image path does not match the running process.'
    }
    if ($AllowWindowRebind) {
        # A windowed graphics-mode change can recreate only the top-level HWND
        # while preserving the exact client process.  The complete PID,
        # creation FILETIME, Windows session, executable path/hash, title,
        # class, realm, authorization lineage and immutable receipt checks
        # above remain mandatory; only the stale parent HWND is not compared.
        [void](Assert-ExactClientWindowBinding -Process $Process)
    }
    else {
        [void](Assert-ExactClientWindowBinding -Process $Process -ExpectedHwnd $receiptHwnd)
    }
    [void](Assert-V1ReceiptIssuanceCommit -Receipt $receipt -ReceiptSha256 $Snapshot.Sha256)
    return $receipt
}

function Assert-LabLaunchReceipt {
    param(
        [System.Diagnostics.Process]$Process,
        [switch]$AllowExpired
    )
    $snapshot = Read-LabLaunchReceiptSnapshot
    return Assert-LabLaunchReceiptSnapshot -Snapshot $snapshot -Process $Process -AllowExpired:$AllowExpired
}

function Read-OperatorAuditSnapshot {
    if (-not (Test-Path -LiteralPath $auditPath -PathType Leaf)) {
        throw 'LAB operator launch audit lineage is missing.'
    }
    $auditBytes = [System.IO.File]::ReadAllBytes($auditPath)
    if ($auditBytes.Length -lt 2 -or $auditBytes.Length -gt 16777216) {
        throw 'LAB operator audit size is outside the accepted bound.'
    }
    $auditText = [System.Text.UTF8Encoding]::new($false, $true).GetString($auditBytes)
    $records = @()
    foreach ($line in @($auditText -split "`r?`n")) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        if ($line.Length -gt 65536) {
            throw 'LAB operator audit contains an overlength record.'
        }
        try {
            $strictEntry = ConvertFrom-StrictJson -Json $line -RecordName 'LAB operator audit record' -IncludeToken
            $records += [pscustomobject]@{
                Record = $strictEntry.Record
                Token = $strictEntry.Token
                LineSha256 = Get-ByteArraySha256 -Bytes (
                    [System.Text.UTF8Encoding]::new($false).GetBytes($line)
                )
            }
        }
        catch {
            throw 'LAB operator audit contains malformed JSON; identity lineage is refused.'
        }
    }
    return [pscustomobject]@{
        Records = @($records)
        FileSha256 = Get-ByteArraySha256 -Bytes $auditBytes
    }
}

function Test-OperatorAuditIdentityEnvelope {
    param($Entry)
    return (
        $Entry.actor -eq 'external_lab_operator_harness' -and
        $Entry.result -eq 'complete' -and
        $Entry.expected_account -eq $expectedAccount -and
        $Entry.expected_character -eq $expectedCharacter -and
        $Entry.instance_id -eq $instanceId -and
        $Entry.actor_id -eq $actorId -and
        $Entry.actor_role -eq 'lab_clone' -and
        $Entry.decision_context -eq 'lab_clone' -and
        $Entry.memory_namespace -eq $memoryNamespace -and
        $Entry.predator_execution_mode -eq 'OBSERVE_ONLY'
    )
}

function Assert-LegacyLaunchAuditIdentityTypes {
    param([Newtonsoft.Json.Linq.JToken]$Token)
    foreach ($stringField in @(
        'occurred_at', 'actor', 'action', 'result', 'expected_account',
        'expected_character', 'instance_id', 'actor_id', 'actor_role',
        'decision_context', 'memory_namespace', 'predator_execution_mode'
    )) {
        [void](Assert-JsonPropertyTokenType -ObjectToken $Token -PropertyName $stringField `
            -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::String) -RecordName 'Legacy Launch audit record')
    }
    $detailsToken = Assert-JsonPropertyTokenType -ObjectToken $Token -PropertyName 'details' `
        -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::Object) -RecordName 'Legacy Launch audit record'
    foreach ($stringField in @(
        'checkpoint', 'hwnd', 'launch_receipt_nonce', 'receipt_expires_at'
    )) {
        [void](Assert-JsonPropertyTokenType -ObjectToken $detailsToken -PropertyName $stringField `
            -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::String) -RecordName 'Legacy Launch audit record.details')
    }
    [void](Assert-JsonPropertyTokenType -ObjectToken $detailsToken -PropertyName 'pid' `
        -ExpectedType ([Newtonsoft.Json.Linq.JTokenType]::Integer) -RecordName 'Legacy Launch audit record.details')
}

function Assert-ExactLegacyLaunchAuditLineage {
    param($Receipt)
    $createdAt = [DateTimeOffset]::Parse([string]$Receipt.created_at)
    $expiresAt = [DateTimeOffset]::Parse([string]$Receipt.expires_at)
    $matches = @()
    $auditSnapshot = Read-OperatorAuditSnapshot
    foreach ($entrySnapshot in @($auditSnapshot.Records)) {
        $entry = $entrySnapshot.Record
        if (-not (Test-OperatorAuditIdentityEnvelope -Entry $entry) -or $entry.action -ne 'Launch') {
            continue
        }
        Assert-LegacyLaunchAuditIdentityTypes -Token $entrySnapshot.Token
        try {
            $occurredAt = [DateTimeOffset]::Parse([string]$entry.occurred_at)
            $auditExpiry = [DateTimeOffset]::Parse([string]$entry.details.receipt_expires_at)
        }
        catch {
            continue
        }
        if (
            [int]$entry.details.pid -eq [int]$Receipt.pid -and
            [string]$entry.details.hwnd -eq [string]$Receipt.hwnd -and
            [string]$entry.details.launch_receipt_nonce -eq [string]$Receipt.receipt_nonce -and
            $auditExpiry -eq $expiresAt -and
            $occurredAt -ge $createdAt -and
            $occurredAt -le $createdAt.AddSeconds(60) -and
            -not [string]::IsNullOrWhiteSpace([string]$entry.details.checkpoint)
        ) {
            $matches += $entrySnapshot
        }
    }
    if ($matches.Count -ne 1) {
        throw 'Legacy v0.1 receipt does not have one exact operator Launch audit lineage.'
    }
    return [pscustomobject]@{
        AuditFileSha256 = [string]$auditSnapshot.FileSha256
        AuditEntrySha256 = [string]$matches[0].LineSha256
    }
}

function Assert-ParentReceiptUnused {
    param([string]$ParentReceiptNonce, [string]$ParentReceiptSha256)
    foreach ($issuance in @(Get-LabIdentityIssuanceSnapshots)) {
        if (
            [string]$issuance.Record.parent_receipt_nonce -eq $ParentReceiptNonce -and
            [string]$issuance.Record.parent_receipt_sha256 -eq $ParentReceiptSha256
        ) {
            throw 'This exact parent receipt has already been adopted or renewed once.'
        }
    }
}

function Write-LabLaunchReceiptProjectionFromCommit {
    param($ReceiptSnapshot)
    $receiptBytes = [byte[]]$ReceiptSnapshot.Bytes
    $receiptSha256 = Get-ByteArraySha256 -Bytes $receiptBytes
    if ($receiptSha256 -ne [string]$ReceiptSnapshot.Sha256) {
        throw 'Committed LAB identity receipt bytes changed before projection recovery.'
    }
    $receiptJson = [System.Text.UTF8Encoding]::new($false, $true).GetString($receiptBytes)
    $strictReceipt = ConvertFrom-StrictJson `
        -Json $receiptJson `
        -RecordName 'Committed LAB identity receipt projection'
    if ([string]$strictReceipt.receipt_nonce -ne [string]$ReceiptSnapshot.Record.receipt_nonce) {
        throw 'Committed LAB identity receipt projection nonce changed before recovery.'
    }
    Write-AtomicJsonRecord `
        -Path $launchReceiptPath `
        -Json $receiptJson `
        -Nonce ([string]$ReceiptSnapshot.Record.receipt_nonce)
    $writtenSha256 = Get-ByteArraySha256 -Bytes ([System.IO.File]::ReadAllBytes($launchReceiptPath))
    if ($writtenSha256 -ne [string]$ReceiptSnapshot.Sha256) {
        throw 'Recovered LAB identity receipt projection hash verification failed.'
    }
}

function Complete-CommittedIdentityProjection {
    param([System.Diagnostics.Process]$Process)
    Assert-ActiveTargetAuthorization
    $issuances = @(Get-LabIdentityIssuanceSnapshots)
    if ($issuances.Count -eq 0) {
        return [pscustomobject]@{ Recovered = $false; Action = $null; Receipt = $null }
    }

    $currentSnapshot = $null
    if (Test-Path -LiteralPath $launchReceiptPath -PathType Leaf) {
        $currentSnapshot = Read-LabLaunchReceiptSnapshot -AllowLegacyV01
        if ($currentSnapshot.Record.schema_version -eq '1.0') {
            [void](Assert-V1ReceiptIssuanceCommit `
                -Receipt $currentSnapshot.Record `
                -ReceiptSha256 $currentSnapshot.Sha256)
        }
    }

    $cursorReceipt = if ($null -ne $currentSnapshot) { $currentSnapshot.Record } else { $null }
    $cursorSha256 = if ($null -ne $currentSnapshot) { [string]$currentSnapshot.Sha256 } else { $null }
    $terminalIssuance = $null
    $advanced = $false
    $visited = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)

    if ($null -eq $cursorReceipt) {
        $metadata = Get-ExactClientProcessMetadata -Process $Process
        $roots = @($issuances | Where-Object {
            $_.Record.action -eq 'Launch' -and
            $null -eq $_.Record.parent_receipt_nonce -and
            [int]$_.ReceiptSnapshot.Record.pid -eq $Process.Id -and
            [string]$_.ReceiptSnapshot.Record.process_creation_filetime_utc -eq $metadata.ProcessCreationFileTimeUtc -and
            [int]$_.ReceiptSnapshot.Record.windows_session_id -eq $metadata.WindowsSessionId
        })
        if ($roots.Count -eq 0) {
            return [pscustomobject]@{ Recovered = $false; Action = $null; Receipt = $null }
        }
        if ($roots.Count -ne 1) {
            throw 'More than one committed root identity matches the running client; recovery is refused.'
        }
        $terminalIssuance = $roots[0]
        $cursorReceipt = $terminalIssuance.ReceiptSnapshot.Record
        $cursorSha256 = [string]$terminalIssuance.ReceiptSnapshot.Sha256
        $advanced = $true
        [void]$visited.Add([string]$cursorReceipt.receipt_nonce)
    }
    else {
        [void]$visited.Add([string]$cursorReceipt.receipt_nonce)
    }

    while ($true) {
        $children = @($issuances | Where-Object {
            [string]$_.Record.parent_receipt_nonce -eq [string]$cursorReceipt.receipt_nonce -and
            [string]$_.Record.parent_receipt_sha256 -eq $cursorSha256
        })
        if ($children.Count -gt 1) {
            throw 'Committed LAB identity lineage forks from one parent; recovery is refused.'
        }
        if ($children.Count -eq 0) {
            break
        }
        $child = $children[0]
        if (
            [string]$child.Record.parent_authorization_sha256 -ne [string]$cursorReceipt.authorization_sha256 -or
            -not $visited.Add([string]$child.Record.new_receipt_nonce)
        ) {
            throw 'Committed LAB identity lineage is cyclic or has broken authorization ancestry.'
        }
        $terminalIssuance = $child
        $cursorReceipt = $child.ReceiptSnapshot.Record
        $cursorSha256 = [string]$child.ReceiptSnapshot.Sha256
        $advanced = $true
    }

    if (-not $advanced) {
        return [pscustomobject]@{ Recovered = $false; Action = $null; Receipt = $null }
    }
    $terminalSnapshot = $terminalIssuance.ReceiptSnapshot
    [void](Assert-LabLaunchReceiptSnapshot -Snapshot $terminalSnapshot -Process $Process -AllowExpired)
    Remove-LabRuntimeArm
    Write-LabLaunchReceiptProjectionFromCommit -ReceiptSnapshot $terminalSnapshot
    return [pscustomobject]@{
        Recovered = $true
        Action = [string]$terminalIssuance.Record.action
        Receipt = $terminalSnapshot.Record
        ReceiptSha256 = [string]$terminalSnapshot.Sha256
    }
}

function Assert-ExactLegacyV01Continuity {
    param([System.Diagnostics.Process]$Process, $Snapshot)
    Assert-ActiveTargetAuthorization
    $receipt = $Snapshot.Record
    $createdAt = [DateTimeOffset]::Parse([string]$receipt.created_at)
    $expiresAt = [DateTimeOffset]::Parse([string]$receipt.expires_at)
    $now = [DateTimeOffset]::UtcNow
    if (
        $createdAt -gt $now -or
        $expiresAt -le $createdAt -or
        ($expiresAt - $createdAt).TotalMinutes -gt $maxSessionMinutes
    ) {
        throw 'Legacy LAB launch receipt has an invalid issuance interval.'
    }
    if ($expiresAt -gt $authorizationExpiresAt) {
        throw 'Legacy LAB launch receipt exceeds authorization expiry.'
    }
    Assert-LabReady
    $realm = Assert-ExactLabRealm
    $routing = Assert-ExactRealmRoutingRecord
    Assert-ExpectedActorBindingRecord -ActorBinding $receipt.actor_binding
    Assert-AuthorizationContinuity -Receipt $receipt
    Assert-LocalRealmAssuranceRecord -RealmAssurance $receipt.realm_assurance -ExpectedState 'local_process_config_verified_at_launch' -NotBefore $createdAt -NotAfter $now
    $metadata = Get-ExactClientProcessMetadata -Process $Process
    $operatorSessionId = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
    $processCreatedAt = [DateTimeOffset]$metadata.ProcessCreatedAtUtc
    if (
        $processCreatedAt -gt $createdAt -or
        ($createdAt - $processCreatedAt).TotalSeconds -gt 60 -or
        $metadata.WindowsSessionId -ne $operatorSessionId
    ) {
        throw 'Legacy receipt is not continuous with the exact process creation and Windows session.'
    }
    $receiptHwnd = ConvertFrom-HexHwnd -Value ([string]$receipt.hwnd)
    if (
        [int]$receipt.pid -ne $Process.Id -or
        $receipt.executable_sha256 -ne $expectedClientSha256 -or
        $receipt.client_build -ne $expectedClientBuild -or
        $receipt.build_signature -ne $expectedBuildSignature -or
        $receipt.target_profile -ne $targetAuthorization.target_profile -or
        $receipt.authorization_id -ne $targetAuthorization.authorization_id -or
        $receipt.environment_scope -ne 'emulator_local' -or
        $receipt.server_kind -ne 'emulator' -or
        $receipt.expected_realm_fingerprint -ne $expectedRealmFingerprint -or
        $receipt.realm_routing_sha256 -ne $routing.Sha256 -or
        $receipt.realmlist_relative_path -ne $realm.RelativePath -or
        $receipt.realmlist_sha256 -ne $realm.Sha256 -or
        $receipt.realmlist_directive -ne $realm.Directive -or
        $receipt.decision_context -ne 'lab_clone' -or
        $receipt.scope -ne 'lab_evaluation_only' -or
        $receipt.execution_authority -ne $false
    ) {
        throw 'Legacy LAB receipt does not match the active exact authorization and realm.'
    }
    $receiptPath = Assert-ClientExecutableIdentity -Path ([string]$receipt.executable_path)
    if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals($receiptPath, $metadata.ExecutablePath)) {
        throw 'Legacy receipt executable path does not match the running process image.'
    }
    [void](Assert-ExactClientWindowBinding -Process $Process -ExpectedHwnd $receiptHwnd)
    $legacyLineage = Assert-ExactLegacyLaunchAuditLineage -Receipt $receipt
    Assert-ParentReceiptUnused -ParentReceiptNonce ([string]$receipt.receipt_nonce) -ParentReceiptSha256 ([string]$Snapshot.Sha256)
    return [pscustomobject]@{
        ExecutablePath = $metadata.ExecutablePath
        ProcessCreatedAtUtc = $metadata.ProcessCreatedAtUtc
        ProcessCreationFileTimeUtc = $metadata.ProcessCreationFileTimeUtc
        WindowsSessionId = $metadata.WindowsSessionId
        LegacyLaunchAuditFileSha256 = $legacyLineage.AuditFileSha256
        LegacyLaunchAuditEntrySha256 = $legacyLineage.AuditEntrySha256
    }
}

function Wait-ForLaunchedClientWindow {
    param([System.Diagnostics.Process]$LaunchedProcess)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $matches = @(Get-Process -Name Wow -ErrorAction SilentlyContinue)
        if ($matches.Count -gt 1) {
            throw 'More than one Wow.exe process appeared during launch; receipt refused.'
        }
        if ($matches.Count -eq 1 -and $matches[0].Id -ne $LaunchedProcess.Id) {
            throw 'Wow.exe PID differs from Start-Process -PassThru; receipt refused.'
        }
        if (-not $LaunchedProcess.HasExited) {
            $LaunchedProcess.Refresh()
            if ($LaunchedProcess.MainWindowHandle -ne [IntPtr]::Zero) {
                [void](Assert-ExactClientWindowBinding -Process $LaunchedProcess)
                return $LaunchedProcess
            }
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'The exact Start-Process client window did not become ready within the timeout.'
}

function Assert-ClientProcessIdentity {
    param([System.Diagnostics.Process]$Process)
    [void](Get-ExactClientProcessMetadata -Process $Process)
    [void](Assert-ExactClientWindowBinding -Process $Process)
}

function New-LabRuntimeArm {
    param([System.Diagnostics.Process]$Process)
    $receipt = Assert-LabLaunchReceipt -Process $Process
    $routing = Assert-ExactRealmRoutingRecord
    $issuedAt = [DateTimeOffset]::UtcNow
    $receiptExpiry = [DateTimeOffset]::Parse([string]$receipt.expires_at)
    $expiresAt = Get-BoundedExpiry -IssuedAt $issuedAt -AdditionalLimit $receiptExpiry
    $nonce = [Guid]::NewGuid().ToString('D')
    $arm = [ordered]@{
        record_type = 'lab_client_runtime_arm'
        schema_version = '0.1'
        arm_nonce = $nonce
        launch_receipt_nonce = [string]$receipt.receipt_nonce
        pid = $Process.Id
        hwnd = [string]$receipt.hwnd
        authorization_id = [string]$targetAuthorization.authorization_id
        authorization_sha256 = $authorizationSha256
        actor_binding = New-ExpectedActorBindingRecord
        target_profile = [string]$targetAuthorization.target_profile
        client_build = $expectedClientBuild
        build_signature = $expectedBuildSignature
        executable_path = [string]$receipt.executable_path
        executable_sha256 = $expectedClientSha256
        expected_realm_fingerprint = $expectedRealmFingerprint
        realm_assurance = New-LocalRealmAssuranceRecord -VerifiedAt $issuedAt -State 'local_process_config_revalidated_at_arm'
        realm_routing_sha256 = $routing.Sha256
        realmlist_relative_path = [string]$receipt.realmlist_relative_path
        realmlist_sha256 = [string]$receipt.realmlist_sha256
        realmlist_directive = [string]$receipt.realmlist_directive
        environment_scope = 'emulator_local'
        server_kind = 'emulator'
        decision_context = $decisionContext
        allowed_actions = @($inputActions)
        issued_at = $issuedAt.ToString('o')
        expires_at = $expiresAt.ToString('o')
        scope = 'lab_operator_bounded_input'
        execution_authority = $true
    }
    $json = $arm | ConvertTo-Json -Depth 5
    Assert-JsonSchema -Json $json -SchemaPath $runtimeArmSchemaPath -RecordName 'LAB runtime arm'
    Write-AtomicJsonRecord -Path $runtimeArmPath -Json $json -Nonce $nonce
    return [pscustomobject]$arm
}

function Assert-RuntimeArm {
    param([string]$Name, [System.Diagnostics.Process]$Process)
    Assert-ActiveTargetAuthorization
    if ($Name -notin $inputActions) {
        throw "Action $Name is not a finite allowlisted LAB input action."
    }
    Assert-LabReady
    $routing = Assert-ExactRealmRoutingRecord
    if (
        $targetAuthorization.environment_scope -ne 'emulator_local' -or
        $targetAuthorization.realm_match.server_kind -ne 'emulator' -or
        $targetAuthorization.realm_match.expected_realm_fingerprint -ne $expectedRealmFingerprint
    ) {
        throw 'Runtime arm realm scope no longer matches the exact LAB authorization.'
    }
    $armSnapshot = Read-ValidatedRuntimeArmSnapshot
    $arm = $armSnapshot.Record
    $issuedAt = [DateTimeOffset]::Parse([string]$arm.issued_at)
    $expiresAt = [DateTimeOffset]::Parse([string]$arm.expires_at)
    $now = [DateTimeOffset]::UtcNow
    if ($issuedAt -gt $now -or $expiresAt -le $now -or $expiresAt -le $issuedAt) {
        throw 'LAB runtime arm is expired or not yet valid.'
    }
    if (($expiresAt - $issuedAt).TotalMinutes -gt $maxSessionMinutes) {
        throw 'LAB runtime arm exceeds approval.max_session_minutes.'
    }
    $receipt = Assert-LabLaunchReceipt -Process $Process
    $receiptExpiry = [DateTimeOffset]::Parse([string]$receipt.expires_at)
    Assert-ExpectedActorBindingRecord -ActorBinding $arm.actor_binding
    Assert-LocalRealmAssuranceRecord -RealmAssurance $arm.realm_assurance -ExpectedState 'local_process_config_revalidated_at_arm' -NotBefore $issuedAt -NotAfter $now
    if (
        $expiresAt -gt $receiptExpiry -or
        $arm.launch_receipt_nonce -ne $receipt.receipt_nonce -or
        [int]$arm.pid -ne $Process.Id -or
        $arm.hwnd -ne $receipt.hwnd -or
        $arm.authorization_id -ne $targetAuthorization.authorization_id -or
        $arm.authorization_sha256 -ne $authorizationSha256 -or
        $arm.target_profile -ne $targetAuthorization.target_profile -or
        $arm.client_build -ne $expectedClientBuild -or
        $arm.build_signature -ne $expectedBuildSignature -or
        $arm.executable_sha256 -ne $expectedClientSha256 -or
        $arm.expected_realm_fingerprint -ne $expectedRealmFingerprint -or
        $arm.realm_routing_sha256 -ne $routing.Sha256 -or
        $arm.realmlist_relative_path -ne $receipt.realmlist_relative_path -or
        $arm.realmlist_sha256 -ne $receipt.realmlist_sha256 -or
        $arm.realmlist_directive -ne $receipt.realmlist_directive -or
        $arm.environment_scope -ne 'emulator_local' -or
        $arm.server_kind -ne 'emulator' -or
        $arm.decision_context -ne $decisionContext -or
        $arm.scope -ne 'lab_operator_bounded_input' -or
        $arm.execution_authority -ne $true -or
        $Name -notin @($arm.allowed_actions)
    ) {
        throw 'LAB runtime arm does not match this exact action, target, realm, or receipt.'
    }
    [void](Assert-ClientExecutableIdentity -Path ([string]$arm.executable_path))
    $remainingSeconds = ($expiresAt - $now).TotalSeconds
    $actionBudgetSeconds = [Math]::Min([double]$maxInputActionSeconds, $remainingSeconds)
    if ($actionBudgetSeconds -le 0) {
        throw 'LAB runtime arm has no remaining bounded input time.'
    }
    $armFileSha256 = [string]$armSnapshot.Sha256
    $script:activeInputLease = [pscustomobject]@{
        Action = $Name
        ArmNonce = [string]$arm.arm_nonce
        ArmFileSha256 = $armFileSha256
        ProcessId = $Process.Id
        Hwnd = ConvertFrom-HexHwnd -Value ([string]$arm.hwnd)
        ExpiresAt = $expiresAt
        ActionBudgetSeconds = $actionBudgetSeconds
        DeadlineTicks = [int64]0
    }
}

function Read-ValidatedRuntimeArmSnapshot {
    if (-not (Test-Path -LiteralPath $runtimeArmPath -PathType Leaf)) {
        throw 'No active LAB runtime arm; input is refused.'
    }
    try {
        $armBytes = [System.IO.File]::ReadAllBytes($runtimeArmPath)
        $armSha256 = Get-ByteArraySha256 -Bytes $armBytes
        $armJson = [System.Text.UTF8Encoding]::new($false, $true).GetString($armBytes)
        $armRecord = ConvertFrom-StrictJson -Json $armJson -RecordName 'LAB runtime arm'
        Assert-JsonSchema -Json $armJson -SchemaPath $runtimeArmSchemaPath -RecordName 'LAB runtime arm'
    }
    catch {
        throw "LAB runtime arm snapshot cannot be read and validated atomically: $($_.Exception.Message)"
    }
    return [pscustomobject]@{
        Record = $armRecord
        Sha256 = $armSha256
    }
}

function Assert-ActiveInputLease {
    param([System.Diagnostics.Process]$Process)
    $lease = $script:activeInputLease
    if ($null -eq $lease) {
        throw 'No active bounded input lease; input is refused.'
    }
    $now = [DateTimeOffset]::UtcNow
    $nowTicks = [System.Diagnostics.Stopwatch]::GetTimestamp()
    if ($now -ge $lease.ExpiresAt) {
        throw 'The bounded input lease expired before the next input token.'
    }
    if ([int64]$lease.DeadlineTicks -eq 0) {
        $remainingSeconds = ($lease.ExpiresAt - $now).TotalSeconds
        $leaseSeconds = [Math]::Min([double]$lease.ActionBudgetSeconds, $remainingSeconds)
        if ($leaseSeconds -le 0) {
            throw 'The bounded input lease has no remaining time.'
        }
        $lease.DeadlineTicks = $nowTicks + [int64]([Math]::Floor(
            $leaseSeconds * [System.Diagnostics.Stopwatch]::Frequency
        ))
    }
    if ($nowTicks -gt [int64]$lease.DeadlineTicks) {
        throw 'The bounded input lease expired before the next input token.'
    }
    $Process.Refresh()
    if (
        $Process.HasExited -or
        $Process.Id -ne [int]$lease.ProcessId -or
        $Process.MainWindowHandle.ToInt64() -ne [long]$lease.Hwnd
    ) {
        throw 'The bounded input lease no longer matches the exact client window.'
    }
    $currentArmSnapshot = Read-ValidatedRuntimeArmSnapshot
    $currentArmSha256 = [string]$currentArmSnapshot.Sha256
    if ($currentArmSha256 -ne [string]$lease.ArmFileSha256) {
        throw 'The LAB runtime arm changed during the input action.'
    }
    $currentArm = $currentArmSnapshot.Record
    if (
        [string]$currentArm.arm_nonce -ne [string]$lease.ArmNonce -or
        [DateTimeOffset]::Parse([string]$currentArm.expires_at) -ne $lease.ExpiresAt
    ) {
        throw 'The LAB runtime arm nonce or expiry changed during the input action.'
    }
}

function Get-ClientProcess {
    $process = Get-SingleWowProcess -AllowNone
    if ($null -eq $process) {
        return $null
    }
    Assert-ClientProcessIdentity -Process $process
    [void](Assert-LabLaunchReceipt -Process $process)
    return $process
}

function Wait-ForClientWindow {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $process = Get-ClientProcess
        if ($null -ne $process) {
            $process.Refresh()
            if ($process.MainWindowHandle -ne [IntPtr]::Zero -and $process.MainWindowTitle -eq 'World of Warcraft') {
                return $process
            }
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'World of Warcraft window did not become ready within the timeout.'
}

function Read-PreferredWindowProfile {
    if (-not (Test-Path -LiteralPath $preferredWindowProfilePath -PathType Leaf)) {
        throw "Preferred LAB client window profile is missing: $preferredWindowProfilePath"
    }
    $json = [System.IO.File]::ReadAllText($preferredWindowProfilePath, [System.Text.UTF8Encoding]::new($false, $true))
    $profile = ConvertFrom-StrictJson -Json $json -RecordName 'preferred LAB client window profile'
    if (
        $profile.record_type -ne 'lab_client_window_profile' -or
        $profile.schema_version -ne '0.1' -or
        $profile.auto_apply_on_launch -ne $true -or
        $profile.windowed -ne $true -or
        [int]$profile.render_resolution.width -lt 800 -or
        [int]$profile.render_resolution.width -gt 7680 -or
        [int]$profile.render_resolution.height -lt 600 -or
        [int]$profile.render_resolution.height -gt 4320 -or
        [int]$profile.render_resolution.refresh_hz -lt 30 -or
        [int]$profile.render_resolution.refresh_hz -gt 360 -or
        [int]$profile.outer_bounds.width -lt 800 -or
        [int]$profile.outer_bounds.width -gt 7680 -or
        [int]$profile.outer_bounds.height -lt 600 -or
        [int]$profile.outer_bounds.height -gt 4320
    ) {
        throw 'Preferred LAB client window profile is invalid or outside bounded display limits.'
    }
    return $profile
}

function Set-PreferredClientGraphicsConfig {
    param($Profile)
    $configPath = Join-Path $ClientRoot 'WTF\Config.wtf'
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        throw "World of Warcraft graphics config is missing: $configPath"
    }
    $settings = [ordered]@{
        # TBC remembers only the account name. Never put the password in the
        # client config; the existing, separately gated Login action reads it
        # from CredentialPath. This runs before Launch, while WoW is closed.
        accountName = $expectedAccount
        gxWindow = if ($Profile.windowed) { '1' } else { '0' }
        gxResolution = ('{0}x{1}' -f [int]$Profile.render_resolution.width, [int]$Profile.render_resolution.height)
        gxRefresh = ([int]$Profile.render_resolution.refresh_hz).ToString([System.Globalization.CultureInfo]::InvariantCulture)
    }
    $seen = @{}
    $output = [System.Collections.Generic.List[string]]::new()
    foreach ($line in [System.IO.File]::ReadAllLines($configPath)) {
        if ($line -match '^SET\s+([A-Za-z0-9_]+)\s+".*"\s*$' -and $settings.Contains($Matches[1])) {
            $name = $Matches[1]
            if (-not $seen.ContainsKey($name)) {
                [void]$output.Add(('SET {0} "{1}"' -f $name, $settings[$name]))
                $seen[$name] = $true
            }
            continue
        }
        [void]$output.Add($line)
    }
    foreach ($entry in $settings.GetEnumerator()) {
        if (-not $seen.ContainsKey([string]$entry.Key)) {
            [void]$output.Add(('SET {0} "{1}"' -f $entry.Key, $entry.Value))
        }
    }
    $temporaryPath = "$configPath.$([Guid]::NewGuid().ToString('N')).tmp"
    try {
        [System.IO.File]::WriteAllText(
            $temporaryPath,
            ([string]::Join("`r`n", $output) + "`r`n"),
            [System.Text.UTF8Encoding]::new($false)
        )
        Move-Item -LiteralPath $temporaryPath -Destination $configPath -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Set-PreferredWindowLayout {
    param(
        [System.Diagnostics.Process]$Process,
        $Profile
    )
    $expectedHandle = $Process.MainWindowHandle
    [void](Assert-ExactClientWindowBinding -Process $Process -ExpectedHwnd $expectedHandle.ToInt64())
    $left = [int]$Profile.outer_bounds.left
    $top = [int]$Profile.outer_bounds.top
    $width = [int]$Profile.outer_bounds.width
    $height = [int]$Profile.outer_bounds.height
    if (-not [PerfectAssassinLabClientNative]::MoveWindow(
        $expectedHandle,
        $left,
        $top,
        $width,
        $height,
        $true
    )) {
        throw 'Could not restore the preferred large LAB client window.'
    }
    Start-Sleep -Milliseconds 500
    [void](Assert-ExactClientWindowBinding -Process $Process -ExpectedHwnd $expectedHandle.ToInt64())
    $actual = Get-ClientRect -Process $Process
    if (
        $actual.Left -ne $left -or
        $actual.Top -ne $top -or
        ($actual.Right - $actual.Left) -ne $width -or
        ($actual.Bottom - $actual.Top) -ne $height
    ) {
        throw 'World of Warcraft did not retain the preferred large LAB client window bounds.'
    }
    return [pscustomobject]@{
        ProfileId = [string]$Profile.profile_id
        Left = $left
        Top = $top
        Width = $width
        Height = $height
    }
}

function Focus-Client {
    param(
        [System.Diagnostics.Process]$Process,
        [switch]$BoundToActiveInputLease
    )
    if ($BoundToActiveInputLease) {
        Assert-ActiveInputLease -Process $Process
        [void](Assert-ExactClientWindowBinding -Process $Process -ExpectedHwnd $Process.MainWindowHandle.ToInt64())
    }
    else {
        Assert-ClientProcessIdentity -Process $Process
    }
    if ($Process.MainWindowTitle -ne 'World of Warcraft') {
        throw 'Unexpected client window title; input refused.'
    }
    $focused = [PerfectAssassinLabClientNative]::SetForegroundWindow(
        $Process.MainWindowHandle
    )
    if (-not $focused) {
        # SetForegroundWindow is allowed to refuse a background caller even
        # after the exact PID/HWND identity checks above. AppActivate uses the
        # shell's normal foreground handoff; authority still remains bound to
        # the already verified WoW process and handle.
        $shell = New-Object -ComObject WScript.Shell
        [void]$shell.AppActivate($Process.Id)
        if (
            [PerfectAssassinLabClientNative]::GetForegroundWindow() -ne
            $Process.MainWindowHandle
        ) {
            $foreground = [PerfectAssassinLabClientNative]::GetForegroundWindow()
            $foregroundThread = [PerfectAssassinLabClientNative]::GetWindowThreadProcessId(
                $foreground, [IntPtr]::Zero
            )
            $targetThread = [PerfectAssassinLabClientNative]::GetWindowThreadProcessId(
                $Process.MainWindowHandle, [IntPtr]::Zero
            )
            $currentThread = [PerfectAssassinLabClientNative]::GetCurrentThreadId()
            $attachedForeground = $false
            $attachedTarget = $false
            try {
                if ($foregroundThread -ne 0 -and $foregroundThread -ne $currentThread) {
                    $attachedForeground = [PerfectAssassinLabClientNative]::AttachThreadInput(
                        $currentThread, $foregroundThread, $true
                    )
                }
                if (
                    $targetThread -ne 0 -and
                    $targetThread -ne $currentThread -and
                    $targetThread -ne $foregroundThread
                ) {
                    $attachedTarget = [PerfectAssassinLabClientNative]::AttachThreadInput(
                        $currentThread, $targetThread, $true
                    )
                }
                [void][PerfectAssassinLabClientNative]::ShowWindowAsync(
                    $Process.MainWindowHandle, 9
                )
                [void][PerfectAssassinLabClientNative]::BringWindowToTop(
                    $Process.MainWindowHandle
                )
                [void][PerfectAssassinLabClientNative]::SetForegroundWindow(
                    $Process.MainWindowHandle
                )
            }
            finally {
                if ($attachedTarget) {
                    [void][PerfectAssassinLabClientNative]::AttachThreadInput(
                        $currentThread, $targetThread, $false
                    )
                }
                if ($attachedForeground) {
                    [void][PerfectAssassinLabClientNative]::AttachThreadInput(
                        $currentThread, $foregroundThread, $false
                    )
                }
            }
        }
    }
    Start-Sleep -Milliseconds 100
    if ([PerfectAssassinLabClientNative]::GetForegroundWindow() -ne $Process.MainWindowHandle) {
        throw 'World of Warcraft is not the foreground window; input is refused.'
    }
}

function Send-ClientAtomicToken {
    param(
        [System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)]
        [string]$Token
    )
    Assert-ActiveInputLease -Process $Process
    Focus-Client -Process $Process -BoundToActiveInputLease
    [void](Assert-ExactClientWindowBinding -Process $Process -ExpectedHwnd $Process.MainWindowHandle.ToInt64())
    Assert-ActiveInputLease -Process $Process
    if ([PerfectAssassinLabClientNative]::GetForegroundWindow() -ne $Process.MainWindowHandle) {
        throw 'Client focus changed immediately before keyboard input; input is refused.'
    }
    [System.Windows.Forms.SendKeys]::SendWait($Token)
    $Process.Refresh()
    Assert-ActiveInputLease -Process $Process
    if (
        $Process.HasExited -or
        [PerfectAssassinLabClientNative]::GetForegroundWindow() -ne $Process.MainWindowHandle
    ) {
        throw 'Client focus changed during keyboard input; remaining input is refused.'
    }
}

function Send-ClientKeys {
    param(
        [System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)]
        [ValidateSet('{ENTER}', '{ESC}', '^a', 'm', 'v', '%{F4}', '%{F9}', '%{F10}')]
        [string]$Keys
    )
    Send-ClientAtomicToken -Process $Process -Token $Keys
}

function Send-ClientText {
    param(
        [System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)]
        [string]$Text
    )
    if (
        $Text.Length -eq 0 -or
        $Text.Length -gt $maxClientTextLength -or
        $Text.IndexOfAny([char[]]@(0..31 + 127)) -ge 0
    ) {
        throw 'Client text is empty or contains unsupported control characters.'
    }
    foreach ($character in $Text.ToCharArray()) {
        $token = ConvertTo-SendKeysLiteral -Value ([string]$character)
        Send-ClientAtomicToken -Process $Process -Token $token
    }
}

function Set-ExplicitUiScale {
    param(
        [System.Diagnostics.Process]$Process,
        [ValidateSet('0.8', '1.0')]
        [string]$Scale
    )
    Focus-Client -Process $Process -BoundToActiveInputLease
    $before = Save-ClientCheckpoint -Process $Process -Label "before-ui-scale-$($Scale.Replace('.', ''))"
    $commands = @('/console useUiScale 1', "/console uiScale $Scale")
    foreach ($command in $commands) {
        Send-ClientKeys -Process $Process -Keys '{ENTER}'
        Send-ClientText -Process $Process -Text $command
        Send-ClientKeys -Process $Process -Keys '{ENTER}'
        Start-Sleep -Milliseconds 250
    }
    Start-Sleep -Seconds 2
    $after = Save-ClientCheckpoint -Process $Process -Label "after-ui-scale-$($Scale.Replace('.', ''))"
    return [pscustomobject]@{ Before = $before; After = $after; Scale = $Scale }
}

function Restore-DefaultUiScale {
    param([System.Diagnostics.Process]$Process)
    Focus-Client -Process $Process
    $before = Save-ClientCheckpoint -Process $Process -Label 'before-ui-scale-default'
    Send-ClientKeys -Process $Process -Keys '{ENTER}'
    Send-ClientText -Process $Process -Text '/console useUiScale 0'
    Send-ClientKeys -Process $Process -Keys '{ENTER}'
    Start-Sleep -Seconds 2
    $after = Save-ClientCheckpoint -Process $Process -Label 'after-ui-scale-default'
    return [pscustomobject]@{ Before = $before; After = $after }
}

function Set-ExplicitWindowSize {
    param(
        [System.Diagnostics.Process]$Process,
        [ValidateSet('compact', 'baseline')]
        [string]$Profile
    )
    $expectedHandle = $Process.MainWindowHandle
    Focus-Client -Process $Process
    $rect = Get-ClientRect -Process $Process
    $preferredWindowProfile = if ($Profile -eq 'baseline') { Read-PreferredWindowProfile } else { $null }
    $width = if ($Profile -eq 'compact') { 1100 } else { [int]$preferredWindowProfile.outer_bounds.width }
    $height = if ($Profile -eq 'compact') { 850 } else { [int]$preferredWindowProfile.outer_bounds.height }
    $before = Save-ClientCheckpoint -Process $Process -Label "before-window-$Profile"
    Assert-ActiveInputLease -Process $Process
    [void](Assert-ExactClientWindowBinding -Process $Process -ExpectedHwnd $expectedHandle.ToInt64())
    Focus-Client -Process $Process
    Assert-ActiveInputLease -Process $Process
    if ([PerfectAssassinLabClientNative]::GetForegroundWindow() -ne $expectedHandle) {
        throw 'Client focus changed immediately before the bounded window resize.'
    }
    if (-not [PerfectAssassinLabClientNative]::MoveWindow(
        $expectedHandle,
        $rect.Left,
        $rect.Top,
        $width,
        $height,
        $true
    )) {
        throw "Could not apply the bounded $Profile LAB window profile."
    }
    Assert-ActiveInputLease -Process $Process
    [void](Assert-ExactClientWindowBinding -Process $Process -ExpectedHwnd $expectedHandle.ToInt64())
    Start-Sleep -Seconds 2
    $after = Save-ClientCheckpoint -Process $Process -Label "after-window-$Profile"
    return [pscustomobject]@{
        Before = $before
        After = $after
        Profile = $Profile
        RequestedOuterWidth = $width
        RequestedOuterHeight = $height
    }
}

function Get-ClientRect {
    param([System.Diagnostics.Process]$Process)
    $rect = New-Object PerfectAssassinLabClientNative+RECT
    if (-not [PerfectAssassinLabClientNative]::GetWindowRect($Process.MainWindowHandle, [ref]$rect)) {
        throw 'Could not read the World of Warcraft window rectangle.'
    }
    return $rect
}

function Save-ClientCheckpoint {
    param([System.Diagnostics.Process]$Process, [string]$Label)
    $expectedHandle = $Process.MainWindowHandle
    Focus-Client -Process $Process
    [void](Assert-ExactClientWindowBinding -Process $Process -ExpectedHwnd $expectedHandle.ToInt64())
    $rect = Get-ClientRect -Process $Process
    $width = $rect.Right - $rect.Left
    $height = $rect.Bottom - $rect.Top
    if ($width -lt 800 -or $height -lt 600) {
        throw 'Client window is too small for a trustworthy visual checkpoint.'
    }
    New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
    $path = Join-Path $runtimeRoot ("{0}-{1}.png" -f [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'), $Label)
    $bitmap = New-Object System.Drawing.Bitmap $width, $height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        if ([PerfectAssassinLabClientNative]::GetForegroundWindow() -ne $expectedHandle) {
            throw 'Client checkpoint refused because the exact window is not foreground.'
        }
        $verifiedRect = Get-ClientRect -Process $Process
        if (
            $verifiedRect.Left -ne $rect.Left -or
            $verifiedRect.Top -ne $rect.Top -or
            $verifiedRect.Right -ne $rect.Right -or
            $verifiedRect.Bottom -ne $rect.Bottom
        ) {
            throw 'Client checkpoint refused because the window rectangle changed before capture.'
        }
        $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
        [void](Assert-ExactClientWindowBinding -Process $Process -ExpectedHwnd $expectedHandle.ToInt64())
        if ([PerfectAssassinLabClientNative]::GetForegroundWindow() -ne $expectedHandle) {
            throw 'Client checkpoint refused because focus changed during capture.'
        }
        $afterRect = Get-ClientRect -Process $Process
        if (
            $afterRect.Left -ne $rect.Left -or
            $afterRect.Top -ne $rect.Top -or
            $afterRect.Right -ne $rect.Right -or
            $afterRect.Bottom -ne $rect.Bottom
        ) {
            throw 'Client checkpoint refused because the window rectangle changed during capture.'
        }
        $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
    return $path
}

function Click-ClientRelative {
    param([System.Diagnostics.Process]$Process, [double]$X, [double]$Y)
    if ($X -lt 0 -or $X -gt 1 -or $Y -lt 0 -or $Y -gt 1) {
        throw 'Relative click coordinate is outside the client window.'
    }
    $expectedHandle = $Process.MainWindowHandle
    Focus-Client -Process $Process -BoundToActiveInputLease
    $rect = Get-ClientRect -Process $Process
    $screenX = $rect.Left + [int](($rect.Right - $rect.Left) * $X)
    $screenY = $rect.Top + [int](($rect.Bottom - $rect.Top) * $Y)
    if (-not [PerfectAssassinLabClientNative]::SetCursorPos($screenX, $screenY)) {
        throw 'Could not position the cursor inside the verified client window; input is refused.'
    }
    Start-Sleep -Milliseconds 100
    Assert-ActiveInputLease -Process $Process
    $Process.Refresh()
    if ($Process.HasExited -or $Process.MainWindowHandle -ne $expectedHandle) {
        throw 'Client window identity changed immediately before mouse input; input is refused.'
    }
    $verifiedRect = Get-ClientRect -Process $Process
    if (
        $verifiedRect.Left -ne $rect.Left -or
        $verifiedRect.Top -ne $rect.Top -or
        $verifiedRect.Right -ne $rect.Right -or
        $verifiedRect.Bottom -ne $rect.Bottom
    ) {
        throw 'Client window rectangle changed immediately before mouse input; input is refused.'
    }
    $cursor = New-Object PerfectAssassinLabClientNative+POINT
    if (-not [PerfectAssassinLabClientNative]::GetCursorPos([ref]$cursor)) {
        throw 'Could not verify the cursor position immediately before mouse input; input is refused.'
    }
    if ($cursor.X -ne $screenX -or $cursor.Y -ne $screenY) {
        throw 'Cursor position changed immediately before mouse input; input is refused.'
    }
    if ([PerfectAssassinLabClientNative]::GetForegroundWindow() -ne $expectedHandle) {
        throw 'Client focus changed immediately before mouse input; input is refused.'
    }
    [PerfectAssassinLabClientNative]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    [PerfectAssassinLabClientNative]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    Assert-ActiveInputLease -Process $Process
}

function ConvertTo-SendKeysLiteral {
    param([string]$Value)
    $builder = [System.Text.StringBuilder]::new()
    foreach ($character in $Value.ToCharArray()) {
        $escaped = switch ($character) {
            '+' { '{+}' }
            '^' { '{^}' }
            '%' { '{%}' }
            '~' { '{~}' }
            '(' { '{(}' }
            ')' { '{)}' }
            '{' { '{{}' }
            '}' { '{}}' }
            '[' { '{[}' }
            ']' { '{]}' }
            default { [string]$character }
        }
        [void]$builder.Append($escaped)
    }
    return $builder.ToString()
}

function Get-LabLaunchIdentityStatus {
    param([System.Diagnostics.Process[]]$Processes)
    $status = [ordered]@{
        state = 'missing'
        schema_version = $null
        receipt_nonce = $null
        identity_origin = $null
        expired = $null
        expires_at = $null
        identity_verified = $false
        observed_pid_matches_receipt = $false
        verification = 'not_performed_status_is_non_authoritative'
        detail = $null
    }
    if (-not (Test-Path -LiteralPath $launchReceiptPath -PathType Leaf)) {
        return [pscustomobject]$status
    }
    try {
        $snapshot = Read-LabLaunchReceiptSnapshot -AllowLegacyV01
        $receipt = $snapshot.Record
        $createdAt = [DateTimeOffset]::Parse([string]$receipt.created_at)
        $expiresAt = [DateTimeOffset]::Parse([string]$receipt.expires_at)
        $now = [DateTimeOffset]::UtcNow
        if ($createdAt -gt $now -or $expiresAt -le $createdAt) {
            throw 'receipt issuance interval is invalid'
        }
        $expired = $expiresAt -le $now
        $observedPidMatches = (
            $Processes.Count -eq 1 -and
            [int]$receipt.pid -eq $Processes[0].Id
        )
        $status.state = if ($receipt.schema_version -eq '0.1') {
            if ($expired) { 'unverified_legacy_v0_1_expired' } else { 'unverified_legacy_v0_1_present' }
        }
        elseif ($expired) {
            'unverified_v1_expired'
        }
        else {
            'unverified_v1_present'
        }
        $status.schema_version = [string]$receipt.schema_version
        $status.receipt_nonce = [string]$receipt.receipt_nonce
        $status.identity_origin = if ($receipt.schema_version -eq '1.0') { [string]$receipt.identity_origin } else { 'legacy_v0_1' }
        $status.expired = $expired
        $status.expires_at = $expiresAt.ToString('o')
        $status.observed_pid_matches_receipt = $observedPidMatches
    }
    catch {
        $status.state = 'malformed_or_untrusted'
        $status.detail = $_.Exception.Message
    }
    return [pscustomobject]$status
}

function Read-ObserverCredential {
    if (-not (Test-Path -LiteralPath $CredentialPath -PathType Leaf)) {
        throw "Observer credential file is missing: $CredentialPath"
    }
    $credentialJson = Get-Content -LiteralPath $CredentialPath -Raw
    $credential = ConvertFrom-StrictJson -Json $credentialJson -RecordName 'Observer credential'
    $account = if ($credential.username) { [string]$credential.username } elseif ($credential.account) { [string]$credential.account } else { '' }
    $password = if ($credential.password) { [string]$credential.password } else { '' }
    if (
        $account -ne $expectedAccount -or
        $account.Length -gt $maxObserverAccountLength -or
        [string]::IsNullOrWhiteSpace($password) -or
        $password.Length -gt $maxObserverPasswordLength
    ) {
        throw 'Observer credential does not match the expected account or has no password.'
    }
    if ($account -match '[\x00-\x1F\x7F]' -or $password -match '[\x00-\x1F\x7F]') {
        throw 'Observer credential contains unsupported control characters.'
    }
    return [pscustomobject]@{ Account = $account; Password = $password }
}

function Assert-NvidiaOperatorLaunch {
    param([System.Diagnostics.Process]$Process)
    $wowRecord = Get-CimInstance Win32_Process -Filter "ProcessId=$($Process.Id)" -ErrorAction Stop
    if ($null -eq $wowRecord -or [int]$wowRecord.ParentProcessId -le 0) {
        throw 'The running LAB client has no verifiable launcher parent.'
    }
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($wowRecord.ParentProcessId)" -ErrorAction Stop
    $expectedPath = 'C:\Program Files\NVIDIA Corporation\NVIDIA app\CEF\NVIDIA App.exe'
    if (
        $null -eq $parent -or
        [string]$parent.Name -ne 'NVIDIA App.exe' -or
        -not [System.StringComparer]::OrdinalIgnoreCase.Equals([string]$parent.ExecutablePath, $expectedPath)
    ) {
        throw 'BindOperatorLaunch accepts only a client whose live parent is the exact NVIDIA App launcher.'
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $expectedPath
    if (
        $signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid -or
        [string]$signature.SignerCertificate.Subject -notmatch 'NVIDIA'
    ) {
        throw 'The NVIDIA App launcher signature is not valid for NVIDIA.'
    }
    $wowCreatedAt = [DateTimeOffset]$wowRecord.CreationDate
    $parentCreatedAt = [DateTimeOffset]$parent.CreationDate
    if ($parentCreatedAt -gt $wowCreatedAt -or ($wowCreatedAt - $parentCreatedAt).TotalMinutes -gt 30) {
        throw 'The NVIDIA parent timing does not prove this bounded operator launch.'
    }
    return [pscustomobject]@{
        ParentPid = [int]$parent.ProcessId
        ParentPath = $expectedPath
        ParentSha256 = (Get-FileHash -LiteralPath $expectedPath -Algorithm SHA256).Hash
    }
}

try {
    switch ($Action) {
        'Status' {
            # Status is observational: an expired or malformed identity is reported,
            # never promoted and never allowed to turn status into an input action.
            $processes = @(Get-Process -Name Wow -ErrorAction SilentlyContinue)
            $process = if ($processes.Count -eq 1) { $processes[0] } else { $null }
            $identityStatus = Get-LabLaunchIdentityStatus -Processes $processes
            $status = [ordered]@{
                client_exists = Test-Path -LiteralPath $clientExecutable -PathType Leaf
                client_running = $null -ne $process
                client_pid = if ($process) { $process.Id } else { $null }
                client_process_count = $processes.Count
                authorization = [ordered]@{
                    state = $authorizationTemporalState
                    recorded_at = [string]$targetAuthorization.approval.recorded_at
                    expires_at = if ($null -ne $configuredAuthorizationExpiresAt) {
                        $configuredAuthorizationExpiresAt.ToString('o')
                    }
                    else {
                        $null
                    }
                    effective_expires_at = if ($null -ne $authorizationExpiresAt) {
                        $authorizationExpiresAt.ToString('o')
                    }
                    else {
                        $null
                    }
                    expiry_source = if ($authorizationHasExplicitExpiry) {
                        'explicit_expires_at'
                    }
                    else {
                        'derived_recorded_at_plus_max_session_minutes'
                    }
                    detail = $authorizationTemporalDetail
                    authorization_sha256 = $authorizationSha256
                    semantic_sha256 = $authorizationSemanticSha256
                }
                launch_receipt_present = Test-Path -LiteralPath $launchReceiptPath -PathType Leaf
                launch_identity = $identityStatus
                runtime_arm_present = Test-Path -LiteralPath $runtimeArmPath -PathType Leaf
                listeners = @(Get-LabListenerStatus)
                predator_execution_mode = 'OBSERVE_ONLY'
            }
            Write-OperatorObservationSafely -Name $Action -Result 'complete'
            $status | ConvertTo-Json -Depth 4
        }
        'Launch' {
            Assert-ActiveTargetAuthorization
            Assert-LabReady
            Assert-LocalInteractiveSession
            if (-not $AcknowledgeClientRisk) {
                throw 'Launch requires -AcknowledgeClientRisk because this legacy client has non-canonical provenance.'
            }
            $canonicalClientPath = Assert-ClientExecutableIdentity -Path $clientExecutable
            $identityLock = Enter-LabIdentityMutationLock
            try {
                $process = Get-SingleWowProcess -AllowNone
                if ($null -ne $process) {
                    $recovery = Complete-CommittedIdentityProjection -Process $process
                    if ($recovery.Recovered -and $recovery.Action -eq 'Launch') {
                        Write-OperatorObservationSafely -Name $Action -Result 'recovered_commit' -Details @{
                            pid = $process.Id
                            new_receipt_nonce = $recovery.Receipt.receipt_nonce
                            receipt_sha256 = $recovery.ReceiptSha256
                            input_tokens_sent = 0
                        }
                        Write-Output "LAB_SESSION_IDENTITY_EXPIRES=$($recovery.Receipt.expires_at)"
                        break
                    }
                    throw 'Wow.exe is already running.'
                }
                Remove-LabRuntimeArm
                Remove-LabLaunchReceipt
                $preferredWindowProfile = Read-PreferredWindowProfile
                Set-PreferredClientGraphicsConfig -Profile $preferredWindowProfile
                $launchedProcess = Start-Process -FilePath $canonicalClientPath -WorkingDirectory $ClientRoot -PassThru
                $process = Wait-ForLaunchedClientWindow -LaunchedProcess $launchedProcess
                Start-Sleep -Milliseconds 1000
                $windowLayout = Set-PreferredWindowLayout -Process $process -Profile $preferredWindowProfile
                $receipt = New-LabLaunchReceipt -Process $process -CanonicalExecutablePath $canonicalClientPath
                $checkpoint = $null
                try {
                    $checkpoint = Save-ClientCheckpoint -Process $process -Label 'launch'
                }
                catch {
                    Write-Warning "Post-commit launch checkpoint was unavailable: $($_.Exception.Message)"
                }
                Write-OperatorObservationSafely -Name $Action -Result 'complete' -Details @{
                    checkpoint = $checkpoint
                    pid = $process.Id
                    hwnd = $receipt.hwnd
                    launch_receipt_nonce = $receipt.receipt_nonce
                    receipt_expires_at = $receipt.expires_at
                    receipt_sha256 = $receipt.ReceiptSha256
                    new_authorization_sha256 = $authorizationSha256
                    new_authorization_semantic_sha256 = $authorizationSemanticSha256
                    identity_origin = $receipt.identity_origin
                    preferred_window_profile = $windowLayout
                }
                if ($null -ne $checkpoint) {
                    Write-Output "LAB_CLIENT_CHECKPOINT=$checkpoint"
                }
                Write-Output "LAB_SESSION_IDENTITY_EXPIRES=$($receipt.expires_at)"
            }
            finally {
                if ($null -ne $identityLock) {
                    $identityLock.Dispose()
                }
            }
        }
        'BindOperatorLaunch' {
            if (-not $AcknowledgeClientRisk -or -not $AcknowledgeSessionIdentity) {
                throw 'BindOperatorLaunch requires -AcknowledgeClientRisk and -AcknowledgeSessionIdentity.'
            }
            Assert-ActiveTargetAuthorization
            Assert-LabReady
            Assert-LocalInteractiveSession
            $canonicalClientPath = Assert-ClientExecutableIdentity -Path $clientExecutable
            $identityLock = Enter-LabIdentityMutationLock
            try {
                $process = Get-SingleWowProcess
                Assert-ClientProcessIdentity -Process $process
                $launcher = Assert-NvidiaOperatorLaunch -Process $process
                Remove-LabRuntimeArm
                Remove-LabLaunchReceipt
                $receipt = New-LabLaunchReceipt -Process $process -CanonicalExecutablePath $canonicalClientPath
                $checkpoint = Save-ClientCheckpoint -Process $process -Label 'bind-operator-launch'
                Write-OperatorObservationSafely -Name $Action -Result 'complete' -Details @{
                    checkpoint = $checkpoint
                    pid = $process.Id
                    hwnd = $receipt.hwnd
                    launch_receipt_nonce = $receipt.receipt_nonce
                    receipt_expires_at = $receipt.expires_at
                    receipt_sha256 = $receipt.ReceiptSha256
                    identity_origin = $receipt.identity_origin
                    launcher = 'NVIDIA App'
                    launcher_pid = $launcher.ParentPid
                    launcher_path = $launcher.ParentPath
                    launcher_sha256 = $launcher.ParentSha256
                    input_tokens_sent = 0
                }
                Write-Output "LAB_CLIENT_CHECKPOINT=$checkpoint"
                Write-Output "LAB_SESSION_IDENTITY_EXPIRES=$($receipt.expires_at)"
            }
            finally {
                if ($null -ne $identityLock) {
                    $identityLock.Dispose()
                }
            }
        }
        'AdoptSession' {
            if (-not $AcknowledgeSessionIdentity) {
                throw 'AdoptSession requires -AcknowledgeSessionIdentity for one-time legacy continuity adoption.'
            }
            Assert-ActiveTargetAuthorization
            $identityLock = Enter-LabIdentityMutationLock
            try {
                $process = Get-SingleWowProcess
                $recovery = Complete-CommittedIdentityProjection -Process $process
                if ($recovery.Recovered -and $recovery.Action -eq 'AdoptSession') {
                    Write-OperatorObservationSafely -Name $Action -Result 'recovered_commit' -Details @{
                        pid = $process.Id
                        new_receipt_nonce = $recovery.Receipt.receipt_nonce
                        receipt_sha256 = $recovery.ReceiptSha256
                        input_tokens_sent = 0
                    }
                    Write-Output "LAB_SESSION_IDENTITY_EXPIRES=$($recovery.Receipt.expires_at)"
                    break
                }
                $snapshot = Read-LabLaunchReceiptSnapshot -AllowLegacyV01
                if ($snapshot.Record.schema_version -ne '0.1') {
                    throw 'AdoptSession accepts only the one-time legacy v0.1 continuity path.'
                }
                $metadata = Assert-ExactLegacyV01Continuity -Process $process -Snapshot $snapshot
                $unchangedSnapshot = Read-LabLaunchReceiptSnapshot -AllowLegacyV01
                if (
                    $unchangedSnapshot.Record.schema_version -ne '0.1' -or
                    $unchangedSnapshot.Sha256 -ne $snapshot.Sha256
                ) {
                    throw 'Legacy receipt changed during continuity verification.'
                }
                $stillRunning = Get-SingleWowProcess
                if ($stillRunning.Id -ne $process.Id) {
                    throw 'Running client changed during legacy continuity verification.'
                }
                $receipt = New-LabLaunchReceipt `
                    -Process $process `
                    -CanonicalExecutablePath $metadata.ExecutablePath `
                    -IdentityOrigin 'legacy_v0_1_continuity_adoption' `
                    -ParentReceiptNonce ([string]$snapshot.Record.receipt_nonce) `
                    -ParentReceiptSha256 ([string]$snapshot.Sha256) `
                    -ParentAuthorizationSha256 ([string]$snapshot.Record.authorization_sha256) `
                    -LegacyLaunchAuditFileSha256 ([string]$metadata.LegacyLaunchAuditFileSha256) `
                    -LegacyLaunchAuditEntrySha256 ([string]$metadata.LegacyLaunchAuditEntrySha256)
                $writtenSha256 = Get-ByteArraySha256 -Bytes ([System.IO.File]::ReadAllBytes($launchReceiptPath))
                if ($writtenSha256 -ne $receipt.ReceiptSha256) {
                    Remove-LabLaunchReceipt
                    throw 'Atomic adopted identity receipt verification failed.'
                }
                Write-OperatorObservationSafely -Name $Action -Result 'complete' -Details @{
                    pid = $process.Id
                    hwnd = $receipt.hwnd
                    parent_receipt_nonce = [string]$snapshot.Record.receipt_nonce
                    parent_receipt_sha256 = [string]$snapshot.Sha256
                    parent_authorization_sha256 = [string]$snapshot.Record.authorization_sha256
                    new_receipt_nonce = $receipt.receipt_nonce
                    receipt_sha256 = $receipt.ReceiptSha256
                    new_authorization_sha256 = $authorizationSha256
                    new_authorization_semantic_sha256 = $authorizationSemanticSha256
                    identity_origin = $receipt.identity_origin
                    expires_at = $receipt.expires_at
                    input_tokens_sent = 0
                }
                Write-Output "LAB_SESSION_IDENTITY_EXPIRES=$($receipt.expires_at)"
            }
            finally {
                if ($null -ne $identityLock) {
                    $identityLock.Dispose()
                }
            }
        }
        'RenewSessionIdentity' {
            if (-not $AcknowledgeSessionIdentity) {
                throw 'RenewSessionIdentity requires -AcknowledgeSessionIdentity for zero-input identity renewal.'
            }
            Assert-ActiveTargetAuthorization
            $identityLock = Enter-LabIdentityMutationLock
            try {
                $process = Get-SingleWowProcess
                $recovery = Complete-CommittedIdentityProjection -Process $process
                if ($recovery.Recovered -and $recovery.Action -eq 'RenewSessionIdentity') {
                    Write-OperatorObservationSafely -Name $Action -Result 'recovered_commit' -Details @{
                        pid = $process.Id
                        new_receipt_nonce = $recovery.Receipt.receipt_nonce
                        receipt_sha256 = $recovery.ReceiptSha256
                        input_tokens_sent = 0
                    }
                    Write-Output "LAB_SESSION_IDENTITY_EXPIRES=$($recovery.Receipt.expires_at)"
                    break
                }
                $snapshot = Read-LabLaunchReceiptSnapshot
                $receiptRecord = if ($AcknowledgeAuthorizationRebind) {
                    Assert-LabLaunchReceiptSnapshot `
                        -Snapshot $snapshot `
                        -Process $process `
                        -AllowExpired `
                        -AllowWindowRebind:$AcknowledgeWindowRebind `
                        -AllowAuthorizationRebind
                }
                elseif ($AcknowledgeWindowRebind) {
                    Assert-LabLaunchReceiptSnapshot `
                        -Snapshot $snapshot `
                        -Process $process `
                        -AllowExpired `
                        -AllowWindowRebind
                }
                else {
                    Assert-LabLaunchReceipt -Process $process -AllowExpired
                }
                if ($receiptRecord.receipt_nonce -ne $snapshot.Record.receipt_nonce) {
                    throw 'LAB receipt changed during identity renewal verification.'
                }
                $unchangedSnapshot = Read-LabLaunchReceiptSnapshot
                if ($unchangedSnapshot.Sha256 -ne $snapshot.Sha256) {
                    throw 'LAB receipt bytes changed during identity renewal verification.'
                }
                Assert-ParentReceiptUnused `
                    -ParentReceiptNonce ([string]$snapshot.Record.receipt_nonce) `
                    -ParentReceiptSha256 ([string]$snapshot.Sha256)
                $metadata = Get-ExactClientProcessMetadata -Process $process
                $stillRunning = Get-SingleWowProcess
                if ($stillRunning.Id -ne $process.Id) {
                    throw 'Running client changed during identity renewal verification.'
                }
                $receipt = New-LabLaunchReceipt `
                    -Process $process `
                    -CanonicalExecutablePath $metadata.ExecutablePath `
                    -IdentityOrigin 'verified_receipt_renewal' `
                    -ParentReceiptNonce ([string]$snapshot.Record.receipt_nonce) `
                    -ParentReceiptSha256 ([string]$snapshot.Sha256) `
                    -ParentAuthorizationSha256 ([string]$snapshot.Record.authorization_sha256)
                $writtenSha256 = Get-ByteArraySha256 -Bytes ([System.IO.File]::ReadAllBytes($launchReceiptPath))
                if ($writtenSha256 -ne $receipt.ReceiptSha256) {
                    Remove-LabLaunchReceipt
                    throw 'Atomic renewed identity receipt verification failed.'
                }
                Write-OperatorObservationSafely -Name $Action -Result 'complete' -Details @{
                    pid = $process.Id
                    hwnd = $receipt.hwnd
                    parent_receipt_nonce = [string]$snapshot.Record.receipt_nonce
                    parent_receipt_sha256 = [string]$snapshot.Sha256
                    parent_authorization_sha256 = [string]$snapshot.Record.authorization_sha256
                    new_receipt_nonce = $receipt.receipt_nonce
                    receipt_sha256 = $receipt.ReceiptSha256
                    new_authorization_sha256 = $authorizationSha256
                    new_authorization_semantic_sha256 = $authorizationSemanticSha256
                    identity_origin = $receipt.identity_origin
                    window_rebound = [bool]$AcknowledgeWindowRebind
                    authorization_rebound = [bool]$AcknowledgeAuthorizationRebind
                    expires_at = $receipt.expires_at
                    input_tokens_sent = 0
                }
                Write-Output "LAB_SESSION_IDENTITY_EXPIRES=$($receipt.expires_at)"
            }
            finally {
                if ($null -ne $identityLock) {
                    $identityLock.Dispose()
                }
            }
        }
        'IssueMovementRealmRevalidation' {
            Assert-ActiveTargetAuthorization
            $movementAuthorization = Read-ActiveMovementAuthorization
            $process = Wait-ForClientWindow
            Assert-LabReady
            $realm = Assert-ExactLabRealm
            $routing = Assert-ExactRealmRoutingRecord
            Assert-ClientProcessIdentity -Process $process
            $receiptSnapshot = Read-LabLaunchReceiptSnapshot
            $receipt = Assert-LabLaunchReceiptSnapshot -Snapshot $receiptSnapshot -Process $process
            $unchangedReceipt = Read-LabLaunchReceiptSnapshot
            if ($unchangedReceipt.Sha256 -ne $receiptSnapshot.Sha256) {
                throw 'Session receipt changed during movement realm revalidation.'
            }
            $observedAt = [DateTimeOffset]::UtcNow
            $expiresAt = $observedAt.AddSeconds(30)
            $receiptExpiresAt = [DateTimeOffset]::Parse([string]$receipt.expires_at)
            if ($movementAuthorization.ExpiresAt -lt $expiresAt) {
                $expiresAt = $movementAuthorization.ExpiresAt
            }
            if ($receiptExpiresAt -lt $expiresAt) {
                $expiresAt = $receiptExpiresAt
            }
            if ($expiresAt -le $observedAt.AddMilliseconds(150)) {
                throw 'Movement realm revalidation has insufficient remaining time.'
            }
            $canonicalUtcFormat = "yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'"
            $observedAtCanonical = $observedAt.UtcDateTime.ToString(
                $canonicalUtcFormat,
                [System.Globalization.CultureInfo]::InvariantCulture
            )
            $expiresAtCanonical = $expiresAt.UtcDateTime.ToString(
                $canonicalUtcFormat,
                [System.Globalization.CultureInfo]::InvariantCulture
            )
            $nonce = [Guid]::NewGuid().ToString('D')
            $movement = $movementAuthorization.Record
            $record = [ordered]@{
                record_type = 'local_realm_revalidation_receipt'
                schema_version = '0.1'
                issuer_id = 'perfect_assassin.local_realm_revalidator'
                revalidation_nonce = $nonce
                authorization_id = [string]$movement.authorization_id
                authorization_sha256 = [string]$movementAuthorization.Sha256
                session_receipt_nonce = [string]$receipt.receipt_nonce
                session_receipt_sha256 = [string]$receiptSnapshot.Sha256
                target_profile = [string]$movement.target_profile
                actor_id = [string]$movement.actor_binding.actor_id
                actor_instance_id = [string]$movement.actor_binding.instance_id
                pid = [int]$receipt.pid
                hwnd = [string]$receipt.hwnd
                process_created_at_utc = [string]$receipt.process_created_at_utc
                process_creation_filetime_utc = [string]$receipt.process_creation_filetime_utc
                windows_session_id = [int]$receipt.windows_session_id
                executable_path = [string]$receipt.executable_path
                executable_sha256 = [string]$receipt.executable_sha256
                environment_scope = 'emulator_local'
                server_kind = 'emulator'
                expected_realm_fingerprint = [string]$receipt.expected_realm_fingerprint
                realm_routing_sha256 = [string]$routing.Sha256
                realmlist_relative_path = [string]$realm.RelativePath
                realmlist_sha256 = [string]$realm.Sha256
                realmlist_directive = [string]$realm.Directive
                method = 'exact_realmlist_listener_process_config_and_realm_route'
                observed_at = $observedAtCanonical
                expires_at = $expiresAtCanonical
                scope = 'lab_evaluation_only'
                execution_authority = $false
            }
            $json = $record | ConvertTo-Json -Depth 8
            Write-AtomicJsonRecord -Path $movementRevalidationPath -Json $json -Nonce $nonce
            $writtenBytes = [System.IO.File]::ReadAllBytes($movementRevalidationPath)
            $writtenSha256 = Get-ByteArraySha256 -Bytes $writtenBytes
            Write-OperatorAudit -Name $Action -Result 'complete' -Details @{
                revalidation_nonce = $nonce
                revalidation_sha256 = $writtenSha256
                movement_authorization_sha256 = [string]$movementAuthorization.Sha256
                session_receipt_nonce = [string]$receipt.receipt_nonce
                session_receipt_sha256 = [string]$receiptSnapshot.Sha256
                expires_at = $expiresAtCanonical
                input_tokens_sent = 0
            }
            Write-Output "LAB_MOVEMENT_REALM_REVALIDATION=$movementRevalidationPath"
            Write-Output "LAB_MOVEMENT_REALM_REVALIDATION_SHA256=$writtenSha256"
            Write-Output "LAB_MOVEMENT_REALM_REVALIDATION_EXPIRES=$expiresAtCanonical"
        }
        'IssueCombatRealmRevalidation' {
            Assert-ActiveTargetAuthorization
            $combatAuthorization = Read-ActiveCombatAuthorization
            $process = Wait-ForClientWindow
            Assert-LabReady
            $realm = Assert-ExactLabRealm
            $routing = Assert-ExactRealmRoutingRecord
            Assert-ClientProcessIdentity -Process $process
            $receiptSnapshot = Read-LabLaunchReceiptSnapshot
            $receipt = Assert-LabLaunchReceiptSnapshot -Snapshot $receiptSnapshot -Process $process
            $unchangedReceipt = Read-LabLaunchReceiptSnapshot
            if ($unchangedReceipt.Sha256 -ne $receiptSnapshot.Sha256) {
                throw 'Session receipt changed during combat realm revalidation.'
            }
            $observedAt = [DateTimeOffset]::UtcNow
            $expiresAt = $observedAt.AddSeconds(75)
            $receiptExpiresAt = [DateTimeOffset]::Parse([string]$receipt.expires_at)
            if ($combatAuthorization.ExpiresAt -lt $expiresAt) {
                $expiresAt = $combatAuthorization.ExpiresAt
            }
            if ($receiptExpiresAt -lt $expiresAt) {
                $expiresAt = $receiptExpiresAt
            }
            if ($expiresAt -le $observedAt.AddMilliseconds(250)) {
                throw 'Combat realm revalidation has insufficient remaining time.'
            }
            $canonicalUtcFormat = "yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'"
            $observedAtCanonical = $observedAt.UtcDateTime.ToString(
                $canonicalUtcFormat,
                [System.Globalization.CultureInfo]::InvariantCulture
            )
            $expiresAtCanonical = $expiresAt.UtcDateTime.ToString(
                $canonicalUtcFormat,
                [System.Globalization.CultureInfo]::InvariantCulture
            )
            $nonce = [Guid]::NewGuid().ToString('D')
            $combat = $combatAuthorization.Record
            $record = [ordered]@{
                record_type = 'local_realm_revalidation_receipt'
                schema_version = '0.1'
                issuer_id = 'perfect_assassin.local_realm_revalidator'
                revalidation_nonce = $nonce
                authorization_id = [string]$combat.authorization_id
                authorization_sha256 = [string]$combatAuthorization.Sha256
                session_receipt_nonce = [string]$receipt.receipt_nonce
                session_receipt_sha256 = [string]$receiptSnapshot.Sha256
                target_profile = [string]$combat.target_profile
                actor_id = [string]$combat.actor_binding.actor_id
                actor_instance_id = [string]$combat.actor_binding.instance_id
                pid = [int]$receipt.pid
                hwnd = [string]$receipt.hwnd
                process_created_at_utc = [string]$receipt.process_created_at_utc
                process_creation_filetime_utc = [string]$receipt.process_creation_filetime_utc
                windows_session_id = [int]$receipt.windows_session_id
                executable_path = [string]$receipt.executable_path
                executable_sha256 = [string]$receipt.executable_sha256
                environment_scope = 'emulator_local'
                server_kind = 'emulator'
                expected_realm_fingerprint = [string]$receipt.expected_realm_fingerprint
                realm_routing_sha256 = [string]$routing.Sha256
                realmlist_relative_path = [string]$realm.RelativePath
                realmlist_sha256 = [string]$realm.Sha256
                realmlist_directive = [string]$realm.Directive
                method = 'exact_realmlist_listener_process_config_and_realm_route'
                observed_at = $observedAtCanonical
                expires_at = $expiresAtCanonical
                scope = 'lab_evaluation_only'
                execution_authority = $false
            }
            $json = $record | ConvertTo-Json -Depth 8
            Write-AtomicJsonRecord -Path $combatRevalidationPath -Json $json -Nonce $nonce
            $writtenBytes = [System.IO.File]::ReadAllBytes($combatRevalidationPath)
            $writtenSha256 = Get-ByteArraySha256 -Bytes $writtenBytes
            Write-OperatorAudit -Name $Action -Result 'complete' -Details @{
                revalidation_nonce = $nonce
                revalidation_sha256 = $writtenSha256
                combat_authorization_sha256 = [string]$combatAuthorization.Sha256
                session_receipt_nonce = [string]$receipt.receipt_nonce
                session_receipt_sha256 = [string]$receiptSnapshot.Sha256
                expires_at = $expiresAtCanonical
                input_tokens_sent = 0
            }
            Write-Output "LAB_COMBAT_REALM_REVALIDATION=$combatRevalidationPath"
            Write-Output "LAB_COMBAT_REALM_REVALIDATION_SHA256=$writtenSha256"
            Write-Output "LAB_COMBAT_REALM_REVALIDATION_EXPIRES=$expiresAtCanonical"
        }
        'ArmSession' {
            Assert-ActiveTargetAuthorization
            Assert-LabReady
            Assert-LocalInteractiveSession
            if (-not $AcknowledgeRuntimeArm) {
                throw 'ArmSession requires -AcknowledgeRuntimeArm for bounded LAB input authority.'
            }
            $process = Wait-ForClientWindow
            $arm = New-LabRuntimeArm -Process $process
            Write-OperatorAudit -Name $Action -Result 'complete' -Details @{
                arm_nonce = $arm.arm_nonce
                expires_at = $arm.expires_at
                allowed_actions = @($arm.allowed_actions)
            }
            Write-Output "LAB_RUNTIME_ARM_EXPIRES=$($arm.expires_at)"
        }
        'DisarmSession' {
            Remove-LabRuntimeArm
            Write-OperatorAudit -Name $Action -Result 'complete'
        }
        'Login' {
            Assert-LabReady
            if ($ConfirmedVisualState -ne 'LoginScreen') {
                throw 'Login requires a separately inspected checkpoint and -ConfirmedVisualState LoginScreen.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process
            $before = Save-ClientCheckpoint -Process $process -Label 'before-login'
            $credential = Read-ObserverCredential
            Click-ClientRelative -Process $process -X 0.50 -Y 0.54
            Send-ClientKeys -Process $process -Keys '^a'
            Send-ClientText -Process $process -Text $credential.Account
            Click-ClientRelative -Process $process -X 0.50 -Y 0.63
            Send-ClientKeys -Process $process -Keys '^a'
            Send-ClientText -Process $process -Text $credential.Password
            $credential = $null
            Click-ClientRelative -Process $process -X 0.50 -Y 0.705
            Start-Sleep -Seconds 8
            $after = Save-ClientCheckpoint -Process $process -Label 'after-login'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{ before = $before; after = $after }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'InspectAddons' {
            if ($ConfirmedVisualState -ne 'CharacterSelect') {
                throw 'InspectAddons requires a separately inspected checkpoint and -ConfirmedVisualState CharacterSelect.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process
            Click-ClientRelative -Process $process -X 0.10 -Y 0.955
            Start-Sleep -Seconds 1
            $checkpoint = Save-ClientCheckpoint -Process $process -Label 'addon-list'
            Send-ClientKeys -Process $process -Keys '{ESC}'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{ checkpoint = $checkpoint }
            Write-Output "LAB_CLIENT_CHECKPOINT=$checkpoint"
        }
        'EnterWorld' {
            if ($ConfirmedVisualState -ne 'CharacterSelect') {
                throw 'EnterWorld requires a separately inspected checkpoint and -ConfirmedVisualState CharacterSelect.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process
            $before = Save-ClientCheckpoint -Process $process -Label 'before-enter-world'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Start-Sleep -Seconds 10
            $after = Save-ClientCheckpoint -Process $process -Label 'after-enter-world'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{ before = $before; after = $after }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'AcknowledgeLoginError' {
            if ($ConfirmedVisualState -ne 'LoginScreen') {
                throw 'AcknowledgeLoginError requires a separately inspected login-screen checkpoint and -ConfirmedVisualState LoginScreen.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-login-error-acknowledgement'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Start-Sleep -Seconds 2
            $after = Save-ClientCheckpoint -Process $process -Label 'after-login-error-acknowledgement'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $before
                after = $after
                fixed_input = 'ENTER'
                input_token_count = 1
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'AcknowledgeDisconnect' {
            if ($ConfirmedVisualState -ne 'DisconnectedDialog') {
                throw 'AcknowledgeDisconnect requires a separately inspected checkpoint and -ConfirmedVisualState DisconnectedDialog.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-disconnect-acknowledgement'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Start-Sleep -Seconds 3
            $after = Save-ClientCheckpoint -Process $process -Label 'after-disconnect-acknowledgement'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $before
                after = $after
                fixed_input = 'ENTER'
                input_token_count = 1
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'ReleaseSpirit' {
            if ($ConfirmedVisualState -ne 'DeadInWorld') {
                throw 'ReleaseSpirit requires a CRC-observed unreleased death and -ConfirmedVisualState DeadInWorld.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-release-spirit'
            # TBC 2.4.3 does not assign keyboard focus to StaticPopup1's
            # Release Spirit button.  Its centered relative geometry is stable
            # across the supported window size/UI scale, so use one bounded
            # click and require the CRC state transition on the next cycle.
            Click-ClientRelative -Process $process -X 0.50 -Y 0.232
            Start-Sleep -Seconds 4
            Assert-ActiveInputLease -Process $process
            $after = Save-ClientCheckpoint -Process $process -Label 'after-release-spirit'
            Write-OperatorAudit -Name $Action -Result 'requires_crc_state_verification' -Details @{
                before = $before
                after = $after
                fixed_input = 'LEFT_CLICK@0.500,0.232'
                input_token_count = 1
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'RetrieveCorpse' {
            if ($ConfirmedVisualState -ne 'GhostAtCorpse') {
                throw 'RetrieveCorpse requires ghost state after exact corpse-goal arrival and -ConfirmedVisualState GhostAtCorpse.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-retrieve-corpse'
            # StaticPopup1's Accept button has the same centered geometry as
            # Release Spirit and is not keyboard-focused in TBC 2.4.3.  Click
            # it once. This action never opens chat, so an unconditional Escape
            # would open TBC's Game Menu and contaminate the resumed journey
            # plus its ShadowPlay evidence.
            Click-ClientRelative -Process $process -X 0.50 -Y 0.232
            Start-Sleep -Seconds 2
            Assert-ActiveInputLease -Process $process
            $after = Save-ClientCheckpoint -Process $process -Label 'after-retrieve-corpse'
            Write-OperatorAudit -Name $Action -Result 'requires_crc_state_verification' -Details @{
                before = $before
                after = $after
                fixed_input = 'LEFT_CLICK@0.500,0.232'
                input_token_count = 1
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'ToggleEnemyNameplates' {
            if ($ConfirmedVisualState -ne 'InWorldChatClosed') {
                throw 'ToggleEnemyNameplates requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-enemy-nameplates-toggle'
            Send-ClientKeys -Process $process -Keys 'v'
            Start-Sleep -Seconds 1
            Assert-ActiveInputLease -Process $process
            $after = Save-ClientCheckpoint -Process $process -Label 'after-enemy-nameplates-toggle'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $before
                after = $after
                fixed_input = 'V'
                input_token_count = 1
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'OpenWorldMap' {
            if ($ConfirmedVisualState -ne 'InWorld') {
                throw 'OpenWorldMap requires a separately inspected checkpoint and -ConfirmedVisualState InWorld.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process
            $before = Save-ClientCheckpoint -Process $process -Label 'before-world-map-open'
            Send-ClientKeys -Process $process -Keys 'm'
            Start-Sleep -Seconds 1
            $after = Save-ClientCheckpoint -Process $process -Label 'after-world-map-open'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{ before = $before; after = $after }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'CloseWorldMap' {
            if ($ConfirmedVisualState -ne 'WorldMapOpen') {
                throw 'CloseWorldMap requires a separately inspected checkpoint and -ConfirmedVisualState WorldMapOpen.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process
            $before = Save-ClientCheckpoint -Process $process -Label 'before-world-map-close'
            Send-ClientKeys -Process $process -Keys 'm'
            Start-Sleep -Seconds 1
            $after = Save-ClientCheckpoint -Process $process -Label 'after-world-map-close'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{ before = $before; after = $after }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'DismissGameMenu' {
            if ($ConfirmedVisualState -notin @('GameMenuOpen', 'InWorldPanelOpen')) {
                throw 'DismissGameMenu requires a separately inspected checkpoint and a confirmed open in-world menu or panel.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-game-menu-dismiss'
            if ($ConfirmedVisualState -eq 'GameMenuOpen') {
                # The button center is measured against the entire native
                # window rectangle, including title bar and frame.
                Click-ClientRelative -Process $process -X 0.50 -Y 0.610
                $fixedInput = 'LEFT_CLICK_RETURN_TO_GAME@0.500,0.610'
            }
            else {
                # Escape closes the already-open top-level panel; it cannot
                # open Game Menu in the same dispatch.
                Send-ClientKeys -Process $process -Keys '{ESC}'
                $fixedInput = 'ESCAPE_CLOSE_TOP_PANEL'
            }
            Start-Sleep -Seconds 1
            Assert-ActiveInputLease -Process $process
            $after = Save-ClientCheckpoint -Process $process -Label 'after-game-menu-dismiss'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $before
                after = $after
                fixed_input = $fixedInput
                input_token_count = 1
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'SetDnd' {
            if ($ConfirmedVisualState -ne 'InWorldChatClosed') {
                throw 'SetDnd requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-dnd'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Send-ClientText -Process $process -Text '/dnd Movement Engine test in progress'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Start-Sleep -Milliseconds 500
            Assert-ActiveInputLease -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $after = Save-ClientCheckpoint -Process $process -Label 'after-dnd'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $before
                after = $after
                fixed_command = '/dnd Movement Engine test in progress'
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'ClearTarget' {
            if ($ConfirmedVisualState -ne 'InWorldChatClosed') {
                throw 'ClearTarget requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-clear-target'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Send-ClientText -Process $process -Text '/cleartarget'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Start-Sleep -Milliseconds 500
            Assert-ActiveInputLease -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $after = Save-ClientCheckpoint -Process $process -Label 'after-clear-target'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $before
                after = $after
                fixed_command = '/cleartarget'
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'ToggleVideoRecording' {
            if ($ConfirmedVisualState -ne 'InWorldChatClosed') {
                throw 'ToggleVideoRecording requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-video-record-toggle'
            Send-ClientKeys -Process $process -Keys '%{F9}'
            Start-Sleep -Seconds 1
            Assert-ActiveInputLease -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $after = Save-ClientCheckpoint -Process $process -Label 'after-video-record-toggle'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $before
                after = $after
                fixed_input = 'ALT+F9'
                input_token_count = 1
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'ReloadUi' {
            if ($ConfirmedVisualState -ne 'InWorldChatClosed') {
                throw 'ReloadUi requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-ui-reload'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Send-ClientText -Process $process -Text '/console reloadui'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Start-Sleep -Seconds 5
            Assert-ActiveInputLease -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $after = Save-ClientCheckpoint -Process $process -Label 'after-ui-reload'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $before
                after = $after
                fixed_command = '/console reloadui'
                settle_seconds = 5
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'ApplyPredatorUiProfile' {
            if ($ConfirmedVisualState -ne 'InWorldChatClosed') {
                throw 'ApplyPredatorUiProfile requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-predator-ui-apply'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Send-ClientText -Process $process -Text '/paobars apply'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Start-Sleep -Seconds 2
            Assert-ActiveInputLease -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $after = Save-ClientCheckpoint -Process $process -Label 'after-predator-ui-apply'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $before
                after = $after
                fixed_command = '/paobars apply'
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'RestorePredatorUiProfile' {
            if ($ConfirmedVisualState -ne 'InWorldChatClosed') {
                throw 'RestorePredatorUiProfile requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-predator-ui-restore'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Send-ClientText -Process $process -Text '/paobars restore'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Start-Sleep -Seconds 2
            Assert-ActiveInputLease -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $after = Save-ClientCheckpoint -Process $process -Label 'after-predator-ui-restore'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $before
                after = $after
                fixed_command = '/paobars restore'
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'SnapshotPredatorUiProfile' {
            if ($ConfirmedVisualState -ne 'InWorldChatClosed') {
                throw 'SnapshotPredatorUiProfile requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-predator-ui-snapshot'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Send-ClientText -Process $process -Text '/paobars snapshot'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Start-Sleep -Seconds 2
            Assert-ActiveInputLease -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $after = Save-ClientCheckpoint -Process $process -Label 'after-predator-ui-snapshot'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $before
                after = $after
                fixed_command = '/paobars snapshot'
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'SetUiScale80' {
            if ($ConfirmedVisualState -ne 'InWorldChatClosed') {
                throw 'SetUiScale80 requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            $result = Set-ExplicitUiScale -Process $process -Scale '0.8'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $result.Before
                after = $result.After
                ui_scale = $result.Scale
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$($result.After)"
        }
        'SetUiScale100' {
            if ($ConfirmedVisualState -ne 'InWorldChatClosed') {
                throw 'SetUiScale100 requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            $result = Set-ExplicitUiScale -Process $process -Scale '1.0'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $result.Before
                after = $result.After
                ui_scale = $result.Scale
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$($result.After)"
        }
        'RestoreUiScaleDefault' {
            if ($ConfirmedVisualState -ne 'InWorldChatClosed') {
                throw 'RestoreUiScaleDefault requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            $result = Restore-DefaultUiScale -Process $process
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $result.Before
                after = $result.After
                use_ui_scale = 0
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$($result.After)"
        }
        'ResizeWindowCompact' {
            if ($ConfirmedVisualState -ne 'InWorld') {
                throw 'ResizeWindowCompact requires a separately inspected checkpoint and -ConfirmedVisualState InWorld.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            $result = Set-ExplicitWindowSize -Process $process -Profile 'compact'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $result.Before
                after = $result.After
                profile = $result.Profile
                requested_outer_width = $result.RequestedOuterWidth
                requested_outer_height = $result.RequestedOuterHeight
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$($result.After)"
        }
        'ResizeWindowBaseline' {
            if ($ConfirmedVisualState -ne 'InWorld') {
                throw 'ResizeWindowBaseline requires a separately inspected checkpoint and -ConfirmedVisualState InWorld.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            $result = Set-ExplicitWindowSize -Process $process -Profile 'baseline'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{
                before = $result.Before
                after = $result.After
                profile = $result.Profile
                requested_outer_width = $result.RequestedOuterWidth
                requested_outer_height = $result.RequestedOuterHeight
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$($result.After)"
        }
        'Capture' {
            Assert-ActiveTargetAuthorization
            $process = Wait-ForClientWindow
            $checkpoint = Save-ClientCheckpoint -Process $process -Label 'manual-checkpoint'
            Write-OperatorAudit -Name $Action -Result 'complete' -Details @{ checkpoint = $checkpoint }
            Write-Output "LAB_CLIENT_CHECKPOINT=$checkpoint"
        }
        'SaveShadowReplay' {
            if ($ConfirmedVisualState -ne 'InWorldChatClosed') {
                throw 'SaveShadowReplay requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process -BoundToActiveInputLease
            $before = Save-ClientCheckpoint -Process $process -Label 'before-shadow-replay-save'
            Send-ClientKeys -Process $process -Keys '%{F10}'
            Start-Sleep -Seconds 4
            Assert-ActiveInputLease -Process $process
            # WoW 2.4.3 also sees F10 and opens its game menu after NVIDIA
            # saves the replay. A synthetic Escape is not reliable here, so
            # activate the explicit Return to Game control.
            Click-ClientRelative -Process $process -X 0.50 -Y 0.610
            Start-Sleep -Seconds 1
            Assert-ActiveInputLease -Process $process
            $after = Save-ClientCheckpoint -Process $process -Label 'after-shadow-replay-save'
            Write-OperatorAudit -Name $Action -Result 'complete' -Details @{
                before = $before
                after = $after
                fixed_hotkey = 'ALT+F10'
                post_save_input = 'LEFT_CLICK_RETURN_TO_GAME@0.500,0.610'
                input_token_count = 2
                settle_seconds = 5
            }
            Write-Output "LAB_CLIENT_CHECKPOINT=$after"
        }
        'Logout' {
            if ($ConfirmedVisualState -ne 'InWorldChatClosed') {
                throw 'Logout requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.'
            }
            $process = Wait-ForClientWindow
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Send-ClientText -Process $process -Text '/logout'
            Send-ClientKeys -Process $process -Keys '{ENTER}'
            Start-Sleep -Seconds 22
            $checkpoint = Save-ClientCheckpoint -Process $process -Label 'after-logout'
            Write-OperatorAudit -Name $Action -Result 'requires_visual_verification' -Details @{ checkpoint = $checkpoint }
            Write-Output "LAB_CLIENT_CHECKPOINT=$checkpoint"
        }
        'Close' {
            $process = Get-ClientProcess
            if ($null -eq $process) {
                Remove-LabRuntimeArm
                Remove-LabLaunchReceipt
                Write-OperatorAudit -Name $Action -Result 'already_closed'
                return
            }
            Assert-RuntimeArm -Name $Action -Process $process
            Focus-Client -Process $process
            Send-ClientKeys -Process $process -Keys '%{F4}'
            if (-not $process.WaitForExit(5000)) {
                throw 'Client did not close normally; forced termination is intentionally not available.'
            }
            Remove-LabRuntimeArm
            Remove-LabLaunchReceipt
            Write-OperatorAudit -Name $Action -Result 'complete'
        }
        'Import' {
            if (Get-ClientProcess) {
                throw 'Client is still running; logout and close it before import.'
            }
            $importScript = Join-Path $PSScriptRoot 'Import-LabObserverCapture.ps1'
            & $importScript -RepositoryRoot $RepositoryRoot -ClientRoot $ClientRoot -Account $expectedAccount
            if ($LASTEXITCODE -ne 0) {
                throw 'Observer import failed.'
            }
            Write-OperatorAudit -Name $Action -Result 'complete'
        }
    }
}
catch {
    Write-OperatorObservationSafely -Name $Action -Result 'failed' -Details @{ error = $_.Exception.Message }
    throw
}
