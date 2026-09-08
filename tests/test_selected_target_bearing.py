from __future__ import annotations

import copy
import importlib
import math
from pathlib import Path
import sys
import unittest

import numpy as np

from perfect_assassin.application.combat_intake import (
    decode_combat_observation,
    decode_target_bearing_observation,
)
from perfect_assassin.contract_validation import ContractValidator
from tests.test_combat_hud import synthetic_combat_hud, valid_packet
from tests.test_coordinate_hud import capture_manifest


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "windows-capture"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))

combat_detector_module = importlib.import_module("combat_hud_detector")
bearing_detector_module = importlib.import_module("selected_target_bearing_detector")


def draw_ellipse(
    frame: np.ndarray,
    *,
    center_x: int,
    center_y: int,
    radius_x: int = 80,
    radius_y: int = 24,
) -> None:
    for angle in np.linspace(0, 2 * math.pi, 360, endpoint=False):
        x = int(round(center_x + radius_x * math.cos(float(angle))))
        y = int(round(center_y + radius_y * math.sin(float(angle))))
        frame[y - 2 : y + 3, x - 2 : x + 3, :3] = (0, 220, 255)


def draw_nameplate(frame: np.ndarray, *, center_x: int, y: int) -> None:
    frame[y : y + 5, center_x - 65 : center_x + 66, :3] = (0, 210, 240)


def draw_combat_ellipse(frame: np.ndarray, *, center_x: int, center_y: int) -> None:
    for angle in np.linspace(0, 2 * math.pi, 360, endpoint=False):
        x = int(round(center_x + 80 * math.cos(float(angle))))
        y = int(round(center_y + 24 * math.sin(float(angle))))
        frame[y - 2 : y + 3, x - 2 : x + 3, :3] = (40, 150, 255)


def draw_dim_orange_ellipse(
    frame: np.ndarray,
    *,
    center_x: int,
    center_y: int,
    radius_x: int = 24,
    radius_y: int = 3,
) -> None:
    for relative_x in range(-radius_x, radius_x + 1):
        curve_y = int(round(radius_y * (abs(relative_x) / radius_x) ** 2))
        x = center_x + relative_x
        y = center_y + curve_y
        frame[y : y + 2, x, :3] = (35, 85, 160)


def draw_thin_ellipse(
    frame: np.ndarray,
    *,
    center_x: int,
    center_y: int,
    radius_x: int = 55,
    radius_y: int = 10,
) -> None:
    for angle in np.linspace(0, 2 * math.pi, 360, endpoint=False):
        x = int(round(center_x + radius_x * math.cos(float(angle))))
        y = int(round(center_y + radius_y * math.sin(float(angle))))
        frame[y, x, :3] = (0, 220, 255)


class SelectedTargetBearingDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.capture_validator = ContractValidator(
            ROOT / "contracts" / "capture-frame.schema.json"
        )
        self.combat_validator = ContractValidator(
            ROOT / "contracts" / "combat-hud.schema.json"
        )
        self.bearing_validator = ContractValidator(
            ROOT / "contracts" / "selected-target-bearing.schema.json"
        )
        combat_profile = combat_detector_module.load_profile(
            ROOT / "config" / "combat" / "combat-hud-tbc243-v2.json"
        )
        self.combat_detector = combat_detector_module.CombatHudDetector(
            combat_profile,
            self.capture_validator,
            self.combat_validator,
        )
        bearing_profile = bearing_detector_module.load_profile(
            ROOT / "config" / "combat" / "selected-target-bearing-tbc243-v1.json"
        )
        self.detector = bearing_detector_module.SelectedTargetBearingDetector(
            bearing_profile,
            self.capture_validator,
            self.combat_validator,
            self.bearing_validator,
        )

    def sample(self, frame: np.ndarray):
        manifest = capture_manifest()
        combat = self.combat_detector.detect(
            manifest,
            frame,
            observation_id="combat-hud:fixture:bearing",
        )
        bearing = self.detector.detect(
            manifest,
            frame,
            combat,
            observation_id="target-bearing:fixture:one",
        )
        combat_state = decode_combat_observation(
            combat,
            validator=self.combat_validator,
        )
        bearing_state = decode_target_bearing_observation(
            bearing,
            validator=self.bearing_validator,
        )
        return combat, bearing, combat_state, bearing_state

    def test_selection_circle_precedes_nameplate_and_binds_same_frame(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        draw_ellipse(frame, center_x=570, center_y=400)
        draw_nameplate(frame, center_x=400, y=300)
        combat, bearing, combat_state, bearing_state = self.sample(frame)

        self.assertEqual(bearing["tracking_state"], "VISIBLE")
        self.assertEqual(bearing["detection_method"], "selection_circle")
        self.assertEqual(bearing["direction"], "RIGHT")
        self.assertGreater(bearing["offset_x_normalized"], 0.3)
        self.assertEqual(bearing["frame_id"], combat["frame_id"])
        self.assertTrue(bearing_state.is_bound_to(combat_state))

    def test_distant_selection_circle_above_old_near_target_roi_is_visible(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        draw_thin_ellipse(
            frame,
            center_x=260,
            center_y=180,
        )
        _combat, bearing, _combat_state, _bearing_state = self.sample(frame)

        self.assertEqual(bearing["tracking_state"], "VISIBLE")
        self.assertEqual(bearing["detection_method"], "distant_selection_arc")
        self.assertEqual(bearing["direction"], "LEFT")

    def test_top_right_minimap_like_ring_cannot_override_world_target(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        draw_ellipse(frame, center_x=720, center_y=130, radius_x=55, radius_y=30)
        draw_ellipse(frame, center_x=260, center_y=400)
        _combat, bearing, _combat_state, _bearing_state = self.sample(frame)

        self.assertEqual(bearing["tracking_state"], "VISIBLE")
        self.assertEqual(bearing["direction"], "LEFT")
        self.assertLess(bearing["center_x_px"], 400)

    def test_right_bottom_clipped_circle_is_rejected_as_overlay_ambiguous(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        draw_ellipse(
            frame,
            center_x=775,
            center_y=470,
            radius_x=105,
            radius_y=85,
        )
        _combat, bearing, _combat_state, _bearing_state = self.sample(frame)

        self.assertEqual(bearing["tracking_state"], "LOST")
        self.assertIsNone(bearing["detection_method"])
        self.assertIsNone(bearing["direction"])

    def test_red_hostile_selection_circle_is_accepted_before_and_during_combat(self) -> None:
        combat_frame = synthetic_combat_hud(valid_packet(in_combat=True))
        draw_combat_ellipse(combat_frame, center_x=260, center_y=400)
        _combat, visible, _combat_state, _bearing_state = self.sample(combat_frame)
        self.assertEqual(visible["tracking_state"], "VISIBLE")
        self.assertEqual(visible["detection_method"], "selection_circle")
        self.assertEqual(visible["direction"], "LEFT")

        idle_frame = synthetic_combat_hud(valid_packet(in_combat=False))
        draw_combat_ellipse(idle_frame, center_x=260, center_y=400)
        _combat, visible_idle, _combat_state, _bearing_state = self.sample(idle_frame)
        self.assertEqual(visible_idle["tracking_state"], "VISIBLE")
        self.assertEqual(visible_idle["detection_method"], "selection_circle")
        self.assertEqual(visible_idle["direction"], "LEFT")

    def test_reviewed_neutral_dummy_can_override_its_red_selection_ring(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(in_combat=False, target_hostile=False, target_reaction=4)
        )
        draw_combat_ellipse(frame, center_x=260, center_y=400)
        manifest = capture_manifest()
        combat = self.combat_detector.detect(
            manifest,
            frame,
            observation_id="combat-hud:fixture:neutral-red-dummy",
        )

        bearing = self.detector.detect(
            manifest,
            frame,
            combat,
            observation_id="target-bearing:fixture:neutral-red-dummy",
            indicator_color_override="red",
        )

        self.assertEqual(bearing["tracking_state"], "VISIBLE")
        self.assertEqual(bearing["detection_method"], "selection_circle")
        self.assertEqual(bearing["direction"], "LEFT")

    def test_neutral_red_ring_fuses_the_closest_yellow_nameplate(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(in_combat=False, target_hostile=False, target_reaction=4)
        )
        draw_combat_ellipse(frame, center_x=260, center_y=400)
        draw_nameplate(frame, center_x=275, y=300)
        draw_nameplate(frame, center_x=620, y=310)
        manifest = capture_manifest()
        combat = self.combat_detector.detect(
            manifest,
            frame,
            observation_id="combat-hud:fixture:ring-plate-fusion",
        )

        result = self.detector.detect(
            manifest,
            frame,
            combat,
            observation_id="target-bearing:fixture:ring-plate-fusion",
            indicator_color_override="red",
        )

        self.assertEqual(result["tracking_state"], "VISIBLE")
        self.assertEqual(
            result["detection_method"], "selection_circle_nameplate_fusion"
        )
        self.assertAlmostEqual(result["center_x_px"], 275, delta=5)

    def test_unknown_indicator_colour_override_is_rejected(self) -> None:
        frame = synthetic_combat_hud(valid_packet())
        manifest = capture_manifest()
        combat = self.combat_detector.detect(
            manifest,
            frame,
            observation_id="combat-hud:fixture:bad-colour-override",
        )
        with self.assertRaisesRegex(Exception, "colour override"):
            self.detector.detect(
                manifest,
                frame,
                combat,
                observation_id="target-bearing:fixture:bad-colour-override",
                indicator_color_override="blue",
            )

    def test_dim_distant_orange_selection_arc_is_visible(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(in_combat=False, target_hostile=False, target_reaction=4)
        )
        draw_dim_orange_ellipse(frame, center_x=470, center_y=400)
        _combat, visible, _combat_state, _bearing_state = self.sample(frame)

        self.assertEqual(visible["tracking_state"], "VISIBLE")
        self.assertEqual(visible["direction"], "RIGHT")
        self.assertAlmostEqual(visible["center_x_px"], 470, delta=5)

    def test_vertically_aligned_strong_traces_share_one_bearing(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(in_combat=False, target_hostile=False, target_reaction=4)
        )
        draw_dim_orange_ellipse(frame, center_x=470, center_y=400)
        draw_nameplate(frame, center_x=470, y=300)
        _combat, visible, _combat_state, _bearing_state = self.sample(frame)

        self.assertEqual(visible["tracking_state"], "VISIBLE")
        self.assertEqual(visible["direction"], "RIGHT")

    def test_spatially_separated_strong_circles_remain_ambiguous(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(in_combat=False, target_hostile=False, target_reaction=4)
        )
        draw_dim_orange_ellipse(frame, center_x=220, center_y=400)
        draw_dim_orange_ellipse(frame, center_x=580, center_y=400)
        _combat, result, _combat_state, _bearing_state = self.sample(frame)

        self.assertEqual(result["tracking_state"], "AMBIGUOUS")
        self.assertEqual(result["reason"], "multiple_selection_circle_candidates")

    def test_unique_nameplate_is_never_treated_as_selected_target_bearing(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        draw_nameplate(frame, center_x=400, y=300)
        _combat, bearing, _combat_state, _bearing_state = self.sample(frame)
        self.assertEqual(bearing["tracking_state"], "AMBIGUOUS")
        self.assertEqual(
            bearing["reason"],
            "unbound_nameplate_not_selected_target_evidence",
        )
        self.assertIsNone(bearing["detection_method"])
        self.assertIsNone(bearing["direction"])
        self.assertEqual(bearing["confidence"], 0)

    def test_missing_or_ambiguous_visual_evidence_never_invents_direction(self) -> None:
        no_indicator = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        _combat, lost, _combat_state, lost_state = self.sample(no_indicator)
        self.assertEqual(lost["tracking_state"], "LOST")
        self.assertIsNone(lost["direction"])
        self.assertEqual(lost_state.confidence, 0)

        ambiguous = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        draw_nameplate(ambiguous, center_x=280, y=290)
        draw_nameplate(ambiguous, center_x=530, y=310)
        _combat, result, _combat_state, _bearing_state = self.sample(ambiguous)
        self.assertEqual(result["tracking_state"], "AMBIGUOUS")
        self.assertIsNone(result["direction"])

    def test_thin_action_bar_fragments_do_not_become_a_selection_circle(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        for left in range(70, 250, 36):
            frame[540:550, left : left + 24, :3] = (0, 220, 255)
        _combat, bearing, _combat_state, _bearing_state = self.sample(frame)

        self.assertEqual(bearing["tracking_state"], "LOST")
        self.assertIsNone(bearing["direction"])

    def test_bottom_left_chat_colored_arc_is_excluded(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        draw_thin_ellipse(frame, center_x=120, center_y=470)
        _combat, bearing, _combat_state, _bearing_state = self.sample(frame)

        self.assertEqual(bearing["tracking_state"], "LOST")
        self.assertIsNone(bearing["detection_method"])
        self.assertIsNone(bearing["direction"])

    def test_large_filled_yellow_world_region_is_not_a_selection_circle(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        frame[380:480, 470:670, :3] = (0, 220, 255)
        _combat, bearing, _combat_state, _bearing_state = self.sample(frame)

        self.assertEqual(bearing["tracking_state"], "LOST")
        self.assertIsNone(bearing["direction"])

    def test_yellow_lamps_do_not_form_a_false_center_ring(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        frame[155:163, 365:368, :3] = (0, 210, 240)
        frame[165:173, 410:413, :3] = (0, 210, 240)
        frame[150:158, 455:458, :3] = (0, 210, 240)
        _combat, bearing, _combat_state, _bearing_state = self.sample(frame)

        self.assertEqual(bearing["tracking_state"], "LOST")
        self.assertIsNone(bearing["direction"])

    def test_bottom_right_yellow_overlay_cannot_steer_facing(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        frame[390:510, 750:790, :3] = (0, 210, 240)
        _combat, bearing, _combat_state, _bearing_state = self.sample(frame)

        self.assertEqual(bearing["tracking_state"], "LOST")
        self.assertIsNone(bearing["direction"])

    def test_same_target_rejects_an_impossible_edge_to_edge_jump(self) -> None:
        first = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        draw_ellipse(first, center_x=620, center_y=400)
        _combat, initial, _combat_state, _bearing_state = self.sample(first)
        self.assertEqual(initial["direction"], "RIGHT")

        jumped = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        draw_ellipse(jumped, center_x=150, center_y=400)
        _combat, result, _combat_state, _bearing_state = self.sample(jumped)
        self.assertEqual(result["tracking_state"], "AMBIGUOUS")
        self.assertEqual(result["reason"], "selected_target_bearing_discontinuous")
        self.assertIsNone(result["direction"])

    def test_same_target_smooths_a_plausible_partial_ring_shift(self) -> None:
        first = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        draw_ellipse(first, center_x=300, center_y=400)
        _combat, initial, _combat_state, _bearing_state = self.sample(first)

        shifted = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        draw_ellipse(shifted, center_x=340, center_y=400)
        _combat, stable, _combat_state, _bearing_state = self.sample(shifted)

        self.assertEqual(stable["tracking_state"], "VISIBLE")
        self.assertGreater(stable["center_x_px"], initial["center_x_px"])
        self.assertLess(stable["center_x_px"], 340)

    def test_cross_frame_and_nonfinite_forgery_fail_closed(self) -> None:
        frame = synthetic_combat_hud(valid_packet())
        draw_ellipse(frame, center_x=260, center_y=400)
        manifest = capture_manifest()
        combat = self.combat_detector.detect(
            manifest,
            frame,
            observation_id="combat-hud:fixture:cross-frame",
        )
        forged = copy.deepcopy(combat)
        forged["frame_id"] = "frame:other"
        with self.assertRaisesRegex(
            bearing_detector_module.SelectedTargetBearingError,
            "identity diverge",
        ):
            self.detector.detect(
                manifest,
                frame,
                forged,
                observation_id="target-bearing:fixture:forged",
            )

        _combat, record, _combat_state, _bearing_state = self.sample(frame)
        record["offset_x_normalized"] = float("nan")
        with self.assertRaises(Exception):
            self.bearing_validator.validate(record)

    def test_dense_yellow_frame_hits_budget_before_component_walk(self) -> None:
        frame = synthetic_combat_hud(valid_packet())
        frame[180:475, 96:704, :3] = (0, 220, 255)
        manifest = capture_manifest()
        combat = self.combat_detector.detect(
            manifest,
            synthetic_combat_hud(
                valid_packet(target_hostile=False, target_reaction=4)
            ),
            observation_id="combat-hud:fixture:dense",
        )
        with self.assertRaisesRegex(
            bearing_detector_module.SelectedTargetBearingError,
            "foreground pixel budget",
        ):
            self.detector.detect(
                manifest,
                frame,
                combat,
                observation_id="target-bearing:fixture:dense",
            )

    def test_many_small_natural_candidates_keep_strong_selected_ring(self) -> None:
        frame = synthetic_combat_hud(
            valid_packet(target_hostile=False, target_reaction=4)
        )
        # More than the candidate capacity of separated 2x2 yellow islands
        # models foliage without exceeding the separately enforced traversal
        # or foreground budgets.
        for index in range(600):
            x = 24 + (index % 100) * 7
            y = 190 + (index // 100) * 9
            frame[y : y + 2, x : x + 2, :3] = (0, 220, 255)
        draw_ellipse(frame, center_x=300, center_y=400)

        _combat, bearing, _combat_state, _bearing_state = self.sample(frame)
        self.assertEqual(bearing["tracking_state"], "VISIBLE")
        self.assertAlmostEqual(bearing["center_x_px"], 300, delta=20)


if __name__ == "__main__":
    unittest.main()
