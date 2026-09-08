from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from perfect_assassin.movement.client_navmesh import NavPolygon


CAMERA_SCENE_MODES = frozenset({"OUTDOOR_HUNT", "WMO_NAV"})


def nearest_navmesh_physical_surfaces(
    polygons: tuple[NavPolygon, ...],
    *,
    world_x: float,
    world_y: float,
) -> frozenset[str]:
    """Return scene evidence from the corridor polygon nearest the actor."""

    if not isfinite(world_x) or not isfinite(world_y):
        raise ValueError("camera world position is invalid")
    if not polygons:
        return frozenset()
    nearest = min(
        polygons,
        key=lambda item: (
            item.centroid.x - world_x
        ) ** 2 + (item.centroid.y - world_y) ** 2,
    )
    return nearest.physical_surfaces


@dataclass(frozen=True, slots=True)
class CameraPivotIntent:
    """One idempotent camera-profile transition.

    Camera yaw is intentionally absent.  RMB facing owns yaw; this controller
    only decides when world collision has compressed the third-person camera
    enough that its pitch/distance composition must be restored.
    """

    mode: str
    camera_distance_max_factor: float
    restore_composition: bool
    zoom_out_steps: int
    pitch_delta_y: int
    reason: str

    def __post_init__(self) -> None:
        if self.mode not in CAMERA_SCENE_MODES:
            raise ValueError("camera scene mode is invalid")
        if (
            not isfinite(self.camera_distance_max_factor)
            or not 1.0 <= self.camera_distance_max_factor <= 2.0
        ):
            raise ValueError("camera distance factor is invalid")
        if type(self.restore_composition) is not bool:
            raise ValueError("camera restore flag is invalid")
        if type(self.zoom_out_steps) is not int or not 0 <= self.zoom_out_steps <= 10:
            raise ValueError("camera zoom step count is invalid")
        if (
            type(self.pitch_delta_y) is not int
            or abs(self.pitch_delta_y) > 60
            or self.pitch_delta_y % 5 != 0
        ):
            raise ValueError("camera pitch delta is invalid")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("camera transition reason is invalid")


class CameraPivotController:
    """Debounce geometry-driven camera modes and repair WMO compression once.

    A WMO transition is accepted quickly so camera collision remains useful in
    doorways.  Returning outdoors requires longer stable evidence.  This
    prevents a mixed ground/WMO polygon seam from repeatedly zooming the view.
    """

    def __init__(
        self,
        *,
        enter_wmo_after_s: float = 0.25,
        exit_wmo_after_s: float = 0.90,
        minimum_transition_interval_s: float = 1.50,
    ) -> None:
        for label, value in (
            ("enter WMO delay", enter_wmo_after_s),
            ("exit WMO delay", exit_wmo_after_s),
            ("camera transition interval", minimum_transition_interval_s),
        ):
            if not isfinite(value) or value < 0:
                raise ValueError(f"{label} is invalid")
        self._enter_wmo_after_s = enter_wmo_after_s
        self._exit_wmo_after_s = exit_wmo_after_s
        self._minimum_transition_interval_s = minimum_transition_interval_s
        self._mode: str | None = None
        self._candidate_mode: str | None = None
        self._candidate_since_s: float | None = None
        self._last_transition_s: float | None = None
        self._wmo_compression_seen = False

    @property
    def mode(self) -> str | None:
        return self._mode

    def observe(
        self,
        *,
        observed_monotonic_s: float,
        physical_surfaces: frozenset[str],
    ) -> CameraPivotIntent | None:
        if not isfinite(observed_monotonic_s) or observed_monotonic_s < 0:
            raise ValueError("camera observation time is invalid")
        if not physical_surfaces.issubset({"ground", "wmo", "doodad"}):
            raise ValueError("camera physical surfaces are invalid")

        # A polygon carrying WMO evidence is treated as interior even when its
        # walkable floor is also classified as ground.  Doodads alone do not
        # imply a ceiling and therefore must not collapse the camera profile.
        candidate = "WMO_NAV" if "wmo" in physical_surfaces else "OUTDOOR_HUNT"
        if candidate != self._candidate_mode:
            self._candidate_mode = candidate
            self._candidate_since_s = observed_monotonic_s

        if self._mode is None:
            self._mode = candidate
            self._last_transition_s = observed_monotonic_s
            self._wmo_compression_seen = candidate == "WMO_NAV"
            return self._intent(
                candidate,
                restore_composition=False,
                reason="initial_geometry_profile",
            )
        if candidate == self._mode:
            if candidate == "WMO_NAV":
                self._wmo_compression_seen = True
            return None

        assert self._candidate_since_s is not None
        stable_for_s = observed_monotonic_s - self._candidate_since_s
        required_s = (
            self._enter_wmo_after_s
            if candidate == "WMO_NAV"
            else self._exit_wmo_after_s
        )
        since_transition_s = (
            float("inf")
            if self._last_transition_s is None
            else observed_monotonic_s - self._last_transition_s
        )
        if stable_for_s < required_s or since_transition_s < self._minimum_transition_interval_s:
            return None

        previous = self._mode
        self._mode = candidate
        self._last_transition_s = observed_monotonic_s
        restore = candidate == "OUTDOOR_HUNT" and self._wmo_compression_seen
        if candidate == "WMO_NAV":
            self._wmo_compression_seen = True
        elif restore:
            self._wmo_compression_seen = False
        return self._intent(
            candidate,
            restore_composition=restore,
            reason=f"stable_{previous.lower()}_to_{candidate.lower()}_transition",
        )

    @staticmethod
    def _intent(
        mode: str,
        *,
        restore_composition: bool,
        reason: str,
    ) -> CameraPivotIntent:
        if mode == "WMO_NAV":
            return CameraPivotIntent(
                mode=mode,
                camera_distance_max_factor=1.35,
                restore_composition=False,
                zoom_out_steps=2,
                pitch_delta_y=15,
                reason=reason,
            )
        return CameraPivotIntent(
            mode=mode,
            camera_distance_max_factor=2.0,
            restore_composition=restore_composition,
            zoom_out_steps=5,
            pitch_delta_y=25,
            reason=reason,
        )
