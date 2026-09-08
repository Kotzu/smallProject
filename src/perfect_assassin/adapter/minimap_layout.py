"""Explicit offline WMO minimap layout hypothesis; not an actor-floor sensor.

The pixel density is supplied by the experiment, never inferred as accuracy.
See docs/adr/2026-09-06-minimap-geometric-composition.md for source and limits.
"""

from dataclasses import dataclass
from math import ceil, cos, floor, isfinite, radians, sin

import numpy as np

from .wmo_groups import WmoGroups, world_to_model


@dataclass(frozen=True)
class MinimapTile:
    group_index: int
    column: int
    row: int
    width: int
    height: int


def tile_layout(groups, tiles, *, pixels_per_model_unit):
    """Place tile rectangles from MOGI minima without stretching alpha bounds.

    X increases right; model Y increases up. Tile row zero is bottommost.
    All input groups remain in the record; missing imagery is not empty space.
    Overlaps are retained, not interpreted as occupied floors or walkability.
    """
    density = pixels_per_model_unit
    if not isinstance(groups, WmoGroups) or not isinstance(tiles, (tuple, list)):
        raise ValueError("expected parsed WMO root and explicit tiles")
    if type(density) not in (int, float) or not isfinite(density) or not 0.1 <= density <= 16:
        raise ValueError("invalid explicit pixel density")
    if not 1 <= len(tiles) <= 64:
        raise ValueError("tile count exceeds budget")
    indexed = {g.index: g for g in groups.groups}
    seen, rectangles = set(), []
    for tile in tiles:
        if not isinstance(tile, MinimapTile):
            raise ValueError("invalid tile")
        values = (tile.group_index, tile.column, tile.row, tile.width, tile.height)
        if any(type(value) is not int for value in values):
            raise ValueError("tile fields must be integers")
        if (tile.group_index not in indexed or not 0 <= tile.column < 32
                or not 0 <= tile.row < 32
                or not 1 <= tile.width <= 256 or not 1 <= tile.height <= 256):
            raise ValueError("invalid tile group, dimensions or grid")
        key = (tile.group_index, tile.column, tile.row)
        if key in seen:
            raise ValueError("duplicate tile identity")
        seen.add(key)
        group = indexed[tile.group_index]
        left = group.minimum[0] * density + tile.column * 256
        top = -group.minimum[1] * density - tile.row * 256 - tile.height
        rectangles.append({"group_index": tile.group_index, "column": tile.column,
                           "row": tile.row, "left": left, "top": top,
                           "width": tile.width, "height": tile.height})
    origin = [floor(min(r[axis] for r in rectangles)) for axis in ("left", "top")]
    size = [ceil(max(r[axis] + r[extent] for r in rectangles)) - start
            for axis, extent, start in zip(("left", "top"), ("width", "height"), origin)]
    if max(size) > 2048:
        raise ValueError("composite exceeds pixel budget")
    return {"source": "OFFLINE_WMO_MINIMAP_LAYOUT_HYPOTHESIS",
            "root_sha256": groups.asset_sha256, "root_id": groups.root_id,
            "pixels_per_model_unit": float(density), "origin_xy": origin,
            "size": size, "tiles": rectangles,
            "groups_without_supplied_tiles": sorted(set(indexed) - {t.group_index for t in tiles}),
            "observed_actor_z": None, "floor_id": None, "execution_authority": False}


def model_xy_from_world_xy(world_xy, transform_matrix):
    """Invert horizontal placement only if unknown height cannot affect it."""
    world_to_model((0, 0, 0), transform_matrix)  # existing affine/bounds checks
    matrix = np.asarray(transform_matrix, dtype=float).reshape(4, 4)
    xy = np.asarray(world_xy, dtype=float)
    if xy.shape != (2,) or not np.isfinite(xy).all():
        raise ValueError("invalid observed XY")
    if np.any(np.abs(matrix[:2, 2]) > 1e-10):
        raise ValueError("horizontal projection depends on unknown height")
    plane = matrix[:2, :2]
    if np.linalg.cond(plane) > 1e6:
        raise ValueError("ill-conditioned horizontal transform")
    return tuple(float(v) for v in np.linalg.solve(plane, xy - matrix[:2, 3]))


def model_xy_to_composite_pixel(model_xy, layout):
    xy = np.asarray(model_xy, dtype=float)
    if xy.shape != (2,) or not np.isfinite(xy).all():
        raise ValueError("invalid model XY")
    density = layout["pixels_per_model_unit"]
    origin = np.asarray(layout["origin_xy"], dtype=float)
    if (type(density) not in (int, float) or not isfinite(density)
            or not 0.1 <= density <= 16 or origin.shape != (2,)
            or not np.isfinite(origin).all()):
        raise ValueError("invalid layout transform")
    return tuple(float(v) for v in xy * (density, -density) - origin)


def expected_texture_translation(before_xy, after_xy, transform_matrix, *,
                                 pixels_per_model_unit, rotation_degrees, scale):
    """Predicted texture shift when the actor anchor stays fixed in the minimap.

    Rotation/scale must be the same for both frames. This predicts a pixel
    displacement only; it neither fits those parameters nor validates Z.
    """
    if (type(rotation_degrees) not in (int, float) or not isfinite(rotation_degrees)
            or abs(rotation_degrees) > 360
            or type(scale) not in (int, float) or not isfinite(scale) or not 0.1 <= scale <= 16):
        raise ValueError("invalid fixed image transformation")
    plane = np.array([model_xy_from_world_xy(xy, transform_matrix)
                      for xy in (before_xy, after_xy)])
    layout = {"pixels_per_model_unit": pixels_per_model_unit, "origin_xy": [0, 0]}
    delta = np.array(model_xy_to_composite_pixel(plane[1] - plane[0], layout))
    angle = radians(rotation_degrees)
    rotation = np.array([[cos(angle), sin(angle)], [-sin(angle), cos(angle)]])
    return tuple(float(v) for v in -scale * (rotation @ delta))
