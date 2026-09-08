from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from perfect_assassin.movement.standalone_world_pack import StandaloneWorldPackError
from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)


ROOT = Path(__file__).resolve().parents[1]


class WorldPackRuntimeProfileTests(unittest.TestCase):
    def _opened(self, *, catalog_id: str = "wow.tbc.2.4.3.8606.client-world-v1"):
        catalog = SimpleNamespace(
            catalog_id=catalog_id,
            target_profile="tbc_243_lab",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            nav_profile_id="tbc243-human-road-corridor-v6",
            maps=(SimpleNamespace(map_id=0, internal_name="Azeroth"),),
        )
        return SimpleNamespace(catalog=catalog, manifest={})

    def test_profile_resolves_pack_below_operator_selected_store(self) -> None:
        source = ROOT / "config" / "navigation" / "world-pack-runtime-tbc243-tirisfal-v2.json"
        profile = json.loads(source.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            with patch(
                "perfect_assassin.movement.world_pack_runtime.open_standalone_world_pack",
                return_value=self._opened(),
            ) as opener:
                binding = load_world_pack_runtime_profile(
                    path,
                    store_root=root / "store",
                    profile_schema_path=ROOT / "contracts" / "world-pack-runtime-profile.schema.json",
                    pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
                    catalog_schema_path=ROOT / "contracts" / "client-world-catalog.schema.json",
                )
            self.assertEqual(binding.profile_id, profile["profile_id"])
            self.assertEqual(
                opener.call_args.args[0],
                (root / "store" / profile["pack_directory_name"]).resolve(),
            )

    def test_profile_and_bundled_catalog_identity_must_match(self) -> None:
        source = ROOT / "config" / "navigation" / "world-pack-runtime-tbc243-tirisfal-v2.json"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "profile.json"
            path.write_bytes(source.read_bytes())
            with patch(
                "perfect_assassin.movement.world_pack_runtime.open_standalone_world_pack",
                return_value=self._opened(catalog_id="different.catalog"),
            ):
                with self.assertRaisesRegex(StandaloneWorldPackError, "catalog_id"):
                    load_world_pack_runtime_profile(
                        path,
                        store_root=root / "store",
                        profile_schema_path=ROOT / "contracts" / "world-pack-runtime-profile.schema.json",
                        pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
                        catalog_schema_path=ROOT / "contracts" / "client-world-catalog.schema.json",
                    )


if __name__ == "__main__":
    unittest.main()
