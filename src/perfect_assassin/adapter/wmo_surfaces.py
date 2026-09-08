"""WMO v17 per-group triangle observations, never a confirmed actor floor.

The retained-triangle mask reproduces the local NAMIGATOR Wmo.cpp filter.
It is a named asset interpretation, not proof of client collision behavior.
"""

import struct
from dataclasses import dataclass
from hashlib import sha256

import numpy as np

from .wmo_groups import WmoGroup, world_to_model

MAX_GROUP_BYTES = 32 * 1024 * 1024
MAX_TRIANGLES = 200_000


def _chunks(data, wanted):
    chunks = {}
    offset = 0
    while offset < len(data):
        if len(data) - offset < 8:
            raise ValueError("truncated group chunk header")
        tag, size = struct.unpack_from("<4sI", data, offset)
        offset += 8
        if size > len(data) - offset:
            raise ValueError("truncated group chunk payload")
        if tag in wanted:
            if tag in chunks:
                raise ValueError("duplicate group geometry chunk")
            chunks[tag] = memoryview(data)[offset : offset + size]
        offset += size
    if set(chunks) != wanted:
        raise ValueError("missing group geometry chunks")
    return chunks


@dataclass(frozen=True)
class WmoMesh:
    asset_sha256: str
    group_index: int
    group_id: int
    flags: int
    vertices: np.ndarray
    indices: np.ndarray
    materials: np.ndarray

    @property
    def retained(self):
        return ((self.materials[:, 0] & 4) == 0) | (self.materials[:, 1] == 255)


def parse_wmo_group(data: bytes, expected: WmoGroup) -> WmoMesh:
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_GROUP_BYTES:
        raise ValueError("invalid group byte size")
    outer = _chunks(data, {b"REVM", b"PGOM"})
    if len(outer[b"REVM"]) != 4 or struct.unpack("<I", outer[b"REVM"])[0] != 17:
        raise ValueError("only group version 17 is supported")
    group = outer[b"PGOM"]
    if len(group) < 68:
        raise ValueError("truncated MOGP header")
    flags = struct.unpack_from("<I", group, 8)[0]
    bounds = struct.unpack_from("<6f", group, 12)
    if (
        not np.isfinite(bounds).all()
        or tuple(bounds) != expected.minimum + expected.maximum
    ):
        raise ValueError("group/root bounds disagree")
    if (flags & 0x2008) != (expected.flags & 0x2008):
        raise ValueError("group/root environment bits disagree")
    group_id = struct.unpack_from("<I", group, 56)[0]
    sub = _chunks(group[68:], {b"YPOM", b"IVOM", b"TVOM"})
    if len(sub[b"TVOM"]) % 12 or len(sub[b"IVOM"]) % 6 or len(sub[b"YPOM"]) % 2:
        raise ValueError("unaligned group geometry")
    count = len(sub[b"IVOM"]) // 6
    if count > MAX_TRIANGLES or len(sub[b"YPOM"]) != count * 2:
        raise ValueError("invalid group triangle count")
    vertices = np.frombuffer(sub[b"TVOM"], dtype="<f4").reshape(-1, 3)
    indices = np.frombuffer(sub[b"IVOM"], dtype="<u2").reshape(-1, 3)
    materials = np.frombuffer(sub[b"YPOM"], dtype="u1").reshape(-1, 2)
    if len(vertices) > 65536 or not np.isfinite(vertices).all():
        raise ValueError("invalid group vertices")
    if count and (not len(vertices) or int(indices.max()) >= len(vertices)):
        raise ValueError("triangle references missing vertex")
    return WmoMesh(
        sha256(data).hexdigest(),
        expected.index,
        group_id,
        flags,
        vertices,
        indices,
        materials,
    )


def segment_hits(mesh: WmoMesh, transform_matrix, start, end) -> list[dict]:
    """Two-sided finite segment intersection; coplanar triangles are not resolved.

    Preserves every triangle hit (including shared edges), with original group
    identity and winding normal. No floor/ceiling/walkable interpretation.
    """
    a = np.asarray(world_to_model(start, transform_matrix))
    b = np.asarray(world_to_model(end, transform_matrix))
    direction = b - a
    length = np.linalg.norm(np.asarray(end) - np.asarray(start))
    if not np.isfinite(length) or not 0 < length <= 10000:
        raise ValueError("segment length must be finite, positive and bounded")
    selected = np.flatnonzero(mesh.retained)
    triangles = mesh.vertices[mesh.indices[selected]].astype(float)
    if not len(triangles):
        return []
    e1, e2 = triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    p = np.cross(direction, e2)
    determinant = np.einsum("ij,ij->i", e1, p)
    scale = (
        np.linalg.norm(e1, axis=1)
        * np.linalg.norm(e2, axis=1)
        * np.linalg.norm(direction)
    )
    valid = (scale > 0) & (np.abs(determinant) > scale * 1e-10)
    inverse = np.zeros_like(determinant)
    np.divide(1, determinant, out=inverse, where=valid)
    offset = a - triangles[:, 0]
    u = np.einsum("ij,ij->i", offset, p) * inverse
    q = np.cross(offset, e1)
    v = (q @ direction) * inverse
    t = np.einsum("ij,ij->i", e2, q) * inverse
    epsilon = 1e-7
    hit = (
        valid
        & (u >= -epsilon)
        & (v >= -epsilon)
        & (u + v <= 1 + epsilon)
        & (t >= -epsilon)
        & (t <= 1 + epsilon)
    )
    matrix = np.asarray(transform_matrix).reshape(4, 4)[:3, :3]
    world_normals = np.cross(e1 @ matrix.T, e2 @ matrix.T)
    result = []
    for index in np.flatnonzero(hit):
        fraction = float(np.clip(t[index], 0, 1))
        world = np.asarray(start) + fraction * (np.asarray(end) - np.asarray(start))
        normal_length = np.linalg.norm(world_normals[index])
        result.append(
            {
                "group_index": mesh.group_index,
                "group_id": mesh.group_id,
                "triangle_index": int(selected[index]),
                "group_flags": mesh.flags,
                "fraction": fraction,
                "distance_yards": fraction * float(length),
                "world_xyz": world.tolist(),
                "world_normal_z": float(world_normals[index, 2] / normal_length),
            }
        )
    return sorted(result, key=lambda h: (h["fraction"], h["triangle_index"]))
