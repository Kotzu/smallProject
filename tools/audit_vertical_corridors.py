"""Bounded offline candidate-to-candidate corridor audit; no height selection."""

import argparse
from hashlib import sha256
import json
from math import dist, isfinite
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "integrations/windows-input"))
from client_navmesh_backend import ClientAssetNavmeshQuery
from perfect_assassin.adapter.wmo_bundle import read_bounded
from perfect_assassin.movement.client_navmesh import NavPoint
from perfect_assassin.movement.world_pack_runtime import load_world_pack_runtime_profile


def describe_corridor(corridor, start, stop, elapsed_s):
    if not isfinite(elapsed_s) or elapsed_s <= 0:
        raise ValueError("invalid observation interval")
    xyz = lambda p: (p.x, p.y, p.z)
    points = [xyz(p) for p in corridor.points]
    return {"complete": corridor.complete,
            "requested_start": xyz(start), "requested_stop": xyz(stop),
            "resolved_start": xyz(corridor.start), "resolved_stop": xyz(corridor.stop),
            "start_displacement_yards": dist(xyz(start), xyz(corridor.start)),
            "stop_displacement_yards": dist(xyz(stop), xyz(corridor.stop)),
            "path_length_yards": sum(dist(a, b) for a, b in zip(points, points[1:])),
            "straight_line_distance_yards": dist(xyz(start), xyz(stop)),
            "elapsed_s": elapsed_s, "point_count": len(points),
            "topology_shortcut": corridor.topology_gap_direct_shortcut_applied,
            "unresolved_blockers": corridor.doodad_unresolved_segment_count,
            "observed_actor_z": None, "floor_id": None, "execution_authority": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--from-second", type=float, action="append", required=True)
    p.add_argument("--to-second", type=float, required=True)
    p.add_argument("--worker", type=Path, required=True)
    p.add_argument("--worker-sha256", required=True)
    p.add_argument("--profile", type=Path, required=True)
    p.add_argument("--store-root", type=Path, required=True)
    p.add_argument("--map-id", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError("output exists")
    if sha256(read_bounded(args.worker, 32 * 1024 * 1024)).hexdigest() != args.worker_sha256.lower():
        raise ValueError("worker hash mismatch")
    data = read_bounded(args.input, 16 * 1024 * 1024)
    rows = json.loads(data)["rows"]
    if not 1 <= len(rows) <= 64 or len({r["frame_second"] for r in rows}) != len(rows):
        raise ValueError("invalid bounded frame rows")
    target = next(r for r in rows if r["frame_second"] == args.to_second)
    starts = [r for r in rows if r["frame_second"] in args.from_second]
    if len(starts) != len(set(args.from_second)) or not starts:
        raise ValueError("missing requested frame")
    for row in [*starts, target]:
        heights, xy = row["vertical_candidates"]["heights"], row["world_xy"]
        if (not isinstance(heights, list) or not 1 <= len(heights) <= 64
                or not isinstance(xy, list) or len(xy) != 2
                or any(type(v) not in (int, float) or not isfinite(v) or abs(v) > 100000
                       for v in [*heights, *xy, row["frame_second"]])):
            raise ValueError("invalid bounded candidate row")
    if sum(len(r["vertical_candidates"]["heights"]) for r in starts) * len(target["vertical_candidates"]["heights"]) > 12:
        raise ValueError("query count exceeds budget")
    jobs = [(a, z1, z2) for a in starts for z1 in a["vertical_candidates"]["heights"]
            for z2 in target["vertical_candidates"]["heights"]]
    if not 1 <= len(jobs) <= 12 or any(a["frame_second"] >= args.to_second for a in starts):
        raise ValueError("query count or time interval outside budget")
    pack = load_world_pack_runtime_profile(args.profile, store_root=args.store_root,
        profile_schema_path=ROOT / "contracts/world-pack-runtime-profile.schema.json",
        pack_schema_path=ROOT / "contracts/standalone-world-pack.schema.json",
        catalog_schema_path=ROOT / "contracts/client-world-catalog.schema.json").pack
    map_name = next(m.internal_name for m in pack.catalog.maps if m.map_id == args.map_id)
    query = ClientAssetNavmeshQuery(worker=args.worker, nav_root=pack.nav_root, timeout_seconds=5)
    results = []
    for source, z1, z2 in jobs:
        start, stop = NavPoint(*source["world_xy"], z1), NavPoint(*target["world_xy"], z2)
        try:
            corridor = query.find_corridor(map_name=map_name, start=start,
                stop_x=stop.x, stop_y=stop.y, stop_z=stop.z)
            result = {"status": "CONDITIONAL_ROUTE", **describe_corridor(
                corridor, start, stop, args.to_second - source["frame_second"])}
        except Exception as error:
            result = {"status": "QUERY_UNRESOLVED", "error": str(error)[:300]}
        result.update({"from_second": source["frame_second"], "to_second": args.to_second,
                       "candidate_start_z": z1, "candidate_stop_z": z2})
        results.append(result)
        print(json.dumps(result, allow_nan=False), flush=True)
    record = {"source": "OFFLINE_CANDIDATE_CORRIDOR_AUDIT", "results": results,
              "input_sha256": sha256(data).hexdigest(), "worker_sha256": args.worker_sha256.lower(),
              "pack_sha256": pack.manifest["content_sha256"], "map_id": args.map_id,
              "observed_actor_z": None, "floor_id": None, "execution_authority": False}
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(record, output, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
