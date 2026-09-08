"""Create a new partial WMO bundle after verifying its pack, index and geometry."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from perfect_assassin.adapter.wmo_bundle import (
    build_wmo_bundle,
    load_wmo_bundle,
    read_bounded,
)
from perfect_assassin.adapter.wmo_groups import MAX_ROOT_BYTES, parse_wmo_root
from perfect_assassin.movement.world_pack_runtime import load_world_pack_runtime_profile
from perfect_assassin.movement.world_structure_index import load_world_structure_index


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", type=Path, required=True)
    p.add_argument("--store-root", type=Path, required=True)
    p.add_argument("--index", type=Path, required=True)
    p.add_argument("--structure-id", required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--group-prefix", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError("bundle destination already exists")
    pack = load_world_pack_runtime_profile(
        args.profile,
        store_root=args.store_root,
        profile_schema_path=ROOT / "contracts/world-pack-runtime-profile.schema.json",
        pack_schema_path=ROOT / "contracts/standalone-world-pack.schema.json",
        catalog_schema_path=ROOT / "contracts/client-world-catalog.schema.json",
    ).pack
    index = load_world_structure_index(
        args.index,
        schema_path=ROOT / "contracts/world-structure-index.schema.json",
        pack=pack,
    )
    matches = [
        s
        for s in index.record["structures"]
        if s["structure_id"] == args.structure_id and s["kind"] == "WMO"
    ]
    if len(matches) != 1:
        raise ValueError("expected one WMO source instance")
    root = parse_wmo_root(read_bounded(args.root, MAX_ROOT_BYTES))
    digest = build_wmo_bundle(
        args.output,
        pack=pack,
        index=index,
        sources=[
            {
                "asset_path": matches[0]["asset_path"],
                "root": args.root,
                "groups": [
                    Path(f"{args.group_prefix}{g.index:03d}.wmo") for g in root.groups
                ],
            }
        ],
    )
    bundle = load_wmo_bundle(
        args.output, expected_sha256=digest, pack=pack, index=index
    )
    print(
        json.dumps(
            {
                "status": "BUILT_AND_RELOADED",
                "manifest_sha256": digest,
                "covered_model_count": len(bundle.models),
                "map_id": index.record["map_id"],
                "coverage": "LISTED_MODELS_ONLY",
                "execution_authority": False,
            }
        )
    )


if __name__ == "__main__":
    main()
