import sys
from concurrent.futures import Future
from math import tau
from pathlib import Path
from types import SimpleNamespace

import pytest

from perfect_assassin.adapter.spatial_sonar import (
    observation_key,
    sonar_applicable,
    sonar_display,
    sonar_record,
)
from perfect_assassin.adapter.vertical_candidates import VerticalSurfaceCandidates
from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness,
    LocalWallSegment,
    NavPoint,
    RadialClearanceProbe,
)

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "integrations/windows-input")
)
from spatial_sonar_observer import SpatialSonarObserver


def labels(now=10):
    return {
        "source": "CLIENT_ADDON_API",
        "execution_authority": False,
        "capture_binding": "pid:created",
        "session_tag": 123,
        "observed_monotonic_s": now,
    }


def sample():
    return SimpleNamespace(
        source=NavPoint(0, 0, 100),
        resolved=NavPoint(0, 0, 120),
        observed_monotonic_s=10.2,
        vertical_candidates=VerticalSurfaceCandidates((120.0, 138.0), 120.0),
        awareness=LocalStaticAwareness(
            frozenset({"wmo"}),
            12,
            False,
            tuple(RadialClearanceProbe(i * tau / 16, 12, True) for i in range(16)),
            wall_segments=(
                LocalWallSegment(NavPoint(2, -5, 120), NavPoint(2, 5, 120), 99),
            ),
        ),
    )


def record():
    return sonar_record(
        sample(),
        key=("pid:created", 123, 0),
        pack_sha256="a" * 64,
        pose_xy=(0, 0),
        pose_observed_s=10,
        requested_s=10.1,
    )


def test_query_distance_is_recomputed_and_never_certifies_actor_floor():
    r = record()
    assert r["nearest_boundaries_at_query"][0]["distance_yards"] == 2
    assert r["query_origin_xyz"][2] == 100 and r["resolved_query_xyz"][2] == 120
    assert (
        r["observed_actor_z"] is r["floor_id"] is r["metric_pose_error_yards"] is None
    )
    assert r["free_space_certified"] is r["execution_authority"] is False
    assert "2 suprafețe candidate" in sonar_display(r, labels=labels(), now_s=10.3)


@pytest.mark.parametrize(
    "key,xy,now",
    [
        (("other", 123, 0), (0, 0), 10.3),
        (("pid:created", 124, 0), (0, 0), 10.3),
        (("pid:created", 123, 1), (0, 0), 10.3),
        (("pid:created", 123, 0), (1, 0), 10.3),
        (("pid:created", 123, 0), (0, 0), 14),
        (("pid:created", 123, 0), (0, 0), 9),
    ],
)
def test_foreign_moved_future_and_expired_geometry_is_not_current(key, xy, now):
    assert not sonar_applicable(record(), key=key, xy=xy, now_s=now)


def test_api_clock_or_provenance_cannot_be_faked_by_geometry():
    assert observation_key(labels(1), 0, now_s=10) is None
    assert (
        observation_key({**labels(), "source": "server_ground_truth"}, 0, now_s=10)
        is None
    )


def test_late_future_from_previous_session_is_discarded_without_another_inflight_job():
    observer = SpatialSonarObserver("not-opened")
    observer.future = Future()
    observer.next_query_s = 100
    try:
        assert (
            observer.poll(labels=labels(), map_id=0, xy=(0, 0), pose_s=10, now_s=10)
            is None
        )
        observer.future.set_result(record())
        assert (
            observer.poll(
                labels={**labels(), "session_tag": 456},
                map_id=0,
                xy=(0, 0),
                pose_s=10,
                now_s=10.4,
            )
            is None
        )
        assert observer.latest["pose_observed_monotonic_s"] == 10
    finally:
        observer.close()


def test_timed_out_native_pipe_is_closed(monkeypatch):
    from threading import Event
    from unittest.mock import Mock

    from persistent_navmesh_awareness import PersistentNavmeshAwarenessService

    release = Event()
    service = object.__new__(PersistentNavmeshAwarenessService)
    service._protocol_timeout_s = 0.01
    service._process = SimpleNamespace(
        stdout=SimpleNamespace(readline=lambda: release.wait(1))
    )
    service.close = Mock(side_effect=release.set)
    with pytest.raises(RuntimeError, match="timed out"):
        service._readline()
    service.close.assert_called_once()


def test_old_pose_with_fresh_labels_does_not_start_geometry_job():
    observer = SpatialSonarObserver("not-opened")
    try:
        assert (
            observer.poll(labels=labels(), map_id=0, xy=(0, 0), pose_s=1, now_s=10)
            is None
        )
        assert observer.future is None
    finally:
        observer.close()


@pytest.mark.parametrize("altitude", [0.0, 2500.0, -50.0])
def test_open_overhead_is_not_infinite_height_or_an_altitude_based_floor(altitude):
    from dataclasses import replace

    s = sample()
    s.resolved = NavPoint(0, 0, altitude)
    s.awareness = replace(s.awareness, overhead_clear=True)
    r = sonar_record(
        s,
        key=("pid:created", 123, 0),
        pack_sha256="a" * 64,
        pose_xy=(0, 0),
        pose_observed_s=10,
        requested_s=10.1,
    )
    assert r["floor_id"] is None
    assert r["ceiling_probe"]["ceiling_height_yards"] is None
    assert r["ceiling_probe"]["status"] == "NO_HIT_IN_TESTED_SEGMENT"
    assert r["ceiling_probe"]["infinite_clearance"] is False
    assert r["ceiling_probe"]["open_world_confirmed"] is False
    text = sonar_display(r, labels=labels(), now_s=10.3)
    assert f"altitudine estimată {altitude:.2f} yd" in text
    assert "Etaj neconfirmat" in text
    assert "Plafon: nedetectat în segmentul testat" in text


def test_single_candidate_and_overhead_hit_do_not_claim_a_floor_or_ceiling_height():
    r = record()
    r["vertical_candidates"]["heights"] = [120.0]
    text = sonar_display(r, labels=labels(), now_s=10.3)
    assert "1 suprafață candidată" in text
    assert "Etaj neconfirmat" in text
    assert "Obstacol deasupra în segmentul testat · distanță necunoscută" in text


def test_optional_bundle_failure_is_attempted_once(monkeypatch):
    from unittest.mock import Mock

    loader = Mock(side_effect=ValueError("invalid index"))
    monkeypatch.setattr(
        "perfect_assassin.movement.world_structure_index.load_world_structure_index",
        loader,
    )
    observer = SpatialSonarObserver(
        "unused",
        wmo_bundle_spec={
            "index": "missing",
            "directory": "missing",
            "sha256": "a" * 64,
        },
    )
    observer.binding = SimpleNamespace(pack=object())
    try:
        assert observer._wmo_association(sample(), 0) is None
        assert observer._wmo_association(sample(), 0) is None
        loader.assert_called_once()
        assert observer.wmo_error == "ValueError: invalid index"
    finally:
        observer.close()


@pytest.mark.parametrize(
    "enabled,failed", [(False, False), (True, False), (True, True)]
)
def test_optional_bundle_preserves_base_sonar_and_uses_original_column(enabled, failed):
    from unittest.mock import Mock

    observer = SpatialSonarObserver("unused", wmo_bundle_spec={} if enabled else None)
    s = sample()
    s.resolved = NavPoint(0.2, 0.2, 120)
    observer.binding = SimpleNamespace(
        pack=SimpleNamespace(
            catalog=SimpleNamespace(maps=[SimpleNamespace(map_id=0)]),
            manifest={"content_sha256": "a" * 64},
        )
    )
    observer.service = Mock()
    observer.service.sample.return_value = s
    observer.service_map = 0
    observer.wmo_load_attempted = True
    evidence = {"confirmed_floor_id": None, "execution_authority": False}
    query = Mock(
        return_value=evidence, side_effect=ValueError("bad map") if failed else None
    )
    observer.wmo_bundle = SimpleNamespace(query=query)
    try:
        r = observer._query_inner(("pid:created", 123, 0), (0, 0), 10, 10.1, 100)
        assert r["floor_id"] is r["observed_actor_z"] is None
        assert r["execution_authority"] is False
        if not enabled:
            assert "wmo_surface_association" not in r
            query.assert_not_called()
        else:
            query.assert_called_once_with(
                map_id=0, xy=(0, 0), candidates=s.vertical_candidates
            )
            assert r["wmo_surface_association"] == (None if failed else evidence)
            assert r["wmo_surface_error"] == ("ValueError: bad map" if failed else None)
    finally:
        observer.close()


@pytest.mark.parametrize("session,now", [(456, 10.4), (123, 14.0)])
def test_bundle_evidence_cannot_outlive_outer_session_or_pose(session, now):
    observer = SpatialSonarObserver("unused")
    observer.latest = {**record(), "wmo_surface_association": {"test": "evidence"}}
    observer.next_query_s = 100
    try:
        assert (
            observer.poll(
                labels={**labels(now), "session_tag": session},
                map_id=0,
                xy=(0, 0),
                pose_s=now,
                now_s=now,
            )
            is None
        )
    finally:
        observer.close()


def test_bundle_config_file_is_loaded_only_on_background_query(tmp_path, monkeypatch):
    import json
    from unittest.mock import Mock

    config = tmp_path / "bundle.json"
    config.write_text(
        json.dumps(
            {
                "index": "missing-index",
                "directory": "missing-bundle",
                "sha256": "a" * 64,
            }
        )
    )
    loader = Mock(side_effect=ValueError("test index failure"))
    monkeypatch.setattr(
        "perfect_assassin.movement.world_structure_index.load_world_structure_index",
        loader,
    )
    observer = SpatialSonarObserver("unused", wmo_bundle_spec=config)
    try:
        loader.assert_not_called()
        assert not observer.wmo_load_attempted
        observer.binding = SimpleNamespace(pack=object())
        assert observer._wmo_association(sample(), 0) is None
        assert loader.call_args.args[0].is_absolute()
        assert observer.wmo_error == "ValueError: test index failure"
    finally:
        observer.close()


def test_cc_passes_opt_in_configuration_only_with_sonar_profile():
    from run_movement_engine_client import _control_center_live_pose_arguments

    kwargs = {"owner_pid": 1, "expected_zone_index": 1, "map_id": 0}
    assert "--spatial-sonar-wmo-config" not in _control_center_live_pose_arguments(
        **kwargs
    )
    assert "--spatial-sonar-wmo-config" not in _control_center_live_pose_arguments(
        **kwargs, spatial_sonar_wmo_config=Path("bundle.json")
    )
    args = _control_center_live_pose_arguments(
        **kwargs,
        spatial_sonar_profile=Path("pack.json"),
        spatial_sonar_wmo_config=Path("bundle.json"),
    )
    assert args[args.index("--spatial-sonar-wmo-config") + 1] == "bundle.json"
