from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator


COMBAT_EXECUTION_AUTHORIZATION_ID = "execution:tbc243-lab:combat-f4a-bounded"
COMBAT_EXECUTION_CAPABILITY = "COMBAT_EXECUTION"
COMBAT_MODE = "COMBAT_ONLY"
COMBAT_ACKNOWLEDGEMENT_REF = "operator_ack:pa024f4a:controlled_lab_combat"
BASE_TEMPLATE_SHA256 = "B8F6DBEF10247F81DCE3863F959AE0B92D0051211ABD42A8C461F55A2763987F"
COMBAT_EXECUTION_SEMANTIC_SHA256 = (
    "96BEDD9279083BD3D3407DFCCF85FC27B23A192EC33BCD071278026CEFECBBAB"
)
MAX_RECORD_BYTES = 2 * 1024 * 1024
ALLOWED_COMBAT_CONTROLS = (
    "TARGET_VISIBLE_HOSTILE",
    "TARGET_NEAREST_HOSTILE",
    "TARGET_EXACT_NAME",
    "TARGET_LAST_HOSTILE",
    "INTERACT_TARGET",
    "ACTION_SLOT_1",
    "ACTION_SLOT_2",
    "ACTION_SLOT_3",
    "MOVE_FORWARD",
    "STRAFE_LEFT",
    "STRAFE_RIGHT",
    "TURN_LEFT",
    "TURN_RIGHT",
)
COMBAT_POLICY = {
    "allowed_controls": list(ALLOWED_COMBAT_CONTROLS),
    "max_actions": 64,
    "max_encounter_seconds": 90,
    "max_acquisition_seconds": 25,
    "max_combat_seconds": 60,
    "max_recovery_seconds": 5,
    "max_approach_pulses": 10,
    "approach_hold_duration_ms": 250,
    "orbit_hold_duration_ms": 90,
    "max_turn_pulses": 12,
    "max_facing_turn_pulses": 24,
    "search_turn_hold_duration_ms": 200,
    "search_turn_mouse_delta_x": 24,
    "turn_near_hold_duration_ms": 25,
    "turn_near_mouse_delta_x": 4,
    "turn_medium_hold_duration_ms": 35,
    "turn_medium_mouse_delta_x": 14,
    "turn_far_hold_duration_ms": 50,
    "turn_far_mouse_delta_x": 28,
    "turn_medium_offset_threshold": 0.25,
    "turn_far_offset_threshold": 0.60,
    "turn_execution_slack_ms": 150,
    "action_key_hold_ms": 25,
    "max_target_level_delta": 1,
    "retreat_health_pct": 25,
    "manual_takeover_required": True,
    "release_all_required": True,
    "player_targets_authorized": False,
    "economy_authorized": False,
}


class CombatExecutionAuthorizationError(ValueError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CombatExecutionAuthorizationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_RECORD_BYTES:
        raise CombatExecutionAuthorizationError("authorization must be bounded exact bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CombatExecutionAuthorizationError("authorization must not contain a BOM")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CombatExecutionAuthorizationError(f"non-finite constant: {token}")
            ),
        )
    except CombatExecutionAuthorizationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise CombatExecutionAuthorizationError("authorization is not strict JSON") from error
    if type(value) is not dict:
        raise CombatExecutionAuthorizationError("authorization root must be an object")
    return value


def _canonical_sha256(value: dict[str, Any]) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise CombatExecutionAuthorizationError("authorization is not canonicalizable") from error
    return hashlib.sha256(raw).hexdigest().upper()


def _semantic_sha256(record: dict[str, Any]) -> str:
    projection = dict(record)
    approval = projection.get("approval")
    if type(approval) is not dict:
        raise CombatExecutionAuthorizationError("authorization approval is missing")
    stable = dict(approval)
    for key in ("recorded_at", "expires_at"):
        stable.pop(key, None)
    evidence_refs = stable.get("evidence_refs")
    if type(evidence_refs) is not list or len(evidence_refs) != 3:
        raise CombatExecutionAuthorizationError("combat approval evidence is invalid")
    stable["evidence_refs"] = evidence_refs[:2]
    projection["approval"] = stable
    return _canonical_sha256(projection)


def _require_aware_utc(now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise CombatExecutionAuthorizationError("now_utc must be timezone-aware")
    return now_utc.astimezone(timezone.utc)


def _exact_output_record(
    base: dict[str, Any],
    *,
    now_utc: datetime,
    evidence_ref: str,
) -> dict[str, Any]:
    if not isinstance(evidence_ref, str) or not 1 <= len(evidence_ref) <= 256:
        raise CombatExecutionAuthorizationError("evidence_ref is invalid")
    actor = dict(base["actor_binding"])
    assurance = dict(actor["binding_assurance"])
    assurance["evidence_refs"] = [
        "authorization:execution:tbc243-lab:combat-f4a-bounded:actor-expected"
    ]
    actor["binding_assurance"] = assurance
    current = _require_aware_utc(now_utc)
    record = dict(base)
    record["authorization_id"] = COMBAT_EXECUTION_AUTHORIZATION_ID
    record["actor_binding"] = actor
    record["permitted_modes"] = [COMBAT_MODE]
    record["permitted_capabilities"] = [
        "SCREEN_CAPTURE_READ_ONLY",
        "VISIBLE_COMBAT_HUD_READ_ONLY",
        COMBAT_EXECUTION_CAPABILITY,
    ]
    record["restrictions"] = [
        "single_local_lab_encounter",
        "hostile_npc_only",
        "no_player_targets",
        "no_gathering_or_economy_loops",
        "manual_takeover_required",
        "no_memory_or_kernel_access",
    ]
    record["combat_policy"] = dict(COMBAT_POLICY)
    record["approval"] = {
        "granted_by": "operator",
        "evidence_refs": [
            "adr:0024",
            COMBAT_ACKNOWLEDGEMENT_REF,
            evidence_ref,
        ],
        "recorded_at": current.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "expires_at": (current + timedelta(minutes=2)).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
        "max_session_minutes": 2,
    }
    record["runtime_arm_required"] = True
    return record


@dataclass(frozen=True, slots=True)
class CombatExecutionAuthorization:
    raw_sha256: str
    semantic_sha256: str
    recorded_at: datetime
    expires_at: datetime
    record: dict[str, Any]


def issue_combat_execution_authorization_snapshot(
    base_raw: bytes,
    *,
    schema_path: Path,
    now_utc: datetime,
    evidence_ref: str,
    acknowledge_controlled_combat: bool,
) -> bytes:
    if acknowledge_controlled_combat is not True:
        raise CombatExecutionAuthorizationError("controlled combat acknowledgement is required")
    if hashlib.sha256(base_raw).hexdigest().upper() != BASE_TEMPLATE_SHA256:
        raise CombatExecutionAuthorizationError("combat observer base template hash diverges")
    base = _parse(base_raw)
    try:
        ContractValidator(schema_path).validate(base)
    except ContractValidationError as error:
        raise CombatExecutionAuthorizationError("base template schema validation failed") from error
    record = _exact_output_record(base, now_utc=now_utc, evidence_ref=evidence_ref)
    try:
        ContractValidator(schema_path).validate(record)
    except ContractValidationError as error:
        raise CombatExecutionAuthorizationError("issued combat authorization is invalid") from error
    raw = (json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    return raw


def load_combat_execution_authorization(
    raw: bytes,
    *,
    schema_path: Path,
    now_utc: datetime,
) -> CombatExecutionAuthorization:
    record = _parse(raw)
    try:
        ContractValidator(schema_path).validate(record)
    except ContractValidationError as error:
        raise CombatExecutionAuthorizationError("combat authorization schema validation failed") from error
    current = _require_aware_utc(now_utc)
    try:
        recorded = datetime.fromisoformat(record["approval"]["recorded_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(record["approval"]["expires_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as error:
        raise CombatExecutionAuthorizationError("combat approval timestamps are invalid") from error
    semantic = _semantic_sha256(record)
    if (
        record.get("authorization_id") != COMBAT_EXECUTION_AUTHORIZATION_ID
        or record.get("permitted_modes") != [COMBAT_MODE]
        or tuple(record.get("combat_policy", {}).get("allowed_controls", ()))
        != ALLOWED_COMBAT_CONTROLS
        or record.get("combat_policy") != COMBAT_POLICY
        or semantic != COMBAT_EXECUTION_SEMANTIC_SHA256
        or recorded > current
        or expires <= current
        or expires > recorded + timedelta(minutes=2)
    ):
        raise CombatExecutionAuthorizationError("combat authorization is not the exact active profile")
    return CombatExecutionAuthorization(
        raw_sha256=hashlib.sha256(raw).hexdigest().upper(),
        semantic_sha256=semantic,
        recorded_at=recorded,
        expires_at=expires,
        record=record,
    )
