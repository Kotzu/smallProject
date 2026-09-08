"""Pinned, partial-coverage WMO metadata bundle for background observation.

Public loaders require an already verified pack and rebuilt structure index.
The expected manifest hash is supplied externally, never trusted from itself.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from perfect_assassin.movement.standalone_world_pack import VerifiedStandaloneWorldPack
from perfect_assassin.movement.world_structure_index import VerifiedWorldStructureIndex

from .surface_association import associate_surfaces
from .wmo_bvh_audit import bvh_asset_name, parse_bvh_geometry, triangle_counts
from .wmo_groups import MAX_ROOT_BYTES, parse_wmo_root
from .wmo_surfaces import MAX_GROUP_BYTES, parse_wmo_group, segment_hits

MAX_TOTAL_BYTES = 256 * 1024 * 1024


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def read_bounded(path, limit):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("bundle input exceeds byte budget")
    return data


def _context(pack, index):
    if not isinstance(pack, VerifiedStandaloneWorldPack) or not isinstance(
        index, VerifiedWorldStructureIndex
    ):
        raise TypeError("bundle requires verified pack/index objects")
    if index.record["source_pack_content_sha256"] != pack.manifest["content_sha256"]:
        raise ValueError("bundle index belongs to another pack")
    return sha256(canonical(dict(index.record))).hexdigest()


def _model(asset_path, root_data, group_data, pack):
    root = parse_wmo_root(root_data)
    if len(group_data) != len(root.groups):
        raise ValueError("bundle must include every group of each listed model")
    meshes, counts = [], Counter()
    for expected, data in zip(root.groups, group_data):
        mesh = parse_wmo_group(data, expected)
        counts.update(triangle_counts(mesh.vertices, mesh.indices[mesh.retained]))
        if sum(counts.values()) > 1_000_000:
            raise ValueError("bundle model exceeds triangle budget")
        meshes.append(mesh)
    leaf = bvh_asset_name(
        read_bounded(pack.pack_root / "BVH/bvh.idx", 16 * 1024 * 1024), asset_path
    )
    bvh_data = read_bounded(pack.pack_root / "BVH" / leaf, 128 * 1024 * 1024)
    root_id, expected_counts = parse_bvh_geometry(bvh_data)
    if root_id != root.root_id or counts != expected_counts:
        raise ValueError("bundle triangles/root do not match verified pack BVH")
    return tuple(meshes), sha256(bvh_data).hexdigest()


@dataclass(frozen=True)
class WmoBundle:
    manifest_sha256: str
    pack_sha256: str
    index: VerifiedWorldStructureIndex
    models: dict
    structures: dict

    def query(self, *, map_id, xy, candidates):
        if type(map_id) is not int or map_id != self.index.record["map_id"]:
            raise ValueError("WMO bundle map mismatch")
        nearby = self.index.spatial.nearby(
            x=xy[0], y=xy[1], radius_yards=0, kinds=("WMO",)
        )
        if len(nearby) > 16:
            raise ValueError("WMO column exceeds instance budget")
        results, missing = [], []
        for nearby_hit in nearby:
            structure = self.structures[nearby_hit.structure.structure_id]
            meshes = self.models.get(structure["asset_path"])
            if meshes is None:
                missing.append(structure["structure_id"])
                continue
            # Finite world bounds from the verified instance; never scan to infinity.
            low, high = (
                structure["bounds"]["min"]["z"] - 1,
                structure["bounds"]["max"]["z"] + 1,
            )
            start, end = (*xy, high), (*xy, low)
            hits = []
            for mesh in meshes:
                hits.extend(
                    segment_hits(mesh, structure["transform_matrix"], start, end)
                )
                if len(hits) > 4096:
                    raise ValueError("WMO column hit budget exceeded")
            association = associate_surfaces(
                candidates,
                query_xy=xy,
                segment_start=start,
                segment_end=end,
                hits=hits,
                tolerance_yards=0.001,
            )
            results.append(
                {"structure_id": structure["structure_id"], "association": association}
            )
        return {
            "schema_version": 1,
            "source": "VERIFIED_WMO_GROUP_BUNDLE",
            "bundle_sha256": self.manifest_sha256,
            "world_pack_sha256": self.pack_sha256,
            "map_id": map_id,
            "query_xy": list(xy),
            "coverage": "LISTED_MODELS_ONLY",
            "loaded_model_count": len(self.models),
            "column_wmo_count": len(nearby),
            "uncovered_structure_ids": missing,
            "structures": results,
            "confirmed_floor_id": None,
            "execution_authority": False,
            "terrain_and_doodads_checked": False,
        }


def load_wmo_bundle(directory, *, expected_sha256, pack, index):
    index_hash = _context(pack, index)
    directory = Path(directory).resolve()
    raw = read_bounded(directory / "manifest.json", 1024 * 1024)
    if (
        not isinstance(expected_sha256, str)
        or not re.fullmatch("[a-f0-9]{64}", expected_sha256)
        or sha256(raw).hexdigest() != expected_sha256
    ):
        raise ValueError("WMO bundle manifest hash mismatch")
    record = json.loads(raw)
    if not isinstance(record, dict) or set(record) != {
        "schema_version",
        "source",
        "pack_sha256",
        "index_sha256",
        "map_id",
        "coverage",
        "models",
        "execution_authority",
    }:
        raise ValueError("invalid WMO bundle manifest fields")
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != 1
        or record["source"] != "CLIENT_WMO_ASSETS"
        or record["execution_authority"] is not False
        or record["coverage"] != "LISTED_MODELS_ONLY"
        or record["pack_sha256"] != pack.manifest["content_sha256"]
        or record["index_sha256"] != index_hash
        or type(record["map_id"]) is not int
        or record["map_id"] != index.record["map_id"]
    ):
        raise ValueError("WMO bundle provenance/coverage mismatch")
    if not isinstance(record["models"], list) or not 1 <= len(record["models"]) <= 64:
        raise ValueError("invalid WMO model count")
    known = {s["asset_path"] for s in index.record["structures"] if s["kind"] == "WMO"}
    files, models = set(), {}
    total = 0

    def artifact(item, limit):
        nonlocal total
        if not isinstance(item, dict) or set(item) != {"file", "sha256"}:
            raise ValueError("invalid bundle artifact")
        name = item["file"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-zA-Z0-9_-]+\.wmo", name)
            or name in files
        ):
            raise ValueError("unsafe or reused bundle filename")
        path = directory / name
        if path.is_symlink() or path.resolve().parent != directory:
            raise ValueError("bundle artifact escapes its directory")
        files.add(name)
        data = read_bounded(path, min(limit, MAX_TOTAL_BYTES - total))
        total += len(data)
        if sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("bundle artifact hash mismatch")
        return data

    for entry in record["models"]:
        if not isinstance(entry, dict) or set(entry) != {
            "asset_path",
            "root",
            "groups",
            "bvh_sha256",
        }:
            raise ValueError("invalid bundle model")
        asset_path = entry["asset_path"]
        if (
            not isinstance(asset_path, str)
            or asset_path not in known
            or asset_path in models
        ):
            raise ValueError("unknown/duplicate WMO model")
        if not isinstance(entry["groups"], list) or len(entry["groups"]) > 512:
            raise ValueError("invalid bundle groups")
        root_data = artifact(entry["root"], MAX_ROOT_BYTES)
        group_data = [artifact(g, MAX_GROUP_BYTES) for g in entry["groups"]]
        meshes, bvh_hash = _model(asset_path, root_data, group_data, pack)
        if bvh_hash != entry["bvh_sha256"]:
            raise ValueError("bundle BVH binding changed")
        models[asset_path] = meshes
    return WmoBundle(
        expected_sha256,
        record["pack_sha256"],
        index,
        models,
        {
            s["structure_id"]: s
            for s in index.record["structures"]
            if s["kind"] == "WMO"
        },
    )


def build_wmo_bundle(directory, *, sources, pack, index):
    """Sources contain asset_path, root Path and group Paths in root index order."""
    index_hash = _context(pack, index)
    if not 1 <= len(sources) <= 64:
        raise ValueError("invalid bundle source count")
    known = {s["asset_path"] for s in index.record["structures"] if s["kind"] == "WMO"}
    payloads, entries, seen = {}, [], set()
    total = 0

    def capture(path, name, limit):
        nonlocal total
        data = read_bounded(path, min(limit, MAX_TOTAL_BYTES - total))
        total += len(data)
        payloads[name] = data
        return {"file": name, "sha256": sha256(data).hexdigest()}

    for number, source in enumerate(sources):
        asset = source["asset_path"]
        if asset not in known or asset in seen:
            raise ValueError("unknown/duplicate bundle source")
        seen.add(asset)
        if len(source["groups"]) > 512:
            raise ValueError("too many source groups")
        root = capture(source["root"], f"model_{number}_root.wmo", MAX_ROOT_BYTES)
        groups = [
            capture(p, f"model_{number}_{i:03d}.wmo", MAX_GROUP_BYTES)
            for i, p in enumerate(source["groups"])
        ]
        _, bvh_hash = _model(
            asset, payloads[root["file"]], [payloads[g["file"]] for g in groups], pack
        )
        entries.append(
            {
                "asset_path": asset,
                "root": root,
                "groups": groups,
                "bvh_sha256": bvh_hash,
            }
        )
    record = {
        "schema_version": 1,
        "source": "CLIENT_WMO_ASSETS",
        "pack_sha256": pack.manifest["content_sha256"],
        "index_sha256": index_hash,
        "map_id": index.record["map_id"],
        "coverage": "LISTED_MODELS_ONLY",
        "models": entries,
        "execution_authority": False,
    }
    raw = canonical(record)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    for name, data in payloads.items():
        with (directory / name).open("xb") as stream:
            stream.write(data)
    with (directory / "manifest.json").open("xb") as stream:
        stream.write(raw)
    return sha256(raw).hexdigest()
