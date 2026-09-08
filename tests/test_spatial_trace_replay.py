from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from perfect_assassin.adapter.spatial_trace import replay_spatial_evidence


def geometry(applied=10.0):
    return {
        "kind": "LIVE_LOCAL_AWARENESS_APPLIED",
        "applied_to_pose_observed_monotonic_s": applied,
        "source_world": [1, 2, 3],
        "resolved_world": [1, 2, 4],
        "boundary_evidence": {
            "source": "client_asset_navmesh_awareness",
            "execution_authority": False,
            "physical_contact_proven": False,
            "observed_monotonic_s": 9.9,
            "component_truncated": False,
            "wall_segments_truncated": True,
            "wall_segments": [
                {"left": [0, 0, 0], "right": [1, 1, 1], "distance_yards": 99}
            ],
            "radial_probes": [
                {"bearing_rad": 0, "clearance_yards": 12, "navmesh_reachable": True}
            ],
        },
    }


def frame(index=1, time=10.1):
    return {
        "kind": "CONTINUOUS_FRAME",
        "frame_index": index,
        "decision_metrics_reference": "decision_observation",
        "decision_observation": {
            "position_source": "client_visible_pose",
            "execution_authority": False,
            "observed_monotonic_s": time,
            "world_x": 1,
            "world_y": 2,
        },
        "observed_monotonic_s": time + 0.1,
        "world_x": 999,
        "world_y": 999,
        "projected_z_source": "decision_corridor_projection_not_observed_z",
        "projected_z_world": 7,
    }


def trace(actions=None):
    return {
        "record_type": "navmesh_roaming_result",
        "schema_version": "0.1",
        "run_id": "fixture-run",
        "map": "FixtureMap",
        "world_pack_content_sha256": "a" * 64,
        "actions": [geometry(), frame()] if actions is None else actions,
    }


def replay(record):
    return replay_spatial_evidence(record, trace_sha256="b" * 64)


def test_partial_xy_not_projected_xyz_and_no_input_mutation():
    record = trace()
    before = deepcopy(record)
    report = replay(record)
    row = report["frames"][0]
    assert row["recorded_client_xy"] == [1, 2]
    assert row["observed_z"] is None
    assert row["corridor_projected_z"] == 7
    assert row["floor_id"] is None
    assert row["horizontal_error_bound_yards"] is None
    assert row["current_wall_distances"] is None
    assert row["geometry"]["set_truncated"] is True
    assert row["query_origin_offset_xy_yards"] == 0
    assert row["execution_authority"] is False
    assert report["complete_spatial_pose_count"] == 0
    assert record == before


@pytest.mark.parametrize(
    "actions",
    [
        [frame(), geometry()],
        [geometry(applied=10.2), frame()],
    ],
)
def test_future_or_later_record_geometry_never_leaks_back(actions):
    row = replay(trace(actions))["frames"][0]
    assert row["geometry"] is None
    assert "MISSING_PRIOR_APPLIED_GEOMETRY" in row["reasons"]


def test_pending_query_does_not_replace_prior_applied_geometry():
    report = replay(trace([geometry(), geometry(applied=10.3), frame()]))
    assert report["frames"][0]["geometry"]["evidence_ref"].endswith("/actions/0")


def test_async_geometry_newer_than_pose_is_explicit_not_negative_freshness():
    query = geometry()
    query["boundary_evidence"]["observed_monotonic_s"] = 10.15
    row = replay(trace([query, frame()]))["frames"][0]
    assert row["geometry"] is not None
    assert "GEOMETRY_OBSERVED_AFTER_POSE" in row["reasons"]
    assert row["geometry_age_relative_to_pose_s"] < 0
    assert row["current_wall_distances"] is None


def test_stale_query_and_moved_origin_are_explicit():
    decision = frame(time=12)
    decision["decision_observation"]["world_x"] = 5
    row = replay(trace([geometry(), decision]))["frames"][0]
    assert {"STALE_LOCAL_QUERY", "QUERY_ORIGIN_MOVED_XY"} <= set(row["reasons"])


@pytest.mark.parametrize(
    "field,value",
    [("world_x", float("nan")), ("world_y", True), ("observed_monotonic_s", -1)],
)
def test_invalid_pose_values_rejected(field, value):
    record = trace()
    record["actions"][1]["decision_observation"][field] = value
    with pytest.raises(ValueError):
        replay(record)


@pytest.mark.parametrize(
    "position_source", ["server_ground_truth", "lab_database", "unknown"]
)
def test_nonclient_pose_is_not_promoted(position_source):
    record = trace()
    record["actions"][1]["decision_observation"]["position_source"] = position_source
    with pytest.raises(ValueError):
        replay(record)


def test_extra_optimistic_fields_are_not_accepted_as_calibration():
    record = trace()
    record["actions"][1]["decision_observation"].update(
        world_z=7, floor_id="ground", confidence=1, horizontal_error_bound_yards=0
    )
    row = replay(record)["frames"][0]
    assert row["observed_z"] is row["floor_id"] is row["pose_confidence"] is None


@pytest.mark.parametrize(
    "actions", [[frame(), frame()], [frame(time=12), frame(index=2, time=11)], []]
)
def test_duplicate_backwards_or_empty_frames_rejected(actions):
    with pytest.raises(ValueError):
        replay(trace(actions))


def test_geometry_limits_and_flags_are_checked():
    for field, value in [
        ("wall_segments", [{}] * 129),
        ("component_truncated", "false"),
        ("source", "server_ground_truth"),
        ("execution_authority", True),
    ]:
        record = trace()
        record["actions"][0]["boundary_evidence"][field] = value
        with pytest.raises(ValueError):
            replay(record)


def test_unknown_height_source_is_not_observed_height():
    record = trace()
    record["actions"][1]["projected_z_source"] = "unknown"
    row = replay(record)["frames"][0]
    assert row["observed_z"] is row["corridor_projected_z"] is None


def test_evidence_identity_and_schema_required():
    for key, value in [
        ("world_pack_content_sha256", "no-hash"),
        ("run_id", ""),
        ("schema_version", "9"),
        ("map", None),
    ]:
        with pytest.raises(ValueError):
            replay({**trace(), key: value})


def vertical_selection():
    return {
        "kind": "INITIAL_VERTICAL_LAYER_SELECTED",
        "execution_authority": False,
        "seed_z": 100,
        "selected_z": 120,
        "candidate_count": 2,
        "candidates": [
            {"resolved_z": 120, "complete": True},
            {"resolved_z": 138, "complete": True},
        ],
        "selection_policy": "fixture_planner_choice",
    }


def test_multiple_complete_routes_do_not_confirm_actor_floor():
    record = trace([vertical_selection(), geometry(), frame()])
    before = deepcopy(record)
    result = replay(record)
    selection = result["initial_vertical_selections"][0]
    assert selection["complete_route_count"] == 2
    assert selection["nearest_alternative_gap_yards"] == 18
    assert selection["observed_actor_z"] is selection["confirmed_floor_id"] is None
    assert selection["candidate_set_exhaustive"] is False
    assert result["recorded_multiheight_selection_count"] == 1
    row = result["frames"][0]
    assert row["prior_initial_vertical_selection_ref"] == selection["evidence_ref"]
    assert row["floor_id"] is row["observed_z"] is None
    assert record == before


def test_later_vertical_choice_never_leaks_into_earlier_frame():
    result = replay(trace([frame(), vertical_selection(), frame(2, 11)]))
    assert result["frames"][0]["prior_initial_vertical_selection_ref"] is None
    assert result["frames"][1]["prior_initial_vertical_selection_ref"] is not None


@pytest.mark.parametrize(
    "key,value",
    [
        ("candidate_count", True),
        ("candidate_count", 3),
        ("selected_z", 999),
        ("seed_z", float("nan")),
        ("execution_authority", True),
    ],
)
def test_invalid_vertical_selection_is_rejected(key, value):
    selection = vertical_selection()
    selection[key] = value
    with pytest.raises(ValueError):
        replay(trace([selection, frame()]))


def test_single_height_is_not_a_proof_of_floor_or_exhaustive_geometry():
    selection = vertical_selection()
    selection["candidate_count"] = 1
    selection["candidates"] = selection["candidates"][:1]
    result = replay(trace([selection, frame()]))
    assert result["recorded_multiheight_selection_count"] == 0
    assert result["initial_vertical_selections"][0]["confirmed_floor_id"] is None
    assert result["complete_spatial_pose_count"] == 0


def test_cli_handles_windows_encoding_and_never_overwrites_evidence(tmp_path):
    source, output = tmp_path / "trace.json", tmp_path / "report.json"
    source.write_text(json.dumps(trace()), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts/replay_spatial_context.py"
    command = [sys.executable, str(script), str(source), "--output", str(output)]
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    first = subprocess.run(command, capture_output=True, env=env, check=False)
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["frame_count"] == 1
    before = output.read_bytes()
    second = subprocess.run(command, capture_output=True, env=env, check=False)
    assert second.returncode != 0
    assert output.read_bytes() == before
