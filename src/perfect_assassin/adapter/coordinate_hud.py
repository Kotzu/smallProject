from __future__ import annotations

from dataclasses import dataclass
from math import floor, isclose, isfinite, pi
from typing import Any, Mapping


MAGIC = 0xA5
PROTOCOL_VERSION = 3
PACKET_BYTES = 14
PAYLOAD_BITS = PACKET_BYTES * 8
VALID_OBSERVATION_FRESHNESS_MS = 600.0
TIMING_TOLERANCE_S = 1e-6


class CoordinateHudProtocolError(ValueError):
    pass


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


@dataclass(frozen=True)
class CoordinateHudPacket:
    sequence: int
    position_available: bool
    map_context_ready: bool
    world_map_visible: bool
    x: float | None
    y: float | None
    continent_index: int
    zone_index: int
    facing_available: bool
    facing_rad: float | None
    player_dead_or_ghost: bool
    player_ghost: bool


def encode_packet(
    *,
    sequence: int,
    position_available: bool,
    map_context_ready: bool,
    world_map_visible: bool,
    x: float | None,
    y: float | None,
    continent_index: int = 0,
    zone_index: int = 0,
    facing_rad: float | None = None,
    player_dead_or_ghost: bool = False,
    player_ghost: bool = False,
) -> bytes:
    if type(player_dead_or_ghost) is not bool or type(player_ghost) is not bool:
        raise CoordinateHudProtocolError("player life-state flags must be booleans")
    if player_ghost and not player_dead_or_ghost:
        raise CoordinateHudProtocolError("ghost state requires dead-or-ghost state")
    if position_available:
        if x is None or y is None or not 0 <= x <= 1 or not 0 <= y <= 1:
            raise CoordinateHudProtocolError("available position requires normalized x and y")
        if not map_context_ready:
            raise CoordinateHudProtocolError(
                "available position requires a ready map context"
            )
        if world_map_visible:
            raise CoordinateHudProtocolError(
                "available position cannot be reported while the world map is visible"
            )
    if facing_rad is not None and (
        isinstance(facing_rad, bool)
        or not isinstance(facing_rad, (int, float))
        or not isfinite(facing_rad)
        or not 0 <= float(facing_rad) < 2 * pi
    ):
        raise CoordinateHudProtocolError("player facing must be radians in [0, 2pi)")
    facing_available = facing_rad is not None
    flags = (
        int(position_available)
        | (int(map_context_ready) << 1)
        | (int(world_map_visible) << 2)
        | (int(facing_available) << 3)
        | (int(player_dead_or_ghost) << 4)
        | (int(player_ghost) << 5)
    )
    # Lua 5.1 uses math.floor(value * 65535 + 0.5). Keep the reference codec
    # byte-identical at half-LSB boundaries instead of Python's ties-to-even round().
    x_quantized = floor((x or 0) * 65535 + 0.5)
    y_quantized = floor((y or 0) * 65535 + 0.5)
    facing_quantized = floor(((float(facing_rad) if facing_available else 0.0) / (2 * pi)) * 65535 + 0.5)
    body = bytes(
        (
            MAGIC,
            PROTOCOL_VERSION,
            flags,
            sequence & 0xFF,
            (x_quantized >> 8) & 0xFF,
            x_quantized & 0xFF,
            (y_quantized >> 8) & 0xFF,
            y_quantized & 0xFF,
            max(0, min(255, int(continent_index))),
            max(0, min(255, int(zone_index))),
            (facing_quantized >> 8) & 0xFF,
            facing_quantized & 0xFF,
        )
    )
    checksum = crc16_ccitt_false(body)
    return body + checksum.to_bytes(2, "big")


def decode_packet(packet: bytes) -> CoordinateHudPacket:
    if len(packet) != PACKET_BYTES:
        raise CoordinateHudProtocolError(f"packet must contain {PACKET_BYTES} bytes")
    if packet[0] != MAGIC:
        raise CoordinateHudProtocolError("magic mismatch")
    if packet[1] != PROTOCOL_VERSION:
        raise CoordinateHudProtocolError("protocol version mismatch")
    expected = int.from_bytes(packet[-2:], "big")
    actual = crc16_ccitt_false(packet[:-2])
    if actual != expected:
        raise CoordinateHudProtocolError("CRC-16 mismatch")
    flags = packet[2]
    if flags & 0xC0:
        raise CoordinateHudProtocolError("reserved flag bits are non-zero")
    available = bool(flags & 1)
    map_context_ready = bool(flags & 2)
    world_map_visible = bool(flags & 4)
    facing_available = bool(flags & 8)
    player_dead_or_ghost = bool(flags & 16)
    player_ghost = bool(flags & 32)
    if player_ghost and not player_dead_or_ghost:
        raise CoordinateHudProtocolError("ghost flag requires dead-or-ghost flag")
    x_quantized = int.from_bytes(packet[4:6], "big")
    y_quantized = int.from_bytes(packet[6:8], "big")
    facing_quantized = int.from_bytes(packet[10:12], "big")
    if not available and (x_quantized or y_quantized):
        raise CoordinateHudProtocolError("unavailable packet contains coordinates")
    if available and not map_context_ready:
        raise CoordinateHudProtocolError(
            "available position requires a ready map context"
        )
    if available and world_map_visible:
        raise CoordinateHudProtocolError(
            "available position cannot be reported while the world map is visible"
        )
    if not facing_available and facing_quantized:
        raise CoordinateHudProtocolError("unavailable packet contains player facing")
    return CoordinateHudPacket(
        sequence=packet[3],
        position_available=available,
        map_context_ready=map_context_ready,
        world_map_visible=world_map_visible,
        x=x_quantized / 65535 if available else None,
        y=y_quantized / 65535 if available else None,
        continent_index=packet[8],
        zone_index=packet[9],
        facing_available=facing_available,
        facing_rad=(
            facing_quantized * (2 * pi) / 65535 if facing_available else None
        ),
        player_dead_or_ghost=player_dead_or_ghost,
        player_ghost=player_ghost,
    )


def validate_valid_observation_semantics(
    observation: Mapping[str, Any],
    *,
    timing_tolerance_s: float = TIMING_TOLERANCE_S,
) -> CoordinateHudPacket:
    """Verify relationships JSON Schema cannot express for a VALID HUD fact.

    The caller still validates the versioned observation schema first. This
    semantic check binds the published position to the CRC-protected packet and
    enforces the monotonic freshness interval used by contract v2.0.
    """

    if observation.get("tracking_state") != "VALID":
        raise CoordinateHudProtocolError("observation must have VALID tracking")
    if (
        not isinstance(timing_tolerance_s, (int, float))
        or isinstance(timing_tolerance_s, bool)
        or not isfinite(timing_tolerance_s)
        or timing_tolerance_s < 0
    ):
        raise CoordinateHudProtocolError(
            "timing tolerance must be finite and non-negative"
        )

    protocol = observation.get("protocol")
    position = observation.get("position")
    player_state = observation.get("player_state")
    timing = observation.get("timing")
    if (
        not isinstance(protocol, Mapping)
        or not isinstance(position, Mapping)
        or not isinstance(player_state, Mapping)
    ):
        raise CoordinateHudProtocolError(
            "VALID observation requires protocol, position and player-state objects"
        )
    if not isinstance(timing, Mapping):
        raise CoordinateHudProtocolError("observation timing must be an object")

    try:
        confidence = float(observation["confidence"])
    except (KeyError, TypeError, ValueError) as error:
        raise CoordinateHudProtocolError("observation confidence is invalid") from error
    if not isfinite(confidence) or not 0 < confidence <= 1:
        raise CoordinateHudProtocolError(
            "VALID observation confidence must be finite and in (0, 1]"
        )

    try:
        packet = decode_packet(bytes.fromhex(str(protocol["packet_hex"])))
    except (KeyError, TypeError, ValueError) as error:
        raise CoordinateHudProtocolError(
            "observation packet_hex is not a valid coordinate HUD packet"
        ) from error

    decoded_flags = (
        int(packet.position_available)
        | (int(packet.map_context_ready) << 1)
        | (int(packet.world_map_visible) << 2)
        | (int(packet.facing_available) << 3)
        | (int(packet.player_dead_or_ghost) << 4)
        | (int(packet.player_ghost) << 5)
    )
    if int(protocol["sequence"]) != packet.sequence:
        raise CoordinateHudProtocolError("protocol sequence diverges from packet_hex")
    if int(protocol["flags"]) != decoded_flags:
        raise CoordinateHudProtocolError("protocol flags diverge from packet_hex")
    if not packet.position_available or observation.get("map_position_available") is not True:
        raise CoordinateHudProtocolError("VALID observation packet has no position")
    if position.get("coordinate_space") != "normalized_current_zone_map":
        raise CoordinateHudProtocolError("observation coordinate space is invalid")
    if (
        float(position["x"]) != packet.x
        or float(position["y"]) != packet.y
        or int(position["continent_index"]) != packet.continent_index
        or int(position["zone_index"]) != packet.zone_index
    ):
        raise CoordinateHudProtocolError("published position diverges from packet_hex")
    published_facing = position.get("facing_rad")
    if packet.facing_available:
        if published_facing is None or float(published_facing) != packet.facing_rad:
            raise CoordinateHudProtocolError("published facing diverges from packet_hex")
    elif published_facing is not None:
        raise CoordinateHudProtocolError("published facing lacks packet evidence")
    if (
        player_state.get("dead_or_ghost") is not packet.player_dead_or_ghost
        or player_state.get("ghost") is not packet.player_ghost
    ):
        raise CoordinateHudProtocolError(
            "published player state diverges from packet_hex"
        )

    try:
        captured_s = float(timing["monotonic_timestamp_s"])
        frame_age_ms = float(timing["frame_age_ms"])
        observed_s = float(timing["observed_monotonic_s"])
        observation_age_ms = float(timing["age_at_observation_ms"])
        freshness_ms = float(timing["freshness_limit_ms"])
        expires_s = float(timing["expires_monotonic_s"])
    except (KeyError, TypeError, ValueError) as error:
        raise CoordinateHudProtocolError("observation timing is incomplete") from error
    if not all(
        isfinite(value)
        for value in (
            captured_s,
            frame_age_ms,
            observed_s,
            observation_age_ms,
            freshness_ms,
            expires_s,
        )
    ):
        raise CoordinateHudProtocolError("observation timing must be finite")
    if (
        captured_s < 0
        or frame_age_ms < 0
        or observed_s < 0
        or observation_age_ms < 0
        or freshness_ms <= 0
        or expires_s < 0
    ):
        raise CoordinateHudProtocolError(
            "observation timing must be non-negative with positive freshness"
        )
    if not isclose(
        freshness_ms,
        VALID_OBSERVATION_FRESHNESS_MS,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise CoordinateHudProtocolError("observation freshness limit is not v2.0")

    tolerance_ms = float(timing_tolerance_s) * 1000.0
    expected_expiry_s = captured_s + freshness_ms / 1000.0
    if not isclose(
        expires_s,
        expected_expiry_s,
        rel_tol=0.0,
        abs_tol=float(timing_tolerance_s),
    ):
        raise CoordinateHudProtocolError("observation expiry is inconsistent")
    if observed_s + timing_tolerance_s < captured_s:
        raise CoordinateHudProtocolError("observation precedes capture")
    if observed_s - timing_tolerance_s > expires_s:
        raise CoordinateHudProtocolError("observation occurs after expiry")
    minimum_age_ms = max(frame_age_ms, (observed_s - captured_s) * 1000.0)
    if observation_age_ms + tolerance_ms < minimum_age_ms:
        raise CoordinateHudProtocolError("observation age understates source age")
    if observation_age_ms - tolerance_ms > freshness_ms:
        raise CoordinateHudProtocolError("VALID observation is stale")
    return packet


def validate_sequence_summary_semantics(
    summary: Mapping[str, Any],
    *,
    duration_tolerance_ms: float = 0.002,
) -> None:
    """Verify cross-field identities for a contract-valid HUD sequence summary."""

    if (
        not isinstance(duration_tolerance_ms, (int, float))
        or isinstance(duration_tolerance_ms, bool)
        or not isfinite(duration_tolerance_ms)
        or duration_tolerance_ms < 0
    ):
        raise CoordinateHudProtocolError(
            "sequence duration tolerance must be finite and non-negative"
        )

    def count(name: str) -> int:
        value = summary.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise CoordinateHudProtocolError(
                f"sequence summary {name} must be a non-negative integer"
            )
        return value

    requested = count("requested_samples")
    observed = count("observed_samples")
    valid = count("valid_observations")
    if observed == 0 or observed > requested:
        raise CoordinateHudProtocolError(
            "sequence observed_samples must be within requested_samples"
        )
    if valid > observed:
        raise CoordinateHudProtocolError(
            "sequence valid_observations exceeds observed_samples"
        )
    all_valid = summary.get("all_observations_valid")
    if not isinstance(all_valid, bool) or all_valid != (valid == observed):
        raise CoordinateHudProtocolError(
            "sequence all_observations_valid contradicts observation counts"
        )
    if summary.get("all_observations_contract_valid") is not True:
        raise CoordinateHudProtocolError(
            "sequence observations were not all contract-valid"
        )

    sequence = summary.get("sequence")
    timing = summary.get("timing")
    if not isinstance(sequence, Mapping) or not isinstance(timing, Mapping):
        raise CoordinateHudProtocolError(
            "sequence summary requires sequence and timing objects"
        )
    advances = sequence.get("advances")
    duplicates = sequence.get("duplicates")
    if (
        not isinstance(advances, int)
        or isinstance(advances, bool)
        or advances < 0
        or not isinstance(duplicates, int)
        or isinstance(duplicates, bool)
        or duplicates < 0
    ):
        raise CoordinateHudProtocolError(
            "sequence transition counts must be non-negative integers"
        )
    possible_transitions = max(valid - 1, 0)
    if advances + duplicates > possible_transitions:
        raise CoordinateHudProtocolError(
            "sequence transition counts exceed valid observations"
        )

    first_sequence = sequence.get("first")
    last_sequence = sequence.get("last")
    if valid == 0:
        if first_sequence is not None or last_sequence is not None:
            raise CoordinateHudProtocolError(
                "empty valid sequence cannot publish endpoints"
            )
    elif not (
        isinstance(first_sequence, int)
        and not isinstance(first_sequence, bool)
        and isinstance(last_sequence, int)
        and not isinstance(last_sequence, bool)
    ):
        raise CoordinateHudProtocolError(
            "non-empty valid sequence requires integer endpoints"
        )
    maximum_forward_delta = sequence.get("maximum_forward_delta")
    maximum_unchanged_ms = sequence.get("maximum_unchanged_ms")
    if (
        not isinstance(maximum_forward_delta, int)
        or isinstance(maximum_forward_delta, bool)
        or maximum_forward_delta < 0
        or not isinstance(maximum_unchanged_ms, (int, float))
        or isinstance(maximum_unchanged_ms, bool)
        or not isfinite(maximum_unchanged_ms)
        or maximum_unchanged_ms < 0
    ):
        raise CoordinateHudProtocolError("sequence transition maxima are invalid")
    if (advances == 0) != (maximum_forward_delta == 0):
        raise CoordinateHudProtocolError(
            "sequence maximum_forward_delta contradicts advances"
        )
    if duplicates == 0 and maximum_unchanged_ms != 0:
        raise CoordinateHudProtocolError(
            "sequence maximum_unchanged_ms contradicts duplicates"
        )

    try:
        first_time = float(timing["first_monotonic_timestamp_s"])
        last_time = float(timing["last_monotonic_timestamp_s"])
        evaluated_time = float(timing["evaluated_monotonic_s"])
        duration_ms = float(timing["duration_ms"])
        maximum_frame_age_ms = float(timing["maximum_frame_age_ms"])
        freshness_limit_ms = float(timing["freshness_limit_ms"])
    except (KeyError, TypeError, ValueError) as error:
        raise CoordinateHudProtocolError("sequence timing is incomplete") from error
    if not all(
        isfinite(value)
        for value in (
            first_time,
            last_time,
            evaluated_time,
            duration_ms,
            maximum_frame_age_ms,
            freshness_limit_ms,
        )
    ):
        raise CoordinateHudProtocolError("sequence timing must be finite")
    if (
        first_time < 0
        or first_time > last_time
        or last_time > evaluated_time
        or maximum_frame_age_ms < 0
        or freshness_limit_ms <= 0
    ):
        raise CoordinateHudProtocolError("sequence timing order is invalid")
    expected_duration_ms = (last_time - first_time) * 1000.0
    if not isclose(
        duration_ms,
        expected_duration_ms,
        rel_tol=0.0,
        abs_tol=float(duration_tolerance_ms),
    ):
        raise CoordinateHudProtocolError("sequence duration is inconsistent")

    gate_state = summary.get("gate_state")
    reason = summary.get("reason")
    if gate_state == "PASS":
        if (
            reason != "fresh_sequence_verified"
            or observed != requested
            or valid != observed
            or not all_valid
            or advances < 1
            or advances + duplicates != observed - 1
            or maximum_frame_age_ms > freshness_limit_ms
        ):
            raise CoordinateHudProtocolError(
                "PASS sequence summary has contradictory counts, flags or reason"
            )
    elif gate_state == "FAIL":
        if reason == "fresh_sequence_verified":
            raise CoordinateHudProtocolError(
                "FAIL sequence summary cannot claim fresh verification"
            )
        if reason == "observation_not_valid" and all_valid:
            raise CoordinateHudProtocolError(
                "observation_not_valid contradicts all_observations_valid"
            )
    else:
        raise CoordinateHudProtocolError("sequence gate_state is invalid")


def packet_to_bits(packet: bytes) -> tuple[int, ...]:
    if len(packet) != PACKET_BYTES:
        raise CoordinateHudProtocolError(f"packet must contain {PACKET_BYTES} bytes")
    return tuple((value >> shift) & 1 for value in packet for shift in range(7, -1, -1))


def bits_to_packet(bits: list[int] | tuple[int, ...]) -> bytes:
    if len(bits) != PAYLOAD_BITS or any(bit not in (0, 1) for bit in bits):
        raise CoordinateHudProtocolError(f"payload must contain {PAYLOAD_BITS} binary values")
    output = bytearray()
    for offset in range(0, PAYLOAD_BITS, 8):
        value = 0
        for bit in bits[offset : offset + 8]:
            value = (value << 1) | bit
        output.append(value)
    return bytes(output)
