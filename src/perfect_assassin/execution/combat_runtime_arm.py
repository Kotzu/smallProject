from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from math import isfinite
from pathlib import Path
from typing import Any
from uuid import uuid4

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator
from perfect_assassin.execution.combat_authorization import (
    COMBAT_EXECUTION_AUTHORIZATION_ID,
    COMBAT_EXECUTION_SEMANTIC_SHA256,
    COMBAT_POLICY,
    CombatExecutionAuthorization,
    load_combat_execution_authorization,
)
from perfect_assassin.execution.movement_runtime_arm import (
    SESSION_AUTHORIZATION_ID,
    SESSION_AUTHORIZATION_SEMANTIC_SHA256,
)


MAX_RECORD_BYTES = 2 * 1024 * 1024
# The runtime arm is issued before live perception initialization and exact
# target acquisition.  Reserve 20 bounded seconds for that startup, then the
# policy's complete 55-second encounter.  The encounter itself remains capped
# independently; this lease does not authorize additional combat time.
MAX_ARM_LIFETIME_SECONDS = 75


class CombatRuntimeArmError(ValueError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CombatRuntimeArmError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse(name: str, raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_RECORD_BYTES:
        raise CombatRuntimeArmError(f"{name} must be bounded exact bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CombatRuntimeArmError(f"{name} must not contain a BOM")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CombatRuntimeArmError(f"{name} contains non-finite {token}")
            ),
        )
    except CombatRuntimeArmError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise CombatRuntimeArmError(f"{name} is not strict JSON") from error
    if type(value) is not dict:
        raise CombatRuntimeArmError(f"{name} root must be an object")
    return value


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _time(name: str, value: Any, *, canonical_z: bool = False) -> datetime:
    if type(value) is not str or (canonical_z and not value.endswith("Z")):
        raise CombatRuntimeArmError(
            f"{name} must be a canonical timestamp"
            if canonical_z
            else f"{name} must be an offset-aware timestamp"
        )
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CombatRuntimeArmError(f"{name} is invalid") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise CombatRuntimeArmError(f"{name} must carry a UTC offset")
    return result.astimezone(timezone.utc)


def _now(now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise CombatRuntimeArmError("now_utc must be timezone-aware")
    return now_utc.astimezone(timezone.utc)


def _session_semantic_sha256(record: dict[str, Any]) -> str:
    projection = dict(record)
    approval = projection.get("approval")
    if type(approval) is not dict:
        raise CombatRuntimeArmError("session authorization approval is missing")
    stable = dict(approval)
    for field in (
        "recorded_at",
        "expires_at",
        "renews_authorization_sha256",
        "renewal_scope",
    ):
        stable.pop(field, None)
    projection["approval"] = stable
    try:
        canonical = json.dumps(
            projection,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise CombatRuntimeArmError("session authorization is not canonicalizable") from error
    return _sha256(canonical)


def _session_expiry(record: dict[str, Any]) -> tuple[datetime, datetime]:
    approval = record["approval"]
    recorded = _time(
        "session approval.recorded_at",
        approval["recorded_at"],
        canonical_z=True,
    )
    max_minutes = approval["max_session_minutes"]
    if type(max_minutes) is not int or not 1 <= max_minutes <= 60:
        raise CombatRuntimeArmError("session approval max lifetime is invalid")
    bounded = recorded + timedelta(minutes=max_minutes)
    configured = approval.get("expires_at")
    expires = (
        bounded
        if configured is None
        else _time("session approval.expires_at", configured, canonical_z=True)
    )
    if expires > bounded:
        raise CombatRuntimeArmError("session approval exceeds its maximum lifetime")
    return recorded, expires


@dataclass(frozen=True, slots=True)
class CombatRuntimeArm:
    arm_nonce: str
    authorization_sha256: str
    session_authorization_sha256: str
    session_receipt_sha256: str
    realm_revalidation_sha256: str
    pid: int
    hwnd: str
    process_creation_filetime_utc: str
    windows_session_id: int
    window_title: str
    window_class: str
    executable_path: str
    executable_sha256: str
    actor_id: str
    actor_instance_id: str
    client_build: str
    build_signature: str
    clock_id: str
    issued_at_monotonic_ms: float
    expires_at_monotonic_ms: float
    policy: dict[str, Any]


def _validate_inputs(
    *,
    authorization_raw: bytes,
    authorization_schema_path: Path,
    session_authorization_raw: bytes,
    session_receipt_raw: bytes,
    session_receipt_schema_path: Path,
    realm_revalidation_raw: bytes,
    realm_revalidation_schema_path: Path,
    now_utc: datetime,
) -> tuple[
    CombatExecutionAuthorization,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    datetime,
]:
    current = _now(now_utc)
    profile = load_combat_execution_authorization(
        authorization_raw,
        schema_path=authorization_schema_path,
        now_utc=current,
    )
    session = _parse("session authorization", session_authorization_raw)
    receipt = _parse("session receipt", session_receipt_raw)
    revalidation = _parse("realm revalidation", realm_revalidation_raw)
    try:
        ContractValidator(authorization_schema_path).validate(session)
        ContractValidator(session_receipt_schema_path).validate(receipt)
        ContractValidator(realm_revalidation_schema_path).validate(revalidation)
    except ContractValidationError as error:
        raise CombatRuntimeArmError("combat arm evidence failed schema validation") from error
    session_recorded, session_expires = _session_expiry(session)
    expected_session_caps = {
        "SCREEN_CAPTURE_READ_ONLY",
        "VISIBLE_COORDINATE_HUD_READ_ONLY",
        "LAB_OPERATOR_FIXED_UI",
    }
    if (
        session.get("authorization_id") != SESSION_AUTHORIZATION_ID
        or session.get("permitted_modes") != []
        or set(session.get("permitted_capabilities", ())) != expected_session_caps
        or _session_semantic_sha256(session) != SESSION_AUTHORIZATION_SEMANTIC_SHA256
        or session_recorded > current
        or session_expires <= current
    ):
        raise CombatRuntimeArmError("session authorization is not exact and active")
    receipt_expires = _time("session receipt expires_at", receipt["expires_at"])
    receipt_created = _time("session receipt created_at", receipt["created_at"])
    session_auth_sha = _sha256(session_authorization_raw)
    receipt_sha = _sha256(session_receipt_raw)
    authorization = profile.record
    actor = authorization["actor_binding"]
    identity_pairs = (
        (receipt["pid"], revalidation["pid"]),
        (receipt["hwnd"], revalidation["hwnd"]),
        (receipt["process_created_at_utc"], revalidation["process_created_at_utc"]),
        (receipt["process_creation_filetime_utc"], revalidation["process_creation_filetime_utc"]),
        (receipt["windows_session_id"], revalidation["windows_session_id"]),
        (receipt["executable_path"], revalidation["executable_path"]),
        (receipt["executable_sha256"], revalidation["executable_sha256"]),
        (receipt["expected_realm_fingerprint"], revalidation["expected_realm_fingerprint"]),
        (receipt["realm_routing_sha256"], revalidation["realm_routing_sha256"]),
        (receipt["realmlist_sha256"], revalidation["realmlist_sha256"]),
    )
    if (
        receipt.get("execution_authority") is not False
        or receipt.get("authorization_sha256") != session_auth_sha
        or receipt.get("authorization_semantic_sha256") != SESSION_AUTHORIZATION_SEMANTIC_SHA256
        or receipt.get("actor_binding", {}).get("actor_id") != actor["actor_id"]
        or receipt.get("actor_binding", {}).get("instance_id") != actor["instance_id"]
        or receipt_expires <= current
        or revalidation.get("authorization_id") != COMBAT_EXECUTION_AUTHORIZATION_ID
        or revalidation.get("authorization_sha256") != profile.raw_sha256
        or revalidation.get("session_receipt_nonce") != receipt["receipt_nonce"]
        or revalidation.get("session_receipt_sha256") != receipt_sha
        or revalidation.get("actor_id") != actor["actor_id"]
        or revalidation.get("actor_instance_id") != actor["instance_id"]
        or any(left != right for left, right in identity_pairs)
        or revalidation.get("realm_routing_sha256")
        != authorization["realm_match"]["expected_routing_sha256"]
        or revalidation.get("realmlist_sha256")
        != authorization["realm_match"]["realmlist_sha256"]
    ):
        raise CombatRuntimeArmError("combat arm evidence identity does not bind exactly")
    revalidated = _time(
        "realm revalidation observed_at",
        revalidation["observed_at"],
        canonical_z=True,
    )
    revalidation_expires = _time(
        "realm revalidation expires_at",
        revalidation["expires_at"],
        canonical_z=True,
    )
    if not (
        receipt_created <= profile.recorded_at <= revalidated <= current
        and current < revalidation_expires <= profile.expires_at
        and revalidation_expires <= receipt_expires
    ):
        raise CombatRuntimeArmError("combat arm evidence causality is invalid")
    final_expiry = min(
        current + timedelta(seconds=MAX_ARM_LIFETIME_SECONDS),
        profile.expires_at,
        session_expires,
        receipt_expires,
        revalidation_expires,
    )
    if final_expiry <= current + timedelta(milliseconds=250):
        raise CombatRuntimeArmError("combat arm has insufficient remaining time")
    return profile, session, receipt, revalidation, final_expiry


def issue_combat_runtime_arm_snapshot(
    *,
    authorization_raw: bytes,
    authorization_schema_path: Path,
    session_authorization_raw: bytes,
    session_receipt_raw: bytes,
    session_receipt_schema_path: Path,
    realm_revalidation_raw: bytes,
    realm_revalidation_schema_path: Path,
    arm_schema_path: Path,
    now_utc: datetime,
    now_monotonic_ms: float,
    clock_id: str,
    acknowledge_controlled_combat: bool,
) -> bytes:
    if acknowledge_controlled_combat is not True:
        raise CombatRuntimeArmError("controlled combat arm acknowledgement is required")
    if (
        isinstance(now_monotonic_ms, bool)
        or not isinstance(now_monotonic_ms, (int, float))
        or not isfinite(now_monotonic_ms)
        or now_monotonic_ms < 0
    ):
        raise CombatRuntimeArmError("combat arm monotonic time is invalid")
    current = _now(now_utc)
    profile, _session, receipt, revalidation, final_expiry = _validate_inputs(
        authorization_raw=authorization_raw,
        authorization_schema_path=authorization_schema_path,
        session_authorization_raw=session_authorization_raw,
        session_receipt_raw=session_receipt_raw,
        session_receipt_schema_path=session_receipt_schema_path,
        realm_revalidation_raw=realm_revalidation_raw,
        realm_revalidation_schema_path=realm_revalidation_schema_path,
        now_utc=current,
    )
    delta_ms = (final_expiry - current).total_seconds() * 1000.0
    record = {
        "record_type": "combat_runtime_arm",
        "schema_version": "0.1",
        "arm_nonce": str(uuid4()),
        "authorization_id": COMBAT_EXECUTION_AUTHORIZATION_ID,
        "authorization_sha256": profile.raw_sha256,
        "authorization_semantic_sha256": COMBAT_EXECUTION_SEMANTIC_SHA256,
        "session_authorization_sha256": _sha256(session_authorization_raw),
        "session_receipt_nonce": receipt["receipt_nonce"],
        "session_receipt_sha256": _sha256(session_receipt_raw),
        "realm_revalidation_nonce": revalidation["revalidation_nonce"],
        "realm_revalidation_sha256": _sha256(realm_revalidation_raw),
        "target_profile": "tbc_243_lab",
        "actor_id": profile.record["actor_binding"]["actor_id"],
        "actor_instance_id": profile.record["actor_binding"]["instance_id"],
        "pid": receipt["pid"],
        "hwnd": receipt["hwnd"],
        "process_created_at_utc": receipt["process_created_at_utc"],
        "process_creation_filetime_utc": receipt["process_creation_filetime_utc"],
        "windows_session_id": receipt["windows_session_id"],
        "window_title": receipt["window_title"],
        "window_class": receipt["window_class"],
        "client_build": receipt["client_build"],
        "build_signature": receipt["build_signature"],
        "executable_path": receipt["executable_path"],
        "executable_sha256": receipt["executable_sha256"],
        "expected_realm_fingerprint": receipt["expected_realm_fingerprint"],
        "realm_routing_sha256": receipt["realm_routing_sha256"],
        "realmlist_sha256": receipt["realmlist_sha256"],
        "policy": dict(COMBAT_POLICY),
        "clock_id": clock_id,
        "issued_at_monotonic_ms": float(now_monotonic_ms),
        "expires_at_monotonic_ms": float(now_monotonic_ms) + delta_ms,
        "issued_at": current.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "expires_at": final_expiry.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "active": True,
        "scope": "lab_controlled_combat",
        "execution_authority": True,
    }
    try:
        ContractValidator(arm_schema_path).validate(record)
    except ContractValidationError as error:
        raise CombatRuntimeArmError("issued combat runtime arm is invalid") from error
    return json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_combat_runtime_arm(
    arm_raw: bytes,
    *,
    arm_schema_path: Path,
    authorization_raw: bytes,
    authorization_schema_path: Path,
    session_authorization_raw: bytes,
    session_receipt_raw: bytes,
    session_receipt_schema_path: Path,
    realm_revalidation_raw: bytes,
    realm_revalidation_schema_path: Path,
    now_utc: datetime,
    now_monotonic_ms: float,
) -> CombatRuntimeArm:
    arm = _parse("combat runtime arm", arm_raw)
    try:
        ContractValidator(arm_schema_path).validate(arm)
    except ContractValidationError as error:
        raise CombatRuntimeArmError("combat runtime arm schema validation failed") from error
    profile, _session, receipt, revalidation, _ = _validate_inputs(
        authorization_raw=authorization_raw,
        authorization_schema_path=authorization_schema_path,
        session_authorization_raw=session_authorization_raw,
        session_receipt_raw=session_receipt_raw,
        session_receipt_schema_path=session_receipt_schema_path,
        realm_revalidation_raw=realm_revalidation_raw,
        realm_revalidation_schema_path=realm_revalidation_schema_path,
        now_utc=now_utc,
    )
    expected = {
        "authorization_sha256": profile.raw_sha256,
        "authorization_semantic_sha256": profile.semantic_sha256,
        "session_authorization_sha256": _sha256(session_authorization_raw),
        "session_receipt_nonce": receipt["receipt_nonce"],
        "session_receipt_sha256": _sha256(session_receipt_raw),
        "realm_revalidation_nonce": revalidation["revalidation_nonce"],
        "realm_revalidation_sha256": _sha256(realm_revalidation_raw),
        "pid": receipt["pid"],
        "hwnd": receipt["hwnd"],
        "process_creation_filetime_utc": receipt["process_creation_filetime_utc"],
        "executable_path": receipt["executable_path"],
        "executable_sha256": receipt["executable_sha256"],
        "actor_id": profile.record["actor_binding"]["actor_id"],
        "actor_instance_id": profile.record["actor_binding"]["instance_id"],
    }
    if any(arm.get(key) != value for key, value in expected.items()):
        raise CombatRuntimeArmError("combat runtime arm exact binding diverges")
    if arm.get("policy") != COMBAT_POLICY:
        raise CombatRuntimeArmError("combat runtime arm policy diverges")
    if (
        arm.get("clock_id") != "clock:windows:monotonic"
        or not isfinite(now_monotonic_ms)
        or now_monotonic_ms < arm["issued_at_monotonic_ms"]
        or now_monotonic_ms >= arm["expires_at_monotonic_ms"]
    ):
        raise CombatRuntimeArmError("combat runtime arm monotonic window is inactive")
    return CombatRuntimeArm(
        arm_nonce=arm["arm_nonce"],
        authorization_sha256=arm["authorization_sha256"],
        session_authorization_sha256=arm["session_authorization_sha256"],
        session_receipt_sha256=arm["session_receipt_sha256"],
        realm_revalidation_sha256=arm["realm_revalidation_sha256"],
        pid=arm["pid"],
        hwnd=arm["hwnd"],
        process_creation_filetime_utc=arm["process_creation_filetime_utc"],
        windows_session_id=arm["windows_session_id"],
        window_title=arm["window_title"],
        window_class=arm["window_class"],
        executable_path=arm["executable_path"],
        executable_sha256=arm["executable_sha256"],
        actor_id=arm["actor_id"],
        actor_instance_id=arm["actor_instance_id"],
        client_build=arm["client_build"],
        build_signature=arm["build_signature"],
        clock_id=arm["clock_id"],
        issued_at_monotonic_ms=arm["issued_at_monotonic_ms"],
        expires_at_monotonic_ms=arm["expires_at_monotonic_ms"],
        policy=dict(arm["policy"]),
    )
