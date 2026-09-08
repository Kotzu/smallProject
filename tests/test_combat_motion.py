from __future__ import annotations

from dataclasses import replace
import unittest

from perfect_assassin.movement.combat_motion import (
    FacingTransferProbeController,
    HumanlikeCombatMotionController,
)
from perfect_assassin.movement.client_navmesh import NavPoint
from perfect_assassin.movement.target_tether import TargetTetherIntent
from tests.test_combat_policy import action, bearing, state


class HumanlikeCombatMotionControllerTests(unittest.TestCase):
    @staticmethod
    def tether(
        state_name: str,
        guidance_error: float | None,
        *,
        edge_clearance: float | None = None,
        edge_safe: bool | None = None,
    ) -> TargetTetherIntent:
        return TargetTetherIntent(
            state=state_name,
            projected_target=NavPoint(8.0, 0.0, 0.0),
            projected_distance_world=8.0,
            guidance_error_rad=guidance_error,
            guidance_point=(
                None if guidance_error is None else NavPoint(4.0, 2.0, 0.0)
            ),
            corridor_centerline_world=((0.0, 0.0), (4.0, 2.0), (8.0, 0.0)),
            direct_distance_world=8.0,
            corridor_distance_world=None if guidance_error is None else 9.0,
            maximum_lateral_detour_world=None if guidance_error is None else 2.0,
            reason="fixture_tether",
            corridor_edge_clearance_world=edge_clearance,
            corridor_edge_safe=edge_safe,
        )

    def test_waiting_navmesh_blocks_blind_forward_approach(self) -> None:
        observed = state(
            sequence=1,
            attack=action(in_range=False),
            sinister_strike=action(in_range=False),
            eviscerate=action(in_range=False),
        )
        controller = HumanlikeCombatMotionController()
        controller.set_tether_guidance(self.tether("WAITING_NAVMESH", None))
        intent = None
        for sequence in range(1, controller.APPROACH_STABLE_FRAMES + 1):
            frame = replace(observed, sequence=sequence)
            intent = controller.decide(
                frame, bearing(frame, direction="CENTER", offset_x_normalized=0.0)
            )
        assert intent is not None
        self.assertEqual(intent.state, "TETHER_BLOCKED")
        self.assertIsNone(intent.frame.movement)
        self.assertIsNone(intent.frame.strafe)

    def test_navmesh_detour_turns_toward_corridor_before_advancing(self) -> None:
        observed = state(
            sequence=1,
            attack=action(in_range=False),
            sinister_strike=action(in_range=False),
            eviscerate=action(in_range=False),
        )
        controller = HumanlikeCombatMotionController()
        controller.set_tether_guidance(self.tether("DETOUR_LEFT", 0.45))
        intent = None
        for sequence in range(1, controller.APPROACH_STABLE_FRAMES + 1):
            frame = replace(observed, sequence=sequence)
            intent = controller.decide(
                frame, bearing(frame, direction="CENTER", offset_x_normalized=0.0)
            )
        assert intent is not None
        self.assertEqual(intent.state, "TETHER_DETOUR")
        self.assertIsNone(intent.frame.movement)
        self.assertIsNone(intent.frame.strafe)
        self.assertTrue(intent.frame.mouse_look)
        self.assertGreater(intent.frame.mouse_velocity_x_px_s, 0)
        self.assertFalse(intent.aligned)

        controller.set_tether_guidance(self.tether("DETOUR_LEFT", 0.05))
        aligned = controller.decide(
            replace(observed, sequence=controller.APPROACH_STABLE_FRAMES + 1),
            bearing(
                replace(observed, sequence=controller.APPROACH_STABLE_FRAMES + 1),
                direction="CENTER",
                offset_x_normalized=0.0,
            ),
        )
        self.assertEqual(aligned.frame.movement, "MOVE_FORWARD")
        self.assertIsNone(aligned.frame.strafe)
        self.assertTrue(aligned.aligned)

    def test_safe_partial_navmesh_horizon_advances_and_requires_replan(self) -> None:
        observed = state(
            sequence=1,
            attack=action(in_range=False),
            sinister_strike=action(in_range=False),
            eviscerate=action(in_range=False),
        )
        controller = HumanlikeCombatMotionController()
        controller.set_tether_guidance(
            self.tether("PARTIAL_ADVANCE_LEFT", 0.35)
        )
        intent = None
        for sequence in range(1, controller.APPROACH_STABLE_FRAMES + 1):
            frame = replace(observed, sequence=sequence)
            intent = controller.decide(
                frame,
                bearing(frame, direction="CENTER", offset_x_normalized=0.0),
            )
        assert intent is not None
        self.assertEqual(intent.state, "TETHER_PARTIAL_ADVANCE")
        self.assertIsNone(intent.frame.movement)
        self.assertIsNone(intent.frame.strafe)
        self.assertGreater(intent.frame.mouse_velocity_x_px_s, 0)

        controller.set_tether_guidance(
            self.tether("PARTIAL_ADVANCE_DIRECT", 0.05)
        )
        aligned = controller.decide(
            replace(observed, sequence=controller.APPROACH_STABLE_FRAMES + 1),
            bearing(
                replace(observed, sequence=controller.APPROACH_STABLE_FRAMES + 1),
                direction="CENTER",
                offset_x_normalized=0.0,
            ),
        )
        self.assertEqual(aligned.state, "TETHER_PARTIAL_ADVANCE")
        self.assertEqual(aligned.frame.movement, "MOVE_FORWARD")
        self.assertIsNone(aligned.frame.strafe)

    def test_visible_candidate_without_selected_target_uses_continuous_facing(self) -> None:
        observed = state(sequence=1, target=None, in_combat=False)
        intent = HumanlikeCombatMotionController().decide(
            observed,
            bearing(observed, direction="RIGHT", offset_x_normalized=0.75),
        )
        self.assertEqual(intent.state, "CANDIDATE_FACE")
        self.assertIsNone(intent.target_identity_crc16)
        self.assertTrue(intent.frame.mouse_look)
        self.assertLess(intent.frame.mouse_velocity_x_px_s, 0)
        self.assertEqual(intent.frame.mouse_delta_x, 0)

    def test_out_of_range_target_is_approached_with_held_w_and_rmb(self) -> None:
        observed = state(
            sequence=1,
            attack=action(in_range=False),
            sinister_strike=action(in_range=False),
            eviscerate=action(in_range=False),
        )
        controller = HumanlikeCombatMotionController()
        intent = None
        for sequence in range(1, controller.APPROACH_STABLE_FRAMES + 1):
            frame = replace(observed, sequence=sequence)
            intent = controller.decide(
                frame,
                bearing(frame, direction="CENTER", offset_x_normalized=0.0),
            )

        assert intent is not None
        self.assertEqual(intent.state, "APPROACH")
        self.assertEqual(intent.frame.movement, "MOVE_FORWARD")
        self.assertTrue(intent.frame.mouse_look)

    def test_unknown_melee_range_never_guesses_forward_motion(self) -> None:
        observed = state(
            sequence=1,
            attack=action(in_range=None),
            sinister_strike=action(in_range=None),
            eviscerate=action(in_range=None),
        )
        intent = HumanlikeCombatMotionController().decide(
            observed,
            bearing(observed, direction="CENTER", offset_x_normalized=0.0),
        )

        self.assertEqual(intent.state, "LOCK")
        self.assertIsNone(intent.frame.movement)
        self.assertTrue(intent.frame.mouse_look)

    def test_aligned_melee_combat_orbits_with_held_strafe_and_rmb(self) -> None:
        observed = state(
            sequence=1,
            in_combat=True,
            attack=action(current=True, in_range=True),
            sinister_strike=action(in_range=True),
            eviscerate=action(in_range=True),
        )
        intent = HumanlikeCombatMotionController().decide(
            observed,
            bearing(observed, direction="CENTER", offset_x_normalized=0.0),
        )

        self.assertEqual(intent.state, "ORBIT")
        self.assertIn(intent.frame.strafe, {"STRAFE_LEFT", "STRAFE_RIGHT"})
        self.assertTrue(intent.frame.mouse_look)
        expected_feedforward = (
            HumanlikeCombatMotionController.ORBIT_MOUSE_FEEDFORWARD_PX
            if intent.frame.strafe == "STRAFE_LEFT"
            else -HumanlikeCombatMotionController.ORBIT_MOUSE_FEEDFORWARD_PX
        )
        self.assertEqual(
            intent.frame.mouse_velocity_x_px_s,
            expected_feedforward
            * HumanlikeCombatMotionController.SERVO_FRAME_RATE_EQUIVALENT_HZ
            * HumanlikeCombatMotionController.LOGICAL_YAW_TO_ACTUATOR_X,
            # Feed-forward is expressed in logical yaw above; the live TBC
            # transport has the opposite raw relative-mouse polarity.
        )

    def test_narrow_lane_guard_holds_strafe_near_bridge_edge(self) -> None:
        observed = state(
            sequence=1,
            in_combat=True,
            attack=action(current=True, in_range=True),
            sinister_strike=action(in_range=True),
            eviscerate=action(in_range=True),
        )
        controller = HumanlikeCombatMotionController()
        controller.set_tether_guidance(
            self.tether(
                "DIRECT",
                0.0,
                edge_clearance=0.30,
                edge_safe=False,
            )
        )

        intent = controller.decide(
            observed,
            bearing(observed, direction="CENTER", offset_x_normalized=0.0),
        )

        self.assertEqual(intent.state, "LANE_GUARD")
        self.assertIsNone(intent.frame.strafe)
        self.assertIsNone(intent.frame.movement)
        self.assertEqual(intent.reason, "combat_lane_edge_clearance_guard")

    def test_large_off_center_target_keeps_rmb_and_corrects_without_strafe(self) -> None:
        observed = state(
            sequence=1,
            in_combat=True,
            attack=action(current=True, in_range=True),
            sinister_strike=action(in_range=True),
            eviscerate=action(in_range=True),
        )
        intent = HumanlikeCombatMotionController().decide(
            observed,
            bearing(observed, direction="RIGHT", offset_x_normalized=0.4),
        )

        self.assertEqual(intent.state, "FACE")
        self.assertIsNone(intent.frame.strafe)
        self.assertLess(intent.frame.mouse_velocity_x_px_s, 0)
        self.assertTrue(intent.frame.mouse_look)

    def test_screen_edge_target_does_not_fake_physical_overlap(self) -> None:
        observed = state(
            sequence=1,
            in_combat=False,
            attack=action(in_range=True),
            sinister_strike=action(in_range=True),
            eviscerate=action(in_range=True),
        )
        intent = HumanlikeCombatMotionController().decide(
            observed,
            bearing(observed, direction="RIGHT", offset_x_normalized=1.0),
        )

        self.assertEqual(intent.state, "FACE")
        self.assertIsNone(intent.frame.movement)
        self.assertLess(intent.frame.mouse_velocity_x_px_s, 0)
        self.assertTrue(intent.frame.mouse_look)

    def test_orbit_is_a_short_burst_not_permanent_strafe(self) -> None:
        controller = HumanlikeCombatMotionController()
        first = state(
            sequence=1,
            in_combat=True,
            attack=action(current=True, in_range=True),
            sinister_strike=action(in_range=True),
            eviscerate=action(in_range=True),
        )
        burst = controller.decide(
            first, bearing(first, direction="CENTER", offset_x_normalized=0.0)
        )
        resting = replace(
            first,
            sequence=2,
            observed_monotonic_s=(
                first.observed_monotonic_s + controller.ORBIT_BURST_SECONDS + 0.05
            ),
        )
        rest = controller.decide(
            resting,
            bearing(resting, direction="CENTER", offset_x_normalized=0.0),
        )
        self.assertIsNotNone(burst.frame.strafe)
        self.assertIsNone(rest.frame.strafe)

    def test_small_facing_correction_does_not_chatter_held_strafe(self) -> None:
        controller = HumanlikeCombatMotionController()
        observed = state(
            sequence=1,
            in_combat=True,
            attack=action(current=True, in_range=True),
            sinister_strike=action(in_range=True),
            eviscerate=action(in_range=True),
        )

        centered = controller.decide(
            observed,
            bearing(observed, direction="CENTER", offset_x_normalized=0.0),
        )
        correcting = controller.decide(
            replace(observed, sequence=2),
            bearing(
                replace(observed, sequence=2),
                direction="RIGHT",
                offset_x_normalized=0.10,
            ),
        )

        self.assertEqual(correcting.frame.strafe, centered.frame.strafe)
        self.assertNotEqual(correcting.frame.mouse_velocity_x_px_s, 0)

    def test_severe_facing_error_suspends_held_strafe(self) -> None:
        controller = HumanlikeCombatMotionController()
        observed = state(
            sequence=1,
            in_combat=True,
            attack=action(current=True, in_range=True),
            sinister_strike=action(in_range=True),
            eviscerate=action(in_range=True),
        )
        controller.decide(
            observed,
            bearing(observed, direction="CENTER", offset_x_normalized=0.0),
        )
        severe = replace(observed, sequence=2)
        intent = controller.decide(
            severe,
            bearing(severe, direction="RIGHT", offset_x_normalized=0.60),
        )

        self.assertIsNone(intent.frame.strafe)
        self.assertTrue(intent.frame.mouse_look)

    def test_target_loss_releases_all_continuous_motion(self) -> None:
        observed = state(target=None, in_combat=False)
        intent = HumanlikeCombatMotionController().decide(observed, None)

        self.assertEqual(intent.state, "RELEASED")
        self.assertEqual(intent.frame.held_controls, frozenset())
        self.assertFalse(intent.frame.mouse_look)

    def test_selected_offscreen_target_uses_continuous_mouse_search(self) -> None:
        observed = state(sequence=2, in_combat=False)
        intent = HumanlikeCombatMotionController().decide(
            observed,
            bearing(
                observed,
                tracking_state="LOST",
                direction=None,
                offset_x_normalized=None,
            ),
        )

        self.assertEqual(intent.state, "HOLD_OCCLUSION")
        self.assertTrue(intent.frame.mouse_look)
        self.assertEqual(intent.frame.mouse_delta_x, 0)
        self.assertEqual(intent.frame.held_controls, frozenset())

    def test_blocked_tether_stops_camera_search_after_transient_loss(self) -> None:
        controller = HumanlikeCombatMotionController(
            require_tether_for_approach=True,
        )
        controller.set_tether_guidance(self.tether("PARTIAL_BLOCKED", 0.4))
        observed = state(
            sequence=1,
            attack=action(in_range=False),
            sinister_strike=action(in_range=False),
            eviscerate=action(in_range=False),
        )
        intent = None
        for sequence in range(1, controller.TRANSIENT_LOSS_FRAMES + 2):
            frame = replace(observed, sequence=sequence)
            intent = controller.decide(
                frame,
                bearing(
                    frame,
                    tracking_state="LOST",
                    direction=None,
                    offset_x_normalized=None,
                ),
            )

        assert intent is not None
        self.assertEqual(intent.state, "HOLD_WORLD_REPOSITION")
        self.assertEqual(intent.frame.mouse_velocity_x_px_s, 0.0)
        self.assertEqual(intent.frame.held_controls, frozenset())
        self.assertTrue(intent.frame.mouse_look)

    def test_transient_target_loss_releases_prior_approach_immediately(self) -> None:
        controller = HumanlikeCombatMotionController(initial_search_direction="LEFT")
        observed = state(
            sequence=1,
            attack=action(in_range=False),
            sinister_strike=action(in_range=False),
            eviscerate=action(in_range=False),
        )
        approach = None
        for sequence in range(1, controller.APPROACH_STABLE_FRAMES + 1):
            frame = replace(observed, sequence=sequence)
            approach = controller.decide(
                frame,
                bearing(frame, direction="CENTER", offset_x_normalized=0.0),
            )
        assert approach is not None
        lost_observed = replace(
            observed,
            sequence=controller.APPROACH_STABLE_FRAMES + 1,
        )
        lost = controller.decide(
            lost_observed,
            bearing(
                lost_observed,
                tracking_state="AMBIGUOUS",
                direction=None,
                offset_x_normalized=None,
            ),
        )

        self.assertEqual(approach.frame.movement, "MOVE_FORWARD")
        self.assertEqual(lost.state, "HOLD_OCCLUSION")
        self.assertEqual(lost.frame.held_controls, frozenset())
        self.assertTrue(lost.frame.mouse_look)

    def test_approach_waits_until_facing_is_inside_translation_corridor(self) -> None:
        observed = state(
            sequence=1,
            attack=action(in_range=False),
            sinister_strike=action(in_range=False),
            eviscerate=action(in_range=False),
        )
        intent = HumanlikeCombatMotionController().decide(
            observed,
            bearing(observed, direction="RIGHT", offset_x_normalized=0.10),
        )

        self.assertIsNone(intent.frame.movement)
        self.assertTrue(intent.frame.mouse_look)

    def test_coarse_center_left_flicker_never_chatters_forward_motion(self) -> None:
        controller = HumanlikeCombatMotionController()
        observed = state(
            sequence=1,
            attack=action(in_range=False),
            sinister_strike=action(in_range=False),
            eviscerate=action(in_range=False),
        )

        movements = []
        for sequence, offset in enumerate((0.0, -0.35) * 4, start=1):
            frame = replace(observed, sequence=sequence)
            intent = controller.decide(
                frame,
                bearing(
                    frame,
                    direction="CENTER" if offset == 0.0 else "LEFT",
                    offset_x_normalized=offset,
                ),
            )
            movements.append(intent.frame.movement)

        self.assertEqual(movements, [None] * len(movements))

    def test_active_approach_survives_one_small_facing_deviation(self) -> None:
        controller = HumanlikeCombatMotionController()
        observed = state(
            sequence=1,
            attack=action(in_range=False),
            sinister_strike=action(in_range=False),
            eviscerate=action(in_range=False),
        )
        intent = None
        for sequence in range(1, controller.APPROACH_STABLE_FRAMES + 1):
            frame = replace(observed, sequence=sequence)
            intent = controller.decide(
                frame,
                bearing(frame, direction="CENTER", offset_x_normalized=0.0),
            )
        assert intent is not None
        deviated = replace(
            observed,
            sequence=controller.APPROACH_STABLE_FRAMES + 1,
        )
        intent = controller.decide(
            deviated,
            bearing(deviated, direction="CENTER", offset_x_normalized=0.10),
        )

        self.assertEqual(intent.frame.movement, "MOVE_FORWARD")

    def test_stable_target_loss_enters_continuous_mouse_search(self) -> None:
        controller = HumanlikeCombatMotionController(initial_search_direction="LEFT")
        observed = state(sequence=2, in_combat=False)
        lost = bearing(
            observed,
            tracking_state="LOST",
            direction=None,
            offset_x_normalized=None,
        )
        intent = None
        for _ in range(controller.TRANSIENT_LOSS_FRAMES + 1):
            intent = controller.decide(observed, lost)

        assert intent is not None
        self.assertEqual(intent.state, "SEARCH")
        self.assertTrue(intent.frame.mouse_look)
        self.assertEqual(
            intent.frame.mouse_velocity_x_px_s,
            controller.SEARCH_MOUSE_VELOCITY_PX_S,
        )

    def test_lost_target_search_stops_before_a_blind_full_rotation(self) -> None:
        controller = HumanlikeCombatMotionController(initial_search_direction="LEFT")
        observed = state(sequence=2, in_combat=False)
        lost = bearing(
            observed,
            tracking_state="LOST",
            direction=None,
            offset_x_normalized=None,
        )
        for _ in range(controller.TRANSIENT_LOSS_FRAMES + 1):
            controller.decide(observed, lost)
        later = replace(
            observed,
            sequence=observed.sequence + 1,
            observed_monotonic_s=(
                observed.observed_monotonic_s
                + controller.SEARCH_SWEEP_SECONDS
                + 0.01
            ),
            expires_monotonic_s=(
                observed.expires_monotonic_s
                + controller.SEARCH_SWEEP_SECONDS
                + 0.01
            ),
        )
        intent = controller.decide(
            later,
            bearing(
                later,
                tracking_state="LOST",
                direction=None,
                offset_x_normalized=None,
            ),
        )

        self.assertEqual(intent.state, "HOLD_LOST_TARGET")
        self.assertEqual(intent.frame.mouse_velocity_x_px_s, 0.0)
        self.assertEqual(intent.frame.held_controls, frozenset())

    def test_initial_search_direction_is_validated_and_right_uses_calibrated_mouse_x(self) -> None:
        with self.assertRaisesRegex(ValueError, "initial_search_direction"):
            HumanlikeCombatMotionController(initial_search_direction="SIDEWAYS")

        controller = HumanlikeCombatMotionController(initial_search_direction="RIGHT")
        observed = state(sequence=2, in_combat=False)
        lost = bearing(
            observed,
            tracking_state="LOST",
            direction=None,
            offset_x_normalized=None,
        )
        intent = None
        for _ in range(controller.TRANSIENT_LOSS_FRAMES + 1):
            intent = controller.decide(observed, lost)
        assert intent is not None
        self.assertEqual(
            intent.frame.mouse_velocity_x_px_s,
            -controller.SEARCH_MOUSE_VELOCITY_PX_S,
        )

    def test_live_continuous_transfer_drives_right_error_toward_zero(self) -> None:
        controller = HumanlikeCombatMotionController(translation_enabled=False)
        observed = state(sequence=1, in_combat=False)
        screen_error = 0.45
        errors = [screen_error]

        # The measured TBC transfer is positive: positive raw mouse-X moves a
        # selected marker farther right.  A stable controller must therefore
        # emit the opposite raw sign for a positive screen error.
        measured_error_per_px_s_frame = 0.00035
        for sequence in range(1, 7):
            frame = replace(
                observed,
                sequence=sequence,
                observed_monotonic_s=observed.observed_monotonic_s + sequence * 0.08,
                expires_monotonic_s=observed.expires_monotonic_s + sequence * 0.08,
            )
            intent = controller.decide(
                frame,
                bearing(frame, direction="RIGHT", offset_x_normalized=screen_error),
            )
            self.assertLess(intent.frame.mouse_velocity_x_px_s, 0)
            screen_error += (
                intent.frame.mouse_velocity_x_px_s
                * measured_error_per_px_s_frame
            )
            errors.append(screen_error)

        self.assertLess(errors[-1], errors[0])

    def test_facing_only_mode_never_translates(self) -> None:
        observed = state(
            sequence=3,
            in_combat=True,
            attack=action(current=True, in_range=True),
            sinister_strike=action(in_range=True),
            eviscerate=action(in_range=True),
        )
        intent = HumanlikeCombatMotionController(
            translation_enabled=False
        ).decide(
            observed,
            bearing(observed, direction="CENTER", offset_x_normalized=0.0),
        )

        self.assertEqual(intent.frame.held_controls, frozenset())
        self.assertTrue(intent.frame.mouse_look)


class FacingTransferProbeControllerTests(unittest.TestCase):
    def test_emits_one_signed_impulse_without_translation_or_strafe(self) -> None:
        controller = FacingTransferProbeController(signed_delta_x=-16)
        observed = state(sequence=1)
        intents = [
            controller.decide(
                replace(observed, sequence=index),
                bearing(
                    replace(observed, sequence=index),
                    direction="LEFT",
                    offset_x_normalized=-0.2,
                ),
            )
            for index in range(1, 26)
        ]

        self.assertEqual(
            [intent.frame.mouse_delta_x for intent in intents],
            [0] * 12 + [-16] * 8 + [0] * 5,
        )
        self.assertTrue(all(intent.frame.mouse_look for intent in intents))
        self.assertTrue(all(not intent.frame.held_controls for intent in intents))


if __name__ == "__main__":
    unittest.main()
