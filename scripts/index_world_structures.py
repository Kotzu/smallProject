from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)
from perfect_assassin.movement.world_structure_index import (
    WorldStructureIndexError,
    build_world_structure_index_record,
    verify_world_structure_index_binding,
)


def _load_binding(profile: Path, store_root: Path):
    return load_world_pack_runtime_profile(
        profile,
        store_root=store_root,
        profile_schema_path=ROOT / "contracts" / "world-pack-runtime-profile.schema.json",
        pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
        catalog_schema_path=ROOT / "contracts" / "client-world-catalog.schema.json",
    )


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build or verify a standalone WMO/doodad spatial index from one "
            "sealed WorldPack map."
        )
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--map", dest="map_name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    binding = _load_binding(args.profile, args.store_root)
    schema = ContractValidator(ROOT / "contracts" / "world-structure-index.schema.json")
    expected = build_world_structure_index_record(
        binding.pack, map_name=args.map_name,
    )
    schema.validate(expected)
    if args.check:
        try:
            existing = json.loads(args.output.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise WorldStructureIndexError(
                f"cannot read structure index for verification: {error}"
            ) from error
        schema.validate(existing)
        verify_world_structure_index_binding(existing, binding.pack)
        status = "VERIFIED"
    else:
        if args.output.exists():
            raise WorldStructureIndexError(
                "structure index output already exists; use --check or a new path"
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(expected, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        status = "CREATED"
    print(json.dumps({
        "status": status,
        "index_id": expected["index_id"],
        "map_id": expected["map_id"],
        "map_name": expected["map_name"],
        "terrain_tile_count": expected["terrain_tile_count"],
        "nav_tile_count": expected["nav_tile_count"],
        "navigation_coverage": expected["navigation_coverage"],
        "structure_count": expected["structure_count"],
        "wmo_count": expected["wmo_count"],
        "doodad_count": expected["doodad_count"],
        "source_pack_content_sha256": expected["source_pack_content_sha256"],
        "dynamic_entity_knowledge": "NONE",
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
