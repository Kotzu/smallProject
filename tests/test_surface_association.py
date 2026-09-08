from copy import deepcopy

import pytest

from perfect_assassin.adapter.surface_association import associate_surfaces
from perfect_assassin.adapter.vertical_candidates import VerticalSurfaceCandidates


def hit(z=10, triangle=5, group=4):
    return {
        "world_xyz": [1, 2, z],
        "group_index": group,
        "group_id": group + 100,
        "triangle_index": triangle,
        "group_flags": 8192,
        "world_normal_z": 1.0,
    }


def associate(heights=(10, 20), hits=None, **changes):
    arguments = {
        "query_xy": (1, 2),
        "segment_start": (1, 2, 30),
        "segment_end": (1, 2, 0),
        "hits": [hit()] if hits is None else hits,
        "tolerance_yards": 0.001,
    }
    arguments.update(changes)
    return associate_surfaces(
        VerticalSurfaceCandidates(tuple(heights), heights[-1]), **arguments
    )


def test_matched_lower_and_unmatched_upper_remain_candidates():
    result = associate()
    assert [c["status"] for c in result["candidates"]] == [
        "MATCHED_GEOMETRY",
        "NO_WMO_MATCH",
    ]
    assert all(c["candidate_retained"] for c in result["candidates"])
    assert result["selected_surface_z_unchanged"] == 20
    assert result["confirmed_floor_id"] is None
    assert result["observed_actor_z"] is None
    assert result["execution_authority"] is False
    assert result["terrain_and_doodads_checked"] is False


def test_all_group_and_shared_edge_identities_survive():
    result = associate((10,), [hit(), hit(triangle=6), hit(group=7)])
    assert len(result["candidates"][0]["matches"]) == 3
    assert {h["group_index"] for h in result["candidates"][0]["matches"]} == {4, 7}


def test_tolerance_is_not_nearest_surface_fallback():
    matches = associate((10.0005,), [hit(), hit(10.1)])["candidates"][0]["matches"]
    assert len(matches) == 1
    assert matches[0]["height_delta_yards"] == pytest.approx(0.0005)
    assert associate((10.1,))["candidates"][0]["matches"] == []


def test_outside_segment_differs_from_no_hit():
    result = associate((-1, 10, 31), [])
    assert [c["status"] for c in result["candidates"]] == [
        "OUTSIDE_TESTED_SEGMENT",
        "NO_WMO_MATCH",
        "OUTSIDE_TESTED_SEGMENT",
    ]


def test_inputs_not_mutated_and_duplicate_heights_keep_indices():
    raw = [hit()]
    original = deepcopy(raw)
    result = associate((10, 10), raw)
    assert raw == original
    assert [c["candidate_index"] for c in result["candidates"]] == [0, 1]


@pytest.mark.parametrize(
    "changes",
    [
        {"query_xy": (1.01, 2)},
        {"segment_end": (1, 3, 0)},
        {"segment_end": (1, 2, 30)},
        {"segment_start": (1, 2, float("inf"))},
        {"tolerance_yards": 1},
        {"tolerance_yards": 0},
        {"tolerance_yards": True},
    ],
)
def test_invalid_or_different_query_cannot_match(changes):
    with pytest.raises(ValueError):
        associate(**changes)


@pytest.mark.parametrize(
    "field,value",
    [
        ("world_xyz", [4, 2, 10]),
        ("world_xyz", [1, 2, 100]),
        ("world_xyz", [1, 2, float("nan")]),
        ("group_id", -1),
        ("group_index", True),
        ("world_normal_z", 2),
    ],
)
def test_invalid_hit_fails_instead_of_becoming_unknown(field, value):
    invalid = hit()
    invalid[field] = value
    with pytest.raises(ValueError):
        associate(hits=[invalid])


def test_surface_and_candidate_count_budgets():
    with pytest.raises(ValueError):
        associate(heights=(10,) * 65)
    with pytest.raises(ValueError):
        associate(hits=[hit()] * 4097)


def test_reversing_segment_does_not_change_association():
    assert associate() == associate(segment_start=(1, 2, 0), segment_end=(1, 2, 30))


def test_boolean_selected_height_is_not_a_numeric_observation():
    with pytest.raises(ValueError):
        associate_surfaces(
            VerticalSurfaceCandidates((1,), True),
            query_xy=(1, 2),
            segment_start=(1, 2, 30),
            segment_end=(1, 2, 0),
            hits=[],
            tolerance_yards=0.001,
        )
