from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from perfect_assassin.adapter.world_map_area import (
    ClientAssetCalibrationProvenance,
    WorldMapAreaBinding,
    WorldMapAreaError,
    WorldMapAreaTable,
)
from perfect_assassin.adapter.coordinate_hud import decode_packet, encode_packet
from perfect_assassin.contract_validation import ContractValidator


LOCAL_TBC243_DBC = Path(r"E:\WoWserver\TBC-LAB\client-data\dbc\WorldMapArea.dbc")
LOCAL_TBC243_DBC_SHA256 = (
    "918BF402A83BAA78B0D35F0978BC760683291EE8CF48D7CE8C90E3814AA1BC7B"
)
PROFILE_PATH = Path(__file__).resolve().parents[1] / "config" / "pose" / "world-map-area-tbc243-8606.json"
PROFILE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "world-map-area-profile.schema.json"
)
SYNTHETIC_MAP_BINDINGS = (
    WorldMapAreaBinding(
        continent_index=2,
        zone_index=25,
        internal_name="SyntheticTirisfal",
        map_id=0,
        area_id=85,
    ),
)


def dbc_fixture(
    records: tuple[
        tuple[int, int, int, str, float, float, float, float, int], ...
    ] = (
        (20, 0, 85, "SyntheticTirisfal", 100.0, -100.0, 1000.0, 0.0, -1),
    ),
) -> bytes:
    strings = bytearray(b"\0")
    encoded_rows = bytearray()
    for (
        record_id,
        map_id,
        area_id,
        internal_name,
        loc_left,
        loc_right,
        loc_top,
        loc_bottom,
        virtual_map_id,
    ) in records:
        name_offset = len(strings)
        strings.extend(internal_name.encode("utf-8") + b"\0")
        encoded_rows.extend(
            struct.pack(
                "<IIIIffffi",
                record_id,
                map_id,
                area_id,
                name_offset,
                loc_left,
                loc_right,
                loc_top,
                loc_bottom,
                virtual_map_id,
            )
        )
    return (
        struct.pack("<4s4I", b"WDBC", len(records), 9, 36, len(strings))
        + encoded_rows
        + strings
    )


def table_from(
    payload: bytes,
    *,
    map_bindings: tuple[WorldMapAreaBinding, ...] = (),
) -> WorldMapAreaTable:
    return WorldMapAreaTable.from_bytes(
        payload,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        client_build="2.4.3.8606-fixture",
        build_signature="fixture:tbc243:world-map-area:v1",
        map_bindings=map_bindings,
    )


def hud_observation(
    *,
    x: float = 0.25,
    y: float = 0.75,
    client_build: str = "2.4.3.8606-fixture",
    build_signature: str = "fixture:tbc243:world-map-area:v1",
    target_profile: str = "tbc_243_fixture",
    authorization_sha256: str = "C" * 64,
    decision_context: str = "champion",
    instance_id: str | None = None,
    actor_id: str | None = None,
    memory_namespace: str | None = None,
    capture_origin: str = "replay_fixture",
    scope: str = "synthetic_fixture",
    continent_index: int = 2,
    zone_index: int = 25,
    observed_monotonic_s: float = 10.01,
    expires_monotonic_s: float = 10.6,
) -> dict:
    packet_bytes = encode_packet(
        sequence=23,
        position_available=True,
        map_context_ready=True,
        world_map_visible=False,
        x=x,
        y=y,
        continent_index=continent_index,
        zone_index=zone_index,
    )
    decoded = decode_packet(packet_bytes)
    return {
        "record_type": "coordinate_hud_observation",
        "schema_version": "2.0",
        "observation_id": "hud:world-map:fixture:0001",
        "frame_id": "frame:world-map:fixture:0001",
        "session_id": "session:world-map:fixture",
        "target_profile": target_profile,
        "authorization_sha256": authorization_sha256,
        "actor_binding": {
            "schema_version": "1.0",
            "instance_id": instance_id or f"instance:world-map:{decision_context}",
            "actor_role": (
                "champion_journey" if decision_context == "champion" else "lab_clone"
            ),
            "actor_id": actor_id or f"actor:predator:{decision_context}",
            "decision_context": decision_context,
            "memory_namespace": memory_namespace
            or (
                "memory:champion:world-map-fixture"
                if decision_context == "champion"
                else "memory:lab:world-map-fixture"
            ),
            "expected_character_name": "Predator",
            "credential_alias": f"credential:fixture:{decision_context}",
            "binding_assurance": {
                "state": "configured_expected_only",
                "evidence_refs": ["authorization:fixture:actor-expected"],
            },
        },
        "decision_context": decision_context,
        "client_build": client_build,
        "build_signature": build_signature,
        "tracking_state": "VALID",
        "reason": "fixture_position_valid",
        "confidence": 0.98,
        "timing": {
            "captured_at": "2026-08-22T21:00:00Z",
            "monotonic_timestamp_s": 10.0,
            "frame_age_ms": 1.0,
            "observed_monotonic_s": observed_monotonic_s,
            "age_at_observation_ms": 10.0,
            "freshness_limit_ms": 600.0,
            "expires_monotonic_s": expires_monotonic_s,
        },
        "protocol": {
            "magic": 165,
            "version": 3,
            "sequence": 23,
            "flags": packet_bytes[2],
            "crc_valid": True,
            "packet_hex": packet_bytes.hex(),
        },
        "position": {
            "coordinate_space": "normalized_current_zone_map",
            "x": decoded.x,
            "y": decoded.y,
            "continent_index": continent_index,
            "zone_index": zone_index,
        },
        "map_position_available": True,
        "player_state": {
            "dead_or_ghost": decoded.player_dead_or_ghost,
            "ghost": decoded.player_ghost,
        },
        "provenance": {
            "origin": "visible_addon_hud",
            "capture_origin": capture_origin,
            "capability": "self_map_position",
            "scope": scope,
            "profile_id": "coordinate_hud_tbc243_v1",
            "profile_version": "0.2.0",
            "profile_sha256": "A" * 64,
            "profile_calibration_state": "synthetic_verified",
            "evidence_refs": [
                "fixture:coordinate-hud:0001",
                "profile:coordinate-hud:fixture",
            ],
        },
        "execution_authority": False,
    }


class WorldMapAreaParserTests(unittest.TestCase):
    def test_versioned_profile_pins_build_asset_and_no_execution(self) -> None:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        ContractValidator(PROFILE_SCHEMA_PATH).validate(profile)
        self.assertEqual(profile["asset_sha256"], LOCAL_TBC243_DBC_SHA256)
        self.assertEqual(
            profile["record_fingerprint_sha256"],
            "82CB76957FC8BB0A6DB94AC1F179BE5EA3B96033AEA02ED3B597D030D9A66215",
        )
        self.assertEqual(profile["map_bindings"][0]["internal_name"], "Tirisfal")
        self.assertEqual(profile["provenance_origin"], "client_asset_calibration")
        self.assertEqual(profile["asset_location_policy"], "external_user_extracted")
        self.assertFalse(profile["execution_authority"])

    def test_self_hashed_bytes_are_always_fixture_only(self) -> None:
        payload = dbc_fixture()
        table = table_from(payload)
        record = table.resolve(internal_name="SyntheticTirisfal")
        self.assertEqual(record.record_id, 20)
        self.assertEqual(record.map_id, 0)
        self.assertEqual(record.area_id, 85)
        self.assertEqual(record.virtual_map_id, -1)
        self.assertEqual(table.provenance.origin, "synthetic_fixture")
        self.assertEqual(table.provenance.scope, "fixture_only")
        self.assertEqual(table.provenance.asset_sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(table.provenance.client_build, "2.4.3.8606-fixture")
        self.assertIsNone(table.provenance.profile)

    def test_direct_file_with_self_computed_hash_is_lab_evaluation_only(self) -> None:
        payload = dbc_fixture()
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "WorldMapArea.dbc"
            asset.write_bytes(payload)
            table = WorldMapAreaTable.from_file(
                asset,
                expected_sha256=hashlib.sha256(payload).hexdigest(),
                client_build="caller-claimed-build",
                build_signature="caller-claimed-signature",
            )
        self.assertEqual(table.provenance.origin, "client_asset_calibration")
        self.assertEqual(table.provenance.scope, "lab_evaluation_only")
        self.assertIsNone(table.provenance.profile)

    def test_direct_constructor_cannot_forge_champion_eligibility(self) -> None:
        fixture_table = table_from(dbc_fixture())
        forged = ClientAssetCalibrationProvenance(
            client_build="2.4.3.8606",
            build_signature=(
                "wow-tbc-2.4.3.8606-enGB:sha256:"
                "406DA0C1C22D6E9121FD3BC17740A0D013660A03748CFE2A235768B8C574D3E6"
            ),
            asset_name="WorldMapArea.dbc",
            asset_sha256=LOCAL_TBC243_DBC_SHA256,
            origin="client_asset_calibration",
            scope="champion_eligible",
            profile="world_map_area_tbc243_8606",
            profile_version="0.2.0",
            target_profile="tbc_243_lab",
        )
        with self.assertRaisesRegex(WorldMapAreaError, "pinned profile"):
            WorldMapAreaTable(fixture_table.records, forged)

    def test_table_identity_and_bindings_are_immutable(self) -> None:
        table = table_from(
            dbc_fixture(),
            map_bindings=SYNTHETIC_MAP_BINDINGS,
        )
        with self.assertRaises(AttributeError):
            table.provenance = ClientAssetCalibrationProvenance(  # type: ignore[misc]
                client_build="forged",
                build_signature="forged",
                asset_name="WorldMapArea.dbc",
                asset_sha256="0" * 64,
                origin="client_asset_calibration",
                scope="champion_eligible",
            )
        with self.assertRaises(AttributeError):
            table._records = ()  # type: ignore[misc]

    def test_profile_loader_rejects_synthetic_asset_and_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = dbc_fixture()
            asset = root / "dbc" / "WorldMapArea.dbc"
            asset.parent.mkdir()
            asset.write_bytes(payload)
            with self.assertRaisesRegex(WorldMapAreaError, "SHA-256 mismatch"):
                WorldMapAreaTable.from_profile(PROFILE_PATH, asset_root=root)

            forged_profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            forged_profile["asset_sha256"] = hashlib.sha256(payload).hexdigest().upper()
            forged_profile_path = root / "forged-profile.json"
            forged_profile_path.write_text(
                json.dumps(forged_profile),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(WorldMapAreaError, "contract validation"):
                WorldMapAreaTable.from_profile(forged_profile_path, asset_root=root)

            with self.assertRaisesRegex(WorldMapAreaError, "stay below"):
                WorldMapAreaTable._resolve_profile_asset(
                    root,
                    "../WorldMapArea.dbc",
                    "WorldMapArea.dbc",
                )

    def test_sha256_and_build_identity_are_mandatory(self) -> None:
        payload = dbc_fixture()
        with self.assertRaisesRegex(WorldMapAreaError, "SHA-256 mismatch"):
            WorldMapAreaTable.from_bytes(
                payload,
                expected_sha256="0" * 64,
                client_build="2.4.3.8606-fixture",
                build_signature="fixture:tbc243:world-map-area:v1",
            )
        with self.assertRaisesRegex(WorldMapAreaError, "64 hexadecimal"):
            WorldMapAreaTable.from_bytes(
                payload,
                expected_sha256="not-a-hash",
                client_build="2.4.3.8606-fixture",
                build_signature="fixture:tbc243:world-map-area:v1",
            )
        with self.assertRaisesRegex(WorldMapAreaError, "client_build"):
            WorldMapAreaTable.from_bytes(
                payload,
                expected_sha256=hashlib.sha256(payload).hexdigest(),
                client_build="",
                build_signature="fixture:tbc243:world-map-area:v1",
            )

    def test_rejects_invalid_wdbc_shape_and_string_references(self) -> None:
        cases: list[tuple[str, bytes, str]] = []

        bad_magic = bytearray(dbc_fixture())
        bad_magic[0:4] = b"XXXX"
        cases.append(("magic", bytes(bad_magic), "magic"))

        wrong_fields = bytearray(dbc_fixture())
        struct.pack_into("<I", wrong_fields, 8, 8)
        cases.append(("fields", bytes(wrong_fields), "field count"))

        wrong_row_size = bytearray(dbc_fixture())
        struct.pack_into("<I", wrong_row_size, 12, 40)
        cases.append(("row_size", bytes(wrong_row_size), "record size"))

        truncated = dbc_fixture()[:-1]
        cases.append(("truncated", truncated, "byte length"))

        trailing = dbc_fixture() + b"X"
        cases.append(("trailing", trailing, "byte length"))

        bad_string_offset = bytearray(dbc_fixture())
        struct.pack_into("<I", bad_string_offset, 20 + 12, 65535)
        cases.append(("string_offset", bytes(bad_string_offset), "out-of-bounds"))

        unterminated = bytearray(dbc_fixture())
        unterminated[-1] = ord("X")
        cases.append(("unterminated", bytes(unterminated), "unterminated"))

        for label, payload, message in cases:
            with self.subTest(case=label):
                with self.assertRaisesRegex(WorldMapAreaError, message):
                    table_from(payload)

    def test_rejects_duplicate_record_ids_and_degenerate_or_nonfinite_bounds(self) -> None:
        duplicate = dbc_fixture(
            (
                (1, 0, 1, "One", 10.0, 0.0, 10.0, 0.0, -1),
                (1, 0, 2, "Two", 20.0, 0.0, 20.0, 0.0, -1),
            )
        )
        with self.assertRaisesRegex(WorldMapAreaError, "duplicate record ID"):
            table_from(duplicate)

        degenerate = dbc_fixture(
            ((1, 0, 1, "Flat", 10.0, 10.0, 20.0, 0.0, -1),)
        )
        with self.assertRaisesRegex(WorldMapAreaError, "degenerate"):
            table_from(degenerate)

        nonfinite = dbc_fixture(
            ((1, 0, 1, "Infinite", 10.0, 0.0, float("inf"), 0.0, -1),)
        )
        with self.assertRaisesRegex(WorldMapAreaError, "non-finite"):
            table_from(nonfinite)

    def test_exact_resolution_fails_on_missing_or_ambiguous_selector(self) -> None:
        table = table_from(
            dbc_fixture(
                (
                    (1, 0, 10, "Shared", 10.0, 0.0, 10.0, 0.0, -1),
                    (2, 1, 11, "Shared", 20.0, 0.0, 20.0, 0.0, -1),
                )
            )
        )
        with self.assertRaisesRegex(WorldMapAreaError, "At least one"):
            table.resolve()
        with self.assertRaisesRegex(WorldMapAreaError, "Ambiguous"):
            table.resolve(internal_name="Shared")
        with self.assertRaisesRegex(WorldMapAreaError, "No WorldMapArea"):
            table.resolve(internal_name="shared")
        with self.assertRaisesRegex(WorldMapAreaError, "map_id must be a non-negative"):
            table.resolve(map_id=-1)
        self.assertEqual(
            table.resolve(internal_name="Shared", map_id=1, area_id=11).record_id,
            2,
        )

    def test_map_id_is_uint32_while_virtual_map_id_remains_signed(self) -> None:
        table = table_from(
            dbc_fixture(
                (
                    (
                        7,
                        0xFFFFFFFF,
                        12,
                        "UnsignedMap",
                        10.0,
                        0.0,
                        10.0,
                        0.0,
                        -1,
                    ),
                )
            )
        )
        record = table.resolve(map_id=0xFFFFFFFF, area_id=12)
        self.assertEqual(record.map_id, 0xFFFFFFFF)
        self.assertEqual(record.virtual_map_id, -1)


class WorldMapAreaTransformTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = table_from(
            dbc_fixture(),
            map_bindings=SYNTHETIC_MAP_BINDINGS,
        )

    def test_cmangos_axis_convention_is_applied_without_fabricating_height(self) -> None:
        coordinate = self.table.transform(
            hud_observation(),
            evaluated_monotonic_s=10.1,
        )
        expected = decode_packet(
            encode_packet(
                sequence=23,
                position_available=True,
                map_context_ready=True,
                world_map_visible=False,
                x=0.25,
                y=0.75,
                continent_index=2,
                zone_index=25,
            )
        )
        self.assertAlmostEqual(coordinate.world_x, 1000.0 - expected.y * 1000.0)
        self.assertAlmostEqual(coordinate.world_y, 100.0 - expected.x * 200.0)
        self.assertEqual(coordinate.coordinate_space, "wow_world_map_2d:map:0")
        self.assertFalse(hasattr(coordinate, "z"))
        self.assertAlmostEqual(coordinate.confidence, 0.98)
        self.assertEqual(
            coordinate.provenance.origin,
            "coordinate_hud_world_map_transform",
        )
        self.assertEqual(coordinate.provenance.scope, "fixture_only")
        self.assertEqual(
            coordinate.provenance.calibration.origin,
            "synthetic_fixture",
        )
        self.assertEqual(
            coordinate.provenance.position.scope,
            "synthetic_fixture",
        )
        self.assertEqual(
            coordinate.provenance.position.session_id,
            "session:world-map:fixture",
        )
        self.assertEqual(
            coordinate.provenance.position.authorization_sha256,
            "C" * 64,
        )
        actor = coordinate.provenance.position.actor_binding
        self.assertEqual(actor.instance_id, "instance:world-map:champion")
        self.assertEqual(actor.actor_id, "actor:predator:champion")
        self.assertEqual(actor.memory_namespace, "memory:champion:world-map-fixture")
        self.assertEqual(actor.expected_character_name, "Predator")
        self.assertEqual(
            actor.binding_assurance.state,
            "configured_expected_only",
        )
        self.assertIn(
            "fixture:coordinate-hud:0001",
            coordinate.provenance.evidence_refs,
        )
        self.assertTrue(
            any(
                reference.startswith("asset:WorldMapArea.dbc:sha256:")
                for reference in coordinate.provenance.evidence_refs
            )
        )
        self.assertFalse(coordinate.provenance.execution_authority)

        uncertainty = coordinate.uncertainty
        self.assertAlmostEqual(
            uncertainty.quantization_radius_world_x,
            1000.0 / (2.0 * 65535.0),
        )
        self.assertAlmostEqual(
            uncertainty.quantization_radius_world_y,
            200.0 / (2.0 * 65535.0),
        )
        self.assertIsNone(uncertainty.total_radius_world_x)
        self.assertIsNone(uncertainty.total_radius_world_y)
        self.assertEqual(uncertainty.source_uncertainty_state, "uncharacterized")

    def test_distinct_lab_clone_actor_bindings_survive_without_cross_talk(self) -> None:
        observation_a = hud_observation(
            decision_context="lab_clone",
            instance_id="instance:world-map:clone-a",
            actor_id="actor:predator:clone-a",
            memory_namespace="memory:lab:world-map:clone-a",
        )
        observation_b = hud_observation(
            decision_context="lab_clone",
            instance_id="instance:world-map:clone-b",
            actor_id="actor:predator:clone-b",
            memory_namespace="memory:lab:world-map:clone-b",
        )

        coordinate_a = self.table.transform(
            observation_a,
            evaluated_monotonic_s=10.1,
        )
        coordinate_b = self.table.transform(
            observation_b,
            evaluated_monotonic_s=10.1,
        )
        actor_a = coordinate_a.provenance.position.actor_binding
        actor_b = coordinate_b.provenance.position.actor_binding

        self.assertEqual(actor_a.instance_id, "instance:world-map:clone-a")
        self.assertEqual(actor_b.instance_id, "instance:world-map:clone-b")
        self.assertEqual(actor_a.memory_namespace, "memory:lab:world-map:clone-a")
        self.assertEqual(actor_b.memory_namespace, "memory:lab:world-map:clone-b")
        self.assertNotEqual(actor_a, actor_b)

        observation_a["actor_binding"]["memory_namespace"] = (
            "memory:lab:world-map:mutated-after-transform"
        )
        observation_a["authorization_sha256"] = "E" * 64
        self.assertEqual(
            coordinate_a.provenance.position.actor_binding.memory_namespace,
            "memory:lab:world-map:clone-a",
        )
        self.assertEqual(
            coordinate_a.provenance.position.authorization_sha256,
            "C" * 64,
        )

    def test_uncharacterized_source_uncertainty_never_silently_becomes_zero(self) -> None:
        coordinate = self.table.transform(
            hud_observation(),
            evaluated_monotonic_s=10.1,
        )
        uncertainty = coordinate.uncertainty
        self.assertEqual(uncertainty.source_uncertainty_state, "uncharacterized")
        self.assertIsNone(uncertainty.source_radius_world_x)
        self.assertIsNone(uncertainty.source_radius_world_y)
        self.assertIsNone(uncertainty.total_radius_world_x)
        self.assertIsNone(uncertainty.total_radius_world_y)

    def test_invalid_normalized_coordinates_fail_closed(self) -> None:
        for x, y in ((-0.1, 0.5), (1.1, 0.5), (float("nan"), 0.5), (0.5, True)):
            with self.subTest(x=x, y=y):
                invalid = hud_observation()
                invalid["position"]["x"] = x
                invalid["position"]["y"] = y
                with self.assertRaises(WorldMapAreaError):
                    self.table.transform(
                        invalid,
                        evaluated_monotonic_s=10.1,
                    )
        with self.assertRaises(TypeError):
            self.table.transform(
                hud_observation(x=0.5, y=0.5),
                evaluated_monotonic_s=10.1,
                normalized_quantization_step=1e-12,
            )
        with self.assertRaises(TypeError):
            self.table.transform(
                hud_observation(x=0.5, y=0.5),
                evaluated_monotonic_s=10.1,
                source_uncertainty_world_units=(0.0, 0.0),
            )

    def test_bare_float_position_cannot_create_a_world_map_fact(self) -> None:
        with self.assertRaisesRegex(WorldMapAreaError, "versioned coordinate HUD"):
            self.table.transform(
                0.25,  # type: ignore[arg-type]
                evaluated_monotonic_s=10.1,
            )

    def test_scope_composition_never_promotes_raw_hud_evidence(self) -> None:
        cases = (
            ("champion_eligible", "unpromoted_evaluation_only", "unpromoted_evaluation_only"),
            ("champion_eligible", "lab_evaluation_only", "lab_evaluation_only"),
            ("champion_eligible", "synthetic_fixture", "fixture_only"),
            ("lab_evaluation_only", "unpromoted_evaluation_only", "lab_evaluation_only"),
            ("fixture_only", "unpromoted_evaluation_only", "fixture_only"),
        )
        for calibration_scope, position_scope, expected in cases:
            with self.subTest(
                calibration_scope=calibration_scope,
                position_scope=position_scope,
            ):
                self.assertEqual(
                    WorldMapAreaTable._derived_scope(
                        calibration_scope,
                        position_scope,
                    ),
                    expected,
                )

    def test_position_contract_binding_and_freshness_fail_closed(self) -> None:
        mismatch = hud_observation(build_signature="other-build")
        with self.assertRaisesRegex(WorldMapAreaError, "build_signature"):
            self.table.transform(
                mismatch,
                evaluated_monotonic_s=10.1,
            )

        with self.assertRaisesRegex(WorldMapAreaError, "expired"):
            self.table.transform(
                hud_observation(),
                evaluated_monotonic_s=10.7,
            )

        divergent_position = hud_observation()
        divergent_position["position"]["x"] += 1.0 / 65535.0
        with self.assertRaisesRegex(WorldMapAreaError, "observation contract"):
            self.table.transform(
                divergent_position,
                evaluated_monotonic_s=10.1,
            )

        forged_freshness = hud_observation()
        forged_freshness["timing"].update(
            {
                "frame_age_ms": 9999.0,
                "age_at_observation_ms": 9999.0,
                "freshness_limit_ms": 1.0,
                "observed_monotonic_s": 10.01,
                "expires_monotonic_s": 200.0,
            }
        )
        with self.assertRaisesRegex(WorldMapAreaError, "observation contract"):
            self.table.transform(
                forged_freshness,
                evaluated_monotonic_s=10.1,
            )

        understated_age = hud_observation()
        understated_age["timing"]["age_at_observation_ms"] = 1.0
        with self.assertRaisesRegex(WorldMapAreaError, "observation contract"):
            self.table.transform(
                understated_age,
                evaluated_monotonic_s=10.1,
            )

        inconsistent_expiry = hud_observation(expires_monotonic_s=11.0)
        with self.assertRaisesRegex(WorldMapAreaError, "observation contract"):
            self.table.transform(
                inconsistent_expiry,
                evaluated_monotonic_s=10.1,
            )

    def test_hud_map_context_cannot_be_substituted_by_the_caller(self) -> None:
        with self.assertRaisesRegex(WorldMapAreaError, "map context"):
            self.table.transform(
                hud_observation(continent_index=2, zone_index=24),
                evaluated_monotonic_s=10.1,
            )
        with self.assertRaises(TypeError):
            self.table.transform(
                hud_observation(),
                evaluated_monotonic_s=10.1,
                internal_name="AnotherZone",
            )

    @unittest.skipUnless(
        LOCAL_TBC243_DBC.is_file(),
        "local extracted TBC 2.4.3 WorldMapArea.dbc is unavailable",
    )
    def test_local_tbc243_tirisfal_asset_and_historical_vector_regression(self) -> None:
        table = WorldMapAreaTable.from_profile(
            PROFILE_PATH,
            asset_root=LOCAL_TBC243_DBC.parent.parent,
        )
        tirisfal = table.resolve(internal_name="Tirisfal", map_id=0, area_id=85)
        self.assertEqual(tirisfal.record_id, 20)
        self.assertAlmostEqual(tirisfal.loc_left, 3033.333251953125)
        self.assertAlmostEqual(tirisfal.loc_right, -1485.4166259765625)
        self.assertAlmostEqual(tirisfal.loc_top, 3837.499755859375)
        self.assertAlmostEqual(tirisfal.loc_bottom, 824.9999389648438)

        coordinate = table.transform(
            hud_observation(
                x=0.29456015869382773,
                y=0.6467078660257878,
                client_build="2.4.3.8606",
                build_signature=(
                    "wow-tbc-2.4.3.8606-enGB:sha256:"
                    "406DA0C1C22D6E9121FD3BC17740A0D013660A03748CFE2A235768B8C574D3E6"
                ),
                target_profile="tbc_243_lab",
                decision_context="champion",
            ),
            evaluated_monotonic_s=10.1,
        )
        self.assertAlmostEqual(coordinate.world_x, 1889.2924278724363, places=9)
        self.assertAlmostEqual(coordinate.world_y, 1702.2895708124415, places=9)
        self.assertEqual(
            coordinate.provenance.calibration.asset_sha256.upper(),
            LOCAL_TBC243_DBC_SHA256,
        )
        self.assertEqual(
            coordinate.provenance.calibration.origin,
            "client_asset_calibration",
        )
        self.assertEqual(
            coordinate.provenance.calibration.scope,
            "champion_eligible",
        )
        self.assertEqual(
            coordinate.provenance.scope,
            "fixture_only",
        )
        self.assertEqual(
            coordinate.provenance.calibration.profile,
            "world_map_area_tbc243_8606",
        )
        self.assertFalse(coordinate.provenance.execution_authority)


if __name__ == "__main__":
    unittest.main()
