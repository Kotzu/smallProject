import struct

import numpy as np
import pytest

from perfect_assassin.adapter.wmo_bvh_audit import (
    bvh_asset_name,
    parse_bvh_geometry,
    triangle_counts,
    triangle_digest,
)


def bvh():
    return (
        b"1HVB"
        + struct.pack("<I9fI3iI", 3, 0, 0, 0, 4, 0, 0, 0, 4, 0, 3, 0, 1, 2, 1)
        + bytes(29)
        + b"BOOF"
        + struct.pack("<I", 712)
    )


def index(entries):
    result = struct.pack("<I", len(entries))
    for pair in entries:
        for value in pair:
            raw = value.encode("ascii")
            result += struct.pack("<I", len(raw)) + raw
    return result + struct.pack("<I", 0)


def test_bvh_geometry_matches_group_coordinates_and_counts():
    root_id, actual = parse_bvh_geometry(bvh())
    expected = triangle_counts(
        np.array([[0, 0, 0], [4, 0, 0], [0, 4, 0]]), np.array([[0, 1, 2]])
    )
    assert root_id == 712 and actual == expected
    assert triangle_digest(actual) == triangle_digest(expected)
    # Duplication must not disappear in set comparisons.
    expected.update(expected.copy())
    assert triangle_digest(actual) != triangle_digest(expected)


@pytest.mark.parametrize(
    "data",
    [b"", b"BAD!", bvh()[:-1], bvh()[:20], bvh().replace(b"BOOF", b"NOPE")],
    ids=["empty", "magic", "root", "vertices", "end"],
)
def test_invalid_geometry_is_not_equivalent(data):
    with pytest.raises(ValueError):
        parse_bvh_geometry(data)


def test_mapping_normalizes_asset_path_but_not_arbitrary_filesystem_paths():
    assert (
        bvh_asset_name(index([("world\\a.wmo", "0001.bvh")]), "WORLD/a.wmo")
        == "0001.bvh"
    )


@pytest.mark.parametrize(
    "leaf", ["../outside", "..\\outside", "E:outside", ".", "..", "x\0"]
)
def test_bvh_mapping_cannot_escape_pack(leaf):
    with pytest.raises(ValueError):
        bvh_asset_name(index([("a.wmo", leaf)]), "a.wmo")


def test_missing_duplicate_and_truncated_mapping_fail():
    for data in (
        index([]),
        index([("a.wmo", "1"), ("A.WMO", "2")]),
        index([("a.wmo", "1")])[:9],
    ):
        with pytest.raises(ValueError):
            bvh_asset_name(data, "a.wmo")
