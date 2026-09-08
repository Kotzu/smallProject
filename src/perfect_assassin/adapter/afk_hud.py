"""Independent AFK status strip. Does not change coordinate/combat protocols."""

from __future__ import annotations

from dataclasses import dataclass

from .coordinate_hud import crc16_ccitt_false


@dataclass(frozen=True)
class AfkHudPacket:
    sequence: int
    known: bool
    afk: bool
    predator_in_world: bool
    input_blocked: bool
    combat_or_dead: bool

    @property
    def eligible(self) -> bool:
        return (
            self.known
            and self.predator_in_world
            and not self.input_blocked
            and not self.combat_or_dead
        )


def decode_afk_packet(raw: bytes) -> AfkHudPacket:
    if len(raw) != 6 or raw[:2] != bytes((0xAF, 1)):
        raise ValueError("invalid AFK strip identity")
    if crc16_ccitt_false(raw[:4]) != int.from_bytes(raw[4:], "big") or raw[3] & 0xE0:
        raise ValueError("invalid AFK strip CRC or flags")
    flags = raw[3]
    if flags & 2 and not flags & 1:
        raise ValueError("AFK state requires known status")
    return AfkHudPacket(
        raw[2],
        bool(flags & 1),
        bool(flags & 2),
        bool(flags & 4),
        bool(flags & 8),
        bool(flags & 16),
    )


@dataclass
class AfkEpisodeLatch:
    """One attempt per AFK episode, rearmed only by two fresh non-AFK samples."""

    handled: bool = False
    previous_sequence: int | None = None
    afk_samples: int = 0
    clear_samples: int = 0

    def observe(self, packet: AfkHudPacket | None, *, movement_busy: bool) -> bool:
        if packet is None or not packet.known:
            self.afk_samples = self.clear_samples = 0
            return False
        if packet.sequence == self.previous_sequence:
            return False
        self.previous_sequence = packet.sequence
        if not packet.predator_in_world:
            self.afk_samples = self.clear_samples = 0
            return False
        if not packet.afk:
            self.afk_samples = 0
            self.clear_samples += 1
            if self.clear_samples >= 2:
                self.handled = False
            return False
        self.clear_samples = 0
        if movement_busy or not packet.eligible:
            self.afk_samples = 0
            return False
        self.afk_samples += 1
        return not self.handled and self.afk_samples >= 2

    def mark_attempted(self) -> None:
        # Persist this BEFORE input, so an uncertain send cannot be retried.
        self.handled = True
