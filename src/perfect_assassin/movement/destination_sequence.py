"""Bounded semantic destination sequences for autonomous journeys.

The sequence contains identifiers only.  It never contains executable
waypoints; every leg is replanned from the fresh observed position by the
navigation runner.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


MAX_DESTINATIONS = 16
MAX_LOOP_COUNT = 32


@dataclass(frozen=True)
class DestinationSequence:
    sequence_id: str
    destination_ids: tuple[str, ...]
    loop_count: int = 1
    map_id: int | None = None
    close_loop: bool = False

    def __post_init__(self) -> None:
        if not self.sequence_id or len(self.sequence_id) > 128:
            raise ValueError("sequence_id must be non-empty and <=128 characters")
        if not 2 <= len(self.destination_ids) <= MAX_DESTINATIONS:
            raise ValueError("destination sequence must contain 2..16 destinations")
        if any(
            not isinstance(destination_id, str)
            or not destination_id
            or len(destination_id) > 160
            for destination_id in self.destination_ids
        ):
            raise ValueError("destination identifiers must be non-empty strings")
        if len(set(self.destination_ids)) != len(self.destination_ids):
            raise ValueError("destination identifiers must be unique")
        if not 1 <= self.loop_count <= MAX_LOOP_COUNT:
            raise ValueError("loop_count must be in [1, 32]")
        if type(self.close_loop) is not bool:
            raise ValueError("close_loop must be a boolean")
        if self.map_id is not None and (
            type(self.map_id) is not int or not 0 <= self.map_id <= 65_535
        ):
            raise ValueError("map_id must be null or an unsigned 16-bit integer")

    def expanded_destination_ids(self) -> tuple[str, ...]:
        """Return the bounded leg order, including return legs for loops."""

        expanded = self.destination_ids * self.loop_count
        if self.close_loop:
            expanded += (self.destination_ids[0],)
        return expanded

    def to_record(self) -> dict[str, Any]:
        return {
            "record_type": "semantic_destination_sequence",
            "schema_version": "1.0",
            "sequence_id": self.sequence_id,
            "destination_ids": list(self.destination_ids),
            "loop_count": self.loop_count,
            "map_id": self.map_id,
            "close_loop": self.close_loop,
            "execution_authority": False,
        }


def load_destination_sequence(path: Path) -> DestinationSequence:
    """Load and validate a bounded, identifier-only sequence file."""

    with path.open("r", encoding="utf-8") as stream:
        record = json.load(stream)
    if not isinstance(record, dict):
        raise ValueError("destination sequence must be a JSON object")
    if record.get("record_type") != "semantic_destination_sequence":
        raise ValueError("destination sequence record_type is invalid")
    if record.get("schema_version") != "1.0":
        raise ValueError("destination sequence schema_version is unsupported")
    if record.get("execution_authority") is not False:
        raise ValueError("destination sequence cannot authorize execution")
    destination_ids = record.get("destination_ids")
    if not isinstance(destination_ids, list):
        raise ValueError("destination_ids must be an array")
    return DestinationSequence(
        sequence_id=record.get("sequence_id", ""),
        destination_ids=tuple(destination_ids),
        loop_count=record.get("loop_count", 1),
        map_id=record.get("map_id"),
        close_loop=record.get("close_loop", False),
    )


def validate_destination_sequence_catalog(
    sequence: DestinationSequence,
    catalog_path: Path,
) -> None:
    """Reject sequence IDs that are absent from the selected semantic catalog.

    The catalog is evidence only: this preflight never turns coordinates into
    executable waypoints.  The navigation child still performs its complete
    map/atlas/geometry validation for each leg.
    """

    try:
        with catalog_path.open("r", encoding="utf-8") as stream:
            catalog = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("semantic destination catalog is unreadable") from error
    if not isinstance(catalog, dict):
        raise ValueError("semantic destination catalog must be a JSON object")
    if (
        catalog.get("record_type") != "semantic_location_catalog"
        or catalog.get("schema_version") != "1.0"
    ):
        raise ValueError("semantic destination catalog identity is unsupported")
    locations = catalog.get("locations")
    if not isinstance(locations, list):
        raise ValueError("semantic destination catalog has no locations")
    catalog_ids: set[str] = set()
    for item in locations:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("semantic destination catalog contains an invalid ID")
        destination_id = item["id"]
        if not destination_id or destination_id in catalog_ids:
            raise ValueError("semantic destination catalog contains duplicate IDs")
        catalog_ids.add(destination_id)
    missing = sorted(set(sequence.destination_ids) - catalog_ids)
    if missing:
        raise ValueError(
            "destination sequence contains IDs absent from the semantic catalog: "
            + ", ".join(missing)
        )
