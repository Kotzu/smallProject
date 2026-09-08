from __future__ import annotations

from pathlib import Path
import unittest

from scripts.run_client_world_map_bake import (
    _result_provenance,
    build_map_bake_commands,
)


class ClientWorldMapBakeRunnerTests(unittest.TestCase):
    def test_commands_use_only_client_assets_and_external_tools(self) -> None:
        commands = build_map_bake_commands(
            python_executable=Path(r"C:\Python\python.exe"),
            road_script=Path(r"E:\PA\build_adt_road_semantics.py"),
            extractor=Path(r"E:\PA\extract.exe"),
            map_builder=Path(r"E:\PA\MapBuilder.exe"),
            data_root=Path(r"E:\Games\WoW\Data"),
            asset_root=Path(r"E:\Runtime\assets"),
            nav_root=Path(r"E:\Runtime\nav"),
            map_name="Zul'gurub",
            threads=8,
        )

        self.assertIn("--extract-map", commands.extraction)
        self.assertIn("Zul'gurub", commands.extraction)
        self.assertIn("Zul'gurub", commands.semantics)
        self.assertIn("Zul'gurub", commands.navmesh)
        combined = " ".join(
            value for command in (
                commands.bvh, commands.extraction,
                commands.semantics, commands.navmesh,
            ) for value in command
        ).casefold()
        self.assertNotIn("mangos", combined)
        self.assertNotIn("database", combined)
        self.assertNotIn("realm", combined)

    def test_asset_destination_cannot_escape_its_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "escaped"):
            build_map_bake_commands(
                python_executable=Path("python"),
                road_script=Path("road.py"),
                extractor=Path("extract.exe"),
                map_builder=Path("MapBuilder.exe"),
                data_root=Path("data"),
                asset_root=Path("assets"),
                nav_root=Path("nav"),
                map_name="../outside",
                threads=8,
            )

    def test_result_provenance_is_client_only(self) -> None:
        provenance = _result_provenance({
            "product": "wow",
            "expansion": "tbc",
            "client_version": "2.4.3",
            "client_build": "8606",
            "asset_container": "mpq",
            "asset_parser_profile": "wow-wdbc-map-v1",
        })

        self.assertEqual(provenance["world_source"], "PINNED_CLIENT_ASSETS_ONLY")
        self.assertEqual(provenance["asset_adapter_id"], "wow-mpq-wdbc-v1")
        self.assertFalse(provenance["server_dependency"])
        self.assertFalse(provenance["emulator_dependency"])


if __name__ == "__main__":
    unittest.main()
