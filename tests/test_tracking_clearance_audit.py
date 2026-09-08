from __future__ import annotations

import importlib.util
import re
import unittest
from io import StringIO
from math import pi
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "tracking_clearance_audit", ROOT / "scripts/audit_tracking_clearance.py"
)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class TrackingClearanceAuditTests(unittest.TestCase):
    """Green tests validate the detector, NOT the failing controller certificate."""

    def test_fixture_budget_is_pinned_to_native_probe(self):
        source = (ROOT / "native/pa_nav_probe/main.cpp").read_text(encoding="utf-8")
        for name, expected in (
            ("kPlayerCapsuleProbeRadius", audit.BODY_RADIUS),
            ("kControllerCrossTrackTolerance", audit.TRACKING_MARGIN),
        ):
            match = re.search(rf"constexpr float {name} = ([0-9.]+)f;", source)
            self.assertIsNotNone(match)
            self.assertEqual(float(match.group(1)), expected)

    def test_independent_distance_includes_endpoints_and_degenerate_segments(self):
        p = audit.NavPoint
        points = (p(0, 0, 0), p(0, 0, 0), p(10, 0, 0), p(10, 10, 0))
        self.assertEqual(audit.line_distance(3, 2, points), 2)
        self.assertEqual(audit.line_distance(-3, -4, points), 5)
        self.assertEqual(audit.line_distance(10, 12, points), 2)
        with self.assertRaises(ValueError):
            audit.line_distance(0, 0, ())

    def test_aligned_straight_control_passes_without_pivot(self):
        result = audit.audit_scenario(
            audit.make_scenario("straight", corner=False, noisy=False), runs=3
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["arrived_runs"], 3)
        self.assertEqual(result["maximum_pivot_fraction"], 0)

    def test_corner_exposes_margin_failure_despite_arrival(self):
        result = audit.audit_scenario(
            audit.make_scenario("corner", corner=True, noisy=False), runs=5
        )
        self.assertTrue(result["geometry_aware"])
        self.assertEqual(result["initial_outside_margin_runs"], 0)
        self.assertEqual(result["arrived_runs"], 5)
        self.assertEqual(result["outside_margin_runs"], 5)
        self.assertEqual(result["status"], "FAIL")
        self.assertGreater(result["maximum_capsule_bound_world"], audit.PROBED_RADIUS)
        self.assertGreater(result["first_violation"]["observation"]["index"], 1)

    def test_rotating_and_translating_does_not_hide_counterexample(self):
        original = audit.audit_scenario(
            audit.make_scenario("corner", corner=True), runs=5
        )
        transformed = audit.audit_scenario(
            audit.make_scenario(
                "transformed",
                corner=True,
                angle=pi / 3,
                translate=(40, -30),
            ),
            runs=5,
        )
        for key in ("status", "arrived_runs", "outside_margin_runs"):
            self.assertEqual(original[key], transformed[key])
        self.assertAlmostEqual(
            original["maximum_distance_world"],
            transformed["maximum_distance_world"],
            places=8,
        )

    def test_mirrored_corner_also_reports_failure(self):
        result = audit.audit_scenario(
            audit.make_scenario("right", corner=True, mirror=True), runs=5
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["initial_outside_margin_runs"], 0)

    def test_report_is_deterministic_and_does_not_present_arrival_as_clearance(self):
        first = audit.run_audit(runs=2)
        self.assertEqual(first, audit.run_audit(runs=2))
        self.assertEqual(first["status"], "FAIL")
        self.assertEqual(first["evidence"], "synthetic_kinematic_not_live")
        self.assertEqual(len(first["scenarios"]), 6)

    def test_invalid_run_count_is_rejected(self):
        scenario = audit.make_scenario("straight", corner=False)
        for count in (0, -1, 10001):
            with self.assertRaises(ValueError):
                audit.audit_scenario(scenario, runs=count)

    def test_cli_returns_failure_without_weakening_report(self):
        with (
            patch.object(audit.sys, "argv", ["audit_tracking_clearance.py"]),
            patch.object(audit, "run_audit", return_value={"status": "FAIL"}),
            patch.object(audit.sys, "stdout", new_callable=StringIO) as output,
        ):
            self.assertEqual(audit.main(), 1)
            self.assertIn('"status": "FAIL"', output.getvalue())
