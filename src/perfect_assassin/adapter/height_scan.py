"""Strict ingestion of the optional four-height client-asset scan."""

from dataclasses import dataclass
from math import isfinite, tau


@dataclass(frozen=True, slots=True)
class HeightRay:
    bearing_rad: float
    height_offset_yards: float
    clear_prefix_yards: float
    blocked_by_yards: float | None

    def to_record(self):
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HeightScan:
    origin_xyz: tuple[float, float, float]
    rays: tuple[HeightRay, ...]

    def to_record(self):
        return {
            "schema_version": 1,
            "source": "CLIENT_ASSET_LINE_OF_SIGHT",
            "exhaustive": False,
            "origin_xyz": list(self.origin_xyz),
            "radius_yards": 12.0,
            "binary_search_iterations": 7,
            "rays": [ray.to_record() for ray in self.rays],
        }


def _finite(value):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError("invalid height scan number")
    return value


def parse_height_scan(record, *, expected_origin):
    if record is None:
        return None
    if not isinstance(record, dict) or set(record) != {
        "schema_version",
        "source",
        "exhaustive",
        "origin_xyz",
        "radius_yards",
        "binary_search_iterations",
        "rays",
    }:
        raise ValueError("invalid height scan record")
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != 1
        or record["source"] != "CLIENT_ASSET_LINE_OF_SIGHT"
        or record["exhaustive"] is not False
        or _finite(record["radius_yards"]) != 12
        or type(record["binary_search_iterations"]) is not int
        or record["binary_search_iterations"] != 7
    ):
        raise ValueError("invalid height scan provenance or protocol")
    origin = record["origin_xyz"]
    if not isinstance(origin, list) or len(origin) != 3 or len(expected_origin) != 3:
        raise ValueError("invalid height scan origin")
    if any(
        abs(_finite(a) - _finite(b)) > 1e-5 for a, b in zip(origin, expected_origin)
    ):
        raise ValueError("height scan origin differs from resolved query")
    rays = record["rays"]
    if not isinstance(rays, list) or len(rays) != 64:
        raise ValueError("invalid height scan ray count")
    parsed = []
    for index, ray in enumerate(rays):
        if not isinstance(ray, dict) or set(ray) != {
            "bearing_rad",
            "height_offset_yards",
            "clear_prefix_yards",
            "blocked_by_yards",
        }:
            raise ValueError("invalid height scan ray")
        angle = _finite(ray["bearing_rad"])
        height = _finite(ray["height_offset_yards"])
        if (
            abs(angle - tau * (index % 16) / 16) > 1e-5
            or abs(height - (0.25, 0.60, 1.20, 1.80)[index // 16]) > 1e-6
        ):
            raise ValueError("height scan grid is incomplete or unordered")
        lower = _finite(ray["clear_prefix_yards"])
        upper = ray["blocked_by_yards"]
        if not 0 <= lower <= 12:
            raise ValueError("invalid height scan clear prefix")
        if upper is None:
            if lower != 12:
                raise ValueError("unblocked scan did not test full radius")
        elif not lower < _finite(upper) <= 12 or upper - lower > 12 / 128 + 2e-6:
            raise ValueError("invalid height scan obstruction bracket")
        parsed.append(HeightRay(angle, height, lower, upper))
    return HeightScan(tuple(origin), tuple(parsed))
