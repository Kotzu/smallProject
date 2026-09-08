from __future__ import annotations

from dataclasses import dataclass
from math import floor, isclose, isfinite
from typing import Any, Mapping

from perfect_assassin.adapter.coordinate_hud import crc16_ccitt_false


MAGIC = 0xC6
PROTOCOL_VERSION = 6
PACKET_BYTES = 28
PAYLOAD_BITS = PACKET_BYTES * 8
MAX_ENERGY = 100
MAX_COMBO_POINTS = 5
COOLDOWN_TICK_MS = 50
VALID_OBSERVATION_FRESHNESS_MS = 600.0
TIMING_TOLERANCE_S = 1e-6
TARGET_BEARING_CODES = {
    0: ("LOST", None, None),
    1: ("AMBIGUOUS", None, None),
    2: ("VISIBLE", "LEFT", -0.75),
    3: ("VISIBLE", "LEFT", -0.35),
    4: ("VISIBLE", "CENTER", 0.0),
    5: ("VISIBLE", "RIGHT", 0.35),
    6: ("VISIBLE", "RIGHT", 0.75),
    # Selected nameplate below the frontal corridor: bounded rightward
    # turn plus camera-pitch lift. Code 7 was previously reserved.
    7: ("VISIBLE", "RIGHT", 1.0),
}


class CombatHudProtocolError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CombatHudPacket:
    sequence: int
    player_alive: bool
    in_combat: bool
    target_exists: bool
    target_hostile: bool
    target_dead: bool
    target_player: bool
    slot1_attack_exact: bool
    slot2_sinister_strike_exact: bool
    slot3_eviscerate_exact: bool
    target_bearing_code: int
    target_frame_x_normalized: float | None
    target_frame_y_normalized: float | None
    player_health_pct: float
    player_energy: int
    player_attack_power: int
    target_health_pct: float | None
    target_health_current: int | None
    target_health_max: int | None
    combo_points: int
    loot_event_sequence: int
    player_level: int
    target_level: int | None
    target_reaction: int | None
    slot1_usable: bool
    slot1_current: bool
    slot1_in_range: bool | None
    slot2_usable: bool
    slot2_in_range: bool | None
    slot2_cooldown_ready: bool
    slot2_cooldown_remaining_ms: int
    slot3_usable: bool
    slot3_in_range: bool | None
    slot3_cooldown_ready: bool
    target_identity_crc16: int | None
    target_interact_x_normalized: float | None
    target_interact_y_normalized: float | None
    visible_attackable_candidate_count: int
    acquisition_x_normalized: float | None
    acquisition_y_normalized: float | None


def _exact_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise CombatHudProtocolError(f"{label} must be a boolean")
    return value


def _bounded_int(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CombatHudProtocolError(
            f"{label} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _quantize_percent(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CombatHudProtocolError(f"{label} must be numeric")
    numeric = float(value)
    if not 0.0 <= numeric <= 100.0:
        raise CombatHudProtocolError(f"{label} must be in [0, 100]")
    return floor(numeric * 255.0 / 100.0 + 0.5)


def _decode_percent(value: int) -> float:
    return value * 100.0 / 255.0


def target_identity_crc16(*, guid: str | None, name: str | None) -> int:
    if guid is not None and not isinstance(guid, str):
        raise CombatHudProtocolError("target guid must be a string or null")
    if name is not None and not isinstance(name, str):
        raise CombatHudProtocolError("target name must be a string or null")
    if guid is None and name is None:
        return 0
    encoded = f"{guid or ''}\x1f{name or ''}".encode("utf-8")
    if len(encoded) > 512:
        raise CombatHudProtocolError("target identity exceeds the byte budget")
    return crc16_ccitt_false(encoded)


def encode_packet(
    *,
    sequence: int,
    player_alive: bool,
    in_combat: bool,
    target_exists: bool,
    target_hostile: bool,
    target_dead: bool,
    target_player: bool,
    slot1_attack_exact: bool,
    slot2_sinister_strike_exact: bool,
    slot3_eviscerate_exact: bool,
    player_health_pct: float,
    player_energy: int,
    player_attack_power: int,
    target_health_pct: float | None,
    target_health_current: int | None,
    target_health_max: int | None,
    combo_points: int,
    loot_event_sequence: int = 0,
    player_level: int,
    target_level: int | None,
    target_reaction: int | None,
    slot1_usable: bool,
    slot1_current: bool,
    slot1_in_range: bool | None,
    slot2_usable: bool,
    slot2_in_range: bool | None,
    slot2_cooldown_ready: bool,
    slot2_cooldown_remaining_ms: int,
    slot3_usable: bool,
    slot3_in_range: bool | None,
    slot3_cooldown_ready: bool,
    target_identity_crc16: int | None,
    target_bearing_code: int,
    target_frame_x_normalized: float | None = None,
    target_frame_y_normalized: float | None = None,
    target_interact_x_normalized: float | None = None,
    target_interact_y_normalized: float | None = None,
    visible_attackable_candidate_count: int = 0,
    acquisition_x_normalized: float | None = None,
    acquisition_y_normalized: float | None = None,
) -> bytes:
    sequence = _bounded_int(sequence, "sequence", 0, 2**63 - 1)
    player_alive = _exact_bool(player_alive, "player_alive")
    in_combat = _exact_bool(in_combat, "in_combat")
    target_exists = _exact_bool(target_exists, "target_exists")
    target_hostile = _exact_bool(target_hostile, "target_hostile")
    target_dead = _exact_bool(target_dead, "target_dead")
    target_player = _exact_bool(target_player, "target_player")
    slot1_attack_exact = _exact_bool(slot1_attack_exact, "slot1_attack_exact")
    slot2_sinister_strike_exact = _exact_bool(
        slot2_sinister_strike_exact, "slot2_sinister_strike_exact"
    )
    slot3_eviscerate_exact = _exact_bool(
        slot3_eviscerate_exact, "slot3_eviscerate_exact"
    )
    target_bearing_code = _bounded_int(
        target_bearing_code, "target_bearing_code", 0, 7
    )
    slot1_usable = _exact_bool(slot1_usable, "slot1_usable")
    slot1_current = _exact_bool(slot1_current, "slot1_current")
    slot2_usable = _exact_bool(slot2_usable, "slot2_usable")
    slot2_cooldown_ready = _exact_bool(
        slot2_cooldown_ready, "slot2_cooldown_ready"
    )
    slot3_usable = _exact_bool(slot3_usable, "slot3_usable")
    slot3_cooldown_ready = _exact_bool(
        slot3_cooldown_ready, "slot3_cooldown_ready"
    )
    if slot1_in_range is not None:
        slot1_in_range = _exact_bool(slot1_in_range, "slot1_in_range")
    if slot2_in_range is not None:
        slot2_in_range = _exact_bool(slot2_in_range, "slot2_in_range")
    if slot3_in_range is not None:
        slot3_in_range = _exact_bool(slot3_in_range, "slot3_in_range")

    player_health_quantized = _quantize_percent(
        player_health_pct, "player_health_pct"
    )
    player_energy = _bounded_int(player_energy, "player_energy", 0, MAX_ENERGY)
    player_attack_power = _bounded_int(
        player_attack_power, "player_attack_power", 0, 65_535
    )
    combo_points = _bounded_int(
        combo_points, "combo_points", 0, MAX_COMBO_POINTS
    )
    loot_event_sequence = _bounded_int(
        loot_event_sequence, "loot_event_sequence", 0, 31
    )
    player_level = _bounded_int(player_level, "player_level", 1, 255)
    cooldown_ms = _bounded_int(
        slot2_cooldown_remaining_ms,
        "slot2_cooldown_remaining_ms",
        0,
        255 * COOLDOWN_TICK_MS,
    )
    cooldown_ticks = min(255, floor(cooldown_ms / COOLDOWN_TICK_MS + 0.5))

    if target_exists:
        if (
            visible_attackable_candidate_count != 0
            or acquisition_x_normalized is not None
            or acquisition_y_normalized is not None
        ):
            raise CombatHudProtocolError(
                "selected target cannot also publish acquisition candidates"
            )
        if (
            target_health_pct is None
            or target_health_current is None
            or target_health_max is None
        ):
            raise CombatHudProtocolError("an existing target requires absolute health")
        target_health_current = _bounded_int(
            target_health_current, "target_health_current", 0, 16_777_215
        )
        target_health_max = _bounded_int(
            target_health_max, "target_health_max", 1, 16_777_215
        )
        if target_health_current > target_health_max:
            raise CombatHudProtocolError("target health current exceeds maximum")
        target_health_quantized = _quantize_percent(
            target_health_pct, "target_health_pct"
        )
        expected_health_quantized = floor(
            target_health_current * 255.0 / target_health_max + 0.5
        )
        if target_health_quantized != expected_health_quantized:
            raise CombatHudProtocolError(
                "target health percent diverges from absolute health"
            )
        if target_level is None:
            encoded_target_level = 255
        else:
            encoded_target_level = _bounded_int(
                target_level, "target_level", 1, 254
            )
        if target_reaction is None:
            raise CombatHudProtocolError("an existing target requires reaction")
        target_reaction = _bounded_int(
            target_reaction, "target_reaction", 1, 8
        )
        identity = _bounded_int(
            target_identity_crc16,
            "target_identity_crc16",
            1,
            65535,
        )
        bearing_visible = target_bearing_code in {2, 3, 4, 5, 6, 7}
        if bearing_visible:
            if target_frame_x_normalized is None:
                coarse_offset = TARGET_BEARING_CODES[target_bearing_code][2]
                assert coarse_offset is not None
                target_frame_x_normalized = (coarse_offset + 1.0) / 2.0
            if target_frame_y_normalized is None:
                target_frame_y_normalized = 0.5
            for value, label in (
                (target_frame_x_normalized, "target_frame_x_normalized"),
                (target_frame_y_normalized, "target_frame_y_normalized"),
            ):
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not 0.0 <= float(value) <= 1.0
                ):
                    raise CombatHudProtocolError(f"{label} must be in [0, 1]")
        elif (
            target_frame_x_normalized is not None
            or target_frame_y_normalized is not None
        ):
            raise CombatHudProtocolError(
                "non-visible target cannot publish selected-frame geometry"
            )
    else:
        visible_attackable_candidate_count = _bounded_int(
            visible_attackable_candidate_count,
            "visible_attackable_candidate_count",
            0,
            255,
        )
        if visible_attackable_candidate_count:
            if acquisition_x_normalized is None or acquisition_y_normalized is None:
                raise CombatHudProtocolError(
                    "visible acquisition candidates require screen geometry"
                )
            for value, label in (
                (acquisition_x_normalized, "acquisition_x_normalized"),
                (acquisition_y_normalized, "acquisition_y_normalized"),
            ):
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not 0.0 < float(value) < 1.0
                ):
                    raise CombatHudProtocolError(
                        f"{label} must be inside the client area"
                    )
        elif acquisition_x_normalized is not None or acquisition_y_normalized is not None:
            raise CombatHudProtocolError(
                "absent acquisition candidates cannot publish screen geometry"
            )
        if any((target_hostile, target_dead, target_player)):
            raise CombatHudProtocolError(
                "target-dependent flags require an existing target"
            )
        if (
            target_health_pct is not None
            or target_health_current is not None
            or target_health_max is not None
            or target_level is not None
            or target_reaction is not None
        ):
            raise CombatHudProtocolError(
                "an absent target cannot publish target state"
            )
        if target_identity_crc16 is not None:
            raise CombatHudProtocolError(
                "an absent target cannot publish an identity fingerprint"
            )
        target_health_quantized = 0
        target_health_current = 0
        target_health_max = 0
        encoded_target_level = 0
        target_reaction = 0
        identity = 0
        if (
            target_frame_x_normalized is not None
            or target_frame_y_normalized is not None
        ):
            raise CombatHudProtocolError(
                "absent target cannot publish selected-frame geometry"
            )

    if target_dead and (
        target_health_quantized != 0 or target_health_current != 0
    ):
        raise CombatHudProtocolError("a dead target must have zero health")
    interact_x_byte = 0
    interact_y_byte = 0
    interact_marker = 0
    if target_interact_x_normalized is not None or target_interact_y_normalized is not None:
        if not target_dead or target_interact_x_normalized is None or target_interact_y_normalized is None:
            raise CombatHudProtocolError("corpse interact point requires a dead target")
        for value, label in (
            (target_interact_x_normalized, "target_interact_x_normalized"),
            (target_interact_y_normalized, "target_interact_y_normalized"),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 < float(value) < 1.0:
                raise CombatHudProtocolError(f"{label} must be inside the client area")
        interact_x_byte = floor(float(target_interact_x_normalized) * 255.0 + 0.5)
        interact_y_byte = floor(float(target_interact_y_normalized) * 255.0 + 0.5)
        interact_marker = 0xA5
    if not player_alive and player_health_quantized != 0:
        raise CombatHudProtocolError("a dead player must have zero health")
    if not slot1_attack_exact and (slot1_usable or slot1_current or slot1_in_range is not None):
        raise CombatHudProtocolError("slot 1 state requires an exact Attack binding")
    if not slot2_sinister_strike_exact and (
        slot2_usable
        or slot2_in_range is not None
        or slot2_cooldown_ready
        or cooldown_ticks
    ):
        raise CombatHudProtocolError(
            "slot 2 state requires an exact Sinister Strike binding"
        )
    if slot2_cooldown_ready and cooldown_ticks != 0:
        raise CombatHudProtocolError(
            "a ready Sinister Strike cannot have cooldown remaining"
        )
    if not slot3_eviscerate_exact and (
        slot3_usable or slot3_in_range is not None or slot3_cooldown_ready
    ):
        raise CombatHudProtocolError(
            "slot 3 state requires an exact Eviscerate binding"
        )

    flags = (
        int(player_alive)
        | (int(in_combat) << 1)
        | (int(target_exists) << 2)
        | (int(target_hostile) << 3)
        | (int(target_dead) << 4)
        | (int(target_player) << 5)
        | (int(slot1_attack_exact) << 6)
        | (int(slot2_sinister_strike_exact) << 7)
    )
    action_flags = (
        int(slot1_usable)
        | (int(slot1_current) << 1)
        | (int(slot1_in_range is not None) << 2)
        | (int(slot1_in_range is True) << 3)
        | (int(slot2_usable) << 4)
        | (int(slot2_in_range is not None) << 5)
        | (int(slot2_in_range is True) << 6)
        | (int(slot2_cooldown_ready) << 7)
    )
    slot3_flags = (
        int(slot3_eviscerate_exact)
        | (int(slot3_usable) << 1)
        | (int(slot3_in_range is not None) << 2)
        | (int(slot3_in_range is True) << 3)
        | (int(slot3_cooldown_ready) << 4)
        | (target_bearing_code << 5)
    )
    target_frame_x_byte = (
        0
        if target_frame_x_normalized is None
        else floor(float(target_frame_x_normalized) * 255.0 + 0.5)
    )
    target_frame_y_byte = (
        0
        if target_frame_y_normalized is None
        else floor(float(target_frame_y_normalized) * 255.0 + 0.5)
    )
    body = bytes(
        (
            MAGIC,
            PROTOCOL_VERSION,
            flags,
            sequence & 0xFF,
            player_health_quantized,
            player_energy,
            target_health_quantized,
            combo_points | (loot_event_sequence << 3),
            player_level,
            encoded_target_level,
            target_reaction,
            action_flags,
            cooldown_ticks,
            slot3_flags,
            (identity >> 8) & 0xFF,
            identity & 0xFF,
            interact_x_byte if target_dead else (
                visible_attackable_candidate_count
                if not target_exists
                else (target_health_current >> 16) & 0xFF
            ),
            interact_y_byte if target_dead else (
                floor(float(acquisition_x_normalized) * 255.0 + 0.5)
                if not target_exists and visible_attackable_candidate_count
                else (target_health_current >> 8) & 0xFF
            ),
            interact_marker if target_dead else (
                floor(float(acquisition_y_normalized) * 255.0 + 0.5)
                if not target_exists and visible_attackable_candidate_count
                else target_health_current & 0xFF
            ),
            (target_health_max >> 16) & 0xFF,
            (target_health_max >> 8) & 0xFF,
            target_health_max & 0xFF,
            (player_attack_power >> 8) & 0xFF,
            player_attack_power & 0xFF,
            target_frame_x_byte,
            target_frame_y_byte,
        )
    )
    checksum = crc16_ccitt_false(body)
    return body + checksum.to_bytes(2, "big")


def decode_packet(packet: bytes) -> CombatHudPacket:
    if not isinstance(packet, bytes) or len(packet) != PACKET_BYTES:
        raise CombatHudProtocolError(f"packet must contain {PACKET_BYTES} bytes")
    if packet[0] != MAGIC:
        raise CombatHudProtocolError("magic mismatch")
    if packet[1] != PROTOCOL_VERSION:
        raise CombatHudProtocolError("protocol version mismatch")
    target_bearing_code = packet[13] >> 5
    if target_bearing_code not in TARGET_BEARING_CODES:
        raise CombatHudProtocolError("reserved target bearing code")
    if int.from_bytes(packet[-2:], "big") != crc16_ccitt_false(packet[:-2]):
        raise CombatHudProtocolError("CRC-16 mismatch")

    flags = packet[2]
    action_flags = packet[11]
    target_exists = bool(flags & 0x04)
    target_dead = bool(flags & 0x10)
    player_alive = bool(flags & 0x01)
    slot1_exact = bool(flags & 0x40)
    slot2_exact = bool(flags & 0x80)
    slot3_flags = packet[13]
    slot3_exact = bool(slot3_flags & 0x01)
    slot1_range = bool(action_flags & 0x08) if action_flags & 0x04 else None
    slot2_range = bool(action_flags & 0x40) if action_flags & 0x20 else None
    slot3_range = bool(slot3_flags & 0x08) if slot3_flags & 0x04 else None
    target_identity = int.from_bytes(packet[14:16], "big")
    target_interact_x = None
    target_interact_y = None
    visible_attackable_candidate_count = 0
    acquisition_x = None
    acquisition_y = None
    if not target_exists:
        visible_attackable_candidate_count = packet[16]
        if visible_attackable_candidate_count:
            if packet[17] == 0 or packet[18] == 0:
                raise CombatHudProtocolError(
                    "visible acquisition candidate geometry is malformed"
                )
            acquisition_x = packet[17] / 255.0
            acquisition_y = packet[18] / 255.0
        elif packet[17] or packet[18]:
            raise CombatHudProtocolError(
                "absent acquisition candidate contains geometry"
            )
        target_health_current = 0
    elif target_dead:
        if packet[18] == 0xA5 and packet[16] > 0 and packet[17] > 0:
            target_interact_x = packet[16] / 255.0
            target_interact_y = packet[17] / 255.0
        elif any(packet[16:19]):
            raise CombatHudProtocolError("dead target interact point is malformed")
        target_health_current = 0
    else:
        target_health_current = int.from_bytes(packet[16:19], "big")
    target_health_max = int.from_bytes(packet[19:22], "big")
    player_attack_power = int.from_bytes(packet[22:24], "big")
    target_frame_x = None
    target_frame_y = None
    if target_exists and target_bearing_code in {2, 3, 4, 5, 6, 7}:
        target_frame_x = packet[24] / 255.0
        target_frame_y = packet[25] / 255.0
    elif packet[24] or packet[25]:
        raise CombatHudProtocolError(
            "non-visible target contains selected-frame geometry"
        )

    if not target_exists:
        if flags & 0x38 or any(
            packet[index]
            for index in (6, 9, 10, 14, 15, 19, 20, 21)
        ):
            raise CombatHudProtocolError("absent target contains target state")
    elif target_identity == 0 or packet[10] == 0 or target_health_max == 0:
        raise CombatHudProtocolError("existing target identity is incomplete")
    if target_health_current > target_health_max:
        raise CombatHudProtocolError("target health current exceeds maximum")
    if target_exists and packet[6] != floor(
        target_health_current * 255.0 / target_health_max + 0.5
    ):
        raise CombatHudProtocolError(
            "target health percent diverges from absolute health"
        )
    if target_dead and (packet[6] != 0 or target_health_current != 0):
        raise CombatHudProtocolError("dead target has non-zero health")
    if not player_alive and packet[4] != 0:
        raise CombatHudProtocolError("dead player has non-zero health")
    combo_points = packet[7] & 0x07
    loot_event_sequence = packet[7] >> 3
    if packet[5] > MAX_ENERGY or combo_points > MAX_COMBO_POINTS:
        raise CombatHudProtocolError("energy or combo points exceed protocol bounds")
    if not slot1_exact and action_flags & 0x0F:
        raise CombatHudProtocolError("slot 1 state lacks an exact binding")
    if not slot2_exact and (action_flags & 0xF0 or packet[12]):
        raise CombatHudProtocolError("slot 2 state lacks an exact binding")
    if action_flags & 0x80 and packet[12] != 0:
        raise CombatHudProtocolError("ready action has cooldown remaining")
    if not slot3_exact and slot3_flags & 0x1E:
        raise CombatHudProtocolError("slot 3 state lacks an exact binding")

    return CombatHudPacket(
        sequence=packet[3],
        player_alive=player_alive,
        in_combat=bool(flags & 0x02),
        target_exists=target_exists,
        target_hostile=bool(flags & 0x08),
        target_dead=target_dead,
        target_player=bool(flags & 0x20),
        slot1_attack_exact=slot1_exact,
        slot2_sinister_strike_exact=slot2_exact,
        slot3_eviscerate_exact=slot3_exact,
        target_bearing_code=target_bearing_code,
        target_frame_x_normalized=target_frame_x,
        target_frame_y_normalized=target_frame_y,
        player_health_pct=_decode_percent(packet[4]),
        player_energy=packet[5],
        player_attack_power=player_attack_power,
        target_health_pct=_decode_percent(packet[6]) if target_exists else None,
        target_health_current=(target_health_current if target_exists else None),
        target_health_max=(target_health_max if target_exists else None),
        combo_points=combo_points,
        loot_event_sequence=loot_event_sequence,
        player_level=packet[8],
        target_level=(None if packet[9] == 255 else packet[9]) if target_exists else None,
        target_reaction=packet[10] if target_exists else None,
        slot1_usable=bool(action_flags & 0x01),
        slot1_current=bool(action_flags & 0x02),
        slot1_in_range=slot1_range,
        slot2_usable=bool(action_flags & 0x10),
        slot2_in_range=slot2_range,
        slot2_cooldown_ready=bool(action_flags & 0x80),
        slot2_cooldown_remaining_ms=packet[12] * COOLDOWN_TICK_MS,
        slot3_usable=bool(slot3_flags & 0x02),
        slot3_in_range=slot3_range,
        slot3_cooldown_ready=bool(slot3_flags & 0x10),
        target_identity_crc16=target_identity if target_exists else None,
        target_interact_x_normalized=target_interact_x,
        target_interact_y_normalized=target_interact_y,
        visible_attackable_candidate_count=visible_attackable_candidate_count,
        acquisition_x_normalized=acquisition_x,
        acquisition_y_normalized=acquisition_y,
    )


def packet_to_bits(packet: bytes) -> tuple[int, ...]:
    if len(packet) != PACKET_BYTES:
        raise CombatHudProtocolError(f"packet must contain {PACKET_BYTES} bytes")
    return tuple((value >> shift) & 1 for value in packet for shift in range(7, -1, -1))


def bits_to_packet(bits: list[int] | tuple[int, ...]) -> bytes:
    if len(bits) != PAYLOAD_BITS or any(type(bit) is not int or bit not in (0, 1) for bit in bits):
        raise CombatHudProtocolError(
            f"payload must contain {PAYLOAD_BITS} binary values"
        )
    output = bytearray()
    for offset in range(0, PAYLOAD_BITS, 8):
        value = 0
        for bit in bits[offset : offset + 8]:
            value = (value << 1) | bit
        output.append(value)
    return bytes(output)


def validate_valid_observation_semantics(
    observation: Mapping[str, Any],
    *,
    timing_tolerance_s: float = TIMING_TOLERANCE_S,
) -> CombatHudPacket:
    if observation.get("tracking_state") != "VALID":
        raise CombatHudProtocolError("observation must have VALID tracking")
    protocol = observation.get("protocol")
    player = observation.get("player")
    target = observation.get("target")
    combat = observation.get("combat")
    actions = observation.get("actions")
    timing = observation.get("timing")
    if not all(isinstance(value, Mapping) for value in (protocol, player, combat, actions, timing)):
        raise CombatHudProtocolError("VALID observation is incomplete")
    try:
        packet = decode_packet(bytes.fromhex(str(protocol["packet_hex"])))
    except (KeyError, TypeError, ValueError) as error:
        raise CombatHudProtocolError("packet_hex is invalid") from error
    if protocol.get("sequence") != packet.sequence or protocol.get("crc_valid") is not True:
        raise CombatHudProtocolError("protocol metadata diverges from packet")
    if player != {
        "alive": packet.player_alive,
        "health_pct": packet.player_health_pct,
        "energy": packet.player_energy,
        "attack_power": packet.player_attack_power,
        "level": packet.player_level,
    }:
        raise CombatHudProtocolError("published player state diverges from packet")
    expected_target: dict[str, Any] | None = None
    if packet.target_exists:
        expected_target = {
            "identity_crc16": packet.target_identity_crc16,
            "hostile": packet.target_hostile,
            "dead": packet.target_dead,
            "is_player": packet.target_player,
            "health_pct": packet.target_health_pct,
            "health_current": packet.target_health_current,
            "health_max": packet.target_health_max,
            "level": packet.target_level,
            "reaction": packet.target_reaction,
            "bearing_code": packet.target_bearing_code,
            "bearing_state": TARGET_BEARING_CODES[packet.target_bearing_code][0],
            "bearing_direction": TARGET_BEARING_CODES[packet.target_bearing_code][1],
            "bearing_offset_x_normalized": (
                None
                if packet.target_frame_x_normalized is None
                else packet.target_frame_x_normalized * 2.0 - 1.0
            ),
            "interact_x_normalized": packet.target_interact_x_normalized,
            "interact_y_normalized": packet.target_interact_y_normalized,
        }
    if target != expected_target:
        raise CombatHudProtocolError("published target state diverges from packet")
    if combat != {
        "in_combat": packet.in_combat,
        "combo_points": packet.combo_points,
        "loot_event_sequence": packet.loot_event_sequence,
        "acquisition_bearing_code": (
            0 if packet.target_exists else packet.target_bearing_code
        ),
        "acquisition_bearing_state": (
            "LOST"
            if packet.target_exists
            else TARGET_BEARING_CODES[packet.target_bearing_code][0]
        ),
        "acquisition_bearing_direction": (
            None
            if packet.target_exists
            else TARGET_BEARING_CODES[packet.target_bearing_code][1]
        ),
        "acquisition_bearing_offset_x_normalized": (
            None
            if packet.target_exists
            else TARGET_BEARING_CODES[packet.target_bearing_code][2]
        ),
        "visible_attackable_candidate_count": (
            0 if packet.target_exists else packet.visible_attackable_candidate_count
        ),
        "acquisition_x_normalized": (
            None if packet.target_exists else packet.acquisition_x_normalized
        ),
        "acquisition_y_normalized": (
            None if packet.target_exists else packet.acquisition_y_normalized
        ),
    }:
        raise CombatHudProtocolError("published combat state diverges from packet")
    expected_actions = {
        "slot1_attack": {
            "exact_binding": packet.slot1_attack_exact,
            "usable": packet.slot1_usable,
            "current": packet.slot1_current,
            "in_range": packet.slot1_in_range,
            "cooldown_ready": True,
            "cooldown_remaining_ms": 0,
        },
        "slot2_sinister_strike": {
            "exact_binding": packet.slot2_sinister_strike_exact,
            "usable": packet.slot2_usable,
            "current": False,
            "in_range": packet.slot2_in_range,
            "cooldown_ready": packet.slot2_cooldown_ready,
            "cooldown_remaining_ms": packet.slot2_cooldown_remaining_ms,
        },
        "slot3_eviscerate": {
            "exact_binding": packet.slot3_eviscerate_exact,
            "usable": packet.slot3_usable,
            "current": False,
            "in_range": packet.slot3_in_range,
            "cooldown_ready": packet.slot3_cooldown_ready,
            "cooldown_remaining_ms": 0,
        },
    }
    if actions != expected_actions:
        raise CombatHudProtocolError("published action state diverges from packet")

    try:
        captured_s = float(timing["monotonic_timestamp_s"])
        observed_s = float(timing["observed_monotonic_s"])
        age_ms = float(timing["age_at_observation_ms"])
        frame_age_ms = float(timing["frame_age_ms"])
        freshness_ms = float(timing["freshness_limit_ms"])
        expires_s = float(timing["expires_monotonic_s"])
    except (KeyError, TypeError, ValueError) as error:
        raise CombatHudProtocolError("observation timing is incomplete") from error
    values = (captured_s, observed_s, age_ms, frame_age_ms, freshness_ms, expires_s)
    if not all(isfinite(value) for value in values) or min(captured_s, observed_s, age_ms, frame_age_ms, expires_s) < 0:
        raise CombatHudProtocolError("observation timing must be finite and non-negative")
    if not isclose(freshness_ms, VALID_OBSERVATION_FRESHNESS_MS, rel_tol=0, abs_tol=1e-9):
        raise CombatHudProtocolError("observation freshness limit is not v1.0")
    if not isclose(
        expires_s,
        captured_s + freshness_ms / 1000.0,
        rel_tol=0,
        abs_tol=timing_tolerance_s,
    ):
        raise CombatHudProtocolError("observation expiry is inconsistent")
    tolerance_ms = timing_tolerance_s * 1000.0
    if observed_s + timing_tolerance_s < captured_s or observed_s - timing_tolerance_s > expires_s:
        raise CombatHudProtocolError("observation time lies outside freshness")
    if age_ms + tolerance_ms < max(frame_age_ms, (observed_s - captured_s) * 1000.0):
        raise CombatHudProtocolError("observation age understates source age")
    if age_ms - tolerance_ms > freshness_ms:
        raise CombatHudProtocolError("VALID combat observation is stale")
    return packet
