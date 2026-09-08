"""Asset-height alternatives; never evidence of the actor's actual floor."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class VerticalSurfaceCandidates:
    heights: tuple[float, ...]
    selected_surface_z: float

    @property
    def ambiguous(self) -> bool:
        return len(set(self.heights)) > 1

    def to_record(self):
        return {
            "schema_version": 1,
            "source": "CLIENT_ASSET_HEIGHT_QUERY",
            "heights": list(self.heights),
            "selected_surface_z": self.selected_surface_z,
            "ambiguous": self.ambiguous,
            "exhaustive": False,
            "observed_actor_z": None,
            "confirmed_floor_id": None,
            "execution_authority": False,
        }


def parse_vertical_candidates(record):
    if record is None:
        return None  # Legacy worker: unknown, not a singleton floor.
    if not isinstance(record, dict) or set(record) != {
        "schema_version",
        "source",
        "exhaustive",
        "selected_surface_z",
        "heights",
    }:
        raise ValueError("invalid vertical candidate record")
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != 1
        or record["source"] != "CLIENT_ASSET_HEIGHT_QUERY"
        or record["exhaustive"] is not False
    ):
        raise ValueError("invalid vertical candidate provenance/version")
    heights = record["heights"]
    if not isinstance(heights, list) or not 1 <= len(heights) <= 64:
        raise ValueError("invalid vertical candidate count")
    selected = record["selected_surface_z"]
    for number in [*heights, selected]:
        if type(number) not in (int, float) or not isfinite(number):
            raise ValueError("invalid vertical candidate height")
    if selected not in heights:
        raise ValueError("selected surface missing from candidates")
    return VerticalSurfaceCandidates(tuple(heights), selected)
