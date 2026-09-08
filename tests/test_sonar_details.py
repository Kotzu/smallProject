import sys
from dataclasses import replace
from math import pi
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations/windows-input"))

from location_label_reader import LocationLabelReader
from sonar_panel import SonarPanel
from test_spatial_sonar import labels, record, sample

from perfect_assassin.adapter.sonar_details import (
    SonarDetails,
    sonar_details,
    world_direction,
)
from perfect_assassin.adapter.spatial_sonar import sonar_record
from perfect_assassin.movement.client_navmesh import (
    LocalTopologicalEgressPortal,
    NavPoint,
    RadialClearanceProbe,
)


@pytest.mark.parametrize(
    "bearing,direction",
    [
        (0, "N"),
        (45, "NV"),
        (90, "V"),
        (135, "SV"),
        (180, "S"),
        (225, "SE"),
        (270, "E"),
        (315, "NE"),
        (-90, "E"),
        (360, "N"),
    ],
)
def test_world_directions_are_not_screen_or_facing_directions(bearing, direction):
    assert world_direction(bearing).split(" · ")[0] == direction


def test_cardinals_match_existing_client_map_transform():
    from perfect_assassin.movement.zone_transform import tbc243_zone_transform

    transform = tbc243_zone_transform(2, 25)
    x, y = transform.world_from_normalized(0.5, 0.5)
    assert transform.normalized_from_world(x + 1, y)[1] < 0.5  # +X north/up
    assert transform.normalized_from_world(x, y + 1)[0] < 0.5  # +Y west/left


def test_radial_clearance_preserves_measurement_scope_and_not_exact_hit():
    s = sample()
    probes = list(s.awareness.radial_probes)
    probes[4] = RadialClearanceProbe(pi / 2, 2.25, False)
    s.awareness = replace(s.awareness, radial_probes=tuple(probes))
    r = sonar_record(
        s,
        key=("pid:created", 123, 0),
        pack_sha256="a" * 64,
        pose_xy=(0, 0),
        pose_observed_s=10,
        requested_s=10.1,
    )
    assert r["radial_probes_at_query"][4]["hit_distance_yards"] is None
    model = sonar_details(r, labels=labels(), now_s=10.5)
    assert len(model.rows) == 17
    blocked = next(row for row in model.rows if row[0] == "Sondă 5")
    assert blocked[1] == "V · 90.0°"
    assert "2.25 / 12.00 yd" in blocked[2]
    assert "distanță exactă necunoscută" in blocked[3]
    assert "capăt navmesh neconfirmat" in blocked[3]
    assert "Nimic detectat până la limita sondei" in model.rows[1][3]
    assert "nu de la un XYZ confirmat" in model.notes
    assert "volumul corpului" in model.notes


def test_opening_shows_width_route_and_unknown_semantics():
    s = sample()
    s.awareness = replace(
        s.awareness,
        egress_portals=(
            LocalTopologicalEgressPortal(
                NavPoint(3, -1, 120),
                NavPoint(3, 1, 120),
                2,
                99,
                4,
                False,
                True,
                frozenset({"wmo"}),
                frozenset({"ground"}),
            ),
        ),
        egress_portals_truncated=True,
    )
    r = sonar_record(
        s,
        key=("pid:created", 123, 0),
        pack_sha256="a" * 64,
        pose_xy=(0, 0),
        pose_observed_s=10,
        requested_s=10.1,
    )
    model = sonar_details(r, labels=labels(), now_s=10.5)
    opening = next(row for row in model.rows if row[0].startswith("Deschidere"))
    assert opening[1] == "N · 0.0°"
    assert opening[2] == "3.00 yd · lățime 2.00 yd"
    assert "Rută geometrică 4.00 yd" in opening[3]
    assert "destinație necunoscute" in opening[3]
    assert "nu este exhaustivă" in model.notes


@pytest.mark.parametrize(
    "mutation",
    [
        {"observation_key": ["other", 123, 0]},
        {"pose_observed_monotonic_s": 1},
        {"execution_authority": True},
        {"distance_scope": "ACTOR"},
        {"resolved_query_xyz": [0, 0, float("inf")]},
        {"nearest_boundaries_at_query": [None]},
        {"openings_at_query": [None]},
        {"radial_probes_at_query": [None]},
        {"radial_probes_at_query": [{}] * 65},
        {"probe_radius_yards": -1},
        {"probe_radius_yards": float("nan")},
    ],
)
def test_invalid_or_foreign_data_removes_distances(mutation):
    r = {**record(), **mutation}
    model = sonar_details(r, labels=labels(), now_s=10.5)
    assert model.rows == ()
    assert "indisponibil" in model.status


def test_legacy_report_keeps_boundaries_but_reports_missing_radials():
    r = record()
    del r["radial_probes_at_query"]
    model = sonar_details(r, labels=labels(), now_s=10.5)
    assert len(model.rows) == 1
    assert "Detaliile sondelor nu sunt disponibile" in model.notes


def test_reader_uses_receipt_identity_gate_without_starting_io():
    from test_location_hud import packet

    from perfect_assassin.adapter.location_hud import LocationStream

    stream = LocationStream("pid:created")
    stream.observe(packet(), 9.9)
    r = stream.observe(packet(millis=1200), 10)
    geometry = record()
    geometry["observation_key"][1] = r["session_tag"]
    r["spatial_sonar"] = geometry
    reader = LocationLabelReader("unused", "unused", 1)
    reader.record, reader.binding = r, "pid:created"
    assert reader.details(10.5).rows
    assert not reader.inflight
    reader.binding = "other"
    assert not reader.details(10.5).rows
    reader.binding = "pid:created"
    assert not reader.details(14).rows


def test_table_does_not_rebuild_unchanged_rows_and_clears_expired_data():
    panel = SimpleNamespace(
        status=Mock(), notes=Mock(), table=Mock(), previous_rows=None
    )
    panel.table.get_children.return_value = ("old",)
    current = SonarDetails("current", (("wall", "N", "2 yd", "conditional"),))
    SonarPanel.update_details(panel, current)
    SonarPanel.update_details(panel, replace(current, status="age changed"))
    assert panel.table.insert.call_count == 1
    assert panel.table.delete.call_count == 1
    SonarPanel.update_details(panel, SonarDetails("expired"))
    assert panel.previous_rows == ()
    assert panel.table.delete.call_count == 2
