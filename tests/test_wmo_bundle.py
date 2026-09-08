import json
import struct
from hashlib import sha256

import pytest
from test_wmo_bvh_audit import bvh
from test_wmo_bvh_audit import index as bvh_index
from test_wmo_groups import root
from test_wmo_surfaces import EXPECTED, IDENTITY, group

from perfect_assassin.adapter.vertical_candidates import VerticalSurfaceCandidates
from perfect_assassin.adapter.wmo_bundle import (
    build_wmo_bundle,
    canonical,
    load_wmo_bundle,
)
from perfect_assassin.movement.standalone_world_pack import VerifiedStandaloneWorldPack
from perfect_assassin.movement.world_structure_index import (
    VerifiedWorldStructureIndex,
    WorldStructureSpatialIndex,
)


@pytest.fixture
def context(tmp_path):
    # Synthetic typed context; real CLI invokes the production pack/index verifiers.
    pack_dir = tmp_path / "pack"
    (pack_dir / "BVH").mkdir(parents=True)
    (pack_dir / "BVH/bvh.idx").write_bytes(bvh_index([("a.wmo", "a.bvh")]))
    (pack_dir / "BVH/a.bvh").write_bytes(bvh()[:-4] + struct.pack("<I", 42))
    pack = VerifiedStandaloneWorldPack(pack_dir, {"content_sha256": "a" * 64}, None)
    structures = []
    for instance_id, asset in enumerate(("a.wmo", "b.wmo")):
        structures.append(
            {
                "structure_id": f"0:wmo:{instance_id}",
                "instance_id": instance_id,
                "kind": "WMO",
                "asset_path": asset,
                "asset_tokens": [],
                "transform_matrix": IDENTITY,
                "bounds": {
                    "min": {"x": -10, "y": -10, "z": -10},
                    "max": {"x": 10, "y": 10, "z": 10},
                },
                "center": {"x": 0, "y": 0, "z": 0},
                "horizontal_radius_yards": 15,
                "collision_role": "ENCLOSURE_OR_LARGE_STRUCTURE",
                "nav_coverage": "FULL",
            }
        )
    record = {
        "map_id": 0,
        "source_pack_content_sha256": "a" * 64,
        "structure_count": 2,
        "structures": structures,
    }
    index = VerifiedWorldStructureIndex(
        record, WorldStructureSpatialIndex.from_record(record)
    )
    source_root = tmp_path / "root.wmo"
    source_group = tmp_path / "group.wmo"
    source_root.write_bytes(
        root(((EXPECTED.flags, EXPECTED.minimum + EXPECTED.maximum),))
    )
    source_group.write_bytes(group())
    sources = [{"asset_path": "a.wmo", "root": source_root, "groups": [source_group]}]
    return pack, index, sources, tmp_path / "bundle"


def build(context):
    pack, index, sources, output = context
    digest = build_wmo_bundle(output, sources=sources, pack=pack, index=index)
    return load_wmo_bundle(
        output, expected_sha256=digest, pack=pack, index=index
    ), digest


def test_build_reload_query_partial_coverage_and_outside_world(context):
    bundle, _ = build(context)
    candidates = VerticalSurfaceCandidates((0, 20), 20)
    result = bundle.query(map_id=0, xy=(1, 2), candidates=candidates)
    assert result["coverage"] == "LISTED_MODELS_ONLY"
    assert result["column_wmo_count"] == 2
    assert result["uncovered_structure_ids"] == ["0:wmo:1"]
    association = result["structures"][0]["association"]
    assert [c["status"] for c in association["candidates"]] == [
        "MATCHED_GEOMETRY",
        "OUTSIDE_TESTED_SEGMENT",
    ]
    assert association["selected_surface_z_unchanged"] == 20
    assert (
        result["confirmed_floor_id"] is None and result["execution_authority"] is False
    )
    outside = bundle.query(map_id=0, xy=(100, 100), candidates=candidates)
    assert outside["structures"] == [] and outside["column_wmo_count"] == 0
    assert outside["terrain_and_doodads_checked"] is False


def test_changed_bytes_and_wrong_external_hash_fail(context):
    _, digest = build(context)
    pack, index, _, output = context
    with pytest.raises(ValueError, match="manifest hash"):
        load_wmo_bundle(output, expected_sha256="0" * 64, pack=pack, index=index)
    artifact = output / "model_0_000.wmo"
    artifact.write_bytes(artifact.read_bytes() + b"x")
    with pytest.raises(ValueError, match="artifact hash"):
        load_wmo_bundle(output, expected_sha256=digest, pack=pack, index=index)


@pytest.mark.parametrize(
    "field,value",
    [
        ("map_id", 1),
        ("coverage", "ALL_WORLD"),
        ("execution_authority", True),
        ("schema_version", True),
        ("pack_sha256", "b" * 64),
        ("index_sha256", "c" * 64),
    ],
)
def test_even_rehashed_manifest_cannot_change_context(context, field, value):
    build(context)
    pack, index, _, output = context
    path = output / "manifest.json"
    record = json.loads(path.read_bytes())
    record[field] = value
    raw = canonical(record)
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="provenance"):
        load_wmo_bundle(
            output, expected_sha256=sha256(raw).hexdigest(), pack=pack, index=index
        )


def test_path_escape_is_rejected_even_with_new_manifest_hash(context):
    build(context)
    pack, index, _, output = context
    path = output / "manifest.json"
    record = json.loads(path.read_bytes())
    record["models"][0]["root"]["file"] = "../root.wmo"
    raw = canonical(record)
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="filename"):
        load_wmo_bundle(
            output, expected_sha256=sha256(raw).hexdigest(), pack=pack, index=index
        )


def test_incomplete_model_fails_before_destination_is_created(context):
    pack, index, sources, output = context
    sources[0]["groups"] = []
    with pytest.raises(ValueError, match="every group"):
        build_wmo_bundle(output, sources=sources, pack=pack, index=index)
    assert not output.exists()


def test_existing_bundle_is_never_overwritten(context):
    _, digest = build(context)
    pack, index, sources, output = context
    with pytest.raises(FileExistsError):
        build_wmo_bundle(output, sources=sources, pack=pack, index=index)
    assert sha256((output / "manifest.json").read_bytes()).hexdigest() == digest


def test_bvh_change_rejected_and_map_gate(context):
    bundle, digest = build(context)
    pack, index, _, output = context
    with pytest.raises(ValueError, match="map mismatch"):
        bundle.query(map_id=1, xy=(1, 2), candidates=VerticalSurfaceCandidates((0,), 0))
    path = pack.pack_root / "BVH/a.bvh"
    data = bytearray(path.read_bytes())
    struct.pack_into("<f", data, 8, 1.0)
    path.write_bytes(data)
    with pytest.raises(ValueError, match="do not match"):
        load_wmo_bundle(output, expected_sha256=digest, pack=pack, index=index)
