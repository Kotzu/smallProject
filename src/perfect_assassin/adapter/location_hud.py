"""Versioned API-label telemetry, independent of coordinate/combat/AFK wires."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .client_environment import decode_environment_bits, environment_display
from .coordinate_hud import crc16_ccitt_false


@dataclass(frozen=True, slots=True)
class LocationPacket:
    sequence: int
    session_tag: int
    client_time_ms: int
    in_world: bool
    region: str | None
    subzone: str | None
    region_overflow: bool
    subzone_overflow: bool
    wire_version: int = 1
    environment_bits: int | None = None
    capabilities_bits: int | None = None


def decode_location_packet(raw: bytes) -> LocationPacket:
    if len(raw) != 144 or raw[0] != 215 or raw[1] not in (1, 2):
        raise ValueError("invalid location packet identity")
    if crc16_ccitt_false(raw[:-2]) != int.from_bytes(raw[-2:], "big"):
        raise ValueError("invalid location CRC")
    flags = raw[3]
    if (
        flags & 0xE0
        or (raw[1] == 1 and raw[12:14] != b"\x00\x00")
        or (raw[1] == 2 and (raw[12] & 0xC0 or raw[13] & 0xFC))
    ):
        raise ValueError("unsupported location flags/reserved fields")
    labels = []
    for offset, size, known, overflow in (
        (14, raw[6], flags & 1, flags & 8),
        (78, raw[7], flags & 2, flags & 16),
    ):
        if size > 64 or (size and (not known or overflow)):
            raise ValueError("invalid location length/availability")
        if any(raw[offset + size : offset + 64]):
            raise ValueError("nonzero location padding")
        text = raw[offset : offset + size].decode("utf-8", errors="strict")
        if any(ord(char) < 32 or ord(char) == 127 for char in text):
            raise ValueError("control character in location")
        labels.append(text if known and not overflow else None)
    return LocationPacket(
        raw[2],
        int.from_bytes(raw[4:6], "big"),
        int.from_bytes(raw[8:12], "big"),
        bool(flags & 4),
        labels[0],
        labels[1],
        bool(flags & 8),
        bool(flags & 16),
        raw[1],
        raw[12] if raw[1] == 2 else None,
        raw[13] if raw[1] == 2 else None,
    )


class LocationStream:
    """Two advancing client samples; capture identity is checked by the caller.

    CRC/session_tag detect corruption and session changes, not authentication.
    Duplicate/stalled pixels never acquire a new observation timestamp.
    """

    def __init__(self, capture_binding: str):
        if not capture_binding:
            raise ValueError("capture binding required")
        self.binding = capture_binding
        self.previous = None
        self.latest = None

    def observe(self, packet: LocationPacket | None, observed_s: float):
        if (
            type(observed_s) not in (int, float)
            or not isfinite(observed_s)
            or observed_s < 0
        ):
            raise ValueError("invalid capture timestamp")
        if packet is None or not packet.in_world:
            self.previous = self.latest = None
            return None
        prior = self.previous
        if prior is None or packet.session_tag != prior.session_tag:
            self.previous, self.latest = packet, None
            return None
        delta = (packet.client_time_ms - prior.client_time_ms) % 2**32
        if delta == 0:
            return self.latest
        if delta >= 2**31:
            self.previous, self.latest = packet, None
            return None
        self.previous = packet
        self.latest = {
            "record_type": "live_client_location",
            "schema_version": "1.0",
            "source": "CLIENT_ADDON_API",
            "transport": f"RGB_NIBBLE_CRC_V{packet.wire_version}",
            "capture_binding": self.binding,
            "session_tag": packet.session_tag,
            "client_time_ms": packet.client_time_ms,
            "sequence": packet.sequence,
            "observed_monotonic_s": observed_s,
            "region": packet.region,
            "subzone": packet.subzone,
            "region_overflow": packet.region_overflow,
            "subzone_overflow": packet.subzone_overflow,
            "region_api": "GetZoneText",
            "subzone_api": "GetSubZoneText",
            "floor_id": None,
            "api_environment": (
                decode_environment_bits(
                    packet.environment_bits, packet.capabilities_bits
                )
                if packet.wire_version == 2
                else None
            ),
            "execution_authority": False,
        }
        return self.latest


def location_display(record, *, now_s: float, expected_binding: str, maximum_age_s=2.0):
    """No file I/O; stale/foreign labels disappear instead of looking current."""
    unknown = "Regiune / subzonă: date API indisponibile"
    if (
        not isinstance(record, dict)
        or record.get("record_type") != "live_client_location"
    ):
        return unknown
    if (
        record.get("capture_binding") != expected_binding
        or record.get("schema_version") != "1.0"
        or record.get("source") != "CLIENT_ADDON_API"
        or record.get("execution_authority") is not False
    ):
        return unknown
    observed = record.get("observed_monotonic_s")
    if (
        type(observed) not in (float, int)
        or not isfinite(observed)
        or not isfinite(now_s)
    ):
        return unknown
    if not 0 <= now_s - observed <= maximum_age_s:
        return "Regiune / subzonă: date API expirate"
    labels = []
    for key in ("region", "subzone"):
        value = record.get(key)
        if value is not None:
            if not isinstance(value, str):
                return unknown
            try:
                if len(value.encode("utf-8")) > 64:
                    return unknown
            except UnicodeEncodeError:
                return unknown
            if any(ord(char) < 32 or ord(char) == 127 for char in value):
                return unknown
        labels.append("indisponibilă" if value is None else value or "nespecificată")
    text = f"Regiune: {labels[0]}\nSubzonă: {labels[1]} · API"
    if record.get("api_environment") is not None:
        text += "\n" + environment_display(record["api_environment"])
    return text
