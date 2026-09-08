from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

import perfect_assassin.movement.navigation_contracts as navigation_contracts

from perfect_assassin.contract_validation import (
    ContractValidationError,
    ContractValidator,
)
from perfect_assassin.movement.navigation_contracts import (
    ArtifactScope,
    Bounds3,
    CoordinateSystem,
    DebugPolygon,
    DebugTileHash,
    GeometryTile,
    GeometryTriangle,
    NavigationActorBinding,
    NavigationContractError,
    NavigationDebugSnapshot,
    NavigationGeometry,
    NavigationMesh,
    NavigationMeshTile,
    NavigationProvenance,
    HASH_WIRE_FORMAT,
    PINNED_RECAST_COMMIT,
    Vector3,
    canonical_json_bytes,
    canonical_record_sha256,
    canonical_wire_bytes,
    decode_navigation_record,
    validate_navigation_record_semantics,
    verify_geometry_mesh_binding,
    verify_mesh_debug_binding,
    verify_navigation_artifact_chain,
    verify_navigation_record_integrity,
    verify_navigation_tile_payload,
)


ROOT = Path(__file__).resolve().parents[1]
ASSET_MANIFEST_SHA256 = "a" * 64
GEOMETRY_PROFILE_HASH = "b" * 64
AGENT_PROFILE_HASH = "c" * 64
AUTHORIZATION_SHA256 = "D" * 64


def detour_fixture_payload(
    *,
    grid_x: int = 31,
    grid_y: int = 31,
    layer: int = 0,
    vertex_count: int = 3,
    polygon_count: int = 1,
    minimum: tuple[float, float, float] = (0.0, -0.5, 0.0),
    maximum: tuple[float, float, float] = (10.0, 1.0, 10.0),
) -> bytes:
    if vertex_count != 3 or polygon_count != 1:
        raise ValueError("the pinned structural fixture is one ground triangle")
    max_link_count = 3
    header = struct.pack(
        "<15i10f",
        navigation_contracts.DETOUR_NAVMESH_MAGIC,
        navigation_contracts.DETOUR_NAVMESH_VERSION,
        grid_x,
        grid_y,
        layer,
        0,
        polygon_count,
        vertex_count,
        max_link_count,
        polygon_count,
        0,
        1,
        0,
        0,
        polygon_count,
        0.0,
        0.0,
        0.0,
        *minimum,
        *maximum,
        1.0,
    )
    ground_y = min(max(0.0, minimum[1]), maximum[1])
    vertices = struct.pack(
        "<9f",
        minimum[0],
        ground_y,
        minimum[2],
        maximum[0],
        ground_y,
        minimum[2],
        minimum[0],
        ground_y,
        maximum[2],
    )
    polygon = struct.pack(
        "<I6H6HHBB",
        0,
        0, 1, 2, 0, 0, 0,
        0, 0, 0, 0, 0, 0,
        1,
        3,
        0,
    )
    links = bytes(max_link_count * navigation_contracts.DETOUR_LINK_BYTES)
    detail_mesh = struct.pack("<IIBB2x", 0, 0, 0, 1)
    detail_triangle = struct.pack("<4B", 0, 1, 2, 0x15)
    return header + vertices + polygon + links + detail_mesh + detail_triangle


FIXTURE_TILE_PAYLOAD = detour_fixture_payload()


def detour_quad_fixture_payload(
    *, concave: bool, near_collinear_roundoff: bool = False,
) -> bytes:
    vertex_count = 4
    polygon_count = 1
    max_link_count = 4
    header = struct.pack(
        "<15i10f",
        navigation_contracts.DETOUR_NAVMESH_MAGIC,
        navigation_contracts.DETOUR_NAVMESH_VERSION,
        31, 31, 0, 0,
        polygon_count, vertex_count, max_link_count,
        polygon_count, 0, 2, 0, 0, polygon_count,
        0.0, 0.0, 0.0,
        0.0, -0.5, 0.0,
        10.0, 1.0, 10.0,
        1.0,
    )
    if near_collinear_roundoff:
        second = (1.0, 0.0, 1.006)
        third = (2.0, 0.0, 2.0)
    else:
        second = (10.0, 0.0, 0.0)
        third = (2.0, 0.0, 2.0) if concave else (10.0, 0.0, 10.0)
    vertices = struct.pack(
        "<12f",
        0.0, 0.0, 0.0,
        *second,
        *third,
        0.0, 0.0, 10.0,
    )
    polygon = struct.pack(
        "<I6H6HHBB",
        0,
        0, 1, 2, 3, 0, 0,
        0, 0, 0, 0, 0, 0,
        1,
        4,
        0,
    )
    links = bytes(max_link_count * navigation_contracts.DETOUR_LINK_BYTES)
    detail_mesh = struct.pack("<IIBB2x", 0, 0, 0, 2)
    detail_triangles = b"".join((
        struct.pack("<4B", 0, 1, 2, 0x05),
        struct.pack("<4B", 0, 2, 3, 0x14),
    ))
    return header + vertices + polygon + links + detail_mesh + detail_triangles


def detour_offmesh_fixture_payload() -> bytes:
    minimum = (0.0, -0.5, 0.0)
    maximum = (10.0, 1.0, 10.0)
    ground_vertices = (
        0.0, 0.0, 0.0,
        10.0, 0.0, 0.0,
        0.0, 0.0, 10.0,
    )
    endpoints = (2.0, 0.0, 2.0, 8.0, 0.0, 8.0)
    header = struct.pack(
        "<15i10f",
        navigation_contracts.DETOUR_NAVMESH_MAGIC,
        navigation_contracts.DETOUR_NAVMESH_VERSION,
        31, 31, 0, 0,
        2, 5, 7,
        1, 0, 1, 0,
        1, 1,
        0.0, 0.0, 0.0,
        *minimum, *maximum, 1.0,
    )
    ground_polygon = struct.pack(
        "<I6H6HHBB",
        0,
        0, 1, 2, 0, 0, 0,
        0, 0, 0, 0, 0, 0,
        1, 3, 0,
    )
    offmesh_polygon = struct.pack(
        "<I6H6HHBB",
        0,
        3, 4, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0,
        1, 2, 0x40,
    )
    return b"".join(
        (
            header,
            struct.pack("<15f", *(ground_vertices + endpoints)),
            ground_polygon,
            offmesh_polygon,
            bytes(7 * navigation_contracts.DETOUR_LINK_BYTES),
            struct.pack("<IIBB2x", 0, 0, 0, 1),
            struct.pack("<4B", 0, 1, 2, 0x15),
            struct.pack("<6ffHBBI", *endpoints, 0.5, 1, 1, 0xFF, 123),
        )
    )


def coordinate_system() -> CoordinateSystem:
    return CoordinateSystem(
        space_id="tbc243:azeroth:recast",
        units="world_units",
        handedness="right_handed",
        axis_x="east",
        axis_y="up",
        axis_z="south",
        triangle_winding="clockwise",
        world_to_nav_row_major=(
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            -1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
        ),
    )


def artifact_bounds() -> Bounds3:
    return Bounds3(Vector3(-1.0, -1.0, -1.0), Vector3(11.0, 2.0, 11.0))


def tile_bounds() -> Bounds3:
    return Bounds3(Vector3(0.0, -0.5, 0.0), Vector3(10.0, 1.0, 10.0))


def candidate_scope(decision_scope: str = "unpromoted_evaluation_only") -> ArtifactScope:
    return ArtifactScope(
        asset_trust="candidate_untrusted",
        promotion_state="unpromoted",
        decision_scope=decision_scope,
    )


def provenance(
    *,
    origin: str = "client_asset_derived",
    scope: str = "unpromoted_evaluation_only",
    capability: str = "client_geometry_extraction",
    source_id: str = "pa-wow-geometry",
) -> NavigationProvenance:
    return NavigationProvenance(
        source_id=source_id,
        origin=origin,
        scope=scope,
        capability=capability,
        evidence_refs=("asset-manifest:tbc243:candidate",),
        observed_at="2026-08-23T08:00:00Z",
        confidence=0.75,
    )


def geometry_tile() -> GeometryTile:
    return GeometryTile(
        tile_id="pgeom:azeroth:31:31:0",
        grid_x=31,
        grid_y=31,
        layer=0,
        bounds=tile_bounds(),
        vertices=(
            Vector3(0.0, 0.0, 0.0),
            Vector3(10.0, 0.0, 0.0),
            Vector3(0.0, 0.0, 10.0),
        ),
        triangles=(
            GeometryTriangle(
                indices=(0, 1, 2),
                area="ground",
                material_ref="terrain:grass",
                source_ref="adt:azeroth:31:31",
            ),
        ),
        source_asset_refs=("mpq:patch-2:azeroth:31:31",),
    )


def geometry() -> NavigationGeometry:
    return NavigationGeometry(
        geometry_id="pgeom:azeroth:deathknell:v1",
        target_profile="tbc_243_lab",
        client_build="2.4.3.8606",
        build_signature="wow-tbc-2.4.3.8606-enGB:sha256:406da0c1",
        map_ref="map:azeroth",
        map_signature="client-assets:azeroth:candidate:v1",
        ordered_asset_manifest_sha256=ASSET_MANIFEST_SHA256,
        geometry_profile_id="geometry-profile:tbc243:rogue",
        geometry_profile_hash=GEOMETRY_PROFILE_HASH,
        coordinate_system=coordinate_system(),
        bounds=artifact_bounds(),
        tiles=(geometry_tile(),),
        artifact_scope=candidate_scope(),
        provenance=provenance(),
        created_at="2026-08-23T08:00:01Z",
    )


def navigation_tile() -> NavigationMeshTile:
    return NavigationMeshTile.from_fixture_payload(
        tile_id="pnav:azeroth:31:31:0",
        grid_x=31,
        grid_y=31,
        layer=0,
        bounds=tile_bounds(),
        vertex_count=3,
        polygon_count=1,
        payload=FIXTURE_TILE_PAYLOAD,
    )


def navigation_tile_for_payload(
    payload: bytes, *, vertex_count: int = 3, polygon_count: int = 1
) -> NavigationMeshTile:
    digest = hashlib.sha256(payload).hexdigest()
    return NavigationMeshTile(
        tile_id="pnav:fixture:structural",
        grid_x=31,
        grid_y=31,
        layer=0,
        bounds=tile_bounds(),
        vertex_count=vertex_count,
        polygon_count=polygon_count,
        binary_artifact_ref=f"sha256:{digest}",
        data_size_bytes=len(payload),
        tile_sha256=digest,
    )


def navigation_mesh() -> NavigationMesh:
    source_geometry = geometry()
    return NavigationMesh(
        mesh_id="pnav:azeroth:deathknell:v1",
        geometry_content_sha256=source_geometry.content_sha256,
        target_profile="tbc_243_lab",
        client_build="2.4.3.8606",
        build_signature="wow-tbc-2.4.3.8606-enGB:sha256:406da0c1",
        map_ref="map:azeroth",
        map_signature="client-assets:azeroth:candidate:v1",
        ordered_asset_manifest_sha256=ASSET_MANIFEST_SHA256,
        recast_pin=PINNED_RECAST_COMMIT,
        agent_profile_id="agent-profile:tbc243:rogue",
        agent_profile_hash=AGENT_PROFILE_HASH,
        coordinate_system=coordinate_system(),
        bounds=artifact_bounds(),
        tiles=(navigation_tile(),),
        artifact_scope=candidate_scope(),
        provenance=provenance(
            capability="navigation_mesh_build", source_id="pa-nav-bake"
        ),
        created_at="2026-08-23T08:00:02Z",
    )


def actor_binding(context: str = "champion") -> NavigationActorBinding:
    champion = context == "champion"
    return NavigationActorBinding(
        instance_id="instance:predator",
        actor_role="champion_journey" if champion else "lab_clone",
        actor_id="champion:predator" if champion else "lab-clone:navigation",
        decision_context=context,
        memory_namespace=(
            "memory:champion:predator" if champion else "memory:lab:navigation"
        ),
        expected_character_name="Predator",
        credential_alias="lab.operator",
        binding_assurance_state="configured_expected_only",
        binding_assurance_evidence_refs=("execution-target:tbc243-lab",),
    )


def debug_provenance(
    context: str = "champion", origin: str = "navigation_runtime"
) -> NavigationProvenance:
    return NavigationProvenance(
        source_id="pa-nav-debug",
        origin=origin,
        scope=(
            "unpromoted_evaluation_only"
            if context == "champion"
            else "lab_evaluation_only"
        ),
        capability="navigation_debug_snapshot",
        evidence_refs=("pnav:azeroth:deathknell:v1",),
        observed_at="2026-08-23T08:00:03Z",
        confidence=0.74,
    )


def debug_snapshot(
    mode: str = "ROUTE",
    *,
    context: str = "champion",
    origin: str = "navigation_runtime",
    mesh_scope: ArtifactScope | None = None,
) -> NavigationDebugSnapshot:
    mesh = navigation_mesh()
    tile = mesh.tiles[0]
    route_points: tuple[Vector3, ...] = ()
    polygons: tuple[DebugPolygon, ...] = ()
    player: Vector3 | None = None
    target: Vector3 | None = None
    uncertainty: float | None = None
    tile_hashes: tuple[DebugTileHash, ...] = ()
    if mode in {"ROUTE", "MESH"}:
        player = Vector3(1.0, 0.0, 1.0)
        target = Vector3(8.0, 0.0, 8.0)
        uncertainty = 0.25
        tile_hashes = (DebugTileHash(tile.tile_id, tile.tile_sha256, tile.bounds),)
        route_points = (player, target)
    if mode == "MESH":
        polygons = (
            DebugPolygon(
                polygon_ref="poly:azeroth:31:31:0:0",
                source_tile_id=tile.tile_id,
                source_polygon_index=0,
                vertices=(
                    Vector3(0.0, 0.0, 0.0),
                    Vector3(10.0, 0.0, 0.0),
                    Vector3(0.0, 0.0, 10.0),
                ),
                area="ground",
                flags=("walkable",),
                traversal_cost=1.0,
                blocked=False,
            ),
        )
    return NavigationDebugSnapshot(
        snapshot_id=f"nav-debug:fixture:{mode.lower()}:{context}",
        mode=mode,
        binding=actor_binding(context),
        authorization_sha256=AUTHORIZATION_SHA256,
        target_profile="tbc_243_lab",
        client_build="2.4.3.8606",
        build_signature="wow-tbc-2.4.3.8606-enGB:sha256:406da0c1",
        map_ref="map:azeroth",
        map_signature="client-assets:azeroth:candidate:v1",
        ordered_asset_manifest_sha256=ASSET_MANIFEST_SHA256,
        navigation_mesh_content_sha256=mesh.content_sha256,
        navigation_mesh_artifact_scope=mesh_scope or mesh.artifact_scope,
        recast_pin=PINNED_RECAST_COMMIT,
        agent_profile_hash=AGENT_PROFILE_HASH,
        coordinate_system=coordinate_system(),
        bounds=artifact_bounds(),
        tile_hashes=tile_hashes,
        player_position=player,
        target_position=target,
        uncertainty_radius=uncertainty,
        route_points=route_points,
        mesh_polygons=polygons,
        provenance=debug_provenance(context, origin),
        created_at="2026-08-23T08:00:04Z",
    )


class NavigationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.geometry_validator = ContractValidator(
            ROOT / "contracts" / "navigation-geometry.schema.json"
        )
        self.mesh_validator = ContractValidator(
            ROOT / "contracts" / "navigation-mesh.schema.json"
        )
        self.debug_validator = ContractValidator(
            ROOT / "contracts" / "navigation-debug-snapshot.schema.json"
        )

    def test_shared_artifacts_are_actor_free_valid_manifests(self) -> None:
        geometry_record = geometry().to_record()
        mesh_record = navigation_mesh().to_record()

        self.geometry_validator.validate(geometry_record)
        self.mesh_validator.validate(mesh_record)
        verify_navigation_record_integrity(geometry_record)
        verify_navigation_record_integrity(mesh_record)

        self.assertNotIn("actor_binding", geometry_record)
        self.assertNotIn("authorization_sha256", geometry_record)
        self.assertNotIn("actor_binding", mesh_record)
        self.assertNotIn("authorization_sha256", mesh_record)
        self.assertEqual(
            mesh_record["artifact_scope"]["asset_trust"], "candidate_untrusted"
        )
        self.assertEqual(
            mesh_record["artifact_scope"]["promotion_state"], "unpromoted"
        )

    def test_pnav_is_a_binary_reference_manifest_not_base64_payload(self) -> None:
        mesh_record = navigation_mesh().to_record()
        tile_record = mesh_record["tiles"][0]

        self.assertNotIn("payload", tile_record)
        self.assertNotIn("payload_base64", tile_record)
        self.assertEqual(
            tile_record["binary_artifact_ref"],
            f"sha256:{hashlib.sha256(FIXTURE_TILE_PAYLOAD).hexdigest()}",
        )
        verify_navigation_tile_payload(navigation_mesh().tiles[0], FIXTURE_TILE_PAYLOAD)

        with self.assertRaises(NavigationContractError):
            verify_navigation_tile_payload(
                navigation_mesh().tiles[0], FIXTURE_TILE_PAYLOAD + b"tampered"
            )

    def test_serialization_and_hashes_are_deterministic(self) -> None:
        first = geometry().to_record()
        second = geometry().to_record()
        self.assertEqual(first, second)
        self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))
        self.assertEqual(
            canonical_json_bytes({"z": 1, "a": 2}),
            canonical_json_bytes({"a": 2, "z": 1}),
        )

    def test_integrity_rejects_nested_and_manifest_tampering(self) -> None:
        geometry_record = geometry().to_record()
        geometry_record["tiles"][0]["vertices"][0]["x"] = 0.5
        with self.assertRaisesRegex(NavigationContractError, "geometry tile hash"):
            verify_navigation_record_integrity(geometry_record)

        mesh_record = navigation_mesh().to_record()
        mesh_record["tiles"][0]["binary_artifact_ref"] = "../other.pnav"
        with self.assertRaisesRegex(NavigationContractError, "opaque sha256"):
            verify_navigation_record_integrity(mesh_record)

        count_tamper = navigation_mesh().to_record()
        count_tamper["tile_count"] = 2
        with self.assertRaisesRegex(NavigationContractError, "tile_count"):
            verify_navigation_record_integrity(count_tamper)

    def test_candidate_untrusted_cannot_claim_promotion(self) -> None:
        with self.assertRaises(NavigationContractError):
            ArtifactScope(
                asset_trust="candidate_untrusted",
                promotion_state="promoted",
                decision_scope="champion_eligible",
            )

        falsely_promoted = geometry().to_record()
        falsely_promoted["artifact_scope"] = {
            "asset_trust": "candidate_untrusted",
            "promotion_state": "promoted",
            "decision_scope": "champion_eligible",
        }
        falsely_promoted["provenance"]["scope"] = "champion_eligible"
        with self.assertRaises(ContractValidationError):
            self.geometry_validator.validate(falsely_promoted)

    def test_wrong_recast_pin_fails_in_python_and_schema(self) -> None:
        with self.assertRaisesRegex(NavigationContractError, "unpinned Recast"):
            replace(navigation_mesh(), recast_pin="0" * 40)

        record = navigation_mesh().to_record()
        record["recast_pin"] = "0" * 40
        with self.assertRaises(ContractValidationError):
            self.mesh_validator.validate(record)

    def test_coordinate_bounds_indices_and_finite_guards_fail_closed(self) -> None:
        with self.assertRaises(NavigationContractError):
            replace(coordinate_system(), handedness="left_handed")
        with self.assertRaises(NavigationContractError):
            Vector3(math.nan, 0.0, 0.0)
        with self.assertRaises(NavigationContractError):
            replace(
                geometry_tile(),
                triangles=(
                    replace(geometry_tile().triangles[0], indices=(0, 1, 3)),
                ),
            )
        with self.assertRaises(NavigationContractError):
            replace(
                geometry_tile(),
                vertices=(
                    Vector3(0.0, 0.0, 0.0),
                    Vector3(10.0, 0.0, 0.0),
                    Vector3(20.0, 0.0, 10.0),
                ),
            )
        with self.assertRaises(NavigationContractError):
            replace(provenance(), confidence=math.inf)

        non_finite = geometry().to_record()
        non_finite["tiles"][0]["vertices"][0]["x"] = math.nan
        with self.assertRaises(ContractValidationError):
            self.geometry_validator.validate(non_finite)

    def test_debug_modes_are_schema_valid_and_explicitly_non_decision(self) -> None:
        for mode in ("OFF", "ROUTE", "MESH"):
            record = debug_snapshot(mode).to_record()
            self.debug_validator.validate(record)
            verify_navigation_record_integrity(record)
            self.assertIs(record["render_only"], True)
            self.assertIs(record["decision_input"], False)
            self.assertIs(record["execution_authority"], False)
            self.assertEqual(record["view_kind"], "top_down")
            self.assertEqual(
                record["actor_binding"]["binding_assurance"]["state"],
                "configured_expected_only",
            )
            self.assertEqual(
                record["provenance"]["scope"], "unpromoted_evaluation_only"
            )

    def test_mode_payload_invariants_reject_mixed_views(self) -> None:
        route = debug_snapshot("ROUTE")
        polygon = debug_snapshot("MESH").mesh_polygons[0]
        with self.assertRaises(NavigationContractError):
            replace(route, mesh_polygons=(polygon,))
        with self.assertRaises(NavigationContractError):
            replace(debug_snapshot("MESH"), mesh_polygons=())
        with self.assertRaises(NavigationContractError):
            replace(
                debug_snapshot("OFF"),
                player_position=Vector3(1.0, 0.0, 1.0),
            )

    def test_configured_champion_debug_cannot_claim_champion_scope(self) -> None:
        with self.assertRaisesRegex(NavigationContractError, "unsupported provenance"):
            replace(debug_provenance(), scope="champion_eligible")

        record = debug_snapshot().to_record()
        record["provenance"]["scope"] = "champion_eligible"
        with self.assertRaises(ContractValidationError):
            self.debug_validator.validate(record)

    def test_server_or_lab_oracle_never_crosses_to_champion(self) -> None:
        with self.assertRaisesRegex(NavigationContractError, "oracle"):
            debug_provenance("champion", "server_mmap")
        with self.assertRaises(NavigationContractError):
            replace(
                debug_snapshot(),
                provenance=debug_provenance("lab_clone", "server_mmap"),
            )

        lab_oracle = debug_snapshot(
            "MESH",
            context="lab_clone",
            origin="server_mmap",
            mesh_scope=candidate_scope("lab_evaluation_only"),
        )
        lab_record = lab_oracle.to_record()
        self.debug_validator.validate(lab_record)
        self.assertEqual(lab_record["provenance"]["scope"], "lab_evaluation_only")
        self.assertIs(lab_record["decision_input"], False)

        mislabeled = copy.deepcopy(lab_record)
        mislabeled["actor_binding"]["actor_role"] = "champion_journey"
        mislabeled["actor_binding"]["decision_context"] = "champion"
        mislabeled["actor_binding"]["memory_namespace"] = "memory:champion:predator"
        with self.assertRaises(ContractValidationError):
            self.debug_validator.validate(mislabeled)

    def test_pgeom_and_pnav_reject_oracle_provenance_entirely(self) -> None:
        oracle = provenance(
            origin="server_ground_truth",
            scope="lab_evaluation_only",
        )
        with self.assertRaisesRegex(NavigationContractError, "client-asset"):
            replace(
                geometry(),
                artifact_scope=candidate_scope("lab_evaluation_only"),
                provenance=oracle,
            )
        with self.assertRaisesRegex(NavigationContractError, "client-asset"):
            replace(
                navigation_mesh(),
                artifact_scope=candidate_scope("lab_evaluation_only"),
                provenance=oracle,
            )

    def test_timestamp_and_bounded_binding_evidence_are_enforced(self) -> None:
        with self.assertRaises(NavigationContractError):
            replace(geometry(), created_at="2026-08-23T07:59:59Z")
        with self.assertRaises(NavigationContractError):
            replace(
                actor_binding(),
                binding_assurance_evidence_refs=tuple(
                    f"evidence:{index}" for index in range(5)
                ),
            )

    def test_debug_hash_detects_render_data_tampering(self) -> None:
        record = debug_snapshot("MESH").to_record()
        record["mesh_polygons"][0]["traversal_cost"] = 999.0
        with self.assertRaisesRegex(NavigationContractError, "content hash"):
            verify_navigation_record_integrity(record)

    def test_cross_language_wire_format_has_a_pinned_golden_vector(self) -> None:
        vector = {
            "a": 1,
            "b": 1.0,
            "c": -0.0,
            "d": "é",
            "e": [True, None],
        }
        expected_hex = (
            "50412d4e41562d5749524500014d00000005530000000161443ff0000000000000"
            "530000000162443ff000000000000053000000016344000000000000000053000000"
            "01645300000002c3a95300000001654100000002544e"
        )
        self.assertEqual(HASH_WIRE_FORMAT, "pa-nav-wire-v1")
        self.assertEqual(canonical_wire_bytes(vector).hex(), expected_hex)
        self.assertEqual(
            canonical_record_sha256(vector),
            "2f6f82d86be92a7cf33dd6cb3478eb8c95ff318d7bbbe66db92a18afd72a9926",
        )
        self.assertEqual(
            canonical_wire_bytes(vector),
            canonical_wire_bytes(dict(reversed(tuple(vector.items())))),
        )
        self.assertEqual(
            canonical_wire_bytes({"zero": -0.0}),
            canonical_wire_bytes({"zero": 0.0}),
        )
        self.assertEqual(
            canonical_wire_bytes({"value": 1}),
            canonical_wire_bytes({"value": 1.0}),
        )

    def test_bounded_raw_decoder_rejects_duplicates_nonfinite_and_wrong_types(self) -> None:
        record = geometry().to_record()
        raw = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        decoded = decode_navigation_record(raw)
        self.assertIsInstance(decoded, NavigationGeometry)
        self.assertEqual(decoded.to_record(), record)

        with self.assertRaisesRegex(NavigationContractError, "repeats object key"):
            decode_navigation_record(
                b'{"record_type":"navigation_geometry","record_type":"navigation_mesh"}'
            )
        with self.assertRaisesRegex(NavigationContractError, "non-finite"):
            decode_navigation_record(b'{"record_type":NaN}')

        mathematically_equivalent = geometry().to_record()
        mathematically_equivalent["tiles"][0]["vertices"][0]["x"] = 0
        mathematically_equivalent["tiles"][0]["grid_x"] = 31.0
        mathematically_equivalent["tile_count"] = 1.0
        tile_unsigned = {
            key: value
            for key, value in mathematically_equivalent["tiles"][0].items()
            if key != "tile_sha256"
        }
        mathematically_equivalent["tiles"][0]["tile_sha256"] = canonical_record_sha256(
            tile_unsigned
        )
        unsigned = {
            key: value
            for key, value in mathematically_equivalent.items()
            if key != "content_sha256"
        }
        mathematically_equivalent["content_sha256"] = canonical_record_sha256(unsigned)
        self.geometry_validator.validate(mathematically_equivalent)
        normalized = validate_navigation_record_semantics(mathematically_equivalent)
        self.assertIs(type(normalized.tiles[0].vertices[0].x), float)
        self.assertIs(type(normalized.tiles[0].grid_x), int)

    def test_raw_preflight_enforces_byte_depth_and_global_token_budgets(self) -> None:
        with patch.object(navigation_contracts, "MAX_NAVIGATION_RECORD_BYTES", 16):
            with self.assertRaisesRegex(NavigationContractError, "byte budget"):
                decode_navigation_record(b"{" + b" " * 16 + b"}")
        with patch.object(navigation_contracts, "MAX_NAVIGATION_NESTING_DEPTH", 2):
            with self.assertRaisesRegex(NavigationContractError, "nesting budget"):
                decode_navigation_record(b"[[[[]]]]")
        with patch.object(navigation_contracts, "MAX_NAVIGATION_JSON_NODES", 1):
            with self.assertRaisesRegex(NavigationContractError, "exact global node"):
                decode_navigation_record(b'{"a":1,"b":2}')

        class HostileDict(dict):
            def items(self):  # pragma: no cover - must never execute
                raise AssertionError("attacker-controlled iteration executed")

        with self.assertRaisesRegex(NavigationContractError, "root must be an object"):
            validate_navigation_record_semantics(HostileDict(geometry().to_record()))

    def test_global_geometry_budget_is_enforced_across_tiles(self) -> None:
        with patch.object(navigation_contracts, "MAX_GEOMETRY_TOTAL_VERTICES", 2):
            with self.assertRaisesRegex(NavigationContractError, "global vertex budget"):
                geometry()
        with patch.object(
            navigation_contracts, "MAX_DEBUG_TOTAL_POLYGON_VERTICES", 2
        ):
            with self.assertRaisesRegex(
                NavigationContractError, "global polygon-vertex budget"
            ):
                debug_snapshot("MESH")

    def test_content_addressed_refs_are_opaque_and_bound_to_payload_hash(self) -> None:
        expected_sha = hashlib.sha256(FIXTURE_TILE_PAYLOAD).hexdigest()
        tile = navigation_tile()
        self.assertEqual(tile.binary_artifact_ref, f"sha256:{expected_sha}")

        with self.assertRaisesRegex(NavigationContractError, "opaque sha256"):
            NavigationMeshTile.from_fixture_payload(
                tile_id="pnav:bad-path",
                grid_x=31,
                grid_y=31,
                layer=0,
                bounds=tile_bounds(),
                vertex_count=3,
                polygon_count=1,
                binary_artifact_ref="../../Data/world.mmap",
                payload=FIXTURE_TILE_PAYLOAD,
            )
        with self.assertRaisesRegex(NavigationContractError, "digest must equal"):
            replace(tile, binary_artifact_ref=f"sha256:{'0' * 64}")

        raw_tile = tile.to_record()
        raw_tile["binary_artifact_ref"] = "../escape.pnav"
        with self.assertRaisesRegex(NavigationContractError, "opaque sha256"):
            verify_navigation_tile_payload(raw_tile, FIXTURE_TILE_PAYLOAD)

        escaped_manifest = navigation_mesh().to_record()
        escaped_manifest["tiles"][0]["binary_artifact_ref"] = "../escape.pnav"
        escaped_manifest["content_sha256"] = canonical_record_sha256(
            {
                key: value
                for key, value in escaped_manifest.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaises(ContractValidationError):
            self.mesh_validator.validate(escaped_manifest)
        with self.assertRaisesRegex(NavigationContractError, "opaque sha256"):
            verify_navigation_record_integrity(escaped_manifest)

    def test_v1_artifacts_cannot_self_promote_even_with_a_recomputed_hash(self) -> None:
        with self.assertRaisesRegex(NavigationContractError, "candidate_untrusted"):
            ArtifactScope(
                asset_trust="trusted_exact_manifest",
                promotion_state="promoted",
                decision_scope="champion_eligible",
            )

        promoted = geometry().to_record()
        promoted["artifact_scope"] = {
            "asset_trust": "trusted_exact_manifest",
            "promotion_state": "promoted",
            "decision_scope": "champion_eligible",
        }
        promoted["provenance"]["scope"] = "champion_eligible"
        promoted["content_sha256"] = canonical_record_sha256(
            {
                key: value
                for key, value in promoted.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaises(ContractValidationError):
            self.geometry_validator.validate(promoted)
        with self.assertRaisesRegex(NavigationContractError, "candidate_untrusted"):
            verify_navigation_record_integrity(promoted)

    def test_geometry_mesh_and_debug_require_exact_cross_artifact_binding(self) -> None:
        source_geometry = geometry()
        mesh = navigation_mesh()
        debug = debug_snapshot("MESH")
        verify_navigation_artifact_chain(source_geometry, mesh, debug)

        with self.assertRaisesRegex(NavigationContractError, "pgeom hash"):
            verify_geometry_mesh_binding(
                source_geometry,
                replace(mesh, geometry_content_sha256="0" * 64),
            )
        with self.assertRaisesRegex(NavigationContractError, "identity fields"):
            verify_geometry_mesh_binding(
                source_geometry,
                replace(mesh, map_signature="client-assets:azeroth:other:v1"),
            )
        shifted_bounds = Bounds3(
            Vector3(0.0, -0.5, 0.0), Vector3(9.0, 1.0, 9.0)
        )
        shifted_tile = replace(mesh.tiles[0], bounds=shifted_bounds)
        with self.assertRaisesRegex(NavigationContractError, "source tile"):
            verify_geometry_mesh_binding(
                source_geometry,
                replace(mesh, tiles=(shifted_tile,)),
            )

        with self.assertRaisesRegex(NavigationContractError, "exact pnav hash"):
            verify_mesh_debug_binding(
                mesh,
                replace(debug, navigation_mesh_content_sha256="0" * 64),
            )
        wrong_tile_hash = DebugTileHash(
            mesh.tiles[0].tile_id, "0" * 64, mesh.tiles[0].bounds
        )
        with self.assertRaisesRegex(NavigationContractError, "exact pnav tile"):
            verify_mesh_debug_binding(
                mesh,
                replace(debug, tile_hashes=(wrong_tile_hash,)),
            )
        with self.assertRaisesRegex(NavigationContractError, "Champion debug"):
            verify_mesh_debug_binding(
                mesh,
                replace(
                    debug,
                    navigation_mesh_artifact_scope=candidate_scope(
                        "lab_evaluation_only"
                    ),
                ),
            )

    def test_champion_debug_cannot_bind_a_lab_scoped_mesh(self) -> None:
        lab_scope = candidate_scope("lab_evaluation_only")
        with self.assertRaisesRegex(NavigationContractError, "Champion debug"):
            replace(
                debug_snapshot(),
                navigation_mesh_artifact_scope=lab_scope,
            )

        record = debug_snapshot().to_record()
        record["navigation_mesh_artifact_scope"] = lab_scope.to_record()
        record["content_sha256"] = canonical_record_sha256(
            {
                key: value
                for key, value in record.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaises(ContractValidationError):
            self.debug_validator.validate(record)
        with self.assertRaisesRegex(NavigationContractError, "Champion debug"):
            verify_navigation_record_integrity(record)

    def test_debug_route_and_polygons_require_exact_tile_evidence(self) -> None:
        first_bounds = Bounds3(
            Vector3(0.0, -0.5, 0.0), Vector3(2.0, 1.0, 2.0)
        )
        second_bounds = Bounds3(
            Vector3(8.0, -0.5, 0.0), Vector3(10.0, 1.0, 2.0)
        )
        disconnected_evidence = (
            DebugTileHash("pnav:fixture:a", "a" * 64, first_bounds),
            DebugTileHash("pnav:fixture:b", "b" * 64, second_bounds),
        )
        with self.assertRaisesRegex(NavigationContractError, "route segment"):
            replace(
                debug_snapshot("ROUTE"),
                tile_hashes=disconnected_evidence,
                player_position=Vector3(1.0, 0.0, 1.0),
                target_position=Vector3(9.0, 0.0, 1.0),
                route_points=(
                    Vector3(1.0, 0.0, 1.0),
                    Vector3(9.0, 0.0, 1.0),
                ),
            )

        mesh_debug = debug_snapshot("MESH")
        with self.assertRaisesRegex(NavigationContractError, "source tile evidence"):
            replace(
                mesh_debug,
                mesh_polygons=(
                    replace(
                        mesh_debug.mesh_polygons[0],
                        source_tile_id="pnav:unreferenced",
                    ),
                ),
            )
        with self.assertRaisesRegex(NavigationContractError, "source tile bounds"):
            replace(
                mesh_debug,
                mesh_polygons=(
                    replace(
                        mesh_debug.mesh_polygons[0],
                        vertices=(
                            Vector3(-0.5, 0.0, 0.0),
                            Vector3(10.0, 0.0, 0.0),
                            Vector3(0.0, 0.0, 10.0),
                        ),
                    ),
                ),
            )

        mesh = navigation_mesh()
        route_debug = debug_snapshot("ROUTE")
        narrowed = Bounds3(
            Vector3(0.0, -0.5, 0.0), Vector3(9.0, 1.0, 9.0)
        )
        mismatched_bounds = replace(
            route_debug,
            tile_hashes=(
                replace(route_debug.tile_hashes[0], bounds=narrowed),
            ),
        )
        with self.assertRaisesRegex(NavigationContractError, "exact pnav tile"):
            verify_mesh_debug_binding(mesh, mismatched_bounds)
        unsupported_polygon_index = replace(
            mesh_debug,
            mesh_polygons=(
                replace(
                    mesh_debug.mesh_polygons[0],
                    source_polygon_index=1,
                ),
            ),
        )
        with self.assertRaisesRegex(NavigationContractError, "payload"):
            verify_mesh_debug_binding(mesh, unsupported_polygon_index)

    def test_input_forms_are_bounded_before_copy_or_utf8_allocation(self) -> None:
        oversized = bytearray(b'{"a":1}')
        with patch.object(navigation_contracts, "MAX_NAVIGATION_RECORD_BYTES", 4):
            with patch.object(
                navigation_contracts,
                "_preflight_json_bytes",
                side_effect=AssertionError("copy occurred before cap"),
            ):
                with self.assertRaisesRegex(NavigationContractError, "byte budget"):
                    decode_navigation_record(oversized)
                with self.assertRaisesRegex(NavigationContractError, "byte budget"):
                    decode_navigation_record(memoryview(oversized))
            with patch.object(
                navigation_contracts,
                "_preflight_json_text",
                side_effect=AssertionError("UTF-8 allocation occurred before cap"),
            ):
                with self.assertRaisesRegex(NavigationContractError, "byte budget"):
                    decode_navigation_record("ééé")
        released = memoryview(b"{}")
        released.release()
        with self.assertRaisesRegex(NavigationContractError, "unavailable"):
            decode_navigation_record(released)

    def test_preparse_node_budget_is_exact_for_objects_keys_and_values(self) -> None:
        raw = b'{"a":1}'  # object + key + value = exactly three nodes
        with patch.object(navigation_contracts, "MAX_NAVIGATION_JSON_NODES", 2):
            with self.assertRaisesRegex(NavigationContractError, "exact global node"):
                decode_navigation_record(raw)
        with patch.object(navigation_contracts, "MAX_NAVIGATION_JSON_NODES", 3):
            with self.assertRaisesRegex(
                NavigationContractError, "unsupported navigation record type"
            ):
                decode_navigation_record(raw)

    def test_numeric_values_are_normalized_before_the_wire_hash(self) -> None:
        point = Vector3(1, 2, 3)
        self.assertTrue(all(type(value) is float for value in (point.x, point.y, point.z)))
        normalized_provenance = replace(provenance(), confidence=1)
        self.assertIs(type(normalized_provenance.confidence), float)
        integer_uncertainty = replace(debug_snapshot(), uncertainty_radius=1)
        float_uncertainty = replace(debug_snapshot(), uncertainty_radius=1.0)
        self.assertIs(type(integer_uncertainty.uncertainty_radius), float)
        self.assertEqual(
            integer_uncertainty.content_sha256,
            float_uncertainty.content_sha256,
        )
        with self.assertRaisesRegex(NavigationContractError, "exact IEEE-754"):
            canonical_wire_bytes({"unsafe_integer": 1 << 53})

    def test_schema_semantics_and_wire_share_mathematical_number_categories(self) -> None:
        equivalent = geometry().to_record()
        equivalent["format_version"] = 1.0
        equivalent["tile_count"] = 1.0
        equivalent["tiles"][0]["grid_x"] = 31.0
        equivalent["tiles"][0]["vertices"][0]["x"] = 0
        tile_unsigned = {
            key: value
            for key, value in equivalent["tiles"][0].items()
            if key != "tile_sha256"
        }
        equivalent["tiles"][0]["tile_sha256"] = canonical_record_sha256(
            tile_unsigned
        )
        equivalent["content_sha256"] = canonical_record_sha256(
            {
                key: value
                for key, value in equivalent.items()
                if key != "content_sha256"
            }
        )
        self.geometry_validator.validate(equivalent)
        normalized = validate_navigation_record_semantics(equivalent)
        self.assertIs(type(normalized.tiles[0].grid_x), int)
        self.assertIs(type(normalized.tiles[0].vertices[0].x), float)
        self.assertEqual(normalized.content_sha256, geometry().content_sha256)

        fractional_integer = copy.deepcopy(equivalent)
        fractional_integer["tiles"][0]["grid_x"] = 31.5
        fractional_integer["tiles"][0]["tile_sha256"] = canonical_record_sha256(
            {
                key: value
                for key, value in fractional_integer["tiles"][0].items()
                if key != "tile_sha256"
            }
        )
        fractional_integer["content_sha256"] = canonical_record_sha256(
            {
                key: value
                for key, value in fractional_integer.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaises(ContractValidationError):
            self.geometry_validator.validate(fractional_integer)
        with self.assertRaisesRegex(NavigationContractError, "integer"):
            validate_navigation_record_semantics(fractional_integer)

        boolean_number = copy.deepcopy(equivalent)
        boolean_number["tiles"][0]["vertices"][0]["x"] = True
        boolean_number["tiles"][0]["tile_sha256"] = canonical_record_sha256(
            {
                key: value
                for key, value in boolean_number["tiles"][0].items()
                if key != "tile_sha256"
            }
        )
        boolean_number["content_sha256"] = canonical_record_sha256(
            {
                key: value
                for key, value in boolean_number.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaises(ContractValidationError):
            self.geometry_validator.validate(boolean_number)
        with self.assertRaisesRegex(NavigationContractError, "finite binary64"):
            validate_navigation_record_semantics(boolean_number)

        boolean_integer = copy.deepcopy(equivalent)
        boolean_integer["format_version"] = True
        boolean_integer["content_sha256"] = canonical_record_sha256(
            {
                key: value
                for key, value in boolean_integer.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaises(ContractValidationError):
            self.geometry_validator.validate(boolean_integer)
        with self.assertRaisesRegex(NavigationContractError, "integer"):
            validate_navigation_record_semantics(boolean_integer)

    def test_v1_requires_full_geometry_to_mesh_tile_bijection(self) -> None:
        second_bounds = Bounds3(
            Vector3(10.0, -0.5, 0.0), Vector3(11.0, 1.0, 10.0)
        )
        second_tile = GeometryTile(
            tile_id="pgeom:azeroth:32:31:0",
            grid_x=32,
            grid_y=31,
            layer=0,
            bounds=second_bounds,
            vertices=(
                Vector3(10.0, 0.0, 0.0),
                Vector3(11.0, 0.0, 0.0),
                Vector3(10.0, 0.0, 10.0),
            ),
            triangles=(
                GeometryTriangle(
                    indices=(0, 1, 2),
                    area="ground",
                    material_ref="terrain:grass",
                    source_ref="adt:azeroth:32:31",
                ),
            ),
            source_asset_refs=("mpq:patch-2:azeroth:32:31",),
        )
        two_tile_geometry = replace(
            geometry(), tiles=(geometry_tile(), second_tile)
        )
        incomplete_mesh = replace(
            navigation_mesh(),
            geometry_content_sha256=two_tile_geometry.content_sha256,
        )
        with self.assertRaisesRegex(NavigationContractError, "full-tile.*bijection"):
            verify_geometry_mesh_binding(two_tile_geometry, incomplete_mesh)

    def test_detour_header_counts_bounds_and_manifest_size_are_correlated(self) -> None:
        tile = navigation_tile()
        with self.assertRaisesRegex(NavigationContractError, "counts exceed"):
            replace(tile, vertex_count=1000)

        wrong_count_payload = bytearray(FIXTURE_TILE_PAYLOAD)
        struct.pack_into("<i", wrong_count_payload, 6 * 4, 2)
        with self.assertRaisesRegex(NavigationContractError, "payload counts"):
            NavigationMeshTile.from_fixture_payload(
                tile_id="pnav:wrong-count",
                grid_x=31,
                grid_y=31,
                layer=0,
                bounds=tile_bounds(),
                vertex_count=3,
                polygon_count=1,
                payload=bytes(wrong_count_payload),
            )

        impossible_sections = bytearray(FIXTURE_TILE_PAYLOAD)
        struct.pack_into("<i", impossible_sections, 10 * 4, 1)
        with self.assertRaisesRegex(NavigationContractError, "Detour header"):
            NavigationMeshTile.from_fixture_payload(
                tile_id="pnav:impossible-sections",
                grid_x=31,
                grid_y=31,
                layer=0,
                bounds=tile_bounds(),
                vertex_count=3,
                polygon_count=1,
                payload=bytes(impossible_sections),
            )

        wrong_bounds_payload = detour_fixture_payload(
            maximum=(9.0, 1.0, 9.0)
        )
        wrong_bounds_tile = NavigationMeshTile(
            tile_id="pnav:wrong-bounds",
            grid_x=31,
            grid_y=31,
            layer=0,
            bounds=tile_bounds(),
            vertex_count=3,
            polygon_count=1,
            binary_artifact_ref=(
                f"sha256:{hashlib.sha256(wrong_bounds_payload).hexdigest()}"
            ),
            data_size_bytes=len(wrong_bounds_payload),
            tile_sha256=hashlib.sha256(wrong_bounds_payload).hexdigest(),
        )
        with self.assertRaisesRegex(NavigationContractError, "payload bounds"):
            verify_navigation_tile_payload(wrong_bounds_tile, wrong_bounds_payload)

        nonfinite_header_payload = bytearray(FIXTURE_TILE_PAYLOAD)
        struct.pack_into("<f", nonfinite_header_payload, 15 * 4, math.nan)
        nonfinite_payload = bytes(nonfinite_header_payload)
        nonfinite_header_tile = replace(
            tile,
            binary_artifact_ref=(
                f"sha256:{hashlib.sha256(nonfinite_payload).hexdigest()}"
            ),
            tile_sha256=hashlib.sha256(nonfinite_payload).hexdigest(),
        )
        with self.assertRaisesRegex(NavigationContractError, "non-finite"):
            verify_navigation_tile_payload(nonfinite_header_tile, nonfinite_payload)

        oversized_count = navigation_mesh().to_record()
        oversized_count["tiles"][0]["vertex_count"] = (
            navigation_contracts.MAX_VERTICES_PER_NAVIGATION_TILE + 1
        )
        with self.assertRaises(ContractValidationError):
            self.mesh_validator.validate(oversized_count)

    def test_detour_payload_is_structurally_validated_before_native_use(self) -> None:
        verify_navigation_tile_payload(navigation_tile(), FIXTURE_TILE_PAYLOAD)

        convex_quad = detour_quad_fixture_payload(concave=False)
        verify_navigation_tile_payload(
            navigation_tile_for_payload(
                convex_quad, vertex_count=4, polygon_count=1,
            ),
            convex_quad,
        )
        concave_quad = detour_quad_fixture_payload(concave=True)
        with self.assertRaisesRegex(NavigationContractError, "polygon is concave"):
            verify_navigation_tile_payload(
                navigation_tile_for_payload(
                    concave_quad, vertex_count=4, polygon_count=1,
                ),
                concave_quad,
            )

        near_collinear_quad = detour_quad_fixture_payload(
            concave=False, near_collinear_roundoff=True,
        )
        verify_navigation_tile_payload(
            navigation_tile_for_payload(
                near_collinear_quad, vertex_count=4, polygon_count=1,
            ),
            near_collinear_quad,
        )

        zero_links = bytearray(FIXTURE_TILE_PAYLOAD)
        struct.pack_into("<i", zero_links, 8 * 4, 0)
        zero_links_payload = bytes(zero_links)
        with self.assertRaisesRegex(NavigationContractError, "maxLinkCount"):
            verify_navigation_tile_payload(
                navigation_tile_for_payload(zero_links_payload), zero_links_payload
            )

        bad_vertex = bytearray(FIXTURE_TILE_PAYLOAD)
        polygon_offset = (
            navigation_contracts.DETOUR_TILE_HEADER_BYTES
            + 3 * navigation_contracts.DETOUR_VERTEX_BYTES
        )
        struct.pack_into("<H", bad_vertex, polygon_offset + 4, 65_534)
        bad_vertex_payload = bytes(bad_vertex)
        with self.assertRaisesRegex(NavigationContractError, "vertex index"):
            verify_navigation_tile_payload(
                navigation_tile_for_payload(bad_vertex_payload), bad_vertex_payload
            )

        bad_neighbour = bytearray(FIXTURE_TILE_PAYLOAD)
        struct.pack_into("<H", bad_neighbour, polygon_offset + 16, 2)
        bad_neighbour_payload = bytes(bad_neighbour)
        with self.assertRaisesRegex(NavigationContractError, "neighbour"):
            verify_navigation_tile_payload(
                navigation_tile_for_payload(bad_neighbour_payload),
                bad_neighbour_payload,
            )

        detail_triangle_offset = len(FIXTURE_TILE_PAYLOAD) - 4
        bad_detail_triangle = bytearray(FIXTURE_TILE_PAYLOAD)
        bad_detail_triangle[detail_triangle_offset] = 254
        bad_detail_payload = bytes(bad_detail_triangle)
        with self.assertRaisesRegex(NavigationContractError, "detail triangle"):
            verify_navigation_tile_payload(
                navigation_tile_for_payload(bad_detail_payload), bad_detail_payload
            )

        bad_bv = bytearray(FIXTURE_TILE_PAYLOAD)
        struct.pack_into("<i", bad_bv, 12 * 4, 2)
        bad_bv.extend(struct.pack("<6Hi", 0, 0, 0, 1, 1, 1, -3))
        bad_bv.extend(struct.pack("<6Hi", 0, 0, 0, 1, 1, 1, 0))
        bad_bv_payload = bytes(bad_bv)
        with self.assertRaisesRegex(NavigationContractError, "BV escape"):
            verify_navigation_tile_payload(
                navigation_tile_for_payload(bad_bv_payload), bad_bv_payload
            )

        offmesh_payload = detour_offmesh_fixture_payload()
        offmesh_tile = navigation_tile_for_payload(
            offmesh_payload, vertex_count=5, polygon_count=2
        )
        verify_navigation_tile_payload(offmesh_tile, offmesh_payload)
        bad_offmesh = bytearray(offmesh_payload)
        offmesh_connection_offset = len(bad_offmesh) - (
            navigation_contracts.DETOUR_OFFMESH_CONNECTION_BYTES
        )
        struct.pack_into("<H", bad_offmesh, offmesh_connection_offset + 28, 65_534)
        bad_offmesh_payload = bytes(bad_offmesh)
        with self.assertRaisesRegex(NavigationContractError, "off-mesh polygon index"):
            verify_navigation_tile_payload(
                navigation_tile_for_payload(
                    bad_offmesh_payload, vertex_count=5, polygon_count=2
                ),
                bad_offmesh_payload,
            )

    def test_mapping_strings_and_number_lexemes_are_bounded_before_allocation(self) -> None:
        with patch.object(navigation_contracts, "MAX_NAVIGATION_STRING_BYTES", 4):
            with self.assertRaisesRegex(NavigationContractError, "string-byte budget"):
                validate_navigation_record_semantics({"record_type": "abcdef"})

        huge_lexeme = b'{"record_type":' + b"9" * 129 + b"}"
        with patch.object(
            navigation_contracts.json,
            "loads",
            side_effect=AssertionError("huge numeric lexeme reached json.loads"),
        ):
            with self.assertRaisesRegex(NavigationContractError, "lexeme budget"):
                decode_navigation_record(huge_lexeme)
        with self.assertRaisesRegex(NavigationContractError, "finite binary64"):
            decode_navigation_record(b'{"record_type":1e9999}')

    def test_transform_determinant_handedness_and_winding_are_consistent(self) -> None:
        reflected = list(coordinate_system().world_to_nav_row_major)
        reflected[0] = -1.0
        with self.assertRaisesRegex(NavigationContractError, "transform row"):
            replace(
                coordinate_system(),
                world_to_nav_row_major=tuple(reflected),
            )
        with self.assertRaisesRegex(NavigationContractError, "winding"):
            replace(coordinate_system(), triangle_winding="counter_clockwise")

        reflected_record = geometry().to_record()
        reflected_record["coordinate_system"]["world_to_nav_row_major"][0] = -1.0
        reflected_record["content_sha256"] = canonical_record_sha256(
            {
                key: value
                for key, value in reflected_record.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaisesRegex(NavigationContractError, "transform row"):
            verify_navigation_record_integrity(reflected_record)

        identity = (
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        )
        with self.assertRaisesRegex(NavigationContractError, "transform row"):
            replace(coordinate_system(), world_to_nav_row_major=identity)

        identity_record = geometry().to_record()
        identity_record["coordinate_system"]["world_to_nav_row_major"] = list(identity)
        identity_record["content_sha256"] = canonical_record_sha256(
            {
                key: value
                for key, value in identity_record.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaisesRegex(NavigationContractError, "transform row"):
            verify_navigation_record_integrity(identity_record)

        left_handed = CoordinateSystem(
            space_id="fixture:left-handed",
            units="world_units",
            handedness="left_handed",
            axis_x="east",
            axis_y="north",
            axis_z="down",
            triangle_winding="counter_clockwise",
            world_to_nav_row_major=(
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                -1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
            ),
        )
        self.assertEqual(left_handed.handedness, "left_handed")


if __name__ == "__main__":
    unittest.main()
