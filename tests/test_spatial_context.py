from __future__ import annotations

import json
import unittest
from dataclasses import replace
from math import pi, tau

from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness,
    LocalWallSegment,
    NavPoint,
    RadialClearanceProbe,
)
from perfect_assassin.movement.spatial_context import (
    SpatialBinding,
    SpatialContextPolicy,
    SpatialGeometryEvidence,
    SpatialPoseEvidence,
    evaluate_spatial_context,
)


def fixtures():
    binding = SpatialBinding(
        "synthetic-session", "SyntheticMap", "a" * 64, "floor:ground"
    )
    pose = SpatialPoseEvidence(
        binding,
        NavPoint(0, 0, 0),
        10.0,
        "frame:1",
        "CLIENT_VISIBLE_HUD",
        0.9,
        0.10,
        0.0,
    )
    awareness = LocalStaticAwareness(
        frozenset({"ground"}),
        12.0,
        True,
        tuple(
            RadialClearanceProbe(index * tau / 16, 12.0, True) for index in range(16)
        ),
        # Deliberately incorrect cached distance: evaluation must recompute it.
        wall_segments=(LocalWallSegment(NavPoint(2, -5, 0), NavPoint(2, 5, 0), 99.0),),
    )
    geometry = SpatialGeometryEvidence(
        binding, NavPoint(0, 0, 0), 10.0, "asset-query:1", awareness
    )
    return pose, geometry


def evaluate(pose, geometry, **kwargs):
    return evaluate_spatial_context(
        pose,
        geometry,
        now_monotonic_s=kwargs.get("now", 10.1),
        speed_bound_yards_per_s=kwargs.get("speed", 7.0),
        response_latency_bound_s=kwargs.get("latency", 0.1),
    )


class SpatialContextTests(unittest.TestCase):
    def test_direction_at_boundary_is_undefined_not_arbitrarily_forward(self):
        pose, geometry = fixtures()
        pose = replace(pose, position=NavPoint(2, 0, 0))
        geometry = replace(geometry, query_origin=pose.position)
        record = evaluate(pose, geometry)
        self.assertEqual(record["nearest_reported_boundary"]["distance_yards"], 0)
        self.assertIsNone(
            record["nearest_reported_boundary"]["relative_body_bearing_rad"]
        )

    def test_distance_is_recomputed_not_cached_or_to_midpoint(self):
        pose, geometry = fixtures()
        pose = replace(pose, position=NavPoint(0.2, 0.1, 0))
        record = evaluate(pose, geometry)
        boundary = record["nearest_reported_boundary"]
        self.assertAlmostEqual(boundary["distance_yards"], 1.8)
        self.assertAlmostEqual(boundary["relative_body_bearing_rad"], 0)
        self.assertEqual(record["status"], "LOCAL_SAMPLES_ONLY")
        self.assertFalse(record["free_space_certified"])
        self.assertFalse(record["execution_authority"])

    def test_latency_and_speed_consume_space_without_sending_a_command(self):
        pose, geometry = fixtures()
        stopped = evaluate(pose, geometry, speed=0)
        moving = evaluate(pose, geometry, speed=7)
        delayed = evaluate(pose, geometry, speed=7, latency=0.2)
        self.assertAlmostEqual(stopped["exposure_radius_yards"], 0.489)
        self.assertAlmostEqual(moving["exposure_radius_yards"], 1.889)
        self.assertGreater(
            delayed["exposure_radius_yards"], moving["exposure_radius_yards"]
        )
        self.assertLess(
            delayed["nearest_reported_boundary"]["exposure_budget_remaining_yards"], 0
        )
        self.assertEqual(delayed["status"], "LOCAL_SAMPLES_ONLY")
        self.assertNotIn("command", delayed)

    def test_no_metric_error_bound_is_not_replaced_by_high_confidence(self):
        pose, geometry = fixtures()
        record = evaluate(
            replace(pose, confidence=1, horizontal_error_bound_yards=None), geometry
        )
        self.assertIn("UNKNOWN_METRIC_POSE_ERROR", record["reasons"])
        self.assertIsNone(record["exposure_radius_yards"])
        self.assertIsNone(record["nearest_reported_boundary"])

    def test_identity_mismatches_suppress_current_distances(self):
        pose, geometry = fixtures()
        for change in (
            {"session_id": "other"},
            {"map_name": "other"},
            {"world_pack_sha256": "b" * 64},
            {"floor_id": "floor:bridge"},
        ):
            with self.subTest(change=change):
                record = evaluate(
                    pose, replace(geometry, binding=replace(geometry.binding, **change))
                )
                self.assertIn("GEOMETRY_BINDING_MISMATCH", record["reasons"])
                self.assertIsNone(record["nearest_reported_boundary"])
                self.assertEqual(record["radial_samples"], [])

    def test_missing_floor_cannot_be_inferred_from_matching_xy(self):
        pose, geometry = fixtures()
        binding = replace(pose.binding, floor_id=None)
        record = evaluate(
            replace(pose, binding=binding), replace(geometry, binding=binding)
        )
        self.assertIn("UNRESOLVED_FLOOR", record["reasons"])

    def test_expired_or_future_pose_is_not_rejuvenated_by_geometry(self):
        pose, geometry = fixtures()
        for time, reason in ((9.0, "STALE_POSE"), (11.0, "FUTURE_POSE_TIMESTAMP")):
            record = evaluate(replace(pose, observed_monotonic_s=time), geometry)
            self.assertIn(reason, record["reasons"])
            self.assertIsNone(record["nearest_reported_boundary"])

    def test_fresh_pose_does_not_rejuvenate_old_query(self):
        pose, geometry = fixtures()
        for time, reason in (
            (8.0, "STALE_LOCAL_QUERY"),
            (11.0, "FUTURE_GEOMETRY_TIMESTAMP"),
        ):
            record = evaluate(pose, replace(geometry, observed_monotonic_s=time))
            self.assertIn(reason, record["reasons"])
            self.assertEqual(record["geometry_observed_monotonic_s"], time)

    def test_origin_drift_horizontal_or_vertical_requires_new_query(self):
        pose, geometry = fixtures()
        for point in (NavPoint(0.31, 0, 0), NavPoint(0, 0, 0.31)):
            record = evaluate(replace(pose, position=point), geometry)
            self.assertIn("QUERY_ORIGIN_MOVED", record["reasons"])

    def test_rays_keep_their_origin_and_gaps_are_unknown(self):
        pose, geometry = fixtures()
        record = evaluate(replace(pose, position=NavPoint(0.2, 0, 0)), geometry)
        self.assertEqual(record["radial_origin"], [0, 0, 0])
        self.assertEqual(record["radial_gaps_semantics"], "UNKNOWN_NOT_INTERPOLATED")
        self.assertEqual(len(record["radial_samples"]), 16)
        for item in record["radial_samples"]:
            self.assertTrue(item["range_limit_reached"])
            self.assertEqual(
                item["distance_origin"], "RECORDED_QUERY_ORIGIN_NOT_CURRENT_POSE"
            )
        self.assertEqual(record["dynamic_obstacles"], "NOT_EVALUATED")

    def test_absent_boundaries_are_not_free_space(self):
        pose, geometry = fixtures()
        record = evaluate(
            pose,
            replace(geometry, awareness=replace(geometry.awareness, wall_segments=())),
        )
        self.assertIsNone(record["nearest_reported_boundary"])
        self.assertFalse(record["free_space_certified"])
        self.assertIn("nu înseamnă spațiu liber", record["operator_summary_ro"])

    def test_truncated_set_is_reported_not_upgraded_to_complete(self):
        pose, geometry = fixtures()
        record = evaluate(
            pose,
            replace(
                geometry,
                awareness=replace(geometry.awareness, component_truncated=True),
            ),
        )
        self.assertTrue(record["nearest_reported_boundary"]["set_truncated"])

    def test_body_heading_rotates_relative_bearing_not_camera(self):
        pose, geometry = fixtures()
        record = evaluate(replace(pose, body_heading_rad=pi / 2), geometry)
        self.assertAlmostEqual(
            record["nearest_reported_boundary"]["relative_body_bearing_rad"], -pi / 2
        )
        record = evaluate(replace(pose, body_heading_rad=None), geometry)
        self.assertIsNone(
            record["nearest_reported_boundary"]["relative_body_bearing_rad"]
        )

    def test_missing_geometry_is_explicit(self):
        pose, _ = fixtures()
        record = evaluate(pose, None)
        self.assertIn("MISSING_GEOMETRY", record["reasons"])
        self.assertEqual(record["status"], "REOBSERVE_OR_REQUERY")

    def test_forbidden_sources_are_rejected(self):
        pose, geometry = fixtures()
        for source in (
            "PROCESS_MEMORY",
            "SERVER_GROUND_TRUTH",
            "LAB_ORACLE",
            "UNKNOWN",
        ):
            with self.assertRaises(ValueError):
                replace(pose, source=source)
            with self.assertRaises(ValueError):
                replace(geometry, source=source)

    def test_nonfinite_and_invalid_numeric_evidence_is_rejected(self):
        pose, geometry = fixtures()
        for value in (float("nan"), float("inf"), -0.1, True):
            with self.assertRaises(ValueError):
                replace(pose, horizontal_error_bound_yards=value)
            with self.assertRaises(ValueError):
                evaluate(pose, geometry, speed=value)
        with self.assertRaises(ValueError):
            SpatialContextPolicy(minimum_pose_confidence=1.1)
        with self.assertRaises(ValueError):
            evaluate(pose, geometry, speed=1e308, latency=1e308)

    def test_low_confidence_stays_unusable(self):
        pose, geometry = fixtures()
        record = evaluate(replace(pose, confidence=0.69), geometry)
        self.assertIn("LOW_POSE_CONFIDENCE", record["reasons"])

    def test_translation_preserves_distance(self):
        pose, geometry = fixtures()

        def shifted(point):
            return NavPoint(point.x + 40, point.y - 30, point.z)

        wall = geometry.awareness.wall_segments[0]
        moved = replace(
            geometry,
            query_origin=shifted(geometry.query_origin),
            awareness=replace(
                geometry.awareness,
                wall_segments=(
                    replace(wall, left=shifted(wall.left), right=shifted(wall.right)),
                ),
            ),
        )
        record = evaluate(replace(pose, position=shifted(pose.position)), moved)
        self.assertEqual(record["nearest_reported_boundary"]["distance_yards"], 2)

    def test_record_is_json_serializable_with_provenance(self):
        pose, geometry = fixtures()
        record = evaluate(pose, geometry)
        self.assertEqual(json.loads(json.dumps(record, allow_nan=False)), record)
        self.assertEqual(record["binding"]["world_pack_sha256"], "a" * 64)
        self.assertEqual(record["pose_evidence_ref"], "frame:1")
        self.assertEqual(record["geometry_evidence_ref"], "asset-query:1")
