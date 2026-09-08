"""Offline per-group WMO segment hits; no runtime promotion or actor floor claim."""

import argparse
import json
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from perfect_assassin.adapter.surface_association import associate_surfaces
from perfect_assassin.adapter.wmo_bvh_audit import (
    bvh_asset_name,
    parse_bvh_geometry,
    triangle_counts,
    triangle_digest,
)
from perfect_assassin.adapter.wmo_groups import MAX_ROOT_BYTES, parse_wmo_root
from perfect_assassin.adapter.wmo_surfaces import (
    MAX_GROUP_BYTES,
    parse_wmo_group,
    segment_hits,
)


def read_bounded(path, limit):
    with path.open("rb") as stream:
        return stream.read(limit + 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--group-prefix", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--structure-id", required=True)
    parser.add_argument("--start", type=float, nargs=3, required=True)
    parser.add_argument("--end", type=float, nargs=3, required=True)
    parser.add_argument("--pack-root", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--candidate-worker", type=Path)
    parser.add_argument("--worker-sha256")
    parser.add_argument("--candidate-z-hint", type=float)
    parser.add_argument("--matching-tolerance", type=float, default=0.001)
    args = parser.parse_args()
    metadata = parse_wmo_root(read_bounded(args.root, MAX_ROOT_BYTES))
    index = json.loads(args.index.read_text(encoding="utf-8"))
    verified_pack = None
    if args.profile is not None:
        if args.pack_root is None:
            parser.error("--profile requires --pack-root")
        from perfect_assassin.movement.world_pack_runtime import (
            load_world_pack_runtime_profile,
        )
        from perfect_assassin.movement.world_structure_index import (
            load_world_structure_index,
        )

        verified_pack = load_world_pack_runtime_profile(
            args.profile,
            store_root=args.pack_root.resolve().parent,
            profile_schema_path=ROOT
            / "contracts/world-pack-runtime-profile.schema.json",
            pack_schema_path=ROOT / "contracts/standalone-world-pack.schema.json",
            catalog_schema_path=ROOT / "contracts/client-world-catalog.schema.json",
        ).pack
        if verified_pack.pack_root != args.pack_root.resolve():
            raise ValueError("profile resolved a different pack")
        index = load_world_structure_index(
            args.index,
            schema_path=ROOT / "contracts/world-structure-index.schema.json",
            pack=verified_pack,
        ).record
    if args.candidate_worker is not None and (
        verified_pack is None
        or args.candidate_z_hint is None
        or args.worker_sha256 is None
    ):
        parser.error(
            "native association requires verified profile, z hint and worker hash"
        )
    matches = [s for s in index["structures"] if s["structure_id"] == args.structure_id]
    if len(matches) != 1 or matches[0]["kind"] != "WMO":
        raise ValueError("expected one WMO instance")
    groups, hits = [], []
    counts = Counter()
    for expected in metadata.groups:
        path = Path(f"{args.group_prefix}{expected.index:03d}.wmo")
        mesh = parse_wmo_group(read_bounded(path, MAX_GROUP_BYTES), expected)
        counts.update(triangle_counts(mesh.vertices, mesh.indices[mesh.retained]))
        if sum(counts.values()) > 1_000_000:
            raise ValueError("group geometry audit exceeds triangle budget")
        current = segment_hits(
            mesh, matches[0]["transform_matrix"], args.start, args.end
        )
        groups.append(
            {
                "index": mesh.group_index,
                "group_id": mesh.group_id,
                "sha256": mesh.asset_sha256,
                "triangles": len(mesh.indices),
                "retained_triangles": int(mesh.retained.sum()),
                "hit_count": len(current),
            }
        )
        hits.extend(current)
    binding = None
    if args.pack_root is not None:
        index_data = read_bounded(args.pack_root / "BVH/bvh.idx", 16 * 1024 * 1024)
        leaf = bvh_asset_name(index_data, matches[0]["asset_path"])
        bvh_data = read_bounded(args.pack_root / "BVH" / leaf, 128 * 1024 * 1024)
        bvh_root_id, bvh_counts = parse_bvh_geometry(bvh_data)
        binding = {
            "bvh_sha256": sha256(bvh_data).hexdigest(),
            "bvh_index_sha256": sha256(index_data).hexdigest(),
            "root_id_matches": bvh_root_id == metadata.root_id,
            "triangle_multiset_matches": counts == bvh_counts,
            "group_triangle_digest": triangle_digest(counts),
            "bvh_triangle_digest": triangle_digest(bvh_counts),
            "missing_from_groups": sum((bvh_counts - counts).values()),
            "extra_in_groups": sum((counts - bvh_counts).values()),
            "world_pack_seal_verified": verified_pack is not None,
        }
    association = None
    if args.candidate_worker is not None:
        if (
            not binding
            or not binding["root_id_matches"]
            or not binding["triangle_multiset_matches"]
        ):
            raise ValueError("WMO geometry does not match verified pack")
        actual_worker_hash = sha256(
            read_bounded(args.candidate_worker, 64 * 1024 * 1024)
        ).hexdigest()
        if actual_worker_hash != args.worker_sha256:
            raise ValueError("candidate worker hash mismatch")
        if args.start[:2] != args.end[:2]:
            raise ValueError("candidate audit requires a vertical segment")
        sys.path.insert(0, str(ROOT / "integrations/windows-input"))
        from persistent_navmesh_awareness import PersistentNavmeshAwarenessService

        service = PersistentNavmeshAwarenessService(
            worker=args.candidate_worker,
            nav_root=verified_pack.nav_root,
            map_name=index["map_name"],
            protocol_timeout_s=5,
        )
        try:
            sample = service.sample(*args.start[:2], args.candidate_z_hint)
            association = associate_surfaces(
                sample.vertical_candidates,
                query_xy=(sample.source.x, sample.source.y),
                segment_start=args.start,
                segment_end=args.end,
                hits=hits,
                tolerance_yards=args.matching_tolerance,
            )
            association["worker_sha256"] = actual_worker_hash
            association["world_pack_sha256"] = verified_pack.manifest["content_sha256"]
            association["structure_id"] = args.structure_id
            association["map_id"] = index["map_id"]
            association["native_query_observed_monotonic_s"] = (
                sample.observed_monotonic_s
            )
            association["runtime_session_binding"] = None
        finally:
            service.close()
    print(
        json.dumps(
            {
                "schema_version": 1,
                "source": "CLIENT_WMO_GROUP_TRIANGLES",
                "root_sha256": metadata.asset_sha256,
                "geometry_binding_audit": binding,
                "candidate_association": association,
                "groups": groups,
                "start": args.start,
                "end": args.end,
                "hits": sorted(
                    hits,
                    key=lambda h: (
                        h["fraction"],
                        h["group_index"],
                        h["triangle_index"],
                    ),
                ),
                "filter": "NAMIGATOR_MOPY_RETAINED",
                "doodads_included": False,
                "terrain_included": False,
                "coplanar_intersections_resolved": False,
                "asset_instance_binding_verified": False,
                "confirmed_floor_id": None,
                "execution_authority": False,
            },
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
