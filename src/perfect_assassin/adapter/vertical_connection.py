"""Strictly bound topology evidence between requested surface hypotheses."""

from math import dist, isfinite


def point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3 or any(
        type(v) not in (int, float) or not isfinite(v) or abs(v) > 100000 for v in value
    ):
        raise ValueError("invalid finite XYZ")
    return tuple(value)


def parse_connection(record, *, sequence, start, stop):
    fields = {"status", "sequence", "requested_start", "requested_stop", "resolved_start",
              "resolved_stop", "path_stop", "start_poly", "stop_poly", "complete",
              "search_limited", "polygon_count", "point_count", "funnel_length_yards",
              "source", "observed_actor_z", "floor_id", "execution_authority"}
    if not isinstance(record, dict) or set(record) != fields:
        raise ValueError("invalid connection fields")
    if (record["status"] != "OK" or type(record["sequence"]) is not int
            or record["sequence"] != sequence or record["source"] != "CLIENT_NAVMESH_TOPOLOGY"
            or record["observed_actor_z"] is not None or record["floor_id"] is not None
            or record["execution_authority"] is not False):
        raise ValueError("invalid connection binding/authority")
    for field, expected in (("requested_start", start), ("requested_stop", stop)):
        if dist(point(record[field]), point(expected)) > 0.025:
            raise ValueError("connection belongs to another endpoint")
    for field in ("resolved_start", "resolved_stop", "path_stop"):
        point(record[field])
    for field in ("complete", "search_limited"):
        if type(record[field]) is not bool:
            raise ValueError("invalid completeness flag")
    if record["complete"] and (record["search_limited"] or dist(record["path_stop"], record["resolved_stop"]) > 0.001):
        raise ValueError("partial result claims completeness")
    for field in ("polygon_count", "point_count"):
        if type(record[field]) is not int or not 1 <= record[field] <= 512:
            raise ValueError("invalid count")
    for field in ("start_poly", "stop_poly"):
        v = record[field]
        if not isinstance(v, str) or not v.isascii() or not v.isdecimal() or not 1 <= len(v) <= 20 or not 0 < int(v) < 2**64:
            raise ValueError("invalid polygon reference")
    length = record["funnel_length_yards"]
    if type(length) not in (int, float) or not isfinite(length) or length < 0:
        raise ValueError("invalid length")
    return {**record, "start_projection_yards": dist(point(start), record["resolved_start"]),
            "stop_projection_yards": dist(point(stop), record["resolved_stop"]),
            "actor_transition_confirmed": False, "volumetric_clearance_checked": False}
