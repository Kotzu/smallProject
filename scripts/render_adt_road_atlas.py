from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from perfect_assassin.adapter.adt_road import AdtRoadSemantic
from perfect_assassin.movement.zone_transform import tbc243_zone_transform
from scripts.convert_tbc_world_map import write_png


ADT_SIZE = 533.0 + 1.0 / 3.0
WORLD_ADTS = 64


def render(source: Path, destination: Path, *, width: int = 1002, height: int = 668) -> None:
    sidecars: dict[tuple[int, int], np.ndarray] = {}
    for path in source.glob("Azeroth_*.road"):
        semantic = AdtRoadSemantic.from_bytes(path.read_bytes())
        sidecars[(semantic.adt_x, semantic.adt_y)] = np.frombuffer(
            semantic.affinity, dtype=np.uint8
        ).reshape((semantic.height, semantic.width))
    if not sidecars:
        raise ValueError("no ADT road sidecars are available")

    zone = tbc243_zone_transform(2, 25)
    normalized_x = (np.arange(width, dtype=np.float64) + 0.5) / width
    normalized_y = (np.arange(height, dtype=np.float64) + 0.5) / height
    world_y = zone.loc_left + normalized_x * (zone.loc_right - zone.loc_left)
    world_x = zone.loc_top + normalized_y * (zone.loc_bottom - zone.loc_top)
    adt_x = np.floor(WORLD_ADTS / 2 - world_y / ADT_SIZE).astype(np.int32)
    adt_y = np.floor(WORLD_ADTS / 2 - world_x / ADT_SIZE).astype(np.int32)
    affinity = np.zeros((height, width), dtype=np.uint8)
    for (tile_x, tile_y), tile in sidecars.items():
        x_columns = np.flatnonzero(adt_x == tile_x)
        y_rows = np.flatnonzero(adt_y == tile_y)
        if x_columns.size == 0 or y_rows.size == 0:
            continue
        west_y = (WORLD_ADTS / 2 - tile_x) * ADT_SIZE
        north_x = (WORLD_ADTS / 2 - tile_y) * ADT_SIZE
        local_columns = np.clip(
            ((west_y - world_y[x_columns]) / ADT_SIZE * 1024).astype(np.int32),
            0, 1023,
        )
        local_rows = np.clip(
            ((north_x - world_x[y_rows]) / ADT_SIZE * 1024).astype(np.int32),
            0, 1023,
        )
        affinity[np.ix_(y_rows, x_columns)] = tile[np.ix_(local_rows, local_columns)]

    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    visible = affinity >= 48
    rgba[visible, 0] = 255
    rgba[visible, 1] = 70
    rgba[visible, 2] = 180
    rgba[visible, 3] = np.maximum(100, affinity[visible])
    write_png(destination, width, height, rgba.tobytes())


def main() -> int:
    parser = argparse.ArgumentParser(description="Render client ADT road semantics in calibrated Tirisfal atlas space.")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    render(arguments.source, arguments.destination)
    print(arguments.destination.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
