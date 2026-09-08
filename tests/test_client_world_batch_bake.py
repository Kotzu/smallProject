from __future__ import annotations

from pathlib import Path
import unittest

from scripts.run_client_world_batch_bake import _map_command, _selected_maps


class ClientWorldBatchBakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = {
            "maps": [
                {
                    "internal_name": "Azeroth",
                    "wdt_present": True,
                    "adt_count": 2,
                },
                {
                    "internal_name": "Expansion01",
                    "wdt_present": True,
                    "adt_count": 1,
                },
                {
                    "internal_name": "Empty",
                    "wdt_present": True,
                    "adt_count": 0,
                },
            ]
        }

    def test_selection_preserves_requested_order(self) -> None:
        self.assertEqual(
            _selected_maps(self.inventory, ("Expansion01", "Azeroth")),
            ("Expansion01", "Azeroth"),
        )

    def test_selection_rejects_duplicates_and_maps_without_adt(self) -> None:
        with self.assertRaises(ValueError):
            _selected_maps(self.inventory, ("Azeroth", "Azeroth"))
        with self.assertRaises(ValueError):
            _selected_maps(self.inventory, ("Empty",))

    def test_command_keeps_paths_as_atomic_arguments(self) -> None:
        command = _map_command(
            inventory=Path("inventory.json"),
            map_name="Expansion01",
            extractor=Path("extractor.exe"),
            map_builder=Path("Map Builder.exe"),
            data_root=Path("WoW Data"),
            asset_root=Path("assets"),
            nav_root=Path("nav"),
            queue_output=Path("queue.json"),
            result=Path("result.json"),
            threads=16,
            timeout_seconds=21600,
        )
        self.assertIn("Map Builder.exe", command)
        self.assertIn("WoW Data", command)
        self.assertEqual(command[-4:], ("--threads", "16", "--timeout-seconds", "21600"))


if __name__ == "__main__":
    unittest.main()
