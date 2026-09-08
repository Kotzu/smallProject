from __future__ import annotations

from dataclasses import dataclass
from math import atan2, hypot, isfinite, pi


# A first displacement chord is only trusted when it is close to the planned
# tangent.  The old 1.10 rad window accepted a diagonal wall slide as "aligned"
# and let W continue along the wrong side of a narrow interior.
INITIAL_FORWARD_DIRECTION_TOLERANCE_RAD = 0.50
INITIAL_FORWARD_DIRECTION_MAX_CROSS_TRACK_WORLD = 1.75
INITIAL_FORWARD_DIRECTION_MIN_DISPLACEMENT_WORLD = 0.75


@dataclass(slots=True)
class DisplacementHeadingEstimator:
    """Rejects quantized pose jitter until displacement proves a useful yaw."""

    minimum_displacement_world: float = INITIAL_FORWARD_DIRECTION_MIN_DISPLACEMENT_WORLD
    _anchor_x: float | None = None
    _anchor_y: float | None = None
    _last_displacement_world: float = 0.0

    def __post_init__(self) -> None:
        if not isfinite(self.minimum_displacement_world) or not 0.5 <= self.minimum_displacement_world <= 5:
            raise ValueError("heading displacement threshold is invalid")

    def reset(self, *, x: float, y: float) -> None:
        if not isfinite(x) or not isfinite(y):
            raise ValueError("heading anchor is invalid")
        self._anchor_x = x
        self._anchor_y = y
        self._last_displacement_world = 0.0

    @property
    def last_displacement_world(self) -> float:
        """Distance of the last chord that produced a heading."""

        return self._last_displacement_world

    def observe(self, *, x: float, y: float) -> float | None:
        if not isfinite(x) or not isfinite(y):
            raise ValueError("heading observation is invalid")
        if self._anchor_x is None or self._anchor_y is None:
            self.reset(x=x, y=y)
            return None
        dx, dy = x - self._anchor_x, y - self._anchor_y
        displacement = hypot(dx, dy)
        if displacement < self.minimum_displacement_world:
            return None
        self._anchor_x, self._anchor_y = x, y
        self._last_displacement_world = displacement
        return atan2(dy, dx)


def assess_initial_forward_direction(
    *,
    expected_heading_rad: float | None,
    observed_heading_rad: float | None,
    displacement_world: float,
    physical_motion_continuous: bool,
    forward_requested: bool,
    cross_track_error_world: float,
    minimum_displacement_world: float = INITIAL_FORWARD_DIRECTION_MIN_DISPLACEMENT_WORLD,
    maximum_error_rad: float = INITIAL_FORWARD_DIRECTION_TOLERANCE_RAD,
    maximum_cross_track_world: float = (
        INITIAL_FORWARD_DIRECTION_MAX_CROSS_TRACK_WORLD
    ),
) -> tuple[str, float | None]:
    """Check one first forward chord against the current corridor tangent.

    The legacy client can retain a camera yaw that is different from the
    character's forward vector after a reset.  A short, physically observed
    forward chord is useful evidence for detecting that mismatch, but only
    while the actor is moving continuously and remains near the corridor.  A
    chord produced while sliding along a wall is therefore left unresolved.
    The result is a proposal for the caller; it grants no input authority.
    """

    values = (
        expected_heading_rad,
        observed_heading_rad,
        displacement_world,
        cross_track_error_world,
        minimum_displacement_world,
        maximum_error_rad,
        maximum_cross_track_world,
    )
    if any(value is not None and not isfinite(value) for value in values):
        raise ValueError("initial forward direction evidence is invalid")
    if (
        not 0.5 <= minimum_displacement_world <= 5.0
        or not 0.20 <= maximum_error_rad <= pi
        or not 0.25 <= maximum_cross_track_world <= 6.0
        or displacement_world < 0.0
        or cross_track_error_world < 0.0
    ):
        raise ValueError("initial forward direction bounds are invalid")
    if (
        expected_heading_rad is None
        or observed_heading_rad is None
        or not forward_requested
        or not physical_motion_continuous
        or displacement_world < minimum_displacement_world
    ):
        return "WAIT", None
    error = _wrap_angle(expected_heading_rad - observed_heading_rad)
    if abs(error) <= maximum_error_rad:
        return "ALIGNED", error
    if cross_track_error_world > maximum_cross_track_world:
        return "UNSAFE", error
    return "REALIGN", error


def _wrap_angle(value: float) -> float:
    while value > pi:
        value -= 2.0 * pi
    while value < -pi:
        value += 2.0 * pi
    return value


@dataclass(slots=True)
class VisibleHeadingObserver:
    """Complement mouse-yaw prediction with the visible minimap arrow.

    The TBC arrow is only a few pixels wide, so its PCA orientation jitters by
    several degrees even when the actor is still. Using that raw angle as the
    servo state makes a smooth 120 Hz actuator change speed every video frame.
    Prediction supplies the high-rate motion; the visible arrow closes drift
    with a bounded correction and remains the absolute source of truth.
    """

    # The legacy minimap marker is an absolute but very coarse PCA axis.  It is
    # useful for closing long-term drift, but must not become the high-rate
    # steering state: a one-pixel change otherwise looks like angular momentum
    # and makes the RMB servo hunt left/right on a straight corridor.
    correction_gain: float = 0.70
    maximum_correction_rad: float = 0.25
    # While W is producing unobstructed, corridor-consistent displacement, the
    # resulting chord is a substantially better observation of body yaw than
    # the tiny minimap glyph.  The runtime decides when that evidence is safe
    # (continuous motion, close to the corridor, no collision clock); this
    # class only performs a bounded complementary correction.
    displacement_correction_gain: float = 0.85
    maximum_displacement_correction_rad: float = 0.40
    maximum_displacement_innovation_rad: float = 0.65
    displacement_visible_correction_gain: float = 0.15
    maximum_displacement_visible_correction_rad: float = 0.06

    def __post_init__(self) -> None:
        if (
            not isfinite(self.correction_gain)
            or not 0.05 <= self.correction_gain <= 1.0
        ):
            raise ValueError("visible heading correction gain is invalid")
        if (
            not isfinite(self.maximum_correction_rad)
            or not 0.02 <= self.maximum_correction_rad <= 0.50
        ):
            raise ValueError("visible heading correction bound is invalid")
        if (
            not isfinite(self.displacement_correction_gain)
            or not 0.05 <= self.displacement_correction_gain <= 1.0
        ):
            raise ValueError("displacement heading correction gain is invalid")
        if (
            not isfinite(self.maximum_displacement_correction_rad)
            or not 0.05 <= self.maximum_displacement_correction_rad <= 0.75
        ):
            raise ValueError("displacement heading correction bound is invalid")
        if (
            not isfinite(self.maximum_displacement_innovation_rad)
            or not 0.20 <= self.maximum_displacement_innovation_rad <= 1.20
        ):
            raise ValueError("displacement heading innovation bound is invalid")
        if (
            not isfinite(self.displacement_visible_correction_gain)
            or not 0.05 <= self.displacement_visible_correction_gain <= 0.50
        ):
            raise ValueError("displacement-visible correction gain is invalid")
        if (
            not isfinite(self.maximum_displacement_visible_correction_rad)
            or not 0.02
            <= self.maximum_displacement_visible_correction_rad
            <= 0.25
        ):
            raise ValueError("displacement-visible correction bound is invalid")

    @staticmethod
    def _wrap(value: float) -> float:
        while value > pi:
            value -= 2 * pi
        while value < -pi:
            value += 2 * pi
        return value

    def observe(
        self,
        *,
        predicted_heading_rad: float | None,
        visible_heading_rad: float | None,
        displacement_heading_rad: float | None = None,
    ) -> tuple[float | None, str]:
        values = (
            predicted_heading_rad,
            visible_heading_rad,
            displacement_heading_rad,
        )
        if any(value is not None and not isfinite(value) for value in values):
            raise ValueError("heading observation is not finite")
        if visible_heading_rad is not None:
            visible = self._wrap(visible_heading_rad)
            if predicted_heading_rad is None:
                return visible, "VISIBLE_CLIENT_HEADING_INITIAL"
            predicted = self._wrap(predicted_heading_rad)
            displacement_fused = False
            if displacement_heading_rad is not None:
                displacement = self._wrap(displacement_heading_rad)
                displacement_innovation = self._wrap(displacement - predicted)
                if (
                    abs(displacement_innovation)
                    <= self.maximum_displacement_innovation_rad
                ):
                    displacement_correction = max(
                        -self.maximum_displacement_correction_rad,
                        min(
                            self.maximum_displacement_correction_rad,
                            displacement_innovation
                            * self.displacement_correction_gain,
                        ),
                    )
                    predicted = self._wrap(
                        predicted + displacement_correction
                    )
                    displacement_fused = True
            # The tiny minimap marker is measured as a principal axis.  On
            # adjacent frames PCA can therefore return the same axis with its
            # direction reversed, producing a physically impossible ~180°
            # jump.  Mouse-integrated yaw is continuous, so select the end of
            # the visible axis nearest that prediction before applying the
            # ordinary bounded correction.
            direct_innovation = self._wrap(visible - predicted)
            flipped_visible = self._wrap(visible + pi)
            flipped_innovation = self._wrap(flipped_visible - predicted)
            axial_flip_corrected = (
                abs(flipped_innovation) < abs(direct_innovation)
            )
            innovation = (
                flipped_innovation if axial_flip_corrected else direct_innovation
            )
            visible_gain = (
                self.displacement_visible_correction_gain
                if displacement_fused
                else self.correction_gain
            )
            visible_bound = (
                self.maximum_displacement_visible_correction_rad
                if displacement_fused
                else self.maximum_correction_rad
            )
            correction = max(
                -visible_bound,
                min(
                    visible_bound,
                    innovation * visible_gain,
                ),
            )
            return (
                self._wrap(predicted + correction),
                (
                    "DISPLACEMENT_VISIBLE_HEADING_AXIAL_FLIP_FUSED"
                    if displacement_fused and axial_flip_corrected
                    else (
                        "DISPLACEMENT_VISIBLE_HEADING_FUSED"
                        if displacement_fused
                        else (
                            "VISIBLE_CLIENT_HEADING_AXIAL_FLIP_FUSED"
                            if axial_flip_corrected
                            else "VISIBLE_CLIENT_HEADING_FUSED"
                        )
                    )
                ),
            )
        return select_heading_observation(
            predicted_heading_rad=predicted_heading_rad,
            api_heading_rad=None,
            displacement_heading_rad=displacement_heading_rad,
        )


def select_heading_observation(
    *,
    predicted_heading_rad: float | None,
    api_heading_rad: float | None,
    displacement_heading_rad: float | None,
) -> tuple[float | None, str]:
    """Fuse heading without mistaking collision sliding for facing.

    A public client API is authoritative when one exists.  On legacy clients,
    one displacement chord may establish the initial yaw.  Once yaw exists it
    is owned by mouse integration; later displacement is diagnostic only
    because a character pressed against a WMO can slide sideways while still
    facing the wall.
    """

    values = (
        predicted_heading_rad,
        api_heading_rad,
        displacement_heading_rad,
    )
    if any(value is not None and not isfinite(value) for value in values):
        raise ValueError("heading observation is not finite")

    def wrapped(value: float) -> float:
        while value > pi:
            value -= 2 * pi
        while value < -pi:
            value += 2 * pi
        return value

    if api_heading_rad is not None:
        return wrapped(api_heading_rad), "VISIBLE_ADDON_API"
    if predicted_heading_rad is None:
        if displacement_heading_rad is None:
            return None, "UNAVAILABLE"
        return (
            wrapped(displacement_heading_rad),
            "DISPLACEMENT_INITIAL_CALIBRATION",
        )
    return (
        wrapped(predicted_heading_rad),
        "MOUSE_INTEGRATED_AFTER_DISPLACEMENT_CALIBRATION",
    )
