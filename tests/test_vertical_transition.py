import copy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_spatial_sonar import record, labels, SpatialSonarObserver, sample
from perfect_assassin.adapter.vertical_transition import snapshot, compare, presentation
from perfect_assassin.adapter.sonar_details import sonar_details
from vertical_transition_observer import VerticalTransitionObserver


def next_record():
    result = record()
    result["pose_observed_monotonic_s"] = 11
    result["pose_xy_at_query"] = [1, 0]
    return result


def query(*, start, stop):
    return {"status": "OK", "sequence": 1, "requested_start": list(start),
            "requested_stop": list(stop), "resolved_start": list(start),
            "resolved_stop": list(stop), "path_stop": list(stop), "start_poly": "1",
            "stop_poly": "2", "complete": True, "search_limited": False,
            "polygon_count": 2, "point_count": 2, "funnel_length_yards": 4,
            "source": "CLIENT_NAVMESH_TOPOLOGY", "observed_actor_z": None,
            "floor_id": None, "execution_authority": False, "start_projection_yards": 0,
            "stop_projection_yards": 0, "actor_transition_confirmed": False,
            "volumetric_clearance_checked": False}


def enriched():
    r = next_record()
    r["vertical_transition"] = compare(snapshot(record()), snapshot(r), query, clock=lambda:11.2)
    return r


def test_all_pairs_preserved_and_presented_without_floor_selection():
    r = enriched()
    rows, note = presentation(r, now_s=11.3)
    assert len(rows) == 4
    assert "0 neverificate" in note
    assert "neconfirmate" in note
    assert r["vertical_candidates"]["heights"] == [120,138]
    model = sonar_details(r, labels=labels(11.3), now_s=11.3)
    assert model.rows[0][0] == "Nivel candidat 1 → 1"
    assert "etaj și deplasare reală neconfirmate" in model.notes


@pytest.mark.parametrize("mutation", [
    lambda b:b["before"]["key"].__setitem__(1,999),
    lambda b:b["before"].__setitem__("pack","b"*64),
    lambda b:b["before"].__setitem__("stamp",1),
    lambda b:b["after"]["xy"].__setitem__(0,9),
    lambda b:b.__setitem__("unqueried_count",99),
    lambda b:b.__setitem__("floor_id","crypt"),
    lambda b:b["pairs"][0].__setitem__("from_index",-1),
    lambda b:b["pairs"][1].__setitem__("to_index",0),
    lambda b:b["pairs"][0]["connection"].__setitem__("requested_start",[8,8,8]),
])
def test_mismatched_evidence_suppressed_without_suppressing_base_sonar(mutation):
    r = enriched()
    mutation(r["vertical_transition"])
    rows, note = presentation(r, now_s=11.3)
    assert not rows and "incompatibilă" in note
    model = sonar_details(r, labels=labels(11.3), now_s=11.3)
    assert model.rows and not any(row[0].startswith("Nivel candidat") for row in model.rows)


def test_previous_pose_expiry_hides_transition_even_when_current_is_fresh():
    rows, note = presentation(enriched(), now_s=13.1)
    assert not rows and "expirată" in note


def test_pair_and_elapsed_budgets_retain_all_candidates():
    before, after = snapshot(record()), snapshot(next_record())
    before["heights"] = list(range(20))
    original = copy.deepcopy(before)
    batch = compare(before, after, query, clock=lambda:11.2)
    assert len(batch["pairs"]) == 16 and batch["unqueried_count"] == 24
    assert before == original
    ticks = iter([11.1,11.1,11.7])
    batch = compare(before, after, query, clock=lambda:next(ticks))
    assert len(batch["pairs"]) == 1 and batch["unqueried_count"] == 39


def test_observer_reuses_worker_and_rebinds_session():
    worker = Mock(query=Mock(side_effect=query))
    factory = Mock(return_value=worker)
    observer = VerticalTransitionObserver(factory=factory, clock=lambda:11.2)
    args = dict(nav_root="assets", map_name="Azeroth")
    observer.observe(record(), **args)
    factory.assert_not_called()
    r = next_record()
    observer.observe(r, **args)
    assert len(r["vertical_transition"]["pairs"]) == 4
    factory.assert_called_once()
    changed = next_record()
    changed["observation_key"][1] += 1
    observer.observe(changed, **args)
    worker.close.assert_called_once()
    assert changed["vertical_transition_status"] == "WAITING"
    assert "vertical_transition" not in changed
    observer.close()


def test_worker_failure_is_optional_and_backed_off():
    factory = Mock(side_effect=RuntimeError("fixture failure"))
    observer = VerticalTransitionObserver(factory=factory, clock=lambda:11.2)
    args = dict(nav_root="assets", map_name="Azeroth")
    observer.observe(record(), **args)
    r = next_record()
    observer.observe(r, **args)
    assert r["vertical_transition_status"] == "UNAVAILABLE"
    for stamp in (11.1,11.2):
        r = next_record(); r["pose_observed_monotonic_s"] = stamp
        observer.observe(r, **args)
    factory.assert_called_once()
    assert r["observed_actor_z"] is None


def test_cc_opt_in_forwarding_requires_profile():
    from run_movement_engine_client import _control_center_live_pose_arguments
    kwargs = dict(owner_pid=1, expected_zone_index=1, map_id=0)
    assert "--spatial-sonar-continuity" not in _control_center_live_pose_arguments(**kwargs, spatial_sonar_continuity=True)
    assert "--spatial-sonar-continuity" in _control_center_live_pose_arguments(
        **kwargs, spatial_sonar_profile="pack.json", spatial_sonar_continuity=True)


def test_base_observer_calls_optional_service_only_in_background_query():
    observer = SpatialSonarObserver("unused", vertical_continuity=True)
    optional = Mock()
    observer.transition_observer = optional
    observer.binding = SimpleNamespace(pack=SimpleNamespace(
        catalog=SimpleNamespace(maps=[SimpleNamespace(map_id=0, internal_name="Azeroth")]),
        nav_root="assets", manifest={"content_sha256":"a"*64}))
    observer.service = Mock(sample=Mock(return_value=sample()))
    observer.service_map = 0
    optional.observe.assert_not_called()
    observer._query_inner(("pid:created",123,0),(0,0),10,10.1,100)
    optional.observe.assert_called_once()
    observer.close()
    observer.executor.shutdown(wait=True)
    optional.close.assert_called_once()
    observer.close()


def test_faster_publication_does_not_increase_geometry_query_rate():
    from concurrent.futures import Future
    from run_nav_viewer_live_bridge import _live_diagnostic_interval
    assert _live_diagnostic_interval(continuity_enabled=True) == .2
    assert _live_diagnostic_interval(continuity_enabled=False) == 1
    observer = SpatialSonarObserver("unused", vertical_continuity=True)
    submitted = []
    def submit(*args):
        future = Future()
        submitted.append(future)
        return future
    observer.executor.shutdown(wait=True)
    observer.executor = Mock(submit=submit)
    try:
        observer.poll(labels=labels(10),map_id=0,xy=(0,0),pose_s=10,now_s=10)
        submitted[0].set_result(record())
        for now in (10.2,10.4,10.6,10.8):
            observer.poll(labels=labels(now),map_id=0,xy=(0,0),pose_s=now,now_s=now)
        assert len(submitted) == 1
        observer.poll(labels=labels(11),map_id=0,xy=(0,0),pose_s=11,now_s=11)
        assert len(submitted) == 2
    finally:
        observer.close()
