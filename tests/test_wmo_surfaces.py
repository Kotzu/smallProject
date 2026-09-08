import struct

import numpy as np
import pytest
from test_wmo_groups import chunk

from perfect_assassin.adapter.wmo_groups import WmoGroup
from perfect_assassin.adapter.wmo_surfaces import parse_wmo_group, segment_hits

IDENTITY = np.eye(4).reshape(-1).tolist()
EXPECTED = WmoGroup(4, 8192, (-10.0, -10.0, -10.0), (10.0, 10.0, 10.0))


def group(
    vertices=((0, 0, 0), (4, 0, 0), (0, 4, 0)),
    indices=((0, 1, 2),),
    materials=((0, 0),),
    version=17,
    extra=b"",
):
    header = bytearray(68)
    struct.pack_into(
        "<I6f", header, 8, EXPECTED.flags, *EXPECTED.minimum, *EXPECTED.maximum
    )
    struct.pack_into("<I", header, 56, 321)
    payload = (
        header
        + chunk(b"MOPY", bytes(v for pair in materials for v in pair))
        + chunk(b"MOVI", b"".join(struct.pack("<3H", *tri) for tri in indices))
        + chunk(b"MOVT", b"".join(struct.pack("<3f", *v) for v in vertices))
        + extra
    )
    return chunk(b"MVER", struct.pack("<I", version)) + chunk(b"MOGP", payload)


def test_real_triangle_not_bounding_box_decides_intersection():
    mesh = parse_wmo_group(group(), EXPECTED)
    hits = segment_hits(mesh, IDENTITY, (1, 1, 2), (1, 1, -2))
    assert len(hits) == 1
    assert hits[0]["world_xyz"] == pytest.approx((1, 1, 0))
    assert hits[0]["group_id"] == 321 and hits[0]["group_index"] == 4
    assert hits[0]["world_normal_z"] == 1
    assert not segment_hits(mesh, IDENTITY, (4, 4, 2), (4, 4, -2))
    assert not mesh.vertices.flags.writeable


@pytest.mark.parametrize(
    "flags,material,retained", [(0, 0, True), (4, 0, False), (4, 255, True)]
)
def test_retained_triangle_mask_matches_named_asset_filter(flags, material, retained):
    mesh = parse_wmo_group(group(materials=((flags, material),)), EXPECTED)
    assert bool(segment_hits(mesh, IDENTITY, (1, 1, 2), (1, 1, -2))) is retained


def test_stacked_surfaces_are_all_retained_not_nearest_selected():
    vertices = ((0, 0, 0), (4, 0, 0), (0, 4, 0), (0, 0, 5), (0, 4, 5), (4, 0, 5))
    mesh = parse_wmo_group(
        group(vertices, ((0, 1, 2), (3, 4, 5)), ((0, 0), (0, 0))), EXPECTED
    )
    hits = segment_hits(mesh, IDENTITY, (1, 1, 7), (1, 1, -2))
    assert [h["world_xyz"][2] for h in hits] == pytest.approx([5, 0])
    assert [h["world_normal_z"] for h in hits] == [-1, 1]
    assert len(segment_hits(mesh, IDENTITY, (1, 1, -2), (1, 1, 7))) == 2


def test_world_segment_transforms_both_endpoints_under_tilt_scale_translation():
    # Local z=0 becomes world y=20, not a world-horizontal floor.
    matrix = [2, 0, 0, 10, 0, 0, -2, 20, 0, 2, 0, 30, 0, 0, 0, 1]
    mesh = parse_wmo_group(group(), EXPECTED)
    hits = segment_hits(mesh, matrix, (12, 24, 32), (12, 16, 32))
    assert hits[0]["world_xyz"] == pytest.approx((12, 20, 32))
    assert hits[0]["distance_yards"] == pytest.approx(4)
    assert hits[0]["world_normal_z"] == 0


def test_segment_bounds_and_coplanar_limit():
    mesh = parse_wmo_group(group(), EXPECTED)
    assert not segment_hits(mesh, IDENTITY, (1, 1, 4), (1, 1, 2))
    assert not segment_hits(mesh, IDENTITY, (1, 1, 0), (2, 1, 0))
    assert len(segment_hits(mesh, IDENTITY, (1, 1, 1), (1, 1, 0))) == 1
    with pytest.raises(ValueError):
        segment_hits(mesh, IDENTITY, (0, 0, 0), (0, 0, 0))


@pytest.mark.parametrize(
    "data",
    [
        b"",
        group()[:-1],
        group(version=14),
        group(indices=((0, 1, 9),)),
        group(materials=()),
        group(vertices=((float("nan"), 0, 0), (4, 0, 0), (0, 4, 0))),
        group(extra=chunk(b"MOVT", b"")),
    ],
    ids=["empty", "truncated", "version", "bad-index", "bad-count", "nan", "duplicate"],
)
def test_malformed_geometry_fails_instead_of_becoming_clear(data):
    with pytest.raises(ValueError):
        parse_wmo_group(data, EXPECTED)


def test_group_root_mismatch_rejected():
    with pytest.raises(ValueError):
        parse_wmo_group(group(), WmoGroup(4, 8, EXPECTED.minimum, EXPECTED.maximum))
    with pytest.raises(ValueError):
        parse_wmo_group(group(), WmoGroup(4, 8192, (0, 0, 0), EXPECTED.maximum))


def test_degenerate_triangle_is_not_a_hit():
    mesh = parse_wmo_group(group(vertices=((0, 0, 0),) * 3), EXPECTED)
    assert not segment_hits(mesh, IDENTITY, (0, 0, 1), (0, 0, -1))


def test_shared_edge_hits_keep_both_triangle_identities():
    mesh = parse_wmo_group(
        group(
            vertices=((0, 0, 0), (4, 0, 0), (0, 4, 0), (4, 4, 0)),
            indices=((0, 1, 2), (1, 3, 2)),
            materials=((0, 0), (0, 0)),
        ),
        EXPECTED,
    )
    hits = segment_hits(mesh, IDENTITY, (2, 2, 3), (2, 2, -3))
    assert [h["triangle_index"] for h in hits] == [0, 1]
    assert [h["world_xyz"][2] for h in hits] == pytest.approx([0, 0])
