from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from perfect_assassin.movement.standalone_world_pack import (
    StandaloneWorldPackError,
)
from perfect_assassin.movement.world_pack_runtime import WorldPackRuntimeBinding


@dataclass(frozen=True, slots=True)
class WorldPackViewerLaunch:
    executable: Path
    working_directory: Path
    nav_root: Path
    arguments: tuple[str, ...]
    profile_id: str
    pack_id: str
    content_sha256: str
    map_id: int
    internal_name: str


def build_world_pack_viewer_launch(
    binding: WorldPackRuntimeBinding,
    *,
    viewer_executable: Path,
    map_id: int,
    world_x: float,
    world_y: float,
    world_z: float | None = None,
    live_state_path: Path | None = None,
) -> WorldPackViewerLaunch:
    viewer_executable = viewer_executable.resolve()
    if not viewer_executable.is_file():
        raise StandaloneWorldPackError(
            "standalone WorldPack viewer executable is unavailable"
        )
    coordinates = (world_x, world_y) if world_z is None else (
        world_x,
        world_y,
        world_z,
    )
    if not all(isfinite(float(value)) for value in coordinates):
        raise StandaloneWorldPackError("viewer world position must be finite")

    matches = [item for item in binding.pack.catalog.maps if item.map_id == map_id]
    if len(matches) != 1:
        raise StandaloneWorldPackError(
            "requested viewer map is not uniquely present in the WorldPack"
        )
    selected = matches[0]
    manifest = binding.pack.manifest
    arguments = [
        str(viewer_executable),
        str(binding.pack.nav_root),
        "--world-pack",
        f"--- {selected.internal_name}",
        f"{float(world_x):.6f}",
        f"{float(world_y):.6f}",
    ]
    if live_state_path is not None:
        arguments.extend(
            [
                "auto" if world_z is None else f"{float(world_z):.6f}",
                str(live_state_path),
            ]
        )
    elif world_z is not None:
        arguments.append(f"{float(world_z):.6f}")

    return WorldPackViewerLaunch(
        executable=viewer_executable,
        working_directory=viewer_executable.parent,
        nav_root=binding.pack.nav_root,
        arguments=tuple(arguments),
        profile_id=binding.profile_id,
        pack_id=str(manifest["pack_id"]),
        content_sha256=str(manifest["content_sha256"]),
        map_id=selected.map_id,
        internal_name=selected.internal_name,
    )
