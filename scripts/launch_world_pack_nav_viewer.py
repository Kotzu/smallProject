from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)
from perfect_assassin.movement.world_pack_viewer import (
    build_world_pack_viewer_launch,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a standalone WorldPack and open its navmesh viewer."
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--viewer", type=Path, required=True)
    parser.add_argument("--map-id", type=int, required=True)
    parser.add_argument("--world-x", type=float, required=True)
    parser.add_argument("--world-y", type=float, required=True)
    parser.add_argument("--world-z", type=float)
    parser.add_argument("--live-state", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    binding = load_world_pack_runtime_profile(
        args.profile,
        store_root=args.store_root,
        profile_schema_path=ROOT
        / "contracts"
        / "world-pack-runtime-profile.schema.json",
        pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
        catalog_schema_path=ROOT
        / "contracts"
        / "client-world-catalog.schema.json",
    )
    launch = build_world_pack_viewer_launch(
        binding,
        viewer_executable=args.viewer,
        map_id=args.map_id,
        world_x=args.world_x,
        world_y=args.world_y,
        world_z=args.world_z,
        live_state_path=args.live_state,
    )
    record: dict[str, object] = {
        "record_type": "world_pack_viewer_launch",
        "schema_version": "1.0",
        "status": "VERIFIED" if args.dry_run else "LAUNCHED",
        "profile_id": launch.profile_id,
        "pack_id": launch.pack_id,
        "content_sha256": launch.content_sha256,
        "map_id": launch.map_id,
        "internal_name": launch.internal_name,
        "client_installation_required": False,
        "server_required": False,
        "emulator_required": False,
        "execution_authority": False,
    }
    if not args.dry_run:
        process = subprocess.Popen(
            launch.arguments,
            cwd=launch.working_directory,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        record["viewer_pid"] = process.pid
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
