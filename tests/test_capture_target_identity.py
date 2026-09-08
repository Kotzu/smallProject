from __future__ import annotations

import argparse
import hashlib
import importlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "windows-capture"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))

identity_module = importlib.import_module("target_identity")
probe_capture_module = importlib.import_module("probe_capture")
probe_continuous_module = importlib.import_module("probe_continuous")
probe_coordinate_hud_module = importlib.import_module("probe_coordinate_hud")
continuous_provider_module = importlib.import_module("continuous_provider")
window_locator_module = importlib.import_module("window_locator")

REALMLIST_BYTES = b"set realmlist 127.0.0.1"
REALMLIST_SHA256 = hashlib.sha256(REALMLIST_BYTES).hexdigest().upper()


def authorization(
    executable_hash: str,
    signature: str = "wow-tbc-2.4.3.8606-enGB",
    client_build: str = "2.4.3.8606",
    approval_now: datetime | None = None,
) -> dict:
    if approval_now is None:
        approval_now = datetime.now(timezone.utc) - timedelta(seconds=10)
    recorded_at = approval_now.astimezone(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    return {
        "record_type": "execution_target_authorization",
        "schema_version": "2.0",
        "authorization_id": "execution:tbc243-lab:test",
        "target_profile": "tbc_243_lab",
        "environment_scope": "emulator_local",
        "actor_binding": {
            "schema_version": "1.0",
            "instance_id": "instance:tbc243-lab:test-clone-01",
            "actor_role": "lab_clone",
            "actor_id": "actor:predator:test-clone-01",
            "decision_context": "lab_clone",
            "memory_namespace": "memory:lab:test-clone-01",
            "expected_character_name": "Predator",
            "credential_alias": "credential:lab:pa_observer",
            "binding_assurance": {
                "state": "configured_expected_only",
                "evidence_refs": ["authorization:fixture:actor-expected"],
            },
        },
        "status": "approved_bounded",
        "purpose": "education_research_content",
        "client_match": {
            "client_build": client_build,
            "build_signature": signature,
            "executable_sha256": executable_hash,
        },
        "realm_match": {
            "expected_realm_fingerprint": "fixture",
            "server_kind": "emulator",
            "realmlist_relative_path": "realmlist.wtf",
            "realmlist_sha256": REALMLIST_SHA256,
            "realmlist_directive": "set realmlist 127.0.0.1",
            "listener_bindings": [
                {
                    "port": port,
                    "process_name": process_name,
                    "executable_path": f"C:\\fixture\\{process_name}.exe",
                    "executable_sha256": "B" * 64,
                    "command_line_arguments": [
                        "-c",
                        f"C:\\fixture\\{process_name}.conf",
                    ],
                    "config_path": f"C:\\fixture\\{process_name}.conf",
                    "config_sha256": "D" * 64,
                }
                for port, process_name in (
                    (3307, "mariadbd"),
                    (3443, "mangosd"),
                    (3724, "realmd"),
                    (8085, "mangosd"),
                )
            ],
            "routing_probe": {
                "database_client_path": "C:\\fixture\\mariadb.exe",
                "database_client_sha256": "E" * 64,
                "secrets_path": "C:\\fixture\\secrets.local.json",
                "host": "127.0.0.1",
                "port": 3307,
                "database": "tbcrealmd",
            },
            "expected_routing_records": [
                {
                    "realm_id": 1,
                    "name": "Fixture",
                    "address": "127.0.0.1",
                    "port": 8085,
                    "icon": 1,
                    "realm_flags": 0,
                    "timezone": 1,
                    "allowed_security_level": 0,
                    "client_builds": ["8606"],
                }
            ],
            "expected_routing_sha256": "F" * 64,
        },
        "permitted_modes": ["MOVEMENT_ONLY"],
        "permitted_capabilities": [
            "SCREEN_CAPTURE_READ_ONLY",
            "VISIBLE_COORDINATE_HUD_READ_ONLY",
        ],
        "restrictions": ["fixture_only"],
        "approval": {
            "granted_by": "operator",
            "evidence_refs": ["fixture:test"],
            "recorded_at": recorded_at,
            "max_session_minutes": 1,
        },
        "runtime_arm_required": True,
    }


def authorization_semantic_sha256(record: dict) -> str:
    projection = dict(record)
    approval = dict(projection["approval"])
    for field in (
        "recorded_at",
        "expires_at",
        "renews_authorization_sha256",
        "renewal_scope",
    ):
        approval.pop(field, None)
    projection["approval"] = approval
    canonical = json.dumps(
        projection,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest().upper()


def process_creation_identity(created_at: datetime) -> tuple[str, str]:
    created_at = created_at.astimezone(timezone.utc)
    epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    delta = created_at - epoch
    filetime = (
        (delta.days * 86400 + delta.seconds) * 10_000_000
        + created_at.microsecond * 10
    )
    canonical = (
        f"{created_at.year:04d}-{created_at.month:02d}-{created_at.day:02d}"
        f"T{created_at.hour:02d}:{created_at.minute:02d}:{created_at.second:02d}"
        f".{created_at.microsecond:06d}0Z"
    )
    return canonical, str(filetime)


def running_process_metadata(
    executable: Path,
    receipt_issued_at: datetime,
    *,
    pid: int = 42,
    windows_session_id: int = 1,
) -> object:
    created_at, filetime = process_creation_identity(
        receipt_issued_at - timedelta(seconds=2)
    )
    return identity_module.RunningProcessIdentityMetadata(
        pid=pid,
        executable_path=executable.resolve(),
        process_created_at_utc=created_at,
        process_creation_filetime_utc=filetime,
        windows_session_id=windows_session_id,
    )


def launch_receipt(
    identity: object,
    executable: Path,
    issued_at: datetime,
    *,
    pid: int = 42,
    hwnd: int = 0x1234,
) -> dict:
    process_created_at, process_filetime = process_creation_identity(
        issued_at - timedelta(seconds=2)
    )
    return {
        "record_type": "lab_client_launch_receipt",
        "schema_version": "1.0",
        "receipt_nonce": "11111111-2222-4333-8444-555555555555",
        "pid": pid,
        "hwnd": f"0x{hwnd:X}",
        "process_created_at_utc": process_created_at,
        "process_creation_filetime_utc": process_filetime,
        "windows_session_id": 1,
        "identity_origin": "operator_launch",
        "parent_receipt_nonce": None,
        "parent_receipt_sha256": None,
        "parent_authorization_sha256": None,
        "window_title": "World of Warcraft",
        "window_class": "GxWindowClassD3d",
        "executable_path": str(executable.resolve()),
        "executable_sha256": identity.executable_sha256,
        "client_build": identity.client_build,
        "build_signature": identity.build_signature,
        "target_profile": identity.target_profile,
        "authorization_id": identity.authorization_id,
        "authorization_sha256": identity.authorization_sha256,
        "authorization_semantic_sha256": identity.authorization_semantic_sha256,
        "actor_binding": {
            "schema_version": "1.0",
            "instance_id": identity.instance_id,
            "actor_role": identity.actor_role,
            "actor_id": identity.actor_id,
            "decision_context": identity.decision_context,
            "memory_namespace": identity.memory_namespace,
            "expected_character_name": identity.expected_character_name,
            "credential_alias": identity.credential_alias,
            "binding_assurance": {
                "state": identity.binding_assurance_state,
                "evidence_refs": list(identity.binding_assurance_evidence_refs),
            },
        },
        "environment_scope": identity.environment_scope,
        "server_kind": identity.server_kind,
        "expected_realm_fingerprint": identity.expected_realm_fingerprint,
        "realm_assurance": {
            "state": "local_process_config_verified_at_launch",
            "method": "exact_realmlist_listener_process_config_and_realm_route",
            "verified_at": issued_at.isoformat(),
        },
        "realm_routing_sha256": identity.expected_realm_routing_sha256,
        "realmlist_relative_path": identity.realmlist_relative_path,
        "realmlist_sha256": identity.realmlist_sha256,
        "realmlist_directive": identity.realmlist_directive,
        "decision_context": "lab_clone",
        "created_at": issued_at.isoformat(),
        "expires_at": (issued_at + timedelta(seconds=30)).isoformat(),
        "scope": "lab_evaluation_only",
        "execution_authority": False,
    }


class CaptureTargetIdentityTests(unittest.TestCase):
    def test_loads_identity_only_after_executable_hash_match(self) -> None:
        payload = b"fixture-client"
        expected_hash = hashlib.sha256(payload).hexdigest().upper()
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            executable = temp / "Wow.exe"
            executable.write_bytes(payload)
            auth = temp / "authorization.json"
            authorization_record = authorization(expected_hash)
            auth.write_text(json.dumps(authorization_record), encoding="utf-8")

            identity = identity_module.load_capture_target_identity(
                auth,
                ROOT / "contracts" / "execution-target-authorization.schema.json",
                executable,
                "2.4.3.8606",
                required_capabilities=(identity_module.SCREEN_CAPTURE_READ_ONLY,),
            )
            self.assertEqual(identity.target_profile, "tbc_243_lab")
            self.assertEqual(identity.instance_id, "instance:tbc243-lab:test-clone-01")
            self.assertEqual(identity.actor_role, "lab_clone")
            self.assertEqual(identity.actor_id, "actor:predator:test-clone-01")
            self.assertEqual(identity.decision_context, "lab_clone")
            self.assertEqual(identity.memory_namespace, "memory:lab:test-clone-01")
            self.assertEqual(identity.expected_character_name, "Predator")
            self.assertEqual(identity.credential_alias, "credential:lab:pa_observer")
            self.assertEqual(
                identity.binding_assurance_state,
                "configured_expected_only",
            )
            self.assertEqual(identity.executable_sha256, expected_hash)
            self.assertEqual(
                identity.build_signature,
                f"wow-tbc-2.4.3.8606-enGB:sha256:{expected_hash}",
            )
            self.assertEqual(
                identity.authorization_semantic_sha256,
                authorization_semantic_sha256(authorization_record),
            )

    def test_authorization_hash_is_from_the_exact_parsed_byte_snapshot(self) -> None:
        payload = b"fixture-client"
        executable_hash = hashlib.sha256(payload).hexdigest().upper()
        first_bytes = json.dumps(
            authorization(executable_hash),
            separators=(",", ":"),
        ).encode("utf-8")
        changed = authorization(executable_hash)
        changed["authorization_id"] = "execution:tbc243-lab:mutated"
        changed_bytes = json.dumps(changed, separators=(",", ":")).encode("utf-8")

        class MutatingAuthorizationSource:
            def __init__(self) -> None:
                self.calls = 0
                self.current = first_bytes

            def open(self, mode: str) -> io.BytesIO:
                self.assert_mode = mode
                self.calls += 1
                result = self.current
                self.current = changed_bytes
                return io.BytesIO(result)

        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "Wow.exe"
            executable.write_bytes(payload)
            source = MutatingAuthorizationSource()
            identity = identity_module.load_capture_target_identity(
                source,
                ROOT / "contracts" / "execution-target-authorization.schema.json",
                executable,
                "2.4.3.8606",
                required_capabilities=(identity_module.SCREEN_CAPTURE_READ_ONLY,),
            )

        self.assertEqual(source.calls, 1)
        self.assertEqual(source.assert_mode, "rb")
        self.assertEqual(identity.authorization_id, "execution:tbc243-lab:test")
        self.assertEqual(
            identity.authorization_sha256,
            hashlib.sha256(first_bytes).hexdigest().upper(),
        )

    def test_file_snapshot_reads_only_the_bound_plus_one_from_one_handle(self) -> None:
        class RecordingStream:
            def __init__(self) -> None:
                self.requested: list[int] = []

            def __enter__(self) -> "RecordingStream":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, maximum: int) -> bytes:
                self.requested.append(maximum)
                return b"X" * maximum

        class RecordingSource:
            def __init__(self) -> None:
                self.open_calls = 0
                self.stream = RecordingStream()

            def open(self, mode: str) -> RecordingStream:
                self.open_calls += 1
                self.mode = mode
                return self.stream

        source = RecordingSource()
        with self.assertRaisesRegex(
            identity_module.CaptureTargetIdentityError,
            "exceeds its exact byte bound",
        ):
            identity_module._read_bounded_file_snapshot(
                source,
                label="bounded fixture",
                maximum_bytes=64,
            )
        self.assertEqual(source.open_calls, 1)
        self.assertEqual(source.mode, "rb")
        self.assertEqual(source.stream.requested, [65])

    def test_strict_json_rejects_nested_numeric_overflow_before_schema_use(self) -> None:
        with self.assertRaisesRegex(
            identity_module.CaptureTargetIdentityError,
            r"non-finite JSON number at outer\[0\]",
        ):
            identity_module._strict_json_object(
                b'{"outer":[1e9999]}',
                label="strict fixture",
                maximum_bytes=64,
            )

    def test_identity_object_rejects_role_context_mismatch(self) -> None:
        fields = {
            "authorization_id": "execution:tbc243-lab:test",
            "target_profile": "tbc_243_lab",
            "permitted_capabilities": ("SCREEN_CAPTURE_READ_ONLY",),
            "instance_id": "instance:tbc243-lab:test-clone-01",
            "actor_role": "lab_clone",
            "actor_id": "actor:predator:test-clone-01",
            "decision_context": "champion",
            "memory_namespace": "memory:lab:test-clone-01",
            "expected_character_name": "Predator",
            "credential_alias": "credential:lab:test-observer",
            "binding_assurance_state": "configured_expected_only",
            "binding_assurance_evidence_refs": (
                "authorization:fixture:actor-expected",
            ),
            "client_build": "2.4.3.8606",
            "build_signature": "fixture",
            "executable_sha256": "A" * 64,
            "authorization_sha256": "B" * 64,
            "environment_scope": "emulator_local",
            "server_kind": "emulator",
            "expected_realm_fingerprint": "fixture",
            "realmlist_relative_path": "realmlist.wtf",
            "realmlist_sha256": REALMLIST_SHA256,
            "realmlist_directive": "set realmlist 127.0.0.1",
            "expected_realm_routing_sha256": "F" * 64,
            "max_session_minutes": 1,
            "authorization_expires_at": None,
            "authorization_recorded_at": "2026-08-22T17:59:50+00:00",
            "authorization_semantic_sha256": "A" * 64,
        }
        with self.assertRaisesRegex(
            identity_module.CaptureTargetIdentityError,
            "inconsistent",
        ):
            identity_module.CaptureTargetIdentity(**fields)

    def test_loader_requires_active_approved_authorization_and_capture_capability(self) -> None:
        verification_now = datetime(2026, 8, 22, 18, 5, tzinfo=timezone.utc)
        cases = []

        approval_now = verification_now - timedelta(seconds=10)
        denied = authorization("A" * 64, approval_now=approval_now)
        denied["status"] = "denied"
        denied["permitted_modes"] = []
        denied["permitted_capabilities"] = []
        denied["approval"] = None
        cases.append(("denied", denied, "approved_bounded"))

        pending_populated = authorization("A" * 64, approval_now=approval_now)
        pending_populated["status"] = "pending_evidence"
        pending_populated["permitted_modes"] = []
        pending_populated["permitted_capabilities"] = []
        cases.append(("pending-populated", pending_populated, "approved_bounded"))

        future_recorded = authorization("A" * 64, approval_now=approval_now)
        future_recorded["approval"]["recorded_at"] = "2026-08-22T18:06:00Z"
        cases.append(("future-recorded", future_recorded, "not active yet"))

        expired = authorization("A" * 64, approval_now=approval_now)
        expired["approval"]["expires_at"] = "2026-08-22T18:04:59Z"
        cases.append(("expired", expired, "expired"))

        missing_capability = authorization("A" * 64, approval_now=approval_now)
        missing_capability["permitted_capabilities"] = [
            "VISIBLE_COORDINATE_HUD_READ_ONLY"
        ]
        cases.append(("missing-capability", missing_capability, "missing required"))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "Wow.exe"
            executable.write_bytes(b"fixture-client")
            executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest().upper()
            for label, payload, expected_error in cases:
                with self.subTest(case=label):
                    payload["client_match"]["executable_sha256"] = executable_hash
                    authorization_path = root / f"{label}.json"
                    authorization_path.write_text(
                        json.dumps(payload),
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(
                        identity_module.CaptureTargetIdentityError,
                        expected_error,
                    ):
                        identity_module.load_capture_target_identity(
                            authorization_path,
                            ROOT
                            / "contracts"
                            / "execution-target-authorization.schema.json",
                            executable,
                            "2.4.3.8606",
                            required_capabilities=(
                                identity_module.SCREEN_CAPTURE_READ_ONLY,
                            ),
                            now=lambda: verification_now,
                        )

            observe_only = authorization(
                executable_hash,
                approval_now=approval_now,
            )
            observe_only["authorization_id"] = "execution:tbc243-lab:observe-only"
            observe_only["permitted_modes"] = []
            observe_only_path = root / "observe-only.json"
            observe_only_path.write_text(
                json.dumps(observe_only),
                encoding="utf-8",
            )
            identity = identity_module.load_capture_target_identity(
                observe_only_path,
                ROOT / "contracts" / "execution-target-authorization.schema.json",
                executable,
                "2.4.3.8606",
                required_capabilities=(identity_module.SCREEN_CAPTURE_READ_ONLY,),
                now=lambda: verification_now,
            )
            self.assertIn(
                identity_module.SCREEN_CAPTURE_READ_ONLY,
                identity.permitted_capabilities,
            )
            self.assertEqual(observe_only["permitted_modes"], [])

    def test_authorization_without_explicit_expiry_uses_the_bounded_session_window(self) -> None:
        verification_now = datetime(2026, 8, 22, 18, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "Wow.exe"
            executable.write_bytes(b"fixture-client")
            executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest().upper()

            expired = authorization(
                executable_hash,
                approval_now=verification_now - timedelta(minutes=1),
            )
            expired_path = root / "expired-derived.json"
            expired_path.write_text(json.dumps(expired), encoding="utf-8")
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "expired",
            ):
                identity_module.load_capture_target_identity(
                    expired_path,
                    ROOT / "contracts" / "execution-target-authorization.schema.json",
                    executable,
                    "2.4.3.8606",
                    required_capabilities=(
                        identity_module.SCREEN_CAPTURE_READ_ONLY,
                    ),
                    now=lambda: verification_now,
                )

            overlong = authorization(
                executable_hash,
                approval_now=verification_now - timedelta(seconds=10),
            )
            overlong["approval"]["expires_at"] = (
                verification_now + timedelta(minutes=2)
            ).isoformat()
            overlong_path = root / "overlong-explicit.json"
            overlong_path.write_text(json.dumps(overlong), encoding="utf-8")
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "exceeds max_session_minutes",
            ):
                identity_module.load_capture_target_identity(
                    overlong_path,
                    ROOT / "contracts" / "execution-target-authorization.schema.json",
                    executable,
                    "2.4.3.8606",
                    required_capabilities=(
                        identity_module.SCREEN_CAPTURE_READ_ONLY,
                    ),
                    now=lambda: verification_now,
                )

    def test_authorization_duplicate_keys_are_rejected_before_policy_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "Wow.exe"
            executable.write_bytes(b"fixture-client")
            executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest().upper()
            raw = json.dumps(authorization(executable_hash))
            raw = raw.replace(
                '"status": "approved_bounded"',
                '"status": "approved_bounded", "status": "denied"',
                1,
            )
            authorization_path = root / "duplicate.json"
            authorization_path.write_text(raw, encoding="utf-8")
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "duplicate JSON key: status",
            ):
                identity_module.load_capture_target_identity(
                    authorization_path,
                    ROOT / "contracts" / "execution-target-authorization.schema.json",
                    executable,
                    "2.4.3.8606",
                    required_capabilities=(
                        identity_module.SCREEN_CAPTURE_READ_ONLY,
                    ),
                )

    def test_process_identity_handle_uses_only_access_denied_legacy_fallback(self) -> None:
        calls: list[int] = []

        def legacy_open(access: int, inherit: bool, pid: int) -> int:
            self.assertFalse(inherit)
            self.assertEqual(pid, 42)
            calls.append(access)
            return 0 if len(calls) == 1 else 123

        handle = identity_module._open_process_identity_handle(
            legacy_open,
            lambda: identity_module.ERROR_ACCESS_DENIED,
            42,
        )
        self.assertEqual(handle, 123)
        self.assertEqual(
            calls,
            [
                identity_module.PROCESS_QUERY_LIMITED_INFORMATION
                | identity_module.SYNCHRONIZE,
                identity_module.PROCESS_QUERY_INFORMATION
                | identity_module.SYNCHRONIZE,
            ],
        )
        vm_rights = 0x0008 | 0x0010 | 0x0020
        self.assertTrue(all(access & vm_rights == 0 for access in calls))

        non_access_denied_calls: list[int] = []

        def denied_for_other_reason(access: int, inherit: bool, pid: int) -> int:
            non_access_denied_calls.append(access)
            return 0

        with self.assertRaisesRegex(
            identity_module.ProcessImageQueryUnavailableError,
            "Win32 87",
        ):
            identity_module._open_process_identity_handle(
                denied_for_other_reason,
                lambda: 87,
                42,
            )
        self.assertEqual(len(non_access_denied_calls), 1)

    def test_running_process_metadata_requires_exact_native_type_and_time_parity(self) -> None:
        created_at, filetime = process_creation_identity(
            datetime(2026, 8, 22, 21, 53, 46, 597645, tzinfo=timezone.utc)
        )
        fields = {
            "pid": 42,
            "executable_path": Path("C:/fixture/Wow.exe"),
            "process_created_at_utc": created_at,
            "process_creation_filetime_utc": filetime,
            "windows_session_id": 1,
        }
        valid = identity_module.RunningProcessIdentityMetadata(**fields)
        self.assertEqual(valid.process_creation_filetime_utc, filetime)

        mutations = {
            "bool-pid": {"pid": True},
            "string-path": {"executable_path": "C:/fixture/Wow.exe"},
            "noncanonical-time": {
                "process_created_at_utc": "2026-08-22T21:53:46.597645Z"
            },
            "filetime-mismatch": {
                "process_creation_filetime_utc": str(int(filetime) + 1)
            },
            "bool-session": {"windows_session_id": True},
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label), self.assertRaises(
                identity_module.CaptureTargetIdentityError
            ):
                identity_module.RunningProcessIdentityMetadata(
                    **{**fields, **mutation}
                )

    def test_non_capture_capability_does_not_cross_capture_identity_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "Wow.exe"
            executable.write_bytes(b"exact client")
            payload = authorization(
                hashlib.sha256(b"exact client").hexdigest(),
                approval_now=datetime(
                    2026, 8, 22, 17, 59, 50, tzinfo=timezone.utc
                ),
            )
            payload["permitted_capabilities"].append("LAB_OPERATOR_FIXED_UI")
            authorization_path = root / "authorization.json"
            authorization_path.write_text(json.dumps(payload), encoding="utf-8")

            identity = identity_module.load_capture_target_identity(
                authorization_path,
                ROOT / "contracts" / "execution-target-authorization.schema.json",
                executable,
                "2.4.3.8606",
                required_capabilities=(identity_module.SCREEN_CAPTURE_READ_ONLY,),
                now=lambda: datetime(2026, 8, 22, 18, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(
                identity.permitted_capabilities,
                (identity_module.SCREEN_CAPTURE_READ_ONLY,),
            )

    def test_distinct_lab_clones_cannot_share_memory_namespace(self) -> None:
        first = identity_module.CaptureTargetIdentity(
            authorization_id="execution:lab:clone-01",
            target_profile="tbc_243_lab",
            permitted_capabilities=("SCREEN_CAPTURE_READ_ONLY",),
            instance_id="instance:lab:clone-01",
            actor_role="lab_clone",
            actor_id="actor:predator:lab-clone-01",
            decision_context="lab_clone",
            memory_namespace="memory:lab:clone-01",
            expected_character_name="PredatorLabOne",
            credential_alias="credential:lab:clone-01",
            binding_assurance_state="configured_expected_only",
            binding_assurance_evidence_refs=(
                "authorization:fixture:actor-expected",
            ),
            client_build="2.4.3.8606",
            build_signature="fixture",
            executable_sha256="A" * 64,
            authorization_sha256="B" * 64,
            environment_scope="emulator_remote",
            server_kind="emulator",
            expected_realm_fingerprint="remote-fixture",
            realmlist_relative_path="realmlist.wtf",
            realmlist_sha256=REALMLIST_SHA256,
            realmlist_directive="set realmlist private.example",
            expected_realm_routing_sha256=None,
            max_session_minutes=1,
            authorization_expires_at=None,
            authorization_recorded_at="2026-08-22T17:59:50+00:00",
            authorization_semantic_sha256="A" * 64,
        )
        second = replace(
            first,
            authorization_id="execution:lab:clone-02",
            instance_id="instance:lab:clone-02",
            actor_id="actor:predator:lab-clone-02",
            expected_character_name="PredatorLabTwo",
            credential_alias="credential:lab:clone-02",
        )
        with self.assertRaisesRegex(
            identity_module.CaptureTargetIdentityError,
            "cannot share",
        ):
            identity_module.validate_actor_binding_set([first, second])

        isolated = replace(second, memory_namespace="memory:lab:clone-02")
        identity_module.validate_actor_binding_set([first, isolated])

        for invalid in ((), ("",), ("duplicate", "duplicate")):
            with self.subTest(evidence_refs=invalid), self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "assurance",
            ):
                replace(first, binding_assurance_evidence_refs=invalid)

    def test_rejects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            executable = temp / "Wow.exe"
            executable.write_bytes(b"unexpected")
            auth = temp / "authorization.json"
            auth.write_text(json.dumps(authorization("a" * 64)), encoding="utf-8")
            with self.assertRaises(identity_module.CaptureTargetIdentityError):
                identity_module.load_capture_target_identity(
                    auth,
                    ROOT / "contracts" / "execution-target-authorization.schema.json",
                    executable,
                    "2.4.3.8606",
                    required_capabilities=(identity_module.SCREEN_CAPTURE_READ_ONLY,),
                )

    def test_rejects_exact_client_build_mismatch(self) -> None:
        payload = b"fixture-client"
        expected_hash = hashlib.sha256(payload).hexdigest().upper()
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            executable = temp / "Wow.exe"
            executable.write_bytes(payload)
            auth = temp / "authorization.json"
            auth.write_text(
                json.dumps(
                    authorization(
                        expected_hash,
                        "wow-tbc-2.5.6-enGB",
                        "2.5.6.unknown",
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaises(identity_module.CaptureTargetIdentityError):
                identity_module.load_capture_target_identity(
                    auth,
                    ROOT / "contracts" / "execution-target-authorization.schema.json",
                    executable,
                    "2.4.3.8606",
                    required_capabilities=(identity_module.SCREEN_CAPTURE_READ_ONLY,),
                )

    def test_rejects_client_build_that_is_only_a_signature_substring(self) -> None:
        payload = b"fixture-client"
        expected_hash = hashlib.sha256(payload).hexdigest().upper()
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            executable = temp / "Wow.exe"
            executable.write_bytes(payload)
            auth = temp / "authorization.json"
            auth.write_text(
                json.dumps(
                    authorization(
                        expected_hash,
                        "wow-tbc-2.4.3.86060-enGB",
                        "2.4.3.86060",
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "exactly match",
            ):
                identity_module.load_capture_target_identity(
                    auth,
                    ROOT / "contracts" / "execution-target-authorization.schema.json",
                    executable,
                    "2.4.3.8606",
                    required_capabilities=(identity_module.SCREEN_CAPTURE_READ_ONLY,),
                )

    def test_ptr_identity_does_not_require_local_realmlist_fields(self) -> None:
        payload = b"ptr-fixture-client"
        expected_hash = hashlib.sha256(payload).hexdigest().upper()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "Wow.exe"
            executable.write_bytes(payload)
            ptr_authorization = authorization(
                expected_hash,
                signature="ptr-fixture-signature",
                client_build="ptr-fixture-build",
            )
            ptr_authorization["authorization_id"] = "execution:ptr:test"
            ptr_authorization["target_profile"] = "tbc_classic_ptr_education"
            ptr_authorization["environment_scope"] = "blizzard_ptr"
            ptr_authorization["actor_binding"] = {
                "schema_version": "1.0",
                "instance_id": "instance:ptr:predator-champion",
                "actor_role": "champion_journey",
                "actor_id": "actor:predator:champion",
                "decision_context": "champion",
                "memory_namespace": "memory:champion:predator-journey",
                "expected_character_name": "Predator",
                "credential_alias": "credential:ptr:predator-champion",
                "binding_assurance": {
                    "state": "configured_expected_only",
                    "evidence_refs": ["authorization:fixture:actor-expected"],
                },
            }
            ptr_authorization["realm_match"] = {
                "expected_realm_fingerprint": "ptr:fixture",
                "server_kind": "blizzard_ptr",
            }
            ptr_authorization["approval"]["granted_by"] = "platform_owner"
            authorization_path = root / "authorization.json"
            authorization_path.write_text(
                json.dumps(ptr_authorization),
                encoding="utf-8",
            )
            identity = identity_module.load_capture_target_identity(
                authorization_path,
                ROOT / "contracts" / "execution-target-authorization.schema.json",
                executable,
                "ptr-fixture-build",
                required_capabilities=(identity_module.SCREEN_CAPTURE_READ_ONLY,),
            )
            self.assertIsNone(identity.realmlist_relative_path)
            self.assertIsNone(identity.realmlist_sha256)
            resolved = identity_module.verify_capture_process_identity(
                123,
                executable,
                identity,
                hwnd=None,
                expected_title=None,
                expected_class=None,
                receipt_path=root / "unused-receipt.json",
                receipt_schema_path=(
                    ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
                ),
                window_resolver=lambda: None,
                process_path_resolver=lambda _pid: executable,
            )
            self.assertTrue(resolved.samefile(executable))

    def test_running_pid_is_bound_to_same_file_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "Wow.exe"
            executable.write_bytes(b"exact-client")
            (root / "realmlist.wtf").write_bytes(REALMLIST_BYTES)
            expected_hash = hashlib.sha256(executable.read_bytes()).hexdigest().upper()
            authorization_payload = authorization(expected_hash)
            authorization_path = root / "authorization.json"
            authorization_path.write_text(
                json.dumps(authorization_payload),
                encoding="utf-8",
            )
            identity = identity_module.load_capture_target_identity(
                authorization_path,
                ROOT / "contracts" / "execution-target-authorization.schema.json",
                executable,
                "2.4.3.8606",
                required_capabilities=(identity_module.SCREEN_CAPTURE_READ_ONLY,),
            )
            resolved = identity_module.verify_running_process_identity(
                123,
                executable,
                identity,
                process_path_resolver=lambda _pid: executable,
            )
            self.assertTrue(resolved.samefile(executable))

            different_path = root / "OtherWow.exe"
            different_path.write_bytes(executable.read_bytes())
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "selected PID",
            ):
                identity_module.verify_running_process_identity(
                    123,
                    executable,
                    identity,
                    process_path_resolver=lambda _pid: different_path,
                )

            executable.write_bytes(b"changed-after-authorization")
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "SHA-256",
            ):
                identity_module.verify_running_process_identity(
                    123,
                    executable,
                    identity,
                    process_path_resolver=lambda _pid: executable,
                )

    def test_champion_on_emulator_still_rejects_wrong_realmlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "Wow.exe"
            executable.write_bytes(b"exact-client")
            realmlist = root / "realmlist.wtf"
            realmlist.write_bytes(REALMLIST_BYTES)
            expected_hash = hashlib.sha256(executable.read_bytes()).hexdigest().upper()
            payload = authorization(expected_hash)
            payload["actor_binding"] = {
                "schema_version": "1.0",
                "instance_id": "instance:emulator:predator-champion",
                "actor_role": "champion_journey",
                "actor_id": "actor:predator:champion",
                "decision_context": "champion",
                "memory_namespace": "memory:champion:predator-journey",
                "expected_character_name": "Predator",
                "credential_alias": "credential:emulator:predator-champion",
                "binding_assurance": {
                    "state": "configured_expected_only",
                    "evidence_refs": ["authorization:fixture:actor-expected"],
                },
            }
            authorization_path = root / "authorization.json"
            authorization_path.write_text(json.dumps(payload), encoding="utf-8")
            identity = identity_module.load_capture_target_identity(
                authorization_path,
                ROOT / "contracts" / "execution-target-authorization.schema.json",
                executable,
                "2.4.3.8606",
                required_capabilities=(identity_module.SCREEN_CAPTURE_READ_ONLY,),
            )
            realmlist.write_text("set realmlist wrong.example", encoding="utf-8")
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "realmlist",
            ):
                identity_module.verify_capture_process_identity(
                    42,
                    executable,
                    identity,
                    hwnd=0x1234,
                    expected_title="World of Warcraft",
                    expected_class="GxWindowClassD3d",
                    receipt_path=root / "unused.json",
                    receipt_schema_path=(
                        ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
                    ),
                    window_resolver=lambda: None,
                    process_path_resolver=lambda _pid: executable,
                )

    def test_remote_emulator_identity_uses_exact_configured_realmlist(self) -> None:
        remote_realmlist = b"set realmlist private.example"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "Wow.exe"
            executable.write_bytes(b"remote-client")
            realmlist = root / "realmlist.wtf"
            realmlist.write_bytes(remote_realmlist)
            expected_hash = hashlib.sha256(executable.read_bytes()).hexdigest().upper()
            payload = authorization(expected_hash)
            payload["authorization_id"] = "execution:remote-emulator:test"
            payload["environment_scope"] = "emulator_remote"
            payload["permitted_modes"] = []
            payload["realm_match"] = {
                "expected_realm_fingerprint": "remote-emulator:allowlisted",
                "server_kind": "emulator",
                "realmlist_relative_path": "realmlist.wtf",
                "realmlist_sha256": hashlib.sha256(remote_realmlist).hexdigest().upper(),
                "realmlist_directive": remote_realmlist.decode("utf-8"),
                "remote_assurance": {
                    "state": "configured_endpoint_only",
                    "evidence_refs": ["fixture:remote-endpoint:configured"],
                },
            }
            authorization_path = root / "authorization.json"
            authorization_path.write_text(json.dumps(payload), encoding="utf-8")
            identity = identity_module.load_capture_target_identity(
                authorization_path,
                ROOT / "contracts" / "execution-target-authorization.schema.json",
                executable,
                "2.4.3.8606",
                required_capabilities=(identity_module.SCREEN_CAPTURE_READ_ONLY,),
            )
            resolved = identity_module.verify_capture_process_identity(
                42,
                executable,
                identity,
                hwnd=0x1234,
                expected_title="World of Warcraft",
                expected_class="GxWindowClassD3d",
                receipt_path=root / "unused.json",
                receipt_schema_path=(
                    ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
                ),
                window_resolver=lambda: None,
                process_path_resolver=lambda _pid: executable,
            )
            self.assertTrue(resolved.samefile(executable))
            self.assertEqual(identity.environment_scope, "emulator_remote")
            self.assertEqual(
                identity.expected_realm_fingerprint,
                "remote-emulator:allowlisted",
            )

    def test_process_bound_capture_checks_before_and_after_frame(self) -> None:
        events: list[str] = []

        def verify() -> None:
            events.append("verify")

        def capture() -> str:
            events.append("capture")
            return "frame"

        result = identity_module.run_process_bound_capture(capture, verify)
        self.assertEqual(result, "frame")
        self.assertEqual(events, ["verify", "capture", "verify"])

    def test_process_bound_capture_fails_closed_when_post_check_fails(self) -> None:
        checks = 0

        def verify() -> None:
            nonlocal checks
            checks += 1
            if checks == 2:
                raise identity_module.CaptureTargetIdentityError(
                    "running process changed after capture"
                )

        with self.assertRaisesRegex(
            identity_module.CaptureTargetIdentityError,
            "changed after capture",
        ):
            identity_module.run_process_bound_capture(lambda: "frame", verify)
        self.assertEqual(checks, 2)

    def test_query_denial_uses_valid_receipt_only_for_lab_clone(self) -> None:
        now = datetime(2026, 8, 22, 18, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "Wow.exe"
            executable.write_bytes(b"exact-client")
            realmlist = root / "realmlist.wtf"
            realmlist.write_bytes(REALMLIST_BYTES)
            expected_hash = hashlib.sha256(executable.read_bytes()).hexdigest().upper()
            authorization_path = root / "authorization.json"
            authorization_path.write_text(
                json.dumps(
                    authorization(
                        expected_hash,
                        approval_now=now - timedelta(seconds=10),
                    )
                ),
                encoding="utf-8",
            )
            identity = identity_module.load_capture_target_identity(
                authorization_path,
                ROOT / "contracts" / "execution-target-authorization.schema.json",
                executable,
                "2.4.3.8606",
                required_capabilities=(identity_module.SCREEN_CAPTURE_READ_ONLY,),
                now=lambda: now,
            )
            receipt_path = root / "launch-receipt.json"
            receipt_path.write_text(
                json.dumps(launch_receipt(identity, executable, now)),
                encoding="utf-8",
            )
            window = window_locator_module.WindowSnapshot(
                hwnd=0x1234,
                pid=42,
                title="World of Warcraft",
                class_name="GxWindowClassD3d",
                visible=True,
                minimized=False,
                foreground=True,
                client_rect=window_locator_module.ScreenRect(0, 0, 800, 600),
                dpi=96,
            )

            def query_denied(_pid: int) -> Path:
                raise identity_module.ProcessImageQueryUnavailableError("denied")

            resolved = identity_module.verify_capture_process_identity(
                42,
                executable,
                identity,
                hwnd=0x1234,
                expected_title="World of Warcraft",
                expected_class="GxWindowClassD3d",
                receipt_path=receipt_path,
                receipt_schema_path=(
                    ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
                ),
                window_resolver=lambda: window,
                process_path_resolver=query_denied,
                process_metadata_resolver=lambda _pid: running_process_metadata(
                    executable, now
                ),
                current_session_id_resolver=lambda: 1,
                now=lambda: now + timedelta(seconds=1),
            )
            self.assertTrue(resolved.samefile(executable))

            self.assertEqual(identity.actor_role, "lab_clone")
            self.assertEqual(identity.decision_context, "lab_clone")

            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "local emulator authorization",
            ):
                identity_module.verify_capture_process_identity(
                    42,
                    executable,
                    replace(identity, environment_scope="emulator_remote"),
                    hwnd=0x1234,
                    expected_title="World of Warcraft",
                    expected_class="GxWindowClassD3d",
                    receipt_path=receipt_path,
                    receipt_schema_path=(
                        ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
                    ),
                    window_resolver=lambda: window,
                    process_path_resolver=query_denied,
                    now=lambda: now + timedelta(seconds=1),
                )

    def test_receipt_fallback_rejects_expiry_mismatch_and_missing_file(self) -> None:
        now = datetime(2026, 8, 22, 18, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "Wow.exe"
            executable.write_bytes(b"exact-client")
            realmlist = root / "realmlist.wtf"
            realmlist.write_bytes(REALMLIST_BYTES)
            expected_hash = hashlib.sha256(executable.read_bytes()).hexdigest().upper()
            authorization_path = root / "authorization.json"
            authorization_path.write_text(
                json.dumps(
                    authorization(
                        expected_hash,
                        approval_now=now - timedelta(seconds=10),
                    )
                ),
                encoding="utf-8",
            )
            identity = identity_module.load_capture_target_identity(
                authorization_path,
                ROOT / "contracts" / "execution-target-authorization.schema.json",
                executable,
                "2.4.3.8606",
                required_capabilities=(identity_module.SCREEN_CAPTURE_READ_ONLY,),
                now=lambda: now,
            )
            receipt_path = root / "launch-receipt.json"
            receipt = launch_receipt(identity, executable, now)
            receipt["pid"] = 43
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            window = window_locator_module.WindowSnapshot(
                hwnd=0x1234,
                pid=42,
                title="World of Warcraft",
                class_name="GxWindowClassD3d",
                visible=True,
                minimized=False,
                foreground=True,
                client_rect=window_locator_module.ScreenRect(0, 0, 800, 600),
                dpi=96,
            )

            def query_denied(_pid: int) -> Path:
                raise identity_module.ProcessImageQueryUnavailableError("denied")

            arguments = {
                "hwnd": 0x1234,
                "expected_title": "World of Warcraft",
                "expected_class": "GxWindowClassD3d",
                "receipt_path": receipt_path,
                "receipt_schema_path": (
                    ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
                ),
                "window_resolver": lambda: window,
                "process_path_resolver": query_denied,
                "process_metadata_resolver": lambda _pid: running_process_metadata(
                    executable, now
                ),
                "current_session_id_resolver": lambda: 1,
                "now": lambda: now + timedelta(seconds=1),
            }
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "pid",
            ):
                identity_module.verify_capture_process_identity(
                    42,
                    executable,
                    identity,
                    **arguments,
                )

            receipt["pid"] = 42
            receipt["authorization_sha256"] = "A" * 64
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "authorization_sha256",
            ):
                identity_module.verify_capture_process_identity(
                    42,
                    executable,
                    identity,
                    **arguments,
                )

            receipt["authorization_sha256"] = identity.authorization_sha256
            hidden_window = window_locator_module.WindowSnapshot(
                hwnd=window.hwnd,
                pid=window.pid,
                title=window.title,
                class_name=window.class_name,
                visible=window.visible,
                minimized=window.minimized,
                foreground=False,
                client_rect=window.client_rect,
                dpi=window.dpi,
            )
            hidden_window_arguments = {
                **arguments,
                "window_resolver": lambda: hidden_window,
            }
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "foreground",
            ):
                identity_module.verify_capture_process_identity(
                    42,
                    executable,
                    identity,
                    **hidden_window_arguments,
                )

            duplicate_receipt = json.dumps(receipt).replace(
                '"pid": 42',
                '"pid": 42, "pid": 99',
                1,
            )
            receipt_path.write_text(duplicate_receipt, encoding="utf-8")
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "duplicate JSON key: pid",
            ):
                identity_module.verify_capture_process_identity(
                    42,
                    executable,
                    identity,
                    **arguments,
                )

            receipt["expires_at"] = now.isoformat()
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "not currently valid",
            ):
                identity_module.verify_capture_process_identity(
                    42,
                    executable,
                    identity,
                    **arguments,
                )

            receipt_path.unlink()
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "cannot be loaded",
            ):
                identity_module.verify_capture_process_identity(
                    42,
                    executable,
                    identity,
                    **arguments,
                )

            receipt_path.write_text(
                json.dumps(launch_receipt(identity, executable, now)),
                encoding="utf-8",
            )
            realmlist.write_text(
                "set realmlist malicious.example\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                identity_module.CaptureTargetIdentityError,
                "realmlist",
            ):
                identity_module.verify_capture_process_identity(
                    42,
                    executable,
                    identity,
                    **arguments,
                )


class CaptureProbeProcessBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = identity_module.CaptureTargetIdentity(
            authorization_id="execution:tbc243-lab:test",
            target_profile="tbc_243_lab",
            permitted_capabilities=("SCREEN_CAPTURE_READ_ONLY",),
            instance_id="instance:tbc243-lab:test-clone-01",
            actor_role="lab_clone",
            actor_id="actor:predator:test-clone-01",
            decision_context="lab_clone",
            memory_namespace="memory:lab:test-clone-01",
            expected_character_name="Predator",
            credential_alias="credential:lab:test-observer",
            binding_assurance_state="configured_expected_only",
            binding_assurance_evidence_refs=(
                "authorization:fixture:actor-expected",
            ),
            client_build="2.4.3.8606",
            build_signature=(
                "wow-tbc-2.4.3.8606-enGB:sha256:" + ("A" * 64)
            ),
            executable_sha256="A" * 64,
            authorization_sha256="B" * 64,
            environment_scope="emulator_local",
            server_kind="emulator",
            expected_realm_fingerprint="fixture",
            realmlist_relative_path="realmlist.wtf",
            realmlist_sha256=REALMLIST_SHA256,
            realmlist_directive="set realmlist 127.0.0.1",
            expected_realm_routing_sha256="F" * 64,
            max_session_minutes=1,
            authorization_expires_at=None,
            authorization_recorded_at="2026-08-22T17:59:50+00:00",
            authorization_semantic_sha256="A" * 64,
        )

    @staticmethod
    def _probe_window(*, left: int = 1, foreground: bool = True):
        return window_locator_module.WindowSnapshot(
            hwnd=0x1234,
            pid=42,
            title="World of Warcraft",
            class_name="GxWindowClassD3d",
            visible=True,
            minimized=False,
            foreground=foreground,
            client_rect=window_locator_module.ScreenRect(left, 1, left + 4, 5),
            dpi=96,
        )

    def _run_manifest_capture_probe(
        self,
        *,
        windows: list[object],
        frame_shape: tuple[int, int, int] = (4, 4, 4),
        output_after_grab: tuple[int, int, int, int] | None = None,
    ) -> tuple[int, dict, list[str]]:
        events: list[str] = []
        coordinates = SimpleNamespace(left=0, top=0, right=8, bottom=8)

        class Camera:
            _output = SimpleNamespace(
                desc=SimpleNamespace(DesktopCoordinates=coordinates)
            )

            def grab(self, **_kwargs: object) -> object:
                events.append("capture")
                if output_after_grab is not None:
                    (
                        coordinates.left,
                        coordinates.top,
                        coordinates.right,
                        coordinates.bottom,
                    ) = output_after_grab
                height, width, _channels = frame_shape
                return SimpleNamespace(
                    shape=frame_shape,
                    strides=(width * 4, 4, 1),
                    dtype="uint8",
                )

            def release(self) -> None:
                events.append("release")

        def clock_boundary() -> tuple[float, str]:
            events.append("clock_boundary")
            return 123.25, "2026-08-22T18:00:00+00:00"

        window_sequence = iter(windows)
        fake_dxcam = SimpleNamespace(create=lambda **_kwargs: Camera())
        with (
            patch.dict(sys.modules, {"dxcam": fake_dxcam}),
            patch.object(
                probe_capture_module,
                "load_capture_target_identity",
                return_value=self.identity,
            ),
            patch.object(
                probe_capture_module,
                "verify_capture_process_identity",
                side_effect=lambda *_args, **_kwargs: events.append("verify"),
            ),
            patch.object(
                probe_capture_module,
                "locate_window",
                side_effect=lambda _query: next(window_sequence),
            ),
            patch.object(
                probe_capture_module,
                "capture_start_clock_boundary",
                side_effect=clock_boundary,
            ),
            redirect_stdout(output := io.StringIO()),
        ):
            exit_code = probe_capture_module.probe(
                [
                    "--window-pid",
                    "42",
                    "--window-hwnd",
                    "0x1234",
                    "--window-title-exact",
                    "World of Warcraft",
                    "--window-class-exact",
                    "GxWindowClassD3d",
                    "--emit-manifest",
                    "--session-id",
                    "session:target-binding-test",
                    "--client-build",
                    "2.4.3.8606",
                    "--authorization-file",
                    "authorization.json",
                    "--client-executable",
                    "Wow.exe",
                ]
            )
        return exit_code, json.loads(output.getvalue()), events

    def test_manifest_probe_binds_process_immediately_around_capture(self) -> None:
        window = self._probe_window()
        exit_code, manifest, events = self._run_manifest_capture_probe(
            windows=[window, window],
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            events,
            ["verify", "clock_boundary", "capture", "verify", "release"],
        )
        self.assertEqual(manifest["decision_context"], "lab_clone")
        self.assertEqual(manifest["provenance"]["scope"], "lab_evaluation_only")
        self.assertIn(self.identity.actor_evidence_ref, manifest["provenance"]["evidence_refs"])
        self.assertEqual(
            manifest["timing"]["captured_at"],
            "2026-08-22T18:00:00+00:00",
        )
        self.assertEqual(manifest["timing"]["monotonic_timestamp_s"], 123.25)

    def test_manifest_probe_rejects_window_change_adjacent_to_grab(self) -> None:
        exit_code, failure, events = self._run_manifest_capture_probe(
            windows=[self._probe_window(), self._probe_window(left=2)],
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(failure["error_type"], "CaptureSourceChangedError")
        self.assertIn("window identity", failure["detail"])
        self.assertEqual(
            events,
            ["verify", "clock_boundary", "capture", "verify", "release"],
        )

    def test_manifest_probe_rejects_output_geometry_change_after_grab(self) -> None:
        exit_code, failure, events = self._run_manifest_capture_probe(
            windows=[self._probe_window()],
            output_after_grab=(0, 0, 9, 8),
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(failure["error_type"], "CaptureSourceChangedError")
        self.assertIn("output geometry", failure["detail"])
        self.assertEqual(
            events,
            ["verify", "clock_boundary", "capture", "verify", "release"],
        )

    def test_manifest_probe_rejects_frame_dimensions_not_matching_source(self) -> None:
        window = self._probe_window()
        exit_code, failure, events = self._run_manifest_capture_probe(
            windows=[window, window],
            frame_shape=(3, 4, 4),
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(failure["error_type"], "CaptureSourceChangedError")
        self.assertIn("frame dimensions", failure["detail"])
        self.assertEqual(
            events,
            ["verify", "clock_boundary", "capture", "verify", "release"],
        )

    def test_capture_probe_context_cannot_be_relabelled_from_cli(self) -> None:
        for parser_factory in (
            probe_capture_module.build_parser,
            probe_continuous_module.build_parser,
            probe_coordinate_hud_module.build_parser,
        ):
            with self.subTest(parser=parser_factory.__module__):
                self.assertNotIn(
                    "--decision-context",
                    parser_factory()._option_string_actions,
                )

    def test_continuous_probe_rejects_non_finite_and_oversized_bounds(self) -> None:
        for value in ("nan", "inf", "-inf", "0", "61"):
            with self.subTest(target_fps=value), self.assertRaises(
                argparse.ArgumentTypeError
            ):
                probe_continuous_module.bounded_float(
                    value,
                    label="target FPS",
                    maximum=probe_continuous_module.MAX_TARGET_FPS,
                )
        for value, maximum in (
            ("601", probe_continuous_module.MAX_SAMPLES),
            ("17", probe_continuous_module.MAX_BUFFER_CAPACITY),
        ):
            with self.subTest(integer=value), self.assertRaises(
                argparse.ArgumentTypeError
            ):
                probe_continuous_module.bounded_integer(
                    value,
                    label="bounded integer",
                    maximum=maximum,
                )
        for value in ("nan", "inf", "1001"):
            with self.subTest(deadline=value), self.assertRaises(
                argparse.ArgumentTypeError
            ):
                probe_continuous_module.bounded_float(
                    value,
                    label="capture deadline",
                    maximum=probe_continuous_module.MAX_CAPTURE_DEADLINE_MS,
                )

    def test_continuous_probe_rejects_requested_duration_over_wall_limit(self) -> None:
        with self.assertRaisesRegex(SystemExit, "30 seconds"):
            probe_continuous_module.probe(
                [
                    "--window-pid", "42",
                    "--window-hwnd", "0x1234",
                    "--window-title-exact", "World of Warcraft",
                    "--window-class-exact", "GxWindowClassD3d",
                    "--samples", "61",
                    "--target-fps", "2",
                    "--session-id", "session:bounded-duration",
                    "--client-build", "2.4.3.8606",
                    "--authorization-file", "authorization.json",
                    "--client-executable", "Wow.exe",
                ]
            )

    def test_continuous_probe_enforces_actual_monotonic_wall_deadline(self) -> None:
        class Provider:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                self.stats = continuous_provider_module.ContinuousCaptureStats()
                self.buffer: list[object] = []

            def open(self) -> None:
                return None

            def next_frame(self) -> object:
                return SimpleNamespace(manifest={"frame": 1})

            def close(self) -> None:
                self.buffer.clear()

        output = io.StringIO()
        with (
            patch.object(
                probe_continuous_module,
                "load_capture_target_identity",
                return_value=self.identity,
            ),
            patch.object(probe_continuous_module, "DxcamWindowCaptureProvider", Provider),
            patch.object(probe_continuous_module, "verify_capture_process_identity"),
            patch.object(
                probe_continuous_module.time,
                "monotonic",
                side_effect=[0.0, 0.0, 31.0],
            ),
            redirect_stdout(output),
        ):
            exit_code = probe_continuous_module.probe(
                [
                    "--window-pid", "42",
                    "--window-hwnd", "0x1234",
                    "--window-title-exact", "World of Warcraft",
                    "--window-class-exact", "GxWindowClassD3d",
                    "--samples", "1",
                    "--target-fps", "1",
                    "--session-id", "session:wall-deadline",
                    "--client-build", "2.4.3.8606",
                    "--authorization-file", "authorization.json",
                    "--client-executable", "Wow.exe",
                ]
            )
        self.assertEqual(exit_code, 1)
        failure = json.loads(output.getvalue())
        self.assertEqual(failure["error_type"], "TimeoutError")
        self.assertIn("wall deadline", failure["detail"])

    def test_continuous_probe_rechecks_deadline_before_final_emission(self) -> None:
        class Provider:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                self.stats = continuous_provider_module.ContinuousCaptureStats()
                self.buffer: list[object] = []

            def open(self) -> None:
                return None

            def next_frame(self) -> object:
                return SimpleNamespace(manifest={"frame": 1})

            def close(self) -> None:
                self.buffer.clear()

        output = io.StringIO()
        with (
            patch.object(
                probe_continuous_module,
                "load_capture_target_identity",
                return_value=self.identity,
            ),
            patch.object(probe_continuous_module, "DxcamWindowCaptureProvider", Provider),
            patch.object(probe_continuous_module, "verify_capture_process_identity"),
            patch.object(
                probe_continuous_module.time,
                "monotonic",
                side_effect=[0.0, 0.0, 0.1, 31.0],
            ),
            patch.object(probe_continuous_module.time, "sleep") as sleeper,
            redirect_stdout(output),
        ):
            exit_code = probe_continuous_module.probe(
                [
                    "--window-pid", "42",
                    "--window-hwnd", "0x1234",
                    "--window-title-exact", "World of Warcraft",
                    "--window-class-exact", "GxWindowClassD3d",
                    "--samples", "1",
                    "--target-fps", "1",
                    "--session-id", "session:wall-deadline-final",
                    "--client-build", "2.4.3.8606",
                    "--authorization-file", "authorization.json",
                    "--client-executable", "Wow.exe",
                ]
            )
        self.assertEqual(exit_code, 1)
        self.assertFalse(sleeper.called)
        failure = json.loads(output.getvalue())
        self.assertEqual(failure["error_type"], "TimeoutError")
        self.assertIn("before emission", failure["detail"])

    def test_manifest_probe_rejects_missing_pid_before_capture_import(self) -> None:
        with self.assertRaisesRegex(SystemExit, "requires --window-pid"):
            probe_capture_module.probe(
                [
                    "--emit-manifest",
                    "--session-id",
                    "session:target-binding-test",
                    "--client-build",
                    "2.4.3.8606",
                    "--authorization-file",
                    "authorization.json",
                    "--client-executable",
                    "Wow.exe",
                ]
            )

    def test_manifest_probe_requires_exact_window_identity_filters(self) -> None:
        base = [
            "--emit-manifest",
            "--window-pid", "42",
            "--session-id", "session:target-binding-test",
            "--client-build", "2.4.3.8606",
            "--authorization-file", "authorization.json",
            "--client-executable", "Wow.exe",
        ]
        for extra in (
            ["--window-title-exact", "World of Warcraft", "--window-class-exact", "GxWindowClassD3d"],
            ["--window-hwnd", "0x1234", "--window-class-exact", "GxWindowClassD3d"],
            ["--window-hwnd", "0x1234", "--window-title-exact", "World of Warcraft"],
        ):
            with self.subTest(extra=extra), self.assertRaisesRegex(
                SystemExit,
                "exact window HWND, title and class",
            ):
                probe_capture_module.probe(base + extra)

    def test_continuous_probe_binds_process_around_every_frame(self) -> None:
        events: list[str] = []

        class Provider:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                self.stats = continuous_provider_module.ContinuousCaptureStats()
                self.buffer: list[object] = []
                self.frame_index = 0

            def open(self) -> None:
                events.append("open")

            def next_frame(self) -> object:
                events.append("capture")
                self.frame_index += 1
                return SimpleNamespace(manifest={"frame": self.frame_index})

            def close(self) -> None:
                events.append("close")
                self.buffer.clear()

        with (
            patch.object(
                probe_continuous_module,
                "load_capture_target_identity",
                return_value=self.identity,
            ),
            patch.object(
                probe_continuous_module,
                "verify_capture_process_identity",
                side_effect=lambda *_args, **_kwargs: events.append("verify"),
            ),
            patch.object(
                probe_continuous_module,
                "DxcamWindowCaptureProvider",
                Provider,
            ),
            patch.object(probe_continuous_module.time, "sleep"),
            redirect_stdout(io.StringIO()),
        ):
            exit_code = probe_continuous_module.probe(
                [
                    "--window-pid",
                    "42",
                    "--window-hwnd",
                    "0x1234",
                    "--window-title-exact",
                    "World of Warcraft",
                    "--window-class-exact",
                    "GxWindowClassD3d",
                    "--samples",
                    "2",
                    "--target-fps",
                    "30",
                    "--session-id",
                    "session:target-binding-test",
                    "--client-build",
                    "2.4.3.8606",
                    "--authorization-file",
                    "authorization.json",
                    "--client-executable",
                    "Wow.exe",
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            events,
            [
                "open",
                "verify",
                "capture",
                "verify",
                "verify",
                "capture",
                "verify",
                "close",
            ],
        )


if __name__ == "__main__":
    unittest.main()
