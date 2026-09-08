"""Offline group-bound candidate audit. No actor localization or client input."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from perfect_assassin.adapter.wmo_groups import (
    MAX_ROOT_BYTES,
    parse_wmo_root,
    world_to_model,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--structure-id", required=True)
    parser.add_argument("--point", type=float, nargs=3, action="append", required=True)
    args = parser.parse_args()
    if len(args.point) > 32:
        raise ValueError("at most 32 audit points")
    with args.asset.open("rb") as stream:
        metadata = parse_wmo_root(stream.read(MAX_ROOT_BYTES + 1))
    index = json.loads(args.index.read_text(encoding="utf-8"))
    structures = [
        s for s in index["structures"] if s["structure_id"] == args.structure_id
    ]
    if len(structures) != 1 or structures[0]["kind"] != "WMO":
        raise ValueError("expected one WMO instance")
    structure = structures[0]
    observations = []
    for point in args.point:
        local = world_to_model(point, structure["transform_matrix"])
        observations.append(
            {
                "world_point": point,
                "model_point": local,
                "bound_candidates": [
                    g.index for g in metadata.groups if g.contains_bounds(local)
                ],
            }
        )
    print(
        json.dumps(
            {
                "source": "CLIENT_WMO_ROOT_METADATA",
                "schema_version": 1,
                "asset_sha256": metadata.asset_sha256,
                "root_id": metadata.root_id,
                "claimed_asset_path": structure["asset_path"],
                "asset_instance_binding_verified": False,
                "groups": [
                    {
                        "index": g.index,
                        "raw_flags": g.flags,
                        "flag_evidence": g.flag_evidence,
                        "min": g.minimum,
                        "max": g.maximum,
                    }
                    for g in metadata.groups
                ],
                "observations": observations,
                "confirmed_floor_id": None,
                "group_membership_confirmed": False,
                "execution_authority": False,
            },
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
