from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator


COMBAT_OBSERVER_AUTHORIZATION_ID = "observation:tbc243-lab:combat-hud-read-only"
COMBAT_OBSERVER_SEMANTIC_SHA256 = (
    "33624D874C0EA1EDDF905A58D3C05FED2D479EA082116DBF4102A5C8F9861C37"
)
MAX_AUTHORIZATION_BYTES = 2 * 1024 * 1024


class CombatAuthorizationError(ValueError):
    """The combat-observation authorization is not the reviewed LAB profile."""


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CombatAuthorizationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_exact_json(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_AUTHORIZATION_BYTES:
        raise CombatAuthorizationError("authorization must be bounded exact bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CombatAuthorizationError("authorization must not contain a BOM")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CombatAuthorizationError(f"non-finite JSON constant: {token}")
            ),
        )
    except CombatAuthorizationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise CombatAuthorizationError("authorization is not strict UTF-8 JSON") from error
    if type(value) is not dict:
        raise CombatAuthorizationError("authorization root must be an object")
    return value


def _semantic_sha256(record: dict[str, Any]) -> str:
    projection = dict(record)
    approval = projection.get("approval")
    if type(approval) is not dict:
        raise CombatAuthorizationError("authorization approval is missing")
    stable_approval = dict(approval)
    for field in (
        "recorded_at",
        "expires_at",
        "renews_authorization_sha256",
        "renewal_scope",
    ):
        stable_approval.pop(field, None)
    projection["approval"] = stable_approval
    try:
        canonical = json.dumps(
            projection,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise CombatAuthorizationError("authorization is not canonicalizable") from error
    return hashlib.sha256(canonical).hexdigest().upper()


def issue_combat_observer_authorization_snapshot(
    template_raw: bytes,
    *,
    schema_path: Path,
    now_utc: datetime,
) -> bytes:
    record = _parse_exact_json(template_raw)
    try:
        ContractValidator(schema_path).validate(record)
    except ContractValidationError as error:
        raise CombatAuthorizationError(
            "combat observer template does not satisfy its schema"
        ) from error
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise CombatAuthorizationError("now_utc must be timezone-aware")
    current = now_utc.astimezone(timezone.utc)
    if (
        record.get("record_type") != "execution_target_authorization"
        or record.get("schema_version") != "2.0"
        or record.get("authorization_id") != COMBAT_OBSERVER_AUTHORIZATION_ID
        or record.get("target_profile") != "tbc_243_lab"
        or record.get("environment_scope") != "emulator_local"
        or record.get("status") != "approved_bounded"
        or record.get("permitted_modes") != []
        or set(record.get("permitted_capabilities", ()))
        != {"SCREEN_CAPTURE_READ_ONLY", "VISIBLE_COMBAT_HUD_READ_ONLY"}
        or record.get("runtime_arm_required") is not True
        or _semantic_sha256(record) != COMBAT_OBSERVER_SEMANTIC_SHA256
    ):
        raise CombatAuthorizationError(
            "authorization is not the exact read-only combat HUD profile"
        )
    approval = dict(record["approval"])
    max_minutes = approval.get("max_session_minutes")
    if type(max_minutes) is not int or not 1 <= max_minutes <= 60:
        raise CombatAuthorizationError("approval.max_session_minutes is invalid")
    approval["recorded_at"] = current.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    approval["expires_at"] = (
        current + timedelta(minutes=max_minutes)
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")
    approval.pop("renews_authorization_sha256", None)
    approval.pop("renewal_scope", None)
    record["approval"] = approval
    raw = (
        json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2)
        + "\n"
    ).encode("utf-8")
    issued = _parse_exact_json(raw)
    try:
        ContractValidator(schema_path).validate(issued)
    except ContractValidationError as error:
        raise CombatAuthorizationError(
            "issued combat authorization does not satisfy its schema"
        ) from error
    if _semantic_sha256(issued) != COMBAT_OBSERVER_SEMANTIC_SHA256:
        raise CombatAuthorizationError("issued authorization changed semantic scope")
    return raw
