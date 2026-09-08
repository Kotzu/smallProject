from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite, pi
from typing import Iterable, Literal

from perfect_assassin.movement.client_navmesh import LocalStaticAwareness
from perfect_assassin.movement.predictive_steering import SteeringIntent


EntityReaction = Literal["HOSTILE", "NEUTRAL", "FRIENDLY", "UNKNOWN"]
AvoidanceSide = Literal["LEFT", "RIGHT"]


@dataclass(frozen=True, slots=True)
class ScreenEntityObservation:
    """One visible entity cue expressed only in the client viewport.

    The movement core deliberately does not claim a world position from a
    nameplate.  Different client adapters can supply this same contract while
    the standalone tracker remains independent from a client, server and map.
    Horizontal position is in [-1, 1], with zero at the viewport centre;
    vertical position and extents are normalized to [0, 1].
    """

    observed_at_s: float
    center_x_normalized: float
    center_y_normalized: float
    width_normalized: float
    height_normalized: float
    reaction: EntityReaction
    confidence: float
    source_key: str | None = None

    def __post_init__(self) -> None:
        values = (
            self.observed_at_s,
            self.center_x_normalized,
            self.center_y_normalized,
            self.width_normalized,
            self.height_normalized,
            self.confidence,
        )
        if any(not isfinite(value) for value in values):
            raise ValueError("dynamic entity observation is non-finite")
        if not -1.0 <= self.center_x_normalized <= 1.0:
            raise ValueError("dynamic entity horizontal position is invalid")
        if not 0.0 <= self.center_y_normalized <= 1.0:
            raise ValueError("dynamic entity vertical position is invalid")
        if not 0.0 < self.width_normalized <= 1.0:
            raise ValueError("dynamic entity width is invalid")
        if not 0.0 < self.height_normalized <= 1.0:
            raise ValueError("dynamic entity height is invalid")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("dynamic entity confidence is invalid")
        if self.source_key is not None and not self.source_key:
            raise ValueError("dynamic entity source key is invalid")


@dataclass(frozen=True, slots=True)
class DynamicEntityTrack:
    """Ephemeral screen-space track; never static world geometry."""

    track_id: str
    reaction: EntityReaction
    first_observed_at_s: float
    last_observed_at_s: float
    expires_at_s: float
    center_x_normalized: float
    center_y_normalized: float
    velocity_x_normalized_per_s: float
    velocity_y_normalized_per_s: float
    width_normalized: float
    height_normalized: float
    position_uncertainty_normalized: float
    confidence: float
    observation_count: int
    source_key: str | None = None

    def __post_init__(self) -> None:
        if not self.track_id:
            raise ValueError("dynamic entity track identity is invalid")
        values = (
            self.first_observed_at_s,
            self.last_observed_at_s,
            self.expires_at_s,
            self.center_x_normalized,
            self.center_y_normalized,
            self.velocity_x_normalized_per_s,
            self.velocity_y_normalized_per_s,
            self.width_normalized,
            self.height_normalized,
            self.position_uncertainty_normalized,
            self.confidence,
        )
        if any(not isfinite(value) for value in values):
            raise ValueError("dynamic entity track is non-finite")
        if not (
            self.first_observed_at_s
            <= self.last_observed_at_s
            < self.expires_at_s
        ):
            raise ValueError("dynamic entity track chronology is invalid")
        if not -1.0 <= self.center_x_normalized <= 1.0:
            raise ValueError("dynamic entity track horizontal position is invalid")
        if not 0.0 <= self.center_y_normalized <= 1.0:
            raise ValueError("dynamic entity track vertical position is invalid")
        if not 0.0 < self.width_normalized <= 1.0:
            raise ValueError("dynamic entity track width is invalid")
        if not 0.0 < self.height_normalized <= 1.0:
            raise ValueError("dynamic entity track height is invalid")
        if not 0.0 <= self.position_uncertainty_normalized <= 1.0:
            raise ValueError("dynamic entity track uncertainty is invalid")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("dynamic entity track confidence is invalid")
        if self.observation_count < 1:
            raise ValueError("dynamic entity track observation count is invalid")

    def predict(self, *, at_s: float) -> tuple[float, float, float]:
        if not isfinite(at_s) or at_s < self.last_observed_at_s:
            raise ValueError("dynamic entity prediction time is invalid")
        elapsed = at_s - self.last_observed_at_s
        x = max(
            -1.0,
            min(
                1.0,
                self.center_x_normalized
                + self.velocity_x_normalized_per_s * elapsed,
            ),
        )
        y = max(
            0.0,
            min(
                1.0,
                self.center_y_normalized
                + self.velocity_y_normalized_per_s * elapsed,
            ),
        )
        uncertainty = min(
            1.0,
            self.position_uncertainty_normalized + elapsed * 0.08,
        )
        return x, y, uncertainty


class DynamicEntityTracker:
    """Nearest-neighbour tracker with short, non-persistent lifetime."""

    def __init__(
        self,
        *,
        ttl_s: float = 0.80,
        maximum_match_distance_normalized: float = 0.22,
        velocity_alpha: float = 0.45,
        position_alpha: float = 0.70,
    ) -> None:
        values = (
            ttl_s,
            maximum_match_distance_normalized,
            velocity_alpha,
            position_alpha,
        )
        if any(not isfinite(value) for value in values):
            raise ValueError("dynamic entity tracker configuration is non-finite")
        if not 0.20 <= ttl_s <= 3.0:
            raise ValueError("dynamic entity tracker TTL is invalid")
        if not 0.02 <= maximum_match_distance_normalized <= 0.50:
            raise ValueError("dynamic entity match distance is invalid")
        if not 0.05 <= velocity_alpha <= 1.0:
            raise ValueError("dynamic entity velocity alpha is invalid")
        if not 0.05 <= position_alpha <= 1.0:
            raise ValueError("dynamic entity position alpha is invalid")
        self.ttl_s = float(ttl_s)
        self.maximum_match_distance_normalized = float(
            maximum_match_distance_normalized
        )
        self.velocity_alpha = float(velocity_alpha)
        self.position_alpha = float(position_alpha)
        self._tracks: dict[str, DynamicEntityTrack] = {}
        self._next_track_number = 1

    def update(
        self,
        observations: Iterable[ScreenEntityObservation],
        *,
        now_s: float,
    ) -> tuple[DynamicEntityTrack, ...]:
        if not isfinite(now_s):
            raise ValueError("dynamic entity tracker time is invalid")
        items = tuple(observations)
        if any(not isinstance(item, ScreenEntityObservation) for item in items):
            raise ValueError("dynamic entity tracker observation type is invalid")
        if any(item.observed_at_s > now_s + 0.005 for item in items):
            raise ValueError("dynamic entity observation is from the future")
        self._expire(now_s)
        unmatched_tracks = set(self._tracks)
        for observation in sorted(
            items,
            key=lambda item: (
                item.source_key or "",
                item.reaction,
                item.center_x_normalized,
                item.center_y_normalized,
            ),
        ):
            track_id = self._match(observation, unmatched_tracks)
            if track_id is None:
                track = self._new_track(observation)
            else:
                unmatched_tracks.remove(track_id)
                track = self._update_track(self._tracks[track_id], observation)
            self._tracks[track.track_id] = track
        return self.active_tracks(now_s=now_s)

    def active_tracks(self, *, now_s: float) -> tuple[DynamicEntityTrack, ...]:
        if not isfinite(now_s):
            raise ValueError("dynamic entity tracker time is invalid")
        self._expire(now_s)
        return tuple(
            sorted(
                self._tracks.values(),
                key=lambda item: (
                    -item.confidence,
                    -item.observation_count,
                    item.track_id,
                ),
            )
        )

    def _expire(self, now_s: float) -> None:
        for track_id in tuple(self._tracks):
            if self._tracks[track_id].expires_at_s <= now_s:
                del self._tracks[track_id]

    def _match(
        self,
        observation: ScreenEntityObservation,
        candidate_ids: set[str],
    ) -> str | None:
        exact = [
            track_id
            for track_id in candidate_ids
            if observation.source_key is not None
            and self._tracks[track_id].source_key == observation.source_key
        ]
        if exact:
            return min(exact)
        best: tuple[float, str] | None = None
        for track_id in candidate_ids:
            track = self._tracks[track_id]
            if not self._reactions_compatible(track.reaction, observation.reaction):
                continue
            predicted_x, predicted_y, _ = track.predict(
                at_s=max(track.last_observed_at_s, observation.observed_at_s),
            )
            dx = observation.center_x_normalized - predicted_x
            dy = observation.center_y_normalized - predicted_y
            distance = (dx * dx + dy * dy) ** 0.5
            allowed = (
                self.maximum_match_distance_normalized
                + track.position_uncertainty_normalized
            )
            if distance > allowed:
                continue
            candidate = (distance, track_id)
            if best is None or candidate < best:
                best = candidate
        return None if best is None else best[1]

    @staticmethod
    def _reactions_compatible(
        left: EntityReaction, right: EntityReaction,
    ) -> bool:
        return left == right or "UNKNOWN" in {left, right}

    def _new_track(
        self, observation: ScreenEntityObservation,
    ) -> DynamicEntityTrack:
        track_id = f"dynamic-screen:{self._next_track_number}"
        self._next_track_number += 1
        return DynamicEntityTrack(
            track_id=track_id,
            reaction=observation.reaction,
            first_observed_at_s=observation.observed_at_s,
            last_observed_at_s=observation.observed_at_s,
            expires_at_s=observation.observed_at_s + self.ttl_s,
            center_x_normalized=observation.center_x_normalized,
            center_y_normalized=observation.center_y_normalized,
            velocity_x_normalized_per_s=0.0,
            velocity_y_normalized_per_s=0.0,
            width_normalized=observation.width_normalized,
            height_normalized=observation.height_normalized,
            position_uncertainty_normalized=0.04,
            confidence=observation.confidence,
            observation_count=1,
            source_key=observation.source_key,
        )

    def _update_track(
        self,
        previous: DynamicEntityTrack,
        observation: ScreenEntityObservation,
    ) -> DynamicEntityTrack:
        if observation.observed_at_s < previous.last_observed_at_s:
            raise ValueError("dynamic entity observations cannot move backward in time")
        dt_s = max(0.001, observation.observed_at_s - previous.last_observed_at_s)
        raw_vx = (
            observation.center_x_normalized - previous.center_x_normalized
        ) / dt_s
        raw_vy = (
            observation.center_y_normalized - previous.center_y_normalized
        ) / dt_s
        velocity_x = (
            previous.velocity_x_normalized_per_s * (1.0 - self.velocity_alpha)
            + raw_vx * self.velocity_alpha
        )
        velocity_y = (
            previous.velocity_y_normalized_per_s * (1.0 - self.velocity_alpha)
            + raw_vy * self.velocity_alpha
        )
        predicted_x, predicted_y, _ = previous.predict(
            at_s=observation.observed_at_s,
        )
        residual = (
            (observation.center_x_normalized - predicted_x) ** 2
            + (observation.center_y_normalized - predicted_y) ** 2
        ) ** 0.5
        alpha = self.position_alpha
        reaction = (
            observation.reaction
            if observation.reaction != "UNKNOWN"
            else previous.reaction
        )
        return DynamicEntityTrack(
            track_id=previous.track_id,
            reaction=reaction,
            first_observed_at_s=previous.first_observed_at_s,
            last_observed_at_s=observation.observed_at_s,
            expires_at_s=observation.observed_at_s + self.ttl_s,
            center_x_normalized=(
                previous.center_x_normalized * (1.0 - alpha)
                + observation.center_x_normalized * alpha
            ),
            center_y_normalized=(
                previous.center_y_normalized * (1.0 - alpha)
                + observation.center_y_normalized * alpha
            ),
            velocity_x_normalized_per_s=velocity_x,
            velocity_y_normalized_per_s=velocity_y,
            width_normalized=(
                previous.width_normalized * (1.0 - alpha)
                + observation.width_normalized * alpha
            ),
            height_normalized=(
                previous.height_normalized * (1.0 - alpha)
                + observation.height_normalized * alpha
            ),
            position_uncertainty_normalized=min(
                0.35,
                max(0.015, previous.position_uncertainty_normalized * 0.65 + residual),
            ),
            confidence=min(
                1.0,
                previous.confidence * 0.35 + observation.confidence * 0.65,
            ),
            observation_count=previous.observation_count + 1,
            source_key=observation.source_key or previous.source_key,
        )


@dataclass(frozen=True, slots=True)
class DynamicAvoidanceDecision:
    state: Literal["CLEAR", "TRACKING", "AVOID", "YIELD"]
    side: AvoidanceSide | None
    mouse_delta_bias: int
    risk: float
    track_id: str | None
    predicted_x_normalized: float | None
    predicted_y_normalized: float | None
    expires_at_s: float | None
    reason: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.risk <= 1.0:
            raise ValueError("dynamic avoidance risk is invalid")
        if not -3 <= self.mouse_delta_bias <= 3:
            raise ValueError("dynamic avoidance mouse bias is invalid")
        if self.state in {"AVOID", "YIELD"} and self.track_id is None:
            raise ValueError("dynamic avoidance action requires a track")
        if self.state == "AVOID" and self.side is None:
            raise ValueError("dynamic avoidance side is missing")
        if self.state != "AVOID" and self.mouse_delta_bias != 0:
            raise ValueError("only active dynamic avoidance can bias steering")


class DynamicCollisionAvoidance:
    """Transient collision-lane policy layered over static navmesh steering.

    It never writes navmesh, WorldPack or learned static-obstacle memory.  The
    controller merely bends an already-valid corridor-following RMB arc while
    a mature visible track occupies the future screen-space travel lane.
    """

    def __init__(
        self,
        *,
        prediction_horizon_s: float = 0.45,
        lane_half_width_normalized: float = 0.14,
        minimum_risk: float = 0.28,
        minimum_observations: int = 2,
        minimum_static_clearance_yards: float = 1.50,
        units_physically_block_movement: bool = True,
    ) -> None:
        values = (
            prediction_horizon_s,
            lane_half_width_normalized,
            minimum_risk,
            minimum_static_clearance_yards,
        )
        if any(not isfinite(value) for value in values):
            raise ValueError("dynamic avoidance configuration is non-finite")
        if not 0.10 <= prediction_horizon_s <= 1.5:
            raise ValueError("dynamic avoidance horizon is invalid")
        if not 0.05 <= lane_half_width_normalized <= 0.40:
            raise ValueError("dynamic avoidance lane width is invalid")
        if not 0.05 <= minimum_risk <= 0.95:
            raise ValueError("dynamic avoidance risk threshold is invalid")
        if not 2 <= minimum_observations <= 10:
            raise ValueError("dynamic avoidance maturity is invalid")
        if not 0.5 <= minimum_static_clearance_yards <= 5.0:
            raise ValueError("dynamic avoidance static clearance is invalid")
        if type(units_physically_block_movement) is not bool:
            raise ValueError("dynamic unit collision semantics are invalid")
        self.prediction_horizon_s = float(prediction_horizon_s)
        self.lane_half_width_normalized = float(lane_half_width_normalized)
        self.minimum_risk = float(minimum_risk)
        self.minimum_observations = int(minimum_observations)
        self.minimum_static_clearance_yards = float(
            minimum_static_clearance_yards
        )
        self.units_physically_block_movement = units_physically_block_movement
        self._active_track_id: str | None = None
        self._active_side: AvoidanceSide | None = None

    def decide(
        self,
        tracks: Iterable[DynamicEntityTrack],
        *,
        now_s: float,
        heading_rad: float | None,
        static_awareness: LocalStaticAwareness | None,
    ) -> DynamicAvoidanceDecision:
        if not isfinite(now_s):
            raise ValueError("dynamic avoidance time is invalid")
        if heading_rad is not None and not isfinite(heading_rad):
            raise ValueError("dynamic avoidance heading is invalid")
        items = tuple(tracks)
        if any(not isinstance(item, DynamicEntityTrack) for item in items):
            raise ValueError("dynamic avoidance track type is invalid")
        ranked: list[tuple[float, DynamicEntityTrack, float, float]] = []
        for track in items:
            prediction_time = min(
                track.expires_at_s - 0.001,
                now_s + self.prediction_horizon_s,
            )
            if prediction_time < track.last_observed_at_s:
                continue
            predicted_x, predicted_y, uncertainty = track.predict(
                at_s=prediction_time,
            )
            risk = self._risk(
                track,
                predicted_x=predicted_x,
                predicted_y=predicted_y,
                uncertainty=uncertainty,
            )
            ranked.append((risk, track, predicted_x, predicted_y))
        if not ranked:
            self._clear_hysteresis()
            return DynamicAvoidanceDecision(
                "CLEAR", None, 0, 0.0, None, None, None, None,
                "no_live_dynamic_entity_tracks",
            )
        if not self.units_physically_block_movement:
            risk, track, predicted_x, predicted_y = max(
                ranked,
                key=lambda item: (
                    item[0],
                    item[1].observation_count,
                    item[1].track_id,
                ),
            )
            self._clear_hysteresis()
            return DynamicAvoidanceDecision(
                "TRACKING", None, 0, risk, track.track_id,
                predicted_x, predicted_y, track.expires_at_s,
                "visible_units_do_not_physically_block_client_movement",
            )
        mature = [
            item
            for item in ranked
            if item[1].observation_count >= self.minimum_observations
        ]
        actionable = [item for item in mature if item[0] >= self.minimum_risk]
        if actionable:
            risk, track, predicted_x, predicted_y = max(
                actionable,
                key=lambda item: (
                    item[0],
                    item[1].observation_count,
                    item[1].track_id,
                ),
            )
        elif mature:
            risk, track, predicted_x, predicted_y = max(
                mature,
                key=lambda item: (
                    item[0],
                    item[1].observation_count,
                    item[1].track_id,
                ),
            )
        else:
            risk, track, predicted_x, predicted_y = max(
                ranked,
                key=lambda item: (
                    item[0],
                    item[1].observation_count,
                    item[1].track_id,
                ),
            )
            return DynamicAvoidanceDecision(
                "TRACKING", None, 0, risk, track.track_id,
                predicted_x, predicted_y, track.expires_at_s,
                "dynamic_track_not_yet_mature",
            )
        if risk < self.minimum_risk:
            if self._active_track_id != track.track_id:
                self._clear_hysteresis()
            return DynamicAvoidanceDecision(
                "TRACKING", None, 0, risk, track.track_id,
                predicted_x, predicted_y, track.expires_at_s,
                "dynamic_track_outside_collision_lane",
            )
        preferred = self._preferred_side(track, predicted_x)
        side = self._select_clear_side(
            preferred,
            heading_rad=heading_rad,
            static_awareness=static_awareness,
        )
        if side is None:
            self._active_track_id = track.track_id
            self._active_side = None
            return DynamicAvoidanceDecision(
                "YIELD", None, 0, risk, track.track_id,
                predicted_x, predicted_y, track.expires_at_s,
                "dynamic_lane_blocked_and_static_sides_unproven",
            )
        self._active_track_id = track.track_id
        self._active_side = side
        magnitude = 3 if risk >= 0.75 else 2 if risk >= 0.50 else 1
        bias = -magnitude if side == "LEFT" else magnitude
        return DynamicAvoidanceDecision(
            "AVOID", side, bias, risk, track.track_id,
            predicted_x, predicted_y, track.expires_at_s,
            "transient_dynamic_volume_avoided_inside_static_navmesh_corridor",
        )

    def apply(
        self,
        intent: SteeringIntent,
        decision: DynamicAvoidanceDecision,
        *,
        maximum_mouse_delta: int,
    ) -> SteeringIntent:
        if not isinstance(intent, SteeringIntent):
            raise ValueError("dynamic avoidance base intent is invalid")
        if type(maximum_mouse_delta) is not int or not 1 <= maximum_mouse_delta <= 16:
            raise ValueError("dynamic avoidance actuator bound is invalid")
        if decision.state == "YIELD" and intent.state == "FOLLOW":
            return replace(
                intent,
                state="DYNAMIC_YIELD",
                forward_hold_ms=0,
                mouse_delta_x=0,
                reason=decision.reason,
            )
        if decision.state != "AVOID" or intent.state != "FOLLOW":
            return intent
        mouse_delta = max(
            -maximum_mouse_delta,
            min(
                maximum_mouse_delta,
                intent.mouse_delta_x + decision.mouse_delta_bias,
            ),
        )
        # Do not let the corridor follower reverse the selected avoidance arc
        # from one frame to the next.  If the static route currently asks for
        # the opposite turn, hold a straight line until the transient volume
        # clears; the route follower may then recenter in one deliberate arc.
        # This is geometry-class behaviour, not a location-specific waypoint.
        if decision.side == "LEFT":
            mouse_delta = min(0, mouse_delta)
        else:
            mouse_delta = max(0, mouse_delta)
        return replace(
            intent,
            state="DYNAMIC_AVOID",
            mouse_delta_x=mouse_delta,
            reason=decision.reason,
        )

    def _risk(
        self,
        track: DynamicEntityTrack,
        *,
        predicted_x: float,
        predicted_y: float,
        uncertainty: float,
    ) -> float:
        half_width = (
            self.lane_half_width_normalized
            + track.width_normalized * 0.5
            + uncertainty
        )
        horizontal = max(0.0, 1.0 - abs(predicted_x) / half_width)
        depth = max(0.0, min(1.0, (predicted_y - 0.25) / 0.35))
        closing = max(
            0.0,
            min(1.0, track.velocity_y_normalized_per_s / 0.25),
        )
        maturity = min(1.0, track.observation_count / 3.0)
        risk = (
            horizontal
            * (0.65 * depth + 0.35 * closing)
            * track.confidence
            * maturity
        )
        return max(0.0, min(1.0, risk))

    def _preferred_side(
        self,
        track: DynamicEntityTrack,
        predicted_x: float,
    ) -> AvoidanceSide:
        if self._active_track_id == track.track_id and self._active_side is not None:
            return self._active_side
        if predicted_x < -0.025:
            return "RIGHT"
        if predicted_x > 0.025:
            return "LEFT"
        if track.velocity_x_normalized_per_s < -0.02:
            return "RIGHT"
        if track.velocity_x_normalized_per_s > 0.02:
            return "LEFT"
        # Deterministic tie-breaking prevents alternating left/right commands
        # while a centred entity is visually stationary.
        return "LEFT" if sum(track.track_id.encode("utf-8")) % 2 == 0 else "RIGHT"

    def _select_clear_side(
        self,
        preferred: AvoidanceSide,
        *,
        heading_rad: float | None,
        static_awareness: LocalStaticAwareness | None,
    ) -> AvoidanceSide | None:
        if heading_rad is None or static_awareness is None:
            return preferred
        alternate: AvoidanceSide = "RIGHT" if preferred == "LEFT" else "LEFT"
        for side in (preferred, alternate):
            bearing = heading_rad + (pi / 4 if side == "LEFT" else -pi / 4)
            bearing %= 2 * pi
            probe = min(
                static_awareness.radial_probes,
                key=lambda item: abs(((item.bearing_rad - bearing + pi) % (2 * pi)) - pi),
            )
            if (
                probe.navmesh_reachable
                and probe.clearance_yards >= self.minimum_static_clearance_yards
            ):
                return side
        return None

    def _clear_hysteresis(self) -> None:
        self._active_track_id = None
        self._active_side = None
