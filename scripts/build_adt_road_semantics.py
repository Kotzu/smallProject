from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.adapter.adt_road import build_road_sidecar


# Exact internal names come from Map.dbc. TBC legitimately contains names such
# as "Zul'gurub" and "Stratholme Raid"; keep those while rejecting every path
# separator, drive marker, wildcard, control character, and dot traversal.
MAP_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ '\-]{0,95}$")


def discover_adt_assets(
    source: Path,
    *,
    map_name: str,
) -> tuple[tuple[Path, int, int], ...]:
    if MAP_NAME.fullmatch(map_name) is None or map_name != map_name.rstrip():
        raise ValueError("map name is not a valid client internal name")
    pattern = re.compile(
        rf"^{re.escape(map_name)}_(\d+?)_(\d+?)\.adt$",
        re.IGNORECASE,
    )
    discovered: list[tuple[Path, int, int]] = []
    for path in source.glob(f"{map_name}_*.adt"):
        match = pattern.fullmatch(path.name)
        if match is None:
            continue
        adt_x, adt_y = (int(value) for value in match.groups())
        if not 0 <= adt_x <= 63 or not 0 <= adt_y <= 63:
            raise ValueError(f"ADT coordinates are invalid: {path.name}")
        discovered.append((path, adt_x, adt_y))
    return tuple(sorted(discovered, key=lambda item: (item[1], item[2], item[0].name)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build immutable road-affinity sidecars from client ADT texture layers."
        )
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--map-name", default="Azeroth")
    arguments = parser.parse_args(argv)
    assets = discover_adt_assets(arguments.source, map_name=arguments.map_name)
    count = 0
    for source, adt_x, adt_y in assets:
        destination = (
            arguments.destination
            / f"{arguments.map_name}_{adt_x:02d}_{adt_y:02d}.road"
        )
        semantic = build_road_sidecar(
            source, destination, adt_x=adt_x, adt_y=adt_y
        )
        road_pixels = sum(value > 0 for value in semantic.affinity)
        print(f"{destination.name}: road_pixels={road_pixels}")
        count += 1
    if count == 0:
        raise SystemExit(f"no {arguments.map_name} ADT assets found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
