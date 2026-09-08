from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from perfect_assassin.movement.standalone_world_pack import (
    StandaloneWorldPackError,
)
from perfect_assassin.movement.world_pack_viewer import (
    build_world_pack_viewer_launch,
)


class WorldPackViewerLaunchTests(unittest.TestCase):
    def _binding(self, root: Path):
        catalog = SimpleNamespace(
            maps=(SimpleNamespace(map_id=0, internal_name="Azeroth"),)
        )
        pack = SimpleNamespace(
            nav_root=root / "pack",
            catalog=catalog,
            manifest={
                "pack_id": "wow.tbc.test.pack",
                "content_sha256": "a" * 64,
            },
        )
        return SimpleNamespace(profile_id="worldpack-runtime:test", pack=pack)

    def test_launch_uses_verified_pack_and_no_client_data_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            viewer = root / "MapViewer.exe"
            viewer.write_bytes(b"candidate")
            launch = build_world_pack_viewer_launch(
                self._binding(root),
                viewer_executable=viewer,
                map_id=0,
                world_x=1843.55,
                world_y=1589.97,
                world_z=93.68,
                live_state_path=root / "live-state.txt",
            )
        self.assertEqual(launch.arguments[1], str(root / "pack"))
        self.assertEqual(launch.nav_root, root / "pack")
        self.assertEqual(launch.arguments[2], "--world-pack")
        self.assertEqual(launch.arguments[3], "--- Azeroth")
        self.assertNotIn("Data", launch.arguments)
        self.assertEqual(launch.pack_id, "wow.tbc.test.pack")

    def test_map_must_be_declared_by_verified_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            viewer = root / "MapViewer.exe"
            viewer.write_bytes(b"candidate")
            with self.assertRaisesRegex(StandaloneWorldPackError, "map"):
                build_world_pack_viewer_launch(
                    self._binding(root),
                    viewer_executable=viewer,
                    map_id=1,
                    world_x=0.0,
                    world_y=0.0,
                )

    def test_non_finite_position_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            viewer = root / "MapViewer.exe"
            viewer.write_bytes(b"candidate")
            with self.assertRaisesRegex(StandaloneWorldPackError, "finite"):
                build_world_pack_viewer_launch(
                    self._binding(root),
                    viewer_executable=viewer,
                    map_id=0,
                    world_x=float("nan"),
                    world_y=0.0,
                )


if __name__ == "__main__":
    unittest.main()
