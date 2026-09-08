"""Bounded WMO v17 group metadata; bounding boxes are not occupied volumes.

Layout reference: https://www.getmangos.eu/wiki/referenceinfo/clientfiles/wmo-file-r20030/
Raw flags are retained. Their relation to a client's IsIndoors requires validation.
"""

import struct
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite

import numpy as np

MAX_ROOT_BYTES = 16 * 1024 * 1024
MAX_GROUPS = 512


@dataclass(frozen=True)
class WmoGroup:
    index: int
    flags: int
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]

    @property
    def flag_evidence(self) -> str:
        indoor, outdoor = bool(self.flags & 0x2000), bool(self.flags & 0x8)
        if indoor and outdoor:
            return "BOTH_FLAGS"
        if indoor:
            return "INTERIOR_FLAG"
        if outdoor:
            return "EXTERIOR_FLAG"
        return "NEITHER_FLAG"

    def contains_bounds(self, point: tuple[float, float, float]) -> bool:
        if len(point) != 3 or not all(isfinite(v) for v in point):
            raise ValueError("invalid local point")
        return all(
            lo <= v <= hi for lo, v, hi in zip(self.minimum, point, self.maximum)
        )


@dataclass(frozen=True)
class WmoGroups:
    asset_sha256: str
    root_id: int
    groups: tuple[WmoGroup, ...]


def parse_wmo_root(data: bytes) -> WmoGroups:
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_ROOT_BYTES:
        raise ValueError("invalid WMO byte size")
    chunks = {}
    offset = 0
    while offset < len(data):
        if len(data) - offset < 8:
            raise ValueError("truncated WMO chunk header")
        tag, size = struct.unpack_from("<4sI", data, offset)
        offset += 8
        if size > len(data) - offset:
            raise ValueError("truncated WMO chunk payload")
        if tag in (b"REVM", b"DHOM", b"IGOM"):
            if tag in chunks:
                raise ValueError("duplicate WMO metadata chunk")
            chunks[tag] = memoryview(data)[offset : offset + size]
        offset += size
    if set(chunks) != {b"REVM", b"DHOM", b"IGOM"}:
        raise ValueError("missing WMO root metadata")
    if len(chunks[b"REVM"]) != 4 or struct.unpack("<I", chunks[b"REVM"])[0] != 17:
        raise ValueError("only WMO version 17 is supported")
    header = chunks[b"DHOM"]
    if len(header) != 64:
        raise ValueError("invalid MOHD size")
    count = struct.unpack_from("<I", header, 4)[0]
    root_id = struct.unpack_from("<I", header, 32)[0]
    info = chunks[b"IGOM"]
    if count > MAX_GROUPS or len(info) != count * 32:
        raise ValueError("invalid MOGI group count")
    groups = []
    for index in range(count):
        flags, *values = struct.unpack_from("<I6fi", info, index * 32)
        minimum, maximum = tuple(values[:3]), tuple(values[3:6])
        if not all(isfinite(v) for v in minimum + maximum) or any(
            lo > hi for lo, hi in zip(minimum, maximum)
        ):
            raise ValueError("invalid WMO group bounds")
        groups.append(WmoGroup(index, flags, minimum, maximum))
    return WmoGroups(sha256(data).hexdigest(), root_id, tuple(groups))


def world_to_model(point, transform_matrix) -> tuple[float, float, float]:
    """Inverse of the row-major model-to-world instance matrix, not camera pose."""
    matrix = np.asarray(transform_matrix, dtype=float)
    xyz = np.asarray(point, dtype=float)
    if matrix.shape != (16,) or xyz.shape != (3,):
        raise ValueError("invalid instance transform shape")
    matrix = matrix.reshape(4, 4)
    if not np.isfinite(matrix).all() or not np.isfinite(xyz).all():
        raise ValueError("nonfinite instance transform/point")
    if not np.array_equal(matrix[3], (0, 0, 0, 1)):
        raise ValueError("instance transform is not affine")
    if np.linalg.cond(matrix[:3, :3]) > 1e6:
        raise ValueError("singular or ill-conditioned instance transform")
    try:
        local = np.linalg.solve(matrix[:3, :3], xyz - matrix[:3, 3])
    except np.linalg.LinAlgError as error:
        raise ValueError("singular instance transform") from error
    if not np.isfinite(local).all():
        raise ValueError("nonfinite transformed point")
    return tuple(float(v) for v in local)
