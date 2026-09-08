"""Compare retained group triangle multisets with the existing BVH geometry.

This audits the geometry prefix/root ID only, not the entire WorldPack seal,
the acceleration tree or the semantics of addon environment observations.
"""

import struct
from collections import Counter
from hashlib import sha256

import numpy as np


def triangle_counts(vertices, indices):
    triangles = np.asarray(vertices[indices], dtype="<f4")
    return Counter(t.tobytes() for t in triangles)


def triangle_digest(counts):
    digest = sha256()
    for triangle, count in sorted(counts.items()):
        digest.update(triangle)
        digest.update(struct.pack("<I", count))
    return digest.hexdigest()


def parse_bvh_geometry(data: bytes):
    if (
        not isinstance(data, bytes)
        or len(data) > 128 * 1024 * 1024
        or data[:4] != b"1HVB"
    ):
        raise ValueError("invalid BVH geometry header")
    offset = 4

    def take(size):
        nonlocal offset
        if size < 0 or size > len(data) - offset:
            raise ValueError("truncated BVH geometry")
        value = memoryview(data)[offset : offset + size]
        offset += size
        return value

    def integer():
        return struct.unpack("<I", take(4))[0]

    vertex_count = integer()
    if not 1 <= vertex_count <= 1_000_000:
        raise ValueError("invalid BVH vertex count")
    vertices = np.frombuffer(take(vertex_count * 12), dtype="<f4").reshape(-1, 3)
    index_count = integer()
    if not 3 <= index_count <= 3_000_000 or index_count % 3:
        raise ValueError("invalid BVH index count")
    indices = np.frombuffer(take(index_count * 4), dtype="<i4").reshape(-1, 3)
    if (
        not np.isfinite(vertices).all()
        or indices.min() < 0
        or indices.max() >= vertex_count
    ):
        raise ValueError("invalid BVH triangles")
    nodes = integer()
    if not 1 <= nodes <= 2_000_000:
        raise ValueError("invalid BVH node count")
    take(nodes * 29)  # Serialized node: uint8 + uint32 + six floats.
    if bytes(take(4)) != b"BOOF":
        raise ValueError("invalid BVH end marker")
    root_id = integer()
    return root_id, triangle_counts(vertices, indices)


def bvh_asset_name(data: bytes, asset_path: str) -> str:
    if not isinstance(data, bytes) or len(data) > 16 * 1024 * 1024:
        raise ValueError("invalid BVH index size")
    offset = 0

    def integer():
        nonlocal offset
        if len(data) - offset < 4:
            raise ValueError("truncated BVH index")
        value = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        return value

    def string():
        nonlocal offset
        size = integer()
        if not 1 <= size <= 1024 or size > len(data) - offset:
            raise ValueError("invalid BVH index path size")
        value = data[offset : offset + size].decode("ascii")
        offset += size
        return value

    count = integer()
    if count > 100000:
        raise ValueError("invalid BVH index count")
    matches = []
    for _ in range(count):
        asset, filename = string(), string()
        if asset.replace("\\", "/").lower() == asset_path.replace("\\", "/").lower():
            matches.append(filename)
    if len(matches) != 1:
        raise ValueError("expected unique BVH asset mapping")
    filename = matches[0]
    if any(c in filename for c in ("/", "\\", ":", "\0")) or filename in (".", ".."):
        raise ValueError("BVH file must be a local leaf")
    return filename
