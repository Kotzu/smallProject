"""Numerical association of same-column asset queries, not actor localization."""

from math import hypot, isfinite

from .vertical_candidates import VerticalSurfaceCandidates


def _number(value):
    return type(value) in (int, float) and isfinite(value)


def associate_surfaces(
    candidates: VerticalSurfaceCandidates,
    *,
    query_xy,
    segment_start,
    segment_end,
    hits,
    tolerance_yards,
):
    """Caller binds both queries to the same verified map/pack/instance.

    Tolerance is an explicit numerical matching budget, not localization error.
    No nearest-only choice; duplicate candidates and all triangle identities survive.
    """
    if (
        not isinstance(candidates, VerticalSurfaceCandidates)
        or not 1 <= len(candidates.heights) <= 64
    ):
        raise ValueError("invalid candidate set")
    if (
        any(not _number(v) for v in candidates.heights)
        or not _number(candidates.selected_surface_z)
        or candidates.selected_surface_z not in candidates.heights
    ):
        raise ValueError("invalid candidate heights")
    if not _number(tolerance_yards) or not 0 < tolerance_yards <= 0.01:
        raise ValueError("invalid numerical matching tolerance")
    if len(query_xy) != 2 or len(segment_start) != 3 or len(segment_end) != 3:
        raise ValueError("invalid query dimensions")
    if not all(_number(v) for v in (*query_xy, *segment_start, *segment_end)):
        raise ValueError("invalid query coordinates")
    if any(
        hypot(p[0] - query_xy[0], p[1] - query_xy[1]) > 1e-5
        for p in (segment_start, segment_end)
    ):
        raise ValueError("surface segment is not the candidate XY column")
    low, high = sorted((segment_start[2], segment_end[2]))
    if not 0 < high - low <= 10000:
        raise ValueError("invalid surface segment extent")
    if not isinstance(hits, (list, tuple)) or len(hits) > 4096:
        raise ValueError("surface hit budget exceeded")
    clean = []
    for hit in hits:
        if not isinstance(hit, dict):
            raise ValueError("invalid surface hit")  # noqa: TRY004 - malformed adapter record
        point = hit.get("world_xyz")
        if (
            not isinstance(point, (list, tuple))
            or len(point) != 3
            or not all(_number(v) for v in point)
        ):
            raise ValueError("invalid surface hit point")
        if (
            hypot(point[0] - query_xy[0], point[1] - query_xy[1]) > 1e-5
            or not low - 1e-5 <= point[2] <= high + 1e-5
        ):
            raise ValueError("surface hit outside query segment")
        for field in ("group_index", "group_id", "triangle_index", "group_flags"):
            if type(hit.get(field)) is not int or not 0 <= hit[field] <= 0xFFFFFFFF:
                raise ValueError("invalid surface identity")
        normal = hit.get("world_normal_z")
        if not _number(normal) or not -1 <= normal <= 1:
            raise ValueError("invalid surface normal")
        clean.append(
            {
                field: hit[field]
                for field in (
                    "group_index",
                    "group_id",
                    "triangle_index",
                    "group_flags",
                    "world_normal_z",
                )
            }
            | {"surface_z": point[2]}
        )
    records = []
    for index, height in enumerate(candidates.heights):
        covered = low <= height <= high
        matches = []
        if covered:
            matches = [
                surface | {"height_delta_yards": abs(height - surface["surface_z"])}
                for surface in clean
                if abs(height - surface["surface_z"]) <= tolerance_yards
            ]
        records.append(
            {
                "candidate_index": index,
                "candidate_z": height,
                "status": "MATCHED_GEOMETRY"
                if matches
                else "NO_WMO_MATCH"
                if covered
                else "OUTSIDE_TESTED_SEGMENT",
                "matches": matches,
                "candidate_retained": True,
            }
        )
    return {
        "schema_version": 1,
        "source": "SAME_COLUMN_ASSET_SURFACE_ASSOCIATION",
        "query_xy": list(query_xy),
        "segment_z": [low, high],
        "numerical_matching_tolerance_yards": tolerance_yards,
        "candidate_source": "CLIENT_ASSET_HEIGHT_QUERY",
        "surface_source": "CLIENT_WMO_GROUP_TRIANGLES",
        "selected_surface_z_unchanged": candidates.selected_surface_z,
        "candidates": records,
        "observed_actor_z": None,
        "confirmed_floor_id": None,
        "execution_authority": False,
        "terrain_and_doodads_checked": False,
    }
