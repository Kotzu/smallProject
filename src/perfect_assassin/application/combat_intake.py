from __future__ import annotations

import hashlib
import json
from typing import Any

from perfect_assassin.adapter.combat_hud import validate_valid_observation_semantics
from perfect_assassin.adapter.target_bearing import (
    validate_selected_target_bearing_semantics,
)
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.domain.combat import (
    TARGET_BEARING_CENTER_TOLERANCE,
    CombatActionState,
    CombatObservationState,
    CombatTargetState,
    TargetBearingState,
)


def decode_combat_observation(
    record: dict[str, Any],
    *,
    validator: ContractValidator,
) -> CombatObservationState:
    """Cross the adapter boundary only after schema and packet semantics agree."""

    validator.validate(record)
    packet = validate_valid_observation_semantics(record)
    canonical = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    observation_sha256 = hashlib.sha256(canonical).hexdigest().upper()
    actor = record["actor_binding"]
    target_record = record["target"]
    target = None
    if target_record is not None:
        target = CombatTargetState(
            identity_crc16=target_record["identity_crc16"],
            hostile=target_record["hostile"],
            dead=target_record["dead"],
            is_player=target_record["is_player"],
            health_pct=target_record["health_pct"],
            health_current=target_record["health_current"],
            health_max=target_record["health_max"],
            level=target_record["level"],
            reaction=target_record["reaction"],
            interact_x_normalized=target_record["interact_x_normalized"],
            interact_y_normalized=target_record["interact_y_normalized"],
        )

    def action(name: str) -> CombatActionState:
        value = record["actions"][name]
        return CombatActionState(
            exact_binding=value["exact_binding"],
            usable=value["usable"],
            current=value["current"],
            in_range=value["in_range"],
            cooldown_ready=value["cooldown_ready"],
            cooldown_remaining_ms=value["cooldown_remaining_ms"],
        )

    return CombatObservationState(
        observation_id=record["observation_id"],
        frame_id=record["frame_id"],
        observation_sha256=observation_sha256,
        authorization_sha256=record["authorization_sha256"],
        actor_id=actor["actor_id"],
        actor_instance_id=actor["instance_id"],
        target_profile=record["target_profile"],
        sequence=packet.sequence,
        observed_monotonic_s=record["timing"]["observed_monotonic_s"],
        expires_monotonic_s=record["timing"]["expires_monotonic_s"],
        confidence=record["confidence"],
        provenance_scope=record["provenance"]["scope"],
        player_alive=record["player"]["alive"],
        player_health_pct=record["player"]["health_pct"],
        player_energy=record["player"]["energy"],
        player_attack_power=record["player"]["attack_power"],
        player_level=record["player"]["level"],
        in_combat=record["combat"]["in_combat"],
        combo_points=record["combat"]["combo_points"],
        target=target,
        attack=action("slot1_attack"),
        sinister_strike=action("slot2_sinister_strike"),
        eviscerate=action("slot3_eviscerate"),
        loot_event_sequence=record["combat"]["loot_event_sequence"],
        visible_attackable_candidate_count=record["combat"][
            "visible_attackable_candidate_count"
        ],
        acquisition_x_normalized=record["combat"]["acquisition_x_normalized"],
        acquisition_y_normalized=record["combat"]["acquisition_y_normalized"],
    )


def decode_target_bearing_observation(
    record: dict[str, Any],
    *,
    validator: ContractValidator,
) -> TargetBearingState:
    validator.validate(record)
    validate_selected_target_bearing_semantics(record)
    canonical = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    actor = record["actor_binding"]
    timing = record["timing"]
    return TargetBearingState(
        observation_id=record["observation_id"],
        observation_sha256=hashlib.sha256(canonical).hexdigest().upper(),
        frame_id=record["frame_id"],
        combat_observation_id=record["combat_observation_id"],
        combat_observation_sha256=record["combat_observation_sha256"],
        authorization_sha256=record["authorization_sha256"],
        actor_id=actor["actor_id"],
        actor_instance_id=actor["instance_id"],
        target_profile=record["target_profile"],
        target_identity_crc16=record["target_identity_crc16"],
        tracking_state=record["tracking_state"],
        direction=record["direction"],
        offset_x_normalized=record["offset_x_normalized"],
        center_y_normalized=(
            None
            if record["center_y_px"] is None
            else record["center_y_px"] / record["frame_height_px"]
        ),
        observed_monotonic_s=timing["observed_monotonic_s"],
        expires_monotonic_s=timing["expires_monotonic_s"],
        confidence=record["confidence"],
        provenance_scope=record["provenance"]["scope"],
    )


def decode_crc_target_bearing(
    record: dict[str, Any],
    observation: CombatObservationState,
    *,
    validator: ContractValidator,
) -> TargetBearingState:
    """Derive target bearing only from the CRC-bound visible addon packet."""

    validator.validate(record)
    validate_valid_observation_semantics(record)
    if record["frame_id"] != observation.frame_id:
        raise ValueError("CRC target bearing frame does not match combat observation")
    target_record = record["target"]
    if target_record is None:
        acquisition = record["combat"]
        tracking_state = acquisition["acquisition_bearing_state"]
        direction = acquisition["acquisition_bearing_direction"]
        offset = acquisition["acquisition_bearing_offset_x_normalized"]
        center_y_normalized = acquisition["acquisition_y_normalized"]
        if acquisition["acquisition_x_normalized"] is not None:
            offset = max(
                -1.0,
                min(1.0, acquisition["acquisition_x_normalized"] * 2.0 - 1.0),
            )
            direction = (
                "LEFT" if offset < -0.12
                else "RIGHT" if offset > 0.12
                else "CENTER"
            )
        target_identity = None
    else:
        tracking_state = target_record["bearing_state"]
        direction = target_record["bearing_direction"]
        offset = target_record["bearing_offset_x_normalized"]
        # Exact selected-frame geometry is the authoritative bearing carried by
        # this same CRC-bound packet. Re-derive the redundant direction label so
        # an older observer addon cannot contradict the canonical domain
        # tolerance at the LEFT/CENTER/RIGHT boundary.
        if tracking_state == "VISIBLE" and offset is not None:
            direction = (
                "LEFT"
                if offset < -TARGET_BEARING_CENTER_TOLERANCE
                else "RIGHT"
                if offset > TARGET_BEARING_CENTER_TOLERANCE
                else "CENTER"
            )
        target_identity = target_record["identity_crc16"]
        center_y_normalized = None
    confidence = 1.0 if tracking_state == "VISIBLE" else 0.0
    bearing_id = f"{record['observation_id']}:crc-bearing"
    material = {
        "origin": "visible_addon_hud_crc",
        "observation_id": bearing_id,
        "frame_id": observation.frame_id,
        "combat_observation_id": observation.observation_id,
        "combat_observation_sha256": observation.observation_sha256,
        "target_identity_crc16": target_identity,
        "tracking_state": tracking_state,
        "direction": direction,
        "offset_x_normalized": offset,
        "center_y_normalized": center_y_normalized,
    }
    canonical = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    expires = min(
        observation.expires_monotonic_s,
        observation.observed_monotonic_s + 0.45,
    )
    return TargetBearingState(
        observation_id=bearing_id,
        observation_sha256=hashlib.sha256(canonical).hexdigest().upper(),
        frame_id=observation.frame_id,
        combat_observation_id=observation.observation_id,
        combat_observation_sha256=observation.observation_sha256,
        authorization_sha256=observation.authorization_sha256,
        actor_id=observation.actor_id,
        actor_instance_id=observation.actor_instance_id,
        target_profile=observation.target_profile,
        target_identity_crc16=target_identity,
        tracking_state=tracking_state,
        direction=direction,
        offset_x_normalized=offset,
        center_y_normalized=center_y_normalized,
        observed_monotonic_s=observation.observed_monotonic_s,
        expires_monotonic_s=expires,
        confidence=confidence,
        provenance_scope=observation.provenance_scope,
    )
