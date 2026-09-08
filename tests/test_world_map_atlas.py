import unittest

from perfect_assassin.movement.world_map_atlas import AtlasViewport, WorldMapAtlasGeometry
from perfect_assassin.movement.zone_transform import tbc243_zone_transform


class WorldMapAtlasGeometryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.atlas = WorldMapAtlasGeometry(tbc243_zone_transform(2, 25), 1002, 668)

    def test_world_pixel_round_trip(self) -> None:
        pixel = self.atlas.pixel_from_world(1843.55, 1589.97)
        world = self.atlas.world_from_pixel(*pixel)
        self.assertAlmostEqual(world[0], 1843.55)
        self.assertAlmostEqual(world[1], 1589.97)

    def test_reviewed_game_anchors_are_not_axis_swapped(self) -> None:
        deathknell = self.atlas.pixel_from_world(1843.55, 1589.97)
        brill = self.atlas.pixel_from_world(2259.25, 290.43)
        self.assertAlmostEqual(deathknell[0], 320.0553289131475)
        self.assertAlmostEqual(deathknell[1], 442.14390634789373)
        self.assertAlmostEqual(brill[0], 608.2188952038732)
        self.assertAlmostEqual(brill[1], 349.9654443135765)
        self.assertGreater(brill[0], deathknell[0])
        self.assertLess(brill[1], deathknell[1])

    def test_zone_corners_match_atlas_corners(self) -> None:
        zone = tbc243_zone_transform(2, 25)
        self.assertEqual(self.atlas.world_from_pixel(0, 0), (zone.loc_top, zone.loc_left))
        self.assertEqual(
            self.atlas.world_from_pixel(1002, 668), (zone.loc_bottom, zone.loc_right)
        )

    def test_outside_pixel_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside"):
            self.atlas.world_from_pixel(-1, 10)

    def test_zoom_keeps_the_same_atlas_coordinate_under_cursor(self) -> None:
        viewport = AtlasViewport(1002, 668)
        before = viewport.pixel_from_screen(
            600, 400, canvas_width=1100, canvas_height=720,
        )
        zoomed = viewport.zoom_at(
            4, cursor_x=600, cursor_y=400,
            canvas_width=1100, canvas_height=720,
        )
        after = zoomed.pixel_from_screen(
            600, 400, canvas_width=1100, canvas_height=720,
        )
        self.assertAlmostEqual(after[0], before[0])
        self.assertAlmostEqual(after[1], before[1])

    def test_pan_changes_view_only_not_world_pixel_transform(self) -> None:
        viewport = AtlasViewport(1002, 668, zoom=3).pan_by(80, -35)
        screen = viewport.screen_from_pixel(
            320.0553289131475, 442.14390634789373,
            canvas_width=1100, canvas_height=720,
        )
        restored = viewport.pixel_from_screen(
            *screen, canvas_width=1100, canvas_height=720,
        )
        self.assertAlmostEqual(restored[0], 320.0553289131475)
        self.assertAlmostEqual(restored[1], 442.14390634789373)


if __name__ == "__main__":
    unittest.main()
