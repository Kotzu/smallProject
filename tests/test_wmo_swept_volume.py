import pytest

from test_wmo_bundle import context, build
from test_wmo_surfaces import EXPECTED, group
from perfect_assassin.adapter.wmo_surfaces import parse_wmo_group
from perfect_assassin.adapter.wmo_swept_volume import evaluate_wmo_sweep


def query(bundle, start=(1, 1, 0), stop=(1, 1, 0), **kwargs):
    return evaluate_wmo_sweep(bundle, map_id=kwargs.pop("map_id", 0), start=start,
                              stop=stop, radius_yards=.4, height_yards=2, **kwargs)


def test_verified_bundle_keeps_partial_coverage_and_support_contact(context):
    bundle, digest = build(context)
    result = query(bundle)
    assert result["bundle_sha256"] == digest
    assert result["world_pack_sha256"] == "a"*64
    assert result["uncovered_structure_ids"] == ["0:wmo:1"]
    assert result["distances"]["all"]["minimum_separation_yards"] == pytest.approx(0)
    assert result["distances"]["low_slope"]["triangle_count"] == 1
    assert result["distances"]["steep"]["minimum_separation_yards"] is None
    assert result["traversability"] == "UNKNOWN"
    assert not result["execution_authority"] and not result["terrain_and_doodads_checked"]
    assert result["confirmed_floor_id"] is None


def test_world_transform_scale_rotation_translation_and_identity(context):
    bundle, _ = build(context)
    # Synthetic fixture changes only; production bundle uses verified transforms.
    bundle.structures["0:wmo:0"]["transform_matrix"] = [
        0,0,3,3, 2,0,0,5, 0,2,0,7, 0,0,0,1]
    result = query(bundle, start=(4,6,7), stop=(4,6,7))
    steep = result["distances"]["steep"]
    assert steep["minimum_separation_yards"] == pytest.approx(.6)
    assert steep["nearest_surface"]["structure_id"] == "0:wmo:0"
    assert steep["nearest_surface"]["triangle_index"] == 0
    assert steep["nearest_surface"]["group_index"] == 0


def test_obstacle_mid_sweep_with_clear_endpoints(context):
    bundle, _ = build(context)
    bundle.models["a.wmo"] = (parse_wmo_group(group(
        vertices=((0,.17,1),(0,.19,1),(0,.18,1.02))), EXPECTED),)
    assert query(bundle, (-2,0,0),(-2,0,0))["distances"]["all"]["minimum_separation_yards"] > 0
    assert query(bundle, (2,0,0),(2,0,0))["distances"]["all"]["minimum_separation_yards"] > 0
    assert query(bundle, (-2,0,0),(2,0,0))["distances"]["all"]["minimum_separation_yards"] < 0


def test_missing_geometry_and_wrong_map_do_not_become_clear(context):
    bundle, _ = build(context)
    result = query(bundle, (100,100,0),(100,100,0))
    assert result["distances"]["all"]["minimum_separation_yards"] is None
    assert result["traversability"] == "UNKNOWN"
    with pytest.raises(ValueError):
        query(bundle, map_id=1)
    with pytest.raises(ValueError):
        query(bundle, (float('nan'),0,0))
    with pytest.raises(TypeError):
        query(object())


def test_orientation_is_not_winding_or_walkability(context):
    bundle, _ = build(context)
    bundle.models["a.wmo"] = (parse_wmo_group(group(indices=((2,1,0),)), EXPECTED),)
    result = query(bundle)
    assert result["distances"]["low_slope"]["nearest_surface"]["world_normal_z"] == -1
    assert result["confirmed_floor_id"] is None
    assert result["pose_and_body_status"] == "UNVERIFIED_HYPOTHESIS"


def test_degenerate_surface_is_retained_and_reported(context):
    bundle, _ = build(context)
    bundle.models["a.wmo"] = (parse_wmo_group(group(
        vertices=((1,0,.4),)*3), EXPECTED),)
    result = query(bundle, (0,0,0),(0,0,0))
    assert result["distances"]["degenerate"]["minimum_separation_yards"] == pytest.approx(.6)
    assert result["distances"]["degenerate"]["nearest_surface"]["world_normal_z"] is None


def test_invalid_transform_rejected_before_geometry_claim(context):
    bundle, _ = build(context)
    bundle.structures["0:wmo:0"]["transform_matrix"] = [0]*16
    with pytest.raises(ValueError):
        query(bundle)
