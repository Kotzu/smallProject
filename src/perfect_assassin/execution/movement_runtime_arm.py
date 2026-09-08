from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from math import isfinite
from pathlib import Path, PureWindowsPath
import re
from typing import Any
from uuid import uuid4

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator
from perfect_assassin.execution.contracts import (
    AuthorityBinding,
    ExecutionAuthorization,
    ExecutionLease,
    ExecutionLeasePolicy,
    MAX_PRIMITIVE_LIFETIME_MS,
    MovementPrimitive,
    RuntimeArmSnapshot,
)


MOVEMENT_AUTHORIZATION_SCHEMA_VERSION = "2.0"
MOVEMENT_AUTHORIZATION_ID = "execution:tbc243-lab:movement-f3a-single-pulse"
MOVEMENT_AUTHORIZATION_TEMPLATE_SHA256 = (
    "6D74054265EE6D1117A285D9CE8A68AF55E2C5160341B77A3794AF819CB19CFC"
)
MOVEMENT_AUTHORIZATION_TEMPLATE_SEMANTIC_SHA256 = (
    "D3BF0A391E34255593EB358A1DA518F9BED3F300D2668EB2B2A1ED76395AF35C"
)
SINGLE_PULSE_ACKNOWLEDGEMENT_REF = "operator_ack:pa024f3a:single_forward_pulse"
SESSION_AUTHORIZATION_ID = "execution:tbc243-lab:bounded-fixed-ui"
SESSION_AUTHORIZATION_SEMANTIC_SHA256 = (
    "C66D8B8F7B6F29CDC9ED8FD9A5B07BBB89A689CE55693DBB5EB91CA09E392E41"
)
MOVEMENT_ARM_SCHEMA_VERSION = "0.1"
SESSION_RECEIPT_RECORD_TYPE = "lab_client_launch_receipt"
SESSION_RECEIPT_SCHEMA_VERSION = "1.0"
REALM_REVALIDATION_RECORD_TYPE = "local_realm_revalidation_receipt"
REALM_REVALIDATION_SCHEMA_VERSION = "0.1"
REALM_REVALIDATION_ISSUER_ID = "perfect_assassin.local_realm_revalidator"
MOVEMENT_MODE = "MOVEMENT_ONLY"
MOVEMENT_CAPABILITY = "MOVEMENT_EXECUTION"
MOVE_FORWARD_CONTROL = "MOVE_FORWARD"
MAX_MOVEMENT_HOLD_MS = 100
MAX_MOVEMENT_ENVELOPE_MS = 150
MAX_MOVEMENT_PRIMITIVES = 1
MAX_MOVEMENT_ARM_LIFETIME_MS = 30_000
MAX_REALM_REVALIDATION_LIFETIME_MS = 30_000
MAX_RUNTIME_RECORD_BYTES = 2 * 1024 * 1024
MAX_CLOCK_WINDOW_DELTA_MS = 1.0
F3A_POSE_COORDINATE_SPACE = "normalized_current_zone_map"
F3A_MIN_POSE_CONFIDENCE = 0.9
F3A_MAX_POSITION_RADIUS_95 = 2.0 / 65_535.0
F3A_EXECUTION_LEASE_POLICY = ExecutionLeasePolicy(
    mode=MOVEMENT_MODE,
    capability=MOVEMENT_CAPABILITY,
    allowed_controls=(MOVE_FORWARD_CONTROL,),
    max_primitives=MAX_MOVEMENT_PRIMITIVES,
    max_hold_duration_ms=MAX_MOVEMENT_HOLD_MS,
    max_execution_envelope_ms=MAX_MOVEMENT_ENVELOPE_MS,
    max_queue_depth=1,
    min_pose_confidence=F3A_MIN_POSE_CONFIDENCE,
    required_pose_components=("POSITION_2D",),
    position_coordinate_space=F3A_POSE_COORDINATE_SPACE,
    max_position_radius_95=F3A_MAX_POSITION_RADIUS_95,
    max_yaw_error_95_deg=None,
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256 = re.compile(r"^[A-F0-9]{64}$")
_UUID = re.compile(
    r"^[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-"
    r"[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}$"
)
_WINDOWS_FILETIME_TIMESTAMP = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})"
    r"(?:\.(\d{1,7}))?Z$"
)
_WINDOWS_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


class MovementArmValidationError(ValueError):
    """A byte snapshot cannot authorize the single-pulse movement gate."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MovementArmValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_record_bytes(name: str, raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_RUNTIME_RECORD_BYTES:
        raise MovementArmValidationError(f"{name} must be bounded exact bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise MovementArmValidationError(f"{name} must not contain a BOM")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                MovementArmValidationError(
                    f"{name} contains a non-finite constant: {token}"
                )
            ),
        )
    except MovementArmValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise MovementArmValidationError(f"{name} is not strict UTF-8 JSON") from error
    if type(value) is not dict:
        raise MovementArmValidationError(f"{name} root must be an object")
    return value


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _canonical_object_bytes(value: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise MovementArmValidationError("record contains a non-canonical object") from error


def _canonical_object_sha256(value: dict[str, Any]) -> str:
    return _sha256(_canonical_object_bytes(value))


def _movement_template_projection_sha256(record: dict[str, Any]) -> str:
    projection = dict(record)
    projection["status"] = "pending_evidence"
    projection["permitted_modes"] = []
    projection["permitted_capabilities"] = []
    projection.pop("movement_policy", None)
    projection["approval"] = None
    return _canonical_object_sha256(projection)


def _authorization_rollover_semantic_sha256(record: dict[str, Any]) -> str:
    projection = dict(record)
    approval = projection.get("approval")
    if type(approval) is not dict:
        raise MovementArmValidationError("session authorization approval is missing")
    stable_approval = dict(approval)
    for field in (
        "recorded_at",
        "expires_at",
        "renews_authorization_sha256",
        "renewal_scope",
    ):
        stable_approval.pop(field, None)
    projection["approval"] = stable_approval
    return _canonical_object_sha256(projection)


def _require_identifier(name: str, value: Any) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise MovementArmValidationError(f"{name} is not a bounded identifier")
    return value


def _require_sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise MovementArmValidationError(f"{name} must be an uppercase SHA-256 digest")
    return value


def _require_uuid(name: str, value: Any) -> str:
    if type(value) is not str or _UUID.fullmatch(value) is None:
        raise MovementArmValidationError(f"{name} must be a UUID")
    return value.lower()


def _require_exact_int(name: str, value: Any, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MovementArmValidationError(
            f"{name} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _require_finite_number(name: str, value: Any) -> float:
    if (
        type(value) not in {int, float}
        or type(value) is bool
        or not isfinite(value)
    ):
        raise MovementArmValidationError(f"{name} must be finite")
    return float(value)


def _parse_time(name: str, value: Any, *, canonical_z: bool = False) -> datetime:
    if type(value) is not str or not value:
        raise MovementArmValidationError(f"{name} must be a timestamp")
    if canonical_z and not value.endswith("Z"):
        raise MovementArmValidationError(f"{name} must be canonical UTC Z time")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as error:
        raise MovementArmValidationError(f"{name} is not a valid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MovementArmValidationError(f"{name} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _require_matching_windows_filetime(
    timestamp: Any,
    filetime: Any,
) -> datetime:
    if type(timestamp) is not str or type(filetime) is not str:
        raise MovementArmValidationError("process creation identity must be strings")
    match = _WINDOWS_FILETIME_TIMESTAMP.fullmatch(timestamp)
    if match is None or not filetime.isdecimal() or not 17 <= len(filetime) <= 20:
        raise MovementArmValidationError(
            "process creation UTC and FILETIME formats are invalid"
        )
    year, month, day, hour, minute, second = map(int, match.groups()[:6])
    fractional_ticks = int((match.group(7) or "").ljust(7, "0"))
    try:
        whole_second = datetime(
            year,
            month,
            day,
            hour,
            minute,
            second,
            tzinfo=timezone.utc,
        )
    except ValueError as error:
        raise MovementArmValidationError(
            "process_created_at_utc is not a valid UTC timestamp"
        ) from error
    delta = whole_second - _WINDOWS_EPOCH
    expected_filetime = (
        (delta.days * 86_400 + delta.seconds) * 10_000_000
        + fractional_ticks
    )
    if int(filetime) != expected_filetime:
        raise MovementArmValidationError(
            "process creation UTC does not match its native FILETIME"
        )
    return whole_second.replace(microsecond=fractional_ticks // 10)


def _require_utc_now(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MovementArmValidationError("now_utc must be timezone-aware")
    return value.astimezone(timezone.utc)


def _actor_identity(record: dict[str, Any]) -> tuple[str, ...]:
    assurance = record.get("binding_assurance")
    if type(assurance) is not dict:
        raise MovementArmValidationError("actor binding assurance is missing")
    return (
        str(record.get("schema_version")),
        str(record.get("instance_id")),
        str(record.get("actor_role")),
        str(record.get("actor_id")),
        str(record.get("decision_context")),
        str(record.get("memory_namespace")),
        str(record.get("expected_character_name")),
        str(record.get("credential_alias")),
        str(assurance.get("state")),
    )


def _verified_build_signature(configured_signature: str, executable_sha256: str) -> str:
    return f"{configured_signature}:sha256:{executable_sha256}"


@dataclass(frozen=True, slots=True)
class MovementAuthorizationProfile:
    authorization_id: str
    authorization_sha256: str
    target_profile: str
    actor_binding_sha256: str
    actor_identity: tuple[str, ...]
    actor_id: str
    actor_instance_id: str
    actor_role: str
    decision_context: str
    client_build: str
    build_signature: str
    executable_sha256: str
    expected_realm_fingerprint: str
    realm_routing_sha256: str
    realmlist_relative_path: str
    realmlist_sha256: str
    realmlist_directive: str
    permitted_modes: frozenset[str]
    permitted_capabilities: frozenset[str]
    allowed_controls: tuple[str, ...]
    max_hold_duration_ms: int
    max_execution_envelope_ms: int
    max_primitives: int
    approval_recorded_at: datetime
    approval_expires_at: datetime


@dataclass(frozen=True, slots=True)
class MovementRuntimeArm:
    binding: AuthorityBinding
    record_sha256: str
    arm_nonce: str
    session_receipt_nonce: str
    session_receipt_sha256: str
    realm_revalidation_nonce: str
    realm_revalidation_sha256: str
    pid: int
    hwnd: str
    process_created_at_utc: str
    process_creation_filetime_utc: str
    windows_session_id: int
    window_title: str
    window_class: str
    client_build: str
    build_signature: str
    executable_path: str
    executable_sha256: str
    expected_realm_fingerprint: str
    realm_routing_sha256: str
    realmlist_relative_path: str
    realmlist_sha256: str
    realmlist_directive: str
    clock_id: str
    issued_at_monotonic_ms: float
    expires_at_monotonic_ms: float
    issued_at: datetime
    expires_at: datetime
    max_hold_duration_ms: int
    max_execution_envelope_ms: int
    max_primitives: int
    lease_policy: ExecutionLeasePolicy

    def __post_init__(self) -> None:
        _require_sha256("movement arm record_sha256", self.record_sha256)
        if self.lease_policy != F3A_EXECUTION_LEASE_POLICY:
            raise MovementArmValidationError(
                "movement arm must carry the exact versioned F3a lease policy"
            )
        if (
            self.max_hold_duration_ms != self.lease_policy.max_hold_duration_ms
            or self.max_execution_envelope_ms
            != self.lease_policy.max_execution_envelope_ms
            or self.max_primitives != self.lease_policy.max_primitives
        ):
            raise MovementArmValidationError(
                "movement arm scalar limits disagree with its F3a lease policy"
            )

    def runtime_snapshot(self) -> RuntimeArmSnapshot:
        return RuntimeArmSnapshot(
            binding=self.binding,
            arm_nonce=self.arm_nonce,
            clock_id=self.clock_id,
            issued_at_monotonic_ms=self.issued_at_monotonic_ms,
            expires_at_monotonic_ms=self.expires_at_monotonic_ms,
            allowed_modes=frozenset({MOVEMENT_MODE}),
            allowed_capabilities=frozenset({MOVEMENT_CAPABILITY}),
            lease_policy=self.lease_policy,
            active=True,
        )

    def execution_authorization(self) -> ExecutionAuthorization:
        return ExecutionAuthorization(
            binding=self.binding,
            clock_id=self.clock_id,
            issued_at_monotonic_ms=self.issued_at_monotonic_ms,
            expires_at_monotonic_ms=self.expires_at_monotonic_ms,
            permitted_modes=frozenset({MOVEMENT_MODE}),
            permitted_capabilities=frozenset({MOVEMENT_CAPABILITY}),
            lease_policy=self.lease_policy,
            active=True,
            runtime_arm_required=True,
        )

    def compile_execution_lease(
        self,
        *,
        lease_id: str,
        owner_id: str,
        now_monotonic_ms: float,
    ) -> ExecutionLease:
        """Compile the only lease shape authorized by the F3a movement arm."""

        current = _require_finite_number("now_monotonic_ms", now_monotonic_ms)
        if (
            current < self.issued_at_monotonic_ms
            or current + self.max_execution_envelope_ms
            > self.expires_at_monotonic_ms
        ):
            raise MovementArmValidationError(
                "F3a lease cannot fit inside the active movement arm"
            )
        policy = self.lease_policy
        return ExecutionLease(
            lease_id=lease_id,
            binding=self.binding,
            owner_id=owner_id,
            runtime_arm_nonce=self.arm_nonce,
            mode=MOVEMENT_MODE,
            capability=MOVEMENT_CAPABILITY,
            clock_id=self.clock_id,
            issued_at_monotonic_ms=current,
            expires_at_monotonic_ms=self.expires_at_monotonic_ms,
            first_sequence=1,
            max_hold_duration_ms=policy.max_hold_duration_ms,
            max_execution_envelope_ms=policy.max_execution_envelope_ms,
            max_queue_depth=policy.max_queue_depth,
            allowed_controls=policy.allowed_controls,
            max_primitives=policy.max_primitives,
            min_pose_confidence=policy.min_pose_confidence,
            required_pose_components=policy.required_pose_components,
            position_coordinate_space=policy.position_coordinate_space,
            max_position_radius_95=policy.max_position_radius_95,
            max_yaw_error_95_deg=policy.max_yaw_error_95_deg,
        )

    def compile_forward_primitive(
        self,
        *,
        lease: ExecutionLease,
        primitive_id: str,
        now_monotonic_ms: float,
        hold_duration_ms: int,
    ) -> MovementPrimitive:
        """Bind one forward-only primitive to an exact compiler-owned lease."""

        if not isinstance(lease, ExecutionLease):
            raise MovementArmValidationError("lease must be an ExecutionLease")
        expected_lease_policy = (
            lease.binding == self.binding
            and lease.runtime_arm_nonce == self.arm_nonce
            and lease.mode == MOVEMENT_MODE
            and lease.capability == MOVEMENT_CAPABILITY
            and lease.clock_id == self.clock_id
            and lease.first_sequence == 1
            and lease.execution_policy() == self.lease_policy
            and self.lease_policy == F3A_EXECUTION_LEASE_POLICY
            and lease.issued_at_monotonic_ms >= self.issued_at_monotonic_ms
            and lease.expires_at_monotonic_ms <= self.expires_at_monotonic_ms
        )
        if not expected_lease_policy:
            raise MovementArmValidationError(
                "lease does not preserve the exact F3a movement policy"
            )
        hold = _require_exact_int(
            "hold_duration_ms",
            hold_duration_ms,
            1,
            self.max_hold_duration_ms,
        )
        current = _require_finite_number("now_monotonic_ms", now_monotonic_ms)
        if (
            current < lease.issued_at_monotonic_ms
            or current + self.max_execution_envelope_ms
            > lease.expires_at_monotonic_ms
        ):
            raise MovementArmValidationError(
                "F3a primitive cannot fit inside the exact lease"
            )
        primitive_expires = min(
            current + MAX_PRIMITIVE_LIFETIME_MS,
            lease.expires_at_monotonic_ms,
        )
        return MovementPrimitive(
            primitive_id=primitive_id,
            lease_id=lease.lease_id,
            binding=self.binding,
            owner_id=lease.owner_id,
            runtime_arm_nonce=self.arm_nonce,
            mode=MOVEMENT_MODE,
            capability=MOVEMENT_CAPABILITY,
            sequence=lease.first_sequence,
            controls=(MOVE_FORWARD_CONTROL,),
            hold_duration_ms=hold,
            max_execution_envelope_ms=self.max_execution_envelope_ms,
            clock_id=self.clock_id,
            issued_at_monotonic_ms=current,
            expires_at_monotonic_ms=primitive_expires,
        )


def issue_movement_authorization_snapshot(
    template_raw: bytes,
    *,
    schema_path: Path,
    now_utc: datetime,
    evidence_refs: tuple[str, ...],
    acknowledge_single_pulse: bool,
) -> bytes:
    """Issue one ephemeral, canonical F3a authorization from a pending template."""

    record = _parse_record_bytes("movement authorization template", template_raw)
    if _sha256(template_raw) != MOVEMENT_AUTHORIZATION_TEMPLATE_SHA256:
        raise MovementArmValidationError(
            "movement authorization template does not match its repository trust anchor"
        )
    if acknowledge_single_pulse is not True:
        raise MovementArmValidationError(
            "single-pulse operator acknowledgement is required"
        )
    try:
        ContractValidator(schema_path).validate(record)
    except ContractValidationError as error:
        raise MovementArmValidationError(
            "movement authorization template does not satisfy its schema"
        ) from error
    current_utc = _require_utc_now(now_utc)
    if (
        record.get("record_type") != "execution_target_authorization"
        or record.get("schema_version") != MOVEMENT_AUTHORIZATION_SCHEMA_VERSION
        or record.get("authorization_id") != MOVEMENT_AUTHORIZATION_ID
        or record.get("target_profile") != "tbc_243_lab"
        or record.get("environment_scope") != "emulator_local"
        or record.get("status") != "pending_evidence"
        or record.get("permitted_modes") != []
        or record.get("permitted_capabilities") != []
        or "movement_policy" in record
        or record.get("approval") is not None
        or record.get("runtime_arm_required") is not True
    ):
        raise MovementArmValidationError(
            "movement authorization template is not the inert F3a profile"
        )
    actor = record.get("actor_binding")
    client = record.get("client_match")
    realm = record.get("realm_match")
    if (
        type(actor) is not dict
        or actor.get("actor_role") != "lab_clone"
        or actor.get("decision_context") != "lab_clone"
        or type(client) is not dict
        or type(realm) is not dict
        or realm.get("server_kind") != "emulator"
        or realm.get("realmlist_directive") != "set realmlist 127.0.0.1"
    ):
        raise MovementArmValidationError(
            "movement authorization template lacks exact LAB identity pins"
        )
    if (
        type(evidence_refs) is not tuple
        or not 1 <= len(evidence_refs) <= 3
        or len(set(evidence_refs)) != len(evidence_refs)
        or any(type(ref) is not str or not 1 <= len(ref) <= 256 for ref in evidence_refs)
        or SINGLE_PULSE_ACKNOWLEDGEMENT_REF in evidence_refs
    ):
        raise MovementArmValidationError("evidence_refs must be 1-3 bounded unique strings")

    recorded_at = current_utc.isoformat(timespec="microseconds").replace("+00:00", "Z")
    expires_at = (current_utc + timedelta(minutes=1)).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    record["status"] = "approved_bounded"
    record["permitted_modes"] = [MOVEMENT_MODE]
    record["permitted_capabilities"] = [
        "SCREEN_CAPTURE_READ_ONLY",
        "VISIBLE_COORDINATE_HUD_READ_ONLY",
        MOVEMENT_CAPABILITY,
    ]
    record["movement_policy"] = {
        "allowed_controls": [MOVE_FORWARD_CONTROL],
        "max_hold_duration_ms": MAX_MOVEMENT_HOLD_MS,
        "max_execution_envelope_ms": MAX_MOVEMENT_ENVELOPE_MS,
        "max_primitives": MAX_MOVEMENT_PRIMITIVES,
        "manual_takeover_required": True,
        "release_all_required": True,
        "combat_authorized": False,
        "economy_authorized": False,
    }
    record["approval"] = {
        "granted_by": "operator",
        "evidence_refs": [*evidence_refs, SINGLE_PULSE_ACKNOWLEDGEMENT_REF],
        "recorded_at": recorded_at,
        "expires_at": expires_at,
        "max_session_minutes": 1,
    }
    try:
        ContractValidator(schema_path).validate(record)
    except ContractValidationError as error:
        raise MovementArmValidationError(
            "issued movement authorization does not satisfy its schema"
        ) from error
    return _canonical_object_bytes(record)


def issue_session_authorization_snapshot(
    template_raw: bytes,
    *,
    schema_path: Path,
    now_utc: datetime,
    renewal_parent_sha256: str | None = None,
) -> bytes:
    """Refresh only the bounded time window of the exact fixed-UI profile."""

    record = _parse_record_bytes("session authorization template", template_raw)
    try:
        ContractValidator(schema_path).validate(record)
    except ContractValidationError as error:
        raise MovementArmValidationError(
            "session authorization template does not satisfy its schema"
        ) from error
    if (
        record.get("record_type") != "execution_target_authorization"
        or record.get("schema_version") != MOVEMENT_AUTHORIZATION_SCHEMA_VERSION
        or record.get("authorization_id") != SESSION_AUTHORIZATION_ID
        or record.get("target_profile") != "tbc_243_lab"
        or record.get("environment_scope") != "emulator_local"
        or record.get("status") != "approved_bounded"
        or record.get("permitted_modes") != []
        or set(record.get("permitted_capabilities", ()))
        != {
            "SCREEN_CAPTURE_READ_ONLY",
            "VISIBLE_COORDINATE_HUD_READ_ONLY",
            "LAB_OPERATOR_FIXED_UI",
        }
        or "movement_policy" in record
        or _authorization_rollover_semantic_sha256(record)
        != SESSION_AUTHORIZATION_SEMANTIC_SHA256
    ):
        raise MovementArmValidationError(
            "session authorization is not the exact fixed-UI semantic profile"
        )
    current_utc = _require_utc_now(now_utc)
    approval = dict(record["approval"])
    max_minutes = _require_exact_int(
        "approval.max_session_minutes",
        approval["max_session_minutes"],
        1,
        60,
    )
    approval["recorded_at"] = current_utc.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    approval["expires_at"] = (
        current_utc + timedelta(minutes=max_minutes)
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if renewal_parent_sha256 is None:
        approval.pop("renews_authorization_sha256", None)
        approval.pop("renewal_scope", None)
    else:
        approval["renews_authorization_sha256"] = _require_sha256(
            "renewal_parent_sha256", renewal_parent_sha256
        )
        approval["renewal_scope"] = "temporal_only"
    record["approval"] = approval
    raw = _canonical_object_bytes(record)
    try:
        ContractValidator(schema_path).validate(record)
    except ContractValidationError as error:
        raise MovementArmValidationError(
            "issued session authorization does not satisfy its schema"
        ) from error
    if _authorization_rollover_semantic_sha256(record) != SESSION_AUTHORIZATION_SEMANTIC_SHA256:
        raise MovementArmValidationError("session authorization issuer changed semantics")
    return raw


def load_movement_authorization_profile(
    raw: bytes, *, schema_path: Path, now_utc: datetime
) -> MovementAuthorizationProfile:
    """Validate one exact authorization byte snapshot without external effects."""

    record = _parse_record_bytes("movement authorization", raw)
    try:
        ContractValidator(schema_path).validate(record)
    except ContractValidationError as error:
        raise MovementArmValidationError(
            "movement authorization does not satisfy its schema"
        ) from error
    current_utc = _require_utc_now(now_utc)
    if (
        record.get("record_type") != "execution_target_authorization"
        or record.get("schema_version") != MOVEMENT_AUTHORIZATION_SCHEMA_VERSION
        or record.get("authorization_id") != MOVEMENT_AUTHORIZATION_ID
        or record.get("target_profile") != "tbc_243_lab"
        or record.get("status") != "approved_bounded"
        or record.get("environment_scope") != "emulator_local"
        or record.get("runtime_arm_required") is not True
    ):
        raise MovementArmValidationError("authorization is not an active local movement profile")
    if (
        _movement_template_projection_sha256(record)
        != MOVEMENT_AUTHORIZATION_TEMPLATE_SEMANTIC_SHA256
    ):
        raise MovementArmValidationError(
            "movement authorization does not match the trusted F3a template"
        )
    if record.get("permitted_modes") != [MOVEMENT_MODE]:
        raise MovementArmValidationError("authorization must permit only MOVEMENT_ONLY")
    expected_capabilities = {
        "SCREEN_CAPTURE_READ_ONLY",
        "VISIBLE_COORDINATE_HUD_READ_ONLY",
        MOVEMENT_CAPABILITY,
    }
    if set(record.get("permitted_capabilities", ())) != expected_capabilities:
        raise MovementArmValidationError("authorization capability set is not movement-only")
    if "LAB_OPERATOR_FIXED_UI" in record.get("permitted_capabilities", ()):
        raise MovementArmValidationError("fixed-UI authority cannot enter movement")

    actor = record["actor_binding"]
    client = record["client_match"]
    realm = record["realm_match"]
    policy = record["movement_policy"]
    approval = record["approval"]
    if (
        policy.get("allowed_controls") != [MOVE_FORWARD_CONTROL]
        or policy.get("max_hold_duration_ms") != MAX_MOVEMENT_HOLD_MS
        or policy.get("max_execution_envelope_ms") != MAX_MOVEMENT_ENVELOPE_MS
        or policy.get("max_primitives") != MAX_MOVEMENT_PRIMITIVES
        or policy.get("manual_takeover_required") is not True
        or policy.get("release_all_required") is not True
        or policy.get("combat_authorized") is not False
        or policy.get("economy_authorized") is not False
    ):
        raise MovementArmValidationError("movement policy exceeds the F3a single pulse")
    if (
        approval.get("granted_by") != "operator"
        or type(approval.get("evidence_refs")) is not list
        or not 2 <= len(approval["evidence_refs"]) <= 4
        or any(
            type(ref) is not str or not 1 <= len(ref) <= 256
            for ref in approval["evidence_refs"]
        )
        or len(set(approval["evidence_refs"])) != len(approval["evidence_refs"])
        or SINGLE_PULSE_ACKNOWLEDGEMENT_REF not in approval["evidence_refs"]
    ):
        raise MovementArmValidationError(
            "movement authorization lacks the single-pulse acknowledgement"
        )

    recorded_at = _parse_time(
        "approval.recorded_at", approval["recorded_at"], canonical_z=True
    )
    expires_at = _parse_time(
        "approval.expires_at", approval["expires_at"], canonical_z=True
    )
    max_session_minutes = _require_exact_int(
        "approval.max_session_minutes", approval["max_session_minutes"], 1, 1
    )
    policy_expiry = recorded_at + timedelta(minutes=max_session_minutes)
    if (
        recorded_at > current_utc
        or current_utc >= expires_at
        or expires_at > policy_expiry
    ):
        raise MovementArmValidationError(
            "movement authorization approval is expired, future, or overlong"
        )

    return MovementAuthorizationProfile(
        authorization_id=_require_identifier(
            "authorization_id", record["authorization_id"]
        ),
        authorization_sha256=_sha256(raw),
        target_profile=_require_identifier("target_profile", record["target_profile"]),
        actor_binding_sha256=_canonical_object_sha256(actor),
        actor_identity=_actor_identity(actor),
        actor_id=_require_identifier("actor_id", actor["actor_id"]),
        actor_instance_id=_require_identifier("instance_id", actor["instance_id"]),
        actor_role=actor["actor_role"],
        decision_context=actor["decision_context"],
        client_build=client["client_build"],
        build_signature=client["build_signature"],
        executable_sha256=_require_sha256(
            "client executable_sha256", client["executable_sha256"]
        ),
        expected_realm_fingerprint=realm["expected_realm_fingerprint"],
        realm_routing_sha256=_require_sha256(
            "expected_routing_sha256", realm["expected_routing_sha256"]
        ),
        realmlist_relative_path=realm["realmlist_relative_path"],
        realmlist_sha256=_require_sha256(
            "realmlist_sha256", realm["realmlist_sha256"]
        ),
        realmlist_directive=realm["realmlist_directive"],
        permitted_modes=frozenset(record["permitted_modes"]),
        permitted_capabilities=frozenset(record["permitted_capabilities"]),
        allowed_controls=tuple(policy["allowed_controls"]),
        max_hold_duration_ms=policy["max_hold_duration_ms"],
        max_execution_envelope_ms=policy["max_execution_envelope_ms"],
        max_primitives=policy["max_primitives"],
        approval_recorded_at=recorded_at,
        approval_expires_at=expires_at,
    )


def issue_movement_runtime_arm_snapshot(
    *,
    authorization: MovementAuthorizationProfile,
    authorization_raw: bytes,
    session_receipt_raw: bytes,
    session_receipt_schema_path: Path,
    session_authorization_raw: bytes,
    authorization_schema_path: Path,
    realm_revalidation_raw: bytes,
    arm_schema_path: Path,
    now_utc: datetime,
    now_monotonic_ms: float,
    clock_id: str,
    acknowledge_single_pulse: bool,
    arm_nonce: str | None = None,
) -> bytes:
    """Issue canonical arm bytes, then round-trip them through the strict loader."""

    if not isinstance(authorization, MovementAuthorizationProfile):
        raise MovementArmValidationError("authorization must be a validated movement profile")
    if acknowledge_single_pulse is not True:
        raise MovementArmValidationError("single-pulse operator acknowledgement is required")
    if _sha256(authorization_raw) != authorization.authorization_sha256:
        raise MovementArmValidationError("movement authorization bytes changed after validation")
    current_utc = _require_utc_now(now_utc)
    current_monotonic = _require_finite_number("now_monotonic_ms", now_monotonic_ms)
    _require_identifier("clock_id", clock_id)
    receipt = _parse_record_bytes("session receipt", session_receipt_raw)
    movement = _parse_record_bytes("movement authorization", authorization_raw)
    revalidation = _parse_record_bytes(
        "local realm revalidation receipt", realm_revalidation_raw
    )
    try:
        ContractValidator(session_receipt_schema_path).validate(receipt)
        ContractValidator(authorization_schema_path).validate(movement)
    except ContractValidationError as error:
        raise MovementArmValidationError(
            "arm issuer inputs do not satisfy their versioned schemas"
        ) from error

    receipt_expiry = _parse_time("receipt.expires_at", receipt["expires_at"])
    revalidation_expiry = _parse_time(
        "realm revalidation expires_at", revalidation["expires_at"], canonical_z=True
    )
    expiry = min(
        current_utc + timedelta(milliseconds=MAX_MOVEMENT_ARM_LIFETIME_MS),
        authorization.approval_expires_at,
        receipt_expiry,
        revalidation_expiry,
    )
    lifetime_ms = (expiry - current_utc).total_seconds() * 1_000.0
    if lifetime_ms < MAX_MOVEMENT_ENVELOPE_MS:
        raise MovementArmValidationError(
            "movement arm cannot fit the single execution envelope"
        )
    nonce = (arm_nonce or str(uuid4())).upper()
    _require_uuid("arm_nonce", nonce)
    actor = movement["actor_binding"]
    record: dict[str, Any] = {
        "record_type": "movement_runtime_arm",
        "schema_version": MOVEMENT_ARM_SCHEMA_VERSION,
        "arm_nonce": nonce,
        "authorization_id": authorization.authorization_id,
        "authorization_sha256": authorization.authorization_sha256,
        "session_receipt": {
            "record_type": SESSION_RECEIPT_RECORD_TYPE,
            "schema_version": SESSION_RECEIPT_SCHEMA_VERSION,
            "receipt_nonce": receipt["receipt_nonce"],
            "receipt_sha256": _sha256(session_receipt_raw),
            "execution_authority": False,
        },
        "target_profile": authorization.target_profile,
        "target_instance_id": (
            f"client:windows:{receipt['pid']}:"
            f"{receipt['process_creation_filetime_utc']}"
        ),
        "actor_binding": actor,
        "pid": receipt["pid"],
        "hwnd": receipt["hwnd"],
        "process_created_at_utc": receipt["process_created_at_utc"],
        "process_creation_filetime_utc": receipt["process_creation_filetime_utc"],
        "windows_session_id": receipt["windows_session_id"],
        "window_title": receipt["window_title"],
        "window_class": receipt["window_class"],
        "client_build": authorization.client_build,
        "build_signature": _verified_build_signature(
            authorization.build_signature,
            authorization.executable_sha256,
        ),
        "executable_path": receipt["executable_path"],
        "executable_sha256": authorization.executable_sha256,
        "environment_scope": "emulator_local",
        "server_kind": "emulator",
        "expected_realm_fingerprint": authorization.expected_realm_fingerprint,
        "realm_routing_sha256": authorization.realm_routing_sha256,
        "realmlist_relative_path": authorization.realmlist_relative_path,
        "realmlist_sha256": authorization.realmlist_sha256,
        "realmlist_directive": authorization.realmlist_directive,
        "realm_revalidation": {
            "record_type": REALM_REVALIDATION_RECORD_TYPE,
            "schema_version": REALM_REVALIDATION_SCHEMA_VERSION,
            "issuer_id": REALM_REVALIDATION_ISSUER_ID,
            "revalidation_nonce": revalidation["revalidation_nonce"],
            "receipt_sha256": _sha256(realm_revalidation_raw),
            "execution_authority": False,
        },
        "allowed_modes": [MOVEMENT_MODE],
        "allowed_capabilities": [MOVEMENT_CAPABILITY],
        "allowed_controls": [MOVE_FORWARD_CONTROL],
        "max_hold_duration_ms": MAX_MOVEMENT_HOLD_MS,
        "max_execution_envelope_ms": MAX_MOVEMENT_ENVELOPE_MS,
        "max_primitives": MAX_MOVEMENT_PRIMITIVES,
        "manual_takeover_required": True,
        "release_all_required": True,
        "combat_authorized": False,
        "economy_authorized": False,
        "clock_id": clock_id,
        "issued_at_monotonic_ms": current_monotonic,
        "expires_at_monotonic_ms": current_monotonic + lifetime_ms,
        "issued_at": current_utc.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "expires_at": expiry.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "active": True,
        "scope": "lab_movement_single_pulse",
        "execution_authority": True,
    }
    raw = _canonical_object_bytes(record)
    try:
        ContractValidator(arm_schema_path).validate(record)
    except ContractValidationError as error:
        raise MovementArmValidationError(
            "issued movement arm does not satisfy its schema"
        ) from error
    # Mandatory self-check prevents the issuer and loader contracts from drifting.
    load_movement_runtime_arm(
        raw,
        schema_path=arm_schema_path,
        authorization=authorization,
        session_receipt_raw=session_receipt_raw,
        session_receipt_schema_path=session_receipt_schema_path,
        session_authorization_raw=session_authorization_raw,
        authorization_schema_path=authorization_schema_path,
        realm_revalidation_raw=realm_revalidation_raw,
        acknowledge_single_pulse=True,
        now_utc=current_utc,
        now_monotonic_ms=current_monotonic,
    )
    return raw


def load_movement_runtime_arm(
    raw: bytes,
    *,
    schema_path: Path,
    authorization: MovementAuthorizationProfile,
    session_receipt_raw: bytes,
    session_receipt_schema_path: Path,
    session_authorization_raw: bytes,
    authorization_schema_path: Path,
    realm_revalidation_raw: bytes,
    acknowledge_single_pulse: bool,
    now_utc: datetime,
    now_monotonic_ms: float,
) -> MovementRuntimeArm:
    """Bind an arm to exact auth and non-authority session receipt snapshots."""

    if not isinstance(authorization, MovementAuthorizationProfile):
        raise MovementArmValidationError("authorization must be a validated movement profile")
    if acknowledge_single_pulse is not True:
        raise MovementArmValidationError(
            "single-pulse operator acknowledgement is required"
        )
    current_utc = _require_utc_now(now_utc)
    current_monotonic = _require_finite_number("now_monotonic_ms", now_monotonic_ms)

    record = _parse_record_bytes("movement runtime arm", raw)
    receipt = _parse_record_bytes("session receipt", session_receipt_raw)
    session_authorization = _parse_record_bytes(
        "session authorization", session_authorization_raw
    )
    revalidation = _parse_record_bytes(
        "local realm revalidation receipt", realm_revalidation_raw
    )
    try:
        ContractValidator(schema_path).validate(record)
        ContractValidator(session_receipt_schema_path).validate(receipt)
        ContractValidator(authorization_schema_path).validate(session_authorization)
    except ContractValidationError as error:
        raise MovementArmValidationError(
            "runtime arm or session receipt does not satisfy its schema"
        ) from error

    expected_session_capabilities = {
        "SCREEN_CAPTURE_READ_ONLY",
        "VISIBLE_COORDINATE_HUD_READ_ONLY",
        "LAB_OPERATOR_FIXED_UI",
    }
    if (
        session_authorization.get("record_type")
        != "execution_target_authorization"
        or session_authorization.get("schema_version")
        != MOVEMENT_AUTHORIZATION_SCHEMA_VERSION
        or session_authorization.get("authorization_id") != SESSION_AUTHORIZATION_ID
        or session_authorization.get("target_profile") != "tbc_243_lab"
        or session_authorization.get("environment_scope") != "emulator_local"
        or session_authorization.get("status") != "approved_bounded"
        or session_authorization.get("permitted_modes") != []
        or set(session_authorization.get("permitted_capabilities", ()))
        != expected_session_capabilities
        or "movement_policy" in session_authorization
        or _authorization_rollover_semantic_sha256(session_authorization)
        != SESSION_AUTHORIZATION_SEMANTIC_SHA256
    ):
        raise MovementArmValidationError(
            "session authorization is not the trusted fixed-UI identity profile"
        )
    session_approval = session_authorization["approval"]
    session_approval_recorded = _parse_time(
        "session authorization approval.recorded_at",
        session_approval["recorded_at"],
    )
    session_max_minutes = _require_exact_int(
        "session authorization approval.max_session_minutes",
        session_approval["max_session_minutes"],
        1,
        60,
    )
    session_bounded_expiry = session_approval_recorded + timedelta(
        minutes=session_max_minutes
    )
    if "expires_at" in session_approval:
        session_approval_expiry = _parse_time(
            "session authorization approval.expires_at",
            session_approval["expires_at"],
        )
        if session_approval_expiry > session_bounded_expiry:
            raise MovementArmValidationError(
                "session authorization explicit expiry exceeds its bound"
            )
    else:
        session_approval_expiry = session_bounded_expiry
    if not session_approval_recorded <= current_utc < session_approval_expiry:
        raise MovementArmValidationError(
            "session authorization is expired or not yet valid"
        )

    session_authorization_sha256 = _sha256(session_authorization_raw)
    if (
        receipt.get("authorization_id") != SESSION_AUTHORIZATION_ID
        or receipt.get("authorization_sha256") != session_authorization_sha256
        or receipt.get("authorization_semantic_sha256")
        != SESSION_AUTHORIZATION_SEMANTIC_SHA256
        or _canonical_object_sha256(receipt.get("actor_binding", {}))
        != _canonical_object_sha256(session_authorization.get("actor_binding", {}))
    ):
        raise MovementArmValidationError(
            "session receipt does not bind the exact trusted session authorization"
        )
    session_client = session_authorization["client_match"]
    session_realm = session_authorization["realm_match"]
    session_receipt_pins = (
        ("target_profile", session_authorization["target_profile"]),
        ("client_build", session_client["client_build"]),
        (
            "build_signature",
            _verified_build_signature(
                session_client["build_signature"],
                session_client["executable_sha256"],
            ),
        ),
        ("executable_sha256", session_client["executable_sha256"]),
        ("environment_scope", session_authorization["environment_scope"]),
        ("server_kind", session_realm["server_kind"]),
        ("expected_realm_fingerprint", session_realm["expected_realm_fingerprint"]),
        ("realm_routing_sha256", session_realm["expected_routing_sha256"]),
        ("realmlist_relative_path", session_realm["realmlist_relative_path"]),
        ("realmlist_sha256", session_realm["realmlist_sha256"]),
        ("realmlist_directive", session_realm["realmlist_directive"]),
        ("decision_context", session_authorization["actor_binding"]["decision_context"]),
    )
    for field, expected in session_receipt_pins:
        if receipt.get(field) != expected:
            raise MovementArmValidationError(
                f"session receipt {field} contradicts its authorization"
            )

    if (
        receipt.get("record_type") != SESSION_RECEIPT_RECORD_TYPE
        or receipt.get("schema_version") != SESSION_RECEIPT_SCHEMA_VERSION
        or receipt.get("execution_authority") is not False
    ):
        raise MovementArmValidationError("session receipt is not v1.0 non-authority evidence")
    receipt_declaration = record["session_receipt"]
    receipt_sha256 = _sha256(session_receipt_raw)
    if (
        receipt_declaration["record_type"] != SESSION_RECEIPT_RECORD_TYPE
        or receipt_declaration["schema_version"] != SESSION_RECEIPT_SCHEMA_VERSION
        or receipt_declaration["execution_authority"] is not False
        or _require_uuid("session receipt nonce", receipt_declaration["receipt_nonce"])
        != _require_uuid("receipt_nonce", receipt["receipt_nonce"])
        or receipt_declaration["receipt_sha256"] != receipt_sha256
    ):
        raise MovementArmValidationError("arm does not bind the exact session receipt bytes")

    revalidation_declaration = record["realm_revalidation"]
    revalidation_sha256 = _sha256(realm_revalidation_raw)
    expected_revalidation_keys = {
        "record_type",
        "schema_version",
        "issuer_id",
        "revalidation_nonce",
        "authorization_id",
        "authorization_sha256",
        "session_receipt_nonce",
        "session_receipt_sha256",
        "target_profile",
        "actor_id",
        "actor_instance_id",
        "pid",
        "hwnd",
        "process_created_at_utc",
        "process_creation_filetime_utc",
        "windows_session_id",
        "executable_path",
        "executable_sha256",
        "environment_scope",
        "server_kind",
        "expected_realm_fingerprint",
        "realm_routing_sha256",
        "realmlist_relative_path",
        "realmlist_sha256",
        "realmlist_directive",
        "method",
        "observed_at",
        "expires_at",
        "scope",
        "execution_authority",
    }
    if set(revalidation) != expected_revalidation_keys:
        raise MovementArmValidationError(
            "realm revalidation receipt fields are incomplete or unexpected"
        )
    revalidation_nonce = _require_uuid(
        "revalidation_nonce", revalidation["revalidation_nonce"]
    )
    if (
        revalidation_declaration["record_type"] != REALM_REVALIDATION_RECORD_TYPE
        or revalidation_declaration["schema_version"]
        != REALM_REVALIDATION_SCHEMA_VERSION
        or revalidation_declaration["issuer_id"] != REALM_REVALIDATION_ISSUER_ID
        or revalidation_declaration["execution_authority"] is not False
        or _require_uuid(
            "declared revalidation nonce",
            revalidation_declaration["revalidation_nonce"],
        )
        != revalidation_nonce
        or revalidation_declaration["receipt_sha256"] != revalidation_sha256
        or revalidation["record_type"] != REALM_REVALIDATION_RECORD_TYPE
        or revalidation["schema_version"] != REALM_REVALIDATION_SCHEMA_VERSION
        or revalidation["issuer_id"] != REALM_REVALIDATION_ISSUER_ID
        or revalidation["method"]
        != "exact_realmlist_listener_process_config_and_realm_route"
        or revalidation["scope"] != "lab_evaluation_only"
        or revalidation["execution_authority"] is not False
    ):
        raise MovementArmValidationError(
            "arm does not bind an accepted non-authority realm revalidation receipt"
        )

    if (
        record["authorization_id"] != authorization.authorization_id
        or record["authorization_sha256"] != authorization.authorization_sha256
        or record["target_profile"] != authorization.target_profile
    ):
        raise MovementArmValidationError("arm authorization/profile binding mismatch")
    arm_actor = record["actor_binding"]
    if _canonical_object_sha256(arm_actor) != authorization.actor_binding_sha256:
        raise MovementArmValidationError("arm actor does not match movement authorization")
    if _actor_identity(receipt["actor_binding"]) != authorization.actor_identity:
        raise MovementArmValidationError("session receipt actor identity mismatch")

    exact_profile_pairs = (
        ("client_build", authorization.client_build),
        (
            "build_signature",
            _verified_build_signature(
                authorization.build_signature,
                authorization.executable_sha256,
            ),
        ),
        ("executable_sha256", authorization.executable_sha256),
        ("expected_realm_fingerprint", authorization.expected_realm_fingerprint),
        ("realm_routing_sha256", authorization.realm_routing_sha256),
        ("realmlist_relative_path", authorization.realmlist_relative_path),
        ("realmlist_sha256", authorization.realmlist_sha256),
        ("realmlist_directive", authorization.realmlist_directive),
    )
    for field, expected in exact_profile_pairs:
        if record[field] != expected:
            raise MovementArmValidationError(f"arm {field} contradicts authorization")

    receipt_identity_fields = (
        "pid",
        "hwnd",
        "process_created_at_utc",
        "process_creation_filetime_utc",
        "windows_session_id",
        "window_title",
        "window_class",
        "client_build",
        "build_signature",
        "executable_path",
        "executable_sha256",
        "target_profile",
        "environment_scope",
        "server_kind",
        "expected_realm_fingerprint",
        "realm_routing_sha256",
        "realmlist_relative_path",
        "realmlist_sha256",
        "realmlist_directive",
    )
    for field in receipt_identity_fields:
        if record[field] != receipt[field]:
            raise MovementArmValidationError(f"arm/session receipt {field} mismatch")

    if (
        revalidation["authorization_id"] != authorization.authorization_id
        or revalidation["authorization_sha256"]
        != authorization.authorization_sha256
        or revalidation["target_profile"] != authorization.target_profile
        or revalidation["actor_id"] != authorization.actor_id
        or revalidation["actor_instance_id"] != authorization.actor_instance_id
        or _require_uuid(
            "realm revalidation session receipt nonce",
            revalidation["session_receipt_nonce"],
        )
        != _require_uuid("session receipt nonce", receipt["receipt_nonce"])
        or _require_sha256(
            "realm revalidation session receipt SHA-256",
            revalidation["session_receipt_sha256"],
        )
        != receipt_sha256
    ):
        raise MovementArmValidationError(
            "realm revalidation does not bind authorization, actor, and session"
        )
    revalidation_identity_fields = (
        "pid",
        "hwnd",
        "process_created_at_utc",
        "process_creation_filetime_utc",
        "windows_session_id",
        "executable_path",
        "executable_sha256",
        "environment_scope",
        "server_kind",
        "expected_realm_fingerprint",
        "realm_routing_sha256",
        "realmlist_relative_path",
        "realmlist_sha256",
        "realmlist_directive",
    )
    _require_exact_int(
        "realm revalidation pid", revalidation["pid"], 1, 0xFFFFFFFF
    )
    _require_exact_int(
        "realm revalidation windows_session_id",
        revalidation["windows_session_id"],
        0,
        0xFFFFFFFF,
    )
    for field in revalidation_identity_fields:
        if revalidation[field] != record[field]:
            raise MovementArmValidationError(
                f"realm revalidation {field} does not match the arm"
            )

    pid = _require_exact_int("pid", record["pid"], 1, 0xFFFFFFFF)
    try:
        hwnd_value = int(record["hwnd"], 16)
    except (TypeError, ValueError) as error:
        raise MovementArmValidationError("hwnd is not an exact hexadecimal handle") from error
    if not 1 <= hwnd_value <= 0xFFFFFFFFFFFFFFFF:
        raise MovementArmValidationError("hwnd is outside the Windows handle range")
    windows_session_id = _require_exact_int(
        "windows_session_id", record["windows_session_id"], 0, 0xFFFFFFFF
    )
    process_created = _require_matching_windows_filetime(
        record["process_created_at_utc"],
        record["process_creation_filetime_utc"],
    )
    expected_target_instance = (
        f"client:windows:{pid}:{record['process_creation_filetime_utc']}"
    )
    if record["target_instance_id"] != expected_target_instance:
        raise MovementArmValidationError("target_instance_id is not the exact process identity")
    executable_path = record["executable_path"]
    if (
        type(executable_path) is not str
        or len(executable_path) > 32_767
        or not PureWindowsPath(executable_path).is_absolute()
    ):
        raise MovementArmValidationError("executable_path must be an absolute Windows path")

    issued_at = _parse_time("issued_at", record["issued_at"], canonical_z=True)
    expires_at = _parse_time("expires_at", record["expires_at"], canonical_z=True)
    revalidated_at = _parse_time(
        "realm revalidation observed_at",
        revalidation["observed_at"],
        canonical_z=True,
    )
    revalidation_expires = _parse_time(
        "realm revalidation expires_at",
        revalidation["expires_at"],
        canonical_z=True,
    )
    receipt_created = _parse_time("receipt.created_at", receipt["created_at"])
    receipt_expires = _parse_time("receipt.expires_at", receipt["expires_at"])
    receipt_realm_verified = _parse_time(
        "receipt.realm_assurance.verified_at",
        receipt["realm_assurance"]["verified_at"],
    )
    if (
        session_approval_recorded > receipt_created
        or receipt_created > revalidated_at
        or authorization.approval_recorded_at > revalidated_at
        or receipt_realm_verified > revalidated_at
        or revalidated_at > issued_at
        or issued_at > current_utc
    ):
        raise MovementArmValidationError(
            "receipt, authorization, revalidation, arm, and now violate causal order"
        )
    wall_lifetime_ms = (expires_at - issued_at).total_seconds() * 1_000.0
    if (
        issued_at > current_utc
        or current_utc >= expires_at
        or wall_lifetime_ms <= 0
        or wall_lifetime_ms > MAX_MOVEMENT_ARM_LIFETIME_MS
        or issued_at < receipt_created
        or receipt_expires > session_approval_expiry
        or process_created > receipt_created
        or process_created > current_utc
        or receipt_realm_verified > receipt_created
        or expires_at > receipt_expires
        or expires_at > authorization.approval_expires_at
    ):
        raise MovementArmValidationError("movement arm wall-clock lifetime is invalid")
    if not receipt_created <= current_utc < receipt_expires:
        raise MovementArmValidationError("session receipt is expired or not yet valid")
    revalidation_lifetime_ms = (
        revalidation_expires - revalidated_at
    ).total_seconds() * 1_000.0
    if (
        revalidated_at > current_utc
        or current_utc >= revalidation_expires
        or expires_at > revalidation_expires
        or revalidation_lifetime_ms <= 0
        or revalidation_lifetime_ms > MAX_REALM_REVALIDATION_LIFETIME_MS
    ):
        raise MovementArmValidationError(
            "realm revalidation evidence is stale, future, or overlong"
        )

    issued_monotonic = _require_finite_number(
        "issued_at_monotonic_ms", record["issued_at_monotonic_ms"]
    )
    expires_monotonic = _require_finite_number(
        "expires_at_monotonic_ms", record["expires_at_monotonic_ms"]
    )
    monotonic_lifetime_ms = expires_monotonic - issued_monotonic
    if (
        issued_monotonic < 0
        or issued_monotonic > current_monotonic
        or current_monotonic >= expires_monotonic
        or monotonic_lifetime_ms <= 0
        or monotonic_lifetime_ms > MAX_MOVEMENT_ARM_LIFETIME_MS
        or abs(monotonic_lifetime_ms - wall_lifetime_ms)
        > MAX_CLOCK_WINDOW_DELTA_MS
    ):
        raise MovementArmValidationError("movement arm monotonic lifetime is invalid")
    wall_elapsed_ms = (current_utc - issued_at).total_seconds() * 1_000.0
    monotonic_elapsed_ms = current_monotonic - issued_monotonic
    wall_remaining_ms = (expires_at - current_utc).total_seconds() * 1_000.0
    monotonic_remaining_ms = expires_monotonic - current_monotonic
    if (
        abs(wall_elapsed_ms - monotonic_elapsed_ms)
        > MAX_CLOCK_WINDOW_DELTA_MS
        or abs(wall_remaining_ms - monotonic_remaining_ms)
        > MAX_CLOCK_WINDOW_DELTA_MS
    ):
        raise MovementArmValidationError(
            "movement arm UTC and monotonic elapsed/remaining windows diverge"
        )

    if (
        record["allowed_modes"] != [MOVEMENT_MODE]
        or record["allowed_capabilities"] != [MOVEMENT_CAPABILITY]
        or record["allowed_controls"] != [MOVE_FORWARD_CONTROL]
        or record["max_hold_duration_ms"] != authorization.max_hold_duration_ms
        or record["max_execution_envelope_ms"]
        != authorization.max_execution_envelope_ms
        or record["max_primitives"] != authorization.max_primitives
        or record["manual_takeover_required"] is not True
        or record["release_all_required"] is not True
        or record["combat_authorized"] is not False
        or record["economy_authorized"] is not False
        or record["active"] is not True
        or record["execution_authority"] is not True
    ):
        raise MovementArmValidationError("runtime arm exceeds its single-pulse policy")

    binding = AuthorityBinding(
        actor_id=authorization.actor_id,
        actor_instance_id=authorization.actor_instance_id,
        actor_role=authorization.actor_role,
        decision_context=authorization.decision_context,
        target_profile=authorization.target_profile,
        target_instance_id=_require_identifier(
            "target_instance_id", record["target_instance_id"]
        ),
        authorization_id=authorization.authorization_id,
        authorization_sha256=authorization.authorization_sha256,
    )
    return MovementRuntimeArm(
        binding=binding,
        record_sha256=_sha256(raw),
        arm_nonce=_require_uuid("arm_nonce", record["arm_nonce"]),
        session_receipt_nonce=_require_uuid(
            "session receipt nonce", receipt["receipt_nonce"]
        ),
        session_receipt_sha256=receipt_sha256,
        realm_revalidation_nonce=revalidation_nonce,
        realm_revalidation_sha256=revalidation_sha256,
        pid=pid,
        hwnd=record["hwnd"],
        process_created_at_utc=record["process_created_at_utc"],
        process_creation_filetime_utc=record["process_creation_filetime_utc"],
        windows_session_id=windows_session_id,
        window_title=record["window_title"],
        window_class=record["window_class"],
        client_build=record["client_build"],
        build_signature=record["build_signature"],
        executable_path=executable_path,
        executable_sha256=_require_sha256(
            "executable_sha256", record["executable_sha256"]
        ),
        expected_realm_fingerprint=record["expected_realm_fingerprint"],
        realm_routing_sha256=_require_sha256(
            "realm_routing_sha256", record["realm_routing_sha256"]
        ),
        realmlist_relative_path=record["realmlist_relative_path"],
        realmlist_sha256=_require_sha256(
            "realmlist_sha256", record["realmlist_sha256"]
        ),
        realmlist_directive=record["realmlist_directive"],
        clock_id=_require_identifier("clock_id", record["clock_id"]),
        issued_at_monotonic_ms=issued_monotonic,
        expires_at_monotonic_ms=expires_monotonic,
        issued_at=issued_at,
        expires_at=expires_at,
        max_hold_duration_ms=record["max_hold_duration_ms"],
        max_execution_envelope_ms=record["max_execution_envelope_ms"],
        max_primitives=record["max_primitives"],
        lease_policy=F3A_EXECUTION_LEASE_POLICY,
    )
