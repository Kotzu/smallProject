import sys
from copy import deepcopy
from math import tau
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "integrations/windows-input")
)

from persistent_navmesh_awareness import PersistentNavmeshAwarenessService
from test_spatial_sonar import labels, record, sample

from perfect_assassin.adapter.height_scan import parse_height_scan
from perfect_assassin.adapter.sonar_details import sonar_details
from perfect_assassin.adapter.spatial_sonar import sonar_record


def scan():
    return {
        "schema_version": 1,
        "source": "CLIENT_ASSET_LINE_OF_SIGHT",
        "exhaustive": False,
        "origin_xyz": [0, 0, 120],
        "radius_yards": 12,
        "binary_search_iterations": 7,
        "rays": [
            {
                "bearing_rad": tau * i / 16,
                "height_offset_yards": h,
                "clear_prefix_yards": 12,
                "blocked_by_yards": None,
            }
            for h in (0.25, 0.60, 1.20, 1.80)
            for i in range(16)
        ],
    }


def test_roundtrip_is_immutable_preserves_grid_and_never_certifies_actor():
    raw = scan()
    before = deepcopy(raw)
    parsed = parse_height_scan(raw, expected_origin=(0, 0, 120))
    assert parsed.to_record() == before
    raw["rays"][0]["clear_prefix_yards"] = 1
    assert parsed.to_record() == before
    s = sample()
    s.height_scan = parsed
    r = sonar_record(
        s,
        key=("pid:created", 123, 0),
        pack_sha256="a" * 64,
        pose_xy=(0, 0),
        pose_observed_s=10,
        requested_s=10.1,
    )
    assert r["height_scan"] == before
    assert r["free_space_certified"] is r["execution_authority"] is False
    assert r["observed_actor_z"] is r["floor_id"] is None
    assert parse_height_scan(None, expected_origin=(0, 0, 120)) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("source", "SERVER"),
        ("exhaustive", True),
        ("radius_yards", float("inf")),
        ("radius_yards", 30),
        ("binary_search_iterations", 1000),
        ("origin_xyz", [1, 0, 120]),
        ("origin_xyz", [0, 0, float("nan")]),
        ("rays", []),
        ("rays", [{}] * 65),
    ],
)
def test_wrong_provenance_grid_origin_or_bounds_rejected(field, value):
    raw = {**scan(), field: value}
    with pytest.raises(ValueError):
        parse_height_scan(raw, expected_origin=(0, 0, 120))


@pytest.mark.parametrize(
    "field,value",
    [
        ("bearing_rad", 1),
        ("bearing_rad", True),
        ("height_offset_yards", 0.4),
        ("clear_prefix_yards", -1),
        ("clear_prefix_yards", 13),
        ("clear_prefix_yards", float("nan")),
        ("blocked_by_yards", 12),
        ("blocked_by_yards", float("inf")),
    ],
)
def test_malformed_ray_rejected(field, value):
    raw = scan()
    raw["rays"][0][field] = value
    with pytest.raises(ValueError):
        parse_height_scan(raw, expected_origin=(0, 0, 120))


def test_low_obstacle_bracket_remains_a_conditional_display_and_expires():
    raw = scan()
    raw["rays"][0].update(clear_prefix_yards=3.375, blocked_by_yards=3.46875)
    raw["rays"][16].update(clear_prefix_yards=3.375, blocked_by_yards=3.46875)
    r = {**record(), "height_scan": raw}
    model = sonar_details(r, labels=labels(), now_s=10.5)
    assert len(model.rows) == 81
    assert any("Z+0.25" in row[0] and "3.38 și 3.47" in row[2] for row in model.rows)
    assert any("Z+1.20" in row[0] and "Nimic detectat" in row[2] for row in model.rows)
    assert "spațiu neverificat" in model.notes
    assert not sonar_details(r, labels=labels(), now_s=14).rows
    raw["rays"][0]["blocked_by_yards"] = (
        4  # bracket too large for the reported protocol
    )
    assert not sonar_details(r, labels=labels(), now_s=10.5).rows


def test_requested_scan_cannot_silently_fall_back_to_a_legacy_response():
    service = object.__new__(PersistentNavmeshAwarenessService)
    service._spatial_scan = True
    service._sequence = 0
    service._process = SimpleNamespace(poll=lambda: None, stdin=Mock(), stdout=Mock())
    service._readline = Mock(return_value='{"status":"OK"}')
    with pytest.raises(RuntimeError, match="height scan is missing"):
        service.sample(0, 0, 120)
