import struct

import pytest

from perfect_assassin.adapter.wmo_groups import parse_wmo_root, world_to_model


def chunk(tag, data):
    return tag[::-1] + struct.pack("<I", len(data)) + data


def root(groups=((0x2000, (0, 0, 0, 5, 5, 5)),), version=17):
    header = bytearray(64)
    struct.pack_into("<I", header, 4, len(groups))
    struct.pack_into("<I", header, 32, 42)
    return (
        chunk(b"MVER", struct.pack("<I", version))
        + chunk(b"MOHD", header)
        + chunk(
            b"MOGI",
            b"".join(
                struct.pack("<I6fi", flags, *bounds, -1) for flags, bounds in groups
            ),
        )
    )


@pytest.mark.parametrize(
    "flags,expected",
    [
        (0, "NEITHER_FLAG"),
        (8, "EXTERIOR_FLAG"),
        (8192, "INTERIOR_FLAG"),
        (8200, "BOTH_FLAGS"),
    ],
)
def test_group_flags_remain_evidence_not_actor_floor(flags, expected):
    parsed = parse_wmo_root(root(((flags, (0, 0, 0, 5, 5, 5)),)))
    assert parsed.root_id == 42
    assert len(parsed.asset_sha256) == 64
    assert parsed.groups[0].flags == flags
    assert parsed.groups[0].flag_evidence == expected


def test_overlapping_groups_remain_multiple_candidates():
    parsed = parse_wmo_root(root(((8, (0, 0, 0, 5, 5, 5)), (8192, (0, 0, 2, 5, 5, 8)))))
    assert [g.index for g in parsed.groups if g.contains_bounds((2, 2, 3))] == [0, 1]
    assert [g.index for g in parsed.groups if g.contains_bounds((2, 2, 6))] == [1]
    assert not any(g.contains_bounds((9, 9, 9)) for g in parsed.groups)


def test_two_altitudes_can_share_one_interior_box():
    # Abstract regression for the real crypt ambiguity, not licensed geometry.
    parsed = parse_wmo_root(root(((8192, (-20, -20, -25, 5, 5, 10)),)))
    for altitude in (-19, -2):
        matches = [g for g in parsed.groups if g.contains_bounds((-17, -14, altitude))]
        assert [g.index for g in matches] == [0]
        assert matches[0].flag_evidence == "INTERIOR_FLAG"
    # Same metadata for two different levels cannot disambiguate them.


def test_exterior_shell_box_can_overlap_interior_room_boxes():
    parsed = parse_wmo_root(
        root(
            (
                (8, (-40, -15, -1, 25, 20, 25)),
                (8192, (-18, -12, -1, 15, 16, 17)),
                (8192, (-16, -10, 7, -1, 4, 17)),
            )
        )
    )
    assert [
        g.flag_evidence for g in parsed.groups if g.contains_bounds((-8, 2, 8))
    ] == ["EXTERIOR_FLAG", "INTERIOR_FLAG", "INTERIOR_FLAG"]


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"REVM",
        root()[:-1],
        root() + b"x",
        root(version=14),
        root() + chunk(b"MVER", struct.pack("<I", 17)),
        chunk(b"MVER", struct.pack("<I", 17)),
        root(((8, (0, 0, 0, float("inf"), 5, 5)),)),
        root(((8, (9, 0, 0, 5, 5, 5)),)),
        root(((8, (0, 0, 0, 5, 5, 5)),) * 513),
    ],
    ids=[
        "empty",
        "header",
        "payload",
        "trailing",
        "version",
        "duplicate",
        "missing",
        "infinite",
        "inverted",
        "too-many",
    ],
)
def test_malformed_or_unsupported_root_is_rejected(data):
    with pytest.raises(ValueError):
        parse_wmo_root(data)


def test_unknown_well_formed_chunk_does_not_hide_metadata():
    assert parse_wmo_root(root() + chunk(b"XXXX", b"unknown")).root_id == 42


def test_world_to_model_uses_inverse_rotation_scale_and_translation():
    matrix = [0, -2, 0, 10, 2, 0, 0, 20, 0, 0, 2, 30, 0, 0, 0, 1]
    assert world_to_model((6, 22, 36), matrix) == pytest.approx((1, 2, 3))


@pytest.mark.parametrize("matrix", [[0] * 16, [1] * 16, [float("nan")] * 16, [1] * 15])
def test_invalid_transform_cannot_create_membership(matrix):
    with pytest.raises(ValueError):
        world_to_model((1, 2, 3), matrix)
