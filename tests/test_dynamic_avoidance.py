from __future__ import annotations

from math import pi, tau
import unittest

from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness,
    NavPoint,
    RadialClearanceProbe,
)
from perfect_assassin.movement.dynamic_avoidance import (
    DynamicCollisionAvoidance,
    DynamicEntityTrack,
    DynamicEntityTracker,
    ScreenEntityObservation,
)
from perfect_assassin.movement.predictive_steering import SteeringIntent


def observation(
    observed_at_s: float,
    *,
    x: float,
    y: float,
    reaction: str = "FRIENDLY",
    source_key: str | None = None,
) -> ScreenEntityObservation:
    return ScreenEntityObservation(
        observed_at_s=observed_at_s,
        center_x_normalized=x,
        center_y_normalized=y,
        width_normalized=0.08,
        height_normalized=0.012,
        reaction=reaction,  # type: ignore[arg-type]
        confidence=0.95,
        source_key=source_key,
    )


def awareness(*, left_clear: float, right_clear: float) -> LocalStaticAwareness:
    probes = []
    for index in range(16):
        bearing = index * tau / 16
        clearance = 12.0
        if abs(((bearing - pi / 4 + pi) % tau) - pi) < 0.20:
            clearance = left_clear
        if abs(((bearing - (tau - pi / 4) + pi) % tau) - pi) < 0.20:
            clearance = right_clear
        probes.append(RadialClearanceProbe(bearing, clearance, clearance >= 1.0))
    return LocalStaticAwareness(
        physical_surfaces=frozenset({"ground"}),
        probe_radius_yards=12.0,
        overhead_clear=True,
        radial_probes=tuple(probes),
    )


class DynamicEntityTrackerTests(unittest.TestCase):
    def test_estimates_velocity_and_expires_without_static_memory(self) -> None:
        tracker = DynamicEntityTracker(ttl_s=0.8)
        first = tracker.update(
            (observation(1.0, x=0.10, y=0.32, source_key="plate:a"),),
            now_s=1.0,
        )
        second = tracker.update(
            (observation(1.1, x=0.08, y=0.38, source_key="plate:a"),),
            now_s=1.1,
        )
        self.assertEqual(first[0].track_id, second[0].track_id)
        self.assertEqual(second[0].observation_count, 2)
        self.assertLess(second[0].velocity_x_normalized_per_s, 0)
        self.assertGreater(second[0].velocity_y_normalized_per_s, 0)
        self.assertEqual(tracker.active_tracks(now_s=1.91), ())

    def test_nearest_neighbour_tracks_multiple_reactions_independently(self) -> None:
        tracker = DynamicEntityTracker()
        tracks = tracker.update(
            (
                observation(2.0, x=-0.25, y=0.35, reaction="HOSTILE"),
                observation(2.0, x=0.25, y=0.35, reaction="FRIENDLY"),
            ),
            now_s=2.0,
        )
        self.assertEqual(len(tracks), 2)
        updated = tracker.update(
            (
                observation(2.1, x=-0.20, y=0.37, reaction="HOSTILE"),
                observation(2.1, x=0.20, y=0.37, reaction="FRIENDLY"),
            ),
            now_s=2.1,
        )
        self.assertEqual({item.reaction for item in updated}, {"HOSTILE", "FRIENDLY"})
        self.assertTrue(all(item.observation_count == 2 for item in updated))


class DynamicCollisionAvoidanceTests(unittest.TestCase):
    def _mature_track(self, *, x: float = 0.08):
        tracker = DynamicEntityTracker()
        tracker.update((observation(1.0, x=x, y=0.42),), now_s=1.0)
        tracker.update((observation(1.1, x=x, y=0.49),), now_s=1.1)
        return tracker.update((observation(1.2, x=x, y=0.55),), now_s=1.2)

    def test_bends_while_moving_away_from_dynamic_entity(self) -> None:
        policy = DynamicCollisionAvoidance()
        decision = policy.decide(
            self._mature_track(x=0.08),
            now_s=1.2,
            heading_rad=0.0,
            static_awareness=awareness(left_clear=12.0, right_clear=12.0),
        )
        self.assertEqual(decision.state, "AVOID")
        self.assertEqual(decision.side, "LEFT")
        self.assertLess(decision.mouse_delta_bias, 0)
        base = SteeringIntent(
            "FOLLOW", 50, 1, NavPoint(5.0, 0.0, 0.0), "corridor",
        )
        adjusted = policy.apply(base, decision, maximum_mouse_delta=5)
        self.assertEqual(adjusted.state, "DYNAMIC_AVOID")
        self.assertEqual(adjusted.forward_hold_ms, 50)
        self.assertLess(adjusted.mouse_delta_x, base.mouse_delta_x)

    def test_chooses_other_side_when_static_geometry_blocks_preference(self) -> None:
        policy = DynamicCollisionAvoidance()
        decision = policy.decide(
            self._mature_track(x=0.08),
            now_s=1.2,
            heading_rad=0.0,
            static_awareness=awareness(left_clear=0.5, right_clear=12.0),
        )
        self.assertEqual(decision.state, "AVOID")
        self.assertEqual(decision.side, "RIGHT")
        self.assertGreater(decision.mouse_delta_bias, 0)

    def test_corridor_correction_cannot_reverse_active_avoidance_arc(self) -> None:
        policy = DynamicCollisionAvoidance()
        decision = policy.decide(
            self._mature_track(x=0.08),
            now_s=1.2,
            heading_rad=0.0,
            static_awareness=awareness(left_clear=12.0, right_clear=12.0),
        )
        self.assertEqual(decision.side, "LEFT")
        opposing = SteeringIntent(
            "FOLLOW", 50, 5, NavPoint(5.0, 0.0, 0.0), "corridor",
        )

        adjusted = policy.apply(opposing, decision, maximum_mouse_delta=5)

        self.assertEqual(adjusted.state, "DYNAMIC_AVOID")
        self.assertEqual(adjusted.forward_hold_ms, 50)
        self.assertLessEqual(adjusted.mouse_delta_x, 0)

    def test_yields_when_both_static_sides_are_unproven(self) -> None:
        policy = DynamicCollisionAvoidance()
        decision = policy.decide(
            self._mature_track(x=0.08),
            now_s=1.2,
            heading_rad=0.0,
            static_awareness=awareness(left_clear=0.5, right_clear=0.5),
        )
        self.assertEqual(decision.state, "YIELD")
        base = SteeringIntent(
            "FOLLOW", 50, 1, NavPoint(5.0, 0.0, 0.0), "corridor",
        )
        adjusted = policy.apply(base, decision, maximum_mouse_delta=5)
        self.assertEqual(adjusted.state, "DYNAMIC_YIELD")
        self.assertEqual(adjusted.forward_hold_ms, 0)

    def test_non_colliding_game_units_remain_awareness_only(self) -> None:
        policy = DynamicCollisionAvoidance(
            units_physically_block_movement=False,
        )
        decision = policy.decide(
            self._mature_track(x=0.08),
            now_s=1.2,
            heading_rad=0.0,
            static_awareness=awareness(left_clear=0.5, right_clear=0.5),
        )
        self.assertEqual(decision.state, "TRACKING")
        self.assertEqual(
            decision.reason,
            "visible_units_do_not_physically_block_client_movement",
        )
        base = SteeringIntent(
            "FOLLOW", 50, 1, NavPoint(5.0, 0.0, 0.0), "corridor",
        )
        self.assertIs(policy.apply(base, decision, maximum_mouse_delta=5), base)

    def test_single_frame_never_changes_movement(self) -> None:
        tracker = DynamicEntityTracker()
        tracks = tracker.update(
            (observation(1.0, x=0.0, y=0.60),),
            now_s=1.0,
        )
        policy = DynamicCollisionAvoidance()
        decision = policy.decide(
            tracks,
            now_s=1.0,
            heading_rad=0.0,
            static_awareness=None,
        )
        self.assertEqual(decision.state, "TRACKING")
        base = SteeringIntent(
            "FOLLOW", 50, 0, NavPoint(5.0, 0.0, 0.0), "corridor",
        )
        self.assertIs(policy.apply(base, decision, maximum_mouse_delta=5), base)

    def test_unconfirmed_track_cannot_hide_mature_collision_risk(self) -> None:
        mature = DynamicEntityTrack(
            track_id="mature",
            reaction="FRIENDLY",
            first_observed_at_s=1.0,
            last_observed_at_s=1.2,
            expires_at_s=2.0,
            center_x_normalized=0.085,
            center_y_normalized=0.55,
            velocity_x_normalized_per_s=0.0,
            velocity_y_normalized_per_s=0.0,
            width_normalized=0.08,
            height_normalized=0.012,
            position_uncertainty_normalized=0.02,
            confidence=0.95,
            observation_count=3,
            source_key="plate:mature",
        )
        unconfirmed = DynamicEntityTrack(
            track_id="unconfirmed",
            reaction="FRIENDLY",
            first_observed_at_s=1.2,
            last_observed_at_s=1.2,
            expires_at_s=2.0,
            center_x_normalized=0.0,
            center_y_normalized=0.90,
            velocity_x_normalized_per_s=0.0,
            velocity_y_normalized_per_s=0.0,
            width_normalized=0.08,
            height_normalized=0.012,
            position_uncertainty_normalized=0.02,
            confidence=0.99,
            observation_count=1,
            source_key="plate:new",
        )
        policy = DynamicCollisionAvoidance()

        decision = policy.decide(
            (mature, unconfirmed),
            now_s=1.2,
            heading_rad=0.0,
            static_awareness=awareness(left_clear=12.0, right_clear=12.0),
        )

        self.assertEqual(decision.state, "AVOID")
        self.assertEqual(decision.track_id, "mature")


if __name__ == "__main__":
    unittest.main()
