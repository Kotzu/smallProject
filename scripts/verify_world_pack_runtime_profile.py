from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve and verify one portable standalone WorldPack profile."
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    args = parser.parse_args(argv)
    binding = load_world_pack_runtime_profile(
        args.profile,
        store_root=args.store_root,
        profile_schema_path=ROOT / "contracts" / "world-pack-runtime-profile.schema.json",
        pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
        catalog_schema_path=ROOT / "contracts" / "client-world-catalog.schema.json",
    )
    print(json.dumps({
        "status": "VERIFIED",
        "profile_id": binding.profile_id,
        "pack_id": binding.pack.manifest["pack_id"],
        "content_sha256": binding.pack.manifest["content_sha256"],
        "nav_profile_id": binding.pack.catalog.nav_profile_id,
        "map_ids": [item.map_id for item in binding.pack.catalog.maps],
        "runtime_dependencies": binding.pack.manifest["runtime_dependencies"],
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
