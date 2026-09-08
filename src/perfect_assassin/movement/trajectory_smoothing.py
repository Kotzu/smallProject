from __future__ import annotations

from dataclasses import dataclass
from math import acos, ceil, hypot, isfinite, tan
from typing import Callable

from .client_navmesh import NavCorridor, NavPoint


SegmentValidator = Callable[[NavPoint, NavPoint], bool]


@dataclass(frozen=True, slots=True)
class SmoothedTrajectory:
    """A curvature-bounded path whose every chord was accepted by navmesh."""

    points: tuple[NavPoint, ...]
    rounded_corner_count: int
    rejected_corner_count: int
    validation_count: int

    def __post_init__(self) -> None:
        if (
            len(self.points) < 2
            or self.rounded_corner_count < 0
            or self.rejected_corner_count < 0
            or self.validation_count < 0
        ):
            raise ValueError("smoothed trajectory is invalid")


def smooth_navmesh_corridor(
    corridor: NavCorridor,
    *,
    validate_segment: SegmentValidator,
    minimum_turn_radius_world: float = 2.25,
    sample_spacing_world: float = 0.60,
    maximum_turn_rad: float = 2.60,
) -> SmoothedTrajectory:
    """Round funnel corners without inventing walkable space.

    The navmesh/funnel remains the global authority.  Each quadratic fillet is
    attempted from largest to smallest and retained only when every sampled
    chord is independently accepted by the caller's active navmesh query.
    Failed corners remain unchanged; there is no geometric shortcut fallback.
    """

    values = (
        minimum_turn_radius_world,
        sample_spacing_world,
        maximum_turn_rad,
    )
    if (
        any(not isfinite(value) for value in values)
        or not 0.75 <= minimum_turn_radius_world <= 12.0
        or not 0.20 <= sample_spacing_world <= 2.0
        or not 1.0 <= maximum_turn_rad < 3.141593
        or not callable(validate_segment)
    ):
        raise ValueError("trajectory smoothing configuration is invalid")

    source = _deduplicate(corridor.guidance_points())
    if len(source) < 3:
        return SmoothedTrajectory(source, 0, 0, 0)

    output: list[NavPoint] = [source[0]]
    rounded = 0
    rejected = 0
    validations = 0
    for index in range(1, len(source) - 1):
        previous, corner, following = source[index - 1:index + 2]
        incoming_length = previous.distance_2d(corner)
        outgoing_length = corner.distance_2d(following)
        if incoming_length <= 0.05 or outgoing_length <= 0.05:
            continue
        incoming = (
            (corner.x - previous.x) / incoming_length,
            (corner.y - previous.y) / incoming_length,
        )
        outgoing = (
            (following.x - corner.x) / outgoing_length,
            (following.y - corner.y) / outgoing_length,
        )
        turn = acos(max(-1.0, min(1.0, incoming[0] * outgoing[0] + incoming[1] * outgoing[1])))
        if turn <= 0.12 or turn >= maximum_turn_rad:
            output.append(corner)
            continue

        desired_trim = minimum_turn_radius_world * tan(turn * 0.5)
        trim = min(desired_trim, incoming_length * 0.38, outgoing_length * 0.38)
        accepted: tuple[NavPoint, ...] | None = None
        while trim >= 0.35:
            start = NavPoint(
                corner.x - incoming[0] * trim,
                corner.y - incoming[1] * trim,
                corner.z,
            )
            stop = NavPoint(
                corner.x + outgoing[0] * trim,
                corner.y + outgoing[1] * trim,
                corner.z,
            )
            samples = _quadratic_samples(
                start,
                corner,
                stop,
                spacing_world=sample_spacing_world,
            )
            candidate = (output[-1], *samples)
            valid = True
            for left, right in zip(candidate, candidate[1:]):
                validations += 1
                if not validate_segment(left, right):
                    valid = False
                    break
            if valid:
                accepted = samples
                break
            trim *= 0.60

        if accepted is None:
            output.append(corner)
            rejected += 1
        else:
            output.extend(accepted)
            rounded += 1

    final = source[-1]
    if output[-1].distance_2d(final) > 0.01:
        validations += 1
        if not validate_segment(output[-1], final):
            # Fail closed to the original Detour/funnel path. Partial smoothing
            # must never make the terminal leg invalid.
            return SmoothedTrajectory(source, 0, rounded + rejected, validations)
        output.append(final)
    return SmoothedTrajectory(_deduplicate(tuple(output)), rounded, rejected, validations)


def _quadratic_samples(
    start: NavPoint,
    control: NavPoint,
    stop: NavPoint,
    *,
    spacing_world: float,
) -> tuple[NavPoint, ...]:
    approximate_length = start.distance_2d(control) + control.distance_2d(stop)
    count = max(2, int(ceil(approximate_length / spacing_world)))
    points: list[NavPoint] = [start]
    for index in range(1, count + 1):
        t = index / count
        inverse = 1.0 - t
        points.append(NavPoint(
            inverse * inverse * start.x + 2.0 * inverse * t * control.x + t * t * stop.x,
            inverse * inverse * start.y + 2.0 * inverse * t * control.y + t * t * stop.y,
            inverse * inverse * start.z + 2.0 * inverse * t * control.z + t * t * stop.z,
        ))
    return tuple(points)


def _deduplicate(points: tuple[NavPoint, ...]) -> tuple[NavPoint, ...]:
    result: list[NavPoint] = []
    for point in points:
        if not result or result[-1].distance_2d(point) > 0.01:
            result.append(point)
    if len(result) < 2:
        raise ValueError("trajectory requires two distinct points")
    return tuple(result)
