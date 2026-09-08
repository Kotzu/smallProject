from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class ZoneMapTransform:
    continent_index: int
    zone_index: int
    name: str
    loc_left: float
    loc_right: float
    loc_top: float
    loc_bottom: float

    def world_from_normalized(self, x: float, y: float) -> tuple[float, float]:
        if not all(isfinite(value) for value in (x, y)):
            raise ValueError("normalized map position must be finite")
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            raise ValueError("normalized map position is outside the current zone")
        return (
            self.loc_top + y * (self.loc_bottom - self.loc_top),
            self.loc_left + x * (self.loc_right - self.loc_left),
        )

    def normalized_from_world(self, world_x: float, world_y: float) -> tuple[float, float]:
        if not all(isfinite(value) for value in (world_x, world_y)):
            raise ValueError("world position must be finite")
        x = (world_y - self.loc_left) / (self.loc_right - self.loc_left)
        y = (world_x - self.loc_top) / (self.loc_bottom - self.loc_top)
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            raise ValueError("world position is outside the current zone map")
        return x, y


# Exact WorldMapArea.dbc bounds from the same 2.4.3 client-data generation.
TBC243_ZONE_TRANSFORMS: dict[tuple[int, int], ZoneMapTransform] = {
    (2, 25): ZoneMapTransform(
        2, 25, "Tirisfal",
        3033.333251953125, -1485.4166259765625,
        3837.499755859375, 824.9999389648438,
    ),
    (2, 26): ZoneMapTransform(
        2, 26, "Undercity",
        873.192626953125, -86.18240356445312,
        1877.9453125, 1237.8411865234375,
    ),
}


def tbc243_zone_transform(continent_index: int, zone_index: int) -> ZoneMapTransform:
    try:
        return TBC243_ZONE_TRANSFORMS[(continent_index, zone_index)]
    except KeyError as error:
        raise ValueError("current zone has no reviewed TBC 2.4.3 world transform") from error
