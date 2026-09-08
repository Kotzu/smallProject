import unittest

from perfect_assassin.movement.heading_estimator import (
    DisplacementHeadingEstimator,
    VisibleHeadingObserver,
)


class DisplacementHeadingEstimatorTests(unittest.TestCase):
    def test_rejects_quantized_micro_steps_until_vector_is_stable(self) -> None:
        estimator = DisplacementHeadingEstimator(minimum_displacement_world=1.0)
        estimator.reset(x=10.0, y=20.0)
        self.assertIsNone(estimator.observe(x=10.18, y=20.14))
        self.assertIsNone(estimator.observe(x=10.54, y=20.42))
        heading = estimator.observe(x=11.08, y=20.84)
        self.assertIsNotNone(heading)
        assert heading is not None
        self.assertAlmostEqual(heading, 0.661, places=2)

    def test_resets_anchor_after_proven_heading(self) -> None:
        estimator = DisplacementHeadingEstimator(minimum_displacement_world=1.0)
        estimator.reset(x=0.0, y=0.0)
        self.assertIsNotNone(estimator.observe(x=2.0, y=0.0))
        self.assertIsNone(estimator.observe(x=2.2, y=0.0))


class VisibleHeadingObserverTests(unittest.TestCase):
    def test_visible_heading_initializes_absolute_yaw(self) -> None:
        heading, source = VisibleHeadingObserver().observe(
            predicted_heading_rad=None,
            visible_heading_rad=2.75,
        )
        self.assertEqual(heading, 2.75)
        self.assertEqual(source, "VISIBLE_CLIENT_HEADING_INITIAL")

    def test_visible_jitter_is_corrected_without_replacing_prediction(self) -> None:
        heading, source = VisibleHeadingObserver(
            correction_gain=0.25,
            maximum_correction_rad=0.10,
        ).observe(
            predicted_heading_rad=1.00,
            visible_heading_rad=1.20,
        )
        self.assertAlmostEqual(heading, 1.05)
        self.assertEqual(source, "VISIBLE_CLIENT_HEADING_FUSED")

    def test_large_visual_innovation_is_bounded_per_fresh_frame(self) -> None:
        heading, _source = VisibleHeadingObserver(
            correction_gain=0.25,
            maximum_correction_rad=0.10,
        ).observe(
            predicted_heading_rad=0.0,
            visible_heading_rad=2.0,
        )
        self.assertAlmostEqual(abs(heading), 0.10)

    def test_pca_axis_flip_is_resolved_against_continuous_prediction(self) -> None:
        heading, source = VisibleHeadingObserver(
            correction_gain=0.70,
            maximum_correction_rad=0.25,
        ).observe(
            predicted_heading_rad=0.20,
            visible_heading_rad=0.20 + 3.141592653589793 - 0.04,
        )
        self.assertAlmostEqual(heading, 0.172, places=3)
        self.assertEqual(source, "VISIBLE_CLIENT_HEADING_AXIAL_FLIP_FUSED")

    def test_normal_visible_heading_is_not_flipped(self) -> None:
        heading, source = VisibleHeadingObserver().observe(
            predicted_heading_rad=-0.40,
            visible_heading_rad=-0.30,
        )
        self.assertAlmostEqual(heading, -0.33, places=3)
        self.assertEqual(source, "VISIBLE_CLIENT_HEADING_FUSED")

    def test_safe_displacement_dominates_minimap_pixel_jitter(self) -> None:
        heading, source = VisibleHeadingObserver().observe(
            predicted_heading_rad=3.00,
            visible_heading_rad=2.66,
            displacement_heading_rad=3.10,
        )

        self.assertAlmostEqual(heading, 3.025, places=3)
        self.assertEqual(source, "DISPLACEMENT_VISIBLE_HEADING_FUSED")

    def test_implausible_displacement_cannot_replace_visible_fusion(self) -> None:
        heading, source = VisibleHeadingObserver().observe(
            predicted_heading_rad=0.0,
            visible_heading_rad=0.10,
            displacement_heading_rad=1.20,
        )

        self.assertAlmostEqual(heading, 0.07, places=3)
        self.assertEqual(source, "VISIBLE_CLIENT_HEADING_FUSED")


if __name__ == "__main__":
    unittest.main()
