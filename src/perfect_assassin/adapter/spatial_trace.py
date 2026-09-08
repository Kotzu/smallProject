"""Read-only v0.1 movement-trace adapter; preserve partial evidence as partial.

Recorded XY plus corridor Z cannot construct SpatialPoseEvidence. This adapter
reports the missing prerequisites instead of inventing a floor or metric error.
It is an offline diagnostic, not authenticated Champion input or a live sensor.
"""

from __future__ import annotations

from collections import Counter
from math import hypot, isfinite

from perfect_assassin.movement.spatial_context import SpatialContextPolicy


def _number(value, *, nonnegative=False):
    if type(value) not in (float, int) or not isfinite(value):
        raise ValueError("nonfinite or nonnumeric trace value")
    if nonnegative and value < 0:
        raise ValueError("negative trace time/distance")
    return value


def _point(value):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("expected recorded XYZ triple")
    return [_number(coordinate) for coordinate in value]


def _hash(value):
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("missing evidence hash")
    if any(char not in "0123456789abcdefABCDEF" for char in value):
        raise ValueError("invalid evidence hash")
    return value.lower()


def _geometry(action, ref):
    boundary = action["boundary_evidence"]
    if (
        boundary["source"] != "client_asset_navmesh_awareness"
        or boundary["execution_authority"] is not False
        or boundary["physical_contact_proven"] is not False
    ):
        raise ValueError("unsupported geometry provenance/authority")
    walls, rays = boundary["wall_segments"], boundary["radial_probes"]
    if not isinstance(walls, list) or not isinstance(rays, list):
        raise TypeError("invalid geometry collections")
    if len(walls) > 128 or len(rays) > 64:
        raise ValueError("geometry exceeds trace bounds")
    for wall in walls:
        _point(wall["left"])
        _point(wall["right"])
        _number(wall["distance_yards"], nonnegative=True)
    for ray in rays:
        _number(ray["bearing_rad"])
        _number(ray["clearance_yards"], nonnegative=True)
        if type(ray["navmesh_reachable"]) is not bool:
            raise ValueError("invalid reachability flag")
    for key in ("component_truncated", "wall_segments_truncated"):
        if type(boundary[key]) is not bool:
            raise ValueError("invalid truncation flag")
    observed = _number(boundary["observed_monotonic_s"], nonnegative=True)
    applied = _number(action["applied_to_pose_observed_monotonic_s"], nonnegative=True)
    # 'applied_to_pose' is the pose timestamp, not wall-clock application time.
    # An asynchronous geometry result can legitimately be newer than that pose.
    return {
        "evidence_ref": ref,
        "source": boundary["source"],
        "observed_monotonic_s": observed,
        "applied_to_pose_observed_monotonic_s": applied,
        "query_origin": _point(action["source_world"]),
        "resolved_world": _point(action["resolved_world"]),
        "wall_count": len(walls),
        "radial_count": len(rays),
        "set_truncated": boundary["component_truncated"]
        or boundary["wall_segments_truncated"],
    }


def _initial_vertical_selection(action, ref):
    """A planner choice is an initial hypothesis, never a measured actor floor."""
    if action.get("execution_authority") is not False:
        raise ValueError("invalid vertical selection authority")
    candidates = action.get("candidates")
    count = action.get("candidate_count")
    if (
        not isinstance(candidates, list)
        or type(count) is not int
        or not 1 <= count <= 64
        or count != len(candidates)
    ):
        raise ValueError("invalid vertical candidates")
    heights = []
    for candidate in candidates:
        heights.append(_number(candidate["resolved_z"]))
        if type(candidate.get("complete")) is not bool:
            raise ValueError("invalid vertical route completeness")
    selected = _number(action["selected_z"])
    if selected not in heights:
        raise ValueError("selected height absent from candidates")
    alternatives = sorted({height for height in heights if height != selected})
    policy = action.get("selection_policy")
    if not isinstance(policy, str) or not policy or len(policy) > 512:
        raise ValueError("invalid vertical selection policy")
    return {
        "evidence_ref": ref,
        "source": "RECORDED_NAVMESH_PLANNER_SELECTION",
        "scope": "INITIAL_HYPOTHESIS_NOT_CURRENT_FLOOR",
        "seed_z": _number(action["seed_z"]),
        "selected_z": selected,
        "candidate_heights": heights,
        "candidate_count": count,
        "complete_route_count": sum(c["complete"] for c in candidates),
        "alternative_heights": alternatives,
        "nearest_alternative_gap_yards": (
            min(abs(height - selected) for height in alternatives)
            if alternatives
            else None
        ),
        "selection_policy": policy,
        "observed_actor_z": None,
        "confirmed_floor_id": None,
        "candidate_set_exhaustive": False,
        "execution_authority": False,
    }


def replay_spatial_evidence(record, *, trace_sha256, policy=None):
    """Associate only earlier, already-applied geometry in one recorded run.

    No calls to the complete-XYZ evaluator are made for this XY-only format.
    Unknown fields cannot be promoted by adding optimistic ad-hoc labels.
    """
    digest = _hash(trace_sha256)
    if (
        record.get("record_type") != "navmesh_roaming_result"
        or record.get("schema_version") != "0.1"
    ):
        raise ValueError("unsupported movement trace")
    run_id, map_name = record["run_id"], record["map"]
    if (
        not isinstance(run_id, str)
        or not run_id
        or not isinstance(map_name, str)
        or not map_name
    ):
        raise ValueError("missing run/map identity")
    pack = _hash(record["world_pack_content_sha256"])
    actions = record["actions"]
    if not isinstance(actions, list) or len(actions) > 50000:
        raise ValueError("invalid or oversized action sequence")
    policy = policy or SpatialContextPolicy()
    geometries, frames, vertical_selections = [], [], []
    previous_index, previous_time = 0, -1
    reasons_count = Counter()
    for index, action in enumerate(actions):
        ref = f"sha256:{digest}#/actions/{index}"
        if action["kind"] == "INITIAL_VERTICAL_LAYER_SELECTED":
            vertical_selections.append(_initial_vertical_selection(action, ref))
            continue
        if action["kind"] == "LIVE_LOCAL_AWARENESS_APPLIED":
            geometries.append(_geometry(action, ref))
            continue
        if action["kind"] != "CONTINUOUS_FRAME":
            continue
        frame_index = action["frame_index"]
        if type(frame_index) is not int or frame_index <= previous_index:
            raise ValueError("duplicate or out-of-order decision frame")
        previous_index = frame_index
        if action.get("decision_metrics_reference") != "decision_observation":
            raise ValueError("decision observation not explicitly bound")
        pose = action["decision_observation"]
        if (
            pose.get("position_source") != "client_visible_pose"
            or pose.get("execution_authority") is not False
        ):
            raise ValueError("unsupported pose provenance/authority")
        observed = _number(pose["observed_monotonic_s"], nonnegative=True)
        post_time = _number(action["observed_monotonic_s"], nonnegative=True)
        if observed < previous_time or post_time < observed:
            raise ValueError("invalid recorded clock order")
        previous_time = observed
        xy = [_number(pose["world_x"]), _number(pose["world_y"])]
        projected_z = None
        if (
            action.get("projected_z_source")
            == "decision_corridor_projection_not_observed_z"
        ):
            projected_z = _number(action["projected_z_world"])
        reasons = [
            "UNOBSERVED_Z",
            "UNRESOLVED_FLOOR",
            "UNKNOWN_METRIC_POSE_ERROR",
            "UNKNOWN_POSE_CONFIDENCE",
        ]
        # Do not use later log events, even when they carry older timestamps.
        eligible = [
            g
            for g in geometries
            if g["applied_to_pose_observed_monotonic_s"] <= observed
        ]
        geometry = eligible[-1] if eligible else None
        age = offset = None
        if geometry is None:
            reasons.append("MISSING_PRIOR_APPLIED_GEOMETRY")
        else:
            age = observed - geometry["observed_monotonic_s"]
            if age < 0:
                reasons.append("GEOMETRY_OBSERVED_AFTER_POSE")
            origin = geometry["query_origin"]
            offset = hypot(xy[0] - origin[0], xy[1] - origin[1])
            if age > policy.maximum_geometry_age_s:
                reasons.append("STALE_LOCAL_QUERY")
            if offset > policy.maximum_query_offset_yards:
                reasons.append("QUERY_ORIGIN_MOVED_XY")
        reasons_count.update(reasons)
        frames.append(
            {
                "frame_index": frame_index,
                "pose_evidence_ref": ref + "/decision_observation",
                "decision_observed_monotonic_s": observed,
                "decision_to_post_observation_s": post_time - observed,
                "recorded_client_xy": xy,
                "observed_z": None,
                "corridor_projected_z": projected_z,
                "floor_id": None,
                "prior_initial_vertical_selection_ref": (
                    vertical_selections[-1]["evidence_ref"]
                    if vertical_selections
                    else None
                ),
                "horizontal_error_bound_yards": None,
                "pose_confidence": None,
                "geometry": geometry,
                "geometry_age_relative_to_pose_s": age,
                "query_origin_offset_xy_yards": offset,
                "status": "PARTIAL_EVIDENCE",
                "reasons": reasons,
                "current_wall_distances": None,
                "free_space_certified": False,
                "execution_authority": False,
            }
        )
    if not frames:
        raise ValueError("no decision frames")
    return {
        "record_type": "spatial_trace_replay",
        "schema_version": "1.0",
        "scope": "OFFLINE_RECORDED_EVIDENCE_NOT_LIVE_OBSERVATION",
        "run_id": run_id,
        "map": map_name,
        "trace_sha256": digest,
        "world_pack_content_sha256": pack,
        "world_pack_rehashed": False,
        "clock_domain": "RECORDED_RUN_MONOTONIC",
        "frame_count": len(frames),
        "geometry_event_count": len(geometries),
        "frames_with_prior_geometry": sum(f["geometry"] is not None for f in frames),
        "initial_vertical_selections": vertical_selections,
        "recorded_multiheight_selection_count": sum(
            bool(item["alternative_heights"]) for item in vertical_selections
        ),
        "complete_spatial_pose_count": 0,
        "reason_counts": dict(reasons_count),
        "frames": frames,
        "free_space_certified": False,
        "execution_authority": False,
        "operator_summary_ro": "Poziția XY și geometria sunt înregistrate; Z observat, etajul și eroarea metrică nu sunt confirmate. Nu publicăm distanțe curente la ziduri.",
    }
