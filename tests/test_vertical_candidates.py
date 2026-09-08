from copy import deepcopy

import pytest

from perfect_assassin.adapter.vertical_candidates import parse_vertical_candidates


def record():
    return {
        "schema_version": 1,
        "source": "CLIENT_ASSET_HEIGHT_QUERY",
        "exhaustive": False,
        "selected_surface_z": 120.5,
        "heights": [120.5, 138.5],
    }


def test_alternatives_are_preserved_without_floor_claim_or_input_mutation():
    raw = record()
    before = deepcopy(raw)
    parsed = parse_vertical_candidates(raw)
    assert parsed.ambiguous
    result = parsed.to_record()
    assert result["heights"] == [120.5, 138.5]
    assert result["observed_actor_z"] is result["confirmed_floor_id"] is None
    assert result["execution_authority"] is result["exhaustive"] is False
    assert raw == before


def test_old_worker_is_unknown_and_single_candidate_is_still_not_confirmed():
    assert parse_vertical_candidates(None) is None
    single = record()
    single["heights"] = [120.5]
    parsed = parse_vertical_candidates(single)
    assert not parsed.ambiguous
    assert parsed.to_record()["confirmed_floor_id"] is None


@pytest.mark.parametrize(
    "key,value",
    [
        ("source", "server_ground_truth"),
        ("schema_version", True),
        ("schema_version", 2),
        ("exhaustive", True),
        ("heights", []),
        ("heights", [120.5] * 65),
        ("heights", [float("nan")]),
        ("heights", [True]),
        ("selected_surface_z", 123),
    ],
)
def test_malformed_or_wrong_source_rejected(key, value):
    raw = record()
    raw[key] = value
    with pytest.raises(ValueError):
        parse_vertical_candidates(raw)
