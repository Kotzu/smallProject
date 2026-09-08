"""Read-only body-volume evaluation against a verified, partial WMO bundle.

Not wired to movement: foot Z and capsule dimensions remain explicit hypotheses.
Orientation buckets describe triangle normals, never floor or walkability labels.
"""
from dataclasses import asdict
from math import hypot

import numpy as np

from perfect_assassin.adapter.wmo_bundle import WmoBundle
from perfect_assassin.adapter.wmo_groups import world_to_model
from perfect_assassin.movement.swept_volume import swept_capsule_surface_distance


def evaluate_wmo_sweep(bundle, *, map_id, start, stop, radius_yards, height_yards):
    if not isinstance(bundle, WmoBundle):
        raise TypeError("sweep requires a loaded WMO bundle")
    if type(map_id) is not int or map_id != bundle.index.record["map_id"]:
        raise ValueError("WMO sweep map mismatch")
    dimensions = dict(radius_yards=radius_yards, height_yards=height_yards)
    # Validate every input before spatial lookup, even for an empty neighborhood.
    swept_capsule_surface_distance(start, stop, triangles=[], **dimensions)
    center = ((start[0]+stop[0])/2, (start[1]+stop[1])/2)
    search_radius = hypot(stop[0]-start[0], stop[1]-start[1])/2+radius_yards+2
    nearby = bundle.index.spatial.nearby(
        x=center[0], y=center[1], radius_yards=search_radius, kinds=("WMO",))
    if len(nearby) > 16:
        raise ValueError("WMO sweep exceeds instance budget")
    faces = {"all": [], "low_slope": [], "steep": [], "degenerate": []}
    identities = {key: [] for key in faces}
    missing = []
    for hit in nearby:
        structure = bundle.structures[hit.structure.structure_id]
        meshes = bundle.models.get(structure["asset_path"])
        if meshes is None:
            missing.append(structure["structure_id"])
            continue
        transform = structure["transform_matrix"]
        world_to_model(start, transform)  # Existing finite affine/conditioning checks.
        matrix = np.asarray(transform, dtype=float).reshape(4, 4)
        for mesh in meshes:
            # Transform geometry, not capsule: preserves world radius under scale.
            vertices = mesh.vertices @ matrix[:3, :3].T + matrix[:3, 3]
            retained = np.flatnonzero(mesh.retained)
            if len(faces["all"])+len(retained) > 200000:
                raise ValueError("WMO sweep exceeds triangle budget")
            for triangle_index in retained:
                triangle = vertices[mesh.indices[triangle_index]]
                normal = np.cross(triangle[1]-triangle[0], triangle[2]-triangle[0])
                norm = float(np.linalg.norm(normal))
                nz = None if norm == 0 else float(normal[2]/norm)
                bucket = "degenerate" if nz is None else "low_slope" if abs(nz) >= .7 else "steep"
                identity = {"structure_id": structure["structure_id"],
                            "asset_path": structure["asset_path"],
                            "group_index": mesh.group_index, "group_id": mesh.group_id,
                            "triangle_index": int(triangle_index), "world_normal_z": nz}
                points = triangle.tolist()
                for key in ("all", bucket):
                    faces[key].append(points)
                    identities[key].append(identity)
    distances = {}
    for key, triangles in faces.items():
        distance = swept_capsule_surface_distance(start, stop, triangles=triangles, **dimensions)
        record = asdict(distance)
        index = record.pop("nearest_triangle_index")
        record["nearest_surface"] = None if index is None else identities[key][index]
        distances[key] = record
    return {"schema_version": 1, "source": "VERIFIED_WMO_GROUP_BUNDLE",
            "bundle_sha256": bundle.manifest_sha256, "world_pack_sha256": bundle.pack_sha256,
            "map_id": map_id, "start_foot_xyz": list(start), "stop_foot_xyz": list(stop),
            "body_hypothesis": dimensions, "pose_and_body_status": "UNVERIFIED_HYPOTHESIS",
            "coverage": "LISTED_MODELS_IN_QUERY_NEIGHBORHOOD_ONLY",
            "search_center_xy": list(center), "search_radius_yards": search_radius,
            "nearby_wmo_count": len(nearby), "uncovered_structure_ids": missing,
            "orientation_threshold_abs_normal_z": .7, "distances": distances,
            "confirmed_floor_id": None, "traversability": "UNKNOWN",
            "terrain_and_doodads_checked": False, "execution_authority": False}
