from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from perfect_assassin.movement.world_map_registry import (
    inspect_world_map_profile,
    load_world_map_registry,
)


ROOT = Path(__file__).parents[1]


class WorldMapRegistryTests(unittest.TestCase):
    def test_checked_in_registry_covers_known_tbc_maps(self) -> None:
        profiles = load_world_map_registry(
            ROOT / "config" / "navigation" / "world-map-registry-tbc243.json",
            schema_path=ROOT / "contracts" / "world-map-registry.schema.json",
        )
        self.assertEqual(len(profiles), 83)
        self.assertTrue({0, 1, 33, 47, 129, 189, 209, 289, 329, 530, 532, 543, 568, 580, 585}.issubset({profile.map_id for profile in profiles}))
        self.assertIn("Shadowfang", {profile.internal_name for profile in profiles})
        self.assertIn("RazorfenKraulInstance", {profile.internal_name for profile in profiles})
        self.assertIn("Karazahn", {profile.internal_name for profile in profiles})
        self.assertTrue(all(
            profile.runtime_profile is None
            or profile.runtime_profile.name.startswith("world-pack-runtime-")
            for profile in profiles
        ))
        azeroth = next(profile for profile in profiles if profile.map_id == 0)
        self.assertTrue(azeroth.semantic_catalog is not None)
        self.assertTrue(azeroth.structure_index is not None)
        self.assertTrue(azeroth.structure_access_graph is not None)
        kalimdor = next(profile for profile in profiles if profile.map_id == 1)
        self.assertIsNone(kalimdor.semantic_catalog)
        self.assertTrue(kalimdor.structure_index is not None)
        self.assertTrue(kalimdor.structure_access_graph is not None)
        kalimdor_readiness = inspect_world_map_profile(kalimdor)
        self.assertTrue(kalimdor_readiness.structure_index_ready)
        self.assertTrue(kalimdor_readiness.structure_access_graph_ready)
        self.assertTrue(kalimdor_readiness.topographic_ready)
        self.assertFalse(kalimdor_readiness.semantic_catalog_ready)
        self.assertTrue(inspect_world_map_profile(azeroth).autonomous_ready)
        self.assertTrue(inspect_world_map_profile(azeroth).topographic_ready)
        self.assertFalse(kalimdor_readiness.autonomous_ready)
        expansion = next(profile for profile in profiles if profile.map_id == 530)
        expansion_readiness = inspect_world_map_profile(expansion)
        self.assertTrue(expansion_readiness.structure_index_ready)
        self.assertTrue(expansion_readiness.structure_access_graph_ready)
        self.assertTrue(expansion_readiness.topographic_ready)
        self.assertFalse(expansion_readiness.semantic_catalog_ready)
        self.assertFalse(expansion_readiness.autonomous_ready)
        proof_maps = [next(profile for profile in profiles if profile.map_id == map_id) for map_id in (47, 532)]
        self.assertTrue(all(profile.runtime_profile is not None for profile in proof_maps))
        self.assertTrue(all(not inspect_world_map_profile(profile).autonomous_ready for profile in proof_maps))
        razorfen = next(profile for profile in profiles if profile.map_id == 47)
        self.assertTrue(inspect_world_map_profile(razorfen).topographic_ready)
        razorfen_downs = next(profile for profile in profiles if profile.map_id == 129)
        razorfen_downs_readiness = inspect_world_map_profile(razorfen_downs)
        self.assertTrue(razorfen_downs_readiness.topographic_ready)
        self.assertFalse(razorfen_downs_readiness.autonomous_ready)
        monastery = next(profile for profile in profiles if profile.map_id == 189)
        monastery_readiness = inspect_world_map_profile(monastery)
        self.assertTrue(monastery_readiness.topographic_ready)
        self.assertFalse(monastery_readiness.autonomous_ready)
        tanaris = next(profile for profile in profiles if profile.map_id == 209)
        tanaris_readiness = inspect_world_map_profile(tanaris)
        self.assertTrue(tanaris_readiness.topographic_ready)
        self.assertFalse(tanaris_readiness.autonomous_ready)
        scholomance = next(profile for profile in profiles if profile.map_id == 289)
        scholomance_readiness = inspect_world_map_profile(scholomance)
        self.assertTrue(scholomance_readiness.topographic_ready)
        self.assertFalse(scholomance_readiness.autonomous_ready)
        stratholme = next(profile for profile in profiles if profile.map_id == 329)
        stratholme_readiness = inspect_world_map_profile(stratholme)
        self.assertTrue(stratholme_readiness.topographic_ready)
        self.assertFalse(stratholme_readiness.autonomous_ready)
        hellfire = next(profile for profile in profiles if profile.map_id == 543)
        hellfire_readiness = inspect_world_map_profile(hellfire)
        self.assertTrue(hellfire_readiness.topographic_ready)
        self.assertFalse(hellfire_readiness.autonomous_ready)
        sunwell_plateau = next(profile for profile in profiles if profile.map_id == 580)
        sunwell_plateau_readiness = inspect_world_map_profile(sunwell_plateau)
        self.assertTrue(sunwell_plateau_readiness.topographic_ready)
        self.assertFalse(sunwell_plateau_readiness.autonomous_ready)
        zulaman = next(profile for profile in profiles if profile.map_id == 568)
        zulaman_readiness = inspect_world_map_profile(zulaman)
        self.assertTrue(zulaman_readiness.topographic_ready)
        self.assertFalse(zulaman_readiness.autonomous_ready)
        sunwell = next(profile for profile in profiles if profile.map_id == 585)
        sunwell_readiness = inspect_world_map_profile(sunwell)
        self.assertTrue(sunwell_readiness.topographic_ready)
        self.assertFalse(sunwell_readiness.autonomous_ready)
        inventory_only = next(profile for profile in profiles if profile.map_id not in {0, 1, 33, 47, 129, 189, 209, 289, 329, 530, 532, 543, 568, 580, 585})
        self.assertIsNone(inventory_only.runtime_profile)
        self.assertFalse(inspect_world_map_profile(inventory_only).autonomous_ready)

    def test_duplicate_map_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text(
                '{"record_type":"tbc243_world_map_registry","schema_version":"1.0",'
                '"client_build":"2.4.3.8606","maps":['
                '{"map_id":0,"internal_name":"A","runtime_profile":"a.json","execution_authority":false},'
                '{"map_id":0,"internal_name":"B","runtime_profile":"b.json","execution_authority":false}'
                '],"execution_authority":false}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_world_map_registry(
                    path,
                    schema_path=ROOT / "contracts" / "world-map-registry.schema.json",
                )

    def test_readiness_rejects_cross_map_artifacts_even_when_files_exist(self) -> None:
        """A stale file must not promote an inventory profile to autonomous."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime.json"
            runtime.write_text(
                '{"record_type":"world_pack_runtime_profile",'
                '"schema_version":"1.0","execution_authority":false,'
                '"maps":[{"map_id":7,"internal_name":"OtherMap"}]}',
                encoding="utf-8",
            )
            semantic = root / "semantic.json"
            semantic.write_text(
                '{"record_type":"semantic_location_catalog",'
                '"schema_version":"1.0","map_name":"OtherMap",'
                '"zone_index":1,"coordinate_system":"tbc243_client_world_xy",'
                '"atlas_calibration":"WorldMapArea.dbc:OtherMap",'
                '"locations":[{"id":"landmark:other","name":"Other",'
                '"world":[1,2]}]}',
                encoding="utf-8",
            )
            structure = root / "structure.json"
            structure.write_text(
                '{"record_type":"world_structure_index","schema_version":"1.0",'
                '"map_id":7,"map_name":"OtherMap","execution_authority":false}',
                encoding="utf-8",
            )
            access = root / "access.json"
            access.write_text(
                '{"record_type":"structure_access_graph","schema_version":"1.0",'
                '"map_id":7,"map_name":"OtherMap","execution_authority":false}',
                encoding="utf-8",
            )
            profile = type("Profile", (), {
                "map_id": 8,
                "internal_name": "SelectedMap",
                "runtime_profile": runtime,
                "semantic_catalog": semantic,
                "structure_index": structure,
                "structure_access_graph": access,
            })()

            readiness = inspect_world_map_profile(profile)

        self.assertFalse(readiness.runtime_profile_ready)
        self.assertFalse(readiness.semantic_catalog_ready)
        self.assertFalse(readiness.structure_index_ready)
        self.assertFalse(readiness.structure_access_graph_ready)
        self.assertFalse(readiness.topographic_ready)
        self.assertFalse(readiness.autonomous_ready)


if __name__ == "__main__":
    unittest.main()
