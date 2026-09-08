"""Viewport-sized raster rendering for Control Center, independent of gameplay."""
from PIL import Image

from perfect_assassin.movement.world_map_atlas import AtlasViewport


def render_atlas_image(base: Image.Image, viewport: AtlasViewport,
                       width: int, height: int) -> Image.Image:
    """Render only the visible canvas, even at 8x; preserve overlay transparency."""
    scale = viewport.scale(canvas_width=width, canvas_height=height)
    ox, oy = viewport.origin(canvas_width=width, canvas_height=height)
    return base.transform(
        (width, height), Image.Transform.AFFINE,
        (1 / scale, 0, -ox / scale, 0, 1 / scale, -oy / scale),
        resample=Image.Resampling.BILINEAR,
        fillcolor=(0, 0, 0, 0),
    )
