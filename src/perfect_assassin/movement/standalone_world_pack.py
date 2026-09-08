from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any, Iterable, Mapping

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_world_adapter import (
    resolve_client_world_adapter,
)
from perfect_assassin.movement.client_world_catalog import (
    ClientWorldCatalog,
    decode_client_world_catalog,
    load_client_world_catalog,
    verify_client_world_catalog,
)


class StandaloneWorldPackError(ValueError):
    """Raised when a WorldPack is incomplete, ambiguous, or modified."""


@dataclass(frozen=True, slots=True)
class VerifiedStandaloneWorldPack:
    pack_root: Path
    manifest: Mapping[str, Any]
    catalog: ClientWorldCatalog

    @property
    def nav_root(self) -> Path:
        return self.pack_root

    @property
    def world_catalog_path(self) -> Path:
        return self.pack_root / "identity" / "client-world-catalog.json"

    @property
    def world_map_catalog_path(self) -> Path:
        return self.pack_root / "identity" / "world-map-catalog.bin"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise StandaloneWorldPackError(
            f"cannot hash WorldPack artifact {path.name!r}: {error}"
        ) from error
    return digest.hexdigest()


def _safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise StandaloneWorldPackError("WorldPack artifact path is unsafe")
    return path


def _content_sha256(files: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda value: str(value["relative_path"])):
        wire = json.dumps(
            {
                "role": item["role"],
                "relative_path": item["relative_path"],
                "byte_size": item["byte_size"],
                "sha256": item["sha256"],
            },
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        digest.update(len(wire).to_bytes(4, "little"))
        digest.update(wire)
    return digest.hexdigest()


def _record_sha256(value: Mapping[str, Any]) -> str:
    wire = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(wire).hexdigest()


def _copy_artifact(
    source: Path,
    *,
    staging_root: Path,
    relative_path: str,
    role: str,
) -> dict[str, Any]:
    relative = _safe_relative_path(relative_path)
    source = source.resolve()
    if not source.is_file() or source.is_symlink():
        raise StandaloneWorldPackError(
            f"WorldPack source artifact is unavailable: {source}"
        )
    destination = staging_root.joinpath(*relative.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {
        "role": role,
        "relative_path": relative.as_posix(),
        "byte_size": destination.stat().st_size,
        "sha256": _sha256(destination),
    }


def _write_json_artifact(
    value: Mapping[str, Any],
    *,
    staging_root: Path,
    relative_path: str,
    role: str,
) -> dict[str, Any]:
    relative = _safe_relative_path(relative_path)
    destination = staging_root.joinpath(*relative.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            value, indent=2, ensure_ascii=False, allow_nan=False, sort_keys=False,
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {
        "role": role,
        "relative_path": relative.as_posix(),
        "byte_size": destination.stat().st_size,
        "sha256": _sha256(destination),
    }


def _write_bytes_artifact(
    value: bytes,
    *,
    staging_root: Path,
    relative_path: str,
    role: str,
) -> dict[str, Any]:
    relative = _safe_relative_path(relative_path)
    destination = staging_root.joinpath(*relative.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(value)
    return {
        "role": role,
        "relative_path": relative.as_posix(),
        "byte_size": destination.stat().st_size,
        "sha256": _sha256(destination),
    }


def _read_pack_json_artifact(pack_root: Path, relative_path: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            pack_root.joinpath(*_safe_relative_path(relative_path).parts).read_text(
                encoding="utf-8",
            )
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StandaloneWorldPackError(
            f"cannot read WorldPack JSON artifact: {relative_path}"
        ) from error
    if not isinstance(value, Mapping):
        raise StandaloneWorldPackError(
            f"WorldPack JSON artifact is not an object: {relative_path}"
        )
    return value


def _verify_geometry_validation_report(
    report: Mapping[str, Any],
    *,
    catalog_record: Mapping[str, Any],
    world_map: Any,
) -> None:
    """Bind a structural Detour audit to exactly one complete catalog map."""

    expected_count = len(world_map.tiles)
    if (
        report.get("record_type") != "navmesh_geometry_validation_report"
        or report.get("schema_version") != "1.0"
        or report.get("status") != "PASS"
        or report.get("validator_id")
        != "perfect-assassin.namigator-detour-v7-structural-v2"
        or report.get("execution_authority") is not False
        or str(report.get("catalog_id")) != str(catalog_record.get("catalog_id"))
        or str(report.get("catalog_sha256", "")).lower()
        != _record_sha256(catalog_record)
        or str(report.get("client_build")) != str(catalog_record.get("client_build"))
        or int(report.get("map_id", -1)) != int(world_map.map_id)
        or str(report.get("internal_name")) != str(world_map.internal_name)
        or int(report.get("expected_tile_count", -1)) != expected_count
        or int(report.get("validated_tile_count", -1)) != expected_count
        or int(report.get("expected_inner_tile_count", -1)) < expected_count
        or int(report.get("validated_inner_tile_count", -1))
        != int(report.get("expected_inner_tile_count", -2))
        or int(report.get("detour_tile_count", -1))
        + int(report.get("empty_inner_tile_count", -1))
        != int(report.get("validated_inner_tile_count", -2))
        or int(report.get("failure_count", -1)) != 0
        or report.get("failures") != []
        or str(report.get("nav_tiles_sha256", "")).lower()
        != str(world_map.nav_tiles_sha256).lower()
    ):
        raise StandaloneWorldPackError(
            f"navmesh geometry validation is incomplete for "
            f"{world_map.internal_name!r}"
        )


def _verify_bundled_tile_repair_evidence(
    *,
    pack_root: Path,
    file_records: Mapping[str, Mapping[str, Any]],
    quality_reports: set[str],
    repair_evidence: set[str],
    repair_regressions: set[str],
) -> None:
    """Re-check repair relations after a pack has been sealed."""
    if not repair_evidence:
        if repair_regressions:
            raise StandaloneWorldPackError(
                "WorldPack has repair regressions without repair evidence"
            )
        return
    catalog_path = "identity/client-world-catalog.json"
    if catalog_path not in file_records:
        raise StandaloneWorldPackError(
            "WorldPack repair evidence requires a bundled runtime catalog"
        )
    catalog = _read_pack_json_artifact(pack_root, catalog_path)
    maps = catalog.get("maps")
    if not isinstance(maps, list):
        raise StandaloneWorldPackError("WorldPack repair catalog maps are invalid")
    catalog_maps = {
        str(item.get("internal_name")): item
        for item in maps if isinstance(item, Mapping)
    }
    if len(catalog_maps) != len(maps):
        raise StandaloneWorldPackError("WorldPack repair catalog map identities are invalid")
    reports_by_name: dict[str, Mapping[str, Any]] = {}
    for relative_path in quality_reports:
        report = _read_pack_json_artifact(pack_root, relative_path)
        map_name = str(report.get("internal_name", ""))
        if (
            not map_name
            or map_name in reports_by_name
            or relative_path != f"evidence/navmesh-bake-quality-{map_name}.json"
        ):
            raise StandaloneWorldPackError(
                "WorldPack repair bake quality identities are invalid"
            )
        reports_by_name[map_name] = report

    expected_repairs: dict[tuple[str, int, int, str], tuple[str, str, str]] = {}
    for map_name, report in reports_by_name.items():
        catalog_map = catalog_maps.get(map_name)
        report_tiles = report.get("nav_tiles")
        final_tiles = (
            catalog_map.get("tiles") if isinstance(catalog_map, Mapping) else None
        )
        if not isinstance(report_tiles, list) or not isinstance(final_tiles, list):
            raise StandaloneWorldPackError(
                "WorldPack repair tile records are invalid"
            )
        raw_by_key: dict[tuple[int, int, str], str] = {}
        final_by_key: dict[tuple[int, int, str], str] = {}
        try:
            for item in report_tiles:
                key = (
                    int(item["grid_x"]), int(item["grid_y"]),
                    str(item["artifact"]),
                )
                raw_by_key[key] = str(item["sha256"]).lower()
            for item in final_tiles:
                key = (
                    int(item["grid_x"]), int(item["grid_y"]),
                    str(item["artifact"]),
                )
                final_by_key[key] = str(item["sha256"]).lower()
        except (KeyError, TypeError, ValueError) as error:
            raise StandaloneWorldPackError(
                "WorldPack repair tile identity is invalid"
            ) from error
        if len(raw_by_key) != len(report_tiles) or set(raw_by_key) != set(final_by_key):
            raise StandaloneWorldPackError(
                "WorldPack repair tile coverage is inconsistent"
            )
        for key, final_sha256 in final_by_key.items():
            raw_sha256 = raw_by_key[key]
            nav_path = f"Nav/{map_name}/{key[2]}"
            nav_record = file_records.get(nav_path)
            if nav_record is None or str(nav_record["sha256"]).lower() != final_sha256:
                raise StandaloneWorldPackError(
                    f"WorldPack repair final tile is inconsistent: {nav_path}"
                )
            if raw_sha256 != final_sha256:
                expected_repairs[(map_name, *key)] = (
                    raw_sha256, final_sha256, _record_sha256(report),
                )

    seen_repairs: set[tuple[str, int, int, str]] = set()
    for relative_path in repair_evidence:
        evidence = _read_pack_json_artifact(pack_root, relative_path)
        tile = evidence.get("tile")
        source = evidence.get("replacement_source")
        defect = evidence.get("defect")
        regression = evidence.get("regression")
        before = regression.get("before") if isinstance(regression, Mapping) else None
        after = regression.get("after") if isinstance(regression, Mapping) else None
        if not isinstance(tile, Mapping):
            raise StandaloneWorldPackError("WorldPack repair evidence tile is invalid")
        try:
            key = (
                str(evidence["internal_name"]),
                int(tile["grid_x"]),
                int(tile["grid_y"]),
                str(tile["artifact"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise StandaloneWorldPackError(
                "WorldPack repair evidence identity is invalid"
            ) from error
        expected = expected_repairs.get(key)
        expected_path = (
            f"evidence/navmesh-tile-repair-{key[0]}-{key[1]:02d}-{key[2]:02d}.json"
        )
        if (
            expected is None
            or key in seen_repairs
            or relative_path != expected_path
            or evidence.get("record_type") != "navmesh_tile_repair_evidence"
            or evidence.get("schema_version") != "1.0"
            or evidence.get("execution_authority") is not False
            or str(evidence.get("catalog_id")) != str(catalog.get("catalog_id"))
            or str(evidence.get("client_build")) != str(catalog.get("client_build"))
            or not isinstance(source, Mapping)
            or str(tile.get("raw_bake_sha256", "")).lower() != expected[0]
            or str(tile.get("replacement_sha256", "")).lower() != expected[1]
            or str(evidence.get("raw_bake_report_sha256", "")).lower() != expected[2]
            or str(source.get("relative_path", "")) != f"Nav/{key[0]}/{key[3]}"
            or str(source.get("artifact_sha256", "")).lower() != expected[1]
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", str(source.get("pack_id", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(source.get("pack_content_sha256", "")))
            or not isinstance(defect, Mapping)
            or not str(defect.get("failure_code", ""))
            or not isinstance(before, Mapping)
            or not isinstance(after, Mapping)
            or before.get("status") != "FAILED"
            or after.get("status") != "PASSED"
            or str(defect.get("evidence_artifact", ""))
            != str(before.get("result_artifact", ""))
            or str(defect.get("evidence_sha256", "")).lower()
            != str(before.get("result_sha256", "")).lower()
        ):
            raise StandaloneWorldPackError(
                f"WorldPack repair evidence is inconsistent: {relative_path}"
            )
        for artifact_path, artifact_sha256 in (
            (str(defect.get("evidence_artifact", "")), str(defect.get("evidence_sha256", ""))),
            (str(before.get("result_artifact", "")), str(before.get("result_sha256", ""))),
            (str(after.get("result_artifact", "")), str(after.get("result_sha256", ""))),
        ):
            record = file_records.get(artifact_path)
            if (
                artifact_path not in repair_regressions
                or record is None
                or str(record["sha256"]).lower() != artifact_sha256.lower()
            ):
                raise StandaloneWorldPackError(
                    f"WorldPack repair regression is inconsistent: {artifact_path}"
                )
        seen_repairs.add(key)
    if seen_repairs != set(expected_repairs):
        raise StandaloneWorldPackError(
            "WorldPack repair evidence does not cover all replaced tiles"
        )


def build_standalone_world_pack(
    inventory: Mapping[str, Any],
    queue: Mapping[str, Any],
    *,
    nav_root: Path,
    world_catalog_asset_path: Path,
    staging_root: Path,
    pack_id: str,
    selected_map_names: Iterable[str],
) -> dict[str, Any]:
    """Copy an exact, declared coverage set into a process-independent pack."""
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", pack_id) is None:
        raise StandaloneWorldPackError("WorldPack ID is invalid")
    if staging_root.exists():
        raise StandaloneWorldPackError("WorldPack staging destination already exists")
    if (
        inventory.get("record_type") != "client_world_asset_inventory"
        or queue.get("record_type") != "client_world_bake_queue"
        or inventory.get("catalog_id") != queue.get("catalog_id")
        or inventory.get("execution_authority") is not False
        or queue.get("execution_authority") is not False
    ):
        raise StandaloneWorldPackError("inventory and bake queue identity mismatch")
    adapter = resolve_client_world_adapter(
        asset_container=str(inventory["asset_container"]),
        world_catalog_parser_profile=str(inventory["asset_parser_profile"]),
    )
    if not bool(queue.get("bvh_ready")):
        raise StandaloneWorldPackError("global BVH is not structurally ready")
    requested = tuple(sorted(set(selected_map_names)))
    if not requested:
        raise StandaloneWorldPackError("WorldPack must declare at least one map")
    queue_maps = {
        str(item["internal_name"]): item
        for item in queue.get("maps", [])
        if isinstance(item, Mapping)
    }
    if len(queue_maps) != len(queue.get("maps", [])):
        raise StandaloneWorldPackError("bake queue map identities are not unique")
    selected: list[Mapping[str, Any]] = []
    for map_name in requested:
        item = queue_maps.get(map_name)
        if item is None:
            raise StandaloneWorldPackError(
                f"map is absent from the pinned bake queue: {map_name!r}"
            )
        if item.get("state") != "COMPLETE":
            raise StandaloneWorldPackError(
                f"map is not complete and cannot be packed: {map_name!r}"
            )
        selected.append(item)
    nav_root = nav_root.resolve()
    if str(nav_root) != str(Path(str(queue["nav_root"])).resolve()):
        raise StandaloneWorldPackError("nav root does not match the bake queue")
    world_catalog_asset_path = world_catalog_asset_path.resolve()
    if _sha256(world_catalog_asset_path) != str(
        inventory["world_catalog_asset_sha256"]
    ):
        raise StandaloneWorldPackError("world catalog asset hash mismatch")

    staging_root.mkdir(parents=True)
    try:
        files: list[dict[str, Any]] = []
        files.append(_copy_artifact(
            world_catalog_asset_path,
            staging_root=staging_root,
            relative_path="identity/world-map-catalog.bin",
            role="WORLD_MAP_CATALOG",
        ))
        for item in selected:
            map_name = str(item["internal_name"])
            files.append(_copy_artifact(
                Path(str(item["map_file"])),
                staging_root=staging_root,
                relative_path=f"{map_name}.map",
                role="NAV_MAP",
            ))
            nav_directory = Path(str(item["nav_directory"]))
            nav_tiles = sorted(nav_directory.glob("*.nav"), key=lambda path: path.name)
            semantics = sorted(
                (nav_root / "semantics").glob(f"{map_name}_*.road"),
                key=lambda path: path.name,
            )
            if len(nav_tiles) != int(item["adt_count"]):
                raise StandaloneWorldPackError(
                    f"navigation tile count changed for {map_name!r}"
                )
            if len(semantics) != int(item["adt_count"]):
                raise StandaloneWorldPackError(
                    f"road semantic count changed for {map_name!r}"
                )
            for path in nav_tiles:
                files.append(_copy_artifact(
                    path,
                    staging_root=staging_root,
                    relative_path=f"Nav/{map_name}/{path.name}",
                    role="NAV_TILE",
                ))
            for path in semantics:
                files.append(_copy_artifact(
                    path,
                    staging_root=staging_root,
                    relative_path=f"semantics/{path.name}",
                    role="ROAD_SEMANTIC",
                ))
        bvh_directory = nav_root / "BVH"
        bvh_index = bvh_directory / "bvh.idx"
        files.append(_copy_artifact(
            bvh_index,
            staging_root=staging_root,
            relative_path="BVH/bvh.idx",
            role="BVH_INDEX",
        ))
        bvh_assets = sorted(bvh_directory.glob("*.bvh"), key=lambda path: path.name)
        if not bvh_assets:
            raise StandaloneWorldPackError("WorldPack BVH artifact set is empty")
        for path in bvh_assets:
            files.append(_copy_artifact(
                path,
                staging_root=staging_root,
                relative_path=f"BVH/{path.name}",
                role="BVH_ASSET",
            ))
        map_records = [
            {
                "map_id": int(item["map_id"]),
                "internal_name": str(item["internal_name"]),
                "adt_count": int(item["adt_count"]),
            }
            for item in selected
        ]
        map_records.sort(key=lambda item: (item["map_id"], item["internal_name"]))
        manifest = {
            "record_type": "standalone_world_pack",
            "schema_version": "1.0",
            "pack_id": pack_id,
            "catalog_id": str(inventory["catalog_id"]),
            "product": str(inventory["product"]),
            "expansion": str(inventory["expansion"]),
            "client_version": str(inventory["client_version"]),
            "client_build": str(inventory["client_build"]),
            "asset_container": adapter.asset_container,
            "asset_adapter_id": adapter.adapter_id,
            "world_source": "PINNED_CLIENT_ASSETS_OFFLINE_IMPORT",
            "nav_runtime_layout": "namigator-nav-bvh-v1",
            "coverage_state": (
                "FULL_CATALOG"
                if len(map_records) == int(queue["eligible_map_count"])
                else "DECLARED_MAPS_ONLY"
            ),
            "eligible_map_count": int(queue["eligible_map_count"]),
            "packed_map_count": len(map_records),
            "maps": map_records,
            "files": sorted(files, key=lambda item: item["relative_path"]),
            "content_sha256": _content_sha256(files),
            "runtime_dependencies": {
                "client_installation_required": False,
                "client_process_required": False,
                "server_required": False,
                "emulator_required": False,
            },
            "execution_authority": False,
        }
        return manifest
    except BaseException:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise


def build_standalone_world_pack_from_catalog(
    catalog_record: Mapping[str, Any],
    *,
    nav_root: Path,
    world_catalog_asset_path: Path,
    staging_root: Path,
    pack_id: str,
    bake_quality_reports: Iterable[Mapping[str, Any]] = (),
    navmesh_geometry_reports: Iterable[Mapping[str, Any]] = (),
    tile_repair_evidence: Iterable[Mapping[str, Any]] = (),
    tile_repair_artifacts: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Seal the exact partial or complete coverage declared by a verified catalog."""
    catalog = decode_client_world_catalog(catalog_record)
    verify_client_world_catalog(
        catalog,
        target_profile=catalog.target_profile,
        client_version=catalog.client_version,
        client_build=catalog.client_build,
        nav_profile_id=catalog.nav_profile_id,
        nav_root=nav_root,
        world_catalog_asset_path=world_catalog_asset_path,
        allow_extra_unselected_artifacts=True,
    )
    nav_root = nav_root.resolve()
    bvh_directory = nav_root / "BVH"
    bvh_index = bvh_directory / "bvh.idx"
    bvh_assets = tuple(bvh_directory.glob("*.bvh"))
    bvh_ready = (
        bvh_index.is_file()
        and bvh_index.stat().st_size > 0
        and bool(bvh_assets)
        and all(path.is_file() and path.stat().st_size > 0 for path in bvh_assets)
    )
    inventory_identity = {
        "record_type": "client_world_asset_inventory",
        "schema_version": "1.0",
        "catalog_id": catalog.catalog_id,
        "product": catalog.product,
        "expansion": catalog.expansion,
        "client_version": catalog.client_version,
        "client_build": catalog.client_build,
        "asset_container": catalog.asset_container,
        "asset_parser_profile": catalog.asset_parser_profile,
        "world_catalog_asset_sha256": catalog.world_catalog_asset_sha256,
        "execution_authority": False,
    }
    queue_maps = [
        {
            "map_id": item.map_id,
            "internal_name": item.internal_name,
            "adt_count": len(item.tiles),
            "state": "COMPLETE",
            "nav_directory": str((nav_root / "Nav" / item.internal_name).resolve()),
            "map_file": str((nav_root / item.map_artifact).resolve()),
        }
        for item in catalog.maps
    ]
    queue_identity = {
        "record_type": "client_world_bake_queue",
        "catalog_id": catalog.catalog_id,
        "nav_root": str(nav_root),
        "bvh_ready": bvh_ready,
        "eligible_map_count": len(queue_maps),
        "maps": queue_maps,
        "execution_authority": False,
    }
    manifest = build_standalone_world_pack(
        inventory_identity,
        queue_identity,
        nav_root=nav_root,
        world_catalog_asset_path=world_catalog_asset_path,
        staging_root=staging_root,
        pack_id=pack_id,
        selected_map_names=(item.internal_name for item in catalog.maps),
    )
    complete_maps = {
        item.internal_name: item
        for item in catalog.maps
        if item.coverage_state == "complete"
    }
    reports_by_name: dict[str, Mapping[str, Any]] = {}
    for report in bake_quality_reports:
        map_name = str(report.get("internal_name", ""))
        if not map_name or map_name in reports_by_name:
            raise StandaloneWorldPackError(
                "navmesh bake quality report identities are invalid"
            )
        reports_by_name[map_name] = report
    if set(reports_by_name) != set(complete_maps):
        raise StandaloneWorldPackError(
            "complete catalog maps require exact navmesh bake quality reports"
        )
    geometry_reports_by_name: dict[str, Mapping[str, Any]] = {}
    for report in navmesh_geometry_reports:
        map_name = str(report.get("internal_name", ""))
        if not map_name or map_name in geometry_reports_by_name:
            raise StandaloneWorldPackError(
                "navmesh geometry validation report identities are invalid"
            )
        geometry_reports_by_name[map_name] = report
    if set(geometry_reports_by_name) != set(complete_maps):
        raise StandaloneWorldPackError(
            "complete catalog maps require exact navmesh geometry validation reports"
        )
    for map_name, report in geometry_reports_by_name.items():
        _verify_geometry_validation_report(
            report,
            catalog_record=catalog_record,
            world_map=complete_maps[map_name],
        )
    repairs_by_key: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    repair_artifacts = dict(tile_repair_artifacts or {})
    for evidence in tile_repair_evidence:
        tile = evidence.get("tile")
        if not isinstance(tile, Mapping):
            raise StandaloneWorldPackError(
                "navmesh tile repair evidence identity is invalid"
            )
        key = (
            str(evidence.get("internal_name", "")),
            int(tile.get("grid_x", -1)),
            int(tile.get("grid_y", -1)),
            str(tile.get("artifact", "")),
        )
        if not key[0] or not key[3] or key in repairs_by_key:
            raise StandaloneWorldPackError(
                "navmesh tile repair evidence identities are invalid"
            )
        repairs_by_key[key] = evidence
    used_repairs: set[tuple[str, int, int, str]] = set()
    required_repair_artifacts: dict[str, str] = {}
    for map_name, report in reports_by_name.items():
        world_map = complete_maps[map_name]
        expected_count = len(world_map.tiles)
        diagnostics = report.get("diagnostics")
        reported_tiles = report.get("nav_tiles")
        expected_tiles = {
            (item.grid_x, item.grid_y, item.artifact): item.sha256
            for item in world_map.tiles
        }
        reported_tile_items = [
            item for item in reported_tiles if isinstance(item, Mapping)
        ] if isinstance(reported_tiles, list) else []
        actual_reported_tiles = {
            (
                int(item.get("grid_x", -1)),
                int(item.get("grid_y", -1)),
                str(item.get("artifact", "")),
            ): str(item.get("sha256", "")).lower()
            for item in reported_tile_items
        }
        if (
            report.get("record_type") != "navmesh_bake_quality_report"
            or report.get("schema_version") != "1.0"
            or report.get("status") not in {
                "COMPLETE_CLEAN", "COMPLETE_WITH_RECAST_DIAGNOSTICS",
            }
            or report.get("execution_authority") is not False
            or report.get("geometric_validation_required") is not True
            or str(report.get("catalog_id")) != catalog.catalog_id
            or str(report.get("client_build")) != catalog.client_build
            or int(report.get("map_id", -1)) != world_map.map_id
            or int(report.get("expected_adt_count", -1)) != expected_count
            or int(report.get("nav_adt_count", -1)) != expected_count
            or len(reported_tile_items) != expected_count
            or len(actual_reported_tiles) != expected_count
            or set(actual_reported_tiles) != set(expected_tiles)
            or report.get("missing_coordinates") != []
            or report.get("extra_coordinates") != []
            or int(report.get("invalid_nav_artifact_count", -1)) != 0
            or report.get("terminal_return_code") != 0
            or not isinstance(diagnostics, Mapping)
            or int(diagnostics.get("failed_tile_count", -1)) != 0
        ):
            raise StandaloneWorldPackError(
                f"navmesh bake quality is incomplete for {map_name!r}"
            )
        mismatched_keys = {
            key for key, final_sha256 in expected_tiles.items()
            if actual_reported_tiles[key] != final_sha256
        }
        if not mismatched_keys and (
            str(report.get("nav_tiles_sha256", "")).lower()
            != world_map.nav_tiles_sha256
        ):
            raise StandaloneWorldPackError(
                f"navmesh bake quality aggregate is inconsistent for {map_name!r}"
            )
        report_sha256 = _record_sha256(report)
        for tile_key in mismatched_keys:
            repair_key = (map_name, *tile_key)
            evidence = repairs_by_key.get(repair_key)
            if evidence is None:
                raise StandaloneWorldPackError(
                    f"navmesh tile replacement lacks repair evidence: "
                    f"{map_name}/{tile_key[2]}"
                )
            tile = evidence.get("tile")
            source = evidence.get("replacement_source")
            defect = evidence.get("defect")
            regression = evidence.get("regression")
            before = regression.get("before") if isinstance(regression, Mapping) else None
            after = regression.get("after") if isinstance(regression, Mapping) else None
            final_sha256 = expected_tiles[tile_key]
            raw_sha256 = actual_reported_tiles[tile_key]
            expected_source_path = f"Nav/{map_name}/{tile_key[2]}"
            if (
                evidence.get("record_type") != "navmesh_tile_repair_evidence"
                or evidence.get("schema_version") != "1.0"
                or evidence.get("execution_authority") is not False
                or str(evidence.get("catalog_id")) != catalog.catalog_id
                or str(evidence.get("client_build")) != catalog.client_build
                or int(evidence.get("map_id", -1)) != world_map.map_id
                or str(evidence.get("raw_bake_report_sha256", "")).lower()
                != report_sha256
                or not isinstance(tile, Mapping)
                or str(tile.get("raw_bake_sha256", "")).lower() != raw_sha256
                or str(tile.get("replacement_sha256", "")).lower() != final_sha256
                or not isinstance(source, Mapping)
                or str(source.get("relative_path", "")) != expected_source_path
                or str(source.get("artifact_sha256", "")).lower() != final_sha256
                or not str(source.get("pack_id", ""))
                or re.fullmatch(r"[a-f0-9]{64}", str(source.get("pack_content_sha256", ""))) is None
                or not isinstance(defect, Mapping)
                or not str(defect.get("failure_code", ""))
                or re.fullmatch(r"[a-f0-9]{64}", str(defect.get("evidence_sha256", ""))) is None
                or not isinstance(regression, Mapping)
                or not str(regression.get("scenario_id", ""))
                or not isinstance(before, Mapping)
                or before.get("status") != "FAILED"
                or re.fullmatch(r"[a-f0-9]{64}", str(before.get("result_sha256", ""))) is None
                or not isinstance(after, Mapping)
                or after.get("status") != "PASSED"
                or re.fullmatch(r"[a-f0-9]{64}", str(after.get("result_sha256", ""))) is None
            ):
                raise StandaloneWorldPackError(
                    f"navmesh tile repair evidence is inconsistent: "
                    f"{map_name}/{tile_key[2]}"
                )
            defect_path = _safe_relative_path(
                str(defect["evidence_artifact"])
            ).as_posix()
            before_path = _safe_relative_path(
                str(before["result_artifact"])
            ).as_posix()
            after_path = _safe_relative_path(
                str(after["result_artifact"])
            ).as_posix()
            if defect_path != before_path:
                raise StandaloneWorldPackError(
                    f"navmesh tile defect must cite the failed regression: "
                    f"{map_name}/{tile_key[2]}"
                )
            for artifact_path, artifact_sha256 in (
                (defect_path, str(defect["evidence_sha256"])),
                (before_path, str(before["result_sha256"])),
                (after_path, str(after["result_sha256"])),
            ):
                previous = required_repair_artifacts.get(artifact_path)
                if previous not in (None, artifact_sha256):
                    raise StandaloneWorldPackError(
                        "navmesh repair artifact hash declarations conflict"
                    )
                required_repair_artifacts[artifact_path] = artifact_sha256
            used_repairs.add(repair_key)
    if used_repairs != set(repairs_by_key):
        raise StandaloneWorldPackError(
            "navmesh tile repair evidence contains undeclared replacements"
        )
    if set(repair_artifacts) != set(required_repair_artifacts):
        raise StandaloneWorldPackError(
            "navmesh tile repair regression artifacts are incomplete"
        )
    for relative_path, expected_sha256 in required_repair_artifacts.items():
        if hashlib.sha256(repair_artifacts[relative_path]).hexdigest() != expected_sha256:
            raise StandaloneWorldPackError(
                f"navmesh tile repair regression hash mismatch: {relative_path}"
            )
    if any(
        item.coverage_state != "complete"
        or item.interior_coverage != "complete"
        or item.road_semantic_coverage != "complete"
        for item in catalog.maps
    ):
        manifest["coverage_state"] = "DECLARED_MAPS_ONLY"
    files = list(manifest["files"])
    files.append(_write_json_artifact(
        catalog_record,
        staging_root=staging_root,
        relative_path="identity/client-world-catalog.json",
        role="CLIENT_WORLD_CATALOG",
    ))
    for map_name, report in sorted(reports_by_name.items()):
        files.append(_write_json_artifact(
            report,
            staging_root=staging_root,
            relative_path=f"evidence/navmesh-bake-quality-{map_name}.json",
            role="NAVMESH_BAKE_QUALITY",
        ))
    for map_name, report in sorted(geometry_reports_by_name.items()):
        files.append(_write_json_artifact(
            report,
            staging_root=staging_root,
            relative_path=f"evidence/navmesh-geometry-{map_name}.json",
            role="NAVMESH_GEOMETRY_VALIDATION",
        ))
    for (map_name, grid_x, grid_y, _artifact), evidence in sorted(
        repairs_by_key.items()
    ):
        files.append(_write_json_artifact(
            evidence,
            staging_root=staging_root,
            relative_path=(
                f"evidence/navmesh-tile-repair-{map_name}-"
                f"{grid_x:02d}-{grid_y:02d}.json"
            ),
            role="NAVMESH_TILE_REPAIR_EVIDENCE",
        ))
    for relative_path, payload in sorted(repair_artifacts.items()):
        files.append(_write_bytes_artifact(
            payload,
            staging_root=staging_root,
            relative_path=relative_path,
            role="NAVMESH_TILE_REPAIR_REGRESSION",
        ))
    files.sort(key=lambda item: item["relative_path"])
    manifest["files"] = files
    manifest["content_sha256"] = _content_sha256(files)
    return manifest


def verify_standalone_world_pack(
    pack_root: Path, manifest: Mapping[str, Any],
) -> None:
    pack_root = pack_root.resolve()
    if manifest.get("record_type") != "standalone_world_pack":
        raise StandaloneWorldPackError("WorldPack manifest identity is invalid")
    dependencies = manifest.get("runtime_dependencies")
    expected_dependency_keys = {
        "client_installation_required", "client_process_required",
        "server_required", "emulator_required",
    }
    if (
        not isinstance(dependencies, Mapping)
        or set(dependencies) != expected_dependency_keys
        or any(value is not False for value in dependencies.values())
    ):
        raise StandaloneWorldPackError("WorldPack has a forbidden runtime dependency")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise StandaloneWorldPackError("WorldPack file manifest is empty")
    expected_paths: set[str] = set()
    file_records: dict[str, Mapping[str, Any]] = {}
    for item in files:
        if not isinstance(item, Mapping):
            raise StandaloneWorldPackError("WorldPack file record is invalid")
        relative = _safe_relative_path(str(item["relative_path"]))
        relative_name = relative.as_posix()
        if relative_name in expected_paths:
            raise StandaloneWorldPackError("WorldPack file paths are not unique")
        expected_paths.add(relative_name)
        file_records[relative_name] = item
        path = pack_root.joinpath(*relative.parts)
        if not path.is_file() or path.is_symlink():
            raise StandaloneWorldPackError(
                f"WorldPack artifact is missing: {relative_name}"
            )
        if path.stat().st_size != int(item["byte_size"]):
            raise StandaloneWorldPackError(
                f"WorldPack artifact size mismatch: {relative_name}"
            )
        if _sha256(path) != str(item["sha256"]):
            raise StandaloneWorldPackError(
                f"WorldPack artifact hash mismatch: {relative_name}"
            )
    actual_paths = {
        path.relative_to(pack_root).as_posix()
        for path in pack_root.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if actual_paths != expected_paths:
        raise StandaloneWorldPackError(
            "WorldPack files do not exactly match the manifest"
        )
    if _content_sha256(files) != str(manifest.get("content_sha256")):
        raise StandaloneWorldPackError("WorldPack aggregate hash mismatch")
    maps = manifest.get("maps")
    if not isinstance(maps, list) or not maps:
        raise StandaloneWorldPackError("WorldPack map declaration is empty")
    map_names = [str(item.get("internal_name")) for item in maps]
    if len(set(map_names)) != len(map_names):
        raise StandaloneWorldPackError("WorldPack map declarations are not unique")
    by_role: dict[str, set[str]] = {}
    for item in files:
        by_role.setdefault(str(item["role"]), set()).add(str(item["relative_path"]))
    if by_role.get("WORLD_MAP_CATALOG") != {"identity/world-map-catalog.bin"}:
        raise StandaloneWorldPackError("WorldPack catalog topology is invalid")
    bundled_catalog = by_role.get("CLIENT_WORLD_CATALOG")
    if bundled_catalog not in (None, {"identity/client-world-catalog.json"}):
        raise StandaloneWorldPackError("WorldPack runtime catalog topology is invalid")
    quality_reports = by_role.get("NAVMESH_BAKE_QUALITY", set())
    if any(
        path not in {
            f"evidence/navmesh-bake-quality-{name}.json"
            for name in map_names
        }
        for path in quality_reports
    ):
        raise StandaloneWorldPackError("WorldPack bake quality topology is invalid")
    geometry_reports = by_role.get("NAVMESH_GEOMETRY_VALIDATION", set())
    if any(
        path not in {
            f"evidence/navmesh-geometry-{name}.json"
            for name in map_names
        }
        for path in geometry_reports
    ):
        raise StandaloneWorldPackError(
            "WorldPack navmesh geometry validation topology is invalid"
        )
    if bundled_catalog is None:
        if geometry_reports:
            raise StandaloneWorldPackError(
                "WorldPack geometry validation requires a bundled runtime catalog"
            )
    else:
        catalog_record = _read_pack_json_artifact(
            pack_root, "identity/client-world-catalog.json",
        )
        catalog = decode_client_world_catalog(catalog_record)
        complete_maps = {
            item.internal_name: item
            for item in catalog.maps
            if item.coverage_state == "complete"
        }
        expected_geometry_paths = {
            f"evidence/navmesh-geometry-{name}.json"
            for name in complete_maps
        }
        if geometry_reports != expected_geometry_paths:
            raise StandaloneWorldPackError(
                "WorldPack complete maps require exact geometry validation evidence"
            )
        for map_name, world_map in complete_maps.items():
            _verify_geometry_validation_report(
                _read_pack_json_artifact(
                    pack_root, f"evidence/navmesh-geometry-{map_name}.json",
                ),
                catalog_record=catalog_record,
                world_map=world_map,
            )
    repair_evidence = by_role.get("NAVMESH_TILE_REPAIR_EVIDENCE", set())
    if any(
        re.fullmatch(
            rf"evidence/navmesh-tile-repair-{re.escape(name)}-[0-9]{{2}}-[0-9]{{2}}\.json",
            path,
        ) is None
        for path in repair_evidence
        for name in [next(
            (candidate for candidate in map_names if path.startswith(
                f"evidence/navmesh-tile-repair-{candidate}-"
            )),
            "",
        )]
    ):
        raise StandaloneWorldPackError("WorldPack tile repair topology is invalid")
    repair_regressions = by_role.get("NAVMESH_TILE_REPAIR_REGRESSION", set())
    if any(
        not path.startswith("evidence/navmesh-repair-regression/")
        or not path.endswith(".json")
        for path in repair_regressions
    ):
        raise StandaloneWorldPackError(
            "WorldPack tile repair regression topology is invalid"
        )
    _verify_bundled_tile_repair_evidence(
        pack_root=pack_root,
        file_records=file_records,
        quality_reports=quality_reports,
        repair_evidence=repair_evidence,
        repair_regressions=repair_regressions,
    )
    if by_role.get("NAV_MAP") != {f"{name}.map" for name in map_names}:
        raise StandaloneWorldPackError("WorldPack map topology is invalid")
    if by_role.get("BVH_INDEX") != {"BVH/bvh.idx"} or not by_role.get("BVH_ASSET"):
        raise StandaloneWorldPackError("WorldPack BVH topology is invalid")
    nav_tiles = by_role.get("NAV_TILE", set())
    road_semantics = by_role.get("ROAD_SEMANTIC", set())
    for item in maps:
        map_name = str(item["internal_name"])
        expected_count = int(item["adt_count"])
        if sum(path.startswith(f"Nav/{map_name}/") for path in nav_tiles) != expected_count:
            raise StandaloneWorldPackError(
                f"WorldPack nav coverage is invalid for {map_name!r}"
            )
        if sum(
            path.startswith(f"semantics/{map_name}_") for path in road_semantics
        ) != expected_count:
            raise StandaloneWorldPackError(
                f"WorldPack semantic coverage is invalid for {map_name!r}"
            )
    known_prefixes = tuple(f"Nav/{name}/" for name in map_names)
    known_semantic_prefixes = tuple(f"semantics/{name}_" for name in map_names)
    if any(not path.startswith(known_prefixes) for path in nav_tiles) or any(
        not path.startswith(known_semantic_prefixes) for path in road_semantics
    ):
        raise StandaloneWorldPackError("WorldPack contains undeclared map coverage")


def open_standalone_world_pack(
    pack_root: Path,
    *,
    pack_schema_path: Path,
    catalog_schema_path: Path,
    expected_pack_id: str | None = None,
    expected_content_sha256: str | None = None,
) -> VerifiedStandaloneWorldPack:
    """Verify and open a runtime-ready WorldPack without external world assets."""
    pack_root = pack_root.resolve()
    manifest_path = pack_root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StandaloneWorldPackError(f"cannot read WorldPack manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise StandaloneWorldPackError("WorldPack manifest is not one object")
    ContractValidator(pack_schema_path).validate(manifest)
    verify_standalone_world_pack(pack_root, manifest)
    if expected_pack_id is not None and manifest["pack_id"] != expected_pack_id:
        raise StandaloneWorldPackError("WorldPack ID does not match the runtime pin")
    if (
        expected_content_sha256 is not None
        and manifest["content_sha256"] != expected_content_sha256
    ):
        raise StandaloneWorldPackError("WorldPack content hash does not match the runtime pin")
    catalog_path = pack_root / "identity" / "client-world-catalog.json"
    if not catalog_path.is_file():
        raise StandaloneWorldPackError("WorldPack has no bundled runtime catalog")
    catalog = load_client_world_catalog(catalog_path, schema_path=catalog_schema_path)
    verify_client_world_catalog(
        catalog,
        target_profile=catalog.target_profile,
        client_version=catalog.client_version,
        client_build=catalog.client_build,
        nav_profile_id=catalog.nav_profile_id,
        nav_root=pack_root,
        world_catalog_asset_path=pack_root / "identity" / "world-map-catalog.bin",
    )
    if catalog.catalog_id != manifest["catalog_id"]:
        raise StandaloneWorldPackError("WorldPack catalog ID is inconsistent")
    manifest_maps = {
        (int(item["map_id"]), str(item["internal_name"]), int(item["adt_count"]))
        for item in manifest["maps"]
    }
    catalog_maps = {
        (item.map_id, item.internal_name, len(item.tiles)) for item in catalog.maps
    }
    if manifest_maps != catalog_maps:
        raise StandaloneWorldPackError("WorldPack runtime catalog coverage is inconsistent")
    return VerifiedStandaloneWorldPack(
        pack_root=pack_root,
        manifest=manifest,
        catalog=catalog,
    )
