"""Offline map viewport/rendering checks; no game input or Tk window."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'integrations/windows-input')]
from PIL import Image
from perfect_assassin.movement.world_map_atlas import AtlasViewport
from movement_map_rendering import render_atlas_image
import run_movement_engine_client as ui


class ResponsiveMapTests(unittest.TestCase):
    def test_whole_map_fits_and_is_centered_at_every_canvas_size(self):
        for width, height in ((1, 1), (320, 700), (700, 320), (1002, 668), (2200, 900)):
            with self.subTest(size=(width, height)):
                # Even follow near an edge must not shift the fitted whole map.
                view = AtlasViewport(1002, 668).centered_on(30, 650)
                scale = view.scale(canvas_width=width, canvas_height=height)
                ox, oy = view.origin(canvas_width=width, canvas_height=height)
                self.assertGreaterEqual(ox, -1e-9)
                self.assertGreaterEqual(oy, -1e-9)
                self.assertAlmostEqual(2 * ox + 1002 * scale, width)
                self.assertAlmostEqual(2 * oy + 668 * scale, height)

    def test_follow_near_every_edge_never_exposes_unnecessary_blank_space(self):
        for zoom in (2, 4, 8):
            for x, y in ((0, 0), (1002, 0), (0, 668), (1002, 668)):
                view = AtlasViewport(1002, 668, zoom).centered_on(x, y)
                ox, oy = view.origin(canvas_width=900, canvas_height=600)
                scale = view.scale(canvas_width=900, canvas_height=600)
                self.assertLessEqual(ox, 0)
                self.assertLessEqual(oy, 0)
                self.assertGreaterEqual(ox + 1002 * scale, 900)
                self.assertGreaterEqual(oy + 668 * scale, 600)

    def test_follow_centers_interior_at_zoom_and_after_resize(self):
        view = AtlasViewport(1002, 668, 4).centered_on(400, 350)
        for w, h in ((900, 600), (500, 700), (1800, 900)):
            screen = view.screen_from_pixel(400, 350, canvas_width=w, canvas_height=h)
            self.assertAlmostEqual(screen[0], w / 2)
            self.assertAlmostEqual(screen[1], h / 2)

    def test_world_screen_round_trip_after_pan_zoom_resize(self):
        for zoom in (1, 3, 8):
            view = AtlasViewport(1002, 668, zoom).pan_by(45, -25)
            for w, h in ((400, 750), (1800, 900)):
                for pixel in ((0, 0), (320.05, 442.14), (1002, 668)):
                    screen = view.screen_from_pixel(*pixel, canvas_width=w, canvas_height=h)
                    restored = view.pixel_from_screen(*screen, canvas_width=w, canvas_height=h)
                    for before, after in zip(pixel, restored):
                        self.assertAlmostEqual(before, after)

    def test_reverse_drag_responds_immediately_after_reaching_edge(self):
        dimensions = dict(canvas_width=900, canvas_height=600)
        edge = AtlasViewport(1002, 668, 3).pan_by(10000, 10000).constrained(**dimensions)
        self.assertEqual(edge.origin(**dimensions), (0, 0))
        moved = edge.pan_by(-10, -10)
        self.assertLess(moved.origin(**dimensions)[0], 0)

    def test_zoom_keeps_cursor_anchor_until_edge_constraint(self):
        view = AtlasViewport(1002, 668)
        dimensions = dict(canvas_width=900, canvas_height=600)
        pixel = view.pixel_from_screen(500, 340, **dimensions)
        zoomed = view.zoom_at(3, cursor_x=500, cursor_y=340, **dimensions)
        for a, b in zip(pixel, zoomed.pixel_from_screen(500, 340, **dimensions)):
            self.assertAlmostEqual(a, b)

    def test_invalid_canvas_rejected(self):
        for width in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                AtlasViewport(1002, 668).scale(canvas_width=width, canvas_height=600)

    def test_render_is_viewport_sized_even_at_maximum_zoom(self):
        base = Image.new('RGBA', (1002, 668), (20, 30, 40, 255))
        for zoom in (1, 8):
            rendered = render_atlas_image(base, AtlasViewport(1002, 668, zoom), 600, 400)
            self.assertEqual(rendered.size, (600, 400))
            self.assertEqual(rendered.getpixel((300, 200)), (20, 30, 40, 255))

    def test_render_preserves_transparent_overlay_and_centered_margins(self):
        base = Image.new('RGBA', (100, 50), (0, 0, 0, 0))
        base.paste((255, 0, 0, 255), (40, 20, 60, 30))
        rendered = render_atlas_image(base, AtlasViewport(100, 50), 200, 200)
        self.assertEqual(rendered.getpixel((100, 100)), (255, 0, 0, 255))
        self.assertEqual(rendered.getpixel((100, 10))[3], 0)
        self.assertEqual(rendered.getpixel((10, 100))[3], 0)

    def test_image_and_marker_share_the_same_transform(self):
        base = Image.new('RGBA', (100, 100))
        base.paste((255, 0, 0, 255), (28, 38, 33, 43))
        view = AtlasViewport(100, 100, 3).centered_on(30, 40)
        rendered = render_atlas_image(base, view, 300, 200)
        x, y = view.screen_from_pixel(30, 40, canvas_width=300, canvas_height=200)
        self.assertEqual(rendered.getpixel((int(x), int(y))), (255, 0, 0, 255))

    def client(self):
        client = object.__new__(ui.MovementEngineClient)
        client.root = Mock()
        client.canvas_resize_job = None
        client.last_snapshot = None
        client.follow_predator = Mock()
        client.atlas_geometry = SimpleNamespace(pixel_width=1002, pixel_height=668)
        client.atlas_viewport = AtlasViewport(1002, 668, 4).pan_by(50, 50)
        client.zoom_text = Mock()
        client._draw_snapshot = Mock()
        return client

    def test_whole_map_disables_follow_so_refresh_cannot_undo_reset(self):
        client = self.client()
        client._reset_atlas_view()
        client.follow_predator.set.assert_called_once_with(False)
        self.assertEqual(client.atlas_viewport, AtlasViewport(1002, 668))
        client._draw_snapshot.assert_called_once_with(None)

    def test_resize_events_coalesce_without_live_process_or_new_polling_loop(self):
        client = self.client()
        client.root.after.return_value = 'resize-job'
        for _ in range(100):
            client._canvas_resized(None)
        client.root.after.assert_called_once_with(40, client._redraw_resized_canvas)
        client._redraw_resized_canvas()
        self.assertIsNone(client.canvas_resize_job)
        client._draw_snapshot.assert_called_once_with(None)

    def test_raster_cache_reuses_static_view_and_retains_only_one_size(self):
        client = self.client()
        cache = {}
        base = Image.new('RGBA', (1002, 668))
        with patch.object(ui.ImageTk, 'PhotoImage') as photo:
            first = client._atlas_photo(base, cache, 600, 400)
            self.assertIs(client._atlas_photo(base, cache, 600, 400), first)
            self.assertEqual(photo.call_count, 1)
            for width in (650, 700, 750):
                client._atlas_photo(base, cache, width, 400)
                self.assertEqual(len(cache), 1)
            self.assertEqual(photo.call_count, 4)


if __name__ == '__main__':
    unittest.main()
