from __future__ import annotations

import unittest

import numpy as np

from perfect_assassin.movement.client_continuity import (
    ContinuityAction,
    ContinuityPolicy,
    VisibleClientState,
    VisibleClientStateObservation,
    classify_visible_client_state,
)


def _frame() -> np.ndarray:
    return np.zeros((600, 800, 4), dtype=np.uint8)


def _red_button(
    frame: np.ndarray, bounds: tuple[float, float, float, float],
) -> None:
    height, width = frame.shape[:2]
    left, top, right, bottom = bounds
    frame[
        int(top * height):int(bottom * height),
        int(left * width):int(right * width),
        :3,
    ] = (18, 22, 125)
    frame[:, :, 3] = 255


class VisibleClientStateTests(unittest.TestCase):
    def test_crc_valid_world_state_dominates_red_action_bar_pixels(self) -> None:
        frame = _frame()
        _red_button(frame, (0.40, 0.65, 0.60, 0.72))
        observation = classify_visible_client_state(
            frame, coordinate_hud_valid=True, player_alive=True,
        )
        self.assertEqual(observation.state, VisibleClientState.IN_WORLD)
        self.assertEqual(observation.confidence, 1.0)

    def test_dead_player_is_distinct_from_disconnected_client(self) -> None:
        observation = classify_visible_client_state(
            _frame(), coordinate_hud_valid=True, player_alive=False,
        )
        self.assertEqual(observation.state, VisibleClientState.DEAD_IN_WORLD)

    def test_released_ghost_is_distinct_from_unreleased_death(self) -> None:
        observation = classify_visible_client_state(
            _frame(),
            coordinate_hud_valid=True,
            player_alive=False,
            player_ghost=True,
        )
        self.assertEqual(observation.state, VisibleClientState.GHOST_IN_WORLD)
        self.assertEqual(
            ContinuityPolicy().decide(observation, recovery_actions_used=0),
            ContinuityAction.RECOVER_CORPSE,
        )

    def test_disconnected_dialog_requires_both_dialog_and_login_buttons(self) -> None:
        frame = _frame()
        _red_button(frame, (0.40, 0.48, 0.60, 0.55))
        _red_button(frame, (0.43, 0.67, 0.57, 0.72))
        observation = classify_visible_client_state(
            frame, coordinate_hud_valid=False, player_alive=None,
        )
        self.assertEqual(observation.state, VisibleClientState.DISCONNECTED_DIALOG)

    def test_login_and_character_select_have_separate_normalized_regions(self) -> None:
        login = _frame()
        _red_button(login, (0.43, 0.67, 0.57, 0.72))
        self.assertEqual(
            classify_visible_client_state(
                login, coordinate_hud_valid=False, player_alive=None,
            ).state,
            VisibleClientState.LOGIN_SCREEN,
        )
        character = _frame()
        _red_button(character, (0.42, 0.88, 0.58, 0.94))
        self.assertEqual(
            classify_visible_client_state(
                character, coordinate_hud_valid=False, player_alive=None,
            ).state,
            VisibleClientState.CHARACTER_SELECT,
        )

    def test_unknown_frame_never_authorizes_input(self) -> None:
        observation = classify_visible_client_state(
            _frame(), coordinate_hud_valid=False, player_alive=None,
        )
        self.assertEqual(observation.state, VisibleClientState.UNKNOWN)
        self.assertEqual(
            ContinuityPolicy().decide(observation, recovery_actions_used=0),
            ContinuityAction.WAIT_FOR_STABLE_FRAME,
        )

    def test_policy_is_bounded_and_maps_exact_states(self) -> None:
        policy = ContinuityPolicy(minimum_confidence=0.55, maximum_recovery_actions=2)
        observation = VisibleClientStateObservation(
            VisibleClientState.CHARACTER_SELECT, 0.9, {},
        )
        self.assertEqual(
            policy.decide(observation, recovery_actions_used=0),
            ContinuityAction.ENTER_WORLD,
        )
        self.assertEqual(
            policy.decide(observation, recovery_actions_used=2),
            ContinuityAction.STOP_FAIL_CLOSED,
        )


if __name__ == "__main__":
    unittest.main()
