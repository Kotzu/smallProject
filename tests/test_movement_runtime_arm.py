from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator
from perfect_assassin.execution import (
    ExecutionGateway,
    ExecutionPoseState,
    FakeInputSink,
    InMemoryRuntimeArm,
    ManualMonotonicClock,
    validate_execution_record_semantics,
)
from perfect_assassin.execution.movement_runtime_arm import (
    F3A_EXECUTION_LEASE_POLICY,
    MAX_MOVEMENT_ARM_LIFETIME_MS,
    MOVE_FORWARD_CONTROL,
    MOVEMENT_CAPABILITY,
    MOVEMENT_MODE,
    MovementArmValidationError,
    issue_movement_authorization_snapshot,
    issue_movement_runtime_arm_snapshot,
    issue_session_authorization_snapshot,
    load_movement_authorization_profile,
    load_movement_runtime_arm,
)


ROOT = Path(__file__).resolve().parents[1]
AUTH_SCHEMA = ROOT / "contracts" / "execution-target-authorization.schema.json"
ARM_SCHEMA = ROOT / "contracts" / "movement-runtime-arm.schema.json"
RECEIPT_SCHEMA = ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
EXECUTION_SCHEMA = ROOT / "contracts" / "execution-gateway.schema.json"
FIXED_AUTH_PATH = ROOT / "config" / "execution-targets" / "tbc_243_lab.json"
MOVEMENT_AUTH_PATH = (
    ROOT / "config" / "execution-targets" / "tbc_243_lab_movement_f3a.json"
)
ISSUE_AT = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 8, 23, 12, 0, 1, tzinfo=timezone.utc)


def exact_json_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def movement_template_record() -> dict[str, object]:
    return json.loads(MOVEMENT_AUTH_PATH.read_text(encoding="utf-8"))


def issued_authorization_raw(
    *, issue_at: datetime = ISSUE_AT,
    evidence_refs: tuple[str, ...] = ("gate:pa024f3a",),
) -> bytes:
    return issue_movement_authorization_snapshot(
        MOVEMENT_AUTH_PATH.read_bytes(),
        schema_path=AUTH_SCHEMA,
        now_utc=issue_at,
        evidence_refs=evidence_refs,
        acknowledge_single_pulse=True,
    )


def movement_profile_record() -> dict[str, object]:
    return json.loads(issued_authorization_raw())


def authorization_semantic_sha256(record: dict[str, object]) -> str:
    stable = copy.deepcopy(record)
    for field in (
        "recorded_at",
        "expires_at",
        "renews_authorization_sha256",
        "renewal_scope",
    ):
        stable["approval"].pop(field, None)
    return hashlib.sha256(exact_json_bytes(stable)).hexdigest().upper()


def session_authorization_raw() -> bytes:
    fixed_raw = FIXED_AUTH_PATH.read_bytes()
    fixed = json.loads(fixed_raw)
    stable_approval = fixed["approval"]
    fixed["approval"] = {
        "granted_by": stable_approval["granted_by"],
        "evidence_refs": stable_approval["evidence_refs"],
        "recorded_at": "2026-08-23T11:45:00Z",
        "expires_at": "2026-08-23T12:15:00Z",
        "max_session_minutes": stable_approval["max_session_minutes"],
        "renews_authorization_sha256": hashlib.sha256(
            fixed_raw
        ).hexdigest().upper(),
        "renewal_scope": "temporal_only",
    }
    return exact_json_bytes(fixed)


def session_receipt_record(
    *, exact_session_authorization_raw: bytes | None = None
) -> dict[str, object]:
    fixed_raw = exact_session_authorization_raw or session_authorization_raw()
    fixed_authorization = json.loads(fixed_raw)
    fixed_authorization_sha256 = hashlib.sha256(fixed_raw).hexdigest().upper()
    return {
        "record_type": "lab_client_launch_receipt",
        "schema_version": "1.0",
        "receipt_nonce": "11111111-2222-3333-4444-555555555555",
        "pid": 4242,
        "hwnd": "0x1234ABCD",
        "process_created_at_utc": "2026-08-23T11:50:00.000000Z",
        "process_creation_filetime_utc": "134319594000000000",
        "windows_session_id": 1,
        "identity_origin": "operator_launch",
        "parent_receipt_nonce": None,
        "parent_receipt_sha256": None,
        "parent_authorization_sha256": None,
        "window_title": "World of Warcraft",
        "window_class": "GxWindowClassD3d",
        "executable_path": "E:\\Games\\WoW TBC 2.4.3\\Wow.exe",
        "executable_sha256": fixed_authorization["client_match"][
            "executable_sha256"
        ],
        "client_build": fixed_authorization["client_match"]["client_build"],
        "build_signature": (
            f"{fixed_authorization['client_match']['build_signature']}:sha256:"
            f"{fixed_authorization['client_match']['executable_sha256']}"
        ),
        "target_profile": fixed_authorization["target_profile"],
        "authorization_id": fixed_authorization["authorization_id"],
        "authorization_sha256": fixed_authorization_sha256,
        "authorization_semantic_sha256": authorization_semantic_sha256(
            fixed_authorization
        ),
        "actor_binding": fixed_authorization["actor_binding"],
        "environment_scope": "emulator_local",
        "server_kind": "emulator",
        "expected_realm_fingerprint": fixed_authorization["realm_match"][
            "expected_realm_fingerprint"
        ],
        "realm_assurance": {
            "state": "local_process_config_verified_at_launch",
            "method": "exact_realmlist_listener_process_config_and_realm_route",
            "verified_at": "2026-08-23T11:59:00Z",
        },
        "realm_routing_sha256": fixed_authorization["realm_match"][
            "expected_routing_sha256"
        ],
        "realmlist_relative_path": fixed_authorization["realm_match"][
            "realmlist_relative_path"
        ],
        "realmlist_sha256": fixed_authorization["realm_match"][
            "realmlist_sha256"
        ],
        "realmlist_directive": fixed_authorization["realm_match"][
            "realmlist_directive"
        ],
        "decision_context": "lab_clone",
        "created_at": "2026-08-23T11:59:00Z",
        "expires_at": "2026-08-23T12:15:00Z",
        "scope": "lab_evaluation_only",
        "execution_authority": False,
    }


def realm_revalidation_record(
    session_receipt_raw: bytes,
    *,
    authorization_raw: bytes | None = None,
) -> dict[str, object]:
    receipt = json.loads(session_receipt_raw)
    exact_authorization_raw = authorization_raw or issued_authorization_raw()
    authorization = json.loads(exact_authorization_raw)
    return {
        "record_type": "local_realm_revalidation_receipt",
        "schema_version": "0.1",
        "issuer_id": "perfect_assassin.local_realm_revalidator",
        "revalidation_nonce": "66666666-7777-8888-9999-AAAAAAAAAAAA",
        "authorization_id": authorization["authorization_id"],
        "authorization_sha256": hashlib.sha256(
            exact_authorization_raw
        ).hexdigest().upper(),
        "session_receipt_nonce": receipt["receipt_nonce"],
        "session_receipt_sha256": hashlib.sha256(
            session_receipt_raw
        ).hexdigest().upper(),
        "target_profile": authorization["target_profile"],
        "actor_id": authorization["actor_binding"]["actor_id"],
        "actor_instance_id": authorization["actor_binding"]["instance_id"],
        "pid": receipt["pid"],
        "hwnd": receipt["hwnd"],
        "process_created_at_utc": receipt["process_created_at_utc"],
        "process_creation_filetime_utc": receipt[
            "process_creation_filetime_utc"
        ],
        "windows_session_id": receipt["windows_session_id"],
        "executable_path": receipt["executable_path"],
        "executable_sha256": receipt["executable_sha256"],
        "environment_scope": receipt["environment_scope"],
        "server_kind": receipt["server_kind"],
        "expected_realm_fingerprint": receipt["expected_realm_fingerprint"],
        "realm_routing_sha256": receipt["realm_routing_sha256"],
        "realmlist_relative_path": receipt["realmlist_relative_path"],
        "realmlist_sha256": receipt["realmlist_sha256"],
        "realmlist_directive": receipt["realmlist_directive"],
        "method": "exact_realmlist_listener_process_config_and_realm_route",
        "observed_at": "2026-08-23T12:00:00Z",
        "expires_at": "2026-08-23T12:00:30Z",
        "scope": "lab_evaluation_only",
        "execution_authority": False,
    }


def movement_arm_record(
    *,
    session_receipt_raw: bytes | None = None,
    authorization_raw: bytes | None = None,
) -> dict[str, object]:
    exact_authorization_raw = authorization_raw or issued_authorization_raw()
    authorization_record = json.loads(exact_authorization_raw)
    authorization_sha256 = hashlib.sha256(exact_authorization_raw).hexdigest().upper()
    receipt_raw = session_receipt_raw or exact_json_bytes(session_receipt_record())
    receipt = json.loads(receipt_raw)
    revalidation_raw = exact_json_bytes(
        realm_revalidation_record(
            receipt_raw,
            authorization_raw=exact_authorization_raw,
        )
    )
    revalidation = json.loads(revalidation_raw)
    return {
        "record_type": "movement_runtime_arm",
        "schema_version": "0.1",
        "arm_nonce": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
        "authorization_id": authorization_record["authorization_id"],
        "authorization_sha256": authorization_sha256,
        "session_receipt": {
            "record_type": "lab_client_launch_receipt",
            "schema_version": "1.0",
            "receipt_nonce": receipt["receipt_nonce"],
            "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest().upper(),
            "execution_authority": False,
        },
        "target_profile": authorization_record["target_profile"],
        "target_instance_id": (
            f"client:windows:{receipt['pid']}:"
            f"{receipt['process_creation_filetime_utc']}"
        ),
        "actor_binding": authorization_record["actor_binding"],
        "pid": receipt["pid"],
        "hwnd": receipt["hwnd"],
        "process_created_at_utc": receipt["process_created_at_utc"],
        "process_creation_filetime_utc": receipt[
            "process_creation_filetime_utc"
        ],
        "windows_session_id": receipt["windows_session_id"],
        "window_title": receipt["window_title"],
        "window_class": receipt["window_class"],
        "client_build": authorization_record["client_match"]["client_build"],
        "build_signature": (
            f"{authorization_record['client_match']['build_signature']}:sha256:"
            f"{authorization_record['client_match']['executable_sha256']}"
        ),
        "executable_path": receipt["executable_path"],
        "executable_sha256": authorization_record["client_match"][
            "executable_sha256"
        ],
        "environment_scope": "emulator_local",
        "server_kind": "emulator",
        "expected_realm_fingerprint": authorization_record["realm_match"][
            "expected_realm_fingerprint"
        ],
        "realm_routing_sha256": authorization_record["realm_match"][
            "expected_routing_sha256"
        ],
        "realmlist_relative_path": authorization_record["realm_match"][
            "realmlist_relative_path"
        ],
        "realmlist_sha256": authorization_record["realm_match"][
            "realmlist_sha256"
        ],
        "realmlist_directive": authorization_record["realm_match"][
            "realmlist_directive"
        ],
        "realm_revalidation": {
            "record_type": "local_realm_revalidation_receipt",
            "schema_version": "0.1",
            "issuer_id": "perfect_assassin.local_realm_revalidator",
            "revalidation_nonce": revalidation["revalidation_nonce"],
            "receipt_sha256": hashlib.sha256(
                revalidation_raw
            ).hexdigest().upper(),
            "execution_authority": False,
        },
        "allowed_modes": ["MOVEMENT_ONLY"],
        "allowed_capabilities": ["MOVEMENT_EXECUTION"],
        "allowed_controls": ["MOVE_FORWARD"],
        "max_hold_duration_ms": 100,
        "max_execution_envelope_ms": 150,
        "max_primitives": 1,
        "manual_takeover_required": True,
        "release_all_required": True,
        "combat_authorized": False,
        "economy_authorized": False,
        "clock_id": "clock:movement:f3a",
        "issued_at_monotonic_ms": 1_000.0,
        "expires_at_monotonic_ms": 31_000.0,
        "issued_at": "2026-08-23T12:00:00Z",
        "expires_at": "2026-08-23T12:00:30Z",
        "active": True,
        "scope": "lab_movement_single_pulse",
        "execution_authority": True,
    }


def validated_profile(
    *,
    exact_movement_authorization_raw: bytes | None = None,
    now_utc: datetime = NOW,
):
    return load_movement_authorization_profile(
        exact_movement_authorization_raw or issued_authorization_raw(),
        schema_path=AUTH_SCHEMA,
        now_utc=now_utc,
    )


def load_fixture_arm(
    arm_record: dict[str, object], receipt_raw: bytes,
    *, realm_revalidation_raw: bytes | None = None,
    exact_session_authorization_raw: bytes | None = None,
    exact_movement_authorization_raw: bytes | None = None,
    acknowledge_single_pulse: object = True,
    now_utc: datetime = NOW,
    now_monotonic_ms: float = 2_000.0,
):
    revalidation_raw = realm_revalidation_raw or exact_json_bytes(
        realm_revalidation_record(
            receipt_raw,
            authorization_raw=exact_movement_authorization_raw,
        )
    )
    return load_movement_runtime_arm(
        exact_json_bytes(arm_record),
        schema_path=ARM_SCHEMA,
        authorization=validated_profile(
            exact_movement_authorization_raw=exact_movement_authorization_raw,
            now_utc=now_utc,
        ),
        session_receipt_raw=receipt_raw,
        session_receipt_schema_path=RECEIPT_SCHEMA,
        session_authorization_raw=(
            exact_session_authorization_raw or session_authorization_raw()
        ),
        authorization_schema_path=AUTH_SCHEMA,
        realm_revalidation_raw=revalidation_raw,
        acknowledge_single_pulse=acknowledge_single_pulse,
        now_utc=now_utc,
        now_monotonic_ms=now_monotonic_ms,
    )


class MovementRuntimeArmTests(unittest.TestCase):
    def setUp(self) -> None:
        self.authorization_validator = ContractValidator(AUTH_SCHEMA)
        self.arm_validator = ContractValidator(ARM_SCHEMA)
        self.receipt_validator = ContractValidator(RECEIPT_SCHEMA)

    def test_fixed_ui_and_movement_authorizations_are_distinct(self) -> None:
        fixed = json.loads(FIXED_AUTH_PATH.read_text(encoding="utf-8"))
        template = movement_template_record()
        movement = movement_profile_record()
        self.authorization_validator.validate(fixed)
        self.authorization_validator.validate(template)
        self.authorization_validator.validate(movement)

        self.assertNotEqual(fixed["authorization_id"], template["authorization_id"])
        self.assertEqual(fixed["permitted_modes"], [])
        self.assertNotIn(MOVEMENT_CAPABILITY, fixed["permitted_capabilities"])
        self.assertNotIn("movement_policy", fixed)
        self.assertIn("LAB_OPERATOR_FIXED_UI", fixed["permitted_capabilities"])

        fixed_rollover = copy.deepcopy(fixed)
        fixed_rollover["approval"]["renews_authorization_sha256"] = "A" * 64
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(fixed_rollover)
        fixed_rollover["approval"]["renewal_scope"] = "temporal_only"
        self.authorization_validator.validate(fixed_rollover)

        self.assertEqual(template["status"], "pending_evidence")
        self.assertEqual(template["permitted_modes"], [])
        self.assertEqual(template["permitted_capabilities"], [])
        self.assertNotIn("movement_policy", template)
        self.assertIsNone(template["approval"])

        self.assertEqual(movement["permitted_modes"], [MOVEMENT_MODE])
        self.assertEqual(
            set(movement["permitted_capabilities"]),
            {
                "SCREEN_CAPTURE_READ_ONLY",
                "VISIBLE_COORDINATE_HUD_READ_ONLY",
                MOVEMENT_CAPABILITY,
            },
        )
        self.assertNotIn("LAB_OPERATOR_FIXED_UI", movement["permitted_capabilities"])
        policy = movement["movement_policy"]
        self.assertEqual(policy["allowed_controls"], [MOVE_FORWARD_CONTROL])
        self.assertEqual(policy["max_hold_duration_ms"], 100)
        self.assertEqual(policy["max_execution_envelope_ms"], 150)
        self.assertEqual(policy["max_primitives"], 1)
        self.assertIs(policy["combat_authorized"], False)
        self.assertIs(policy["economy_authorized"], False)

        with self.assertRaises(MovementArmValidationError):
            load_movement_authorization_profile(
                FIXED_AUTH_PATH.read_bytes(), schema_path=AUTH_SCHEMA, now_utc=NOW
            )
        with self.assertRaises(MovementArmValidationError):
            load_movement_authorization_profile(
                MOVEMENT_AUTH_PATH.read_bytes(), schema_path=AUTH_SCHEMA, now_utc=NOW
            )

    def test_valid_arm_binds_exact_non_authority_receipt_and_gateway_inputs(self) -> None:
        receipt_raw = exact_json_bytes(session_receipt_record())
        arm_record = movement_arm_record(session_receipt_raw=receipt_raw)
        self.receipt_validator.validate(json.loads(receipt_raw))
        self.arm_validator.validate(arm_record)

        arm = load_fixture_arm(arm_record, receipt_raw)

        self.assertEqual(arm.max_hold_duration_ms, 100)
        self.assertEqual(arm.max_execution_envelope_ms, 150)
        self.assertEqual(arm.max_primitives, 1)
        self.assertEqual(
            arm.session_receipt_sha256,
            hashlib.sha256(receipt_raw).hexdigest().upper(),
        )
        receipt = json.loads(receipt_raw)
        self.assertNotEqual(
            receipt["authorization_id"], arm.binding.authorization_id
        )
        self.assertIs(receipt["execution_authority"], False)

        snapshot = arm.runtime_snapshot()
        authorization = arm.execution_authorization()
        self.assertEqual(snapshot.allowed_modes, frozenset({MOVEMENT_MODE}))
        self.assertEqual(
            snapshot.allowed_capabilities, frozenset({MOVEMENT_CAPABILITY})
        )
        self.assertEqual(snapshot.binding, arm.binding)
        self.assertEqual(authorization.binding, arm.binding)
        self.assertTrue(authorization.runtime_arm_required)

        for acknowledgement in (False, 1, "true", None):
            with self.subTest(runtime_acknowledgement=acknowledgement):
                with self.assertRaisesRegex(
                    MovementArmValidationError,
                    "acknowledgement",
                ):
                    load_fixture_arm(
                        arm_record,
                        receipt_raw,
                        acknowledge_single_pulse=acknowledgement,
                    )

    def test_schema_rejects_any_scope_beyond_one_forward_pulse(self) -> None:
        receipt_raw = exact_json_bytes(session_receipt_record())
        cases = (
            ("allowed_controls", ["MOVE_FORWARD", "MOVE_BACKWARD"]),
            ("max_hold_duration_ms", 101),
            ("max_execution_envelope_ms", 151),
            ("max_primitives", 2),
            ("combat_authorized", True),
            ("economy_authorized", True),
        )
        for field, value in cases:
            with self.subTest(field=field):
                arm_record = movement_arm_record(session_receipt_raw=receipt_raw)
                arm_record[field] = value
                with self.assertRaises(ContractValidationError):
                    self.arm_validator.validate(arm_record)

        movement = movement_profile_record()
        movement["permitted_capabilities"].append("LAB_OPERATOR_FIXED_UI")
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(movement)

        movement = movement_profile_record()
        movement["approval"]["renews_authorization_sha256"] = "A" * 64
        movement["approval"]["renewal_scope"] = "temporal_only"
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(movement)

    def test_authorization_is_ephemeral_and_cannot_self_promote(self) -> None:
        issued_raw = issued_authorization_raw()
        issued = json.loads(issued_raw)
        self.authorization_validator.validate(issued)

        profile = load_movement_authorization_profile(
            issued_raw,
            schema_path=AUTH_SCHEMA,
            now_utc=NOW,
        )
        self.assertEqual(
            profile.authorization_sha256,
            hashlib.sha256(issued_raw).hexdigest().upper(),
        )
        self.assertEqual(issued["approval"]["recorded_at"], "2026-08-23T12:00:00.000000Z")
        self.assertEqual(issued["approval"]["expires_at"], "2026-08-23T12:01:00.000000Z")
        self.assertIn(
            "operator_ack:pa024f3a:single_forward_pulse",
            issued["approval"]["evidence_refs"],
        )

        with self.assertRaisesRegex(MovementArmValidationError, "future"):
            load_movement_authorization_profile(
                issued_raw,
                schema_path=AUTH_SCHEMA,
                now_utc=datetime(2026, 8, 23, 11, 59, 59, tzinfo=timezone.utc),
            )
        with self.assertRaisesRegex(MovementArmValidationError, "expired"):
            load_movement_authorization_profile(
                issued_raw,
                schema_path=AUTH_SCHEMA,
                now_utc=datetime(2026, 8, 23, 12, 1, 0, tzinfo=timezone.utc),
            )

        overlong = copy.deepcopy(issued)
        overlong["approval"]["expires_at"] = "2026-08-23T12:01:01Z"
        self.authorization_validator.validate(overlong)
        with self.assertRaisesRegex(MovementArmValidationError, "overlong"):
            load_movement_authorization_profile(
                exact_json_bytes(overlong),
                schema_path=AUTH_SCHEMA,
                now_utc=NOW,
            )

        missing_expiry = copy.deepcopy(issued)
        del missing_expiry["approval"]["expires_at"]
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(missing_expiry)

        noncanonical = copy.deepcopy(issued)
        noncanonical["approval"]["recorded_at"] = "2026-08-23T15:00:00+03:00"
        self.authorization_validator.validate(noncanonical)
        with self.assertRaisesRegex(MovementArmValidationError, "canonical"):
            load_movement_authorization_profile(
                exact_json_bytes(noncanonical),
                schema_path=AUTH_SCHEMA,
                now_utc=NOW,
            )

        with self.assertRaisesRegex(MovementArmValidationError, "template"):
            issue_movement_authorization_snapshot(
                issued_raw,
                schema_path=AUTH_SCHEMA,
                now_utc=NOW,
                evidence_refs=("gate:pa024f3a",),
                acknowledge_single_pulse=True,
            )

    def test_session_authorization_issuer_changes_only_temporal_fields(self) -> None:
        issued_raw = issue_session_authorization_snapshot(
            FIXED_AUTH_PATH.read_bytes(),
            schema_path=AUTH_SCHEMA,
            now_utc=ISSUE_AT,
        )
        issued = json.loads(issued_raw)
        self.authorization_validator.validate(issued)
        self.assertEqual(issued["approval"]["recorded_at"], "2026-08-23T12:00:00.000000Z")
        self.assertEqual(issued["approval"]["expires_at"], "2026-08-23T12:30:00.000000Z")
        self.assertNotIn("renews_authorization_sha256", issued["approval"])
        self.assertEqual(
            authorization_semantic_sha256(issued),
            "C66D8B8F7B6F29CDC9ED8FD9A5B07BBB89A689CE55693DBB5EB91CA09E392E41",
        )

        parent = "B" * 64
        renewal = json.loads(
            issue_session_authorization_snapshot(
                FIXED_AUTH_PATH.read_bytes(),
                schema_path=AUTH_SCHEMA,
                now_utc=ISSUE_AT,
                renewal_parent_sha256=parent,
            )
        )
        self.assertEqual(renewal["approval"]["renews_authorization_sha256"], parent)
        self.assertEqual(renewal["approval"]["renewal_scope"], "temporal_only")
        self.assertEqual(authorization_semantic_sha256(renewal), authorization_semantic_sha256(issued))

    def test_issuer_requires_trusted_template_and_explicit_acknowledgement(self) -> None:
        template_raw = MOVEMENT_AUTH_PATH.read_bytes()
        kwargs = {
            "schema_path": AUTH_SCHEMA,
            "now_utc": ISSUE_AT,
            "evidence_refs": ("gate:pa024f3a",),
        }
        with self.assertRaises(TypeError):
            issue_movement_authorization_snapshot(template_raw, **kwargs)
        for acknowledgement in (False, 1, "true", None):
            with self.subTest(acknowledgement=acknowledgement):
                with self.assertRaisesRegex(
                    MovementArmValidationError,
                    "acknowledgement",
                ):
                    issue_movement_authorization_snapshot(
                        template_raw,
                        acknowledge_single_pulse=acknowledgement,
                        **kwargs,
                    )

        replacements = (
            (
                b"406DA0C1C22D6E9121FD3BC17740A0D013660A03748CFE2A235768B8C574D3E6",
                b"A" * 64,
            ),
            (
                b"509F103A0A9A81832111754A11834A4A2DCCCC5F80D80FA2CB212C2DD705BD5A",
                b"B" * 64,
            ),
            (
                b"C515E91C8DAD4F515AC13B9A88FBDB6738E89BC4629E3D6CC5C37E619A808051",
                b"C" * 64,
            ),
            (
                b"actor:predator:lab-clone-01",
                b"actor:predator:lab-clone-02",
            ),
            (
                b"authorization:execution:tbc243-lab:movement-f3a-single-pulse:actor-expected",
                b"authorization:execution:tbc243-lab:movement-f3a-single-pulse:actor-mutated",
            ),
        )
        for old, new in replacements:
            with self.subTest(old=old):
                self.assertIn(old, template_raw)
                tampered = template_raw.replace(old, new, 1)
                with self.assertRaisesRegex(MovementArmValidationError, "trust anchor"):
                    issue_movement_authorization_snapshot(
                        tampered,
                        acknowledge_single_pulse=True,
                        **kwargs,
                    )

    def test_loader_rejects_self_authored_approved_snapshots(self) -> None:
        issued = json.loads(issued_authorization_raw())
        mutations = (
            ("authorization_id", "execution:tbc243-lab:movement-f3a-forged"),
            ("client_match.executable_sha256", "A" * 64),
            ("realm_match.listener_bindings.0.executable_sha256", "B" * 64),
            ("realm_match.expected_routing_sha256", "C" * 64),
            ("actor_binding.actor_id", "actor:predator:lab-clone-02"),
        )
        for path, value in mutations:
            with self.subTest(path=path):
                forged = copy.deepcopy(issued)
                parts = path.split(".")
                current = forged
                for part in parts[:-1]:
                    current = current[int(part)] if part.isdigit() else current[part]
                current[parts[-1]] = value
                self.authorization_validator.validate(forged)
                with self.assertRaises(MovementArmValidationError):
                    load_movement_authorization_profile(
                        exact_json_bytes(forged),
                        schema_path=AUTH_SCHEMA,
                        now_utc=NOW,
                    )

        no_ack = copy.deepcopy(issued)
        no_ack["approval"]["evidence_refs"] = ["gate:pa024f3a"]
        self.authorization_validator.validate(no_ack)
        with self.assertRaisesRegex(MovementArmValidationError, "acknowledgement"):
            load_movement_authorization_profile(
                exact_json_bytes(no_ack),
                schema_path=AUTH_SCHEMA,
                now_utc=NOW,
            )

    def test_realm_revalidation_requires_exact_external_non_authority_evidence(self) -> None:
        receipt_raw = exact_json_bytes(session_receipt_record())
        cases = (
            ("issuer_id", "untrusted.self_asserted_issuer"),
            ("execution_authority", True),
            ("pid", 4243),
            ("windows_session_id", True),
            ("session_receipt_nonce", 123),
            ("realm_routing_sha256", "B" * 64),
            ("expires_at", "2026-08-23T12:00:01Z"),
        )
        for field, value in cases:
            with self.subTest(field=field):
                revalidation = realm_revalidation_record(receipt_raw)
                revalidation[field] = value
                revalidation_raw = exact_json_bytes(revalidation)
                arm_record = movement_arm_record(session_receipt_raw=receipt_raw)
                arm_record["realm_revalidation"]["receipt_sha256"] = hashlib.sha256(
                    revalidation_raw
                ).hexdigest().upper()
                with self.assertRaises(MovementArmValidationError):
                    load_fixture_arm(
                        arm_record,
                        receipt_raw,
                        realm_revalidation_raw=revalidation_raw,
                    )

        receipt = session_receipt_record()
        receipt["execution_authority"] = True
        authority_receipt_raw = exact_json_bytes(receipt)
        arm_record = movement_arm_record(session_receipt_raw=authority_receipt_raw)
        with self.assertRaisesRegex(MovementArmValidationError, "schema"):
            load_fixture_arm(arm_record, authority_receipt_raw)

    def test_session_receipt_requires_current_trusted_fixed_ui_authorization(self) -> None:
        session_auth_raw = session_authorization_raw()
        session_auth = json.loads(session_auth_raw)
        self.authorization_validator.validate(session_auth)
        self.assertEqual(
            authorization_semantic_sha256(session_auth),
            "C66D8B8F7B6F29CDC9ED8FD9A5B07BBB89A689CE55693DBB5EB91CA09E392E41",
        )

        receipt_raw = exact_json_bytes(
            session_receipt_record(
                exact_session_authorization_raw=session_auth_raw
            )
        )
        arm_record = movement_arm_record(session_receipt_raw=receipt_raw)
        load_fixture_arm(
            arm_record,
            receipt_raw,
            exact_session_authorization_raw=session_auth_raw,
        )

        forged_auth = copy.deepcopy(session_auth)
        forged_auth["client_match"]["executable_sha256"] = "A" * 64
        forged_auth_raw = exact_json_bytes(forged_auth)
        forged_receipt = session_receipt_record(
            exact_session_authorization_raw=forged_auth_raw
        )
        forged_receipt_raw = exact_json_bytes(forged_receipt)
        forged_arm = movement_arm_record(
            session_receipt_raw=forged_receipt_raw
        )
        with self.assertRaisesRegex(MovementArmValidationError, "trusted fixed-UI"):
            load_fixture_arm(
                forged_arm,
                forged_receipt_raw,
                exact_session_authorization_raw=forged_auth_raw,
            )

        expired_auth = copy.deepcopy(session_auth)
        expired_auth["approval"]["recorded_at"] = "2026-08-23T11:00:00Z"
        expired_auth["approval"]["expires_at"] = "2026-08-23T11:30:00Z"
        expired_auth_raw = exact_json_bytes(expired_auth)
        expired_receipt = session_receipt_record(
            exact_session_authorization_raw=expired_auth_raw
        )
        expired_receipt["created_at"] = "2026-08-23T11:29:00Z"
        expired_receipt["expires_at"] = "2026-08-23T11:30:00Z"
        expired_receipt_raw = exact_json_bytes(expired_receipt)
        expired_arm = movement_arm_record(
            session_receipt_raw=expired_receipt_raw
        )
        with self.assertRaisesRegex(MovementArmValidationError, "expired"):
            load_fixture_arm(
                expired_arm,
                expired_receipt_raw,
                exact_session_authorization_raw=expired_auth_raw,
            )

    def test_f3a_compiler_and_real_gateway_enforce_one_forward_primitive(self) -> None:
        receipt_raw = exact_json_bytes(session_receipt_record())
        arm = load_fixture_arm(
            movement_arm_record(session_receipt_raw=receipt_raw),
            receipt_raw,
        )
        lease = arm.compile_execution_lease(
            lease_id="lease:f3a:single-forward",
            owner_id="controller:f3a:single-forward",
            now_monotonic_ms=2_000.0,
        )
        primitive = arm.compile_forward_primitive(
            lease=lease,
            primitive_id="primitive:f3a:forward:1",
            now_monotonic_ms=2_000.0,
            hold_duration_ms=100,
        )
        self.assertEqual(lease.allowed_controls, (MOVE_FORWARD_CONTROL,))
        self.assertEqual(lease.max_primitives, 1)
        self.assertEqual(lease.max_queue_depth, 1)
        self.assertEqual(primitive.controls, (MOVE_FORWARD_CONTROL,))
        self.assertEqual(lease.execution_policy(), F3A_EXECUTION_LEASE_POLICY)
        self.assertEqual(
            arm.execution_authorization().lease_policy,
            F3A_EXECUTION_LEASE_POLICY,
        )
        self.assertEqual(
            arm.runtime_snapshot().lease_policy,
            F3A_EXECUTION_LEASE_POLICY,
        )
        ContractValidator(EXECUTION_SCHEMA).validate(lease.to_record())
        ContractValidator(EXECUTION_SCHEMA).validate(primitive.to_record())

        binding = arm.binding
        pose = ExecutionPoseState(
            pose_id="pose:f3a:position-only",
            actor_id=binding.actor_id,
            actor_instance_id=binding.actor_instance_id,
            actor_role=binding.actor_role,
            decision_context=binding.decision_context,
            target_profile=binding.target_profile,
            target_instance_id=binding.target_instance_id,
            authorization_id=binding.authorization_id,
            authorization_sha256=binding.authorization_sha256,
            state="VALID",
            source_scope="lab_evaluation_only",
            source_id="fixture:f3a:pose",
            capability="pose_estimate",
            source_origins=("visible_addon_hud",),
            evidence_refs=("frame:f3a:one",),
            confidence=0.95,
            freshness_status="FRESH",
            available_pose_components=("POSITION_2D",),
            position_coordinate_space="normalized_current_zone_map",
            position_radius_95=1.0 / 65_535.0,
            yaw_error_95_deg=None,
            clock_id=arm.clock_id,
            observed_at_monotonic_ms=1_999.0,
            expires_at_monotonic_ms=3_500.0,
        )
        clock = ManualMonotonicClock(arm.clock_id, 2_000.0)
        sink = FakeInputSink()
        gateway = ExecutionGateway(
            authorization=arm.execution_authorization(),
            lease=lease,
            runtime_arm=InMemoryRuntimeArm(arm.runtime_snapshot()),
            clock=clock,
            sink=sink,
        )

        executed = gateway.execute(primitive, pose)
        self.assertEqual((executed.status, executed.reason_code), ("EXECUTED", "EXECUTED"))
        self.assertEqual([item.controls for item in sink.applied], [(MOVE_FORWARD_CONTROL,)])

        second = replace(
            primitive,
            primitive_id="primitive:f3a:forward:2",
            sequence=2,
        )
        exhausted = gateway.execute(second, pose)
        self.assertEqual(
            (exhausted.status, exhausted.reason_code),
            ("REJECTED", "PRIMITIVE_BUDGET_EXHAUSTED"),
        )
        self.assertEqual(len(sink.applied), 1)
        ContractValidator(EXECUTION_SCHEMA).validate(exhausted.to_record())

        denied_sink = FakeInputSink()
        denied_gateway = ExecutionGateway(
            authorization=arm.execution_authorization(),
            lease=lease,
            runtime_arm=InMemoryRuntimeArm(arm.runtime_snapshot()),
            clock=ManualMonotonicClock(arm.clock_id, 2_000.0),
            sink=denied_sink,
        )
        denied = denied_gateway.execute(
            replace(primitive, controls=("MOVE_BACKWARD",)),
            pose,
        )
        self.assertEqual(
            (denied.status, denied.reason_code),
            ("REJECTED", "CONTROL_DENIED"),
        )
        self.assertEqual(denied_sink.applied, [])
        ContractValidator(EXECUTION_SCHEMA).validate(denied.to_record())

        policy_mutations = (
            replace(
                lease,
                allowed_controls=("MOVE_FORWARD", "MOVE_BACKWARD"),
            ),
            replace(lease, max_primitives=2),
            replace(lease, max_hold_duration_ms=101),
            replace(lease, max_execution_envelope_ms=151),
            replace(lease, max_queue_depth=2),
            replace(lease, min_pose_confidence=0.899_999),
            replace(
                lease,
                required_pose_components=("POSITION_2D", "YAW"),
                max_yaw_error_95_deg=1.0,
            ),
            replace(lease, position_coordinate_space="world_map_2d"),
            replace(
                lease,
                max_position_radius_95=(2.0 / 65_535.0) + 1e-9,
            ),
            replace(
                lease,
                issued_at_monotonic_ms=arm.issued_at_monotonic_ms - 0.001,
            ),
        )
        for broadened in policy_mutations:
            with self.assertRaisesRegex(MovementArmValidationError, "exact F3a"):
                arm.compile_forward_primitive(
                    lease=broadened,
                    primitive_id="primitive:f3a:forbidden",
                    now_monotonic_ms=2_000.0,
                    hold_duration_ms=100,
                )

        # A manually widened lease cannot bypass the compiler by being passed
        # straight to the real gateway. Authorization rejects it first; when
        # authorization is deliberately widened in the fixture, the exact arm
        # independently rejects the same lease before FakeInputSink.
        widened = policy_mutations[0]
        authorization_sink = FakeInputSink()
        authorization_gateway = ExecutionGateway(
            authorization=arm.execution_authorization(),
            lease=widened,
            runtime_arm=InMemoryRuntimeArm(arm.runtime_snapshot()),
            clock=ManualMonotonicClock(arm.clock_id, 2_000.0),
            sink=authorization_sink,
        )
        authorization_denied = authorization_gateway.execute(primitive, pose)
        self.assertEqual(
            (authorization_denied.status, authorization_denied.reason_code),
            ("REJECTED", "LEASE_POLICY_DENIED"),
        )
        self.assertEqual(authorization_sink.applied, [])

        arm_sink = FakeInputSink()
        arm_gateway = ExecutionGateway(
            authorization=replace(
                arm.execution_authorization(),
                lease_policy=widened.execution_policy(),
            ),
            lease=widened,
            runtime_arm=InMemoryRuntimeArm(arm.runtime_snapshot()),
            clock=ManualMonotonicClock(arm.clock_id, 2_000.0),
            sink=arm_sink,
        )
        arm_denied = arm_gateway.execute(primitive, pose)
        self.assertEqual(
            (arm_denied.status, arm_denied.reason_code),
            ("REJECTED", "RUNTIME_ARM_POLICY_MISMATCH"),
        )
        self.assertEqual(arm_sink.applied, [])

    def test_runtime_arm_issuer_round_trips_exact_bytes_through_loader(self) -> None:
        movement_raw = issued_authorization_raw()
        session_auth_raw = session_authorization_raw()
        receipt_raw = exact_json_bytes(
            session_receipt_record(
                exact_session_authorization_raw=session_auth_raw
            )
        )
        revalidation_raw = exact_json_bytes(
            realm_revalidation_record(
                receipt_raw,
                authorization_raw=movement_raw,
            )
        )
        profile = validated_profile(
            exact_movement_authorization_raw=movement_raw,
            now_utc=NOW,
        )
        arm_raw = issue_movement_runtime_arm_snapshot(
            authorization=profile,
            authorization_raw=movement_raw,
            session_receipt_raw=receipt_raw,
            session_receipt_schema_path=RECEIPT_SCHEMA,
            session_authorization_raw=session_auth_raw,
            authorization_schema_path=AUTH_SCHEMA,
            realm_revalidation_raw=revalidation_raw,
            arm_schema_path=ARM_SCHEMA,
            now_utc=NOW,
            now_monotonic_ms=2_000.0,
            clock_id="clock:movement:f3a",
            acknowledge_single_pulse=True,
            arm_nonce="AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
        )
        self.assertEqual(arm_raw, exact_json_bytes(json.loads(arm_raw)))
        issued = json.loads(arm_raw)
        self.arm_validator.validate(issued)
        self.assertEqual(issued["allowed_controls"], ["MOVE_FORWARD"])
        self.assertEqual(issued["max_primitives"], 1)
        self.assertEqual(issued["issued_at_monotonic_ms"], 2_000.0)
        self.assertEqual(issued["expires_at_monotonic_ms"], 31_000.0)

        loaded = load_movement_runtime_arm(
            arm_raw,
            schema_path=ARM_SCHEMA,
            authorization=profile,
            session_receipt_raw=receipt_raw,
            session_receipt_schema_path=RECEIPT_SCHEMA,
            session_authorization_raw=session_auth_raw,
            authorization_schema_path=AUTH_SCHEMA,
            realm_revalidation_raw=revalidation_raw,
            acknowledge_single_pulse=True,
            now_utc=NOW,
            now_monotonic_ms=2_000.0,
        )
        self.assertEqual(loaded.arm_nonce, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    def test_runtime_arm_issuer_refuses_insufficient_remaining_window(self) -> None:
        movement_raw = issued_authorization_raw()
        session_auth_raw = session_authorization_raw()
        receipt_raw = exact_json_bytes(
            session_receipt_record(
                exact_session_authorization_raw=session_auth_raw
            )
        )
        revalidation_raw = exact_json_bytes(
            realm_revalidation_record(receipt_raw, authorization_raw=movement_raw)
        )
        with self.assertRaisesRegex(
            MovementArmValidationError, "cannot fit the single execution envelope"
        ):
            issue_movement_runtime_arm_snapshot(
                authorization=validated_profile(
                    exact_movement_authorization_raw=movement_raw,
                    now_utc=NOW,
                ),
                authorization_raw=movement_raw,
                session_receipt_raw=receipt_raw,
                session_receipt_schema_path=RECEIPT_SCHEMA,
                session_authorization_raw=session_auth_raw,
                authorization_schema_path=AUTH_SCHEMA,
                realm_revalidation_raw=revalidation_raw,
                arm_schema_path=ARM_SCHEMA,
                now_utc=datetime(2026, 8, 23, 12, 0, 29, 900000, tzinfo=timezone.utc),
                now_monotonic_ms=30_900.0,
                clock_id="clock:movement:f3a",
                acknowledge_single_pulse=True,
            )

    def test_utc_and_monotonic_elapsed_remaining_windows_must_align(self) -> None:
        receipt_raw = exact_json_bytes(session_receipt_record())
        at_tolerance = movement_arm_record(session_receipt_raw=receipt_raw)
        at_tolerance["issued_at_monotonic_ms"] = 1_001.0
        at_tolerance["expires_at_monotonic_ms"] = 31_001.0
        load_fixture_arm(at_tolerance, receipt_raw)

        shifted = movement_arm_record(session_receipt_raw=receipt_raw)
        shifted["issued_at_monotonic_ms"] = 1_001.01
        shifted["expires_at_monotonic_ms"] = 31_001.01
        with self.assertRaisesRegex(MovementArmValidationError, "elapsed/remaining"):
            load_fixture_arm(shifted, receipt_raw)

    def test_lease_control_and_primitive_budgets_have_three_layer_parity(self) -> None:
        receipt_raw = exact_json_bytes(session_receipt_record())
        arm = load_fixture_arm(
            movement_arm_record(session_receipt_raw=receipt_raw),
            receipt_raw,
        )
        lease = arm.compile_execution_lease(
            lease_id="lease:f3a:parity",
            owner_id="controller:f3a:parity",
            now_monotonic_ms=2_000.0,
        )
        validator = ContractValidator(EXECUTION_SCHEMA)
        for changes in (
            {"allowed_controls": []},
            {"allowed_controls": ["MOVE_FORWARD", "MOVE_FORWARD"]},
            {"allowed_controls": ["FLY"]},
            {"max_primitives": 0},
            {"max_primitives": 4_097},
            {"max_primitives": True},
        ):
            with self.subTest(raw=changes):
                record = lease.to_record()
                record.update(changes)
                with self.assertRaises(ContractValidationError):
                    validator.validate(record)
                with self.assertRaises(ValueError):
                    validate_execution_record_semantics(record)

        for changes in (
            {"allowed_controls": ()},
            {"allowed_controls": ("MOVE_FORWARD", "MOVE_FORWARD")},
            {"allowed_controls": ("FLY",)},
            {"max_primitives": 0},
            {"max_primitives": 4_097},
            {"max_primitives": True},
        ):
            with self.subTest(dataclass=changes):
                with self.assertRaises(ValueError):
                    replace(lease, **changes)

    def test_receipt_auth_revalidation_arm_and_now_have_strict_causality(self) -> None:
        receipt_raw = exact_json_bytes(session_receipt_record())

        before_authorization = realm_revalidation_record(receipt_raw)
        before_authorization["observed_at"] = "2026-08-23T11:59:59.900000Z"
        before_authorization["expires_at"] = "2026-08-23T12:00:29.900000Z"
        before_authorization_raw = exact_json_bytes(before_authorization)
        arm_record = movement_arm_record(session_receipt_raw=receipt_raw)
        arm_record["realm_revalidation"]["receipt_sha256"] = hashlib.sha256(
            before_authorization_raw
        ).hexdigest().upper()
        with self.assertRaisesRegex(MovementArmValidationError, "causal order"):
            load_fixture_arm(
                arm_record,
                receipt_raw,
                realm_revalidation_raw=before_authorization_raw,
            )

        after_arm = realm_revalidation_record(receipt_raw)
        after_arm["observed_at"] = "2026-08-23T12:00:00.100000Z"
        after_arm["expires_at"] = "2026-08-23T12:00:30.100000Z"
        after_arm_raw = exact_json_bytes(after_arm)
        arm_record = movement_arm_record(session_receipt_raw=receipt_raw)
        arm_record["realm_revalidation"]["receipt_sha256"] = hashlib.sha256(
            after_arm_raw
        ).hexdigest().upper()
        with self.assertRaisesRegex(MovementArmValidationError, "causal order"):
            load_fixture_arm(
                arm_record,
                receipt_raw,
                realm_revalidation_raw=after_arm_raw,
            )

        future_arm = movement_arm_record(session_receipt_raw=receipt_raw)
        future_arm["issued_at"] = "2026-08-23T12:00:02Z"
        future_arm["expires_at"] = "2026-08-23T12:00:30Z"
        future_arm["issued_at_monotonic_ms"] = 3_000.0
        future_arm["expires_at_monotonic_ms"] = 31_000.0
        with self.assertRaisesRegex(MovementArmValidationError, "causal order"):
            load_fixture_arm(future_arm, receipt_raw)

        early_movement_auth_raw = issued_authorization_raw(
            issue_at=datetime(2026, 8, 23, 11, 59, 40, tzinfo=timezone.utc)
        )
        later_receipt = session_receipt_record()
        later_receipt["created_at"] = "2026-08-23T11:59:59.950000Z"
        later_receipt_raw = exact_json_bytes(later_receipt)
        before_receipt = realm_revalidation_record(
            later_receipt_raw,
            authorization_raw=early_movement_auth_raw,
        )
        before_receipt["observed_at"] = "2026-08-23T11:59:59.900000Z"
        before_receipt["expires_at"] = "2026-08-23T12:00:29.900000Z"
        before_receipt_raw = exact_json_bytes(before_receipt)
        arm_record = movement_arm_record(
            session_receipt_raw=later_receipt_raw,
            authorization_raw=early_movement_auth_raw,
        )
        arm_record["realm_revalidation"]["receipt_sha256"] = hashlib.sha256(
            before_receipt_raw
        ).hexdigest().upper()
        with self.assertRaisesRegex(MovementArmValidationError, "causal order"):
            load_fixture_arm(
                arm_record,
                later_receipt_raw,
                realm_revalidation_raw=before_receipt_raw,
                exact_movement_authorization_raw=early_movement_auth_raw,
            )

    def test_cross_profile_hash_and_actor_substitution_fail_closed(self) -> None:
        receipt_raw = exact_json_bytes(session_receipt_record())
        wrong_hash = movement_arm_record(session_receipt_raw=receipt_raw)
        wrong_hash["authorization_sha256"] = "A" * 64
        with self.assertRaisesRegex(MovementArmValidationError, "authorization"):
            load_fixture_arm(wrong_hash, receipt_raw)

        wrong_actor = movement_arm_record(session_receipt_raw=receipt_raw)
        wrong_actor["actor_binding"]["actor_id"] = "actor:predator:other-lab-clone"
        self.arm_validator.validate(wrong_actor)
        with self.assertRaisesRegex(MovementArmValidationError, "arm actor"):
            load_fixture_arm(wrong_actor, receipt_raw)

    def test_receipt_nonce_hash_and_process_realm_identity_are_exact(self) -> None:
        receipt_raw = exact_json_bytes(session_receipt_record())
        cases = (
            ("session_receipt.receipt_nonce", "99999999-2222-3333-4444-555555555555"),
            ("session_receipt.receipt_sha256", "A" * 64),
            ("pid", 4243),
            ("hwnd", "0x1234ABCE"),
            ("process_creation_filetime_utc", "133742000000000001"),
            ("executable_path", "E:\\Games\\Other\\Wow.exe"),
            ("realm_routing_sha256", "B" * 64),
        )
        for path, value in cases:
            with self.subTest(path=path):
                arm_record = movement_arm_record(session_receipt_raw=receipt_raw)
                if path.startswith("session_receipt."):
                    arm_record["session_receipt"][path.split(".")[1]] = value
                else:
                    arm_record[path] = value
                self.arm_validator.validate(arm_record)
                with self.assertRaises(MovementArmValidationError):
                    load_fixture_arm(arm_record, receipt_raw)

        mismatched_filetime_receipt = session_receipt_record()
        mismatched_filetime_receipt["process_creation_filetime_utc"] = (
            "134319594000000001"
        )
        mismatched_filetime_raw = exact_json_bytes(mismatched_filetime_receipt)
        arm_record = movement_arm_record(
            session_receipt_raw=mismatched_filetime_raw
        )
        with self.assertRaisesRegex(MovementArmValidationError, "FILETIME"):
            load_fixture_arm(arm_record, mismatched_filetime_raw)

        null_hwnd_receipt = session_receipt_record()
        null_hwnd_receipt["hwnd"] = "0x0"
        null_hwnd_raw = exact_json_bytes(null_hwnd_receipt)
        arm_record = movement_arm_record(session_receipt_raw=null_hwnd_raw)
        with self.assertRaisesRegex(MovementArmValidationError, "handle"):
            load_fixture_arm(arm_record, null_hwnd_raw)

    def test_arm_wall_monotonic_and_receipt_lifetimes_are_bounded(self) -> None:
        receipt_raw = exact_json_bytes(session_receipt_record())

        too_long = movement_arm_record(session_receipt_raw=receipt_raw)
        too_long["expires_at"] = "2026-08-23T12:00:31Z"
        too_long["expires_at_monotonic_ms"] = (
            1_000.0 + MAX_MOVEMENT_ARM_LIFETIME_MS + 1_000.0
        )
        with self.assertRaisesRegex(MovementArmValidationError, "wall-clock"):
            load_fixture_arm(too_long, receipt_raw)

        expired = movement_arm_record(session_receipt_raw=receipt_raw)
        expired["expires_at"] = "2026-08-23T12:00:01Z"
        expired["expires_at_monotonic_ms"] = 2_000.0
        with self.assertRaisesRegex(MovementArmValidationError, "wall-clock"):
            load_fixture_arm(expired, receipt_raw)

        clocks_disagree = movement_arm_record(session_receipt_raw=receipt_raw)
        clocks_disagree["expires_at_monotonic_ms"] = 30_000.0
        with self.assertRaisesRegex(MovementArmValidationError, "monotonic"):
            load_fixture_arm(clocks_disagree, receipt_raw)

        short_receipt = session_receipt_record()
        short_receipt["expires_at"] = "2026-08-23T12:00:20Z"
        short_receipt_raw = exact_json_bytes(short_receipt)
        arm_record = movement_arm_record(session_receipt_raw=short_receipt_raw)
        with self.assertRaisesRegex(MovementArmValidationError, "wall-clock"):
            load_fixture_arm(arm_record, short_receipt_raw)

    def test_target_instance_and_receipt_version_cannot_be_forged(self) -> None:
        receipt_raw = exact_json_bytes(session_receipt_record())
        wrong_instance = movement_arm_record(session_receipt_raw=receipt_raw)
        wrong_instance["target_instance_id"] = "client:windows:4242:other"
        with self.assertRaisesRegex(MovementArmValidationError, "process identity"):
            load_fixture_arm(wrong_instance, receipt_raw)

        wrong_version = movement_arm_record(session_receipt_raw=receipt_raw)
        wrong_version["session_receipt"]["schema_version"] = "0.2"
        with self.assertRaises(ContractValidationError):
            self.arm_validator.validate(wrong_version)


if __name__ == "__main__":
    unittest.main()
