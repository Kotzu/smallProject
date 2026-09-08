"""Read-only, conditional geometry presentation; no certified actor floor."""

from math import atan2, degrees, hypot, isfinite


def observation_key(labels, map_id, *, now_s):
    if not isinstance(labels, dict):
        return None
    stamp = labels.get("observed_monotonic_s")
    if (
        labels.get("source") != "CLIENT_ADDON_API"
        or labels.get("execution_authority") is not False
        or type(stamp) not in (int, float)
        or not isfinite(stamp)
        or not 0 <= now_s - stamp <= 2
        or not isinstance(labels.get("capture_binding"), str)
        or not labels["capture_binding"]
        or type(labels.get("session_tag")) is not int
        or type(map_id) is not int
    ):
        return None
    return (labels["capture_binding"], labels["session_tag"], map_id)


def sonar_record(sample, *, key, pack_sha256, pose_xy, pose_observed_s, requested_s):
    """Distances refer to resolved query origin, not current measured actor XYZ."""
    origin = sample.resolved

    def segment(item):
        a, b = item.left, item.right
        dx, dy = b.x - a.x, b.y - a.y
        denominator = dx * dx + dy * dy
        t = (
            max(
                0.0,
                min(1.0, ((origin.x - a.x) * dx + (origin.y - a.y) * dy) / denominator),
            )
            if denominator
            else 0.0
        )
        x, y = a.x + t * dx, a.y + t * dy
        return {
            "distance_yards": hypot(x - origin.x, y - origin.y),
            "bearing_world_deg": degrees(atan2(y - origin.y, x - origin.x)),
            "left": [a.x, a.y, a.z],
            "right": [b.x, b.y, b.z],
        }

    walls = sorted(
        (segment(w) for w in sample.awareness.wall_segments),
        key=lambda w: w["distance_yards"],
    )
    exits = []
    for portal in sample.awareness.egress_portals[:8]:
        exits.append(
            {
                **segment(portal),
                "width_yards": portal.width_yards,
                "route_distance_yards": portal.route_distance_yards,
                "height_yards": None,
                "kind": "UNKNOWN_OPENING",
                "destination": None,
            }
        )
    return {
        "record_type": "conditional_spatial_sonar",
        "schema_version": "1.0",
        "source": "CLIENT_ASSET_GEOMETRY",
        "observation_key": list(key),
        "world_pack_sha256": pack_sha256,
        "pose_xy_at_query": list(pose_xy),
        "pose_observed_monotonic_s": pose_observed_s,
        "query_requested_monotonic_s": requested_s,
        "geometry_observed_monotonic_s": sample.observed_monotonic_s,
        "query_origin_xyz": [sample.source.x, sample.source.y, sample.source.z],
        "resolved_query_xyz": [origin.x, origin.y, origin.z],
        "z_status": "ASSET_ESTIMATE",
        "observed_actor_z": None,
        "floor_id": None,
        "floor_status": "UNCONFIRMED_NOT_ALTITUDE_INDEX",
        "ceiling_probe": {
            "status": (
                "NO_HIT_IN_TESTED_SEGMENT"
                if sample.awareness.overhead_clear
                else "BLOCKED_TESTED_SEGMENT"
            ),
            "ceiling_height_yards": None,
            "infinite_clearance": False,
            "open_world_confirmed": False,
        },
        "metric_pose_error_yards": None,
        "vertical_candidates": (
            sample.vertical_candidates.to_record()
            if sample.vertical_candidates
            else None
        ),
        "nearest_boundaries_at_query": walls[:8],
        "boundary_set_truncated": sample.awareness.wall_segments_truncated
        or len(walls) > 8,
        "component_truncated": sample.awareness.component_truncated,
        "openings_at_query": exits,
        "openings_truncated": sample.awareness.egress_portals_truncated
        or len(sample.awareness.egress_portals) > 8,
        "radial_probe_count": len(sample.awareness.radial_probes),
        "probe_radius_yards": sample.awareness.probe_radius_yards,
        "radial_probes_at_query": [
            {
                "bearing_world_deg": degrees(probe.bearing_rad),
                "tested_clear_distance_yards": probe.clearance_yards,
                "hit_distance_yards": None,
                "navmesh_endpoint_status": (
                    "REACHABLE_BY_RAYCAST"
                    if probe.navmesh_reachable
                    else "NOT_CONFIRMED"
                ),
            }
            for probe in sample.awareness.radial_probes
        ],
        "egress_inference_complete": sample.awareness.egress_inference_complete,
        "height_scan": (
            sample.height_scan.to_record()
            if getattr(sample, "height_scan", None)
            else None
        ),
        "distance_scope": "CONDITIONAL_RESOLVED_QUERY_ORIGIN_NOT_CURRENT_ACTOR",
        "dynamic_obstacles": "NOT_OBSERVED_BY_THIS_CHANNEL",
        "free_space_certified": False,
        "execution_authority": False,
    }


def sonar_applicable(record, *, key, xy, now_s):
    if not isinstance(record, dict) or key is None:
        return False
    try:
        age = now_s - record["pose_observed_monotonic_s"]
        origin = record["pose_xy_at_query"]
        return (
            record["record_type"] == "conditional_spatial_sonar"
            and record["schema_version"] == "1.0"
            and record["source"] == "CLIENT_ASSET_GEOMETRY"
            and record["execution_authority"] is False
            and record["observation_key"] == list(key)
            and 0 <= age <= 3
            and hypot(origin[0] - xy[0], origin[1] - xy[1]) <= 0.5
        )
    except (KeyError, TypeError, ValueError, IndexError):
        return False


def sonar_display(record, *, labels, now_s):
    unknown = "Sonar: aștept geometria · etaj neconfirmat"
    if not isinstance(record, dict):
        return unknown
    try:
        key = observation_key(labels, record["observation_key"][2], now_s=now_s)
        if not sonar_applicable(
            record, key=key, xy=record["pose_xy_at_query"], now_s=now_s
        ):
            return "Sonar: date expirate/incompatibile · etaj neconfirmat"
        z = record["resolved_query_xyz"][2]
        if type(z) not in (float, int) or not isfinite(z):
            return unknown
        candidates = record.get("vertical_candidates")
        count = len(candidates["heights"]) if candidates else None
        count_text = (
            ("1 suprafață candidată" if count == 1 else f"{count} suprafețe candidate")
            if count is not None
            else "alternative necunoscute"
        )
        ceiling_text = {
            "NO_HIT_IN_TESTED_SEGMENT": "Plafon: nedetectat în segmentul testat",
            "BLOCKED_TESTED_SEGMENT": "Obstacol deasupra în segmentul testat · distanță necunoscută",
        }.get((record.get("ceiling_probe") or {}).get("status"), "Plafon: necunoscut")
        return (
            f"Sonar: altitudine estimată {z:.2f} yd · {count_text}"
            f"\nEtaj neconfirmat · geometrie condițională\n{ceiling_text}"
        )
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return unknown
