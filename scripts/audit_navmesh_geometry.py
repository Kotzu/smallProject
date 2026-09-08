from __future__ import annotations

import argparse
import hashlib
import json
from math import isfinite
from multiprocessing import get_context
import os
from pathlib import Path
import struct
import sys
import tempfile
from typing import Any, Mapping
import zlib


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_world_catalog import (
    ClientWorldCatalog,
    decode_client_world_catalog,
)
from perfect_assassin.movement.navigation_contracts import (
    Bounds3,
    NavigationContractError,
    NavigationMeshTile,
    Vector3,
    verify_navigation_tile_payload,
)


CATALOG_SCHEMA = ROOT / "contracts" / "client-world-catalog.schema.json"
REPORT_SCHEMA = ROOT / "contracts" / "navmesh-geometry-validation-report.schema.json"
VALIDATOR_ID = "perfect-assassin.namigator-detour-v7-structural-v2"
_HEADER_FORMAT = "<15i10f"
_HEADER_SIZE = struct.calcsize(_HEADER_FORMAT)
_NAMIGATOR_ADT_HEADER_FORMAT = "<6I"
_NAMIGATOR_ADT_HEADER_SIZE = struct.calcsize(_NAMIGATOR_ADT_HEADER_FORMAT)
_NAMIGATOR_FILE_SIGNATURE = struct.unpack("<I", b"VANN")[0]
_NAMIGATOR_FILE_VERSION = struct.unpack("<I", b"5100")[0]
_NAMIGATOR_FILE_ADT = struct.unpack("<I", b"\x00TDA")[0]
_NAMIGATOR_TILES_PER_ADT = 16
_NAMIGATOR_TILE_COUNT = _NAMIGATOR_TILES_PER_ADT ** 2
_NAMIGATOR_QUAD_HOLE_BYTES = 64
_NAMIGATOR_QUAD_HEIGHT_BYTES = 145 * struct.calcsize("<f")
# Full-continent auditing found a legitimate dense ADT just below 197 MiB.
# Keep a hard, per-file allocation ceiling with enough headroom for such tiles;
# structure/count budgets below still reject malformed expansion inside it.
_MAX_DECOMPRESSED_NAMIGATOR_BYTES = 256 * 1024 * 1024
_MAX_HEIGHTFIELD_DIMENSION = 512
_MAX_HEIGHTFIELD_SPANS_PER_COLUMN = 4096
_MAX_HEIGHTFIELD_SPANS_PER_TILE = 2_000_000


class _PayloadReader:
    """Bounds-checked little-endian reader for a decompressed Namigator ADT."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.position = 0

    def take(self, size: int) -> bytes:
        if size < 0 or size > len(self.payload) - self.position:
            raise NavigationContractError("Namigator ADT payload is truncated")
        result = self.payload[self.position : self.position + size]
        self.position += size
        return result

    def skip(self, size: int) -> None:
        """Advance across a validated diagnostic section without copying it."""

        if size < 0 or size > len(self.payload) - self.position:
            raise NavigationContractError("Namigator ADT payload is truncated")
        self.position += size

    def unpack(self, format_string: str) -> tuple[Any, ...]:
        size = struct.calcsize(format_string)
        return struct.unpack(format_string, self.take(size))

    def u32(self) -> int:
        return int(self.unpack("<I")[0])

    def i32(self) -> int:
        return int(self.unpack("<i")[0])


def _decompress_namigator(payload: bytes) -> bytes:
    """Decode exactly one bounded zlib stream; reject trailing or truncated data."""

    decompressor = zlib.decompressobj()
    remaining = payload
    decoded = bytearray()
    while remaining:
        room = _MAX_DECOMPRESSED_NAMIGATOR_BYTES - len(decoded)
        if room <= 0:
            raise NavigationContractError("Namigator ADT decompression exceeds safety limit")
        chunk = decompressor.decompress(remaining, room)
        decoded.extend(chunk)
        if decompressor.unconsumed_tail:
            remaining = decompressor.unconsumed_tail
            continue
        remaining = b""
    room = _MAX_DECOMPRESSED_NAMIGATOR_BYTES - len(decoded)
    decoded.extend(decompressor.flush(room))
    if len(decoded) > _MAX_DECOMPRESSED_NAMIGATOR_BYTES:
        raise NavigationContractError("Namigator ADT decompression exceeds safety limit")
    if not decompressor.eof or decompressor.unused_data:
        raise NavigationContractError("Namigator ADT zlib stream is incomplete or has trailing bytes")
    return bytes(decoded)


def _normalized_detour_payload(payload: bytes) -> bytes:
    """Normalize Namigator's zeroed 64-bit link scratch area to the v7 verifier.

    Namigator is built with ``DT_POLYREF64``.  Its serialized ``dtLink`` is
    therefore 16 bytes rather than the 12-byte layout used by the portable
    verifier.  Before ``addTile`` both variants are required to be all zero;
    only that scratch area differs.  Geometry, polygon, BV and detail sections
    are preserved byte-for-byte and are then checked by the shared verifier.
    """

    if len(payload) < _HEADER_SIZE:
        raise NavigationContractError("navigation tile payload has no Detour header")
    header = struct.unpack_from(_HEADER_FORMAT, payload, 0)
    polygon_count, vertex_count, max_link_count = header[6], header[7], header[8]
    detail_mesh_count, detail_vertex_count = header[9], header[10]
    detail_triangle_count, bv_node_count = header[11], header[12]
    offmesh_connection_count = header[13]
    section_counts = header[6:15]
    if any(count < 0 for count in section_counts):
        raise NavigationContractError("navigation tile payload contains a negative section count")
    fixed_size = (
        _HEADER_SIZE
        + vertex_count * 12
        + polygon_count * 32
        + detail_mesh_count * 12
        + detail_vertex_count * 12
        + detail_triangle_count * 4
        + bv_node_count * 16
        + offmesh_connection_count * 36
    )
    size_32 = fixed_size + max_link_count * 12
    size_64 = fixed_size + max_link_count * 16
    if len(payload) == size_32:
        return payload
    if len(payload) != size_64:
        raise NavigationContractError(
            "navigation tile payload size contradicts pinned Detour v7 layouts"
        )
    link_start = _HEADER_SIZE + vertex_count * 12 + polygon_count * 32
    link_end = link_start + max_link_count * 16
    if any(payload[link_start:link_end]):
        raise NavigationContractError(
            "navigation tile payload link scratch space is not zero before addTile"
        )
    normalized = b"".join((
        payload[:link_start],
        bytes(max_link_count * 12),
        payload[link_end:],
    ))
    # Recast quantizes geometry to the tile's ``bvQuantFactor`` grid.  The
    # native output can consequently lie up to one quantization unit outside a
    # mathematical tile edge (for example 11233.333 instead of 11233.332).
    # Prove that bounded condition against the original header, then widen only
    # the in-memory verifier manifest by that same one unit.  This is not a
    # lossy conversion: every geometry byte remains untouched.
    normalized_header = struct.unpack_from(_HEADER_FORMAT, normalized, 0)
    quantization = normalized_header[24]
    if not isfinite(quantization) or quantization <= 0.0:
        raise NavigationContractError("navigation tile payload quantization is invalid")
    tolerance = max(1e-5, (1.0 / quantization) + 1e-5)
    header_minimum = normalized_header[18:21]
    header_maximum = normalized_header[21:24]
    vertex_offset = _HEADER_SIZE
    detail_vertex_offset = (
        vertex_offset
        + vertex_count * 12
        + polygon_count * 32
        + max_link_count * 12
        + detail_mesh_count * 12
    )
    def verify_quantized_vertex(vertex: tuple[float, float, float]) -> None:
        if any(not isfinite(value) for value in vertex) or any(
            value < minimum - tolerance or value > maximum + tolerance
            for value, minimum, maximum in zip(vertex, header_minimum, header_maximum)
        ):
            raise NavigationContractError(
                "navigation tile vertex exceeds its bounded quantization envelope"
            )
    ground_vertex_count = vertex_count - offmesh_connection_count * 2
    for vertex_index in range(ground_vertex_count):
        verify_quantized_vertex(struct.unpack_from("<3f", normalized, vertex_offset + vertex_index * 12))
    for vertex_index in range(detail_vertex_count):
        verify_quantized_vertex(
            struct.unpack_from("<3f", normalized, detail_vertex_offset + vertex_index * 12)
        )
    widened = bytearray(normalized)
    struct.pack_into(
        "<6f",
        widened,
        18 * 4,
        *(value - tolerance for value in header_minimum),
        *(value + tolerance for value in header_maximum),
    )
    return bytes(widened)


def _verify_detour_tile(
    *, map_name: str, artifact: str, payload: bytes, expected_grid_x: int, expected_grid_y: int,
) -> None:
    normalized = _normalized_detour_payload(payload)
    decoded_tile = _tile_from_payload(
        map_name=map_name, artifact=artifact, payload=normalized,
    )
    if decoded_tile.grid_x != expected_grid_x or decoded_tile.grid_y != expected_grid_y:
        raise NavigationContractError("navigation tile coordinates do not match container")
    verify_navigation_tile_payload(decoded_tile, normalized)


def _verify_namigator_adt(
    *, map_name: str, artifact: str, payload: bytes, expected_adt_x: int, expected_adt_y: int,
) -> tuple[int, int]:
    """Validate one compressed Namigator ADT and all of its embedded Detour tiles."""

    reader = _PayloadReader(_decompress_namigator(payload))
    # Keep the worker entry point self-contained.  On Windows the validator
    # is imported again in a spawned process; using the pinned header layout
    # directly here avoids relying on a module-global that can be absent while
    # the script is executed as ``__mp_main__`` under Python 3.14.
    signature, version, kind, adt_x, adt_y, tile_count = reader.unpack("<6I")
    if (
        signature != _NAMIGATOR_FILE_SIGNATURE
        or version != _NAMIGATOR_FILE_VERSION
        or kind != _NAMIGATOR_FILE_ADT
    ):
        raise NavigationContractError("Namigator ADT header is not the pinned format")
    if adt_x != expected_adt_x or adt_y != expected_adt_y:
        raise NavigationContractError("navigation tile coordinates do not match catalog")
    if tile_count != _NAMIGATOR_TILE_COUNT:
        raise NavigationContractError("Namigator ADT does not contain exactly 256 Detour tiles")

    seen_coordinates: set[tuple[int, int]] = set()
    detour_tile_count = 0
    empty_tile_count = 0
    min_tile_x = adt_x * _NAMIGATOR_TILES_PER_ADT
    min_tile_y = adt_y * _NAMIGATOR_TILES_PER_ADT
    max_tile_x = min_tile_x + _NAMIGATOR_TILES_PER_ADT
    max_tile_y = min_tile_y + _NAMIGATOR_TILES_PER_ADT
    for index in range(tile_count):
        tile_x, tile_y = reader.unpack("<2I")
        if not (min_tile_x <= tile_x < max_tile_x and min_tile_y <= tile_y < max_tile_y):
            raise NavigationContractError("Namigator inner tile lies outside its ADT")
        coordinate = (int(tile_x), int(tile_y))
        if coordinate in seen_coordinates:
            raise NavigationContractError("Namigator ADT contains a duplicate inner tile")
        seen_coordinates.add(coordinate)

        wmo_count = reader.u32()
        if wmo_count > 1_000_000:
            raise NavigationContractError("Namigator WMO reference count exceeds safety limit")
        reader.skip(wmo_count * 4)
        doodad_count = reader.u32()
        if doodad_count > 1_000_000:
            raise NavigationContractError("Namigator doodad reference count exceeds safety limit")
        reader.skip(doodad_count * 4)

        quad_height_present = reader.take(1)[0]
        if quad_height_present not in {0, 1}:
            raise NavigationContractError("Namigator quad-height flag is invalid")
        if quad_height_present:
            reader.skip(8 + _NAMIGATOR_QUAD_HOLE_BYTES + _NAMIGATOR_QUAD_HEIGHT_BYTES)

        width, height = reader.unpack("<2i")
        if not (0 < width <= _MAX_HEIGHTFIELD_DIMENSION and 0 < height <= _MAX_HEIGHTFIELD_DIMENSION):
            raise NavigationContractError("Namigator heightfield dimensions exceed safety limit")
        bounds_and_scale = reader.unpack("<8f")
        if any(not isfinite(value) for value in bounds_and_scale):
            raise NavigationContractError("Namigator heightfield contains a non-finite value")
        bmin = bounds_and_scale[0:3]
        bmax = bounds_and_scale[3:6]
        if any(low > high for low, high in zip(bmin, bmax)) or bounds_and_scale[6] <= 0 or bounds_and_scale[7] <= 0:
            raise NavigationContractError("Namigator heightfield bounds or scale are invalid")
        span_total = 0
        for _ in range(width * height):
            span_count = reader.u32()
            if span_count > _MAX_HEIGHTFIELD_SPANS_PER_COLUMN:
                raise NavigationContractError("Namigator heightfield column exceeds safety limit")
            span_total += span_count
            if span_total > _MAX_HEIGHTFIELD_SPANS_PER_TILE:
                raise NavigationContractError("Namigator heightfield span total exceeds safety limit")
            # The heightfield columns are diagnostic/recovery data, not input
            # to Detour's native ``addTile``.  Their only variable-length
            # element is the count above, already bounded before this exact
            # byte skip.  Parsing billions of individual span triplets would
            # make a full-world integrity audit needlessly slow without adding
            # a native-memory safety property.
            reader.skip(span_count * 12)

        mesh_size = reader.u32()
        if mesh_size == 0:
            # Namigator deliberately serializes all 16x16 spatial records.
            # SerializeMeshTile returns success with an empty buffer when
            # Recast finds no contours; the native loader also treats size 0
            # as a valid non-walkable tile and never calls addTile for it.
            empty_tile_count += 1
            continue
        if mesh_size < _HEADER_SIZE:
            raise NavigationContractError("Namigator inner tile has a truncated Detour payload")
        mesh_payload = reader.take(mesh_size)
        try:
            _verify_detour_tile(
                map_name=map_name,
                artifact=f"{artifact}#{index}",
                payload=mesh_payload,
                expected_grid_x=int(tile_x),
                expected_grid_y=int(tile_y),
            )
        except NavigationContractError as error:
            raise NavigationContractError(
                f"{artifact} inner tile ({tile_x}, {tile_y}) is invalid: {error}"
            ) from error
        detour_tile_count += 1
    expected_coordinates = {
        (tile_x, tile_y)
        for tile_x in range(min_tile_x, max_tile_x)
        for tile_y in range(min_tile_y, max_tile_y)
    }
    if seen_coordinates != expected_coordinates or reader.position != len(reader.payload):
        raise NavigationContractError("Namigator ADT does not exactly cover its declared tile grid")
    if detour_tile_count + empty_tile_count != _NAMIGATOR_TILE_COUNT:
        raise NavigationContractError("Namigator ADT inner tile accounting is inconsistent")
    return detour_tile_count, empty_tile_count


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return value


def _record_sha256(value: Mapping[str, Any]) -> str:
    wire = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(wire).hexdigest()


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _tile_from_payload(*, map_name: str, artifact: str, payload: bytes) -> NavigationMeshTile:
    if len(payload) < _HEADER_SIZE:
        raise NavigationContractError("navigation tile payload has no Detour header")
    header = struct.unpack_from(_HEADER_FORMAT, payload, 0)
    return NavigationMeshTile(
        tile_id=(
            f"audit:{map_name}:{int(header[2])}:{int(header[3])}:"
            f"{int(header[4])}"
        ),
        grid_x=int(header[2]),
        grid_y=int(header[3]),
        layer=int(header[4]),
        bounds=Bounds3(
            Vector3(float(header[18]), float(header[19]), float(header[20])),
            Vector3(float(header[21]), float(header[22]), float(header[23])),
        ),
        vertex_count=int(header[7]),
        polygon_count=int(header[6]),
        binary_artifact_ref=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        data_size_bytes=len(payload),
        tile_sha256=hashlib.sha256(payload).hexdigest(),
    )


def _failure_code(error: BaseException) -> str:
    if isinstance(error, FileNotFoundError):
        return "MISSING_NAV_TILE"
    if isinstance(error, PermissionError):
        return "UNREADABLE_NAV_TILE"
    message = str(error).lower()
    if "sha256" in message or "hash" in message:
        return "NAV_TILE_SHA256_MISMATCH"
    if "coordinates" in message:
        return "NAV_TILE_COORDINATE_MISMATCH"
    if "detour" in message:
        return "DETOUR_HEADER_INVALID"
    return "DETOUR_PAYLOAD_INVALID"


def _validate_catalogued_artifact(
    task: tuple[str, str, str, str, int, int],
) -> dict[str, Any]:
    """Validate one catalogued artifact in an isolated worker.

    The result contains only JSON-shaped primitives so process workers never
    need to pickle domain objects or a complete world catalog.  ``executor.map``
    preserves catalog order, keeping reports byte-for-byte deterministic.
    """

    map_name, nav_directory, artifact, expected_sha256, grid_x, grid_y = task
    artifact_path = Path(nav_directory) / artifact
    expected_inner_tile_count = 0
    try:
        payload = artifact_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected_sha256:
            raise NavigationContractError("navigation tile sha256 does not match catalog")
        if payload.startswith(b"\x78"):
            expected_inner_tile_count = _NAMIGATOR_TILE_COUNT
            detour_count, empty_count = _verify_namigator_adt(
                map_name=map_name,
                artifact=artifact,
                payload=payload,
                expected_adt_x=grid_x,
                expected_adt_y=grid_y,
            )
            validated_inner_tile_count = detour_count + empty_count
        else:
            expected_inner_tile_count = 1
            _verify_detour_tile(
                map_name=map_name,
                artifact=artifact,
                payload=payload,
                expected_grid_x=grid_x,
                expected_grid_y=grid_y,
            )
            validated_inner_tile_count = 1
            detour_count = 1
            empty_count = 0
    except (OSError, NavigationContractError, ValueError, struct.error) as error:
        return {
            "artifact": artifact,
            "validated_tile_count": 0,
            "expected_inner_tile_count": expected_inner_tile_count,
            "validated_inner_tile_count": 0,
            "detour_tile_count": 0,
            "empty_inner_tile_count": 0,
            "failure": {"artifact": artifact, "code": _failure_code(error)},
        }
    return {
        "artifact": artifact,
        "validated_tile_count": 1,
        "expected_inner_tile_count": expected_inner_tile_count,
        "validated_inner_tile_count": validated_inner_tile_count,
        "detour_tile_count": detour_count,
        "empty_inner_tile_count": empty_count,
        "failure": None,
    }


def build_navmesh_geometry_validation_report(
    catalog_record: Mapping[str, Any],
    *,
    nav_root: Path,
    map_name: str,
    workers: int = 1,
    worker_tasks_per_child: int = 24,
) -> dict[str, Any]:
    """Prove every catalogued tile is structurally safe before a native load."""

    ContractValidator(CATALOG_SCHEMA).validate(catalog_record)
    catalog: ClientWorldCatalog = decode_client_world_catalog(catalog_record)
    maps = [item for item in catalog.maps if item.internal_name == map_name]
    if len(maps) != 1:
        raise ValueError("catalog map is not unique")
    world_map = maps[0]
    nav_directory = nav_root.resolve() / "Nav" / map_name
    expected_artifacts = {item.artifact for item in world_map.tiles}
    actual_artifacts = {
        item.name for item in nav_directory.glob("*.nav") if item.is_file()
    } if nav_directory.is_dir() else set()

    failures: list[dict[str, str]] = []
    if actual_artifacts != expected_artifacts:
        for artifact in sorted(expected_artifacts - actual_artifacts):
            failures.append({"artifact": artifact, "code": "MISSING_NAV_TILE"})
        for artifact in sorted(actual_artifacts - expected_artifacts):
            failures.append({"artifact": artifact, "code": "UNDECLARED_NAV_TILE"})

    if workers < 1 or workers > 16:
        raise ValueError("workers must be between 1 and 16")
    if worker_tasks_per_child < 1 or worker_tasks_per_child > 256:
        raise ValueError("worker_tasks_per_child must be between 1 and 256")
    tasks = [
        (
            map_name,
            str(nav_directory),
            tile.artifact,
            tile.sha256,
            tile.grid_x,
            tile.grid_y,
        )
        for tile in world_map.tiles
    ]
    if workers == 1:
        artifact_results = map(_validate_catalogued_artifact, tasks)
        worker_pool = None
    else:
        # Full continents contain very dense ADTs.  CPython's allocator may
        # retain their decompressed buffers after a task completes even though
        # the objects are unreachable.  ``multiprocessing.Pool`` provides
        # reliable worker replacement on Windows; ProcessPoolExecutor with
        # max_tasks_per_child can leave the coordinator waiting after all
        # workers retire on current Python 3.14 builds.
        worker_pool = get_context("spawn").Pool(
            processes=workers,
            maxtasksperchild=worker_tasks_per_child,
        )
        artifact_results = worker_pool.imap(
            _validate_catalogued_artifact,
            tasks,
            chunksize=1,
        )

    validated_tile_count = 0
    expected_inner_tile_count = 0
    validated_inner_tile_count = 0
    detour_tile_count = 0
    empty_inner_tile_count = 0
    try:
        for result in artifact_results:
            validated_tile_count += result["validated_tile_count"]
            expected_inner_tile_count += result["expected_inner_tile_count"]
            validated_inner_tile_count += result["validated_inner_tile_count"]
            detour_tile_count += result["detour_tile_count"]
            empty_inner_tile_count += result["empty_inner_tile_count"]
            failure = result["failure"]
            if failure is not None and not any(
                item["artifact"] == failure["artifact"] for item in failures
            ):
                failures.append(failure)
    except BaseException:
        if worker_pool is not None:
            worker_pool.terminate()
        raise
    else:
        if worker_pool is not None:
            worker_pool.close()
    finally:
        if worker_pool is not None:
            worker_pool.join()

    report = {
        "record_type": "navmesh_geometry_validation_report",
        "schema_version": "1.0",
        "status": "PASS" if not failures else "FAIL",
        "validator_id": VALIDATOR_ID,
        "catalog_id": catalog.catalog_id,
        "catalog_sha256": _record_sha256(catalog_record),
        "client_build": catalog.client_build,
        "map_id": world_map.map_id,
        "internal_name": map_name,
        "expected_tile_count": len(world_map.tiles),
        "validated_tile_count": validated_tile_count,
        "expected_inner_tile_count": expected_inner_tile_count,
        "validated_inner_tile_count": validated_inner_tile_count,
        "detour_tile_count": detour_tile_count,
        "empty_inner_tile_count": empty_inner_tile_count,
        "failure_count": len(failures),
        "failures": failures,
        "nav_tiles_sha256": world_map.nav_tiles_sha256,
        "execution_authority": False,
    }
    ContractValidator(REPORT_SCHEMA).validate(report)
    return report


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate every catalogued Detour v7 tile structurally before "
            "WorldPack promotion."
        )
    )
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--nav-root", type=Path, required=True)
    parser.add_argument("--map-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--workers",
        type=int,
        default=min(4, os.cpu_count() or 1),
        help="Independent ADT validation workers (1-16; default: up to 4).",
    )
    parser.add_argument(
        "--worker-tasks-per-child",
        type=int,
        default=24,
        help="Recycle a worker after this many ADTs (1-256; default: 24).",
    )
    args = parser.parse_args(argv)
    report = build_navmesh_geometry_validation_report(
        _read_object(args.catalog),
        nav_root=args.nav_root,
        map_name=args.map_name,
        workers=args.workers,
        worker_tasks_per_child=args.worker_tasks_per_child,
    )
    _atomic_write(args.output, report)
    print(json.dumps({
        "status": report["status"],
        "internal_name": report["internal_name"],
        "expected_tile_count": report["expected_tile_count"],
        "validated_tile_count": report["validated_tile_count"],
        "failure_count": report["failure_count"],
        "execution_authority": False,
    }, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(run())
