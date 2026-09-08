from dataclasses import replace
from math import cos, sin

import numpy as np
import pytest

from perfect_assassin.adapter.minimap_layout import (
    MinimapTile, expected_texture_translation, model_xy_from_world_xy,
    model_xy_to_composite_pixel, tile_layout,
)
from perfect_assassin.adapter.wmo_groups import WmoGroup, WmoGroups


def groups():
    return WmoGroups("a" * 64, 123, (
        WmoGroup(0, 0, (-10, -20, -50), (20, 30, 100)),
        WmoGroup(1, 0, (0, 5, -1000), (20, 40, 2000)),
    ))


def test_tiles_share_metric_frame_and_missing_is_not_empty_space():
    result = tile_layout(groups(), [MinimapTile(0, 0, 0, 64, 128)], pixels_per_model_unit=2)
    assert result["origin_xy"] == [-20, -88]
    assert result["size"] == [64, 128]
    assert result["groups_without_supplied_tiles"] == [1]
    assert result["observed_actor_z"] is None
    assert result["floor_id"] is None
    assert result["execution_authority"] is False
    assert model_xy_to_composite_pixel((-10, -20), result) == (0, 128)


def test_multi_tile_grid_starts_from_bottom_and_handles_partial_edge():
    result = tile_layout(groups(), [MinimapTile(0, 0, 0, 256, 256),
                                  MinimapTile(0, 1, 1, 32, 64)], pixels_per_model_unit=2)
    a, b = result["tiles"]
    assert b["left"] - a["left"] == 256
    assert b["top"] == a["top"] - 64
    assert result["size"] == [288, 320]


def test_group_offsets_not_fitted_independently():
    result = tile_layout(groups(), [MinimapTile(0, 0, 0, 64, 128),
                                  MinimapTile(1, 0, 0, 32, 32)], pixels_per_model_unit=2)
    a, b = result["tiles"]
    assert b["left"] - a["left"] == 20
    assert b["top"] - a["top"] == 46


@pytest.mark.parametrize("density", [0, -1, True, np.nan, np.inf, 17])
def test_invalid_density(density):
    with pytest.raises(ValueError):
        tile_layout(groups(), [MinimapTile(0, 0, 0, 32, 32)], pixels_per_model_unit=density)


@pytest.mark.parametrize("field,value", [("group_index", 3), ("column", -1),
    ("row", 32), ("width", 0), ("height", 257), ("width", True)])
def test_invalid_tile(field, value):
    tile = replace(MinimapTile(0, 0, 0, 32, 32), **{field: value})
    with pytest.raises(ValueError):
        tile_layout(groups(), [tile], pixels_per_model_unit=2)


def test_duplicate_count_and_canvas_budget():
    tile = MinimapTile(0, 0, 0, 32, 32)
    for tiles in ([], [tile, tile], [tile]*65, [tile, replace(tile, column=31)]):
        with pytest.raises(ValueError):
            tile_layout(groups(), tiles, pixels_per_model_unit=2)


def test_vertical_group_bounds_do_not_change_flat_image():
    original = groups()
    shifted = WmoGroups(original.asset_sha256, original.root_id,
                        tuple(replace(g, minimum=(*g.minimum[:2], g.minimum[2]+10000),
                                      maximum=(*g.maximum[:2], g.maximum[2]+10000))
                              for g in original.groups))
    tiles = [MinimapTile(0, 0, 0, 32, 32)]
    assert tile_layout(original, tiles, pixels_per_model_unit=2) == tile_layout(shifted, tiles, pixels_per_model_unit=2)


def test_world_xy_round_trip_under_yaw_and_translation_without_height():
    yaw = 0.38
    matrix = np.array([[cos(yaw), -sin(yaw), 0, 1234],
                       [sin(yaw), cos(yaw), 0, -456], [0, 0, 1, 30], [0, 0, 0, 1]])
    for z in (-2000, 0, 10000):
        world = matrix @ (4, -9, z, 1)
        assert model_xy_from_world_xy(world[:2], matrix.ravel()) == pytest.approx((4, -9))


def test_tilt_requires_unknown_height_and_cannot_be_silently_inverted():
    matrix = np.eye(4)
    matrix[0, 2] = 0.01
    with pytest.raises(ValueError, match="unknown height"):
        model_xy_from_world_xy((1, 2), matrix.ravel())


@pytest.mark.parametrize("xy", [(np.nan, 0), (0, np.inf), (0,), (0, 0, 0)])
def test_invalid_horizontal_input(xy):
    with pytest.raises(ValueError):
        model_xy_from_world_xy(xy, np.eye(4).ravel())


def test_bad_transform_and_layout():
    matrix = np.eye(4)
    matrix[0, 0] = 0
    with pytest.raises(ValueError):
        model_xy_from_world_xy((1, 2), matrix.ravel())
    with pytest.raises(ValueError):
        model_xy_to_composite_pixel((1, 2), {"pixels_per_model_unit": 2, "origin_xy": [np.nan, 0]})


@pytest.mark.parametrize("rotation,expected", [(0, (-8, 4)), (90, (4, 8)),
                                               (180, (8, -4)), (270, (-4, -8))])
def test_texture_moves_opposite_actor_in_fixed_view(rotation, expected):
    result = expected_texture_translation((0, 0), (4, 2), np.eye(4).ravel(),
        pixels_per_model_unit=2, rotation_degrees=rotation, scale=1)
    assert result == pytest.approx(expected)


@pytest.mark.parametrize("rotation,scale", [(np.nan, 1), (0, np.inf), (0, 0), (999, 1)])
def test_displacement_rejects_invalid_fixed_view(rotation, scale):
    with pytest.raises(ValueError):
        expected_texture_translation((0, 0), (1, 1), np.eye(4).ravel(),
            pixels_per_model_unit=2, rotation_degrees=rotation, scale=scale)
