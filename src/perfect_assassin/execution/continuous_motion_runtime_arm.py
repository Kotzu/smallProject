"""Bounded issuer for a continuous F4a navigation runtime arm.

This module creates a short-lived record only after the approved F4a
authorization, fixed-UI session receipt and fresh local realm revalidation are
all present. It has no game or input dependency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator
from perfect_assassin.execution.continuous_motion_authorization import (
    CONTINUOUS_MOTION_ACKNOWLEDGEMENT_REF,
    CONTINUOUS_NAVIGATION_AUTHORIZATION_ID,
    CONTINUOUS_NAVIGATION_CONTROLS,
    CONTINUOUS_NAVIGATION_MAX_ENVELOPE_MS,
    CONTINUOUS_NAVIGATION_MAX_HOLD_MS,
    CONTINUOUS_NAVIGATION_MAX_PRIMITIVES,
    ContinuousMotionAuthorizationProfile,
)


MAX_ARM_LIFETIME_MS = 10 * 60 * 1000
REALM_REVALIDATION_RECORD_TYPE = "local_realm_revalidation_receipt"


class ContinuousMotionRuntimeArmError(ValueError):
    pass


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _read(raw: bytes, name: str) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= 2 * 1024 * 1024:
        raise ContinuousMotionRuntimeArmError(f"{name} is outside its byte bound")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise ContinuousMotionRuntimeArmError(f"{name} is not strict JSON") from error
    if type(value) is not dict:
        raise ContinuousMotionRuntimeArmError(f"{name} root must be an object")
    return value


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _time(value: Any, name: str) -> datetime:
    if type(value) is not str:
        raise ContinuousMotionRuntimeArmError(f"{name} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContinuousMotionRuntimeArmError(f"{name} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContinuousMotionRuntimeArmError(f"{name} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def issue_continuous_motion_runtime_arm_snapshot(
    *,
    authorization: ContinuousMotionAuthorizationProfile,
    authorization_raw: bytes,
    session_authorization_raw: bytes,
    session_receipt_raw: bytes,
    realm_revalidation_raw: bytes,
    arm_schema_path: Path,
    authorization_schema_path: Path,
    session_receipt_schema_path: Path,
    realm_revalidation_schema_path: Path,
    now_utc: datetime,
    now_monotonic_ms: float,
    clock_id: str,
    arm_nonce: str | None = None,
) -> bytes:
    if not isinstance(authorization, ContinuousMotionAuthorizationProfile):
        raise ContinuousMotionRuntimeArmError("authorization profile is not validated")
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ContinuousMotionRuntimeArmError("now_utc must include an offset")
    now = now_utc.astimezone(timezone.utc)
    if type(now_monotonic_ms) not in {int, float} or now_monotonic_ms < 0:
        raise ContinuousMotionRuntimeArmError("now_monotonic_ms is invalid")
    if type(clock_id) is not str or not clock_id:
        raise ContinuousMotionRuntimeArmError("clock_id is invalid")
    if _sha256(authorization_raw) != authorization.raw_sha256:
        raise ContinuousMotionRuntimeArmError("authorization bytes changed after validation")
    authorization_record = _read(authorization_raw, "continuous authorization")
    session = _read(session_authorization_raw, "session authorization")
    receipt = _read(session_receipt_raw, "session receipt")
    revalidation = _read(realm_revalidation_raw, "realm revalidation")
    try:
        ContractValidator(authorization_schema_path).validate(authorization_record)
        ContractValidator(session_receipt_schema_path).validate(receipt)
        ContractValidator(realm_revalidation_schema_path).validate(revalidation)
    except ContractValidationError as error:
        raise ContinuousMotionRuntimeArmError("arm evidence failed its contract") from error
    if (
        session.get("authorization_id") != "execution:tbc243-lab:bounded-fixed-ui"
        or session.get("permitted_modes") != []
        or set(session.get("permitted_capabilities", ()))
        != {
            "SCREEN_CAPTURE_READ_ONLY",
            "VISIBLE_COORDINATE_HUD_READ_ONLY",
            "LAB_OPERATOR_FIXED_UI",
        }
        or session.get("status") != "approved_bounded"
        or session.get("environment_scope") != "emulator_local"
        or receipt.get("execution_authority") is not False
        or receipt.get("authorization_sha256") != _sha256(session_authorization_raw)
        or receipt.get("actor_binding") != session.get("actor_binding")
    ):
        raise ContinuousMotionRuntimeArmError(
            "session receipt is not the exact non-authority fixed-UI evidence"
        )
    if (
        revalidation.get("record_type") != REALM_REVALIDATION_RECORD_TYPE
        or revalidation.get("execution_authority") is not False
        or revalidation.get("authorization_id") != CONTINUOUS_NAVIGATION_AUTHORIZATION_ID
        or revalidation.get("authorization_sha256") != _sha256(authorization_raw)
        or revalidation.get("session_receipt_nonce") != receipt.get("receipt_nonce")
        or revalidation.get("session_receipt_sha256") != _sha256(session_receipt_raw)
        or revalidation.get("actor_id") != authorization.actor_binding.get("actor_id")
        or revalidation.get("actor_instance_id") != authorization.actor_binding.get("instance_id")
    ):
        raise ContinuousMotionRuntimeArmError(
            "realm revalidation does not bind authorization, receipt and actor"
        )
    if not authorization_record.get("approval", {}).get("evidence_refs"):
        raise ContinuousMotionRuntimeArmError("F4a approval has no evidence")
    if CONTINUOUS_MOTION_ACKNOWLEDGEMENT_REF not in authorization_record["approval"]["evidence_refs"]:
        raise ContinuousMotionRuntimeArmError("F4a acknowledgement evidence is missing")

    receipt_expires = _time(receipt["expires_at"], "session receipt expires_at")
    revalidation_expires = _time(revalidation["expires_at"], "realm revalidation expires_at")
    expiry = min(
        now + timedelta(milliseconds=MAX_ARM_LIFETIME_MS),
        authorization.approval_expires_at,
        receipt_expires,
        revalidation_expires,
    )
    lifetime_ms = (expiry - now).total_seconds() * 1000.0
    if lifetime_ms < CONTINUOUS_NAVIGATION_MAX_ENVELOPE_MS:
        raise ContinuousMotionRuntimeArmError("continuous arm has insufficient remaining time")
    nonce = arm_nonce or str(uuid4())
    try:
        nonce = str(UUID(nonce)).lower()
    except (ValueError, AttributeError, TypeError) as error:
        raise ContinuousMotionRuntimeArmError("arm_nonce is not a UUID") from error
    process_filetime = str(receipt["process_creation_filetime_utc"])
    pid = int(receipt["pid"])
    record: dict[str, Any] = {
        "record_type": "continuous_motion_runtime_arm",
        "schema_version": "0.1",
        "arm_nonce": nonce,
        "authorization_id": CONTINUOUS_NAVIGATION_AUTHORIZATION_ID,
        "authorization_sha256": _sha256(authorization_raw),
        "session_receipt_sha256": _sha256(session_receipt_raw),
        "realm_revalidation_sha256": _sha256(realm_revalidation_raw),
        "target_profile": authorization.target_profile,
        "target_instance_id": f"client:windows:{pid}:{process_filetime}",
        "actor_binding": authorization.actor_binding,
        "pid": pid,
        "hwnd": receipt["hwnd"],
        "process_creation_filetime_utc": process_filetime,
        "window_title": receipt["window_title"],
        "window_class": receipt["window_class"],
        "executable_path": receipt["executable_path"],
        "executable_sha256": receipt["executable_sha256"],
        "clock_id": clock_id,
        "issued_at_monotonic_ms": float(now_monotonic_ms),
        "expires_at_monotonic_ms": float(now_monotonic_ms) + lifetime_ms,
        "allowed_controls": list(CONTINUOUS_NAVIGATION_CONTROLS),
        "max_hold_duration_ms": CONTINUOUS_NAVIGATION_MAX_HOLD_MS,
        "max_execution_envelope_ms": CONTINUOUS_NAVIGATION_MAX_ENVELOPE_MS,
        "max_primitives": CONTINUOUS_NAVIGATION_MAX_PRIMITIVES,
        "lease_timeout_ms": CONTINUOUS_NAVIGATION_MAX_HOLD_MS,
        "manual_takeover_required": True,
        "release_all_required": True,
        "combat_authorized": False,
        "economy_authorized": False,
        "active": True,
        "scope": "lab_movement_continuous_navmesh",
        "execution_authority": True,
    }
    try:
        ContractValidator(arm_schema_path).validate(record)
    except ContractValidationError as error:
        raise ContinuousMotionRuntimeArmError("issued F4a arm failed its contract") from error
    return _canonical(record)
