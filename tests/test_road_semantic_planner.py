from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from perfect_assassin.adapter.adt_road import (
    AdtRoadSemantic,
    ROAD_SIDECAR_DIMENSION,
)
from perfect_assassin.movement.road_semantic_planner import (
    ClientRoadSemanticPlanner,
    RoadSemanticPlanError,
    RoadWorldPoint,
)


class ClientRoadSemanticPlannerTests(unittest.TestCase):
    def make_sidecar(self, root: Path) -> None:
        affinity = bytearray(ROAD_SIDECAR_DIMENSION ** 2)
        # An L-shaped synthetic road at the planner's native 8-pixel scale.
        for coarse_column in range(20, 81):
            for row in range(20 * 8, 21 * 8):
                for column in range(coarse_column * 8, (coarse_column + 1) * 8):
                    affinity[row * ROAD_SIDECAR_DIMENSION + column] = 255
        for coarse_row in range(20, 81):
            for row in range(coarse_row * 8, (coarse_row + 1) * 8):
                for column in range(80 * 8, 81 * 8):
                    affinity[row * ROAD_SIDECAR_DIMENSION + column] = 255
        semantic = AdtRoadSemantic(
            29, 28, ROAD_SIDECAR_DIMENSION, ROAD_SIDECAR_DIMENSION,
            bytes(affinity), ("Tileset\\FixtureRoad.blp",),
        )
        (root / "Azeroth_29_28.road").write_bytes(semantic.to_bytes())

    def test_world_grid_round_trip_preserves_game_axes(self) -> None:
        planner = ClientRoadSemanticPlanner(sidecar_root=Path("unused"))
        point = RoadWorldPoint(1843.55, 1589.97)
        restored = planner.cell_to_world(planner.world_to_cell(point))
        self.assertLess(abs(restored.x - point.x), planner.cell_world)
        self.assertLess(abs(restored.y - point.y), planner.cell_world)

    def test_generated_route_prefers_client_road_cells(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_sidecar(root)
            planner = ClientRoadSemanticPlanner(sidecar_root=root)
            start = planner.cell_to_world((28 * 128 + 20, 29 * 128 + 20))
            stop = planner.cell_to_world((28 * 128 + 80, 29 * 128 + 80))
            route = planner.plan(
                start_x=start.x, start_y=start.y,
                destination_x=stop.x, destination_y=stop.y,
            )
        self.assertEqual(route.offroad_bridge_cell_count, 0)
        self.assertGreater(route.road_cell_count, 100)
        self.assertEqual(route.source, "client_adt_texture_semantics")
        self.assertFalse(route.execution_authority)
        self.assertEqual(route.waypoints[0], route.road_entry)
        self.assertEqual(route.waypoints[-1], route.road_exit)

    def test_missing_sidecars_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            planner = ClientRoadSemanticPlanner(sidecar_root=Path(directory))
            with self.assertRaisesRegex(RoadSemanticPlanError, "sidecars"):
                planner.plan(
                    start_x=1, start_y=2, destination_x=3, destination_y=4
                )

    def test_generated_variants_share_client_atlas_but_do_not_force_the_road(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_sidecar(root)
            planner = ClientRoadSemanticPlanner(sidecar_root=root)
            start = planner.cell_to_world((28 * 128 + 20, 29 * 128 + 20))
            stop = planner.cell_to_world((28 * 128 + 80, 29 * 128 + 80))
            variants = {
                route.profile_id: route
                for route in planner.plan_variants(
                    start_x=start.x, start_y=start.y,
                    destination_x=stop.x, destination_y=stop.y,
                )
            }

        self.assertEqual(set(variants), {"road_backbone", "balanced", "shortcut"})
        self.assertEqual(variants["road_backbone"].offroad_bridge_cell_count, 0)
        self.assertGreater(variants["shortcut"].offroad_bridge_cell_count, 0)
        self.assertLess(
            variants["shortcut"].path_cost,
            variants["road_backbone"].path_cost,
        )

    def test_route_variants_share_one_loaded_and_dilated_atlas_grid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_sidecar(root)
            planner = ClientRoadSemanticPlanner(sidecar_root=root)
            start = planner.cell_to_world((28 * 128 + 20, 29 * 128 + 20))
            stop = planner.cell_to_world((28 * 128 + 80, 29 * 128 + 80))
            with (
                patch.object(
                    planner, "_load_cells", wraps=planner._load_cells,
                ) as load_cells,
                patch.object(
                    planner, "_near_road_cells", wraps=planner._near_road_cells,
                ) as near_road_cells,
            ):
                planner.plan_variants(
                    start_x=start.x,
                    start_y=start.y,
                    destination_x=stop.x,
                    destination_y=stop.y,
                )
                planner.plan(
                    start_x=stop.x,
                    start_y=stop.y,
                    destination_x=start.x,
                    destination_y=start.y,
                )

        load_cells.assert_called_once_with()
        near_road_cells.assert_called_once()

    def test_sparse_corner_touch_is_not_promoted_to_a_road_cell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            affinity = bytearray(ROAD_SIDECAR_DIMENSION ** 2)
            # Eight fully opaque pixels are only one edge of an 8x8 cell.
            # The old any-pixel reduction incorrectly promoted its centre.
            for row in range(8):
                affinity[row * ROAD_SIDECAR_DIMENSION] = 255
            # A neighbouring fully covered cell keeps the fixture valid.
            for row in range(8):
                for column in range(8, 16):
                    affinity[row * ROAD_SIDECAR_DIMENSION + column] = 255
            (root / "Azeroth_29_28.road").write_bytes(AdtRoadSemantic(
                29,
                28,
                ROAD_SIDECAR_DIMENSION,
                ROAD_SIDECAR_DIMENSION,
                bytes(affinity),
                ("Tileset\\FixtureRoad.blp",),
            ).to_bytes())
            planner = ClientRoadSemanticPlanner(sidecar_root=root)

            road_cells, _bounds, anchors = planner._load_cells()

        sparse = (28 * 128, 29 * 128)
        covered = (28 * 128, 29 * 128 + 1)
        self.assertNotIn(sparse, road_cells)
        self.assertNotIn(sparse, anchors)
        self.assertIn(covered, road_cells)
        self.assertIn(covered, anchors)

    def test_road_anchor_tracks_affinity_centroid_not_coarse_cell_center(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            affinity = bytearray(ROAD_SIDECAR_DIMENSION ** 2)
            for row in range(8):
                for column in range(4, 8):
                    affinity[row * ROAD_SIDECAR_DIMENSION + column] = 255
            (root / "Azeroth_29_28.road").write_bytes(AdtRoadSemantic(
                29,
                28,
                ROAD_SIDECAR_DIMENSION,
                ROAD_SIDECAR_DIMENSION,
                bytes(affinity),
                ("Tileset\\FixtureRoad.blp",),
            ).to_bytes())
            planner = ClientRoadSemanticPlanner(sidecar_root=root)

            _road_cells, _bounds, anchors = planner._load_cells()

        cell = (28 * 128, 29 * 128)
        coarse_center = planner.cell_to_world(cell)
        self.assertIn(cell, anchors)
        self.assertLess(anchors[cell].y, coarse_center.y)
        self.assertLess(
            abs(anchors[cell].y - coarse_center.y),
            planner.cell_world,
        )


if __name__ == "__main__":
    unittest.main()
