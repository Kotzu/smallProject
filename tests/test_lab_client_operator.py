from __future__ import annotations

import copy
import base64
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator


ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "scripts" / "Invoke-LabClientOperator.ps1"
WINDOW_PROFILE = ROOT / "config" / "movement-lab" / "client-window-profile.json"
ADDON = (
    ROOT
    / "integrations"
    / "tbc243-addon"
    / "PerfectAssassinObserver"
    / "PerfectAssassinObserver.lua"
)
AUTHORIZATION = ROOT / "config" / "execution-targets" / "tbc_243_lab.json"
AUTHORIZATION_SCHEMA = ROOT / "contracts" / "execution-target-authorization.schema.json"
LAUNCH_RECEIPT_SCHEMA = ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
RUNTIME_ARM_SCHEMA = ROOT / "contracts" / "lab-client-runtime-arm.schema.json"
IDENTITY_ISSUANCE_SCHEMA = (
    ROOT / "contracts" / "lab-client-identity-issuance.schema.json"
)
INPUT_ACTIONS = (
    "Login",
    "InspectAddons",
    "EnterWorld",
    "AcknowledgeLoginError",
    "AcknowledgeDisconnect",
    "ReleaseSpirit",
    "RetrieveCorpse",
    "ToggleEnemyNameplates",
    "OpenWorldMap",
    "CloseWorldMap",
    "DismissGameMenu",
    "SetDnd",
    "ClearTarget",
    "ToggleVideoRecording",
    "ReloadUi",
    "ApplyPredatorUiProfile",
    "RestorePredatorUiProfile",
    "SnapshotPredatorUiProfile",
    "SetUiScale80",
    "SetUiScale100",
    "RestoreUiScaleDefault",
    "ResizeWindowCompact",
    "ResizeWindowBaseline",
    "SaveShadowReplay",
    "Logout",
    "Close",
)


def run_operator_with_authorization(
    raw_authorization: str, *, action: str = "Status"
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        authorization_path = root / "config" / "execution-targets" / "tbc_243_lab.json"
        schema_path = root / "contracts" / AUTHORIZATION_SCHEMA.name
        authorization_path.parent.mkdir(parents=True)
        schema_path.parent.mkdir(parents=True)
        authorization_path.write_text(raw_authorization, encoding="utf-8")
        shutil.copyfile(AUTHORIZATION_SCHEMA, schema_path)
        command = [
                "pwsh",
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(OPERATOR),
                "-Action",
                action,
                "-RepositoryRoot",
                str(root),
                "-ClientRoot",
                str(root / "client"),
            ]
        if action in {"AdoptSession", "RenewSessionIdentity"}:
            command.append("-AcknowledgeSessionIdentity")
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )


def run_operator_status_with_receipt(raw_receipt: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        authorization_path = root / "config" / "execution-targets" / "tbc_243_lab.json"
        contracts_path = root / "contracts"
        receipt_path = root / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
        authorization_path.parent.mkdir(parents=True)
        contracts_path.mkdir(parents=True)
        receipt_path.parent.mkdir(parents=True)
        shutil.copyfile(AUTHORIZATION, authorization_path)
        shutil.copyfile(AUTHORIZATION_SCHEMA, contracts_path / AUTHORIZATION_SCHEMA.name)
        shutil.copyfile(LAUNCH_RECEIPT_SCHEMA, contracts_path / LAUNCH_RECEIPT_SCHEMA.name)
        receipt_path.write_text(raw_receipt, encoding="utf-8")
        return subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(OPERATOR),
                "-Action",
                "Status",
                "-RepositoryRoot",
                str(root),
                "-ClientRoot",
                str(root / "client"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )


def valid_v1_launch_receipt() -> dict[str, object]:
    authorization = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
    return {
        "record_type": "lab_client_launch_receipt",
        "schema_version": "1.0",
        "receipt_nonce": "11111111-1111-4111-8111-111111111111",
        "pid": 1234,
        "hwnd": "0xABC",
        "process_created_at_utc": "2026-08-22T21:53:46.5976452Z",
        "process_creation_filetime_utc": "134319092265976452",
        "windows_session_id": 1,
        "identity_origin": "operator_launch",
        "parent_receipt_nonce": None,
        "parent_receipt_sha256": None,
        "parent_authorization_sha256": None,
        "window_title": "World of Warcraft",
        "window_class": "GxWindowClassD3d",
        "executable_path": r"E:\Games\WoW TBC 2.4.3\Wow.exe",
        "executable_sha256": authorization["client_match"]["executable_sha256"],
        "client_build": authorization["client_match"]["client_build"],
        "build_signature": (
            f"{authorization['client_match']['build_signature']}:sha256:"
            f"{authorization['client_match']['executable_sha256']}"
        ),
        "target_profile": authorization["target_profile"],
        "authorization_id": authorization["authorization_id"],
        "authorization_sha256": "A" * 64,
        "authorization_semantic_sha256": "D" * 64,
        "actor_binding": copy.deepcopy(authorization["actor_binding"]),
        "environment_scope": "emulator_local",
        "server_kind": "emulator",
        "expected_realm_fingerprint": authorization["realm_match"][
            "expected_realm_fingerprint"
        ],
        "realm_assurance": {
            "state": "local_process_config_verified_at_launch",
            "method": "exact_realmlist_listener_process_config_and_realm_route",
            "verified_at": "2026-08-22T21:53:49Z",
        },
        "realm_routing_sha256": "B" * 64,
        "realmlist_relative_path": "realmlist.wtf",
        "realmlist_sha256": "C" * 64,
        "realmlist_directive": "set realmlist 127.0.0.1",
        "decision_context": "lab_clone",
        "created_at": "2026-08-22T21:53:49Z",
        "expires_at": "2026-08-22T22:23:49Z",
        "scope": "lab_evaluation_only",
        "execution_authority": False,
    }


def valid_legacy_v01_launch_receipt() -> dict[str, object]:
    receipt = valid_v1_launch_receipt()
    receipt["schema_version"] = "0.1"
    for field in (
        "process_created_at_utc",
        "process_creation_filetime_utc",
        "windows_session_id",
        "identity_origin",
        "parent_receipt_nonce",
        "parent_receipt_sha256",
        "parent_authorization_sha256",
        "authorization_semantic_sha256",
    ):
        del receipt[field]
    return receipt


def active_authorization() -> dict[str, object]:
    authorization = copy.deepcopy(json.loads(AUTHORIZATION.read_text(encoding="utf-8")))
    now = datetime.now(timezone.utc)
    authorization["approval"]["recorded_at"] = (now - timedelta(minutes=1)).isoformat()
    authorization["approval"]["expires_at"] = (now + timedelta(minutes=10)).isoformat()
    return authorization


def powershell_function(script: str, name: str) -> str:
    start = script.index(f"function {name} {{")
    next_function = script.find("\nfunction ", start + 1)
    if next_function < 0:
        return script[start:]
    return script[start:next_function]


def run_powershell_source(source: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as directory:
        script_path = Path(directory) / "runtime-test.ps1"
        script_path.write_text(
            "$ErrorActionPreference = 'Stop'\n" + source,
            encoding="utf-8",
        )
        return subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(script_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )


def valid_identity_issuance(
    receipt: dict[str, object] | None = None,
) -> tuple[dict[str, object], bytes]:
    receipt = copy.deepcopy(receipt or valid_v1_launch_receipt())
    receipt_json = json.dumps(receipt, separators=(",", ":"))
    receipt_bytes = receipt_json.encode("utf-8")
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest().upper()
    origin = str(receipt["identity_origin"])
    action = {
        "operator_launch": "Launch",
        "legacy_v0_1_continuity_adoption": "AdoptSession",
        "verified_receipt_renewal": "RenewSessionIdentity",
    }[origin]
    legacy_audit = "E" * 64 if action == "AdoptSession" else None
    marker = {
        "record_type": "lab_client_identity_issuance",
        "schema_version": "1.0",
        "issuance_nonce": receipt["receipt_nonce"],
        "action": action,
        "identity_origin": origin,
        "parent_receipt_nonce": receipt["parent_receipt_nonce"],
        "parent_receipt_sha256": receipt["parent_receipt_sha256"],
        "parent_authorization_sha256": receipt["parent_authorization_sha256"],
        "new_receipt_nonce": receipt["receipt_nonce"],
        "new_receipt_sha256": receipt_sha256,
        "new_authorization_sha256": receipt["authorization_sha256"],
        "new_authorization_semantic_sha256": receipt[
            "authorization_semantic_sha256"
        ],
        "pid": receipt["pid"],
        "hwnd": receipt["hwnd"],
        "process_creation_filetime_utc": receipt[
            "process_creation_filetime_utc"
        ],
        "windows_session_id": receipt["windows_session_id"],
        "issued_at": receipt["created_at"],
        "receipt_utf8_base64": base64.b64encode(receipt_bytes).decode("ascii"),
        "legacy_launch_audit_file_sha256": legacy_audit,
        "legacy_launch_audit_entry_sha256": legacy_audit,
        "scope": "lab_identity_issuance_commit",
        "execution_authority": False,
    }
    return marker, receipt_bytes


class LabClientOperatorBoundaryTests(unittest.TestCase):
    def test_operator_exposes_only_bounded_phases(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn(
            "[ValidateSet('Status', 'Launch', 'BindOperatorLaunch', 'AdoptSession', 'RenewSessionIdentity', 'IssueMovementRealmRevalidation', 'IssueCombatRealmRevalidation', 'ArmSession', 'DisarmSession', 'Login', 'InspectAddons', 'EnterWorld', 'AcknowledgeLoginError', 'AcknowledgeDisconnect', 'ReleaseSpirit', 'RetrieveCorpse', 'ToggleEnemyNameplates', 'OpenWorldMap', 'CloseWorldMap', 'DismissGameMenu', 'SetDnd', 'ClearTarget', 'ToggleVideoRecording', 'ReloadUi', 'ApplyPredatorUiProfile', 'RestorePredatorUiProfile', 'SnapshotPredatorUiProfile', 'SetUiScale80', 'SetUiScale100', 'RestoreUiScaleDefault', 'ResizeWindowCompact', 'ResizeWindowBaseline', 'Capture', 'SaveShadowReplay', 'Logout', 'Close', 'Import')]",
            script,
        )

    def test_operator_can_bind_only_an_explicit_nvidia_operator_launch(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        block = script[
            script.index("        'BindOperatorLaunch' {") :
            script.index("        'AdoptSession' {")
        ]
        self.assertIn("AcknowledgeClientRisk", block)
        self.assertIn("AcknowledgeSessionIdentity", block)
        self.assertIn("Assert-ActiveTargetAuthorization", block)
        self.assertIn("Assert-LabReady", block)
        self.assertIn("Assert-ClientProcessIdentity", block)
        self.assertIn("Assert-NvidiaOperatorLaunch", block)
        self.assertIn("input_tokens_sent = 0", block)
        helper = script[
            script.index("function Assert-NvidiaOperatorLaunch") :
            script.index("try {", script.index("function Assert-NvidiaOperatorLaunch"))
        ]
        self.assertIn("NVIDIA App.exe", helper)
        self.assertIn("Get-AuthenticodeSignature", helper)
        self.assertIn("SignatureStatus]::Valid", helper)
        self.assertIn("TotalMinutes -gt 30", helper)
        self.assertNotIn("Send-Client", helper)

    def test_set_dnd_is_fixed_and_requires_closed_chat(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        block = script[
            script.index("        'SetDnd' {") :
            script.index("        'ReloadUi' {")
        ]
        self.assertIn("ConfirmedVisualState -ne 'InWorldChatClosed'", block)
        self.assertIn("Assert-RuntimeArm", block)
        self.assertIn("'/dnd Movement Engine test in progress'", block)
        self.assertNotIn("$command", block)

    def test_video_record_toggle_is_exact_alt_f9(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        block = script[
            script.index("        'ToggleVideoRecording' {") :
            script.index("        'ReloadUi' {")
        ]
        self.assertIn("ConfirmedVisualState -ne 'InWorldChatClosed'", block)
        self.assertIn("Assert-RuntimeArm", block)
        self.assertIn("Send-ClientKeys -Process $process -Keys '%{F9}'", block)
        self.assertNotIn("SendSlash", script)
        self.assertNotIn("Invoke-Expression", script)
        self.assertNotIn("Stop-Process", script)
        self.assertNotIn("taskkill", script.lower())
        self.assertIn("[ValidateRange(1, 60)]", script)

    def test_movement_revalidation_is_zero_input_and_exactly_bound(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        block = script[
            script.index("        'IssueMovementRealmRevalidation' {") :
            script.index("        'IssueCombatRealmRevalidation' {")
        ]
        self.assertIn("Read-ActiveMovementAuthorization", block)
        self.assertIn("Assert-LabReady", block)
        self.assertIn("Assert-ExactRealmRoutingRecord", block)
        self.assertIn("Assert-ClientProcessIdentity", block)
        self.assertIn("input_tokens_sent = 0", block)
        self.assertIn("Write-AtomicJsonRecord", block)
        self.assertNotIn("Send-Client", block)
        self.assertNotIn("Focus-Client", block)
        self.assertNotIn("mouse_event", block)
        self.assertIn("[string]$AuthorizationFile = ''", script)
        self.assertIn("[string]$MovementAuthorizationFile = ''", script)
        self.assertIn("[switch]$AcknowledgeSinglePulse", script)
        self.assertIn("$actorIdentityFields", script)
        self.assertIn("$actorIdentityMismatch", script)
        self.assertIn("'memory_namespace'", script)
        self.assertIn("'expected_character_name'", script)
        self.assertIn("binding_assurance.state", script)
        self.assertNotIn("$fixedActorJson -ne $movementActorJson", script)
        self.assertIn("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'", block)
        self.assertIn("observed_at = $observedAtCanonical", block)
        self.assertIn("expires_at = $expiresAtCanonical", block)

    def test_combat_revalidation_is_zero_input_and_exactly_bound(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        block = script[
            script.index("        'IssueCombatRealmRevalidation' {") :
            script.index("        'ArmSession' {")
        ]
        self.assertIn("Read-ActiveCombatAuthorization", block)
        self.assertIn("Assert-LabReady", block)
        self.assertIn("Assert-ExactRealmRoutingRecord", block)
        self.assertIn("Assert-ClientProcessIdentity", block)
        self.assertIn("input_tokens_sent = 0", block)
        self.assertIn("Write-AtomicJsonRecord", block)
        self.assertNotIn("Send-Client", block)
        self.assertNotIn("Focus-Client", block)
        self.assertNotIn("mouse_event", block)
        self.assertIn("[string]$CombatAuthorizationFile = ''", script)
        self.assertIn("[switch]$AcknowledgeControlledCombat", script)
        self.assertIn("player_targets_authorized -ne $false", script)
        self.assertIn("economy_authorized -ne $false", script)

    def test_operator_launch_preserves_absent_parent_fields_as_json_null(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        signature = script[
            script.index("function New-LabLaunchReceipt") :
            script.index("    Assert-ActiveTargetAuthorization", script.index("function New-LabLaunchReceipt"))
        ]
        for name in (
            "ParentReceiptNonce",
            "ParentReceiptSha256",
            "ParentAuthorizationSha256",
            "LegacyLaunchAuditFileSha256",
            "LegacyLaunchAuditEntrySha256",
        ):
            self.assertIn(f"[AllowNull()]${name}", signature)
            self.assertNotIn(f"[AllowNull()][string]${name}", signature)

    def test_operator_is_explicitly_outside_predator_execution(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("external_lab_operator_harness", script)
        self.assertIn("predator_execution_mode = 'OBSERVE_ONLY'", script)
        self.assertIn("requires_visual_verification", script)
        self.assertIn("-ConfirmedVisualState LoginScreen", script)
        self.assertIn("-ConfirmedVisualState CharacterSelect", script)
        self.assertIn("-ConfirmedVisualState InWorld", script)
        self.assertIn("-ConfirmedVisualState InWorldChatClosed", script)

    def test_addon_inspection_is_bounded_to_character_select(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("'InspectAddons' {", script)
        self.assertIn("InspectAddons requires a separately inspected checkpoint", script)
        self.assertIn("-Label 'addon-list'", script)
        self.assertIn("Send-ClientKeys -Process $process -Keys '{ESC}'", script)

    def test_world_map_probe_is_bounded_and_visually_gated(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("'OpenWorldMap' {", script)
        self.assertIn("OpenWorldMap requires a separately inspected checkpoint", script)
        self.assertIn("'CloseWorldMap' {", script)
        self.assertIn("CloseWorldMap requires a separately inspected checkpoint", script)
        self.assertIn("-ConfirmedVisualState WorldMapOpen", script)
        self.assertEqual(script.count("Send-ClientKeys -Process $process -Keys 'm'"), 2)

    def test_ui_reload_is_fixed_bounded_and_requires_visual_verification(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        block = script[
            script.index("        'ReloadUi' {") :
            script.index("        'SetUiScale80' {")
        ]
        self.assertIn(
            "ReloadUi requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.",
            block,
        )
        self.assertIn("Assert-RuntimeArm -Name $Action -Process $process", block)
        self.assertIn("Focus-Client -Process $process -BoundToActiveInputLease", block)
        self.assertIn("-Label 'before-ui-reload'", block)
        self.assertIn(
            "Send-ClientText -Process $process -Text '/console reloadui'", block
        )
        self.assertEqual(block.count("'/console reloadui'"), 2)
        self.assertNotIn("'/reload'", block)
        self.assertIn("Start-Sleep -Seconds 5", block)
        self.assertIn("Assert-ActiveInputLease -Process $process", block)
        self.assertIn("-Label 'after-ui-reload'", block)
        self.assertIn("-Result 'requires_visual_verification'", block)
        self.assertNotIn("$Command", block)
        self.assertNotIn("/logout", block)
        self.assertNotIn("SendSlash", block)
        self.assertLess(
            block.index("-Label 'before-ui-reload'"),
            block.index(
                "Send-ClientText -Process $process -Text '/console reloadui'"
            ),
        )
        self.assertLess(
            block.index("Start-Sleep -Seconds 5"),
            block.index("-Label 'after-ui-reload'"),
        )

    def test_predator_ui_profile_commands_are_fixed_bounded_and_reversible(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        block = script[
            script.index("        'ApplyPredatorUiProfile' {") :
            script.index("        'SetUiScale80' {")
        ]
        for action, command in (
            ("ApplyPredatorUiProfile", "/paobars apply"),
            ("RestorePredatorUiProfile", "/paobars restore"),
            ("SnapshotPredatorUiProfile", "/paobars snapshot"),
        ):
            self.assertIn(f"'{action}' {{", block)
            self.assertIn(
                f"{action} requires a separately inspected checkpoint and -ConfirmedVisualState InWorldChatClosed.",
                block,
            )
            self.assertEqual(block.count(f"'{command}'"), 2)
        self.assertEqual(block.count("Assert-RuntimeArm -Name $Action -Process $process"), 3)
        self.assertEqual(block.count("Assert-ActiveInputLease -Process $process"), 3)
        self.assertNotIn("$Command", block)

    def test_hud_layout_matrix_uses_only_fixed_reversible_profiles(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        for action in (
            "ReloadUi",
            "SetUiScale80",
            "SetUiScale100",
            "RestoreUiScaleDefault",
            "ResizeWindowCompact",
            "ResizeWindowBaseline",
        ):
            self.assertIn(f"'{action}' {{", script)
            self.assertIn(
                f"{action} requires a separately inspected checkpoint",
                script,
            )
        self.assertIn("[ValidateSet('0.8', '1.0')]", script)
        self.assertIn("[ValidateSet('compact', 'baseline')]", script)
        self.assertIn("@('/console useUiScale 1', \"/console uiScale $Scale\")", script)
        self.assertIn("Send-ClientText -Process $Process -Text '/console useUiScale 0'", script)
        self.assertIn("$width = if ($Profile -eq 'compact') { 1100 } else { [int]$preferredWindowProfile.outer_bounds.width }", script)
        self.assertIn("$height = if ($Profile -eq 'compact') { 850 } else { [int]$preferredWindowProfile.outer_bounds.height }", script)
        self.assertNotIn("[string]$ConsoleCommand", script)
        resize_helper = script[
            script.index("function Set-ExplicitWindowSize") :
            script.index("function Get-ClientRect")
        ]
        self.assertGreaterEqual(
            resize_helper.count("Assert-ActiveInputLease -Process $Process"), 3
        )
        self.assertIn("Assert-ExactClientWindowBinding", resize_helper)
        self.assertLess(
            resize_helper.rindex("Assert-ActiveInputLease -Process $Process", 0, resize_helper.index("MoveWindow(")),
            resize_helper.index("MoveWindow("),
        )
        self.assertIn("GetForegroundWindow() -ne $expectedHandle", resize_helper)

    def test_launch_restores_the_operator_selected_large_window(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        profile = json.loads(WINDOW_PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(profile["record_type"], "lab_client_window_profile")
        self.assertTrue(profile["auto_apply_on_launch"])
        self.assertTrue(profile["windowed"])
        self.assertEqual(profile["render_resolution"], {
            "width": 3840,
            "height": 2160,
            "refresh_hz": 120,
        })
        self.assertEqual(profile["outer_bounds"], {
            "left": 1353,
            "top": 2,
            "width": 3643,
            "height": 2093,
        })
        launch_block = script[
            script.index("        'Launch' {") :
            script.index("        'AdoptSession' {")
        ]
        self.assertIn("Set-PreferredClientGraphicsConfig", launch_block)
        self.assertIn("Set-PreferredWindowLayout", launch_block)
        self.assertIn("preferred_window_profile = $windowLayout", launch_block)

    def test_every_client_action_is_bound_to_exact_path_hash_and_authorization(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("config\\execution-targets\\tbc_243_lab.json", script)
        self.assertIn("environment_scope -ne 'emulator_local'", script)
        self.assertIn("realm_match.server_kind -ne 'emulator'", script)
        self.assertIn("$process = Get-SingleWowProcess -AllowNone", script)
        self.assertIn("Assert-ClientProcessIdentity -Process $Process", script)
        self.assertIn("$actualHwnd -ne [long]$ExpectedHwnd", script)
        self.assertNotIn("$ExpectedHwnd.Value", script)
        self.assertNotIn("$AdditionalLimit.Value", script)
        self.assertIn("$additionalExpiry = [DateTimeOffset]$AdditionalLimit", script)
        self.assertIn("Get-FileHash -LiteralPath $actualPath -Algorithm SHA256", script)
        self.assertIn("Running WoW process path does not match", script)
        self.assertIn("SHA-256 does not match", script)
        self.assertIn("[System.IO.File]::ReadAllBytes($authorizationPath)", script)
        self.assertIn("Get-ByteArraySha256 -Bytes $authorizationBytes", script)
        self.assertNotIn(
            "Get-FileHash -LiteralPath $authorizationPath -Algorithm SHA256",
            script,
        )

    def test_each_keyboard_or_mouse_submit_rechecks_exact_foreground_hwnd(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("public static extern IntPtr GetForegroundWindow()", script)
        self.assertIn("function Send-ClientAtomicToken", script)
        self.assertIn("function Send-ClientKeys", script)
        self.assertIn("function Send-ClientText", script)
        self.assertIn(
            "GetForegroundWindow() -ne $Process.MainWindowHandle",
            script,
        )
        self.assertEqual(
            script.count("[System.Windows.Forms.SendKeys]::SendWait("),
            1,
        )
        atomic_helper = script[
            script.index("function Send-ClientAtomicToken") :
            script.index("function Set-ExplicitUiScale")
        ]
        self.assertIn("Client focus changed during keyboard input", atomic_helper)
        self.assertIn("foreach ($character in $Text.ToCharArray())", atomic_helper)
        self.assertIn(
            "Send-ClientAtomicToken -Process $Process -Token $token",
            atomic_helper,
        )
        click_helper = script[script.index("function Click-ClientRelative") :]
        self.assertLess(
            click_helper.index("Focus-Client -Process $Process"),
            click_helper.index("$rect = Get-ClientRect -Process $Process"),
        )
        self.assertIn(
            "if (-not [PerfectAssassinLabClientNative]::SetCursorPos($screenX, $screenY))",
            click_helper,
        )
        self.assertIn("public static extern bool GetCursorPos(out POINT point)", script)
        self.assertIn("$verifiedRect = Get-ClientRect -Process $Process", click_helper)
        self.assertIn("$verifiedRect.Left -ne $rect.Left", click_helper)
        self.assertIn(
            "if (-not [PerfectAssassinLabClientNative]::GetCursorPos([ref]$cursor))",
            click_helper,
        )
        self.assertIn("$cursor.X -ne $screenX", click_helper)
        self.assertLess(
            click_helper.index("$verifiedRect = Get-ClientRect -Process $Process"),
            click_helper.index("mouse_event(0x0002"),
        )
        self.assertLess(
            click_helper.index("$cursor.X -ne $screenX"),
            click_helper.index("mouse_event(0x0002"),
        )
        self.assertLess(
            click_helper.index("GetForegroundWindow()"),
            click_helper.index("mouse_event(0x0002"),
        )

    def test_visual_checkpoint_requires_stable_foreground_client_window(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("SetProcessDpiAwarenessContext", script)
        self.assertIn("SetThreadDpiAwarenessContext", script)
        self.assertIn("[IntPtr](-4)", script)
        self.assertIn("GetThreadDpiAwarenessContext", script)
        self.assertIn("AreDpiAwarenessContextsEqual", script)
        self.assertLess(
            script.index("SetProcessDpiAwarenessContext([IntPtr](-4))"),
            script.index("Add-Type -AssemblyName System.Drawing"),
        )
        helper = script[
            script.index("function Save-ClientCheckpoint") :
            script.index("function Click-ClientRelative")
        ]
        self.assertIn("Focus-Client -Process $Process", helper)
        self.assertIn("Assert-ExactClientWindowBinding", helper)
        self.assertGreaterEqual(helper.count("GetForegroundWindow()"), 2)
        self.assertIn("$verifiedRect = Get-ClientRect -Process $Process", helper)
        self.assertIn("$afterRect = Get-ClientRect -Process $Process", helper)
        self.assertLess(helper.index("CopyFromScreen("), helper.index("$bitmap.Save("))
        self.assertLess(helper.index("$afterRect = Get-ClientRect"), helper.index("$bitmap.Save("))

    def test_zero_input_authorization_rebind_keeps_exact_process_and_realm_gates(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("[switch]$AcknowledgeAuthorizationRebind", script)
        renewal = script[
            script.index("        'RenewSessionIdentity' {") :
            script.index("        'IssueMovementRealmRevalidation' {")
        ]
        self.assertIn("-AllowAuthorizationRebind", renewal)
        self.assertIn("-AllowWindowRebind:$AcknowledgeWindowRebind", renewal)
        self.assertIn("input_tokens_sent = 0", renewal)
        self.assertNotIn("Send-Client", renewal)
        validator = powershell_function(script, "Assert-LabLaunchReceiptSnapshot")
        self.assertIn("Assert-LabReady", validator)
        self.assertIn("Assert-ExactRealmRoutingRecord", validator)
        self.assertIn("Assert-ExactProcessCreationBinding", validator)
        self.assertIn("Assert-ExactClientWindowBinding", validator)
        self.assertIn("$receipt.authorization_sha256 -notmatch", validator)

    def test_input_tokens_are_bounded_by_unchanged_runtime_arm_and_deadline(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("$maxInputActionSeconds = 30", script)
        self.assertIn("ActionBudgetSeconds = $actionBudgetSeconds", script)
        self.assertIn("DeadlineTicks = [int64]0", script)
        self.assertIn("if ([int64]$lease.DeadlineTicks -eq 0)", script)
        self.assertIn("$lease.DeadlineTicks = $nowTicks +", script)
        self.assertIn("Focus-Client -Process $Process -BoundToActiveInputLease", script)
        click_helper = script.split("function Click-ClientRelative", 1)[1].split("function ConvertTo-SendKeysLiteral", 1)[0]
        self.assertLess(
            click_helper.index("Assert-ActiveInputLease -Process $Process"),
            click_helper.index("GetCursorPos([ref]$cursor)"),
        )
        self.assertLess(
            click_helper.index("GetForegroundWindow() -ne $expectedHandle"),
            click_helper.index("mouse_event(0x0002"),
        )
        self.assertIn("function Assert-ActiveInputLease", script)
        runtime_arm_helper = script[
            script.index("function Assert-RuntimeArm") :
            script.index("function Assert-ActiveInputLease")
        ]
        self.assertNotIn("return $arm", runtime_arm_helper)
        self.assertIn("$armSnapshot = Read-ValidatedRuntimeArmSnapshot", runtime_arm_helper)
        snapshot_helper = script[
            script.index("function Read-ValidatedRuntimeArmSnapshot") :
            script.index("function Assert-ActiveInputLease")
        ]
        self.assertIn("[System.IO.File]::ReadAllBytes($runtimeArmPath)", snapshot_helper)
        self.assertIn("Get-ByteArraySha256 -Bytes $armBytes", snapshot_helper)
        self.assertIn("UTF8Encoding]::new($false, $true).GetString($armBytes)", snapshot_helper)
        self.assertIn("Assert-JsonSchema -Json $armJson", snapshot_helper)
        self.assertLess(
            snapshot_helper.index("ReadAllBytes($runtimeArmPath)"),
            snapshot_helper.index("Get-ByteArraySha256 -Bytes $armBytes"),
        )
        self.assertLess(
            snapshot_helper.index("ReadAllBytes($runtimeArmPath)"),
            snapshot_helper.index("ConvertFrom-StrictJson"),
        )
        self.assertNotIn("Get-FileHash", snapshot_helper)
        self.assertNotIn("Get-Content", snapshot_helper)
        self.assertIn("[System.Diagnostics.Stopwatch]::GetTimestamp()", script)
        self.assertIn("ArmFileSha256 = $armFileSha256", script)
        self.assertIn(
            "Hwnd = ConvertFrom-HexHwnd -Value ([string]$arm.hwnd)", script
        )
        lease_helper = script[
            script.index("function Assert-ActiveInputLease") :
            script.index("function Get-ClientProcess")
        ]
        self.assertIn(
            "$currentArmSnapshot = Read-ValidatedRuntimeArmSnapshot",
            lease_helper,
        )
        self.assertIn("$currentArmSha256 -ne [string]$lease.ArmFileSha256", lease_helper)
        self.assertIn("$currentArm.arm_nonce", lease_helper)
        self.assertIn("$currentArm.expires_at", lease_helper)
        self.assertIn(
            "$Process.MainWindowHandle.ToInt64() -ne [long]$lease.Hwnd",
            lease_helper,
        )
        atomic_helper = script[
            script.index("function Send-ClientAtomicToken") :
            script.index("function Send-ClientKeys")
        ]
        self.assertGreaterEqual(
            atomic_helper.count("Assert-ActiveInputLease -Process $Process"), 2
        )
        self.assertLess(
            atomic_helper.rindex("Assert-ActiveInputLease -Process $Process", 0, atomic_helper.index("[System.Windows.Forms.SendKeys]::SendWait($Token)")),
            atomic_helper.index("[System.Windows.Forms.SendKeys]::SendWait($Token)"),
        )
        final_lease = atomic_helper.rindex(
            "Assert-ActiveInputLease -Process $Process",
            0,
            atomic_helper.index("[System.Windows.Forms.SendKeys]::SendWait($Token)"),
        )
        final_foreground = atomic_helper.rindex(
            "GetForegroundWindow()",
            0,
            atomic_helper.index("[System.Windows.Forms.SendKeys]::SendWait($Token)"),
        )
        send = atomic_helper.index("[System.Windows.Forms.SendKeys]::SendWait($Token)")
        final_window_binding = atomic_helper.rindex(
            "Assert-ExactClientWindowBinding",
            0,
            send,
        )
        between_foreground_and_send = atomic_helper[final_foreground:send]
        self.assertLess(final_window_binding, final_lease)
        self.assertGreater(final_foreground, final_lease)
        self.assertNotIn("Start-Sleep", between_foreground_and_send)
        self.assertNotIn("Get-Content", between_foreground_and_send)
        self.assertNotIn("Get-FileHash", between_foreground_and_send)
        click_helper = script[script.index("function Click-ClientRelative") :]
        self.assertLess(
            click_helper.index("Assert-ActiveInputLease -Process $Process"),
            click_helper.index("mouse_event(0x0002"),
        )

    def test_overlength_credentials_and_text_are_refused_before_input(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("$maxObserverAccountLength = 32", script)
        self.assertIn("$maxObserverPasswordLength = 64", script)
        self.assertIn("$maxClientTextLength = 128", script)
        text_helper = script[
            script.index("function Send-ClientText") :
            script.index("function Set-ExplicitUiScale")
        ]
        self.assertLess(
            text_helper.index("$Text.Length -gt $maxClientTextLength"),
            text_helper.index("foreach ($character in $Text.ToCharArray())"),
        )
        credential_helper = script[
            script.index("function Read-ObserverCredential") :
            script.index("try {\n    switch ($Action)")
        ]
        self.assertIn("$account.Length -gt $maxObserverAccountLength", credential_helper)
        self.assertIn("$password.Length -gt $maxObserverPasswordLength", credential_helper)
        login_branch = script[
            script.index("        'Login' {") :
            script.index("        'InspectAddons' {")
        ]
        self.assertLess(
            login_branch.index("$credential = Read-ObserverCredential"),
            login_branch.index("Click-ClientRelative -Process $process"),
        )

    def test_operator_never_embeds_or_prints_a_password(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertNotIn("password = '", script.lower())
        self.assertNotIn("Write-Output $credential", script)
        self.assertNotIn("ConvertTo-Json $credential", script)
        self.assertNotIn("[string]$ExpectedAccount", script)
        self.assertNotIn("[string]$ExpectedCharacter", script)
        self.assertIn("$expectedAccount = 'ADMIN'", script)
        self.assertIn("$expectedCharacter = 'Predator'", script)
        self.assertIn("contains unsupported control characters", script)
        password_click = script.index(
            "Click-ClientRelative -Process $process -X 0.50 -Y 0.63"
        )
        password_write = script.index(
            "Send-ClientText -Process $process -Text $credential.Password",
            password_click,
        )
        password_clear = script.index(
            "Send-ClientKeys -Process $process -Keys '^a'",
            password_click,
        )
        self.assertLess(password_clear, password_write)

    def test_chat_commands_require_a_visually_confirmed_closed_chat(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn(
            "[ValidateSet('LoginScreen', 'CharacterSelect', 'InWorld', 'InWorldChatClosed', 'InWorldPanelOpen', 'WorldMapOpen', 'GameMenuOpen', 'DisconnectedDialog', 'DeadInWorld', 'GhostAtCorpse')]",
            script,
        )
        for action in (
            "SetUiScale80",
            "SetUiScale100",
            "RestoreUiScaleDefault",
            "Logout",
        ):
            block = script[script.index(f"'{action}' {{") :]
            self.assertIn("-ConfirmedVisualState InWorldChatClosed", block)

    def test_operator_refuses_remote_desktop_before_legacy_client_launch(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("SystemInformation]::TerminalServerSession", script)
        launch = script.index("'Launch' {")
        remote_guard = script.index("Assert-LocalInteractiveSession", launch)
        start_process = script.index(
            "Start-Process -FilePath $canonicalClientPath -WorkingDirectory $ClientRoot -PassThru",
            launch,
        )
        self.assertLess(remote_guard, start_process)

    def test_launch_receipt_is_atomic_non_authority_and_exactly_process_bound(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        launch = script[script.index("'Launch' {") : script.index("'ArmSession' {")]
        self.assertIn("Start-Process -FilePath $canonicalClientPath", launch)
        self.assertIn("-PassThru", launch)
        self.assertIn("Wait-ForLaunchedClientWindow -LaunchedProcess $launchedProcess", launch)
        self.assertIn("New-LabLaunchReceipt -Process $process", launch)
        self.assertIn("[System.IO.File]::Move($temporaryPath, $Path, $true)", script)
        self.assertIn("scope = 'lab_evaluation_only'", script)
        self.assertIn("execution_authority = $false", script)
        self.assertIn("receipt_nonce = $nonce", script)
        self.assertIn("Remove-LabLaunchReceipt", script)
        self.assertIn("$identityLock = Enter-LabIdentityMutationLock", launch)
        self.assertLess(
            launch.index("Enter-LabIdentityMutationLock"),
            launch.index("Start-Process -FilePath $canonicalClientPath"),
        )

    def test_v1_receipt_binds_native_creation_ticks_session_and_parent_lineage(self) -> None:
        schema = json.loads(LAUNCH_RECEIPT_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.0")
        for field in (
            "process_created_at_utc",
            "process_creation_filetime_utc",
            "windows_session_id",
            "identity_origin",
            "parent_receipt_nonce",
            "parent_receipt_sha256",
            "parent_authorization_sha256",
            "authorization_semantic_sha256",
        ):
            self.assertIn(field, schema["required"])
        validator = ContractValidator(LAUNCH_RECEIPT_SCHEMA)
        receipt = valid_v1_launch_receipt()
        validator.validate(receipt)

        missing_ticks = copy.deepcopy(receipt)
        del missing_ticks["process_creation_filetime_utc"]
        with self.assertRaises(ContractValidationError):
            validator.validate(missing_ticks)

        rounded_ticks = copy.deepcopy(receipt)
        rounded_ticks["process_creation_filetime_utc"] = 134319092265976450
        with self.assertRaises(ContractValidationError):
            validator.validate(rounded_ticks)

        illegal_parent = copy.deepcopy(receipt)
        illegal_parent["parent_receipt_nonce"] = "22222222-2222-4222-8222-222222222222"
        illegal_parent["parent_receipt_sha256"] = "D" * 64
        illegal_parent["parent_authorization_sha256"] = "E" * 64
        with self.assertRaises(ContractValidationError):
            validator.validate(illegal_parent)

        renewal_without_parent = copy.deepcopy(receipt)
        renewal_without_parent["identity_origin"] = "verified_receipt_renewal"
        with self.assertRaises(ContractValidationError):
            validator.validate(renewal_without_parent)

    def test_process_creation_uses_exact_native_filetime_not_cim_rounding(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        metadata = script[
            script.index("function Get-ExactClientProcessMetadata") :
            script.index("function Assert-ExactPropertySet")
        ]
        self.assertIn("GetProcessTimes", metadata)
        self.assertIn(
            '[DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] public static extern bool QueryFullProcessImageNameW',
            script,
        )
        self.assertIn("$creation.HighDateTime -shl 32", metadata)
        self.assertIn("[DateTime]::FromFileTimeUtc($creationFileTime)", metadata)
        self.assertIn("ProcessCreationFileTimeUtc = $creationFileTime.ToString", metadata)
        self.assertIn("OpenProcess(0x00101000", metadata)
        self.assertIn("OpenProcess(0x00100400", metadata)
        self.assertIn(
            "$limitedQueryError = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()",
            metadata,
        )
        self.assertIn("if ($limitedQueryError -ne 5)", metadata)
        self.assertLess(
            metadata.index("OpenProcess(0x00101000"),
            metadata.index("GetLastWin32Error()"),
        )
        self.assertLess(
            metadata.index("if ($limitedQueryError -ne 5)"),
            metadata.index("OpenProcess(0x00100400"),
        )
        non_access_denied_guard = metadata[
            metadata.index("if ($limitedQueryError -ne 5)") :
            metadata.index("OpenProcess(0x00100400")
        ]
        self.assertIn("throw", non_access_denied_guard)
        self.assertIn("$managedSessionId = [int]$Process.SessionId", metadata)
        self.assertIn("Native and managed Windows session identity disagree", metadata)
        self.assertNotIn("Get-CimInstance", metadata)
        receipt_guard = script[
            script.index("function Assert-LabLaunchReceipt") :
            script.index("function Read-OperatorAuditSnapshot")
        ]
        self.assertIn(
            "Assert-ExactProcessCreationBinding",
            receipt_guard,
        )
        creation_guard = powershell_function(script, "Assert-ExactProcessCreationBinding")
        self.assertIn("UtcDateTime.ToFileTimeUtc().ToString", creation_guard)
        self.assertIn("native creation FILETIME", creation_guard)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_native_filetime_two_tick_string_mismatch_is_rejected_at_runtime(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        helper = powershell_function(script, "Assert-ExactProcessCreationBinding")
        source = helper + r'''
$metadata = [pscustomobject]@{ ProcessCreationFileTimeUtc = '134319092265976452' }
$createdAt = [DateTimeOffset]::Parse('2026-08-22T21:53:49Z')
$exact = [pscustomobject]@{
    process_created_at_utc = '2026-08-22T21:53:46.5976452Z'
    process_creation_filetime_utc = '134319092265976452'
}
Assert-ExactProcessCreationBinding -Receipt $exact -Metadata $metadata -ReceiptCreatedAt $createdAt
$rounded = [pscustomobject]@{
    process_created_at_utc = '2026-08-22T21:53:46.5976450Z'
    process_creation_filetime_utc = '134319092265976450'
}
try {
    Assert-ExactProcessCreationBinding -Receipt $rounded -Metadata $metadata -ReceiptCreatedAt $createdAt
    throw 'two-tick mismatch was accepted'
}
catch {
    if ($_.Exception.Message -notmatch 'native creation FILETIME') { throw }
}
'''
        result = run_powershell_source(source)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_adoption_and_renewal_are_acknowledged_zero_input_identity_mutations(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("[switch]$AcknowledgeSessionIdentity", script)
        for action, next_action in (
            ("AdoptSession", "RenewSessionIdentity"),
            ("RenewSessionIdentity", "ArmSession"),
        ):
            branch = script[
                script.index(f"        '{action}' {{") :
                script.index(f"        '{next_action}' {{")
            ]
            self.assertIn("AcknowledgeSessionIdentity", branch)
            self.assertIn("Get-SingleWowProcess", branch)
            self.assertIn("input_tokens_sent = 0", branch)
            self.assertIn("parent_receipt_nonce", branch)
            self.assertIn("parent_receipt_sha256", branch)
            self.assertIn("receipt_sha256", branch)
            self.assertNotIn("Focus-Client", branch)
            self.assertNotIn("Send-Client", branch)
            self.assertNotIn("Click-ClientRelative", branch)
            self.assertNotIn("Save-ClientCheckpoint", branch)
            self.assertNotIn("Start-Process", branch)
            self.assertNotIn("Stop-Process", branch)
            self.assertNotIn("WaitForExit", branch)
        adoption = script[
            script.index("        'AdoptSession' {") :
            script.index("        'RenewSessionIdentity' {")
        ]
        self.assertIn("schema_version -ne '0.1'", adoption)
        self.assertIn("Assert-ExactLegacyV01Continuity", adoption)
        self.assertIn("legacy_v0_1_continuity_adoption", adoption)
        renewal = script[
            script.index("        'RenewSessionIdentity' {") :
            script.index("        'ArmSession' {")
        ]
        self.assertIn("Assert-LabLaunchReceipt -Process $process -AllowExpired", renewal)
        self.assertIn("verified_receipt_renewal", renewal)

    def test_explicit_window_rebind_preserves_all_process_identity_checks(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("[switch]$AcknowledgeWindowRebind", script)
        receipt_check_start = script.index("function Assert-LabLaunchReceiptSnapshot")
        receipt_check = script[
            receipt_check_start :
            script.index("function Assert-LabLaunchReceipt {", receipt_check_start)
        ]
        self.assertIn("Assert-ExactProcessCreationBinding", receipt_check)
        self.assertIn("$receipt.pid -ne $Process.Id", receipt_check)
        self.assertIn("$receipt.windows_session_id -ne $metadata.WindowsSessionId", receipt_check)
        self.assertIn("$receipt.executable_sha256 -ne $expectedClientSha256", receipt_check)
        self.assertIn("Assert-ClientExecutableIdentity", receipt_check)
        self.assertIn("Assert-V1ReceiptIssuanceCommit", receipt_check)
        self.assertIn("if ($AllowWindowRebind)", receipt_check)
        self.assertIn("Assert-ExactClientWindowBinding -Process $Process)", receipt_check)
        self.assertIn(
            "Assert-ExactClientWindowBinding -Process $Process -ExpectedHwnd $receiptHwnd",
            receipt_check,
        )
        renewal = script[
            script.index("        'RenewSessionIdentity' {") :
            script.index("        'ArmSession' {")
        ]
        self.assertIn("if ($AcknowledgeWindowRebind)", renewal)
        self.assertIn("-AllowWindowRebind", renewal)
        self.assertIn("window_rebound = [bool]$AcknowledgeWindowRebind", renewal)
        self.assertNotIn("Focus-Client", renewal)
        self.assertNotIn("Send-Client", renewal)

    def test_legacy_adoption_is_one_time_and_requires_exact_launch_continuity(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        continuity = script[
            script.index("function Assert-ExactLegacyV01Continuity") :
            script.index("function Wait-ForLaunchedClientWindow")
        ]
        for evidence in (
            "$processCreatedAt -gt $createdAt",
            ".TotalSeconds -gt 60",
            "$metadata.WindowsSessionId -ne $operatorSessionId",
            "[int]$receipt.pid -ne $Process.Id",
            "Assert-ExactClientWindowBinding",
            "Assert-ExactLegacyLaunchAuditLineage",
            "Assert-ParentReceiptUnused",
        ):
            self.assertIn(evidence, continuity)
        lineage = script[
            script.index("function Assert-ExactLegacyLaunchAuditLineage") :
            script.index("function Assert-ParentReceiptUnused")
        ]
        self.assertIn("$matches.Count -ne 1", lineage)
        self.assertIn("entry.details.launch_receipt_nonce", lineage)
        self.assertIn("entry.details.receipt_expires_at", lineage)
        self.assertIn("entry.details.pid", lineage)
        self.assertIn("entry.details.hwnd", lineage)
        self.assertIn("$occurredAt -le $createdAt.AddSeconds(60)", lineage)
        self.assertIn("Assert-LegacyLaunchAuditIdentityTypes", lineage)
        self.assertIn("AuditFileSha256", lineage)
        self.assertIn("AuditEntrySha256", lineage)

    def test_identity_replacement_revokes_arm_before_atomic_receipt_write(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        receipt_writer = script[
            script.index("function New-LabLaunchReceipt") :
            script.index("function Assert-LabLaunchReceipt")
        ]
        self.assertLess(
            receipt_writer.index("Remove-LabRuntimeArm"),
            receipt_writer.index("Write-AtomicImmutableJsonRecord"),
        )
        self.assertLess(
            receipt_writer.index("Write-AtomicImmutableJsonRecord"),
            receipt_writer.index("Write-AtomicJsonRecord -Path $launchReceiptPath"),
        )
        self.assertIn("Enter-LabIdentityMutationLock", script)
        self.assertIn("[System.IO.FileShare]::None", script)

    def test_identity_issuance_schema_binds_commit_origin_parent_and_receipt(self) -> None:
        validator = ContractValidator(IDENTITY_ISSUANCE_SCHEMA)
        marker, _ = valid_identity_issuance()
        validator.validate(marker)

        wrong_origin = copy.deepcopy(marker)
        wrong_origin["identity_origin"] = "verified_receipt_renewal"
        with self.assertRaises(ContractValidationError):
            validator.validate(wrong_origin)

        receipt = valid_v1_launch_receipt()
        receipt["identity_origin"] = "legacy_v0_1_continuity_adoption"
        receipt["parent_receipt_nonce"] = "22222222-2222-4222-8222-222222222222"
        receipt["parent_receipt_sha256"] = "F" * 64
        receipt["parent_authorization_sha256"] = "A" * 64
        adopted_marker, _ = valid_identity_issuance(receipt)
        validator.validate(adopted_marker)
        adopted_marker["legacy_launch_audit_entry_sha256"] = None
        with self.assertRaises(ContractValidationError):
            validator.validate(adopted_marker)

    def test_v1_identity_trust_uses_immutable_commit_not_jsonl(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        receipt_assertion = powershell_function(script, "Assert-LabLaunchReceiptSnapshot")
        self.assertIn("Assert-V1ReceiptIssuanceCommit", receipt_assertion)
        self.assertNotIn("OperatorAudit", receipt_assertion)
        parent_guard = powershell_function(script, "Assert-ParentReceiptUnused")
        self.assertIn("Get-LabIdentityIssuanceSnapshots", parent_guard)
        self.assertNotIn("OperatorAudit", parent_guard)
        recovery = powershell_function(script, "Complete-CommittedIdentityProjection")
        self.assertIn("Assert-LabLaunchReceiptSnapshot", recovery)
        self.assertIn("Write-LabLaunchReceiptProjectionFromCommit", recovery)
        self.assertIn("Committed LAB identity lineage forks", recovery)
        self.assertIn("Write-OperatorObservationSafely", script)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_identity_issuance_runtime_rejects_embedded_receipt_hash_mismatch(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        helpers = "\n".join(
            powershell_function(script, name)
            for name in (
                "Assert-JsonSchema",
                "Get-ByteArraySha256",
                "ConvertFrom-StrictJson",
                "Get-LabIdentityIssuancePath",
                "Read-LabIdentityIssuanceSnapshot",
            )
        )
        marker, _ = valid_identity_issuance()

        def invoke(record: dict[str, object]) -> subprocess.CompletedProcess[str]:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                issuance_root = root / "identity-issuances"
                issuance_root.mkdir()
                nonce = str(record["new_receipt_nonce"])
                (issuance_root / f"{nonce.lower()}.json").write_text(
                    json.dumps(record, separators=(",", ":")),
                    encoding="utf-8",
                )
                quoted_root = str(issuance_root).replace("'", "''")
                quoted_marker_schema = str(IDENTITY_ISSUANCE_SCHEMA).replace("'", "''")
                quoted_receipt_schema = str(LAUNCH_RECEIPT_SCHEMA).replace("'", "''")
                source = helpers + f"""
$identityIssuanceRoot = '{quoted_root}'
$identityIssuanceSchemaPath = '{quoted_marker_schema}'
$launchReceiptSchemaPath = '{quoted_receipt_schema}'
[void](Read-LabIdentityIssuanceSnapshot -ReceiptNonce '{nonce}')
"""
                return run_powershell_source(source)

        valid_result = invoke(marker)
        self.assertEqual(
            valid_result.returncode,
            0,
            valid_result.stderr + valid_result.stdout,
        )
        mismatched = copy.deepcopy(marker)
        receipt_bytes = base64.b64decode(str(mismatched["receipt_utf8_base64"]))
        mismatched["receipt_utf8_base64"] = base64.b64encode(
            receipt_bytes + b" "
        ).decode("ascii")
        mismatch_result = invoke(mismatched)
        self.assertNotEqual(mismatch_result.returncode, 0)
        self.assertIn(
            "embedded receipt hash does not match",
            mismatch_result.stderr + mismatch_result.stdout,
        )

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_atomic_commit_is_idempotent_and_projection_recovers_after_commit(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        helpers = "\n".join(
            powershell_function(script, name)
            for name in (
                "Get-ByteArraySha256",
                "ConvertFrom-StrictJson",
                "Write-DurableUtf8Text",
                "Write-AtomicJsonRecord",
                "Write-AtomicImmutableJsonRecord",
                "Write-LabLaunchReceiptProjectionFromCommit",
            )
        )
        _, receipt_bytes = valid_identity_issuance()
        receipt = valid_v1_launch_receipt()
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest().upper()
        encoded_receipt = base64.b64encode(receipt_bytes).decode("ascii")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker_path = root / "commit.json"
            receipt_path = root / "receipt.json"
            quoted_marker = str(marker_path).replace("'", "''")
            quoted_receipt = str(receipt_path).replace("'", "''")
            source = helpers + f"""
$launchReceiptPath = '{quoted_receipt}'
$markerPath = '{quoted_marker}'
$nonce = '{receipt['receipt_nonce']}'
Write-AtomicImmutableJsonRecord -Path $markerPath -Json '{{"commit":1}}' -Nonce $nonce
Write-AtomicImmutableJsonRecord -Path $markerPath -Json '{{"commit":1}}' -Nonce $nonce
try {{
    Write-AtomicImmutableJsonRecord -Path $markerPath -Json '{{"commit":2}}' -Nonce $nonce
    throw 'immutable overwrite was accepted'
}}
catch {{
    if ($_.Exception.Message -notmatch 'different bytes') {{ throw }}
}}
$snapshot = [pscustomobject]@{{
    Bytes = [Convert]::FromBase64String('{encoded_receipt}')
    Sha256 = '{receipt_sha}'
    Record = [pscustomobject]@{{ receipt_nonce = $nonce }}
}}
Write-LabLaunchReceiptProjectionFromCommit -ReceiptSnapshot $snapshot
Write-LabLaunchReceiptProjectionFromCommit -ReceiptSnapshot $snapshot
if ((Get-Content -Raw -LiteralPath $markerPath) -ne '{{"commit":1}}') {{ throw 'marker changed' }}
"""
            result = run_powershell_source(source)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue(
                receipt_path.exists(),
                result.stderr + result.stdout,
            )
            self.assertEqual(receipt_path.read_bytes(), receipt_bytes)

    def test_authorization_rollover_is_temporal_only_and_semantically_exact(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        semantic = script[
            script.index("function ConvertTo-CanonicalJsonNode") :
            script.index("$ErrorActionPreference")
        ]
        for excluded_temporal_field in (
            "recorded_at",
            "expires_at",
            "renews_authorization_sha256",
            "renewal_scope",
        ):
            self.assertIn(excluded_temporal_field, semantic)
        continuity = script[
            script.index("function Assert-AuthorizationContinuity") :
            script.index("function New-LocalRealmAssuranceRecord")
        ]
        self.assertIn(
            "$Receipt.authorization_semantic_sha256 -ne $authorizationSemanticSha256",
            continuity,
        )
        self.assertIn("Parent receipt authorization semantics differ", continuity)
        self.assertIn("$parentAuthorizationSha256 -ne $authorizationSha256", continuity)
        self.assertIn("approval.renewal_scope -ne 'temporal_only'", continuity)
        self.assertIn(
            "approval.renews_authorization_sha256 -ne $parentAuthorizationSha256",
            continuity,
        )
        self.assertIn("Authorization hash rollover is not an explicit", continuity)
        for action in ("AdoptSession", "RenewSessionIdentity"):
            start = script.index(f"        '{action}' {{")
            next_branch = script.index("\n        '", start + 10)
            branch = script[start:next_branch]
            self.assertIn("parent_authorization_sha256", branch)
            self.assertIn("new_authorization_sha256", branch)
            self.assertIn("new_authorization_semantic_sha256", branch)

    def test_active_approval_window_is_rechecked_and_cannot_exceed_cap(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        helper = script[
            script.index("function Assert-ActiveTargetAuthorization") :
            script.index("function ConvertFrom-HexHwnd")
        ]
        self.assertIn("$authorizationTemporalState -ne 'active'", helper)
        self.assertIn("$approvalRecordedAt -gt $now", helper)
        self.assertIn("$authorizationExpiresAt -le $now", helper)
        self.assertIn(
            "$authorizationExpiresAt -gt $approvalRecordedAt.AddMinutes($maxSessionMinutes)",
            helper,
        )
        temporal_setup = script[
            script.index("$authorizationTemporalState = 'invalid'") :
            script.index("$expectedClientSha256")
        ]
        self.assertIn("$authorizationBound = $approvalRecordedAt.AddMinutes", temporal_setup)
        self.assertIn("$authorizationExpiresAt = $authorizationBound", temporal_setup)
        self.assertIn("$configuredAuthorizationExpiresAt -gt $authorizationBound", temporal_setup)
        bounded_expiry = powershell_function(script, "Get-BoundedExpiry")
        self.assertIn("$authorizationExpiresAt -lt $expiresAt", bounded_expiry)

    def test_status_reports_expired_identity_without_asserting_active_receipt(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        status_branch = script[
            script.index("        'Status' {") : script.index("        'Launch' {")
        ]
        self.assertIn("Get-Process -Name Wow", status_branch)
        self.assertIn("Get-LabLaunchIdentityStatus", status_branch)
        self.assertNotIn("Get-ClientProcess", status_branch)
        self.assertNotIn("Assert-LabLaunchReceipt", status_branch)
        status_helper = script[
            script.index("function Get-LabLaunchIdentityStatus") :
            script.index("function Read-ObserverCredential")
        ]
        self.assertIn("unverified_v1_expired", status_helper)
        self.assertIn("unverified_legacy_v0_1_expired", status_helper)
        self.assertIn("identity_verified = $false", status_helper)
        self.assertIn("observed_pid_matches_receipt", status_helper)
        self.assertNotIn("process_match", status_helper)
        self.assertNotIn("window_title -eq", status_helper)
        self.assertNotIn("window_class -eq", status_helper)
        self.assertIn("catch {", status_helper)
        self.assertIn("malformed_or_untrusted", status_helper)

    def test_disconnect_acknowledgement_is_one_visually_gated_enter(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        branch = script[
            script.index("        'AcknowledgeDisconnect' {") :
            script.index("        'ReleaseSpirit' {")
        ]
        self.assertIn("-ConfirmedVisualState DisconnectedDialog", branch)
        self.assertIn("Assert-RuntimeArm -Name $Action -Process $process", branch)
        self.assertEqual(
            branch.count("Send-ClientKeys -Process $process -Keys '{ENTER}'"), 1
        )
        self.assertNotIn("/logout", branch)
        self.assertNotIn("%{F4}", branch)
        self.assertIn("input_token_count = 1", branch)

    def test_login_error_acknowledgement_is_one_login_gated_enter(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        branch = script[
            script.index("        'AcknowledgeLoginError' {") :
            script.index("        'AcknowledgeDisconnect' {")
        ]
        self.assertIn("-ConfirmedVisualState LoginScreen", branch)
        self.assertIn("Assert-RuntimeArm -Name $Action -Process $process", branch)
        self.assertEqual(
            branch.count("Send-ClientKeys -Process $process -Keys '{ENTER}'"), 1
        )
        self.assertIn("input_token_count = 1", branch)

    def test_death_actions_are_single_input_and_separately_state_gated(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        release = script[
            script.index("        'ReleaseSpirit' {") :
            script.index("        'RetrieveCorpse' {")
        ]
        self.assertIn("-ConfirmedVisualState DeadInWorld", release)
        self.assertEqual(
            release.count(
                "Click-ClientRelative -Process $process -X 0.50 -Y 0.232"
            ),
            1,
        )
        self.assertNotIn("Send-ClientKeys", release)
        self.assertIn("input_token_count = 1", release)

        retrieve = script[
            script.index("        'RetrieveCorpse' {") :
            script.index("        'ToggleEnemyNameplates' {")
        ]
        self.assertIn("-ConfirmedVisualState GhostAtCorpse", retrieve)
        self.assertEqual(
            retrieve.count(
                "Click-ClientRelative -Process $process -X 0.50 -Y 0.232"
            ),
            1,
        )
        self.assertNotIn("Send-ClientKeys", retrieve)
        self.assertNotIn("Send-ClientKeys -Process $process -Keys '{ENTER}'", retrieve)
        self.assertIn("input_token_count = 1", retrieve)

    def test_game_menu_is_dismissed_through_explicit_return_control(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        dismiss = script[
            script.index("        'DismissGameMenu' {") :
            script.index("        'ReloadUi' {")
        ]
        self.assertIn("'GameMenuOpen', 'InWorldPanelOpen'", dismiss)
        self.assertIn(
            "Click-ClientRelative -Process $process -X 0.50 -Y 0.610",
            dismiss,
        )
        self.assertIn("Send-ClientKeys -Process $process -Keys '{ESC}'", dismiss)

        save = script[
            script.index("        'SaveShadowReplay' {") :
            script.index("        'Logout' {")
        ]
        self.assertIn("Send-ClientKeys -Process $process -Keys '%{F10}'", save)
        self.assertIn(
            "Click-ClientRelative -Process $process -X 0.50 -Y 0.610",
            save,
        )
        self.assertNotIn("Send-ClientKeys -Process $process -Keys '{ESC}'", save)

    def test_runtime_arm_is_explicit_bounded_and_checked_for_every_input_action(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("[switch]$AcknowledgeRuntimeArm", script)
        self.assertIn("ArmSession requires -AcknowledgeRuntimeArm", script)
        self.assertIn("function Assert-RuntimeArm", script)
        self.assertIn("approval.max_session_minutes", script)
        self.assertIn("scope = 'lab_operator_bounded_input'", script)
        self.assertIn("execution_authority = $true", script)
        self.assertEqual(
            script.count("Assert-RuntimeArm -Name $Action -Process $process"),
            len(INPUT_ACTIONS),
        )
        switch_start = script.index("try {\n    switch ($Action)")
        switch_body = script[switch_start:]
        for action in INPUT_ACTIONS:
            with self.subTest(action=action):
                branch_start = switch_body.index(f"        '{action}' {{")
                next_branch = switch_body.find("\n        '", branch_start + 1)
                branch = switch_body[
                    branch_start : next_branch if next_branch >= 0 else None
                ]
                self.assertIn(
                    "Assert-RuntimeArm -Name $Action -Process $process",
                    branch,
                )

    def test_realm_gate_pins_realmlist_and_listener_owner_images(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn("function Assert-ExactLabRealm", script)
        self.assertIn("set realmlist 127.0.0.1", script)
        self.assertIn("[System.IO.File]::ReadAllBytes", script)
        self.assertIn("$actualHash -ne $expectedRealmlistSha256", script)
        self.assertIn("$ownerHash -ne [string]$binding.executable_sha256", script)
        self.assertIn("$owner.ProcessName -ne [string]$binding.process_name", script)
        self.assertIn("ParseCommandLine([string]$ownerInfo.CommandLine)", script)
        self.assertIn("$binding.command_line_arguments", script)
        self.assertIn("$configHash -ne [string]$binding.config_sha256", script)
        self.assertIn("command line does not reference its pinned config file", script)
        self.assertIn("function Assert-ExactRealmRoutingRecord", script)
        self.assertIn("FROM realmlist ORDER BY id", script)
        self.assertIn("$env:MYSQL_PWD = $databasePassword", script)
        self.assertIn("$databasePassword = $null", script)
        self.assertIn("$actualRoutingSha256 -ne $expectedRoutingSha256", script)
        self.assertIn("realm_routing_sha256 = $routing.Sha256", script)
        self.assertNotIn("Write-Output $databasePassword", script)
        self.assertNotIn("Write-Output $secrets", script)
        self.assertNotIn("Write-Output $ownerInfo.CommandLine", script)
        runtime_gate = script[script.index("function Assert-RuntimeArm") :]
        self.assertLess(
            runtime_gate.index("Assert-LabReady"),
            runtime_gate.index("$armSnapshot = Read-ValidatedRuntimeArmSnapshot"),
        )

    def test_runtime_artifact_schemas_are_strict_and_separate_identity_from_arm(self) -> None:
        launch_schema = json.loads(LAUNCH_RECEIPT_SCHEMA.read_text(encoding="utf-8"))
        arm_schema = json.loads(RUNTIME_ARM_SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(launch_schema["properties"]["execution_authority"]["const"])
        self.assertTrue(arm_schema["properties"]["execution_authority"]["const"])
        self.assertEqual(
            set(arm_schema["properties"]["allowed_actions"]["items"]["enum"]),
            set(INPUT_ACTIONS),
        )
        self.assertFalse(launch_schema["additionalProperties"])
        self.assertFalse(arm_schema["additionalProperties"])
        for schema in (launch_schema, arm_schema):
            self.assertIn("actor_binding", schema["required"])
            self.assertIn("expected_realm_fingerprint", schema["required"])
            self.assertIn("realm_assurance", schema["required"])
            self.assertIn("realm_routing_sha256", schema["required"])
            self.assertEqual(
                schema["$defs"]["actorBinding"]["properties"][
                    "expected_character_name"
                ]["const"],
                "Predator",
            )
            self.assertEqual(
                schema["$defs"]["actorBinding"]["properties"][
                    "binding_assurance"
                ]["properties"]["state"]["const"],
                "configured_expected_only",
            )
        self.assertEqual(
            launch_schema["$defs"]["realmAssurance"]["properties"]["state"][
                "const"
            ],
            "local_process_config_verified_at_launch",
        )
        self.assertEqual(
            arm_schema["$defs"]["realmAssurance"]["properties"]["state"][
                "const"
            ],
            "local_process_config_revalidated_at_arm",
        )
        for schema in (launch_schema, arm_schema):
            self.assertEqual(
                schema["$defs"]["realmAssurance"]["properties"]["method"][
                    "const"
                ],
                "exact_realmlist_listener_process_config_and_realm_route",
            )
        self.assertNotIn("realm_fingerprint", launch_schema["properties"])
        self.assertNotIn("realm_fingerprint", arm_schema["properties"])
        ContractValidator(LAUNCH_RECEIPT_SCHEMA)
        ContractValidator(RUNTIME_ARM_SCHEMA)
        ContractValidator(IDENTITY_ISSUANCE_SCHEMA)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_operator_rejects_malformed_authorization_before_json_trust(self) -> None:
        result = run_operator_with_authorization("{not-json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("JSON", result.stderr + result.stdout)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_operator_rejects_duplicate_authorization_keys_at_root_and_nested(self) -> None:
        raw = AUTHORIZATION.read_text(encoding="utf-8")
        duplicate_root = raw.replace(
            "{", '{\n  "target_profile": "shadow-profile",', 1
        )
        root_result = run_operator_with_authorization(duplicate_root)
        self.assertNotEqual(root_result.returncode, 0)
        self.assertIn("JSON", root_result.stderr + root_result.stdout)

        duplicate_nested = raw.replace(
            '"client_match": {',
            '"client_match": {\n    "executable_sha256": "' + "A" * 64 + '",',
            1,
        )
        nested_result = run_operator_with_authorization(duplicate_nested)
        self.assertNotEqual(nested_result.returncode, 0)
        self.assertIn("JSON", nested_result.stderr + nested_result.stdout)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_operator_rejects_comments_and_trailing_commas_before_authorization_trust(self) -> None:
        raw = AUTHORIZATION.read_text(encoding="utf-8")
        with_comment = raw.replace("{", "{/*not-json*/", 1)
        comment_result = run_operator_with_authorization(with_comment)
        self.assertNotEqual(comment_result.returncode, 0)
        self.assertIn("JSON", comment_result.stderr + comment_result.stdout)

        trailing_comma = raw.rstrip()
        trailing_comma = trailing_comma[:-1] + ",}"
        comma_result = run_operator_with_authorization(trailing_comma)
        self.assertNotEqual(comma_result.returncode, 0)
        self.assertIn("JSON", comma_result.stderr + comma_result.stdout)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_legacy_receipt_duplicate_comment_and_trailing_comma_are_diagnostic_only(self) -> None:
        canonical = json.dumps(valid_legacy_v01_launch_receipt())
        malformed_receipts = (
            canonical.replace(
                "{", '{"schema_version":"0.1",', 1
            ),
            canonical.replace("{", "{/*not-json*/", 1),
            canonical[:-1] + ",}",
        )
        for malformed in malformed_receipts:
            with self.subTest(receipt=malformed[:40]):
                result = run_operator_status_with_receipt(malformed)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                status = json.loads(result.stdout)
                self.assertEqual(
                    status["launch_identity"]["state"],
                    "malformed_or_untrusted",
                )

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_legacy_receipt_rejects_json_type_coercion_at_root_and_nested(self) -> None:
        valid_result = run_operator_status_with_receipt(
            json.dumps(valid_legacy_v01_launch_receipt())
        )
        self.assertEqual(
            valid_result.returncode,
            0,
            valid_result.stderr + valid_result.stdout,
        )
        self.assertIn(
            json.loads(valid_result.stdout)["launch_identity"]["state"],
            {"unverified_legacy_v0_1_present", "unverified_legacy_v0_1_expired"},
        )
        mutations = []
        pid_string = valid_legacy_v01_launch_receipt()
        pid_string["pid"] = "1234"
        mutations.append(pid_string)
        authority_number = valid_legacy_v01_launch_receipt()
        authority_number["execution_authority"] = 0
        mutations.append(authority_number)
        actor_number = valid_legacy_v01_launch_receipt()
        actor_number["actor_binding"]["actor_id"] = 7
        mutations.append(actor_number)
        evidence_number = valid_legacy_v01_launch_receipt()
        evidence_number["actor_binding"]["binding_assurance"]["evidence_refs"] = [1]
        mutations.append(evidence_number)
        realm_number = valid_legacy_v01_launch_receipt()
        realm_number["realm_assurance"]["verified_at"] = 1
        mutations.append(realm_number)

        for receipt in mutations:
            with self.subTest(receipt=receipt):
                result = run_operator_status_with_receipt(json.dumps(receipt))
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertEqual(
                    json.loads(result.stdout)["launch_identity"]["state"],
                    "malformed_or_untrusted",
                )

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_legacy_launch_audit_identity_types_reject_pid_string_at_runtime(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        helpers = "\n".join(
            powershell_function(script, name)
            for name in (
                "ConvertFrom-StrictJson",
                "Get-ExactJsonTokenType",
                "Get-RequiredJsonPropertyToken",
                "Assert-JsonPropertyTokenType",
                "Assert-LegacyLaunchAuditIdentityTypes",
            )
        )
        audit = {
            "occurred_at": "2026-08-22T21:53:49Z",
            "actor": "external_lab_operator_harness",
            "action": "Launch",
            "result": "complete",
            "expected_account": "PA_OBSERVER",
            "expected_character": "Predator",
            "instance_id": "lab-instance",
            "actor_id": "lab-actor",
            "actor_role": "lab_clone",
            "decision_context": "lab_clone",
            "memory_namespace": "memory:lab:test",
            "predator_execution_mode": "OBSERVE_ONLY",
            "details": {
                "checkpoint": "checkpoint.png",
                "pid": 1234,
                "hwnd": "0xABC",
                "launch_receipt_nonce": "11111111-1111-4111-8111-111111111111",
                "receipt_expires_at": "2026-08-22T22:23:49Z",
            },
        }

        def invoke(record: dict[str, object]) -> subprocess.CompletedProcess[str]:
            encoded = base64.b64encode(
                json.dumps(record, separators=(",", ":")).encode("utf-8")
            ).decode("ascii")
            source = helpers + f"""
$json = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'))
$strict = ConvertFrom-StrictJson -Json $json -RecordName 'audit' -IncludeToken
Assert-LegacyLaunchAuditIdentityTypes -Token $strict.Token
"""
            return run_powershell_source(source)

        valid_result = invoke(audit)
        self.assertEqual(
            valid_result.returncode,
            0,
            valid_result.stderr + valid_result.stdout,
        )
        wrong_type = copy.deepcopy(audit)
        wrong_type["details"]["pid"] = "1234"
        wrong_result = invoke(wrong_type)
        self.assertNotEqual(wrong_result.returncode, 0)
        self.assertIn("exact JSON Integer", wrong_result.stderr + wrong_result.stdout)

    def test_all_identity_authority_json_is_strict_parsed_from_one_snapshot(self) -> None:
        script = OPERATOR.read_text(encoding="utf-8")
        helper = script[
            script.index("function ConvertFrom-StrictJson") :
            script.index("$ErrorActionPreference")
        ]
        self.assertIn("DuplicatePropertyNameHandling", helper)
        self.assertIn("DuplicatePropertyNameHandling]::Error", helper)
        self.assertIn("Test-Json -Json $Json -ErrorAction Stop", helper)
        self.assertIn("JToken]::Parse($Json, $loadSettings)", helper)
        self.assertIn("ConvertFrom-Json -DateKind String", helper)
        self.assertEqual(script.count("ConvertFrom-Json"), 1)
        self.assertIn(
            "ConvertFrom-StrictJson -Json $authorizationJson -RecordName 'LAB target authorization'",
            script,
        )
        receipt_reader = script[
            script.index("function Read-LabLaunchReceiptSnapshot") :
            script.index("function Remove-LabLaunchReceipt")
        ]
        self.assertLess(
            receipt_reader.index("ReadAllBytes($launchReceiptPath)"),
            receipt_reader.index("ConvertFrom-StrictJson -Json $receiptJson"),
        )
        self.assertEqual(receipt_reader.count("ReadAllBytes($launchReceiptPath)"), 1)
        issuance_reader = powershell_function(
            script, "Read-LabIdentityIssuanceSnapshot"
        )
        self.assertIn("[System.IO.File]::ReadAllBytes($path)", issuance_reader)
        self.assertIn(
            "ConvertFrom-StrictJson -Json $markerJson",
            issuance_reader,
        )
        self.assertIn(
            "Assert-JsonSchema -Json $markerJson",
            issuance_reader,
        )
        arm_reader = script[
            script.index("function Read-ValidatedRuntimeArmSnapshot") :
            script.index("function Assert-ActiveInputLease")
        ]
        self.assertLess(
            arm_reader.index("ReadAllBytes($runtimeArmPath)"),
            arm_reader.index("ConvertFrom-StrictJson -Json $armJson"),
        )
        self.assertEqual(arm_reader.count("ReadAllBytes($runtimeArmPath)"), 1)
        audit_reader = script[
            script.index("function Read-OperatorAuditSnapshot") :
            script.index("function Test-OperatorAuditIdentityEnvelope")
        ]
        self.assertIn("ConvertFrom-StrictJson -Json $line", audit_reader)
        self.assertIn("-IncludeToken", audit_reader)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_operator_accepts_no_predator_execution_mode_for_fixed_ui(self) -> None:
        authorization = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
        authorization["permitted_modes"] = []
        result = run_operator_with_authorization(json.dumps(authorization))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_operator_rejects_missing_fixed_ui_capability(self) -> None:
        authorization = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
        authorization["permitted_capabilities"].remove("LAB_OPERATOR_FIXED_UI")
        result = run_operator_with_authorization(json.dumps(authorization))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "not an approved exact local-emulator identity",
            result.stderr + result.stdout,
        )

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_operator_rejects_session_limit_above_absolute_cap(self) -> None:
        authorization = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
        authorization["approval"]["max_session_minutes"] = 61
        result = run_operator_with_authorization(json.dumps(authorization))
        self.assertNotEqual(result.returncode, 0)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_operator_rejects_future_approval(self) -> None:
        authorization = active_authorization()
        authorization["approval"]["recorded_at"] = "2999-01-01T00:00:00Z"
        authorization["approval"]["expires_at"] = "2999-01-01T00:10:00Z"
        result = run_operator_with_authorization(
            json.dumps(authorization), action="AdoptSession"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("recorded_at is in the future", result.stderr + result.stdout)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_authority_derives_missing_expiry_and_rejects_expired_or_overlong(self) -> None:
        derived = active_authorization()
        del derived["approval"]["expires_at"]
        derived_status = run_operator_with_authorization(json.dumps(derived))
        self.assertEqual(
            derived_status.returncode,
            0,
            derived_status.stderr + derived_status.stdout,
        )
        derived_payload = json.loads(derived_status.stdout)
        self.assertEqual(derived_payload["authorization"]["state"], "active")
        self.assertIsNone(derived_payload["authorization"]["expires_at"])
        self.assertEqual(
            derived_payload["authorization"]["expiry_source"],
            "derived_recorded_at_plus_max_session_minutes",
        )
        expected_expiry = datetime.fromisoformat(
            str(derived["approval"]["recorded_at"])
        ) + timedelta(minutes=int(derived["approval"]["max_session_minutes"]))
        effective_expiry = datetime.fromisoformat(
            derived_payload["authorization"]["effective_expires_at"]
        )
        self.assertEqual(effective_expiry, expected_expiry)

        derived_action = run_operator_with_authorization(
            json.dumps(derived), action="AdoptSession"
        )
        self.assertNotEqual(derived_action.returncode, 0)
        derived_action_output = derived_action.stderr + derived_action.stdout
        self.assertTrue(
            "no operator launch receipt" in derived_action_output.lower()
            or "no wow.exe process is running" in derived_action_output.lower(),
            derived_action_output,
        )
        self.assertNotIn(
            "no active bounded approval window",
            derived_action_output,
        )

        expired = active_authorization()
        now = datetime.now(timezone.utc)
        expired["approval"]["recorded_at"] = (now - timedelta(minutes=20)).isoformat()
        expired["approval"]["expires_at"] = (now - timedelta(minutes=10)).isoformat()
        expired_result = run_operator_with_authorization(
            json.dumps(expired), action="AdoptSession"
        )
        self.assertNotEqual(expired_result.returncode, 0)
        self.assertIn(
            "effective approval expiry is not in the future",
            expired_result.stderr + expired_result.stdout,
        )

        overlong = active_authorization()
        overlong["approval"]["recorded_at"] = (now - timedelta(minutes=1)).isoformat()
        overlong["approval"]["expires_at"] = (now + timedelta(minutes=30)).isoformat()
        overlong_result = run_operator_with_authorization(
            json.dumps(overlong), action="AdoptSession"
        )
        self.assertNotEqual(overlong_result.returncode, 0)
        overlong_output = overlong_result.stderr + overlong_result.stdout
        self.assertIn("approval interval exceeds", overlong_output)
        self.assertIn("approval.max_session_minutes", overlong_output)

        derived_expired = active_authorization()
        del derived_expired["approval"]["expires_at"]
        derived_expired["approval"]["recorded_at"] = (
            now - timedelta(minutes=40)
        ).isoformat()
        expired_status = run_operator_with_authorization(json.dumps(derived_expired))
        self.assertEqual(expired_status.returncode, 0)
        self.assertEqual(
            json.loads(expired_status.stdout)["authorization"]["state"],
            "expired",
        )

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_status_reports_expired_authorization_without_throwing(self) -> None:
        authorization = active_authorization()
        now = datetime.now(timezone.utc)
        authorization["approval"]["recorded_at"] = (now - timedelta(minutes=20)).isoformat()
        authorization["approval"]["expires_at"] = (now - timedelta(minutes=10)).isoformat()
        result = run_operator_with_authorization(json.dumps(authorization))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        status = json.loads(result.stdout)
        self.assertEqual(status["authorization"]["state"], "expired")
        self.assertIsNotNone(status["authorization"]["detail"])

    def test_zone_changes_trigger_fresh_client_visible_location_snapshot(self) -> None:
        addon = ADDON.read_text(encoding="utf-8")
        for event in ("ZONE_CHANGED", "ZONE_CHANGED_INDOORS", "ZONE_CHANGED_NEW_AREA"):
            self.assertIn(f'PAO_Frame:RegisterEvent("{event}")', addon)
        self.assertIn('if event == "ZONE_CHANGED"', addon)
        self.assertIn("PAO_PlayerSnapshot()", addon)


if __name__ == "__main__":
    unittest.main()
