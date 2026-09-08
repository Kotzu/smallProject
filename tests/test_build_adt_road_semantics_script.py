from pathlib import Path
import tempfile
import unittest

from scripts.build_adt_road_semantics import discover_adt_assets


class BuildAdtRoadSemanticsScriptTests(unittest.TestCase):
    def test_discovers_any_versioned_client_map_without_hardcoded_azeroth(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Shadowfang_29_34.adt").touch()
            (root / "Shadowfang_25_30.adt").touch()
            (root / "Azeroth_28_27.adt").touch()

            discovered = discover_adt_assets(root, map_name="Shadowfang")

        self.assertEqual(
            tuple((item[0].name, item[1], item[2]) for item in discovered),
            (
                ("Shadowfang_25_30.adt", 25, 30),
                ("Shadowfang_29_34.adt", 29, 34),
            ),
        )

    def test_rejects_path_like_or_out_of_grid_asset_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Shadowfang_64_30.adt").touch()

            with self.assertRaisesRegex(ValueError, "coordinates"):
                discover_adt_assets(root, map_name="Shadowfang")
            with self.assertRaisesRegex(ValueError, "map name"):
                discover_adt_assets(root, map_name="../Shadowfang")

    def test_accepts_exact_map_dbc_names_with_space_or_apostrophe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Zul'gurub_33_52.adt").touch()
            (root / "Stratholme Raid_37_24.adt").touch()

            zul = discover_adt_assets(root, map_name="Zul'gurub")
            raid = discover_adt_assets(root, map_name="Stratholme Raid")

        self.assertEqual(zul[0][1:], (33, 52))
        self.assertEqual(raid[0][1:], (37, 24))


if __name__ == "__main__":
    unittest.main()
