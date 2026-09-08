from __future__ import annotations

import argparse
import json
from math import isfinite
from pathlib import Path
import sys
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_navmesh_roaming import (
    DEFAULT_ZONE_TRANSFORM_CATALOG,
    LiveCoordinatePoseSource,
    _load_zone_transform,
    _position,
)


DEFAULT_AUTHORIZATION = (
    ROOT / "data" / "runtime" / "operator" / "tbc_243_lab.active.json"
)
DEFAULT_RECEIPT = (
    ROOT / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
)


def _read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    return value


def pose_record(
    observation: dict[str, object], *, expected_zone_index: int,
    map_id: int = 0,
    map_name: str = "Azeroth",
    transform_catalog: Path = DEFAULT_ZONE_TRANSFORM_CATALOG,
) -> dict[str, object]:
    position = observation.get("position")
    if not isinstance(position, dict):
        raise RuntimeError("coordinate HUD observation is incomplete")
    continent_index = position.get("continent_index")
    # Older HUD fixture records predate the explicit continent field.  Keep
    # their Azeroth compatibility while requiring the field for any new map.
    if continent_index is None and map_id == 0:
        continent_index = 2
    if type(continent_index) is not int or continent_index < 0:
        raise RuntimeError("coordinate HUD continent index is invalid")
    transform = _load_zone_transform(
        transform_catalog,
        map_id=map_id,
        zone_index=expected_zone_index,
    )
    normalized_x, normalized_y, world_x, world_y = _position(
        observation,
        expected_zone_index=expected_zone_index,
        transform=transform,
        expected_map_id=map_id,
    )
    timing = observation.get("timing")
    if not isinstance(timing, dict) or not isinstance(position, dict):
        raise RuntimeError("coordinate HUD observation is incomplete")
    observed_s = float(timing["observed_monotonic_s"])
    facing = position.get("facing_rad")
    if not all(isfinite(value) for value in (
        normalized_x, normalized_y, world_x, world_y, observed_s,
    )):
        raise RuntimeError("coordinate HUD observation is non-finite")
    if facing is not None and not isfinite(float(facing)):
        raise RuntimeError("coordinate HUD facing is non-finite")
    return {
        "record_type": "nav_viewer_pose",
        "schema_version": "1.0",
        "observed_monotonic_s": observed_s,
        "map_name": map_name,
        "continent_index": continent_index,
        "zone_index": expected_zone_index,
        "normalized_position": [normalized_x, normalized_y],
        "world_position": [world_x, world_y],
        "facing_rad": None if facing is None else float(facing),
        "source": "visible_coordinate_hud_read_only",
        "execution_authority": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read one fresh client-visible pose for the external 3D nav viewer."
    )
    parser.add_argument(
        "--session-authorization-file", type=Path, default=DEFAULT_AUTHORIZATION,
    )
    parser.add_argument("--session-receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument(
        "--expected-zone-index", type=int, choices=range(0, 65_536), default=25,
    )
    parser.add_argument("--map-id", type=int, choices=range(0, 65_536), default=0)
    parser.add_argument("--map-name", default="Azeroth")
    parser.add_argument(
        "--zone-transform-catalog", type=Path,
        default=DEFAULT_ZONE_TRANSFORM_CATALOG,
    )
    return parser


def capture_pose_record(
    *,
    authorization_file: Path,
    receipt_file: Path,
    expected_zone_index: int,
    map_id: int = 0,
    map_name: str = "Azeroth",
    transform_catalog: Path = DEFAULT_ZONE_TRANSFORM_CATALOG,
) -> dict[str, object]:
    receipt = _read_object(receipt_file)
    source = LiveCoordinatePoseSource(
        authorization_file=authorization_file,
        receipt_file=receipt_file,
        receipt=receipt,
        session_id=f"session:nav-viewer-pose:{uuid4()}",
    )
    source.open()
    try:
        observation = source.next_observation()
    finally:
        source.close()
    return pose_record(
        observation,
        expected_zone_index=expected_zone_index,
        map_id=map_id,
        map_name=map_name,
        transform_catalog=transform_catalog,
    )


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    record = capture_pose_record(
        authorization_file=args.session_authorization_file,
        receipt_file=args.session_receipt,
        expected_zone_index=args.expected_zone_index,
        map_id=args.map_id,
        map_name=args.map_name,
        transform_catalog=args.zone_transform_catalog,
    )
    print(json.dumps(
        record,
        ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
