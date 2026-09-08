"""Read-only asset/recorded-pose replay, not a simulated or live movement run."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "integrations/windows-input")]
from perfect_assassin.movement.continuous_trajectory_follower import ContinuousTrajectoryFollower
from perfect_assassin.movement.predictive_steering import SteeringState
from perfect_assassin.movement.client_navmesh import NavPoint


def replay_geometry(frames, corridor):
    """Compare geometry only: discarded live decisions can alter actuator history."""
    if not frames:
        raise ValueError("no recorded frames")
    follower = ContinuousTrajectoryFollower()
    rows = []
    for frame in frames:
        d = frame["decision_observation"]
        intent = follower.decide(SteeringState(
            d["world_x"], d["world_y"], d["heading_rad"],
            d["speed_world_per_s"], d["no_progress_s"],
        ), corridor)
        expected = frame["lookahead_world"]
        if expected is None or intent.lookahead is None:
            raise ValueError("replay requires nonterminal lookahead evidence")
        actual = [intent.lookahead.x, intent.lookahead.y, intent.lookahead.z]
        errors = [math.dist(actual, expected),
                  abs(intent.cross_track_error_world - frame["cross_track_error_world"]),
                  abs(intent.projected_z_world - frame["projected_z_world"])]
        if not all(math.isfinite(e) for e in errors):
            raise ValueError("nonfinite geometry comparison")
        rows.append({"frame_index": frame["frame_index"],
                     "lookahead_error_yards": errors[0],
                     "cross_track_error_delta_yards": errors[1],
                     "projected_z_error_yards": errors[2]})
    maximum = max(max(row[k] for k in (
        "lookahead_error_yards", "cross_track_error_delta_yards",
        "projected_z_error_yards")) for row in rows)
    return {"frame_count": len(rows), "maximum_geometry_error_yards": maximum,
            "geometry_matches": maximum <= 1e-6, "frames": rows,
            "actuator_commands_replayed": False, "execution_authority": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--nav-root", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--through-frame", type=int, required=True)
    parser.add_argument("--sample-frames", type=int, nargs="*", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.through_frame <= 18000:
        parser.error("--through-frame must be in [1, 18000]")
    if any(index < 1 or index > args.through_frame for index in args.sample_frames):
        parser.error("sample frames must be inside the selected prefix")
    r = json.loads(args.result.read_text(encoding="utf-8"))
    manifest = json.loads((args.nav_root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["content_sha256"] != r["world_pack_content_sha256"]:
        raise ValueError("world-pack manifest differs from recorded evidence")
    frames = [a for a in r["actions"] if a["kind"] == "CONTINUOUS_FRAME"
              and a["frame_index"] <= args.through_frame]
    if not frames or frames[-1]["frame_index"] != args.through_frame:
        raise ValueError("requested prefix is not completely present in recording")
    egress = next(a for a in r["actions"] if a["kind"] == "STRUCTURE_EGRESS_PLANNED")
    # MovementEngine retains the boundary approach, not a newly queried direct
    # path to the outside anchor. Confusing these produces a different corridor.
    goal = egress["opening_world"]
    d = frames[0]["decision_observation"]
    layer = next(a["selected_z"] for a in r["actions"]
                 if a["kind"] == "INITIAL_VERTICAL_LAYER_SELECTED")
    from client_navmesh_backend import ClientAssetNavmeshQuery
    query = ClientAssetNavmeshQuery(worker=args.worker, nav_root=args.nav_root,
                                   timeout_seconds=4)
    corridor = query.find_corridor(map_name=r["map"],
        start=NavPoint(d["world_x"], d["world_y"], layer),
        stop_x=goal[0], stop_y=goal[1], stop_z=goal[2])
    report = replay_geometry(frames, corridor)
    report.update(run_id=r["run_id"], record_type="structure_egress_geometry_replay",
                  scope="offline_asset_requery_and_recorded_pose",
                  manifest_matches=True, full_pack_rehashed=False,
                  physical_contact_proven=False, clearance_samples=[])
    # Never interpret a freshly queried path as the historical one unless its
    # recorded geometry metrics agree across the entire selected prefix.
    if report["geometry_matches"]:
        follower = ContinuousTrajectoryFollower()
        by_index = {f["frame_index"]: f for f in frames}
        for index in args.sample_frames:
            f = by_index[index]
            d = f["decision_observation"]
            projection = follower._point_at_progress(corridor, f["corridor_progress_world"])
            row = {"frame_index": index, "cross_track_yards": f["cross_track_error_world"]}
            for label, point in (("decision", NavPoint(d["world_x"], d["world_y"], f["projected_z_world"])),
                                 ("path_projection", projection)):
                local = query.find_corridor(map_name=r["map"], start=point,
                    stop_x=point.x, stop_y=point.y, stop_z=point.z)
                row[label] = {"minimum_radial_clearance_yards": min(
                    p.clearance_yards for p in local.start_awareness.radial_probes),
                    "resolved_z_delta_yards": local.start.z - point.z,
                    "source": "offline_asset_requery_not_physical_body_clearance"}
            report["clearance_samples"].append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "frames"}, indent=2))
    return 0 if report["geometry_matches"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
