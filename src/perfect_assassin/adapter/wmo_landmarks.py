"""Resolve explicit asset vertices for offline image/geometry correspondence.

Vertex identity proves the 3D point, not its association with an image pixel.
"""

from hashlib import sha256

import numpy as np

from .wmo_bundle import WmoBundle, canonical
from .wmo_groups import world_to_model


def resolve_landmarks(bundle, *, structure_id, references):
    if not isinstance(bundle, WmoBundle):
        raise TypeError("landmarks require a verified WMO bundle")
    if not isinstance(references, list) or not 1 <= len(references) <= 64:
        raise ValueError("invalid landmark reference count")
    structure = bundle.structures[structure_id]
    meshes = bundle.models[structure["asset_path"]]
    matrix = np.asarray(structure["transform_matrix"], dtype=float).reshape(4, 4)
    # Apply the same affine/conditioning check used by the query adapter.
    world_to_model((0, 0, 0), structure["transform_matrix"])
    seen, points = set(), []
    for reference in references:
        if not isinstance(reference, dict) or set(reference) != {
            "group_index",
            "vertex_index",
        }:
            raise ValueError("invalid vertex reference")
        group, vertex = reference["group_index"], reference["vertex_index"]
        if type(group) is not int or type(vertex) is not int or min(group, vertex) < 0:
            raise ValueError("invalid vertex identity")
        matches = [mesh for mesh in meshes if mesh.group_index == group]
        if (
            len(matches) != 1
            or vertex >= len(matches[0].vertices)
            or (group, vertex) in seen
        ):
            raise ValueError("missing or duplicate vertex")
        seen.add((group, vertex))
        mesh = matches[0]
        if not np.any(mesh.indices == vertex):
            raise ValueError("unreferenced asset vertex")
        local = mesh.vertices[vertex].astype(float)
        world = matrix[:3, :3] @ local + matrix[:3, 3]
        points.append(
            {
                "group_index": group,
                "group_id": mesh.group_id,
                "vertex_index": vertex,
                "group_asset_sha256": mesh.asset_sha256,
                "model_xyz": local.tolist(),
                "world_xyz": world.tolist(),
                "used_by_retained_triangle": bool(
                    np.any(mesh.indices[mesh.retained] == vertex)
                ),
                "pixel_correspondence_verified": False,
            }
        )
    return {
        "schema_version": 1,
        "source": "VERIFIED_CLIENT_WMO_VERTICES",
        "bundle_sha256": bundle.manifest_sha256,
        "world_pack_sha256": bundle.pack_sha256,
        "structure_id": structure_id,
        "map_id": bundle.index.record["map_id"],
        "instance_transform_sha256": sha256(
            canonical(structure["transform_matrix"])
        ).hexdigest(),
        "points": points,
        "confirmed_floor_id": None,
        "execution_authority": False,
    }
