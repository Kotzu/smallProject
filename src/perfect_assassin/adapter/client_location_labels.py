"""API-derived location names; labels never certify XYZ, floor or geometry.

SavedVariables is an archive transport, even when read moments after writing.
It is not a fresh in-world stream. No OCR, screenshot inference or client I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite


@dataclass(frozen=True, slots=True)
class ClientLocationLabels:
    session_id: str
    evidence_ref: str
    captured_epoch: int
    game_time_ms: int
    synthetic: bool
    zone: str | None
    subzone: str | None

    def __post_init__(self):
        if not self.session_id or not self.evidence_ref:
            raise ValueError("location evidence requires session and reference")
        if type(self.synthetic) is not bool:
            raise TypeError("synthetic must be boolean")
        if (
            type(self.captured_epoch) is not int
            or not 1 <= self.captured_epoch <= 4102444800
        ):
            raise ValueError("invalid captured epoch")
        if type(self.game_time_ms) is not int or self.game_time_ms < 0:
            raise ValueError("invalid client clock")
        for label in (self.zone, self.subzone):
            if label is not None and (not isinstance(label, str) or len(label) > 256):
                raise ValueError("invalid API location label")

    def presentation(
        self, *, expected_session_id: str, now_utc: datetime, stale_after_s=5.0
    ):
        """Safe display model for future CC integration; never a live location."""
        if now_utc.tzinfo is None or now_utc.utcoffset() is None:
            raise ValueError("evaluation time must include timezone")
        if (
            type(stale_after_s) not in (float, int)
            or not isfinite(stale_after_s)
            or stale_after_s <= 0
        ):
            raise ValueError("invalid label freshness bound")
        age = now_utc.timestamp() - self.captured_epoch
        reasons = ["ARCHIVE_NOT_LIVE_TRANSPORT"]
        if self.session_id != expected_session_id:
            reasons.append("SESSION_MISMATCH")
        if self.synthetic:
            reasons.append("SYNTHETIC_EVIDENCE")
        if age < 0:
            reasons.append("FUTURE_RECORD")
        elif age > stale_after_s:
            reasons.append("STALE_RECORD")
        field_states = {
            name: "UNAVAILABLE"
            if value is None
            else "EMPTY"
            if value == ""
            else "REPORTED"
            for name, value in (("zone", self.zone), ("subzone", self.subzone))
        }
        if not self.zone and not self.subzone:
            reasons.append("NO_LOCATION_LABEL")
        # Historical text is separate from any current label. A caller cannot
        # accidentally present an old archive as the player's current room.
        compatible = (
            self.session_id == expected_session_id and not self.synthetic and age >= 0
        )
        last_label = (self.subzone or self.zone or None) if compatible else None
        return {
            "record_type": "client_location_labels",
            "schema_version": "1.0",
            "session_id": self.session_id,
            "evidence_ref": self.evidence_ref,
            "source": "CLIENT_ADDON_API",
            "transport": "SAVED_VARIABLES_ARCHIVE",
            "captured_at": datetime.fromtimestamp(self.captured_epoch, UTC).isoformat(),
            "game_time_ms": self.game_time_ms,
            "age_s": age,
            "zone": self.zone,
            "subzone": self.subzone,
            "api_functions": {"zone": "GetZoneText", "subzone": "GetSubZoneText"},
            "field_states": field_states,
            "status": "HISTORICAL_ONLY",
            "reasons": reasons,
            "current_label": None,
            "last_recorded_label": last_label,
            "floor_id": None,
            "observed_z": None,
            "geometry_identity": None,
            "physical_room_confirmed": False,
            "execution_authority": False,
            "operator_summary_ro": "Nume primit prin API, din arhivă; locația actuală nu este confirmată.",
        }


def labels_from_validated_export(export):
    """Called only after the existing addon schema and event order validation.

    Each snapshot is complete for the fields it actually contains: a missing
    or empty subzone never inherits a room name from an earlier observation.
    """
    snapshots = []
    for event in export["events"]:
        if event["kind"] not in {"player_snapshot", "map_position_snapshot"}:
            continue
        payload = event["payload"]
        snapshots.append(
            ClientLocationLabels(
                session_id=export["session_id"],
                evidence_ref=f"addon:{export['session_id']}:{event['seq']:06d}",
                captured_epoch=event["captured_epoch"],
                game_time_ms=event["game_time_ms"],
                synthetic=export["synthetic"],
                zone=payload.get("world_zone"),
                subzone=payload.get("world_subzone"),
            )
        )
    return tuple(snapshots)
