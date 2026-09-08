"""Issuer for the explicitly acknowledged local F4a navigation profile.

The issuer starts from the already reviewed fixed-UI template and widens it
only when the operator gives a separate continuous-motion acknowledgement.
It never copies game/addon content and it never sends input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator


CONTINUOUS_NAVIGATION_AUTHORIZATION_ID = (
    "execution:tbc243-lab:movement-f4a-continuous-navmesh"
)
CONTINUOUS_NAVIGATION_MODE = "MOVEMENT_ONLY"
CONTINUOUS_NAVIGATION_CAPABILITIES = (
    "SCREEN_CAPTURE_READ_ONLY",
    "VISIBLE_COORDINATE_HUD_READ_ONLY",
    "MOVEMENT_EXECUTION",
)
CONTINUOUS_NAVIGATION_CONTROLS = (
    "MOVE_FORWARD",
    "MOVE_BACKWARD",
    "STRAFE_LEFT",
    "STRAFE_RIGHT",
)
CONTINUOUS_NAVIGATION_MAX_HOLD_MS = 450
CONTINUOUS_NAVIGATION_MAX_ENVELOPE_MS = 500
CONTINUOUS_NAVIGATION_MAX_PRIMITIVES = 4096
CONTINUOUS_NAVIGATION_MAX_SESSION_MINUTES = 10
CONTINUOUS_MOTION_ACKNOWLEDGEMENT_REF = (
    "operator_ack:pa024f4a:continuous_navmesh"
)


class ContinuousMotionAuthorizationError(ValueError):
    pass


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _read_object(raw: bytes, name: str) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= 2 * 1024 * 1024:
        raise ContinuousMotionAuthorizationError(f"{name} is outside its byte bound")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise ContinuousMotionAuthorizationError(f"{name} is not strict JSON") from error
    if type(value) is not dict:
        raise ContinuousMotionAuthorizationError(f"{name} root must be an object")
    return value


def _canonical(value: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ContinuousMotionAuthorizationError("authorization is not canonical JSON") from error


@dataclass(frozen=True, slots=True)
class ContinuousMotionAuthorizationProfile:
    record: dict[str, Any]
    raw_sha256: str
    authorization_id: str
    target_profile: str
    actor_binding: dict[str, Any]
    client_match: dict[str, Any]
    realm_match: dict[str, Any]
    approval_recorded_at: datetime
    approval_expires_at: datetime
    renews_authorization_sha256: str | None


def issue_continuous_motion_authorization_snapshot(
    template_raw: bytes,
    *,
    schema_path: Path,
    now_utc: datetime,
    evidence_refs: tuple[str, ...],
    acknowledge_continuous_motion: bool,
    renewal_parent_sha256: str | None = None,
) -> bytes:
    """Issue a bounded F4a authorization from the exact fixed-UI template."""

    if acknowledge_continuous_motion is not True:
        raise ContinuousMotionAuthorizationError(
            "continuous navigation operator acknowledgement is required"
        )
    if (
        type(evidence_refs) is not tuple
        or not 1 <= len(evidence_refs) <= 3
        or len(set(evidence_refs)) != len(evidence_refs)
        or any(type(ref) is not str or not 1 <= len(ref) <= 256 for ref in evidence_refs)
        or CONTINUOUS_MOTION_ACKNOWLEDGEMENT_REF in evidence_refs
    ):
        raise ContinuousMotionAuthorizationError("evidence_refs must be bounded and unique")
    record = _read_object(template_raw, "fixed-UI authorization template")
    try:
        ContractValidator(schema_path).validate(record)
    except ContractValidationError as error:
        raise ContinuousMotionAuthorizationError(
            "fixed-UI template does not satisfy its authorization contract"
        ) from error
    fixed_caps = {
        "SCREEN_CAPTURE_READ_ONLY",
        "VISIBLE_COORDINATE_HUD_READ_ONLY",
        "LAB_OPERATOR_FIXED_UI",
    }
    if (
        record.get("record_type") != "execution_target_authorization"
        or record.get("schema_version") != "2.0"
        or record.get("authorization_id") != "execution:tbc243-lab:bounded-fixed-ui"
        or record.get("status") != "approved_bounded"
        or record.get("environment_scope") != "emulator_local"
        or record.get("permitted_modes") != []
        or set(record.get("permitted_capabilities", ())) != fixed_caps
        or "movement_policy" in record
        or type(record.get("approval")) is not dict
    ):
        raise ContinuousMotionAuthorizationError(
            "template is not the exact fixed-UI profile"
        )
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ContinuousMotionAuthorizationError("now_utc must include a UTC offset")
    current = now_utc.astimezone(timezone.utc)
    approval_recorded = current.isoformat(timespec="microseconds").replace("+00:00", "Z")
    approval_expires = (
        current + timedelta(minutes=CONTINUOUS_NAVIGATION_MAX_SESSION_MINUTES)
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")
    record = dict(record)
    record["authorization_id"] = CONTINUOUS_NAVIGATION_AUTHORIZATION_ID
    record["status"] = "approved_bounded"
    record["permitted_modes"] = [CONTINUOUS_NAVIGATION_MODE]
    record["permitted_capabilities"] = list(CONTINUOUS_NAVIGATION_CAPABILITIES)
    record["restrictions"] = [
        "continuous_navmesh_only",
        "no_combat",
        "no_gathering_or_economy",
        "manual_takeover_required",
        "release_all_required",
        "fresh_authorization_snapshot_required",
        "no_memory_or_kernel_access",
    ]
    record["movement_policy"] = {
        "allowed_controls": list(CONTINUOUS_NAVIGATION_CONTROLS),
        "max_hold_duration_ms": CONTINUOUS_NAVIGATION_MAX_HOLD_MS,
        "max_execution_envelope_ms": CONTINUOUS_NAVIGATION_MAX_ENVELOPE_MS,
        "max_primitives": CONTINUOUS_NAVIGATION_MAX_PRIMITIVES,
        "manual_takeover_required": True,
        "release_all_required": True,
        "combat_authorized": False,
        "economy_authorized": False,
    }
    record["approval"] = {
        "granted_by": "operator",
        "evidence_refs": [*evidence_refs, CONTINUOUS_MOTION_ACKNOWLEDGEMENT_REF],
        "recorded_at": approval_recorded,
        "expires_at": approval_expires,
        "max_session_minutes": CONTINUOUS_NAVIGATION_MAX_SESSION_MINUTES,
    }
    if renewal_parent_sha256 is not None:
        if (
            type(renewal_parent_sha256) is not str
            or len(renewal_parent_sha256) != 64
            or any(character not in "0123456789ABCDEF" for character in renewal_parent_sha256)
        ):
            raise ContinuousMotionAuthorizationError(
                "renewal parent authorization hash is invalid"
            )
        record["approval"]["renews_authorization_sha256"] = renewal_parent_sha256
        record["approval"]["renewal_scope"] = "temporal_only"
    try:
        ContractValidator(schema_path).validate(record)
    except ContractValidationError as error:
        raise ContinuousMotionAuthorizationError(
            "issued F4a authorization does not satisfy its contract"
        ) from error
    return _canonical(record)


def load_continuous_motion_authorization_profile(
    raw: bytes, *, schema_path: Path, now_utc: datetime
) -> ContinuousMotionAuthorizationProfile:
    record = _read_object(raw, "continuous motion authorization")
    try:
        ContractValidator(schema_path).validate(record)
    except ContractValidationError as error:
        raise ContinuousMotionAuthorizationError(
            "continuous motion authorization failed its contract"
        ) from error
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ContinuousMotionAuthorizationError("now_utc must include a UTC offset")
    current = now_utc.astimezone(timezone.utc)
    if (
        record.get("authorization_id") != CONTINUOUS_NAVIGATION_AUTHORIZATION_ID
        or record.get("status") != "approved_bounded"
        or record.get("permitted_modes") != [CONTINUOUS_NAVIGATION_MODE]
        or tuple(record.get("permitted_capabilities", ())) != CONTINUOUS_NAVIGATION_CAPABILITIES
        or record.get("movement_policy", {}).get("allowed_controls")
        != list(CONTINUOUS_NAVIGATION_CONTROLS)
    ):
        raise ContinuousMotionAuthorizationError("authorization is not the exact F4a profile")
    approval = record["approval"]
    recorded = datetime.fromisoformat(approval["recorded_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(approval["expires_at"].replace("Z", "+00:00"))
    if not recorded <= current < expires:
        raise ContinuousMotionAuthorizationError("F4a authorization is expired or not yet valid")
    if expires > recorded + timedelta(minutes=CONTINUOUS_NAVIGATION_MAX_SESSION_MINUTES):
        raise ContinuousMotionAuthorizationError("F4a authorization exceeds its bounded lifetime")
    if CONTINUOUS_MOTION_ACKNOWLEDGEMENT_REF not in approval.get("evidence_refs", ()):
        raise ContinuousMotionAuthorizationError("F4a acknowledgement evidence is missing")
    renewal_parent = approval.get("renews_authorization_sha256")
    if renewal_parent is not None and (
        type(renewal_parent) is not str
        or len(renewal_parent) != 64
        or any(character not in "0123456789ABCDEF" for character in renewal_parent)
        or approval.get("renewal_scope") != "temporal_only"
    ):
        raise ContinuousMotionAuthorizationError("F4a temporal renewal chain is invalid")
    return ContinuousMotionAuthorizationProfile(
        record=record,
        raw_sha256=_sha256(raw),
        authorization_id=CONTINUOUS_NAVIGATION_AUTHORIZATION_ID,
        target_profile=str(record["target_profile"]),
        actor_binding=dict(record["actor_binding"]),
        client_match=dict(record["client_match"]),
        realm_match=dict(record["realm_match"]),
        approval_recorded_at=recorded.astimezone(timezone.utc),
        approval_expires_at=expires.astimezone(timezone.utc),
        renews_authorization_sha256=renewal_parent,
    )
