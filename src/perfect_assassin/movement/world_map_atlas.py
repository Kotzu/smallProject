from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .zone_transform import ZoneMapTransform


@dataclass(frozen=True, slots=True)
class WorldMapAtlasGeometry:
    """Pure world/pixel transform for one exact client world-map atlas."""

    zone: ZoneMapTransform
    pixel_width: int
    pixel_height: int

    def __post_init__(self) -> None:
        if type(self.pixel_width) is not int or type(self.pixel_height) is not int:
            raise ValueError("world-map atlas dimensions must be integers")
        if self.pixel_width <= 0 or self.pixel_height <= 0:
            raise ValueError("world-map atlas dimensions must be positive")

    def pixel_from_world(self, world_x: float, world_y: float) -> tuple[float, float]:
        normalized_x, normalized_y = self.zone.normalized_from_world(world_x, world_y)
        return normalized_x * self.pixel_width, normalized_y * self.pixel_height

    def world_from_pixel(self, pixel_x: float, pixel_y: float) -> tuple[float, float]:
        if not all(isfinite(value) for value in (pixel_x, pixel_y)):
            raise ValueError("world-map atlas pixel must be finite")
        if not 0.0 <= pixel_x <= self.pixel_width or not 0.0 <= pixel_y <= self.pixel_height:
            raise ValueError("pixel is outside the world-map atlas")
        return self.zone.world_from_normalized(
            pixel_x / self.pixel_width, pixel_y / self.pixel_height
        )


@dataclass(frozen=True, slots=True)
class AtlasViewport:
    """Fit-relative UI transform; pan is in atlas pixels, never world coordinates."""

    image_width: int
    image_height: int
    zoom: int = 1
    pan_x: float = 0.0
    pan_y: float = 0.0

    def __post_init__(self) -> None:
        if (
            type(self.image_width) is not int
            or type(self.image_height) is not int
            or type(self.zoom) is not int
            or self.image_width <= 0
            or self.image_height <= 0
            or not 1 <= self.zoom <= 8
            or not all(isfinite(value) for value in (self.pan_x, self.pan_y))
        ):
            raise ValueError("atlas viewport geometry is invalid")

    def scale(self, *, canvas_width: float, canvas_height: float) -> float:
        if not all(isfinite(value) and value > 0 for value in (canvas_width, canvas_height)):
            raise ValueError("atlas canvas dimensions are invalid")
        return min(canvas_width / self.image_width, canvas_height / self.image_height) * self.zoom

    def origin(self, *, canvas_width: float, canvas_height: float) -> tuple[float, float]:
        scale = self.scale(canvas_width=canvas_width, canvas_height=canvas_height)

        def bounded_origin(canvas: float, image: float, pan: float) -> float:
            extent = image * scale
            if extent <= canvas:
                return (canvas - extent) / 2.0
            return max(canvas - extent, min(0.0, (canvas - extent) / 2.0 + pan * scale))

        return (
            bounded_origin(canvas_width, self.image_width, self.pan_x),
            bounded_origin(canvas_height, self.image_height, self.pan_y),
        )

    def screen_from_pixel(
        self, pixel_x: float, pixel_y: float, *, canvas_width: float, canvas_height: float,
    ) -> tuple[float, float]:
        origin_x, origin_y = self.origin(
            canvas_width=canvas_width, canvas_height=canvas_height
        )
        scale = self.scale(canvas_width=canvas_width, canvas_height=canvas_height)
        return origin_x + pixel_x * scale, origin_y + pixel_y * scale

    def pixel_from_screen(
        self, screen_x: float, screen_y: float, *, canvas_width: float, canvas_height: float,
    ) -> tuple[float, float]:
        origin_x, origin_y = self.origin(
            canvas_width=canvas_width, canvas_height=canvas_height
        )
        scale = self.scale(canvas_width=canvas_width, canvas_height=canvas_height)
        return (screen_x - origin_x) / scale, (screen_y - origin_y) / scale

    def zoom_at(
        self, target_zoom: int, *, cursor_x: float, cursor_y: float,
        canvas_width: float, canvas_height: float,
    ) -> "AtlasViewport":
        if type(target_zoom) is not int or not 1 <= target_zoom <= 8:
            raise ValueError("atlas zoom is outside [1, 8]")
        pixel_x, pixel_y = self.pixel_from_screen(
            cursor_x, cursor_y,
            canvas_width=canvas_width, canvas_height=canvas_height,
        )
        scale = self.scale(canvas_width=canvas_width, canvas_height=canvas_height) * target_zoom / self.zoom
        return AtlasViewport(
            self.image_width, self.image_height, target_zoom,
            (cursor_x - canvas_width / 2.0) / scale + self.image_width / 2.0 - pixel_x,
            (cursor_y - canvas_height / 2.0) / scale + self.image_height / 2.0 - pixel_y,
        )

    def centered_on(self, pixel_x: float, pixel_y: float) -> "AtlasViewport":
        return AtlasViewport(self.image_width, self.image_height, self.zoom,
                             self.image_width / 2.0 - pixel_x,
                             self.image_height / 2.0 - pixel_y)

    def constrained(self, *, canvas_width: float, canvas_height: float) -> "AtlasViewport":
        """Remove invisible overscroll so reversing a drag responds immediately."""
        scale = self.scale(canvas_width=canvas_width, canvas_height=canvas_height)
        ox, oy = self.origin(canvas_width=canvas_width, canvas_height=canvas_height)
        return AtlasViewport(
            self.image_width, self.image_height, self.zoom,
            (ox - (canvas_width - self.image_width * scale) / 2.0) / scale,
            (oy - (canvas_height - self.image_height * scale) / 2.0) / scale,
        )

    def pan_by(self, delta_x: float, delta_y: float) -> "AtlasViewport":
        if not all(isfinite(value) for value in (delta_x, delta_y)):
            raise ValueError("atlas pan delta is invalid")
        return AtlasViewport(
            self.image_width, self.image_height, self.zoom,
            self.pan_x + delta_x, self.pan_y + delta_y,
        )
