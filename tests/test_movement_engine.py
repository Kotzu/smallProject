from __future__ import annotations

import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import io
import json
from math import tau
import os
import tempfile
from types import SimpleNamespace

from perfect_assassin.movement.engine import MovementEngine
from perfect_assassin.movement.client_navmesh import (
    ClientNavmeshError, LocalStaticAwareness, LocalTopologicalEgressPortal, LocalWallSegment,
    NavCorridor, NavPoint, NavPolygon, NavPortal, RadialClearanceProbe,
)
from perfect_assassin.movement.client_continuity import (
    VisibleClientState,
    VisibleClientStateObservation,
)
from perfect_assassin.movement.road_semantic_planner import (
    RoadWorldPoint, SemanticRoadRoute,
)
from perfect_assassin.movement.local_environment_awareness import (
    LocalEnvironmentAwareness, StructureContainmentEvidence,
)
from perfect_assassin.movement.structure_access_graph import (
    StructureAccessSpatialGraph,
)
from perfect_assassin.movement.operator_path import OperatorAuthoredPath
from perfect_assassin.movement.obstacle_memory import (
    LOCAL_CLEARANCE_EVIDENCE, LearnedObstacle,
)
from perfect_assassin.movement.predictive_steering import SteeringIntent
from perfect_assassin.movement.world_model import LayeredWorldModel
from perfect_assassin.movement.world_structure_index import (
    AxisAlignedBounds,
    Vector3,
    WorldStructure,
    WorldStructureSpatialIndex,
)
from perfect_assassin.movement.zone_transform import tbc243_zone_transform
from perfect_assassin.capture import (
    CaptureDeadlineExceededError,
    NoFreshCaptureFrameError,
)
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.domain.combat_range import (
    selected_target_melee_range_awareness,
)
from perfect_assassin.movement.dynamic_avoidance import DynamicEntityTrack
from perfect_assassin.movement.continuous_trajectory_follower import (
    ContinuousTrajectoryFollower,
)


RUNNER_PATH = Path(__file__).parents[1] / "integrations" / "windows-input"
import sys
if str(RUNNER_PATH) not in sys.path:
    sys.path.insert(0, str(RUNNER_PATH))
from run_navmesh_roaming import (
    BREADCRUMB_BACKTRACK_ARRIVAL_RADIUS_WORLD,
    COLLISION_SLIDE_EVIDENCE_S,
    CORRIDOR_RECENTER_PREPLAN_CROSS_TRACK_WORLD,
    CORRIDOR_RECENTER_PREPLAN_MAX_START_DRIFT_WORLD,
    LOCAL_CLEARANCE_ARRIVAL_RADIUS_WORLD,
    PIVOT_STALL_TIMEOUT_S,
    SEMANTIC_STATIC_FRONTIER_WORKER_QUERY_CONCURRENCY,
    STUCK_PROGRESS_EVIDENCE_S,
    _bounded_blocker_union, _suppress_learned_blockers_containing_pose,
    _latest_calibration, _load_semantic_destination, _navmesh_map_sha256,
    _load_zone_transform,
    _resume_heading, _resume_position,
    _resume_z_hint, _semantic_fallback_candidates,
    _semantic_forward_bypass_candidates, _semantic_goal_queue,
    _semantic_forward_bypass_in_worker_process,
    _warm_process_pool,
    _load_operator_path_journey, _operator_goal_queue,
    _observe_player_heading,
    _orient_initial_fallback_heading_to_corridor,
    _body_camera_yaw_delta,
    _body_yaw_observation,
    _exact_body_yaw_observation,
    _acquire_initial_visible_heading,
    EXACT_BODY_HEADING_SOURCE,
    PRESERVED_EXACT_BODY_HEADING_SOURCE,
    _allow_initial_direction_realignment,
    _scope_query_for_structure_egress,
    _corridor_requested_stop_z,
    DisplacementHeadingEstimator,
    assess_initial_forward_direction,
    _blocker_route_quality,
    _allow_bounded_blocker_exclusion,
    _collision_approach_heading,
    _dynamic_entity_awareness_record,
    _inject_confirmed_clearance_priors,
    _confirmed_local_corridor_clearance,
    _inject_traversed_surface_prior,
    _local_static_awareness_record,
    _local_clearance_anchor_pairs, _local_clearance_leg_is_valid,
    _portal_recenter_candidates,
    _point_segment_distance_2d,
    _segment_aabb_distance_2d,
    _route_static_structure_blockers,
    _semantic_goal_overlaps_static_structure,
    _merge_static_structure_horizon_blockers,
    _inject_static_structure_clearance_priors,
    _filter_traversable_wmo_horizon_blockers,
    _suppress_proven_wmo_horizon_blockers,
    _wmo_baseline_reaches_local_goal_in_worker_process,
    _select_initial_vertical_layer,
    _semantic_corridor_refinement, _semantic_refinement_midpoint,
    _replan_is_corridor_recenter_only,
    _recovery_budget_can_reset, _semantic_handoff_is_continuous,
    _semantic_cached_corridor_advances_toward_goal,
    _semantic_corridor_goal_divergence,
    _semantic_should_fly_by, _semantic_should_preplan,
    _corridor_recenter_no_progress_evidence,
    _update_pivot_stall_clock,
    CombatHudDetectionError,
    ClientVisibleStateError,
    CONTINUOUS_LEASE_TIMEOUT_MS,
    VisibleHeadingObserver,
    LiveCoordinatePoseSource,
    NAVIGATION_CAPTURE_DEADLINE_MS,
    CAMERA_STARTUP_SETTLE_ATTEMPTS,
    CAMERA_STARTUP_SETTLE_INTERVAL_S,
    CAMERA_STARTUP_STABLE_VISIBLE_FRAMES,
    VISIBLE_STATE_REACQUISITION_ATTEMPTS,
    VISIBLE_STATE_REACQUISITION_INTERVAL_S,
)
import run_movement_engine_client as movement_ui
import run_structure_awareness_service as structure_service
import run_nav_viewer_live_bridge as nav_viewer_bridge
import run_nav_viewer_pose_once as nav_viewer_pose
import persistent_navmesh_awareness as persistent_awareness


class ZoneMapTransformTests(unittest.TestCase):
    def test_recenter_preplan_starts_before_trajectory_must_stop(self) -> None:
        self.assertGreater(CORRIDOR_RECENTER_PREPLAN_CROSS_TRACK_WORLD, 0.0)
        self.assertLess(
            CORRIDOR_RECENTER_PREPLAN_CROSS_TRACK_WORLD,
            ContinuousTrajectoryFollower.MAX_CROSS_TRACK_REPLAN_WORLD,
        )
        self.assertGreaterEqual(
            CORRIDOR_RECENTER_PREPLAN_MAX_START_DRIFT_WORLD,
            11.0,
        )

    def test_route_tangent_never_flips_physical_minimap_heading_in_memory(self) -> None:
        corridor = NavCorridor(
            "Azeroth",
            31,
            31,
            NavPoint(0.0, 0.0, 1.0),
            NavPoint(-10.0, 0.0, 1.0),
            (NavPoint(0.0, 0.0, 1.0), NavPoint(-10.0, 0.0, 1.0)),
            source="test",
        )

        heading, source, ambiguous = _orient_initial_fallback_heading_to_corridor(
            0.0,
            heading_source="MINIMAP_VISION_FALLBACK",
            corridor=corridor,
        )

        self.assertEqual(heading, 0.0)
        self.assertEqual(source, "MINIMAP_VISION_FALLBACK")
        self.assertTrue(ambiguous)

    def test_control_center_reconciles_starting_from_live_process(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "integrations"
            / "windows-input"
            / "run_movement_engine_client.py"
        ).read_text(encoding="utf-8")
        self.assertIn('self.state == "STARTING"', source)
        self.assertIn("self.process.poll() is None", source)
        self.assertIn("self._set_running()", source)

    def test_verified_structure_egress_exclusion_survives_local_retry_budget(self) -> None:
        self.assertTrue(
            _allow_bounded_blocker_exclusion(
                True,
                local_recovery_attempts=3,
                structure_egress_active=True,
            )
        )
        self.assertFalse(
            _allow_bounded_blocker_exclusion(
                True,
                local_recovery_attempts=3,
                structure_egress_active=False,
            )
        )
        self.assertFalse(
            _allow_bounded_blocker_exclusion(
                False,
                local_recovery_attempts=4,
                structure_egress_active=True,
            )
        )
        self.assertTrue(
            _allow_bounded_blocker_exclusion(
                False,
                local_recovery_attempts=2,
                structure_egress_active=True,
                candidate_complete=True,
                excluded_polygons=8,
                route_length_world=28.2,
                route_maximum_length_world=26.6,
            )
        )
        self.assertFalse(
            _allow_bounded_blocker_exclusion(
                False,
                local_recovery_attempts=2,
                structure_egress_active=True,
                candidate_complete=True,
                excluded_polygons=0,
                route_length_world=28.2,
                route_maximum_length_world=26.6,
            )
        )
        self.assertFalse(
            _allow_bounded_blocker_exclusion(
                False,
                local_recovery_attempts=2,
                structure_egress_active=True,
                candidate_complete=True,
                excluded_polygons=8,
                route_length_world=28.7,
                route_maximum_length_world=26.6,
            )
        )

    def test_verified_structure_egress_restarts_geometry_steering_after_recovery(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        start = source.index("if blocker_route_accepted:")
        end = source.index("goal_x, goal_y = replan_goal_x, replan_goal_y", start)
        recovery = source[start:end]
        self.assertIn("if structure_resume_goal is not None:", recovery)
        self.assertIn("engine.steering = structure_egress_steering", recovery)
        self.assertIn("STRUCTURE_EGRESS_STEERING_RESET", recovery)

    def test_structure_egress_runner_targets_revalidated_exit_anchor(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        # The graph midpoint is only a topology witness.  Every runner entry
        # point must use StructureEgressPlan.movement_target so a client-
        # asset-proven outside anchor is not replaced by the covered midpoint.
        self.assertGreaterEqual(
            source.count("initial_egress.movement_target.x"), 1,
        )
        self.assertGreaterEqual(
            source.count("next_egress.movement_target.x"), 1,
        )
        self.assertGreaterEqual(
            source.count("waypoint_egress.movement_target.x"), 1,
        )
        self.assertGreaterEqual(
            source.count("frontier_egress.movement_target.x"), 1,
        )

    def test_recovery_memory_skips_only_repeated_local_clearance_failures(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("RecoveryStrategyMemory", source)
        self.assertIn("LEARNED_RECOVERY_STRATEGY_FAILURE", source)
        self.assertIn("LEARNED_RECOVERY_STRATEGY_SKIPPED", source)
        self.assertIn("same_bounded_cell_failed_twice_before", source)
        self.assertIn("recovery_strategy_memory.resolve_success", source)

    def test_exact_crc_hud_facing_bypasses_visual_fusion(self) -> None:
        observer = Mock()
        heading, source = _observe_player_heading(
            SimpleNamespace(latest_facing_source="COORDINATE_HUD_EXACT"),
            observer,
            predicted_heading_rad=0.25,
            observation={"position": {"facing_rad": 1.75}},
            displacement_heading_rad=0.50,
        )

        self.assertEqual(heading, 1.75)
        self.assertEqual(source, "COORDINATE_HUD_EXACT")
        observer.observe.assert_not_called()

    def test_minimap_facing_restores_bounded_visible_fusion(self) -> None:
        observer = VisibleHeadingObserver()
        heading, source = _observe_player_heading(
            SimpleNamespace(latest_facing_source="MINIMAP_VISION_FALLBACK"),
            observer,
            predicted_heading_rad=0.25,
            observation={"position": {"facing_rad": 0.65}},
            displacement_heading_rad=0.50,
        )

        self.assertAlmostEqual(heading, 0.50, places=3)
        self.assertEqual(source, "VISIBLE_CLIENT_HEADING_FUSED")

    def test_minimap_axis_jump_cannot_reverse_integrated_heading_before_motion(self) -> None:
        observer = VisibleHeadingObserver()
        heading, source = _observe_player_heading(
            SimpleNamespace(latest_facing_source="MINIMAP_VISION_FALLBACK"),
            observer,
            predicted_heading_rad=3.10,
            observation={"position": {"facing_rad": 0.02}},
            displacement_heading_rad=None,
        )

        # Wrapped angles may represent pi as either +pi or -pi.
        self.assertAlmostEqual(abs(heading), 3.140, places=2)
        self.assertEqual(source, "VISIBLE_CLIENT_HEADING_AXIAL_FLIP_FUSED")

    def test_minimap_heading_ignores_disagreeing_slide_chord(self) -> None:
        observer = VisibleHeadingObserver()
        heading, source = _observe_player_heading(
            SimpleNamespace(latest_facing_source="MINIMAP_VISION_FALLBACK"),
            observer,
            predicted_heading_rad=-2.80,
            observation={"position": {"facing_rad": 0.40}},
            displacement_heading_rad=-2.75,
        )

        self.assertAlmostEqual(heading, -2.759, places=2)
        self.assertEqual(source, "VISIBLE_CLIENT_HEADING_AXIAL_FLIP_FUSED")

    def test_minimap_slide_chord_must_agree_with_integrated_yaw(self) -> None:
        observer = VisibleHeadingObserver()
        heading, source = _observe_player_heading(
            SimpleNamespace(latest_facing_source="MINIMAP_VISION_FALLBACK"),
            observer,
            predicted_heading_rad=1.70,
            observation={"position": {"facing_rad": 2.72}},
            displacement_heading_rad=2.72,
        )

        self.assertAlmostEqual(heading, 1.95, places=2)
        self.assertEqual(source, "VISIBLE_CLIENT_HEADING_FUSED")

    def test_mouse_heading_integration_is_bounded_by_the_continuous_lease(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        update = source.index("if heading is not None and receipt_frame.mouse_velocity_x_px_s:")
        update_end = source.index("            dx, dy = world_x - before_x", update)
        block = source[update:update_end]
        self.assertIn("MOUSE_HEADING_ACTIVE_LEASE_S", block)
        self.assertIn('"kind": "MOUSE_HEADING_INTEGRATION_CLAMPED"', block)

    def test_continuous_frame_records_capture_and_observation_latency(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        frame = source[source.index('"kind": "CONTINUOUS_FRAME"'):]
        self.assertIn('"observation_gap_s": dt_s', frame)
        self.assertIn('"observation_latency_ms"', frame)
        self.assertIn('"capture_latency_ms"', frame)
        self.assertIn('"client_facing_source"', frame)
        self.assertIn('"body_yaw_observation_rad"', frame)
        self.assertIn('"camera_yaw_estimate_rad"', frame)
        self.assertIn('"body_camera_yaw_delta_rad"', frame)

    def test_continuous_runner_gates_stale_heading_before_input(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        gate = source[source.index("heading_integrity = assess_heading_integrity("):]
        self.assertIn("last_visible_heading_observed_s", gate)
        self.assertIn('"kind": "HEADING_EVIDENCE_LOST"', gate)
        self.assertIn('status = "HEADING_EVIDENCE_LOST"', gate)
        frame = source[source.index('"heading_integrity_state":'):]
        self.assertIn('"heading_integrity_evidence_age_s"', frame)

    def test_body_camera_yaw_delta_wraps_without_confusing_the_channels(self) -> None:
        self.assertAlmostEqual(
            _body_camera_yaw_delta(6.20, 0.05),
            0.1331853071795863,
            places=6,
        )
        self.assertIsNone(_body_camera_yaw_delta(None, 0.05))

    def test_minimap_facing_stays_out_of_the_exact_body_channel(self) -> None:
        observation = {"position": {"facing_rad": 1.5}}
        self.assertAlmostEqual(
            _exact_body_yaw_observation(
                observation,
                client_facing_source=EXACT_BODY_HEADING_SOURCE,
            ),
            1.5,
        )
        self.assertIsNone(
            _exact_body_yaw_observation(
                observation,
                client_facing_source="MINIMAP_VISION_FALLBACK",
            )
        )
        self.assertAlmostEqual(
            _body_yaw_observation(
                observation,
                client_facing_source="MINIMAP_VISION_FALLBACK",
            ),
            1.5,
        )

    def test_initial_direction_probe_uses_the_estimator_chord_not_one_frame_step(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        probe = source[source.index("assess_initial_forward_direction("):]
        self.assertIn("heading_estimator.last_displacement_world", probe)

    def test_initial_direction_realign_requests_a_stationary_pivot(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        probe = source[source.index('"kind": "INITIAL_FORWARD_DIRECTION_REALIGNED"'):]
        self.assertIn("request_stationary_pivot", probe)
        self.assertIn('"stationary_pivot_requested"', probe)

    def test_initial_direction_realign_requests_one_clean_pose_replan(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("MAX_INITIAL_DIRECTION_CORRIDOR_REPLANS = 1", source)
        self.assertIn('"kind": "INITIAL_DIRECTION_CORRIDOR_REPLAN_REQUESTED"', source)
        self.assertIn("initial_direction_replan_pending", source)
        self.assertIn("initial_direction_replan_forced", source)
        self.assertIn('"trajectory_loop_detected"', source)
        self.assertIn("initial_direction_replan_attempts", source)
        self.assertIn("< MAX_INITIAL_DIRECTION_CORRIDOR_REPLANS", source)

    def test_initial_direction_replan_does_not_block_on_small_calibration_offset(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "INITIAL_DIRECTION_REPLAN_MIN_CROSS_TRACK_WORLD = 2.0",
            source,
        )
        self.assertIn(
            '"kind": "INITIAL_DIRECTION_CORRIDOR_REPLAN_SKIPPED"',
            source,
        )
        self.assertIn("stationary_pivot_kept_without_sync_query", source)

    def test_structure_egress_first_chord_does_not_rebuild_proven_stair_route(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "structure_egress_initial_calibration = (\n"
            "                    structure_egress_opening_id is not None",
            source,
        )
        self.assertIn(
            "and not structure_egress_initial_calibration",
            source,
        )

    def test_initial_direction_realign_is_retried_with_a_bounded_limit(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("MAX_INITIAL_DIRECTION_PROBE_REALIGNS = 3", source)
        probe = source[source.index("retry_direction_probe ="):]
        self.assertIn("initial_direction_probe_realignment_count", probe)
        self.assertIn("< MAX_INITIAL_DIRECTION_PROBE_REALIGNS", probe)

    def test_live_heading_divergence_realign_is_bounded_and_stationary(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("MAX_LIVE_HEADING_DIVERGENCE_REALIGNS = 2", source)
        self.assertIn("MIN_DIRECTION_REALIGN_TANGENT_PROJECTION = 0.25", source)
        self.assertIn("INITIAL_FORWARD_DIRECTION_MIN_DISPLACEMENT_WORLD = 0.75", source)
        self.assertIn("INITIAL_FORWARD_DIRECTION_MAX_CROSS_TRACK_WORLD = 1.75", source)
        guard = source[source.index("LIVE_HEADING_DIVERGENCE_THRESHOLD_RAD"):]
        self.assertIn("LIVE_HEADING_DIVERGENCE_REALIGNED", guard)
        self.assertIn("request_stationary_pivot", guard)
        self.assertIn("< MAX_LIVE_HEADING_DIVERGENCE_REALIGNS", guard)
        self.assertIn("len(corridor.guidance_points()) <= 3", guard)
        self.assertIn("direction_probe_tangent_projection", guard)

    def test_wall_slide_direction_probe_is_logged_and_not_adopted(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            '"kind": "INITIAL_FORWARD_DIRECTION_REALIGNMENT_SKIPPED"',
            source,
        )
        self.assertIn("insufficient_projection_onto_", source)

    def test_clean_first_direction_chord_can_repair_stale_camera_heading(self) -> None:
        self.assertTrue(
            _allow_initial_direction_realignment(
                tangent_projection=-0.65,
                initial_realignment_count=1,
                cross_track_error_world=0.60,
                collision_slide_s=0.0,
                collision_evidence=False,
            )
        )

    def test_direction_chord_exception_does_not_override_known_collision_slide(self) -> None:
        self.assertFalse(
            _allow_initial_direction_realignment(
                tangent_projection=-0.65,
                initial_realignment_count=1,
                cross_track_error_world=0.60,
                collision_slide_s=0.0,
                collision_evidence=True,
            )
        )

    def test_breadcrumb_direction_probe_is_one_bounded_collision_exception(self) -> None:
        self.assertTrue(
            _allow_initial_direction_realignment(
                tangent_projection=-0.65,
                initial_realignment_count=1,
                cross_track_error_world=0.60,
                collision_slide_s=0.0,
                collision_evidence=True,
                verified_breadcrumb_recovery=True,
            )
        )
        self.assertFalse(
            _allow_initial_direction_realignment(
                tangent_projection=-0.65,
                initial_realignment_count=2,
                cross_track_error_world=0.60,
                collision_slide_s=0.0,
                collision_evidence=True,
                verified_breadcrumb_recovery=True,
            )
        )

    def test_runner_preserves_egress_scope_when_replanning_observed_blocker(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        collision = source[source.index("candidate_blockers = _bounded_blocker_union"):]
        self.assertIn(
            "candidate_query = query.with_observed_blockers(candidate_blockers)",
            collision,
        )
        self.assertIn("query = query.without_structure_egress_scope()", source)

    def test_collision_replan_preserves_floor_aware_egress_height(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        recovery = source[source.index("deferred_resume_goal = ("):]
        self.assertIn(
            "replan_goal_z = _corridor_requested_stop_z(corridor)",
            recovery,
        )
        self.assertIn("goal_z=replan_goal_z", recovery)
        self.assertIn("stop_z=side_anchor.z", recovery)
        self.assertIn("stop_z=pass_anchor.z", recovery)

    def test_corridor_requested_stop_height_is_optional_but_exact(self) -> None:
        corridor = NavCorridor(
            map_name="Azeroth",
            adt_x=0,
            adt_y=0,
            start=NavPoint(0.0, 0.0, 10.0),
            stop=NavPoint(2.0, 0.0, 20.0),
            points=(NavPoint(0.0, 0.0, 10.0), NavPoint(2.0, 0.0, 20.0)),
            requested_stop=NavPoint(2.0, 0.0, 20.0),
        )
        self.assertEqual(_corridor_requested_stop_z(corridor), 20.0)
        self.assertIsNone(
            _corridor_requested_stop_z(
                NavCorridor(
                    map_name="Azeroth",
                    adt_x=0,
                    adt_y=0,
                    start=NavPoint(0.0, 0.0, 10.0),
                    stop=NavPoint(2.0, 0.0, 10.0),
                    points=(
                        NavPoint(0.0, 0.0, 10.0),
                        NavPoint(2.0, 0.0, 10.0),
                    ),
                )
            )
        )

    def test_structure_egress_scope_uses_worldpack_structure_bounds(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        helper = source[source.index("def _scope_query_for_structure_egress"):]
        self.assertIn("bounds.minimum.x", helper)
        self.assertIn("query.for_structure_egress", helper)

    def test_bounded_direct_slice_can_skip_expensive_structure_scan(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("--skip-structure-awareness", source)
        self.assertIn("operator_requested_bounded_direct_navmesh_slice", source)
        self.assertIn("if args.skip_structure_awareness", source)
        self.assertIn("if not args.skip_structure_awareness", source)

    def test_f4a_arm_is_bound_only_after_read_only_preflight(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("--runtime-arm-wait-seconds", source)
        self.assertIn("_PreflightMotionRelease", source)
        self.assertIn('"status": "PREFLIGHT_READY"', source)
        bind = source.index('"kind": "CONTINUOUS_MOTION_ARM_BOUND_AFTER_PREFLIGHT"')
        control_loop = source.index("while (", bind)
        self.assertLess(bind, control_loop)
        arm_call = source.rfind("_load_runtime_motion_authority_after_preflight", 0, bind)
        self.assertGreater(arm_call, source.index('"status": "PREFLIGHT_READY"'))
        self.assertIn("wait_seconds=args.runtime_arm_wait_seconds", source[arm_call:bind])
        self.assertIn(
            "arm_files_required_before_preflight = args.runtime_arm_wait_seconds <= 0.0",
            source,
        )
        early_gate = source[
            source.index("arm_files_required_before_preflight ="):
            source.index("continuous_authorization_raw = (", source.index("arm_files_required_before_preflight ="))
        ]
        self.assertIn("and (\n                    not args.continuous_motion_arm_file.is_file()", early_gate)

    def test_preflight_arm_wait_is_bounded_and_never_issues_authority(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        helper_start = source.index("def _load_runtime_motion_authority_after_preflight")
        helper_end = source.index("def build_parser", helper_start)
        helper = source[helper_start:helper_end]
        self.assertIn("deadline = time.monotonic() + wait_seconds", helper)
        self.assertIn("if wait_seconds <= 0.0 or time.monotonic() >= deadline", helper)
        self.assertNotIn("issue_continuous_motion", helper)

    def test_preflight_rejection_is_published_as_not_running(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        checkpoint = source.index(
            "# Do not publish a misleading RUNNING checkpoint"
        )
        checkpoint_end = source.index("        while (", checkpoint)
        block = source[checkpoint:checkpoint_end]
        self.assertIn('else "LIVE_PREFLIGHT_REJECTED"', block)
        self.assertIn('if live_preflight_ready', block)

    def test_initial_forward_direction_accepts_a_corridor_aligned_chord(self) -> None:
        status, error = assess_initial_forward_direction(
            expected_heading_rad=0.0,
            observed_heading_rad=0.35,
            displacement_world=1.30,
            physical_motion_continuous=True,
            forward_requested=True,
            cross_track_error_world=0.40,
        )

        self.assertEqual(status, "ALIGNED")
        self.assertAlmostEqual(error, -0.35)

    def test_initial_forward_direction_realigns_a_diagonal_chord_before_forward(self) -> None:
        status, error = assess_initial_forward_direction(
            expected_heading_rad=3.14,
            observed_heading_rad=2.60,
            displacement_world=1.05,
            physical_motion_continuous=True,
            forward_requested=True,
            cross_track_error_world=0.55,
        )

        self.assertEqual(status, "REALIGN")
        self.assertAlmostEqual(error, 0.54, places=2)

    def test_initial_forward_direction_requests_realign_for_opposite_chord(self) -> None:
        status, error = assess_initial_forward_direction(
            expected_heading_rad=3.12,
            observed_heading_rad=0.02,
            displacement_world=1.52,
            physical_motion_continuous=True,
            forward_requested=True,
            cross_track_error_world=1.25,
        )

        self.assertEqual(status, "REALIGN")
        self.assertIsNotNone(error)
        assert error is not None
        self.assertGreater(abs(error), 3.0)

    def test_initial_forward_direction_rejects_a_wall_slide_chord(self) -> None:
        status, error = assess_initial_forward_direction(
            expected_heading_rad=0.0,
            observed_heading_rad=1.57,
            displacement_world=1.60,
            physical_motion_continuous=True,
            forward_requested=True,
            cross_track_error_world=2.10,
        )

        self.assertEqual(status, "UNSAFE")
        self.assertIsNotNone(error)

    def test_initial_forward_direction_waits_for_a_real_forward_chord(self) -> None:
        status, error = assess_initial_forward_direction(
            expected_heading_rad=0.0,
            observed_heading_rad=0.0,
            displacement_world=0.60,
            physical_motion_continuous=False,
            forward_requested=True,
            cross_track_error_world=0.0,
        )

        self.assertEqual((status, error), ("WAIT", None))

    def test_direction_probe_keeps_cumulative_chord_length_from_estimator(self) -> None:
        estimator = DisplacementHeadingEstimator(minimum_displacement_world=1.25)
        estimator.reset(x=0.0, y=0.0)
        self.assertIsNone(estimator.observe(x=0.60, y=0.0))
        observed = estimator.observe(x=1.52, y=0.0)

        self.assertEqual(observed, 0.0)
        self.assertAlmostEqual(estimator.last_displacement_world, 1.52)
        status, _ = assess_initial_forward_direction(
            expected_heading_rad=3.12,
            observed_heading_rad=observed,
            displacement_world=estimator.last_displacement_world,
            physical_motion_continuous=True,
            forward_requested=True,
            cross_track_error_world=1.25,
        )
        self.assertEqual(status, "REALIGN")

    def test_initial_heading_reacquires_without_input_before_returning(self) -> None:
        class PoseSource:
            latest_facing_source = "UNAVAILABLE"

            def __init__(self) -> None:
                self._observations = [
                    {"position": {"x": 0.1, "y": 0.2}},
                    {"position": {"x": 0.1, "y": 0.2, "facing_rad": 1.25}},
                ]

            def next_observation(self):
                observation = self._observations.pop(0)
                if "facing_rad" in observation["position"]:
                    self.latest_facing_source = "COORDINATE_HUD_EXACT"
                return observation

        source = PoseSource()
        observer = Mock()
        observer.observe.return_value = (None, "UNAVAILABLE")
        with patch("run_navmesh_roaming.time.sleep") as sleep:
            observation, heading, heading_source, attempts = (
                _acquire_initial_visible_heading(
                    source,
                    observer,
                    observation=source.next_observation(),
                    predicted_heading_rad=None,
                )
            )

        self.assertEqual(observation["position"]["facing_rad"], 1.25)
        self.assertEqual((heading, heading_source, attempts), (1.25, "COORDINATE_HUD_EXACT", 2))
        sleep.assert_called_once()
        observer.observe.assert_called_once()

    def test_strict_initial_heading_waits_for_exact_hud_after_minimap_fallback(self) -> None:
        class PoseSource:
            latest_facing_source = "MINIMAP_VISION_FALLBACK"

            def __init__(self) -> None:
                self._observations = [
                    {"position": {"x": 0.1, "y": 0.2, "facing_rad": 0.40}},
                    {"position": {"x": 0.1, "y": 0.2, "facing_rad": 1.25}},
                ]

            def next_observation(self):
                observation = self._observations.pop(0)
                self.latest_facing_source = (
                    "COORDINATE_HUD_EXACT"
                    if observation["position"]["facing_rad"] == 1.25
                    else "MINIMAP_VISION_FALLBACK"
                )
                return observation

        source = PoseSource()
        observer = Mock()
        observer.observe.return_value = (0.40, "VISIBLE_CLIENT_HEADING_FUSED")
        with patch("run_navmesh_roaming.time.sleep") as sleep:
            observation, heading, heading_source, attempts = (
                _acquire_initial_visible_heading(
                    source,
                    observer,
                    observation=source.next_observation(),
                    predicted_heading_rad=None,
                    require_exact_body_heading=True,
                )
            )

        self.assertEqual(observation["position"]["facing_rad"], 1.25)
        self.assertEqual(
            (heading, heading_source, attempts),
            (1.25, "COORDINATE_HUD_EXACT", 2),
        )
        sleep.assert_called_once()

    def test_initial_heading_fails_closed_without_natural_stride(self) -> None:
        class PoseSource:
            latest_facing_source = "UNAVAILABLE"

            def next_observation(self):
                return {"position": {"x": 0.1, "y": 0.2}}

        observer = Mock()
        observer.observe.return_value = (None, "UNAVAILABLE")
        with patch("run_navmesh_roaming.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "refusing natural calibration stride"):
                _acquire_initial_visible_heading(
                    PoseSource(),
                    observer,
                    observation={"position": {"x": 0.1, "y": 0.2}},
                    predicted_heading_rad=None,
                    max_attempts=2,
                )
        self.assertEqual(observer.observe.call_count, 2)

    def test_post_plan_refresh_preserves_last_exact_heading_when_facing_temporarily_missing(self) -> None:
        class PoseSource:
            latest_facing_source = "UNAVAILABLE"

            def next_observation(self):
                return {"position": {"x": 0.1, "y": 0.2}}

        source = PoseSource()
        observer = Mock()
        observer.observe.return_value = (0.42, "MOUSE_INTEGRATED_MINIMAP_FALLBACK")

        observation, heading, heading_source, attempts = (
            _acquire_initial_visible_heading(
                source,
                observer,
                observation={"position": {"x": 0.1, "y": 0.2}},
                predicted_heading_rad=1.25,
                previous_heading_rad=1.25,
                previous_heading_source=EXACT_BODY_HEADING_SOURCE,
                preserve_previous_exact=True,
            )
        )

        self.assertEqual(observation["position"]["x"], 0.1)
        self.assertEqual((heading, heading_source, attempts), (
            1.25,
            PRESERVED_EXACT_BODY_HEADING_SOURCE,
            1,
        ))

    def test_post_plan_refresh_does_not_replace_exact_heading_with_minimap_fallback(self) -> None:
        class PoseSource:
            latest_facing_source = "MINIMAP_VISION_FALLBACK"

            def next_observation(self):
                return {
                    "position": {"x": 0.1, "y": 0.2, "facing_rad": 0.42}
                }

        source = PoseSource()
        observer = Mock()
        observer.observe.return_value = (0.42, "VISIBLE_CLIENT_HEADING_FUSED")

        observation, heading, heading_source, attempts = (
            _acquire_initial_visible_heading(
                source,
                observer,
                observation=source.next_observation(),
                predicted_heading_rad=1.25,
                previous_heading_rad=1.25,
                previous_heading_source=EXACT_BODY_HEADING_SOURCE,
                preserve_previous_exact=True,
            )
        )

        self.assertEqual(observation["position"]["facing_rad"], 0.42)
        self.assertEqual((heading, heading_source, attempts), (
            1.25,
            PRESERVED_EXACT_BODY_HEADING_SOURCE,
            1,
        ))
        observer.observe.assert_called_once()

    def test_preserved_exact_heading_requires_an_exact_previous_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "previous exact body heading"):
            _acquire_initial_visible_heading(
                SimpleNamespace(latest_facing_source="UNAVAILABLE"),
                Mock(),
                observation={"position": {"x": 0.1, "y": 0.2}},
                predicted_heading_rad=1.25,
                previous_heading_rad=1.25,
                previous_heading_source="MOUSE_INTEGRATED_MINIMAP_FALLBACK",
                preserve_previous_exact=True,
            )

    def test_post_plan_runner_enables_one_bounded_exact_heading_preservation(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        start = source.index("# Detour planning is bounded")
        end = source.index("if args.require_exact_body_heading:", start)
        post_plan = source[start:end]
        self.assertIn("previous_heading_source = heading_source", post_plan)
        self.assertIn(
            "previous_heading_source == EXACT_BODY_HEADING_SOURCE",
            post_plan,
        )
        self.assertIn(
            "require_exact_body_heading=args.require_exact_body_heading",
            post_plan,
        )
        self.assertIn("EXACT_HEADING_PRESERVED_AFTER_POST_PLAN_MISS", source)

    def test_initial_runner_passes_strict_heading_requirement_before_control(self) -> None:
        source = (
            RUNNER_PATH / "run_navmesh_roaming.py"
        ).read_text(encoding="utf-8")
        marker = "observation, heading, heading_source, heading_attempts = (\n            _acquire_initial_visible_heading("
        start = source.index(marker)
        end = source.index(")\n        )", start)
        initial_call = source[start:end]
        self.assertIn(
            "require_exact_body_heading=args.require_exact_body_heading",
            initial_call,
        )

    def test_strict_exact_heading_is_rechecked_before_each_motion_frame(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        start = source.index("heading_integrity = assess_heading_integrity(")
        end = source.index("navigation_frame = ContinuousMotionFrame(", start)
        control_gate = source[start:end]
        self.assertIn("if args.require_exact_body_heading:", control_gate)
        self.assertIn("_require_exact_body_heading(", control_gate)
        self.assertIn('status = "EXACT_BODY_HEADING_LOST"', control_gate)

    def test_normal_launchers_do_not_require_unavailable_exact_facing(self) -> None:
        supervisor = (
            RUNNER_PATH / "run_journey_combat_supervisor.py"
        ).read_text(encoding="utf-8")
        reviewed = (
            RUNNER_PATH / "run_reviewed_journey_route.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('"--require-exact-body-heading",', supervisor)
        self.assertNotIn('"--require-exact-body-heading",', reviewed)

    def test_live_pose_factory_keeps_actor_gate_explicit_and_diagnostic(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        factory_start = source.index("def _default_pose_source_factory(")
        factory_end = source.index("def _build_mission_steering(", factory_start)
        factory = source[factory_start:factory_end]
        self.assertIn("require_player_anchor: bool", factory)
        self.assertIn("require_player_anchor=require_player_anchor", factory)

        arm_start = source.index("arm_camera_gate = getattr(pose_source", factory_end)
        first_observation = source.index(
            "observation = pose_source.next_observation()", arm_start
        )
        self.assertLess(arm_start, first_observation)
        strict_branch = source.rfind("if args.require_player_anchor:", factory_end, arm_start)
        self.assertGreaterEqual(strict_branch, factory_end)
        self.assertIn("arm_camera_gate()", source[arm_start:first_observation])
        self.assertIn('"kind": "CAMERA_ACTOR_DIAGNOSTIC_ONLY"', source)

    def test_startup_camera_settle_requires_a_visible_streak_before_returning(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        visible_anchor = {
            "left": 0.48,
            "top": 0.50,
            "right": 0.54,
            "bottom": 0.72,
            "center_x": 0.51,
            "center_y": 0.61,
        }
        visible = {
            "tracking_state": "VISIBLE",
            "confidence": 0.92,
            "actor_anchor": visible_anchor,
        }
        lost = {
            "tracking_state": "LOST",
            "confidence": 0.0,
            "actor_anchor": None,
        }
        frames = iter(
            [
                {"tracking_state": "VALID", "frame": 1},
                {"tracking_state": "VALID", "frame": 2},
                {"tracking_state": "VALID", "frame": 3},
                {"tracking_state": "VALID", "frame": 4},
            ]
        )
        camera = iter([lost, visible, visible, visible])

        def next_frame() -> dict[str, object]:
            source._latest_camera_integrity = next(camera)
            return next(frames)

        source.next_observation = Mock(side_effect=next_frame)
        with patch("run_navmesh_roaming.time.sleep") as sleep:
            observed = source.wait_for_camera_integrity(
                max_attempts=CAMERA_STARTUP_SETTLE_ATTEMPTS,
                interval_s=CAMERA_STARTUP_SETTLE_INTERVAL_S,
                required_visible_frames=CAMERA_STARTUP_STABLE_VISIBLE_FRAMES,
            )

        self.assertEqual(observed["frame"], 4)
        self.assertEqual(source.last_camera_settle_attempts, 4)
        self.assertEqual(
            source.last_camera_settle_visible_frames,
            CAMERA_STARTUP_STABLE_VISIBLE_FRAMES,
        )
        self.assertEqual(sleep.call_count, 3)

    def test_startup_camera_settle_fails_closed_after_bound(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        source._latest_camera_integrity = {
            "tracking_state": "LOST",
            "confidence": 0.0,
            "actor_anchor": None,
        }
        source.next_observation = Mock(
            side_effect=lambda: {"tracking_state": "VALID"}
        )
        with patch("run_navmesh_roaming.time.sleep") as sleep:
            with self.assertRaises(ClientVisibleStateError):
                source.wait_for_camera_integrity(
                    max_attempts=3,
                    interval_s=0.01,
                    required_visible_frames=2,
                )

        self.assertEqual(source.next_observation.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(source.last_camera_settle_attempts, 3)
        self.assertEqual(source.last_camera_settle_visible_frames, 0)

    def test_bounded_calibration_does_not_override_fused_visible_heading(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        start = source.index("if calibration_heading_hold_frames > 0:")
        end = source.index("            if progress > 0.08:", start)
        block = source[start:end]
        self.assertIn('heading_source.startswith("VISIBLE_CLIENT_HEADING")', block)
        self.assertIn("never overwrite a fresh visual", block)
        self.assertIn("heading_before_visible_refresh", block)

    def test_native_topology_proof_uses_worldpack_slope_profile(self) -> None:
        source = (
            Path(__file__).parents[1] / "native" / "pa_nav_probe" / "main.cpp"
        ).read_text(encoding="utf-8")
        ground_candidate = source[
            source.index("bool ground_candidate(") :
            source.index("float polyline_length_2d(")
        ]

        self.assertIn('#include "Common.hpp"', source)
        self.assertIn("MeshSettings::WalkableSlope", source)
        self.assertIn("kMaximumWalkableSlopeRatio", ground_candidate)
        self.assertNotIn("horizontal * 0.70f", ground_candidate)

    def test_transient_visible_state_miss_releases_motion_then_reacquires(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        release = Mock()
        expected = {"tracking_state": "VALID"}
        transient = ClientVisibleStateError(
            VisibleClientStateObservation(
                state=VisibleClientState.UNKNOWN,
                confidence=0.0,
                evidence={"coordinate_hud_crc_valid": False},
            ),
            last_valid_pose=None,
        )
        source._on_capture_stall = release
        source._next_fresh_observation = Mock(
            side_effect=[transient, expected]
        )

        with patch("run_navmesh_roaming.time.sleep") as sleep:
            observed = source.next_observation()

        self.assertIs(observed, expected)
        release.assert_called_once_with()
        sleep.assert_called_once_with(VISIBLE_STATE_REACQUISITION_INTERVAL_S)
        self.assertEqual(source._next_fresh_observation.call_count, 2)
        self.assertIsNotNone(source.last_observation_latency_ms)

    def test_observation_latency_properties_are_recorded_for_live_forensics(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        source._next_fresh_observation = Mock(return_value={"tracking_state": "VALID"})

        observed = source.next_observation()

        self.assertEqual(observed["tracking_state"], "VALID")
        self.assertIsNotNone(source.last_observation_latency_ms)
        self.assertGreaterEqual(source.last_observation_latency_ms, 0.0)

    def test_slow_observation_releases_the_lease_without_extending_authority(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        release = Mock()
        source._on_capture_stall = release
        source._next_fresh_observation = Mock(return_value={"tracking_state": "VALID"})

        with patch(
            "run_navmesh_roaming.time.monotonic",
            side_effect=[10.0, 10.0 + (CONTINUOUS_LEASE_TIMEOUT_MS / 1000.0) + 0.01],
        ):
            source.next_observation()

        release.assert_called_once_with()
        self.assertGreater(
            source.last_observation_latency_ms,
            CONTINUOUS_LEASE_TIMEOUT_MS,
        )

    def test_visible_state_reacquisition_exhaustion_preserves_fail_closed_error(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        release = Mock()
        persistent = ClientVisibleStateError(
            VisibleClientStateObservation(
                state=VisibleClientState.LOGIN_SCREEN,
                confidence=0.95,
                evidence={"coordinate_hud_crc_valid": False},
            ),
            last_valid_pose={"tracking_state": "VALID"},
        )
        source._on_capture_stall = release
        source._next_fresh_observation = Mock(side_effect=persistent)

        with patch("run_navmesh_roaming.time.sleep") as sleep:
            with self.assertRaises(ClientVisibleStateError) as raised:
                source.next_observation()

        self.assertIs(raised.exception, persistent)
        self.assertEqual(
            source._next_fresh_observation.call_count,
            VISIBLE_STATE_REACQUISITION_ATTEMPTS,
        )
        self.assertEqual(release.call_count, VISIBLE_STATE_REACQUISITION_ATTEMPTS)
        self.assertEqual(
            sleep.call_count,
            VISIBLE_STATE_REACQUISITION_ATTEMPTS - 1,
        )

    def test_transient_combat_hud_detection_error_releases_motion_and_reacquires(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        release = Mock()
        expected = {"tracking_state": "VALID"}
        transient = CombatHudDetectionError(
            "marker foreground pixel budget exceeded"
        )
        source._on_capture_stall = release
        source._next_fresh_observation = Mock(
            side_effect=[transient, expected]
        )

        with patch("run_navmesh_roaming.time.sleep") as sleep:
            observed = source.next_observation()

        self.assertIs(observed, expected)
        release.assert_called_once_with()
        sleep.assert_called_once_with(VISIBLE_STATE_REACQUISITION_INTERVAL_S)
        self.assertEqual(source._next_fresh_observation.call_count, 2)

    def test_non_visual_pose_failure_is_not_retried(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        release = Mock()
        source._on_capture_stall = release
        source._next_fresh_observation = Mock(
            side_effect=RuntimeError("coordinate observation is stale")
        )

        with patch("run_navmesh_roaming.time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "observation is stale"):
                source.next_observation()

        release.assert_not_called()
        sleep.assert_not_called()
        source._next_fresh_observation.assert_called_once_with()

    def test_capture_stall_releases_input_before_one_bounded_restart(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        provider = Mock()
        packet = object()
        provider.next_frame.side_effect = (
            [NoFreshCaptureFrameError("stale")] * 3 + [packet]
        )
        release = Mock()
        source._provider = provider
        source._on_capture_stall = release
        source._capture_restart_count = 0
        source._verify_identity = Mock()

        with patch("run_navmesh_roaming.time.sleep"):
            observed = source._next_capture_packet()

        self.assertIs(observed, packet)
        release.assert_called_once_with()
        provider.close.assert_called_once_with()
        provider.open.assert_called_once_with()
        self.assertEqual(source.capture_restart_count, 1)

    def test_capture_deadline_spike_is_retried_before_restart(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        provider = Mock()
        packet = object()
        provider.next_frame.side_effect = (
            [CaptureDeadlineExceededError("busy compositor")] * 3 + [packet]
        )
        release = Mock()
        source._provider = provider
        source._on_capture_stall = release
        source._capture_restart_count = 0
        source._verify_identity = Mock()

        with patch("run_navmesh_roaming.time.sleep"):
            observed = source._next_capture_packet()

        self.assertIs(observed, packet)
        release.assert_called_once_with()
        provider.close.assert_called_once_with()
        provider.open.assert_called_once_with()
        self.assertEqual(source.capture_restart_count, 1)

    def test_navigation_capture_deadline_allows_one_bounded_compositor_frame(self) -> None:
        self.assertEqual(NAVIGATION_CAPTURE_DEADLINE_MS, 300.0)

    def test_bounded_blocker_union_deduplicates_and_keeps_nearest_eight(self) -> None:
        blockers = tuple(
            (float(index * 10), 0.0, 30.0, 1.5) for index in range(10)
        )
        selected = _bounded_blocker_union(
            blockers,
            ((50.5, 0.0, 30.2, 1.5),),
            origin_x=55.0,
            origin_y=0.0,
        )

        self.assertEqual(len(selected), 8)
        self.assertEqual(selected[0][0], 50.0)
        self.assertNotIn((50.5, 0.0, 30.2, 1.5), selected)

    def test_learned_blocker_containing_start_pose_is_suppressed_without_deleting_memory(self) -> None:
        retained, suppressed = _suppress_learned_blockers_containing_pose(
            (
                (0.5, 0.0, 20.1, 2.0),
                (8.0, 0.0, 20.0, 2.0),
                (0.0, 0.0, 40.0, 5.0),
            ),
            start_x=0.0,
            start_y=0.0,
            start_z=20.0,
        )

        self.assertEqual(suppressed, ((0.5, 0.0, 20.1, 2.0),))
        self.assertEqual(
            retained,
            ((8.0, 0.0, 20.0, 2.0), (0.0, 0.0, 40.0, 5.0)),
        )

    def test_undercity_visible_coordinate_maps_to_server_teleport(self) -> None:
        transform = tbc243_zone_transform(2, 26)
        world_x, world_y = transform.world_from_normalized(
            0.6581979095140001, 0.4571908140688182
        )
        self.assertAlmostEqual(world_x, 1585.25, delta=1.5)
        self.assertAlmostEqual(world_y, 241.65, delta=0.5)

    def test_world_and_normalized_round_trip(self) -> None:
        transform = tbc243_zone_transform(2, 26)
        normalized = transform.normalized_from_world(1693.43994140625, 424.1050109863281)
        restored = transform.world_from_normalized(*normalized)
        self.assertAlmostEqual(restored[0], 1693.43994140625, places=5)
        self.assertAlmostEqual(restored[1], 424.1050109863281, places=5)

    def test_unreviewed_zone_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            tbc243_zone_transform(2, 999)

    def test_stuck_recovery_is_bounded_and_alternates_lateral_clearance(self) -> None:
        engine = MovementEngine(
            navigator=Mock(), steering=Mock(),
            world=LayeredWorldModel(map_name="Azeroth", static_navmesh_sha256="A" * 64),
        )
        first = engine.recovery_maneuver(attempt=0)
        second = engine.recovery_maneuver(attempt=1)
        self.assertEqual(
            tuple(step.control for step in first.steps),
            ("JUMP", "MOVE_BACKWARD", "STRAFE_RIGHT"),
        )
        self.assertEqual(second.steps[2].control, "STRAFE_LEFT")
        with self.assertRaises(ValueError):
            engine.recovery_maneuver(attempt=2)

    def test_converging_pivot_does_not_become_a_false_collision(self) -> None:
        elapsed = 0.0
        anchor = None
        for error in (2.40, 2.29, 2.18, 2.07, 1.96, 1.85, 1.74, 1.63):
            elapsed, anchor = _update_pivot_stall_clock(
                elapsed_s=elapsed,
                anchor_error_rad=anchor,
                dt_s=0.5,
                controller_state="PIVOT",
                waypoint_error_rad=error,
            )
            self.assertEqual(elapsed, 0.0)
        self.assertAlmostEqual(anchor, 1.63)

    def test_non_converging_pivot_still_reaches_the_stall_budget(self) -> None:
        elapsed = 0.0
        anchor = None
        for _ in range(8):
            elapsed, anchor = _update_pivot_stall_clock(
                elapsed_s=elapsed,
                anchor_error_rad=anchor,
                dt_s=0.5,
                controller_state="PIVOT",
                waypoint_error_rad=2.0,
            )
        self.assertGreaterEqual(elapsed, PIVOT_STALL_TIMEOUT_S)
        elapsed, anchor = _update_pivot_stall_clock(
            elapsed_s=elapsed,
            anchor_error_rad=anchor,
            dt_s=0.5,
            controller_state="FOLLOW",
            waypoint_error_rad=0.2,
        )
        self.assertEqual((elapsed, anchor), (0.0, None))

    def test_local_clearance_commits_to_corner_before_next_leg(self) -> None:
        self.assertEqual(LOCAL_CLEARANCE_ARRIVAL_RADIUS_WORLD, 0.5)

    def test_collision_blocker_uses_physical_facing_before_commanded_path(self) -> None:
        intent = SteeringIntent(
            "REPLAN", 0, 0, NavPoint(0.0, 10.0, 1.0),
            "stuck_progress_gate",
        )

        blocked_heading = _collision_approach_heading(
            intent,
            world_x=0.0,
            world_y=0.0,
            observed_heading_rad=0.0,
            goal_x=10.0,
            goal_y=0.0,
        )

        self.assertAlmostEqual(blocked_heading, 0.0)

    def test_corridor_divergence_with_progress_is_not_collision_evidence(self) -> None:
        self.assertTrue(_replan_is_corridor_recenter_only(
            intent_reason="persistent_corridor_divergence",
            no_progress_s=0.19,
            collision_slide_s=0.0,
        ))

    def test_trajectory_loop_requests_clean_replan_without_fake_collision(self) -> None:
        self.assertTrue(_replan_is_corridor_recenter_only(
            intent_reason="trajectory_loop_detected",
            no_progress_s=0.0,
            collision_slide_s=0.0,
        ))

    def test_confined_forward_stall_realigns_without_learning_fake_blocker(self) -> None:
        self.assertTrue(_replan_is_corridor_recenter_only(
            intent_reason="confined_forward_stall_realign",
            no_progress_s=0.61,
            collision_slide_s=COLLISION_SLIDE_EVIDENCE_S,
        ))

    def test_stuck_or_sliding_divergence_keeps_collision_recovery(self) -> None:
        self.assertFalse(_replan_is_corridor_recenter_only(
            intent_reason="persistent_corridor_divergence",
            no_progress_s=STUCK_PROGRESS_EVIDENCE_S,
            collision_slide_s=0.0,
        ))
        self.assertFalse(_replan_is_corridor_recenter_only(
            intent_reason="persistent_corridor_divergence",
            no_progress_s=0.0,
            collision_slide_s=COLLISION_SLIDE_EVIDENCE_S,
        ))
        self.assertFalse(_replan_is_corridor_recenter_only(
            intent_reason="stuck_progress_gate",
            no_progress_s=STUCK_PROGRESS_EVIDENCE_S,
            collision_slide_s=0.0,
        ))

    def test_corridor_recenter_precedes_observed_collision_in_runner(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        recenter = source.index('"kind": "CORRIDOR_RECENTER_REPLAN"')
        collision = source.index('"kind": "OBSERVED_COLLISION_REPLAN"')
        self.assertLess(recenter, collision)
        recenter_branch_start = source.index(
            "if intent.state == \"REPLAN\" and"
        )
        recenter_branch_end = source.index(
            '\n            if intent.state == "REPLAN":',
            recenter_branch_start,
        )
        branch = source[
            recenter_branch_start:recenter_branch_end
        ]
        self.assertNotIn("engine.mark_stuck", branch)
        self.assertNotIn("learned_obstacle_memory.observe", branch)

    def test_confined_recenter_accumulates_physical_stall_evidence(self) -> None:
        first = _corridor_recenter_no_progress_evidence(
            intent_reason="confined_forward_stall_realign",
            no_progress_s=0.68,
            accumulated_confined_stall_s=0.0,
        )
        second = _corridor_recenter_no_progress_evidence(
            intent_reason="confined_forward_stall_realign",
            no_progress_s=0.68,
            accumulated_confined_stall_s=first,
        )
        third = _corridor_recenter_no_progress_evidence(
            intent_reason="confined_forward_stall_realign",
            no_progress_s=0.68,
            accumulated_confined_stall_s=second,
        )

        self.assertLess(first, STUCK_PROGRESS_EVIDENCE_S)
        self.assertLess(second, STUCK_PROGRESS_EVIDENCE_S)
        self.assertGreaterEqual(third, STUCK_PROGRESS_EVIDENCE_S)
        self.assertEqual(
            _corridor_recenter_no_progress_evidence(
                intent_reason="persistent_corridor_divergence",
                no_progress_s=0.25,
                accumulated_confined_stall_s=9.0,
            ),
            0.25,
        )

    def test_local_clearance_replans_keep_observed_blocker_in_all_legs(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        start = source.index("for side_anchor, pass_anchor in (")
        end = source.index(
            "                # Two independently validated sidesteps",
            start,
        )
        block = source[start:end]
        self.assertEqual(block.count("candidate_query.find_corridor("), 3)
        self.assertNotIn("side_corridor = query.find_corridor", block)
        self.assertNotIn("pass_corridor = query.find_corridor", block)
        self.assertNotIn("mission_probe = query.find_corridor", block)

    def test_initial_structure_horizon_is_refreshed_after_client_layer_selection(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        layer = source.index("current_z_hint = selected_initial_z")
        refresh = source.index(
            "_merge_static_structure_horizon_blockers(",
            layer,
        )
        initial_plan = source.index(
            "_plan_semantic_goal_or_forward_projection(",
            layer,
        )
        self.assertLess(refresh, initial_plan)
        self.assertIn(
            '"kind": "STATIC_STRUCTURE_BLOCKERS_REFRESHED_AFTER_LAYER"',
            source[refresh:initial_plan],
        )

    def test_navigation_camera_never_enables_smart_pivot(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        pivot_intent = source.index("def _apply_camera_pivot_intent")
        pivot_intent_end = source.index("def build_parser", pivot_intent)
        block = source[pivot_intent:pivot_intent_end]
        self.assertIn("smart_pivot=False", block)
        self.assertNotIn('smart_pivot=intent.mode == "WMO_NAV"', block)

    def test_normal_navigation_never_overwrites_operator_camera_view(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        startup = source[source.index("pose_source.open()"):source.index("if args.activate_stealth:")]
        self.assertNotIn("_apply_navigation_camera_profile(", startup)
        self.assertIn('"kind": "START_CAMERA_PREFERENCES_APPLIED"', startup)
        preserved = source.index('"kind": "TERMINAL_CAMERA_COMPOSITION_PRESERVED"')
        release = source.rfind("motion.release_all()", 0, preserved)
        terminal = source[release:preserved + 80]
        self.assertGreaterEqual(release, 0)
        self.assertNotIn('"kind": "TERMINAL_CAMERA_HOME_RESTORED"', source)
        self.assertIn('"kind": "TERMINAL_CAMERA_COMPOSITION_PRESERVED"', terminal)

    def test_partial_corridor_prioritizes_frontier_worker_over_next_goal_preplan(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        start = source.index("if (\n                _semantic_should_preplan(")
        end = source.index("            ):\n                next_goal", start)
        block = source[start:end]
        self.assertIn("and corridor.complete", block)
        self.assertIn("SEMANTIC_STATIC_FRONTIER_BYPASS_PREPLAN_STARTED", source)

    def test_frontier_preplan_has_a_dedicated_worker_pool(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "semantic_frontier_preplan_executor = ProcessPoolExecutor(\n"
            "        max_workers=1,",
            source,
        )
        frontier_start = source.index("frontier_preplan_needed = (")
        frontier_end = source.index("            local_sample = live_awareness.poll(", frontier_start)
        frontier_block = source[frontier_start:frontier_end]
        self.assertIn("semantic_frontier_preplan_executor.submit(", frontier_block)
        self.assertIn(
            "semantic_frontier_preplan_executor.shutdown(",
            source,
        )

    def test_frontier_result_is_materialized_before_awareness_and_handoff(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        materialize = source.index(
            '"kind": "SEMANTIC_STATIC_FRONTIER_BYPASS_RESULT_MATERIALIZED"'
        )
        awareness = source.index("local_sample = live_awareness.poll(", materialize)
        handoff = source.index("if frontier_handoff_matches:", materialize)
        self.assertLess(materialize, awareness)
        self.assertLess(materialize, handoff)
        self.assertIn("consume_ready_frontier_result_before_handoff", source)

    def test_frontier_handoff_does_not_index_empty_nonsemantic_goal_queue(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        handoff = source.index("if frontier_handoff_matches:")
        bypass = source.index(
            "if not fine_fallback_applied and semantic_goals:",
            handoff,
        )
        self.assertIn(
            "Normalized-coordinate and operator paths do not build a",
            source[bypass - 400:bypass],
        )
        self.assertIn("bypass_limit = semantic_goals[", source[bypass:])

    def test_process_pools_warm_before_pose_clock(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        warmup = source.index("_warm_process_pool(")
        pose_open = source.index("pose_source.open()")
        self.assertLess(warmup, pose_open)
        self.assertIn("ASYNC_WORKER_POOLS_WARMED", source)
        self.assertIn("_async_worker_pool_warmup", source)

    def test_warm_process_pool_rejects_invalid_bounds(self) -> None:
        with self.assertRaises(ValueError):
            _warm_process_pool(Mock(), pool_name="test", worker_count=0)
        with self.assertRaises(ValueError):
            _warm_process_pool(Mock(), pool_name="test", worker_count=1, timeout_s=0)

    def test_repeated_partial_replan_keeps_frontier_future_for_handoff(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        start = source.index("previous_frontier = corridor.stop")
        end = source.index("corridor = engine.plan(", start)
        repeated_replan_prefix = source[start:end]
        self.assertNotIn(
            "semantic_frontier_preplan_future.cancel()",
            repeated_replan_prefix,
        )
        self.assertIn(
            "Keep a worker result that was started from this exact",
            repeated_replan_prefix,
        )
        handoff = source.index("if frontier_handoff_matches:")
        handoff_end = source.index(
            "if not fine_fallback_applied and semantic_frontier_preplan_future is not None:",
            handoff,
        )
        self.assertIn(
            "semantic_frontier_preplan_future.done()",
            source[handoff:handoff_end],
        )

    def test_changed_frontier_clears_stale_frontier_future(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        handoff = source.index("if frontier_handoff_matches:")
        changed_frontier = source.index(
            "elif semantic_frontier_preplan_future is not None:",
            handoff,
        )
        changed_branch = source[changed_frontier:]
        self.assertIn(
            "A replan that moved to a different frontier cannot",
            changed_branch,
        )
        self.assertIn(
            "semantic_frontier_preplan_future.cancel()",
            changed_branch,
        )

    def test_primary_preplan_isolated_from_advisory_queries_and_reused_at_handoff(
        self,
    ) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "semantic_advisory_executor = ProcessPoolExecutor(\n"
            "        max_workers=2,",
            source,
        )
        wmo_start = source.index("semantic_advisory_executor.submit(")
        preplan_start = source.index(
            "semantic_preplan_future = semantic_preplan_executor.submit("
        )
        self.assertLess(wmo_start, preplan_start)
        handoff_start = source.index(
            "cached_continuation = (\n"
            "                            semantic_clearance_continuation_cache.pop("
        )
        handoff_end = source.index(
            "if prepared_waypoint_corridor is not None:", handoff_start
        )
        handoff_block = source[handoff_start:handoff_end]
        self.assertLess(
            handoff_block.index("semantic_clearance_continuation_cache.pop("),
            handoff_block.index("semantic_handoff_cache.pop("),
        )
        self.assertIn("semantic_preplan_future.done()", handoff_block)
        self.assertIn("SEMANTIC_CORRIDOR_PREPLAN_REUSED_", handoff_block)
        self.assertIn("semantic_advisory_executor.shutdown(", source)

    def test_movement_engine_preserves_an_exact_interior_floor_hint(self) -> None:
        navigator = Mock()
        expected = Mock()
        navigator.find_corridor.return_value = expected
        engine = MovementEngine(
            navigator=navigator,
            steering=Mock(),
            world=LayeredWorldModel(
                map_name="Shadowfang", static_navmesh_sha256="A" * 64,
            ),
        )

        result = engine.plan(
            start=NavPoint(-228.191, 2111.41, 76.8904),
            goal_x=-76.7541,
            goal_y=2152.41,
            goal_z=155.792,
        )

        self.assertIs(result, expected)
        navigator.find_corridor.assert_called_once_with(
            map_name="Shadowfang",
            start=NavPoint(-228.191, 2111.41, 76.8904),
            stop_x=-76.7541,
            stop_y=2152.41,
            stop_z=155.792,
        )

    @staticmethod
    def _inside_structure_awareness(
        *,
        map_name: str,
        structure_id: str,
        position: NavPoint,
        topology_complete: bool = True,
    ) -> LocalEnvironmentAwareness:
        return LocalEnvironmentAwareness(
            map_name=map_name,
            observed_monotonic_s=10.0,
            position=position,
            environment_state="INSIDE_STATIC_WMO",
            environment_confidence=0.95,
            physical_surfaces=frozenset({"wmo"}),
            topology_complete=topology_complete,
            containing_structures=(StructureContainmentEvidence(
                structure_id=structure_id,
                asset_path="world/wmo/fixture/interior.wmo",
                nav_coverage="FULL",
            ),),
            boundaries=(),
            verified_egresses=(),
            candidate_opening_bearings_rad=(),
            nearby_wmo_count=1,
            nearby_static_obstacle_count=0,
        )

    @staticmethod
    def _structure_access_graph(
        *,
        structure_id: str,
        opening: NavPoint,
        to_surfaces: tuple[str, ...] = ("ground",),
    ) -> StructureAccessSpatialGraph:
        return StructureAccessSpatialGraph({
            "access_openings": [{
                "opening_id": "access:portable-fixture-egress",
                "structure_ids": [structure_id],
                "midpoint": [opening.x, opening.y, opening.z],
                "connected_width_yards": 2.0,
                "from_surfaces": ["wmo"],
                "to_surfaces": list(to_surfaces),
                "opening_kind": "COVERED_TO_OPEN_ROUTE_VERIFIED",
                "execution_authority": False,
            }],
        })

    def test_structure_egress_is_revalidated_before_it_becomes_a_subgoal(self) -> None:
        for map_name, structure_id in (
            ("PortableContinent", "7:wmo:101"),
            ("PortableDungeon", "33:wmo:202"),
        ):
            with self.subTest(map_name=map_name):
                start = NavPoint(0.0, 0.0, 5.0)
                opening = NavPoint(10.0, 0.0, 5.0)
                destination = NavPoint(100.0, 0.0, 5.0)
                direct = NavCorridor(
                    map_name, 0, 0, start, NavPoint(2.0, 0.0, 5.0),
                    (start, NavPoint(2.0, 0.0, 5.0)),
                    complete=False, requested_stop=destination,
                )
                approach = NavCorridor(
                    map_name, 0, 0, start, opening, (start, opening),
                )
                continuation = NavCorridor(
                    map_name, 0, 0, opening, destination,
                    (opening, destination),
                )
                navigator = Mock()
                navigator.find_corridor.side_effect = (approach, continuation)
                engine = MovementEngine(
                    navigator=navigator,
                    steering=Mock(),
                    world=LayeredWorldModel(
                        map_name=map_name, static_navmesh_sha256="A" * 64,
                    ),
                    structure_access=self._structure_access_graph(
                        structure_id=structure_id,
                        opening=opening,
                        to_surfaces=(
                            ("wmo",)
                            if map_name == "PortableDungeon"
                            else ("ground",)
                        ),
                    ),
                )

                proposal = engine.plan_via_known_structure_egress(
                    awareness=self._inside_structure_awareness(
                        map_name=map_name,
                        structure_id=structure_id,
                        position=start,
                    ),
                    direct_corridor=direct,
                    goal_x=destination.x,
                    goal_y=destination.y,
                    goal_z=destination.z,
                )

                self.assertIsNotNone(proposal)
                assert proposal is not None
                self.assertEqual(proposal.structure_id, structure_id)
                self.assertEqual(proposal.opening, opening)
                self.assertIs(proposal.approach, approach)
                self.assertIs(proposal.continuation, continuation)
                self.assertEqual(navigator.find_corridor.call_count, 2)

    def test_unreachable_structure_opening_is_not_used(self) -> None:
        map_name = "PortableMap"
        structure_id = "1:wmo:9"
        start = NavPoint(0.0, 0.0, 5.0)
        opening = NavPoint(10.0, 0.0, 5.0)
        destination = NavPoint(100.0, 0.0, 5.0)
        direct = NavCorridor(
            map_name, 0, 0, start, NavPoint(2.0, 0.0, 5.0),
            (start, NavPoint(2.0, 0.0, 5.0)),
            complete=False, requested_stop=destination,
        )
        unreachable = NavCorridor(
            map_name, 0, 0, start, NavPoint(5.0, 0.0, 5.0),
            (start, NavPoint(5.0, 0.0, 5.0)),
            complete=False, requested_stop=opening,
        )
        navigator = Mock()
        navigator.find_corridor.return_value = unreachable
        engine = MovementEngine(
            navigator=navigator,
            steering=Mock(),
            world=LayeredWorldModel(
                map_name=map_name, static_navmesh_sha256="A" * 64,
            ),
            structure_access=self._structure_access_graph(
                structure_id=structure_id, opening=opening,
            ),
        )

        proposal = engine.plan_via_known_structure_egress(
            awareness=self._inside_structure_awareness(
                map_name=map_name, structure_id=structure_id, position=start,
            ),
            direct_corridor=direct,
            goal_x=destination.x,
            goal_y=destination.y,
            goal_z=destination.z,
        )

        self.assertIsNone(proposal)
        navigator.find_corridor.assert_called_once()

    def test_complete_direct_route_never_detours_via_structure_graph(self) -> None:
        start = NavPoint(0.0, 0.0, 5.0)
        destination = NavPoint(100.0, 0.0, 5.0)
        navigator = Mock()
        engine = MovementEngine(
            navigator=navigator,
            steering=Mock(),
            world=LayeredWorldModel(
                map_name="PortableMap", static_navmesh_sha256="A" * 64,
            ),
            structure_access=self._structure_access_graph(
                structure_id="1:wmo:9", opening=NavPoint(10.0, 0.0, 5.0),
            ),
        )
        direct = NavCorridor(
            "PortableMap", 0, 0, start, destination, (start, destination),
        )

        proposal = engine.plan_via_known_structure_egress(
            awareness=self._inside_structure_awareness(
                map_name="PortableMap",
                structure_id="1:wmo:9",
                position=start,
            ),
            direct_corridor=direct,
            goal_x=destination.x,
            goal_y=destination.y,
            goal_z=destination.z,
        )

        self.assertIsNone(proposal)
        navigator.find_corridor.assert_not_called()

    def test_complete_cross_boundary_chord_uses_verified_structure_exit(self) -> None:
        map_name = "PortableMap"
        structure_id = "1:wmo:9"
        start = NavPoint(0.0, 0.0, 5.0)
        opening = NavPoint(10.0, 0.0, 5.0)
        destination = NavPoint(100.0, 0.0, 5.0)
        direct = NavCorridor(
            map_name, 0, 0, start, destination, (start, destination),
        )
        approach = NavCorridor(
            map_name, 0, 0, start, opening, (start, opening),
        )
        continuation = NavCorridor(
            map_name, 0, 0, opening, destination, (opening, destination),
        )
        navigator = Mock()
        navigator.find_corridor.side_effect = (approach, continuation)
        structures = WorldStructureSpatialIndex((WorldStructure(
            structure_id=structure_id,
            kind="WMO",
            instance_id=9,
            asset_path="world/wmo/fixture/interior.wmo",
            asset_tokens=("world", "wmo", "fixture", "interior"),
            bounds=AxisAlignedBounds(
                Vector3(-20.0, -20.0, 0.0),
                Vector3(20.0, 20.0, 20.0),
            ),
            center=Vector3(0.0, 0.0, 10.0),
            horizontal_radius_yards=28.3,
            collision_role="ENCLOSURE_OR_LARGE_STRUCTURE",
            nav_coverage="FULL",
        ),))
        engine = MovementEngine(
            navigator=navigator,
            steering=Mock(),
            world=LayeredWorldModel(
                map_name=map_name, static_navmesh_sha256="A" * 64,
            ),
            structures=structures,
            structure_access=self._structure_access_graph(
                structure_id=structure_id, opening=opening,
            ),
        )

        proposal = engine.plan_via_known_structure_egress(
            awareness=self._inside_structure_awareness(
                map_name=map_name,
                structure_id=structure_id,
                position=start,
                topology_complete=False,
            ),
            direct_corridor=direct,
            goal_x=destination.x,
            goal_y=destination.y,
            goal_z=destination.z,
        )

        self.assertIsNotNone(proposal)
        assert proposal is not None
        self.assertEqual(proposal.opening, opening)
        self.assertIs(proposal.approach, approach)
        self.assertIs(proposal.continuation, continuation)

    def test_structure_egress_uses_optional_scoped_navigator(self) -> None:
        map_name = "PortableMap"
        structure_id = "1:wmo:9"
        start = NavPoint(0.0, 0.0, 5.0)
        opening = NavPoint(10.0, 0.0, 5.0)
        destination = NavPoint(100.0, 0.0, 5.0)
        direct = NavCorridor(
            map_name, 0, 0, start, destination, (start, destination),
        )
        approach = NavCorridor(
            map_name, 0, 0, start, opening, (start, opening),
        )
        continuation = NavCorridor(
            map_name, 0, 0, opening, destination, (opening, destination),
        )

        class ScopedNavigator:
            surface_evidence_available = False

            def __init__(self) -> None:
                self._responses = iter((approach, continuation))
                self.scopes: list[tuple[float, ...]] = []

            def for_structure_egress(
                self,
                *,
                bounds: tuple[float, float, float, float, float, float],
            ) -> ScopedNavigator:
                self.scopes.append(bounds)
                return self

            def find_corridor(self, **_: object) -> NavCorridor:
                return next(self._responses)

        navigator = ScopedNavigator()
        structures = WorldStructureSpatialIndex((WorldStructure(
            structure_id=structure_id,
            kind="WMO",
            instance_id=9,
            asset_path="world/wmo/fixture/interior.wmo",
            asset_tokens=("world", "wmo", "fixture", "interior"),
            bounds=AxisAlignedBounds(
                Vector3(-20.0, -20.0, 0.0),
                Vector3(20.0, 20.0, 20.0),
            ),
            center=Vector3(0.0, 0.0, 10.0),
            horizontal_radius_yards=28.3,
            collision_role="ENCLOSURE_OR_LARGE_STRUCTURE",
            nav_coverage="FULL",
        ),))
        engine = MovementEngine(
            navigator=navigator,
            steering=Mock(),
            world=LayeredWorldModel(
                map_name=map_name, static_navmesh_sha256="A" * 64,
            ),
            structures=structures,
            structure_access=self._structure_access_graph(
                structure_id=structure_id, opening=opening,
            ),
        )

        proposal = engine.plan_via_known_structure_egress(
            awareness=self._inside_structure_awareness(
                map_name=map_name, structure_id=structure_id, position=start,
            ),
            direct_corridor=direct,
            goal_x=destination.x,
            goal_y=destination.y,
            goal_z=destination.z,
        )

        self.assertIsNotNone(proposal)
        self.assertEqual(
            navigator.scopes,
            [(-20.0, -20.0, 0.0, 20.0, 20.0, 20.0)],
        )

    def test_complete_goal_inside_same_structure_keeps_direct_corridor(self) -> None:
        map_name = "PortableMap"
        structure_id = "1:wmo:9"
        start = NavPoint(0.0, 0.0, 5.0)
        destination = NavPoint(15.0, 0.0, 5.0)
        navigator = Mock()
        structures = WorldStructureSpatialIndex((WorldStructure(
            structure_id=structure_id,
            kind="WMO",
            instance_id=9,
            asset_path="world/wmo/fixture/interior.wmo",
            asset_tokens=("world", "wmo", "fixture", "interior"),
            bounds=AxisAlignedBounds(
                Vector3(-20.0, -20.0, 0.0),
                Vector3(20.0, 20.0, 20.0),
            ),
            center=Vector3(0.0, 0.0, 10.0),
            horizontal_radius_yards=28.3,
            collision_role="ENCLOSURE_OR_LARGE_STRUCTURE",
            nav_coverage="FULL",
        ),))
        engine = MovementEngine(
            navigator=navigator,
            steering=Mock(),
            world=LayeredWorldModel(
                map_name=map_name, static_navmesh_sha256="A" * 64,
            ),
            structures=structures,
            structure_access=self._structure_access_graph(
                structure_id=structure_id,
                opening=NavPoint(10.0, 0.0, 5.0),
            ),
        )
        direct = NavCorridor(
            map_name, 0, 0, start, destination, (start, destination),
        )

        proposal = engine.plan_via_known_structure_egress(
            awareness=self._inside_structure_awareness(
                map_name=map_name,
                structure_id=structure_id,
                position=start,
            ),
            direct_corridor=direct,
            goal_x=destination.x,
            goal_y=destination.y,
            goal_z=destination.z,
        )

        self.assertIsNone(proposal)
        navigator.find_corridor.assert_not_called()

    def test_verified_structure_egress_can_handoff_without_a_stop_pulse(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        start = source.index(
            "structure_egress_continuation is not None",
        )
        stop = source.index(
            "if _semantic_should_fly_by(",
            start,
        )
        handoff = source[start:stop]

        self.assertIn('"kind": "STRUCTURE_EGRESS_FLYBY"', handoff)
        self.assertIn("corridor = prepared_continuation", handoff)
        self.assertIn("_semantic_handoff_is_continuous", handoff)
        self.assertNotIn("motion.release_all", handoff)

    def test_partial_semantic_handoff_keeps_frontier_for_local_bypass(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        marker = '"kind": "SEMANTIC_FRONTIER_REPLAN_REQUIRED"'
        start = source.index(marker)
        stop = source.index("observation = pose_source.next_observation()", start)
        frontier_block = source[start:stop]

        self.assertIn("Keep the bounded partial corridor alive", frontier_block)
        self.assertNotIn('status = "SEMANTIC_FRONTIER_REPLAN_REQUIRED"', frontier_block)
        self.assertNotIn("break", frontier_block)

    def test_route_static_structure_blockers_include_map_doodad_on_next_horizon(self) -> None:
        def structure(structure_id: str, x: float, y: float) -> WorldStructure:
            return WorldStructure(
                structure_id=structure_id,
                kind="DOODAD",
                instance_id=1,
                asset_path="world/generic/human/passive doodads/signposts/stonesignpost01.mdx",
                asset_tokens=("world", "generic", "human", "signpost"),
                bounds=AxisAlignedBounds(
                    Vector3(x - 1.0, y - 1.0, 83.0),
                    Vector3(x + 1.0, y + 1.0, 86.0),
                ),
                center=Vector3(x, y, 84.5),
                horizontal_radius_yards=1.28,
                collision_role="STATIC_OBSTACLE_CANDIDATE",
                nav_coverage="NONE",
            )

        structures = WorldStructureSpatialIndex((
            structure("on_route", 15.0, 0.0),
            structure("off_route", 15.0, 20.0),
        ))
        blockers = _route_static_structure_blockers(
            structures=structures,
            start=NavPoint(0.0, 0.0, 84.0),
            goals=(RoadWorldPoint(30.0, 0.0),),
        )

        self.assertEqual(len(blockers), 1)
        self.assertAlmostEqual(blockers[0][0], 15.0)
        self.assertAlmostEqual(blockers[0][1], 0.0)
        self.assertGreaterEqual(blockers[0][3], 1.25)

    def test_route_static_structure_blockers_use_bounds_for_elongated_prop(self) -> None:
        tree = WorldStructure(
            structure_id="elongated_tree",
            kind="DOODAD",
            instance_id=1,
            asset_path="world/lordaeron/tirisfalglade/passivedoodads/trees/tree.mdx",
            asset_tokens=("world", "tree"),
            bounds=AxisAlignedBounds(
                Vector3(-5.0, 0.0, 80.0), Vector3(40.0, 5.0, 90.0)
            ),
            center=Vector3(17.5, 2.5, 85.0),
            horizontal_radius_yards=31.0,
            collision_role="STATIC_OBSTACLE_CANDIDATE",
            nav_coverage="FULL",
        )

        blockers = _route_static_structure_blockers(
            structures=WorldStructureSpatialIndex((tree,)),
            start=NavPoint(0.0, 60.0, 85.0),
            goals=(RoadWorldPoint(30.0, 60.0),),
        )

        self.assertEqual(blockers, ())

    def test_route_static_structure_blockers_narrow_broad_prop_disc_to_footprint(self) -> None:
        outpost = WorldStructure(
            structure_id="broad_outpost",
            kind="DOODAD",
            instance_id=1,
            asset_path="world/generic/outpost.mdx",
            asset_tokens=("world", "outpost"),
            bounds=AxisAlignedBounds(
                Vector3(-42.0, -17.0, 50.0), Vector3(42.0, 17.0, 80.0)
            ),
            center=Vector3(0.0, 0.0, 65.0),
            horizontal_radius_yards=45.0,
            collision_role="STATIC_OBSTACLE_CANDIDATE",
            nav_coverage="FULL",
        )

        blockers = _route_static_structure_blockers(
            structures=WorldStructureSpatialIndex((outpost,)),
            start=NavPoint(-60.0, 18.0, 65.0),
            goals=(RoadWorldPoint(60.0, 18.0),),
        )

        self.assertEqual(len(blockers), 1)
        # A bounded fraction of the narrow y half-extent is used instead of a
        # 30-yard circumscribed disc that would block the road outside it.  The
        # nav worker applies actor clearance independently.
        self.assertAlmostEqual(blockers[0][0], 0.0)
        self.assertAlmostEqual(blockers[0][1], 0.0)
        self.assertLessEqual(blockers[0][3], 15.5)

    def test_route_static_structure_blockers_narrow_moderate_tree_disc(self) -> None:
        tree = WorldStructure(
            structure_id="moderate_tree",
            kind="DOODAD",
            instance_id=1,
            asset_path="world/lordaeron/tirisfalglade/passivedoodads/trees/tree.mdx",
            asset_tokens=("world", "tree"),
            bounds=AxisAlignedBounds(
                Vector3(-9.0, -6.0, 78.0), Vector3(9.0, 6.0, 100.0)
            ),
            center=Vector3(0.0, 0.0, 89.0),
            horizontal_radius_yards=10.82,
            collision_role="STATIC_OBSTACLE_CANDIDATE",
            nav_coverage="FULL",
        )

        blockers = _route_static_structure_blockers(
            structures=WorldStructureSpatialIndex((tree,)),
            start=NavPoint(-1.0, 8.0, 89.0),
            goals=(RoadWorldPoint(24.0, 0.0),),
        )

        self.assertEqual(len(blockers), 1)
        # The local footprint (not the circumscribed tree radius) keeps the
        # road cell just outside the measured bounds open.
        self.assertLess(blockers[0][3], 8.0)

    def test_route_static_structure_blockers_include_wmo_corner_on_horizon(self) -> None:
        house = WorldStructure(
            structure_id="wmo_house",
            kind="WMO",
            instance_id=1,
            asset_path="world/wmo/azeroth/buildings/house.wmo",
            asset_tokens=("world", "wmo", "house"),
            bounds=AxisAlignedBounds(
                Vector3(18.0, -10.0, 80.0), Vector3(42.0, 18.0, 105.0)
            ),
            center=Vector3(30.0, 4.0, 92.5),
            horizontal_radius_yards=18.0,
            collision_role="ENCLOSURE_OR_LARGE_STRUCTURE",
            nav_coverage="FULL",
        )

        blockers = _route_static_structure_blockers(
            structures=WorldStructureSpatialIndex((house,)),
            start=NavPoint(0.0, 20.0, 84.0),
            goals=(RoadWorldPoint(50.0, 20.0),),
        )

        self.assertEqual(len(blockers), 1)
        self.assertAlmostEqual(blockers[0][0], 30.0)
        self.assertAlmostEqual(blockers[0][1], 4.0)
        self.assertLess(
            blockers[0][3],
            house.horizontal_radius_yards,
            "a WMO circumscribed disc must not seal the road outside its AABB",
        )

    def test_route_static_structure_blockers_skip_wmo_containing_route_start(self) -> None:
        crypt = WorldStructure(
            structure_id="wmo_crypt",
            kind="WMO",
            instance_id=1,
            asset_path="world/wmo/dungeon/crypt.wmo",
            asset_tokens=("world", "wmo", "crypt"),
            bounds=AxisAlignedBounds(
                Vector3(-10.0, -10.0, 80.0), Vector3(10.0, 10.0, 105.0)
            ),
            center=Vector3(0.0, 0.0, 92.5),
            horizontal_radius_yards=14.2,
            collision_role="ENCLOSURE_OR_LARGE_STRUCTURE",
            nav_coverage="FULL",
        )

        blockers = _route_static_structure_blockers(
            structures=WorldStructureSpatialIndex((crypt,)),
            start=NavPoint(0.0, 0.0, 92.0),
            goals=(RoadWorldPoint(30.0, 0.0),),
        )

        self.assertEqual(blockers, ())

    def test_semantic_goal_inside_broad_prop_is_rejected_but_outside_sample_is_allowed(self) -> None:
        outpost = WorldStructure(
            structure_id="broad_outpost_goal",
            kind="DOODAD",
            instance_id=1,
            asset_path="world/generic/outpost.mdx",
            asset_tokens=("world", "outpost"),
            bounds=AxisAlignedBounds(
                Vector3(-42.0, -17.0, 50.0), Vector3(42.0, 17.0, 80.0)
            ),
            center=Vector3(0.0, 0.0, 65.0),
            horizontal_radius_yards=45.0,
            collision_role="STATIC_OBSTACLE_CANDIDATE",
            nav_coverage="FULL",
        )
        structures = WorldStructureSpatialIndex((outpost,))

        self.assertTrue(
            _semantic_goal_overlaps_static_structure(
                structures=structures,
                goal=RoadWorldPoint(20.0, 10.0),
                z=65.0,
            )
        )
        self.assertFalse(
            _semantic_goal_overlaps_static_structure(
                structures=structures,
                goal=RoadWorldPoint(20.0, 19.0),
                z=65.0,
            )
        )

    def test_static_structure_horizon_merges_late_prop_without_route_wide_scan(self) -> None:
        cart = WorldStructure(
            structure_id="cart",
            kind="DOODAD",
            instance_id=1,
            asset_path="world/azeroth/karazahn/passivedoodads/brokencart/kn_brokencart.mdx",
            asset_tokens=("world", "azeroth", "karazahn", "brokencart"),
            bounds=AxisAlignedBounds(
                Vector3(8.0, -2.0, 78.0), Vector3(12.0, 2.0, 82.0)
            ),
            center=Vector3(10.0, 0.0, 80.0),
            horizontal_radius_yards=3.0,
            collision_role="STATIC_OBSTACLE_CANDIDATE",
            nav_coverage="FULL",
        )
        merged, added = _merge_static_structure_horizon_blockers(
            structures=WorldStructureSpatialIndex((cart,)),
            observed_blockers=(),
            start=NavPoint(0.0, 0.0, 80.0),
            goals=(RoadWorldPoint(20.0, 0.0),),
        )

        self.assertEqual(len(added), 1)
        self.assertAlmostEqual(merged[0][0], 10.0)

    def test_static_structure_clearance_uses_navmesh_validated_anchors(self) -> None:
        cart = WorldStructure(
            structure_id="static_cart",
            kind="DOODAD",
            instance_id=1,
            asset_path="world/generic/cart.mdx",
            asset_tokens=("world", "cart"),
            bounds=AxisAlignedBounds(
                Vector3(4.0, -1.0, -1.0), Vector3(6.0, 1.0, 1.0)
            ),
            center=Vector3(5.0, 0.0, 0.0),
            horizontal_radius_yards=1.5,
            collision_role="STATIC_OBSTACLE_CANDIDATE",
            nav_coverage="FULL",
        )

        class SyntheticQuery:
            def find_corridor(
                self, *, map_name, start, stop_x, stop_y, stop_z=None,
            ):
                stop = NavPoint(stop_x, stop_y, stop_z)
                # The negative-Y side is a synthetic wall; the positive side
                # is the only navmesh-proven clearance route.
                if start.y < -0.1 or stop.y < -0.1:
                    reached = NavPoint(start.x, start.y, start.z)
                    return NavCorridor(
                        map_name, 0, 0, start, reached, (start, reached),
                        complete=False, requested_stop=stop,
                    )
                return NavCorridor(
                    map_name, 0, 0, start, stop, (start, stop),
                    complete=True, requested_stop=stop,
                )

        goals, actions = _inject_static_structure_clearance_priors(
            structures=WorldStructureSpatialIndex((cart,)),
            route_start=RoadWorldPoint(0.0, 0.0),
            start_z=0.0,
            goals=(RoadWorldPoint(10.0, 0.0),),
            query=SyntheticQuery(),
            map_name="Azeroth",
        )

        self.assertEqual(len(goals), 3)
        self.assertGreater(goals[0].y, 0.0)
        self.assertGreater(goals[1].y, 0.0)
        self.assertEqual(goals[-1], RoadWorldPoint(10.0, 0.0))
        self.assertEqual(actions[0]["kind"], "STATIC_STRUCTURE_CLEARANCE_APPLIED")

    def test_traversable_wmo_baseline_removes_new_exclusion(self) -> None:
        bridge = WorldStructure(
            structure_id="covered_bridge",
            kind="WMO",
            instance_id=1,
            asset_path="world/wmo/coveredbridge.wmo",
            asset_tokens=("world", "wmo", "coveredbridge"),
            bounds=AxisAlignedBounds(
                Vector3(-20.0, -30.0, 0.0), Vector3(20.0, 30.0, 40.0)
            ),
            center=Vector3(0.0, 0.0, 20.0),
            horizontal_radius_yards=30.0,
            collision_role="ENCLOSURE_OR_LARGE_STRUCTURE",
            nav_coverage="FULL",
        )
        candidate = (0.0, 0.0, 20.0, 30.0)

        class SyntheticQuery:
            def find_corridor(
                self, *, map_name, start, stop_x, stop_y, stop_z=None,
            ):
                stop = NavPoint(stop_x, stop_y, stop_z or start.z)
                return NavCorridor(
                    map_name, 0, 0, start, stop, (start, stop),
                    complete=True, requested_stop=stop,
                )

        retained, added, actions = _filter_traversable_wmo_horizon_blockers(
            structures=WorldStructureSpatialIndex((bridge,)),
            horizon_blockers=(candidate,),
            added_blockers=(candidate,),
            query_factory=lambda blockers: SyntheticQuery(),
            map_name="Azeroth",
            start=NavPoint(-5.0, 0.0, 20.0),
            goal=RoadWorldPoint(5.0, 0.0),
            current_waypoint_index=1,
            next_waypoint_index=2,
            local_goal_radius=3.0,
        )

        self.assertEqual(retained, ())
        self.assertEqual(added, ())
        self.assertEqual(actions[0]["kind"], "SEMANTIC_HORIZON_WMO_BASELINE_PASS")

    @patch("run_navmesh_roaming.ClientAssetNavmeshQuery")
    def test_wmo_baseline_worker_returns_only_complete_local_corridor(
        self, query_type: Mock,
    ) -> None:
        start = NavPoint(0.0, 0.0, 20.0)
        stop = NavPoint(5.0, 0.0, 20.0)
        query_type.return_value.find_corridor.return_value = NavCorridor(
            "Azeroth", 0, 0, start, stop, (start, stop),
            complete=True, requested_stop=stop,
        )

        passed = _wmo_baseline_reaches_local_goal_in_worker_process(
            worker_path="worker.exe",
            nav_root_path="nav",
            observed_blockers=((1.0, 1.0, 20.0, 2.0),),
            map_name="Azeroth",
            start=start,
            stop_x=stop.x,
            stop_y=stop.y,
            local_goal_radius=3.0,
        )

        self.assertTrue(passed)
        query_type.assert_called_once()
        query_type.return_value.find_corridor.assert_called_once_with(
            map_name="Azeroth",
            start=start,
            stop_x=stop.x,
            stop_y=stop.y,
        )

    def test_proven_wmo_is_suppressed_only_for_same_semantic_handoff(self) -> None:
        candidate = (10.0, 20.0, 30.0, 4.0)
        horizon, added = _suppress_proven_wmo_horizon_blockers(
            horizon_blockers=(candidate,),
            added_blockers=(candidate,),
            proven_for_goal={(candidate, 4)},
            next_waypoint_index=4,
        )
        self.assertEqual(horizon, ())
        self.assertEqual(added, ())

        horizon, added = _suppress_proven_wmo_horizon_blockers(
            horizon_blockers=(candidate,),
            added_blockers=(candidate,),
            proven_for_goal={(candidate, 4)},
            next_waypoint_index=5,
        )
        self.assertEqual(horizon, (candidate,))
        self.assertEqual(added, (candidate,))

    def test_segment_aabb_distance_rejects_elongated_canopy_near_route(self) -> None:
        distance = _segment_aabb_distance_2d(
            RoadWorldPoint(0.0, 60.0),
            RoadWorldPoint(25.0, 60.0),
            minimum_x=-5.0,
            minimum_y=0.0,
            maximum_x=40.0,
            maximum_y=5.0,
        )

        self.assertAlmostEqual(distance, 55.0)

    def test_runtime_record_exposes_collision_and_detour_awareness_separately(self) -> None:
        start = NavPoint(10.0, 20.0, 30.0)
        awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"ground"}),
            probe_radius_yards=12.0,
            overhead_clear=True,
            radial_probes=tuple(
                RadialClearanceProbe(
                    index * tau / 16,
                    12.0,
                    index < 13,
                )
                for index in range(16)
            ),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28, start, NavPoint(20.0, 20.0, 30.0),
            (start, NavPoint(20.0, 20.0, 30.0)),
            start_awareness=awareness,
        )

        record = _local_static_awareness_record(corridor)

        self.assertEqual(record["environment_class"], "OPEN_GROUND")
        self.assertEqual(record["collision_clear_count"], 16)
        self.assertEqual(record["detour_confirmed_opening_count"], 13)
        self.assertIs(record["execution_authority"], False)

    def test_initial_layer_prefers_matching_enclosed_surface_over_short_exterior_chord(self) -> None:
        start = NavPoint(10.0, 10.0, 100.0)
        goal = NavPoint(20.0, 10.0, 100.0)
        enclosed = LocalStaticAwareness(
            physical_surfaces=frozenset({"wmo"}),
            probe_radius_yards=12.0,
            overhead_clear=False,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 3.0, False)
                for index in range(16)
            ),
        )
        exterior = LocalStaticAwareness(
            physical_surfaces=frozenset({"ground"}),
            probe_radius_yards=12.0,
            overhead_clear=True,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 12.0, True)
                for index in range(16)
            ),
        )
        enclosed_corridor = NavCorridor(
            "PortableMap", 0, 0, NavPoint(10.0, 10.0, 121.0),
            NavPoint(15.0, 10.0, 121.0),
            (NavPoint(10.0, 10.0, 121.0), NavPoint(15.0, 10.0, 121.0)),
            height_candidate_count=2,
            complete=False,
            requested_stop=goal,
            start_awareness=enclosed,
        )
        exterior_corridor = NavCorridor(
            "PortableMap", 0, 0, NavPoint(10.0, 10.0, 138.0), goal,
            (NavPoint(10.0, 10.0, 138.0), goal),
            height_candidate_count=2,
            start_awareness=exterior,
        )

        class LayerProbe:
            def plan(self, *, start: NavPoint, goal_x: float, goal_y: float) -> NavCorridor:
                return enclosed_corridor if start.z < 130.0 else exterior_corridor

        selected_z, _, evidence = _select_initial_vertical_layer(
            LayerProbe(),
            start_x=start.x,
            start_y=start.y,
            seed_z=100.0,
            goal_x=goal.x,
            goal_y=goal.y,
        )

        self.assertEqual(selected_z, 121.0)
        self.assertEqual(len(evidence), 2)
        self.assertEqual(evidence[0]["resolved_z"], 121.0)

    def test_initial_layer_skips_a_guessed_height_with_no_polygon(self) -> None:
        start = NavPoint(10.0, 10.0, 100.0)
        goal = NavPoint(20.0, 10.0, 100.0)
        enclosed = NavCorridor(
            "PortableMap", 0, 0, NavPoint(10.0, 10.0, 121.0),
            NavPoint(15.0, 10.0, 121.0),
            (NavPoint(10.0, 10.0, 121.0), NavPoint(15.0, 10.0, 121.0)),
            height_candidate_count=1,
            complete=False,
            requested_stop=goal,
            start_awareness=LocalStaticAwareness(
                physical_surfaces=frozenset({"wmo"}),
                probe_radius_yards=12.0,
                overhead_clear=False,
                radial_probes=tuple(
                    RadialClearanceProbe(index * tau / 8, 3.0, False)
                    for index in range(8)
                ),
            ),
        )

        class LayerProbe:
            def __init__(self) -> None:
                self.calls = 0

            def plan(self, *, start: NavPoint, goal_x: float, goal_y: float) -> NavCorridor:
                self.calls += 1
                if self.calls == 1:
                    raise ClientNavmeshError("corridor endpoint has no polygon")
                return enclosed

        probe = LayerProbe()
        selected_z, _, evidence = _select_initial_vertical_layer(
            probe,
            start_x=start.x,
            start_y=start.y,
            seed_z=100.0,
            goal_x=goal.x,
            goal_y=goal.y,
        )

        self.assertEqual(selected_z, 121.0)
        self.assertEqual(probe.calls, 2)
        self.assertEqual(len(evidence), 1)

    def test_runtime_record_distinguishes_verified_egress_from_raw_transition(self) -> None:
        start = NavPoint(10.0, 20.0, 30.0)
        egress = LocalTopologicalEgressPortal(
            NavPoint(16.0, 20.0, 42.0), NavPoint(16.0, 24.0, 42.0),
            4.0, 6.0, 64.6, False, True,
            frozenset({"wmo"}), frozenset({"ground"}),
        )
        awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"wmo"}),
            probe_radius_yards=12.0,
            overhead_clear=False,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 4.0, False)
                for index in range(16)
            ),
            component_polygon_count=20,
            egress_portals=(egress,),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28, start, NavPoint(20.0, 20.0, 30.0),
            (start, NavPoint(20.0, 20.0, 30.0)),
            start_awareness=awareness,
        )

        record = _local_static_awareness_record(corridor)

        self.assertEqual(record["environment_class"], "WMO_STRUCTURE_WITH_EGRESS")
        self.assertTrue(record["egress_inference_complete"])
        self.assertEqual(record["egress_portals"][0]["route_distance_yards"], 64.6)
        self.assertTrue(record["egress_portals"][0]["route_verified"])

    def test_runtime_record_marks_stalled_wmo_frontier_as_non_executable(self) -> None:
        start = NavPoint(-187.20, 2139.88, 83.23)
        awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"wmo"}),
            probe_radius_yards=12.0,
            overhead_clear=False,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 4.0, False)
                for index in range(16)
            ),
            component_polygon_count=126,
            wall_segments=(LocalWallSegment(
                NavPoint(-186.0, 2138.0, 83.2),
                NavPoint(-186.0, 2142.0, 83.2),
                1.2,
            ),),
        )
        corridor = NavCorridor(
            "Shadowfang", 27, 31, start, start, (start,),
            complete=False,
            requested_stop=NavPoint(-76.75, 2152.41, 155.71),
            start_awareness=awareness,
        )

        record = _local_static_awareness_record(corridor)
        conditional = record["conditional_traversal_frontier"]

        self.assertEqual(
            conditional["kind"],
            "POSSIBLE_WMO_DOOR_GATE_OR_FLOOR_TRANSITION",
        )
        self.assertTrue(conditional["requires_live_visible_confirmation"])
        self.assertFalse(conditional["execution_authority"])

    def test_resume_heading_uses_displacement_then_retained_mouse_turns(self) -> None:
        record = {
            "record_type": "navmesh_roaming_result",
            "final_world": [2.0, 1.0],
            "actions": [
                {"kind": "FORWARD", "world_x": 0.0, "world_y": 0.0, "progress_world": 1.0},
                {"kind": "FORWARD", "world_x": 2.0, "world_y": 0.0, "progress_world": 2.0},
                {"kind": "MOUSE_TURN", "delta_x": -14},
                {"kind": "FORWARD", "world_x": 2.0, "world_y": 1.0, "progress_world": 0.1},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resume.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            position, heading = _resume_heading(path)
        self.assertEqual(position, (2.0, 1.0))
        self.assertAlmostEqual(heading, 0.0364, places=6)

    def test_resume_heading_accepts_continuous_navigation_frames(self) -> None:
        record = {
            "record_type": "navmesh_roaming_result",
            "final_world": [1.0, 1.0],
            "actions": [
                {
                    "kind": "CONTINUOUS_FRAME",
                    "world_x": 0.0,
                    "world_y": 0.0,
                    "progress_world": 0.2,
                },
                {
                    "kind": "CONTINUOUS_FRAME",
                    "world_x": 1.0,
                    "world_y": 1.0,
                    "progress_world": 1.4,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resume-continuous.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            position, heading = _resume_heading(path)
        self.assertEqual(position, (1.0, 1.0))
        self.assertAlmostEqual(heading, 0.7853981633974483, places=6)

    def test_resume_position_accepts_stuck_result_without_heading_evidence(self) -> None:
        record = {
            "record_type": "navmesh_roaming_result",
            "final_world": [3.0, 4.0],
            "actions": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stuck.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(_resume_position(path), (3.0, 4.0))

    def test_resume_preserves_topology_derived_navmesh_height(self) -> None:
        record = {
            "record_type": "navmesh_roaming_result",
            "final_world": [3.0, 4.0],
            "final_world_z_hint": 132.625,
            "actions": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stair-resume.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(_resume_z_hint(path, fallback=100.0), 132.625)

    def test_latest_calibration_skips_newer_rejected_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proven = root / "single-forward-pulse-proven.json"
            rejected = root / "single-forward-pulse-rejected.json"
            proven.write_text(
                json.dumps({"status": "PROVEN_DISPLACEMENT"}),
                encoding="utf-8",
            )
            rejected.write_text(
                json.dumps({"status": "OBSERVATION_REJECTED"}),
                encoding="utf-8",
            )
            os.utime(proven, (1_000, 1_000))
            os.utime(rejected, (2_000, 2_000))

            self.assertEqual(_latest_calibration(root), proven)

    def test_semantic_destination_is_bound_to_exact_client_atlas_coordinates(self) -> None:
        catalog = {
            "record_type": "semantic_location_catalog",
            "schema_version": "1.0",
            "map_name": "Azeroth",
            "zone_index": 25,
            "coordinate_system": "tbc243_client_world_xy",
            "atlas_calibration": "WorldMapArea.dbc:Tirisfal",
            "locations": [{
                "id": "settlement:brill", "name": "Brill",
                "world": [2259.25, 290.43], "arrival_radius_yards": 45.0,
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.json"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            destination = _load_semantic_destination(
                path, destination_id="settlement:brill", expected_zone_index=25,
            )
            self.assertEqual(destination, (2259.25, 290.43, 45.0, "Brill"))
            catalog["atlas_calibration"] = "approximate_overlay"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "exact client atlas"):
                _load_semantic_destination(
                    path, destination_id="settlement:brill", expected_zone_index=25,
                )

    def test_semantic_destination_can_resolve_non_tirisfal_client_transform(self) -> None:
        catalog = {
            "record_type": "semantic_location_catalog",
            "schema_version": "1.0",
            "map_name": "Kalimdor",
            "zone_index": 14,
            "coordinate_system": "tbc243_client_world_xy",
            "atlas_calibration": "WorldMapArea.dbc:Durotar",
            "locations": [{
                "id": "settlement:orgrimmar",
                "name": "Orgrimmar",
                "world": [-5000.0, 1000.0],
                "arrival_radius_yards": 35.0,
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kalimdor-locations.json"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            transform = _load_zone_transform(
                Path(__file__).parents[1]
                / "config/pose/world-map-zone-transforms-tbc243-8606.json",
                map_id=1,
                zone_index=14,
            )
            self.assertEqual(transform.internal_name, "Durotar")
            destination = _load_semantic_destination(
                path,
                destination_id="settlement:orgrimmar",
                expected_zone_index=14,
                expected_map_name="Kalimdor",
                expected_map_id=1,
            )
        self.assertEqual(destination, (-5000.0, 1000.0, 35.0, "Orgrimmar"))

    def test_operator_journey_rejoins_nearest_point_and_keeps_order(self) -> None:
        journey = OperatorAuthoredPath(
            "operator:deathknell-brill", "Deathknell to Brill", "Azeroth",
        )
        journey = journey.add(x=0.0, y=0.0).add(x=10.0, y=0.0).add(x=20.0, y=0.0)

        start_index, goals = _operator_goal_queue(
            journey, start_x=7.0, start_y=4.0,
        )

        self.assertEqual(start_index, 1)
        self.assertEqual(
            goals, (RoadWorldPoint(10.0, 0.0), RoadWorldPoint(20.0, 0.0)),
        )

    def test_operator_journey_loader_rejects_other_map_and_empty_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "operator-path.json"
            empty = OperatorAuthoredPath("empty", "Empty", "Azeroth")
            path.write_text(json.dumps(empty.to_record()), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "no waypoints"):
                _load_operator_path_journey(path)

            other = OperatorAuthoredPath("other", "Other", "Kalimdor").add(
                x=1.0, y=2.0,
            )
            path.write_text(json.dumps(other.to_record()), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "another client map"):
                _load_operator_path_journey(path)

    def test_semantic_queue_is_generated_and_ends_at_exact_destination(self) -> None:
        route = SemanticRoadRoute(
            RoadWorldPoint(10.0, 20.0), RoadWorldPoint(40.0, 50.0),
            RoadWorldPoint(10.0, 20.0), RoadWorldPoint(39.0, 49.0),
            (
                RoadWorldPoint(10.0, 20.0),
                RoadWorldPoint(25.0, 35.0),
                RoadWorldPoint(39.0, 49.0),
            ),
            12, 1, 2, 15,
        )
        planner = Mock()
        planner.plan.return_value = route
        planned, goals = _semantic_goal_queue(
            planner=planner, start_x=10.0, start_y=20.0,
            destination_x=40.0, destination_y=50.0,
        )
        self.assertIs(planned, route)
        self.assertEqual(
            goals,
            (
                RoadWorldPoint(39.0, 49.0),
                RoadWorldPoint(40.0, 50.0),
            ),
        )

    def test_semantic_queue_accepts_a_preselected_risk_aware_variant(self) -> None:
        route = SemanticRoadRoute(
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(40.0, 0.0),
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(36.0, 0.0),
            (
                RoadWorldPoint(0.0, 0.0),
                RoadWorldPoint(18.0, 4.0),
                RoadWorldPoint(36.0, 0.0),
            ),
            2, 1, 0, 3,
            profile_id="balanced",
        )
        planner = Mock()

        planned, goals = _semantic_goal_queue(
            planner=planner,
            start_x=0.0,
            start_y=0.0,
            destination_x=40.0,
            destination_y=0.0,
            route=route,
        )

        planner.plan.assert_not_called()
        self.assertIs(planned, route)
        self.assertEqual(goals[-1], RoadWorldPoint(40.0, 0.0))

    def test_semantic_queue_coalesces_nearby_texture_cells_before_detour(self) -> None:
        route = SemanticRoadRoute(
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(100.0, 0.0),
            RoadWorldPoint(2.0, 0.0), RoadWorldPoint(95.0, 0.0),
            (
                RoadWorldPoint(2.0, 0.0),
                RoadWorldPoint(14.0, 0.0),
                RoadWorldPoint(28.0, 0.0),
                RoadWorldPoint(42.0, 0.0),
                RoadWorldPoint(70.0, 0.0),
                RoadWorldPoint(95.0, 0.0),
            ),
            20, 2, 0, 22,
        )
        planner = Mock()
        planner.plan.return_value = route
        _, goals = _semantic_goal_queue(
            planner=planner, start_x=0.0, start_y=0.0,
            destination_x=100.0, destination_y=0.0,
        )
        self.assertEqual(
            goals,
            (
                RoadWorldPoint(28.0, 0.0),
                RoadWorldPoint(70.0, 0.0),
                RoadWorldPoint(95.0, 0.0),
                RoadWorldPoint(100.0, 0.0),
            ),
        )

    def test_semantic_queue_keeps_gentle_road_curve_inside_one_yard_band(self) -> None:
        route = SemanticRoadRoute(
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(48.0, 9.0),
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(48.0, 9.0),
            (
                RoadWorldPoint(0.0, 0.0),
                RoadWorldPoint(12.0, 0.0),
                RoadWorldPoint(24.0, 1.5),
                RoadWorldPoint(36.0, 4.5),
                RoadWorldPoint(48.0, 9.0),
            ),
            5, 0, 0, 5,
        )
        planner = Mock()
        planner.plan.return_value = route

        _, goals = _semantic_goal_queue(
            planner=planner, start_x=0.0, start_y=0.0,
            destination_x=48.0, destination_y=9.0,
        )

        self.assertEqual(
            goals,
            (RoadWorldPoint(36.0, 4.5), RoadWorldPoint(48.0, 9.0)),
        )

    def test_confirmed_obstacle_outside_actor_route_tube_does_not_steer(self) -> None:
        obstacle = LearnedObstacle(
            obstacle_id="obstacle:bridgeclearance",
            map_name="SyntheticWorld",
            zone_index=77,
            x=10.0, y=3.1, z=5.0, radius=1.5, observations=2,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-02T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )
        query = Mock()

        goals, evidence = _inject_confirmed_clearance_priors(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(20.0, 0.0),),
            obstacles=(obstacle,),
            query=query,
            map_name="SyntheticWorld",
        )

        self.assertEqual(goals, (RoadWorldPoint(20.0, 0.0),))
        self.assertEqual(evidence, ())
        query.find_corridor.assert_not_called()

    def test_confirmed_clearance_prior_on_nearby_upper_layer_does_not_seal_start(self) -> None:
        obstacle = LearnedObstacle(
            obstacle_id="obstacle:upper-crypt-floor",
            map_name="SyntheticWorld",
            zone_index=77,
            x=4.0, y=1.0, z=18.0, radius=2.0, observations=2,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-02T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )
        query = Mock()

        goals, evidence = _inject_confirmed_clearance_priors(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(20.0, 0.0),),
            obstacles=(obstacle,),
            query=query,
            map_name="SyntheticWorld",
            route_start_z=0.0,
        )

        self.assertEqual(goals, (RoadWorldPoint(20.0, 0.0),))
        self.assertEqual(
            evidence[0]["kind"],
            "CONFIRMED_CLEARANCE_PRIOR_SKIPPED_VERTICAL_LAYER",
        )
        self.assertEqual(evidence[0]["obstacle_id"], obstacle.obstacle_id)
        query.find_corridor.assert_not_called()

    def test_confirmed_clearance_prior_caches_validated_resume_corridor(self) -> None:
        obstacle = LearnedObstacle(
            obstacle_id="obstacle:cache-resume",
            map_name="SyntheticWorld",
            zone_index=77,
            x=10.0, y=0.0, z=5.0, radius=1.5, observations=2,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-02T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )

        class CompleteQuery:
            def find_corridor(
                self, *, map_name, start, stop_x, stop_y, stop_z=None,
            ):
                stop = NavPoint(stop_x, stop_y, stop_z)
                return NavCorridor(
                    map_name, 0, 0, start, stop, (start, stop),
                )

        cache: dict[tuple[float, float, float, float], NavCorridor] = {}
        goals, evidence = _inject_confirmed_clearance_priors(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(20.0, 0.0),),
            obstacles=(obstacle,),
            query=CompleteQuery(),
            map_name="SyntheticWorld",
            continuation_cache=cache,
        )

        self.assertEqual(len(goals), 3)
        self.assertEqual(evidence[0]["kind"], "CONFIRMED_CLEARANCE_PRIOR_APPLIED")
        self.assertEqual(len(cache), 1)
        key, continuation = next(iter(cache.items()))
        self.assertAlmostEqual(key[2], 20.0)
        self.assertAlmostEqual(key[3], 0.0)
        self.assertTrue(continuation.complete)
        self.assertGreaterEqual(len(continuation.guidance_points()), 2)

    def test_semantic_queue_keeps_corner_before_detour_chord_cuts_inside(self) -> None:
        route = SemanticRoadRoute(
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(40.0, 24.0),
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(36.0, 24.0),
            (
                RoadWorldPoint(0.0, 0.0),
                RoadWorldPoint(12.0, 0.0),
                RoadWorldPoint(24.0, 0.0),
                RoadWorldPoint(24.0, 12.0),
                RoadWorldPoint(24.0, 24.0),
                RoadWorldPoint(36.0, 24.0),
            ),
            6, 0, 0, 6,
        )
        planner = Mock()
        planner.plan.return_value = route

        _, goals = _semantic_goal_queue(
            planner=planner, start_x=0.0, start_y=0.0,
            destination_x=40.0, destination_y=24.0,
        )

        self.assertIn(RoadWorldPoint(24.0, 0.0), goals)
        self.assertIn(RoadWorldPoint(24.0, 24.0), goals)
        self.assertLessEqual(
            _point_segment_distance_2d(
                RoadWorldPoint(24.0, 12.0),
                RoadWorldPoint(24.0, 0.0),
                RoadWorldPoint(24.0, 24.0),
            ),
            0.01,
        )

    def test_long_local_corridor_refines_when_it_leaves_semantic_surface(self) -> None:
        fine = tuple(
            RoadWorldPoint(0.0, float(y))
            for y in (0.0, 12.0, 24.0, 36.0, 48.0)
        )
        route = SemanticRoadRoute(
            fine[0], fine[-1], fine[0], fine[-1], fine, 5, 0, 0, 5,
        )
        corridor = NavCorridor(
            "SyntheticWorld", 1, 1,
            NavPoint(0.0, 0.0, 5.0), NavPoint(0.0, 48.0, 5.0),
            (
                NavPoint(0.0, 0.0, 5.0),
                NavPoint(18.0, 18.0, 5.0),
                NavPoint(0.0, 48.0, 5.0),
            ),
            requested_stop=NavPoint(0.0, 48.0, 5.0),
        )

        refinement = _semantic_corridor_refinement(
            route=route,
            corridor=corridor,
            start_x=0.0,
            start_y=0.0,
            target_x=0.0,
            target_y=48.0,
        )

        self.assertIsNotNone(refinement)
        assert refinement is not None
        self.assertEqual(refinement[0], 2)
        self.assertEqual(refinement[1], RoadWorldPoint(0.0, 24.0))
        self.assertGreater(refinement[2], 4.0)

        speculative = _semantic_refinement_midpoint(
            route=route,
            start_x=0.0,
            start_y=0.0,
            target_x=0.0,
            target_y=48.0,
        )
        self.assertEqual(speculative, refinement[:2])

    def test_long_local_corridor_keeps_full_straight_walkable_surface(self) -> None:
        fine = tuple(
            RoadWorldPoint(0.0, float(y))
            for y in (0.0, 12.0, 24.0, 36.0, 48.0)
        )
        route = SemanticRoadRoute(
            fine[0], fine[-1], fine[0], fine[-1], fine, 5, 0, 0, 5,
        )
        corridor = NavCorridor(
            "SyntheticWorld", 1, 1,
            NavPoint(0.0, 0.0, 5.0), NavPoint(0.0, 48.0, 5.0),
            (
                NavPoint(0.0, 0.0, 5.0),
                NavPoint(2.5, 24.0, 5.0),
                NavPoint(0.0, 48.0, 5.0),
            ),
            requested_stop=NavPoint(0.0, 48.0, 5.0),
        )

        self.assertIsNone(_semantic_corridor_refinement(
            route=route,
            corridor=corridor,
            start_x=0.0,
            start_y=0.0,
            target_x=0.0,
            target_y=48.0,
        ))

    def test_partial_coarse_horizon_can_fall_back_to_ordered_fine_cells(self) -> None:
        route = SemanticRoadRoute(
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(40.0, 0.0),
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(40.0, 0.0),
            tuple(RoadWorldPoint(float(x), 0.0) for x in range(0, 41, 4)),
            11, 0, 0, 11,
        )

        candidates = _semantic_fallback_candidates(
            route=route,
            start_x=17.0,
            start_y=0.0,
            target_x=36.0,
            target_y=0.0,
            minimum_route_index=3,
        )

        self.assertEqual(candidates[0], (5, RoadWorldPoint(20.0, 0.0)))
        self.assertEqual(candidates[-1], (9, RoadWorldPoint(36.0, 0.0)))
        self.assertEqual(tuple(index for index, _ in candidates), tuple(range(5, 10)))

    def test_unreachable_road_sample_probes_forward_to_next_coarse_horizon(self) -> None:
        route = SemanticRoadRoute(
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(60.0, 0.0),
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(60.0, 0.0),
            tuple(RoadWorldPoint(float(x), 0.0) for x in range(0, 61, 4)),
            16, 0, 0, 16,
        )

        candidates = _semantic_forward_bypass_candidates(
            route=route,
            start_x=22.0,
            start_y=0.0,
            blocked_target_x=24.0,
            blocked_target_y=0.0,
            limit_x=40.0,
            limit_y=0.0,
            minimum_route_index=4,
        )

        self.assertEqual(candidates[0], (7, RoadWorldPoint(28.0, 0.0)))
        self.assertEqual(candidates[-1], (10, RoadWorldPoint(40.0, 0.0)))
        self.assertTrue(all(index > 6 for index, _ in candidates))

    def test_static_frontier_bypass_can_extend_past_covered_coarse_goal(self) -> None:
        route = SemanticRoadRoute(
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(80.0, 0.0),
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(80.0, 0.0),
            tuple(RoadWorldPoint(float(x), 0.0) for x in range(0, 81, 4)),
            21, 0, 0, 21,
        )

        candidates = _semantic_forward_bypass_candidates(
            route=route,
            start_x=22.0,
            start_y=0.0,
            blocked_target_x=24.0,
            blocked_target_y=0.0,
            limit_x=28.0,
            limit_y=0.0,
            minimum_route_index=4,
            maximum_forward_waypoints=4,
        )

        self.assertEqual(
            tuple(index for index, _ in candidates), tuple(range(7, 12)),
        )
        self.assertEqual(candidates[-1], (11, RoadWorldPoint(44.0, 0.0)))

    def test_static_frontier_bypass_bound_is_rejected_outside_reviewed_range(self) -> None:
        route = SemanticRoadRoute(
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(20.0, 0.0),
            RoadWorldPoint(0.0, 0.0), RoadWorldPoint(20.0, 0.0),
            tuple(RoadWorldPoint(float(x), 0.0) for x in range(0, 21, 4)),
            6, 0, 0, 6,
        )
        with self.assertRaises(ValueError):
            _semantic_forward_bypass_candidates(
                route=route,
                start_x=0.0,
                start_y=0.0,
                blocked_target_x=4.0,
                blocked_target_y=0.0,
                limit_x=8.0,
                limit_y=0.0,
                maximum_forward_waypoints=33,
            )

    @patch("run_navmesh_roaming.ClientAssetNavmeshQuery")
    def test_static_frontier_worker_returns_first_navmesh_validated_route_cell(
        self, query_type: Mock,
    ) -> None:
        valid = NavCorridor(
            "Azeroth", 30, 28,
            NavPoint(10.0, 0.0, 4.0), NavPoint(18.0, 0.0, 4.0),
            (NavPoint(10.0, 0.0, 4.0), NavPoint(18.0, 0.0, 4.0)),
            requested_stop=NavPoint(18.0, 0.0, 4.0),
        )
        query = query_type.return_value
        query.find_corridor.side_effect = [RuntimeError("partial"), valid]

        result = _semantic_forward_bypass_in_worker_process(
            worker_path="worker.exe",
            nav_root_path="nav",
            observed_blockers=(),
            map_name="Azeroth",
            start=NavPoint(10.0, 0.0, 4.0),
            candidates=((7, 14.0, 0.0), (9, 18.0, 0.0)),
            local_goal_radius=3.0,
        )

        self.assertEqual(result, (9, valid))
        self.assertEqual(query.find_corridor.call_count, 2)

    @patch("run_navmesh_roaming.ClientAssetNavmeshQuery")
    def test_static_frontier_worker_returns_fast_path_without_speculative_tail(
        self, query_type: Mock,
    ) -> None:
        valid = NavCorridor(
            "Azeroth", 30, 28,
            NavPoint(10.0, 0.0, 4.0), NavPoint(14.0, 0.0, 4.0),
            (NavPoint(10.0, 0.0, 4.0), NavPoint(14.0, 0.0, 4.0)),
            requested_stop=NavPoint(14.0, 0.0, 4.0),
        )
        query = query_type.return_value
        query.find_corridor.return_value = valid

        result = _semantic_forward_bypass_in_worker_process(
            worker_path="worker.exe",
            nav_root_path="nav",
            observed_blockers=(),
            map_name="Azeroth",
            start=NavPoint(10.0, 0.0, 4.0),
            candidates=((7, 14.0, 0.0), (9, 18.0, 0.0)),
            local_goal_radius=3.0,
        )

        self.assertEqual(result, (7, valid))
        self.assertEqual(query.find_corridor.call_count, 1)

    def test_static_frontier_worker_rejects_unbounded_candidate_batch(self) -> None:
        with self.assertRaises(ValueError):
            _semantic_forward_bypass_in_worker_process(
                worker_path="worker.exe",
                nav_root_path="nav",
                observed_blockers=(),
                map_name="Azeroth",
                start=NavPoint(10.0, 0.0, 4.0),
                candidates=tuple((index, float(index), 0.0) for index in range(33)),
                local_goal_radius=3.0,
            )

    def test_static_frontier_worker_fanout_matches_measured_bounded_batch(self) -> None:
        self.assertEqual(SEMANTIC_STATIC_FRONTIER_WORKER_QUERY_CONCURRENCY, 10)
        self.assertLessEqual(
            SEMANTIC_STATIC_FRONTIER_WORKER_QUERY_CONCURRENCY,
            32,
        )

    @patch("run_navmesh_roaming.ClientAssetNavmeshQuery")
    def test_static_frontier_worker_accepts_inclusive_coarse_horizon_batch(
        self, query_type: Mock,
    ) -> None:
        valid = NavCorridor(
            "Azeroth", 30, 28,
            NavPoint(10.0, 0.0, 4.0), NavPoint(42.0, 0.0, 4.0),
            (NavPoint(10.0, 0.0, 4.0), NavPoint(42.0, 0.0, 4.0)),
            requested_stop=NavPoint(42.0, 0.0, 4.0),
        )
        query = query_type.return_value

        def find_corridor(*, stop_x: float, **_: object) -> NavCorridor:
            if stop_x == 42.0:
                return valid
            raise RuntimeError("partial")

        query.find_corridor.side_effect = find_corridor
        candidates = tuple((index, float(10 + index * 4), 0.0) for index in range(9))

        result = _semantic_forward_bypass_in_worker_process(
            worker_path="worker.exe",
            nav_root_path="nav",
            observed_blockers=(),
            map_name="Azeroth",
            start=NavPoint(10.0, 0.0, 4.0),
            candidates=candidates,
            local_goal_radius=3.0,
        )

        self.assertEqual(result, (8, valid))
        self.assertEqual(query.find_corridor.call_count, 9)

    def test_semantic_horizon_preplans_then_flies_by_without_chasing_point_behind(self) -> None:
        self.assertFalse(_semantic_should_preplan(remaining_world=35.01, has_next=True))
        self.assertTrue(_semantic_should_preplan(remaining_world=35.0, has_next=True))
        self.assertFalse(_semantic_should_preplan(remaining_world=5.0, has_next=False))
        self.assertTrue(_semantic_should_preplan(
            remaining_world=120.0, has_next=True, radius_world=140.0,
        ))
        self.assertFalse(_semantic_should_fly_by(
            remaining_world=3.0, has_next=True, next_corridor_ready=False,
        ))
        self.assertTrue(_semantic_should_fly_by(
            remaining_world=3.0, has_next=True, next_corridor_ready=True,
        ))
        self.assertFalse(_semantic_should_fly_by(
            remaining_world=3.01, has_next=True, next_corridor_ready=True,
        ))

    def test_semantic_handoff_requires_forward_heading_and_local_corridor_contact(self) -> None:
        corridor = NavCorridor(
            "Azeroth", 30, 28,
            NavPoint(10.0, 0.0, 4.0), NavPoint(30.0, 0.0, 4.0),
            (NavPoint(10.0, 0.0, 4.0), NavPoint(30.0, 0.0, 4.0)),
        )

        self.assertTrue(_semantic_handoff_is_continuous(
            corridor, world_x=9.0, world_y=0.5, heading_rad=0.0,
        ))
        self.assertFalse(_semantic_handoff_is_continuous(
            corridor, world_x=9.0, world_y=0.5, heading_rad=3.14159,
        ))
        self.assertFalse(_semantic_handoff_is_continuous(
            corridor, world_x=9.0, world_y=8.0, heading_rad=0.0,
        ))

    def test_semantic_handoff_rejects_cached_corridor_that_starts_behind_goal(self) -> None:
        corridor = NavCorridor(
            "Azeroth", 30, 28,
            NavPoint(10.0, 0.0, 4.0), NavPoint(30.0, 0.0, 4.0),
            (
                NavPoint(10.0, 0.0, 4.0),
                NavPoint(0.0, 0.0, 4.0),
                NavPoint(30.0, 0.0, 4.0),
            ),
        )

        divergence = _semantic_corridor_goal_divergence(
            corridor,
            world_x=10.0,
            world_y=0.0,
            goal_x=30.0,
            goal_y=0.0,
        )

        self.assertIsNotNone(divergence)
        assert divergence is not None
        self.assertAlmostEqual(divergence[0], 3.141592653589793)
        self.assertFalse(_semantic_cached_corridor_advances_toward_goal(
            corridor,
            world_x=10.0,
            world_y=0.0,
            goal_x=30.0,
            goal_y=0.0,
        ))

    def test_semantic_handoff_allows_cached_clearance_arc_toward_goal(self) -> None:
        corridor = NavCorridor(
            "Azeroth", 30, 28,
            NavPoint(10.0, 0.0, 4.0), NavPoint(30.0, 0.0, 4.0),
            (
                NavPoint(10.0, 0.0, 4.0),
                NavPoint(14.0, 5.0, 4.0),
                NavPoint(30.0, 0.0, 4.0),
            ),
        )

        self.assertTrue(_semantic_cached_corridor_advances_toward_goal(
            corridor,
            world_x=10.0,
            world_y=0.0,
            goal_x=30.0,
            goal_y=0.0,
        ))

    def test_recovery_budget_resets_only_after_leaving_obstacle_neighborhood(self) -> None:
        self.assertFalse(_recovery_budget_can_reset(
            world_x=14.99, world_y=0.0, last_collision_world=(0.0, 0.0),
        ))
        self.assertTrue(_recovery_budget_can_reset(
            world_x=15.0, world_y=0.0, last_collision_world=(0.0, 0.0),
        ))
        self.assertFalse(_recovery_budget_can_reset(
            world_x=100.0, world_y=100.0, last_collision_world=None,
        ))

    def test_collision_recovery_uses_forward_portal_centers_not_key_macro(self) -> None:
        vertices = (
            NavPoint(0.0, -2.0, 1.0),
            NavPoint(10.0, -2.0, 1.0),
            NavPoint(5.0, 2.0, 1.0),
        )
        polygons = tuple(
            NavPolygon(
                index=index, area=0, polygon_type=0, slope_degrees=0.0,
                centroid=NavPoint(float(index * 5), 0.0, 1.0),
                vertices=vertices, physical_surfaces=frozenset({"wmo"}),
            )
            for index in range(3)
        )
        corridor = NavCorridor(
            "Azeroth", 30, 28,
            NavPoint(0.0, 0.0, 1.0), NavPoint(15.0, 0.0, 1.0),
            (NavPoint(0.0, 0.0, 1.0), NavPoint(15.0, 0.0, 1.0)),
            polygons=polygons,
            portals=(
                NavPortal(0, 1, NavPoint(4.0, -2.0, 1.0), NavPoint(4.0, 2.0, 1.0), 4.0),
                NavPortal(1, 2, NavPoint(9.0, -2.0, 1.0), NavPoint(9.0, 2.0, 1.0), 4.0),
            ),
        )

        self.assertEqual(
            _portal_recenter_candidates(corridor, world_x=3.5, world_y=0.0),
            (NavPoint(9.0, 0.0, 1.0),),
        )
        single_polygon_corridor = NavCorridor(
            "Azeroth", 30, 28,
            NavPoint(0.0, 0.0, 1.0), NavPoint(5.0, 0.0, 1.0),
            (NavPoint(0.0, 0.0, 1.0), NavPoint(5.0, 0.0, 1.0)),
            polygons=(polygons[0],),
            portals=(),
        )
        self.assertEqual(
            _portal_recenter_candidates(
                single_polygon_corridor, world_x=0.0, world_y=0.0,
            ),
            (),
        )
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(encoding="utf-8")
        self.assertNotIn('"kind": "STUCK_RECOVERY"', source)
        self.assertNotIn("engine.recovery_maneuver(", source)

    def test_local_clearance_is_derived_from_collision_geometry(self) -> None:
        blocker = (1.25, 0.0, 1.0, 1.5)
        pairs = _local_clearance_anchor_pairs(
            world_x=0.0, world_y=0.0, world_z=1.0, blocker=blocker,
        )
        self.assertEqual(len(pairs), 2)
        self.assertAlmostEqual(pairs[0][0].x, 0.0)
        self.assertAlmostEqual(pairs[1][0].x, 0.0)
        self.assertLess(pairs[0][0].y, 0.0)
        self.assertGreater(pairs[1][0].y, 0.0)
        self.assertGreater(pairs[0][1].x, blocker[0])
        self.assertGreater(pairs[1][1].x, blocker[0])

        direct = NavCorridor(
            "Azeroth", 30, 28,
            NavPoint(0.0, 0.0, 1.0), NavPoint(0.0, 2.25, 1.25),
            (NavPoint(0.0, 0.0, 1.0), NavPoint(0.0, 2.25, 1.25)),
        )
        self.assertTrue(_local_clearance_leg_is_valid(
            direct,
            requested_start=NavPoint(0.0, 0.0, 1.0),
            requested_stop=NavPoint(0.0, 2.25, 1.0),
        ))

    def test_local_clearance_allows_bounded_radius_scaled_arc(self) -> None:
        corridor = NavCorridor(
            "Azeroth", 30, 28,
            NavPoint(0.0, 0.0, 1.0), NavPoint(2.5, 0.0, 1.0),
            (
                NavPoint(0.0, 0.0, 1.0),
                NavPoint(0.0, 2.0, 1.0),
                NavPoint(2.5, 2.0, 1.0),
                NavPoint(2.5, 0.0, 1.0),
            ),
        )

        self.assertFalse(_local_clearance_leg_is_valid(
            corridor,
            requested_start=NavPoint(0.0, 0.0, 1.0),
            requested_stop=NavPoint(2.5, 0.0, 1.0),
        ))
        self.assertTrue(_local_clearance_leg_is_valid(
            corridor,
            requested_start=NavPoint(0.0, 0.0, 1.0),
            requested_stop=NavPoint(2.5, 0.0, 1.0),
            maximum_detour_extra_world=2.5,
        ))

    def test_confirmed_clearance_prior_is_geometry_derived_and_navmesh_validated(self) -> None:
        obstacle = LearnedObstacle(
            obstacle_id="obstacle:1234567890abcdef",
            map_name="SyntheticWorld",
            zone_index=77,
            x=10.0,
            y=0.0,
            z=5.0,
            radius=1.5,
            observations=2,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-02T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )

        class SyntheticQuery:
            def find_corridor(
                self, *, map_name, start, stop_x, stop_y, stop_z=None,
            ):
                stop = NavPoint(stop_x, stop_y, stop_z)
                # Synthetic wall blocks only the negative-Y bypass.  This is
                # deliberately not an Azeroth coordinate or asset.
                if start.y < -0.1 or stop.y < -0.1:
                    reached = NavPoint(start.x, start.y, start.z)
                    return NavCorridor(
                        map_name, 0, 0, start, reached, (start, reached),
                        complete=False, requested_stop=stop,
                    )
                return NavCorridor(
                    map_name, 0, 0, start, stop, (start, stop),
                )

        goals, evidence = _inject_confirmed_clearance_priors(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(20.0, 0.0),),
            obstacles=(obstacle,),
            query=SyntheticQuery(),
            map_name="SyntheticWorld",
        )

        self.assertEqual(len(goals), 3)
        self.assertGreater(goals[0].y, 0.0)
        self.assertGreater(goals[1].y, 0.0)
        self.assertEqual(goals[2], RoadWorldPoint(20.0, 0.0))
        self.assertEqual(evidence[0]["obstacle_id"], obstacle.obstacle_id)
        self.assertEqual(
            evidence[0]["source"], "confirmed_client_observed_geometry",
        )

    def test_boundary_sample_rejects_safe_corners_with_unsafe_middle_segment(self) -> None:
        obstacle = LearnedObstacle(
            obstacle_id="obstacle:narrow-boundary",
            map_name="SyntheticWorld", zone_index=77,
            x=10.0, y=0.0, z=5.0, radius=1.0, observations=3,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-03T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )

        class NarrowQuery:
            def find_corridor(
                self, *, map_name, start, stop_x, stop_y, stop_z=None,
            ):
                stop = NavPoint(stop_x, stop_y, stop_z)
                if max(abs(start.y), abs(stop.y)) > 1.80:
                    return NavCorridor(
                        map_name, 0, 0, start, start, (start, start),
                        complete=False, requested_stop=stop,
                    )
                return NavCorridor(map_name, 0, 0, start, stop, (start, stop))

        goals, evidence = _inject_confirmed_clearance_priors(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(20.0, 0.0),),
            obstacles=(obstacle,), query=NarrowQuery(),
            map_name="SyntheticWorld",
        )

        # The former 1.75-yard bypass had safe diagonal corners but its
        # middle segment violated the 1.0 + 1.25-yard body envelope.
        self.assertEqual(goals, (RoadWorldPoint(20.0, 0.0),))
        self.assertEqual(evidence[0]["kind"], "CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED")

    def test_boundary_sample_rejects_point_only_clearance_for_actor_body(self) -> None:
        obstacle = LearnedObstacle(
            obstacle_id="obstacle:point-only-clearance",
            map_name="SyntheticWorld", zone_index=77,
            x=10.0, y=0.0, z=5.0, radius=1.5, observations=3,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-03T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )

        class PointOnlyQuery:
            def find_corridor(
                self, *, map_name, start, stop_x, stop_y, stop_z=None,
            ):
                stop = NavPoint(stop_x, stop_y, stop_z)
                if max(abs(start.y), abs(stop.y)) > 1.30:
                    return NavCorridor(
                        map_name, 0, 0, start, start, (start, start),
                        complete=False, requested_stop=stop,
                    )
                return NavCorridor(map_name, 0, 0, start, stop, (start, stop))

        goals, evidence = _inject_confirmed_clearance_priors(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(20.0, 0.0),),
            obstacles=(obstacle,), query=PointOnlyQuery(),
            map_name="SyntheticWorld",
        )

        self.assertEqual(goals, (RoadWorldPoint(20.0, 0.0),))
        self.assertEqual(evidence[0]["kind"], "CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED")

    def test_local_clearance_rejects_large_navmesh_projection(self) -> None:
        requested_start = NavPoint(0.0, 0.0, 1.0)
        requested_stop = NavPoint(2.0, 0.0, 1.0)
        projected_stop = NavPoint(2.0, 0.25, 1.0)
        corridor = NavCorridor(
            "SyntheticWorld", 0, 0,
            requested_start, projected_stop,
            (requested_start, projected_stop),
        )

        self.assertFalse(_local_clearance_leg_is_valid(
            corridor,
            requested_start=requested_start,
            requested_stop=requested_stop,
        ))

    def test_confirmed_clearance_checks_actual_local_corridor_geometry(self) -> None:
        obstacle = LearnedObstacle(
            obstacle_id="obstacle:local-dogleg",
            map_name="SyntheticWorld", zone_index=77,
            x=9.0, y=9.0, z=5.0, radius=1.5, observations=3,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-03T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )
        corridor = NavCorridor(
            "SyntheticWorld", 0, 0,
            NavPoint(0.0, 0.0, 5.0), NavPoint(20.0, 0.0, 5.0),
            (
                NavPoint(0.0, 0.0, 5.0),
                NavPoint(10.0, 10.0, 5.0),
                NavPoint(20.0, 10.0, 5.0),
                NavPoint(20.0, 0.0, 5.0),
            ),
        )

        class CompleteQuery:
            def find_corridor(
                self, *, map_name, start, stop_x, stop_y, stop_z=None,
            ):
                stop = NavPoint(stop_x, stop_y, stop_z)
                return NavCorridor(map_name, 0, 0, start, stop, (start, stop))

        anchors, evidence = _confirmed_local_corridor_clearance(
            corridor=corridor,
            obstacles=(obstacle,),
            query=CompleteQuery(),
            map_name="SyntheticWorld",
            route_start_z=5.0,
        )

        self.assertIsNotNone(anchors)
        self.assertEqual(
            evidence[0]["kind"], "CONFIRMED_CLEARANCE_PRIOR_APPLIED",
        )
        self.assertGreater(
            _point_segment_distance_2d(
                RoadWorldPoint(obstacle.x, obstacle.y),
                RoadWorldPoint(0.0, 0.0),
                RoadWorldPoint(20.0, 0.0),
            ),
            obstacle.radius + 1.25,
        )

    def test_confirmed_clearance_without_valid_bypass_is_reported_unresolved(self) -> None:
        obstacle = LearnedObstacle(
            obstacle_id="obstacle:blockedcorridor",
            map_name="SyntheticWorld", zone_index=77,
            x=10.0, y=0.0, z=5.0, radius=1.5, observations=2,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-02T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )

        class BlockedQuery:
            def find_corridor(
                self, *, map_name, start, stop_x, stop_y, stop_z=None,
            ):
                stop = NavPoint(stop_x, stop_y, stop_z)
                return NavCorridor(
                    map_name, 0, 0, start, start, (start, start),
                    complete=False, requested_stop=stop,
                )

        goals, evidence = _inject_confirmed_clearance_priors(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(20.0, 0.0),),
            obstacles=(obstacle,), query=BlockedQuery(),
            map_name="SyntheticWorld",
        )

        self.assertEqual(goals, (RoadWorldPoint(20.0, 0.0),))
        self.assertEqual(
            evidence[0]["kind"], "CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED",
        )
        self.assertEqual(
            evidence[0]["reason"],
            "no_navmesh_validated_bypass_for_confirmed_geometry",
        )

    def test_far_confirmed_clearance_uses_global_navmesh_segment(self) -> None:
        obstacle = LearnedObstacle(
            obstacle_id="obstacle:far-blocker",
            map_name="SyntheticWorld", zone_index=77,
            x=500.0, y=0.0, z=50.0, radius=1.5, observations=2,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-02T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )

        class NoLocalArcQuery:
            observed_blockers = ()

            def __init__(self, *, global_query=False):
                self.global_query = global_query

            def with_observed_blockers(self, blockers):
                self.asserted_blockers = blockers
                return NoLocalArcQuery(global_query=True)

            def find_corridor(
                self, *, map_name, start, stop_x, stop_y, stop_z=None,
            ):
                stop = NavPoint(stop_x, stop_y, stop_z)
                if self.global_query:
                    middle = NavPoint(
                        (start.x + stop.x) / 2.0,
                        (start.y + stop.y) / 2.0 + 4.0,
                        stop.z,
                    )
                    return NavCorridor(
                        map_name, 0, 0, start, stop,
                        (start, middle, stop), requested_stop=stop,
                    )
                return NavCorridor(
                    map_name, 0, 0, start, start, (start, start),
                    complete=False, requested_stop=stop,
                )

        continuation_cache = {}
        goals, evidence = _inject_confirmed_clearance_priors(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(1_000.0, 0.0),),
            obstacles=(obstacle,), query=NoLocalArcQuery(),
            map_name="SyntheticWorld",
            continuation_cache=continuation_cache,
        )

        self.assertEqual(goals, (RoadWorldPoint(1_000.0, 0.0),))
        self.assertIn((0.0, 0.0, 1_000.0, 0.0), continuation_cache)
        self.assertTrue(
            continuation_cache[(0.0, 0.0, 1_000.0, 0.0)].complete
        )
        self.assertEqual(
            evidence[0]["kind"],
            "CONFIRMED_CLEARANCE_PRIOR_APPLIED_BY_GLOBAL_NAVMESH",
        )
        self.assertEqual(evidence[0]["semantic_waypoints_inserted"], 0)
        self.assertGreater(
            evidence[0]["distance_from_route_start_world"], 96.0,
        )

        uncached_goals, uncached_evidence = _inject_confirmed_clearance_priors(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(1_000.0, 0.0),),
            obstacles=(obstacle,), query=NoLocalArcQuery(),
            map_name="SyntheticWorld",
        )
        self.assertEqual(uncached_goals, (RoadWorldPoint(1_000.0, 0.0),))
        self.assertEqual(
            uncached_evidence[0]["kind"],
            "CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED",
        )

    def test_confirmed_obstacle_inside_terminal_arrival_area_is_not_chased(self) -> None:
        obstacle = LearnedObstacle(
            obstacle_id="obstacle:terminal-prop",
            map_name="SyntheticWorld", zone_index=77,
            x=19.0, y=0.0, z=5.0, radius=3.0, observations=3,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-02T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )
        query = Mock()
        goals, evidence = _inject_confirmed_clearance_priors(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(20.0, 0.0),),
            obstacles=(obstacle,), query=query,
            map_name="SyntheticWorld", terminal_goal_radius_world=22.0,
        )
        self.assertEqual(goals, (RoadWorldPoint(20.0, 0.0),))
        self.assertEqual(
            evidence[0]["kind"],
            "CONFIRMED_CLEARANCE_PRIOR_WITHIN_TERMINAL_RADIUS",
        )
        query.find_corridor.assert_not_called()

    def test_observed_surface_repairs_only_a_contradicted_local_chord(self) -> None:
        from perfect_assassin.movement.manual_path_recording import (
            ManualPathRecording, ManualPathVertex,
        )

        obstacle = LearnedObstacle(
            obstacle_id="obstacle:falsemeshwall",
            map_name="SyntheticWorld", zone_index=77,
            x=5.0, y=0.0, z=5.0, radius=1.5, observations=2,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-02T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )
        recording = ManualPathRecording(
            recording_id="manual:synthetic", name="Observed local passage",
            status="COMPLETE", minimum_spacing_world=0.75,
            vertices=tuple(
                ManualPathVertex(x, y, float(index))
                for index, (x, y) in enumerate((
                    (0.0, 0.0), (0.0, 2.0), (2.0, 3.0),
                    (5.0, 3.0), (8.0, 3.0), (10.0, 0.0),
                ))
            ),
        )

        goals, bypassed, evidence = _inject_traversed_surface_prior(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(10.0, 0.0),),
            obstacles=(obstacle,), recording=recording,
        )

        self.assertEqual(goals, (RoadWorldPoint(10.0, 0.0),))
        self.assertEqual(bypassed, (obstacle.obstacle_id,))
        self.assertEqual(
            evidence["kind"], "TRAVERSED_SURFACE_TOPOLOGY_PRIOR_APPLIED",
        )
        self.assertEqual(evidence["local_point_count"], 0)
        self.assertGreater(evidence["observed_point_count"], 0)
        self.assertFalse(evidence["execution_authority"])

    def test_semantic_runner_suppresses_traversal_contradicted_polygon_blocker(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            '"LEARNED_POLYGON_BLOCKER_SUPPRESSED_BY_COMPLETE_"', source,
        )
        delayed = source.index("if args.semantic_destination_id is None:")
        contradiction = source.index(
            "active_learned_polygon_blockers = tuple(", delayed,
        )
        static_horizon = source.index(
            "static_structure_blockers = _route_static_structure_blockers(",
            contradiction,
        )
        self.assertLess(delayed, contradiction)
        self.assertLess(contradiction, static_horizon)

    def test_observed_surface_does_not_replace_uncontradicted_route(self) -> None:
        from perfect_assassin.movement.manual_path_recording import (
            ManualPathRecording, ManualPathVertex,
        )

        recording = ManualPathRecording(
            recording_id="manual:synthetic", name="Irrelevant prior",
            status="COMPLETE", minimum_spacing_world=0.75,
            vertices=(
                ManualPathVertex(0.0, 0.0, 0.0),
                ManualPathVertex(0.0, 2.0, 1.0),
            ),
        )
        original = (RoadWorldPoint(10.0, 0.0),)

        goals, bypassed, evidence = _inject_traversed_surface_prior(
            route_start=RoadWorldPoint(0.0, 0.0), goals=original,
            obstacles=(), recording=recording,
        )

        self.assertEqual(goals, original)
        self.assertEqual(bypassed, ())
        self.assertIsNone(evidence)

    def test_noisy_demonstration_is_evidence_only_not_executable_prefix(self) -> None:
        from perfect_assassin.movement.manual_path_recording import (
            ManualPathRecording, ManualPathVertex,
        )

        obstacle = LearnedObstacle(
            obstacle_id="obstacle:noisy-boundary",
            map_name="SyntheticWorld", zone_index=77,
            x=5.0, y=0.0, z=5.0, radius=1.5, observations=2,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-02T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )
        # The actor reaches the same local area only after repeated camera
        # corrections and backtracking.  This must not become executable
        # route geometry merely because it eventually rejoins a clear goal.
        xy = ((0.0, 0.0), (0.0, 2.0), (2.0, 2.0), (0.0, 2.0),
              (2.0, 2.0), (0.0, 2.0), (2.0, 2.0), (10.0, 0.0))
        recording = ManualPathRecording(
            recording_id="manual:noisy", name="Noisy local demonstration",
            status="COMPLETE", minimum_spacing_world=0.75,
            vertices=tuple(
                ManualPathVertex(x, y, float(index))
                for index, (x, y) in enumerate(xy)
            ),
        )

        goals, bypassed, evidence = _inject_traversed_surface_prior(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(10.0, 0.0),),
            obstacles=(obstacle,), recording=recording,
        )

        self.assertEqual(goals, (RoadWorldPoint(10.0, 0.0),))
        self.assertEqual(bypassed, (obstacle.obstacle_id,))
        self.assertIsNotNone(evidence)
        self.assertEqual(
            evidence["kind"], "TRAVERSED_SURFACE_TOPOLOGY_PRIOR_REJECTED",
        )
        self.assertIn(
            evidence["reason"],
            {
                "recording_detour_ratio_exceeded",
                "recording_reentered_start_basin",
                "recording_backtracking_detected",
            },
        )

    def test_clearance_prior_supersedes_route_sample_inside_obstacle_envelope(self) -> None:
        obstacle = LearnedObstacle(
            obstacle_id="obstacle:abcdef0123456789",
            map_name="SyntheticWorld",
            zone_index=77,
            x=10.0, y=0.0, z=5.0, radius=1.5, observations=2,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-02T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )

        class PositiveSideQuery:
            def find_corridor(
                self, *, map_name, start, stop_x, stop_y, stop_z=None,
            ):
                stop = NavPoint(stop_x, stop_y, stop_z)
                if start.y < -0.1 or stop.y < -0.1:
                    return NavCorridor(
                        map_name, 0, 0, start, start, (start, start),
                        complete=False, requested_stop=stop,
                    )
                return NavCorridor(map_name, 0, 0, start, stop, (start, stop))

        goals, evidence = _inject_confirmed_clearance_priors(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(9.0, 0.0), RoadWorldPoint(20.0, 0.0)),
            obstacles=(obstacle,),
            query=PositiveSideQuery(),
            map_name="SyntheticWorld",
        )

        self.assertNotIn(RoadWorldPoint(9.0, 0.0), goals)
        self.assertEqual(len(goals), 3)
        self.assertEqual(goals[-1], RoadWorldPoint(20.0, 0.0))
        self.assertEqual(evidence[0]["superseded_route_sample_count"], 1)

    def test_off_route_memory_cannot_steer(self) -> None:
        provisional = LearnedObstacle(
            obstacle_id="obstacle:fedcba0987654321",
            map_name="SyntheticWorld",
            zone_index=77,
            x=10.0,
            y=20.0,
            z=5.0,
            radius=1.5,
            observations=1,
            first_observed_at="2026-08-01T00:00:00Z",
            last_observed_at="2026-08-01T00:00:00Z",
            last_run_id="navigation:synthetic",
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )
        query = Mock()

        goals, evidence = _inject_confirmed_clearance_priors(
            route_start=RoadWorldPoint(0.0, 0.0),
            goals=(RoadWorldPoint(20.0, 0.0),),
            obstacles=(provisional,),
            query=query,
            map_name="SyntheticWorld",
        )

        self.assertEqual(goals, (RoadWorldPoint(20.0, 0.0),))
        self.assertEqual(evidence, ())
        query.find_corridor.assert_not_called()

    def test_small_blocker_cannot_promote_a_map_scale_detour(self) -> None:
        baseline = NavCorridor(
            "Azeroth", 30, 28,
            NavPoint(0.0, 0.0, 1.0), NavPoint(30.0, 0.0, 1.0),
            (NavPoint(0.0, 0.0, 1.0), NavPoint(30.0, 0.0, 1.0)),
        )
        pathological = NavCorridor(
            "Azeroth", 30, 28,
            NavPoint(10.0, 0.0, 1.0), NavPoint(30.0, 0.0, 1.0),
            (
                NavPoint(10.0, 0.0, 1.0),
                NavPoint(10.0, -100.0, 1.0),
                NavPoint(30.0, -100.0, 1.0),
                NavPoint(30.0, 0.0, 1.0),
            ),
        )
        accepted, candidate_length, baseline_length, maximum = (
            _blocker_route_quality(
                pathological,
                baseline,
                world_x=10.0,
                world_y=0.0,
                goal_x=30.0,
                goal_y=0.0,
                blocker_radius=1.5,
            )
        )

        self.assertFalse(accepted)
        self.assertGreater(candidate_length, maximum)
        self.assertAlmostEqual(baseline_length, 20.0)

        local_detour = NavCorridor(
            "Azeroth", 30, 28,
            NavPoint(10.0, 0.0, 1.0), NavPoint(30.0, 0.0, 1.0),
            (
                NavPoint(10.0, 0.0, 1.0),
                NavPoint(14.0, -2.0, 1.0),
                NavPoint(18.0, 0.0, 1.0),
                NavPoint(30.0, 0.0, 1.0),
            ),
        )
        self.assertTrue(_blocker_route_quality(
            local_detour,
            baseline,
            world_x=10.0,
            world_y=0.0,
            goal_x=30.0,
            goal_y=0.0,
            blocker_radius=1.5,
        )[0])

    def test_local_clearance_is_preferred_before_global_blocker_route(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(encoding="utf-8")
        recovery = source[
            source.index("if intent.state == \"REPLAN\":") :
            source.index("topology_recovery_accepted =", source.index("if intent.state == \"REPLAN\":"))
        ]
        self.assertLess(
            recovery.index("for side_anchor, pass_anchor"),
            recovery.index("for portal_target"),
        )
        self.assertIn("if local_clearance_corridors is not None", recovery)
        self.assertIn("blocker_route_accepted = False", recovery)
        post_plan = source[
            source.index("if blocker_route_accepted or portal_recenter_corridor is not None:") :
            source.index("# Detour queries are bounded", source.index("if blocker_route_accepted or portal_recenter_corridor is not None:"))
        ]
        self.assertIn("local_clearance_corridors is None", post_plan)
        self.assertIn("breadcrumb_backtrack_corridor is None", post_plan)
        self.assertNotIn("else:\n                    break", post_plan)

    def test_breadcrumb_backtrack_uses_jitter_tolerant_arrival_radius(self) -> None:
        self.assertGreater(BREADCRUMB_BACKTRACK_ARRIVAL_RADIUS_WORLD, 2.0)
        self.assertGreater(
            BREADCRUMB_BACKTRACK_ARRIVAL_RADIUS_WORLD,
            LOCAL_CLEARANCE_ARRIVAL_RADIUS_WORLD,
        )
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        start = source.index("elif breadcrumb_backtrack_corridor is not None:")
        end = source.index('"kind": "VERIFIED_BREADCRUMB_BACKTRACK_PLANNED"', start)
        recovery = source[start:end]
        self.assertIn("BREADCRUMB_BACKTRACK_ARRIVAL_RADIUS_WORLD", recovery)
        self.assertNotIn("LOCAL_CLEARANCE_ARRIVAL_RADIUS_WORLD),", recovery)

    def test_one_provisional_collision_cannot_poison_future_global_routes(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(encoding="utf-8")
        learned = source[
            source.index("learned_polygon_obstacles = tuple(") :
            source.index("learned_polygon_blockers = tuple(")
        ]
        self.assertIn('item.confidence == "confirmed"', learned)
        self.assertIn("item.evidence == DETOUR_EXCLUSION_EVIDENCE", learned)

    def test_external_ui_launches_semantic_engine_not_reviewed_route_file(self) -> None:
        source = (RUNNER_PATH / "run_movement_engine_client.py").read_text(encoding="utf-8")
        self.assertNotIn("run_reviewed_journey_route.py", source)
        self.assertNotIn('"--semantic-destination-id", "settlement:brill"', source)
        self.assertIn('"--semantic-destination-id", destination_id', source)
        self.assertIn("values=tuple(self.destination_id_by_name)", source)
        launch = source[source.index("self.process = subprocess.Popen(") : source.index("self.root.after(0, self._set_running)")]
        self.assertIn('"--world-pack-profile", str(WORLD_PACK_PROFILE)', launch)
        self.assertIn('"--world-pack-store", str(WORLD_PACK_STORE)', launch)
        self.assertIn('"--world-structure-index", str(WORLD_STRUCTURE_INDEX)', launch)
        self.assertIn(
            '["--structure-access-graph", str(STRUCTURE_ACCESS_GRAPH)]', source,
        )
        self.assertIn("*structure_access_arguments", launch)
        self.assertIn('"--continue-through-routine-aggro"', launch)
        self.assertNotIn('"--nav-root"', launch)

    def test_control_center_unifies_combat_and_movement_without_a_second_window(self) -> None:
        center = (RUNNER_PATH / "run_movement_engine_client.py").read_text(
            encoding="utf-8"
        )
        legacy = (RUNNER_PATH / "run_predator_control.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'self.root.title("Predator")', center,
        )
        self.assertIn(
            'self.workspace_tabs.add(navigation_tab, text="Mers")', center,
        )
        self.assertIn('self.workspace_tabs.add(future_tab, text="Alte lucruri")', center)
        self.assertIn('self.workspace_tabs.select(navigation_tab)', center)
        self.assertIn("def _prepare_and_launch_combat", center)
        self.assertIn("MovementEngineClient().run()", legacy)
        self.assertNotIn("PredatorControlWindow().run()", legacy)

    def test_control_center_exposes_bounded_read_only_stationary_certification(self) -> None:
        center = (RUNNER_PATH / "run_movement_engine_client.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('text="Verifică locul"', center)
        self.assertIn('text="Verifică (4 secunde)"', center)
        self.assertIn("def _collect_stationary_validation", center)
        collector = center[
            center.index("def _collect_stationary_validation") :
            center.index("def _consume_stationary_validation_result")
        ]
        self.assertIn("read_live_pose_file", collector)
        self.assertIn("evaluate_stationary_pose", collector)
        self.assertNotIn("send_input", collector.lower())
        self.assertNotIn("_write_command", collector)

    def test_control_center_primary_words_are_plain_and_action_first(self) -> None:
        center = (RUNNER_PATH / "run_movement_engine_client.py").read_text(
            encoding="utf-8"
        )
        primary = center[
            center.index("class MovementEngineClient:") :
            center.index("    def _active_pose_zone_index", center.index("class MovementEngineClient:"))
        ]
        for plain_label in (
            'text="PREDATOR — UNDE MERGE"',
            'text="Harta"',
            'text="Unde merge?"',
            'text="Îi dau voie să meargă singur"',
            'text="Alege singur drumul"',
            'text="Verifică locul"',
            'text="Harta acum"',
            'text="Urmărește Predatorul"',
        ):
            self.assertIn(plain_label, primary)
        for old_label in (
            "Poate merge singur (doar în LAB)",
            "Unelte manuale",
            "Lumea jocului",
            "Test de poziție și direcție",
            "Coordonatele sunt aceleași ca în joc",
        ):
            self.assertNotIn(old_label, primary)

    def test_control_center_keeps_checked_movement_permission_alive(self) -> None:
        center = (RUNNER_PATH / "run_movement_engine_client.py").read_text(
            encoding="utf-8"
        )
        renew = center[
            center.index("    def _renew_continuous_motion_arm_once") :
            center.index("    def _prepare_and_launch_combat")
        ]
        self.assertIn('"IssueMovementRealmRevalidation"', renew)
        self.assertIn('str(CONTINUOUS_MOTION_REVALIDATION_FILE)', renew)
        self.assertIn('"issue_continuous_motion_runtime_arm.py"', renew)
        self.assertIn("MOTION_ARM_RENEW_INTERVAL_S", renew)
        self.assertIn("MOTION_AUTH_RENEW_INTERVAL_S", renew)
        self.assertIn("SESSION_RENEW_INTERVAL_S", renew)
        hidden = center[
            center.index("    def _run_hidden_checked") :
            center.index("    def _renew_continuous_motion_arm_once")
        ]
        self.assertIn("creationflags=0x08000000", hidden)
        self.assertIn("motion_stop_event = Event()", center)
        self.assertIn("self.motion_arm_renew_stop.set()", center)
        self.assertIn("target=self._maintain_continuous_motion_arm", center)
        self.assertIn("command=self._continuous_motion_permission_changed", center)

    def test_stationary_certification_text_reports_truthfully(self) -> None:
        passing = {
            "record_type": "stationary_pose_validation",
            "schema_version": "1.0",
            "sample_count": 21,
            "duration_s": 4.0,
            "passed": True,
            "failures": [],
            "expected_location_id": "landmark:deathknell-crypt",
            "within_expected_location": True,
            "execution_authority": False,
        }
        self.assertIn("BINE", movement_ui._stationary_pose_text(passing))
        self.assertIn("era în criptă", movement_ui._stationary_pose_text(passing))
        failing = {
            **passing,
            "sample_count": 0,
            "passed": False,
            "failures": ["insufficient_unique_samples"],
        }
        self.assertIn("nu am primit destule date", movement_ui._stationary_pose_text(failing))
        no_location_proof = {
            **passing,
            "within_expected_location": None,
        }
        self.assertIn(
            "Nu pot dovedi că Predatorul este în criptă",
            movement_ui._stationary_pose_text(no_location_proof),
        )
        self.assertIn("Testul nu a putut fi citit", movement_ui._stationary_pose_text({}))

    def test_control_center_reads_a_fresh_shared_live_pose(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "live-state.txt"
            state.write_text(
                "\n".join((
                    "PA_NAV_VIEWER_STATE 4",
                    "sequence 42",
                    "observed 100.250000000",
                    "pose 1837.500000 1586.250000",
                    "facing 1.570796327",
                    "corridor 0",
                    "walls 0",
                    "transitions 0",
                    "egresses 0",
                    "conditional_boundaries 0",
                    "trail 0",
                    "end",
                )) + "\n",
                encoding="ascii",
            )
            pose = movement_ui._read_live_map_pose(
                state, now_monotonic_s=100.50,
            )

        self.assertIsNotNone(pose)
        assert pose is not None
        self.assertEqual(pose.sequence, 42)
        self.assertEqual((pose.world_x, pose.world_y), (1837.5, 1586.25))
        self.assertAlmostEqual(pose.facing_rad, 1.570796327)

    def test_control_center_names_live_pose_sources_and_age(self) -> None:
        pose = movement_ui.LiveMapPose(
            sequence=7,
            observed_monotonic_s=100.0,
            world_x=1837.5,
            world_y=1586.25,
            facing_rad=1.25,
            position_source="COORDINATE_HUD",
            facing_source="COORDINATE_HUD_EXACT",
        )
        text = movement_ui._live_observation_source_text(
            pose, now_monotonic_s=100.123,
        )
        self.assertIn("Locul: îl văd", text)
        self.assertIn("exact încotro privește", text)
        self.assertIn("acum 123 ms", text)
        unavailable = movement_ui._live_observation_source_text(
            None, now_monotonic_s=100.0,
        )
        self.assertIn("încă nu îl văd", unavailable)

    def test_control_center_rejects_a_stale_shared_live_pose(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "live-state.txt"
            state.write_text(
                "PA_NAV_VIEWER_STATE 2\nsequence 1\nobserved 10\n"
                "pose 1 2\nfacing none\ncorridor 0\nwalls 0\n"
                "transitions 0\negresses 0\nend\n",
                encoding="ascii",
            )
            pose = movement_ui._read_live_map_pose(
                state, now_monotonic_s=11.0,
            )
        self.assertIsNone(pose)

    def test_pose_only_live_map_never_reuses_old_local_geometry(self) -> None:
        pose = movement_ui.LiveMapPose(
            sequence=7,
            observed_monotonic_s=20.0,
            world_x=10.0,
            world_y=11.0,
            facing_rad=0.25,
            facing_source="COORDINATE_HUD_EXACT",
        )
        snapshot = movement_ui._snapshot_with_live_pose(None, pose)

        self.assertEqual((snapshot.player_world_x, snapshot.player_world_y), (10.0, 11.0))
        self.assertEqual(snapshot.player_facing_rad, 0.25)
        self.assertEqual(snapshot.body_facing_rad, 0.25)
        self.assertEqual(snapshot.body_facing_source, "COORDINATE_HUD_EXACT")
        self.assertIn(
            "Fața: 14.3°",
            movement_ui._body_camera_orientation_text(snapshot),
        )
        self.assertIn(
            "camera: nu o văd",
            movement_ui._body_camera_orientation_text(snapshot),
        )
        self.assertEqual(snapshot.navmesh_polygons_world, ())
        self.assertEqual(snapshot.corridor_centerline_world, ())
        self.assertIn("LOCALIZARE LIVE", snapshot.controller_state)

    def test_live_body_pose_preserves_separate_camera_estimate(self) -> None:
        snapshot = movement_ui.MovementLabSnapshot(
            20.0, "LOST", None, None,
            player_world_x=9.0,
            player_world_y=10.0,
            player_facing_rad=0.4,
            body_facing_rad=0.5,
            body_facing_source="COORDINATE_HUD_EXACT",
            camera_yaw_estimate_rad=0.4,
            camera_yaw_source="MOUSE_INTEGRATED_ESTIMATE",
            body_camera_yaw_delta_rad=0.1,
        )
        pose = movement_ui.LiveMapPose(
            sequence=8,
            observed_monotonic_s=20.2,
            world_x=10.0,
            world_y=11.0,
            facing_rad=0.6,
            facing_source="COORDINATE_HUD_EXACT",
        )
        merged = movement_ui._snapshot_with_live_pose(snapshot, pose)
        self.assertEqual(merged.body_facing_rad, 0.6)
        self.assertEqual(merged.camera_yaw_estimate_rad, 0.4)
        self.assertAlmostEqual(merged.body_camera_yaw_delta_rad, 0.2)
        text = movement_ui._body_camera_orientation_text(merged)
        self.assertIn("Fața: 34.4°", text)
        self.assertIn("camera: 22.9°", text)
        self.assertIn("între ele +11.5°", text)

    def test_map_draws_exact_body_and_estimated_camera_as_distinct_arrows(self) -> None:
        center = (RUNNER_PATH / "run_movement_engine_client.py").read_text(
            encoding="utf-8"
        )
        start = center.index("def draw_orientation_arrow")
        end = center.index("show_operator_layers =", start)
        drawing = center[start:end]
        self.assertIn("snapshot.body_facing_rad", drawing)
        self.assertIn('color="#1677ff"', drawing)
        self.assertIn("snapshot.camera_yaw_estimate_rad", drawing)
        self.assertIn('color="#ff9f43"', drawing)
        self.assertNotIn("snapshot.player_facing_rad", drawing)
        self.assertIn(
            "Albastru = Predatorul • Portocaliu = privirea", center,
        )

    def test_control_center_verifies_the_large_world_pack_once_per_process(self) -> None:
        movement_ui._cached_world_pack_binding.cache_clear()
        expected = object()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            movement_ui, "WORLD_PACK_PROFILE", Path(directory) / "profile.json",
        ), patch.object(
            movement_ui, "WORLD_PACK_STORE", Path(directory) / "packs",
        ), patch.object(
            movement_ui,
            "load_world_pack_runtime_profile",
            return_value=expected,
        ) as loader:
            self.assertIs(movement_ui._verified_world_pack_binding(), expected)
            self.assertIs(movement_ui._verified_world_pack_binding(), expected)
        self.assertEqual(loader.call_count, 1)
        movement_ui._cached_world_pack_binding.cache_clear()

    def test_control_center_refreshes_the_large_movement_state_only_after_change(self) -> None:
        center = (RUNNER_PATH / "run_movement_engine_client.py").read_text(
            encoding="utf-8"
        )
        refresh = center[
            center.index("def _refresh_runtime_view(") : center.index("def _write_combat_command")
        ]
        self.assertIn("MOVEMENT_STATE.stat().st_mtime_ns", refresh)
        self.assertIn("if current_mtime_ns != self.movement_state_mtime_ns", refresh)
        self.assertIn("self.root.after(250, self._refresh)", center)

    def test_control_center_rejects_snapshot_from_an_earlier_boot_epoch(self) -> None:
        snapshot = SimpleNamespace(observed_monotonic_s=1_200_000.0)
        self.assertFalse(movement_ui._movement_snapshot_is_fresh(
            snapshot, now_monotonic_s=20_000.0,
        ))
        snapshot.observed_monotonic_s = 19_999.25
        self.assertTrue(movement_ui._movement_snapshot_is_fresh(
            snapshot, now_monotonic_s=20_000.0,
        ))
        snapshot.observed_monotonic_s = 19_998.0
        self.assertFalse(movement_ui._movement_snapshot_is_fresh(
            snapshot, now_monotonic_s=20_000.0,
        ))

    def test_control_center_defaults_to_the_verified_full_azeroth_access_graph(self) -> None:
        self.assertIsNotNone(movement_ui.STRUCTURE_ACCESS_GRAPH)
        assert movement_ui.STRUCTURE_ACCESS_GRAPH is not None
        self.assertEqual(
            movement_ui.STRUCTURE_ACCESS_GRAPH.name,
            "azeroth-full-v3-structure-access-graph-v1.json",
        )
        self.assertEqual(
            movement_ui.WORLD_PACK_PROFILE.name,
            "world-pack-runtime-tbc243-azeroth-full-v3.json",
        )
        self.assertEqual(
            movement_ui.WORLD_STRUCTURE_INDEX.name,
            "azeroth-full-v3-world-structure-index-v1.json",
        )
        runner = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(encoding="utf-8")
        self.assertIn(
            'DEFAULT_STRUCTURE_ACCESS_GRAPH: Path | None = None',
            runner,
        )

    def test_autonomous_start_requires_every_verified_awareness_artifact(self) -> None:
        base = {
            "structure_loading": False,
            "semantic_gate_open": True,
            "structure_index_loaded": True,
            "structure_graph_configured": True,
            "structure_graph_loaded": True,
            "structure_error": None,
        }
        ready, label, explanation = movement_ui.autonomous_start_readiness(**base)
        self.assertTrue(ready)
        self.assertEqual(label, "▶  PORNEȘTE MERSUL")
        self.assertEqual(explanation, "Gata de mers — fără luptă")

        rejected = (
            ("structure_loading", True, "VERIFIC HARTA", "Verific pe unde"),
            ("semantic_gate_open", False, "DRUMUL NU ESTE GATA", "Drumul"),
            ("structure_index_loaded", False, "HARTA NU ESTE GATA", "Lipsesc"),
            ("structure_graph_configured", False, "HARTA NU ESTE GATA", "intrările"),
            ("structure_graph_loaded", False, "HARTA NU MERGE", "intrările"),
            ("structure_error", "hash mismatch", "HARTA NU MERGE", "jurnalul"),
        )
        for field, value, expected_label, expected_explanation in rejected:
            with self.subTest(field=field):
                inputs = dict(base)
                inputs[field] = value
                ready, label, explanation = movement_ui.autonomous_start_readiness(
                    **inputs
                )
                self.assertFalse(ready)
                self.assertIn(expected_label, label)
                self.assertIn(expected_explanation, explanation)

        ready, label, explanation = movement_ui.autonomous_start_readiness(
            **{
                **base,
                "semantic_gate_open": False,
                "semantic_gate_reason": "VALIDATION_PASS_AUTHORITY_DISABLED",
            }
        )
        self.assertFalse(ready)
        self.assertEqual(label, "BIFEAZĂ CĂSUȚA")
        self.assertIn("Harta e gata", explanation)
        self.assertIn("Bifează", explanation)

    def test_crypt_trial_progress_is_explicitly_non_promotable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "gate.json"
            report.write_text(
                json.dumps({
                    "record_type": "movement_live_trial_gate",
                    "schema_version": "1.0",
                    "baseline_id": "crypt-egress-me452-v1",
                    "required_trial_count": 10,
                    "declared_trial_count": 0,
                    "valid_trial_count": 0,
                    "promotion_eligible": False,
                    "failures": ["minimum_filmed_trials_not_met"],
                    "execution_authority": False,
                    "baseline_intact": True,
                }),
                encoding="utf-8",
            )
            text = movement_ui._crypt_trial_gate_text(report)
        self.assertIn("păstrat", text)
        self.assertIn("0/10", text)
        self.assertIn("aprobate vizual", text)
        self.assertIn("nu certifică versiunea curentă", text)

    def test_crypt_trial_display_survives_non_object_and_invalid_json(self) -> None:
        """A damaged evidence file must not abort the recurring UI refresh."""
        invalid_documents = ("null", "[]", "42", "true", '"text"', '{"partial":')
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "gate.json"
            for document in invalid_documents:
                with self.subTest(document=document):
                    report.write_text(document, encoding="utf-8")
                    self.assertEqual(
                        movement_ui._crypt_trial_gate_text(report),
                        "Ieșirea din criptă: testele nu au fost citite",
                    )
            report.unlink()
            self.assertEqual(
                movement_ui._crypt_trial_gate_text(report),
                "Ieșirea din criptă: testele nu au fost citite",
            )

    def test_crypt_trial_display_rejects_invalid_evidence_fields(self) -> None:
        base = {
            "record_type": "movement_live_trial_gate",
            "schema_version": "1.0",
            "required_trial_count": 10,
            "declared_trial_count": 10,
            "valid_trial_count": 10,
            "execution_authority": False,
            "baseline_intact": True,
        }
        invalid_fields = (
            {"baseline_intact": "true"},
            {"baseline_intact": None},
            {"execution_authority": True},
            {"declared_trial_count": 9},
            {"valid_trial_count": -1},
            {"valid_trial_count": True},
            {"required_trial_count": 9},
        )
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "gate.json"
            for fields in invalid_fields:
                with self.subTest(fields=fields):
                    report.write_text(json.dumps({**base, **fields}), encoding="utf-8")
                    self.assertEqual(
                        movement_ui._crypt_trial_gate_text(report),
                        "Ieșirea din criptă: testele nu au fost citite",
                    )
            report.write_text(json.dumps(base), encoding="utf-8")
            text = movement_ui._crypt_trial_gate_text(report)
            self.assertIn("aprobate vizual 10/10", text)
            self.assertIn("nu certifică versiunea curentă", text)
            report.write_text(
                json.dumps({**base, "baseline_intact": False}), encoding="utf-8",
            )
            self.assertIn("nu este intact", movement_ui._crypt_trial_gate_text(report))

    def test_registry_profile_readiness_is_not_hardcoded_to_azeroth(self) -> None:
        """A complete non-zero map profile reaches its own awareness gate."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = tuple(root / name for name in (
                "runtime.json",
                "semantic.json",
                "structure.json",
                "access.json",
            ))
            for artifact in artifacts:
                artifact.write_text("{}", encoding="utf-8")
            client = movement_ui.MovementEngineClient.__new__(
                movement_ui.MovementEngineClient
            )
            client.active_world_map_profile = SimpleNamespace(
                map_id=33,
                runtime_profile=artifacts[0],
                semantic_catalog=artifacts[1],
                structure_index=artifacts[2],
                structure_access_graph=artifacts[3],
            )
            client.structure_awareness_loading = True
            ready, label, explanation = client._autonomous_start_readiness()

        self.assertFalse(ready)
        self.assertIn("VERIFIC HARTA", label)
        self.assertIn("Verific pe unde poate merge", explanation)
        source = (RUNNER_PATH / "run_movement_engine_client.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("profile.map_id != 0", source)

    def test_selected_profile_binds_semantic_gate_to_its_worldpack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected_profile = root / "selected-profile.json"
            selected_profile.write_text("selected", encoding="utf-8")
            default_profile = root / "default-profile.json"
            default_profile.write_text("default", encoding="utf-8")
            worker = root / "worker.exe"
            worker.write_bytes(b"worker")
            gate = root / "gate.json"
            gate.write_text("{}", encoding="utf-8")
            profile = SimpleNamespace(runtime_profile=selected_profile)
            raw_identity = {
                field: f"fixture-{field}"
                for field in movement_ui.SemanticLiveGateIdentity.__dataclass_fields__
            }
            raw_identity["world_pack_profile"] = str(selected_profile.resolve())
            raw_identity["worker"] = str(worker.resolve())
            with (
                patch.object(movement_ui, "WORLD_PACK_PROFILE", default_profile),
                patch.object(movement_ui, "WORKER", worker),
                patch.object(movement_ui, "SEMANTIC_GATE", gate),
                patch.object(movement_ui, "semantic_live_gate_open", return_value=True) as gate_open,
            ):
                self.assertTrue(
                    movement_ui._semantic_gate_open_for_structure_summary(
                        {"semantic_gate_identity": raw_identity},
                        profile=profile,
                    )
                )
            expected = gate_open.call_args.kwargs["expected"]

        self.assertEqual(expected.world_pack_profile, str(selected_profile.resolve()))
        self.assertEqual(expected.worker, str(worker.resolve()))

    def test_disabled_live_authority_is_not_reported_as_failed_regression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected_profile = root / "selected-profile.json"
            selected_profile.write_text("selected", encoding="utf-8")
            worker = root / "worker.exe"
            worker.write_bytes(b"worker")
            gate = root / "gate.json"
            gate.write_text(
                json.dumps({"live_authority_enabled": False}),
                encoding="utf-8",
            )
            profile = SimpleNamespace(runtime_profile=selected_profile)
            raw_identity = {
                field: f"fixture-{field}"
                for field in movement_ui.SemanticLiveGateIdentity.__dataclass_fields__
            }
            raw_identity["world_pack_profile"] = str(selected_profile.resolve())
            raw_identity["worker"] = str(worker.resolve())

            def gate_open(record, *, expected):
                return record.get("live_authority_enabled") is True

            with (
                patch.object(movement_ui, "WORKER", worker),
                patch.object(movement_ui, "SEMANTIC_GATE", gate),
                patch.object(movement_ui, "semantic_live_gate_open", side_effect=gate_open),
            ):
                state = movement_ui._semantic_gate_state_for_structure_summary(
                    {"semantic_gate_identity": raw_identity}, profile=profile,
                )

        self.assertEqual(state, "VALIDATION_PASS_AUTHORITY_DISABLED")

    def test_checkbox_can_only_rebind_an_unchanged_verified_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            validation = root / "validation.json"
            validation.write_text('{"status":"PASS"}', encoding="utf-8")
            profile = root / "profile.json"
            profile.write_text("{}", encoding="utf-8")
            worker = root / "worker.exe"
            worker.write_bytes(b"worker")
            expected = movement_ui.SemanticLiveGateIdentity(
                world_pack_profile=str(profile.resolve()),
                world_pack_profile_sha256=hashlib.sha256(profile.read_bytes()).hexdigest(),
                world_pack_profile_id="worldpack-runtime:test:v1",
                world_pack_id="wow.test.pack-v1",
                world_pack_content_sha256="a" * 64,
                target_profile="test_lab",
                client_version="2.4.3",
                client_build="2.4.3.8606",
                nav_profile_id="test-nav-v1",
                worker=str(worker.resolve()),
                worker_sha256=hashlib.sha256(worker.read_bytes()).hexdigest(),
            )
            disabled = movement_ui.build_semantic_live_gate_record(
                expected,
                validation_result=validation,
                status="PASS",
                live_authority_enabled=False,
            )
            enabled = movement_ui.rebind_semantic_live_gate_authority(
                disabled, expected=expected, enabled=True,
            )
            self.assertTrue(
                movement_ui.semantic_live_gate_open(enabled, expected=expected)
            )
            validation.write_text('{"status":"CHANGED"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                movement_ui.rebind_semantic_live_gate_authority(
                    disabled, expected=expected, enabled=True,
                )

    def test_control_center_start_rechecks_awareness_fail_closed(self) -> None:
        source = (RUNNER_PATH / "run_movement_engine_client.py").read_text(
            encoding="utf-8"
        )
        start = source[source.index("def start(self)") : source.index("def _set_running")]
        self.assertIn("self._apply_autonomous_start_readiness()", start)
        self.assertIn("if not ready:", start)
        self.assertNotIn("if not self._semantic_gate_open()", start)
        self.assertIn(
            "self._apply_autonomous_start_readiness(update_status=True)", source,
        )

    def test_control_center_validates_large_awareness_off_the_tk_thread(self) -> None:
        source = (RUNNER_PATH / "run_movement_engine_client.py").read_text(
            encoding="utf-8"
        )
        constructor = source[
            source.index("def __init__", source.index("class MovementEngineClient:")) :
            source.index("def _load_structure_awareness_background")
        ]
        self.assertIn(
            "Thread(target=self._load_structure_awareness_background, daemon=True).start()",
            constructor,
        )
        self.assertNotIn("_load_verified_structure_awareness()", constructor)
        worker = source[
            source.index("def _load_structure_awareness_background") :
            source.index("def _consume_structure_awareness_result")
        ]
        self.assertIn("self.structure_awareness_results.put", worker)
        self.assertNotIn("self.root.after", worker)
        refresh = source[source.index("def _refresh(self)") :]
        self.assertIn("self._consume_structure_awareness_result()", refresh)

        client = movement_ui.MovementEngineClient.__new__(
            movement_ui.MovementEngineClient
        )
        client.structure_awareness_loading = True
        with patch.object(
            movement_ui.MovementEngineClient,
            "_semantic_gate_open",
            side_effect=AssertionError("gate verification reached the Tk thread"),
        ):
            ready, label, _ = client._autonomous_start_readiness()
        self.assertFalse(ready)
        self.assertIn("VERIFIC HARTA", label)

    def test_background_awareness_completion_rearms_only_through_readiness(self) -> None:
        client = movement_ui.MovementEngineClient.__new__(
            movement_ui.MovementEngineClient
        )
        client.state = "STOPPED"
        client.structure_awareness_loading = True
        client._apply_autonomous_start_readiness = Mock()
        process = Mock()
        summary = {
            "event": "READY",
            "world_pack_id": "wow.test.pack",
            "world_pack_content_sha256": "a" * 64,
            "structure_index_id": "index:test",
            "structure_index_sha256": "b" * 64,
            "structure_count": 4,
            "wmo_count": 1,
            "doodad_count": 3,
            "graph_id": "graph:test",
            "graph_content_sha256": "c" * 64,
            "access_opening_count": 2,
            "execution_authority": False,
        }
        client._finish_structure_awareness_load(
            process=process,
            summary=summary,
            error=None,
        )
        self.assertIs(client.structure_awareness_service, process)
        self.assertIs(client.structure_awareness_summary, summary)
        self.assertFalse(client.structure_awareness_loading)
        client._apply_autonomous_start_readiness.assert_called_once_with(
            update_status=True
        )

    def test_structure_awareness_service_protocol_is_read_only_and_compact(self) -> None:
        ready = {
            "event": "READY",
            "world_pack_id": "wow.test.pack",
            "world_pack_content_sha256": "a" * 64,
            "structure_index_id": "index:test",
            "structure_index_sha256": "b" * 64,
            "structure_count": 2,
            "wmo_count": 1,
            "doodad_count": 1,
            "graph_id": "graph:test",
            "graph_content_sha256": "c" * 64,
            "access_opening_count": 1,
            "semantic_gate_identity": {
                "world_pack_profile": "C:\\fixture\\profile.json",
                "world_pack_profile_sha256": "d" * 64,
                "world_pack_profile_id": "profile:test",
                "world_pack_id": "wow.test.pack",
                "world_pack_content_sha256": "a" * 64,
                "target_profile": "tbc_243_lab",
                "client_version": "2.4.3",
                "client_build": "8606",
                "nav_profile_id": "nav:test",
                "worker": "C:\\fixture\\worker.exe",
                "worker_sha256": "e" * 64,
            },
            "execution_authority": False,
        }
        self.assertIs(movement_ui._validated_structure_service_ready(ready), ready)
        forged = dict(ready, execution_authority=True)
        with self.assertRaisesRegex(RuntimeError, "READY invalid"):
            movement_ui._validated_structure_service_ready(forged)

    def test_structure_awareness_worker_matches_allowlisted_graph_hash(self) -> None:
        profiles = movement_ui.load_world_map_registry(
            movement_ui.WORLD_MAP_REGISTRY,
            schema_path=movement_ui.WORLD_MAP_REGISTRY_SCHEMA,
        )
        azeroth = next(profile for profile in profiles if profile.map_id == 0)
        kalimdor = next(profile for profile in profiles if profile.map_id == 1)
        expansion = next(profile for profile in profiles if profile.map_id == 530)
        self.assertEqual(movement_ui._structure_awareness_worker(azeroth), movement_ui.WORKER)
        self.assertEqual(movement_ui._structure_awareness_worker(kalimdor), movement_ui.WORKER_V35)
        self.assertEqual(movement_ui._structure_awareness_worker(expansion), movement_ui.WORKER_V35)

        with tempfile.TemporaryDirectory() as directory:
            graph = Path(directory) / "graph.json"
            graph.write_text(
                json.dumps({"probe_worker_sha256": "0" * 64}),
                encoding="utf-8",
            )
            forged = SimpleNamespace(structure_access_graph=graph)
            with self.assertRaisesRegex(RuntimeError, "allowlisted"):
                movement_ui._structure_awareness_worker(forged)

        hits = (
            SimpleNamespace(
                structure=SimpleNamespace(
                    structure_id="0:wmo:1", kind="WMO",
                    asset_path="world/test/crypt.wmo", nav_coverage="PARTIAL",
                ),
                horizontal_distance_yards=0.0,
                vertical_distance_yards=0.0,
                contains_horizontal=True,
                contains_3d=True,
            ),
            SimpleNamespace(
                structure=SimpleNamespace(
                    structure_id="0:doodad:2", kind="DOODAD",
                    asset_path="world/test/tree.m2", nav_coverage="NONE",
                ),
                horizontal_distance_yards=4.0,
                vertical_distance_yards=0.0,
                contains_horizontal=False,
                contains_3d=False,
            ),
        )
        nearby = structure_service.build_nearby_response(
            request_id="nearby:test", hits=hits, include_hits=False,
        )
        self.assertEqual(nearby["wmo_count"], 1)
        self.assertEqual(nearby["obstacle_count"], 1)
        self.assertEqual(nearby["inside_wmo_asset"], "world/test/crypt.wmo")
        self.assertEqual(nearby["hits"], [])
        self.assertFalse(nearby["execution_authority"])
        self.assertIs(movement_ui._validated_structure_nearby(nearby), nearby)

    def test_dynamic_awareness_publishes_tracks_without_invented_world_range(self) -> None:
        track = DynamicEntityTrack(
            track_id="dynamic-screen:1",
            reaction="HOSTILE",
            first_observed_at_s=10.0,
            last_observed_at_s=10.2,
            expires_at_s=11.0,
            center_x_normalized=0.15,
            center_y_normalized=0.48,
            velocity_x_normalized_per_s=0.02,
            velocity_y_normalized_per_s=-0.01,
            width_normalized=0.12,
            height_normalized=0.02,
            position_uncertainty_normalized=0.04,
            confidence=0.91,
            observation_count=3,
            source_key="nameplate:fixture",
        )
        record = _dynamic_entity_awareness_record(
            (track,), observed_at_s=10.2, adapter_error=None,
        )
        ContractValidator(
            Path(__file__).parents[1]
            / "contracts" / "dynamic-entity-awareness.schema.json"
        ).validate(record)
        self.assertEqual(record["track_count"], 1)
        self.assertEqual(record["tracks"][0]["reaction"], "HOSTILE")
        self.assertIsNone(record["tracks"][0]["world_position"])
        self.assertIsNone(record["tracks"][0]["distance_yards"])
        self.assertFalse(record["execution_authority"])

    def test_external_ui_accepts_only_observed_non_authoritative_dynamic_tracks(self) -> None:
        record = _dynamic_entity_awareness_record(
            (), observed_at_s=42.0, adapter_error=None,
        )
        movement_state = {"dynamic_entity_awareness": record}
        self.assertIs(
            movement_ui._read_dynamic_entity_awareness(movement_state),
            record,
        )

        record["execution_authority"] = True
        self.assertIsNone(
            movement_ui._read_dynamic_entity_awareness(movement_state)
        )
        record["execution_authority"] = False
        record["tracks"] = [{
            "reaction": "HOSTILE",
            "world_position": [1.0, 2.0, 3.0],
            "distance_yards": 4.0,
        }]
        record["track_count"] = 1
        self.assertIsNone(
            movement_ui._read_dynamic_entity_awareness(movement_state)
        )

    def test_dynamic_awareness_text_rejects_stale_and_previous_boot_records(self) -> None:
        record = _dynamic_entity_awareness_record(
            (), observed_at_s=100.0, adapter_error=None,
        )
        fresh = movement_ui._dynamic_awareness_text(
            record, now_monotonic_s=100.5,
        )
        self.assertIn("visible/last_seen: 0", fresh)
        self.assertIn("screen-space", fresh)

        stale = movement_ui._dynamic_awareness_text(
            record, now_monotonic_s=102.0,
        )
        self.assertIn("snapshot expirat", stale)
        previous_boot = movement_ui._dynamic_awareness_text(
            record, now_monotonic_s=10.0,
        )
        self.assertIn("snapshot expirat", previous_boot)

    def test_control_center_reports_range_band_not_an_invented_exact_distance(self) -> None:
        record = selected_target_melee_range_awareness(
            target_identity_crc16=4567,
            observed_monotonic_s=30.0,
            expires_monotonic_s=30.6,
            ability_witnesses={
                "rogue.auto_attack": False,
                "rogue.sinister_strike": False,
            },
        )
        movement_state = {"selected_target_range_awareness": record}
        self.assertIs(
            movement_ui._read_selected_target_range_awareness(movement_state),
            record,
        )
        text = movement_ui._selected_target_range_text(
            record,
            now_monotonic_s=30.5,
            target_identity_crc16=4567,
        )
        self.assertIn(">5 yd", text)
        self.assertIn("exact indisponibil", text)

        self.assertIn(
            "alt target",
            movement_ui._selected_target_range_text(
                record,
                now_monotonic_s=30.5,
                target_identity_crc16=9999,
            ),
        )
        self.assertIn(
            "expirat",
            movement_ui._selected_target_range_text(
                record,
                now_monotonic_s=31.0,
                target_identity_crc16=4567,
            ),
        )

    def test_control_center_rejects_authoritative_or_exact_range_claims(self) -> None:
        record = selected_target_melee_range_awareness(
            target_identity_crc16=4567,
            observed_monotonic_s=30.0,
            expires_monotonic_s=30.6,
            ability_witnesses={"rogue.auto_attack": True},
        )
        movement_state = {"selected_target_range_awareness": record}
        record["exact_distance_yards"] = 3.0
        self.assertIsNone(
            movement_ui._read_selected_target_range_awareness(movement_state)
        )
        record["exact_distance_yards"] = None
        record["execution_authority"] = True
        self.assertIsNone(
            movement_ui._read_selected_target_range_awareness(movement_state)
        )

    def test_control_center_reads_permanent_observer_pose_experience(self) -> None:
        summary = {
            "record_type": "dynamic_experience_summary",
            "schema_version": "2.0",
            "database_schema_version": 2,
            "map_name": "Azeroth",
            "navmesh_sha256": "A" * 64,
            "observation_count": 3,
            "reaction_counts": {
                "HOSTILE": 2,
                "NEUTRAL": 1,
                "FRIENDLY": 0,
                "UNKNOWN": 0,
            },
            "last_observed_at_utc": "2026-08-28T12:00:00Z",
            "experience_semantics": (
                "APPEND_ONLY_OBSERVER_POSE_ENCOUNTER_MEMORY"
            ),
            "entity_position_semantics": "UNKNOWN_NOT_INFERRED",
            "execution_authority": False,
        }
        state = {"dynamic_experience_summary": summary}
        self.assertIs(
            movement_ui._read_dynamic_experience_summary(state),
            summary,
        )
        text = movement_ui._dynamic_experience_text(summary)
        self.assertIn("3 întâlniri", text)
        self.assertIn("poziția entității necunoscută", text)

        summary["reaction_counts"]["HOSTILE"] = 3
        self.assertIsNone(movement_ui._read_dynamic_experience_summary(state))

    def test_roaming_runner_persists_only_mature_observed_dynamic_tracks(self) -> None:
        runner = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("DynamicExperienceStore", runner)
        self.assertIn("track.observation_count < 2", runner)
        self.assertIn("encounter_from_track", runner)
        self.assertIn(
            "dynamic_experience_summary=dynamic_experience_summary",
            runner,
        )
        self.assertIn("observer_world_z=None", runner)

    def test_external_ui_reads_only_non_authoritative_structure_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "movement.json"
            state.write_text(json.dumps({
                "structure_access_awareness": {
                    "graph_id": "wow.test.pack:Map:structure-access-v1",
                    "graph_content_sha256": "a" * 64,
                    "coverage_state": "PARTIAL_OBSERVED_COMPONENTS",
                    "applicable_to_live_pose": True,
                    "known_opening_count": 2,
                    "known_openings": [],
                    "physical_door_semantics": "UNKNOWN_NOT_INFERRED",
                    "execution_authority": False,
                },
            }), encoding="utf-8")
            with patch.object(movement_ui, "MOVEMENT_STATE", state):
                record = movement_ui._read_structure_access()
                self.assertIsNotNone(record)
                self.assertEqual(record["known_opening_count"], 2)
                raw = json.loads(state.read_text(encoding="utf-8"))
                raw["structure_access_awareness"]["execution_authority"] = True
                state.write_text(json.dumps(raw), encoding="utf-8")
                self.assertIsNone(movement_ui._read_structure_access())

    def test_external_ui_centers_3d_navmesh_viewer_on_exact_live_position(self) -> None:
        snapshot = movement_ui.MovementLabSnapshot(
            observed_monotonic_s=1.0,
            tracking_state="LOST",
            target_identity_crc16=None,
            target_error_x_normalized=None,
            player_world_x=1843.2786594,
            player_world_y=1591.8289421,
            player_world_z=93.680946,
        )

        arguments = movement_ui._nav_viewer_arguments(snapshot)

        self.assertEqual(arguments[2], "--world-pack")
        self.assertEqual(arguments[3], "--- Azeroth")
        self.assertEqual(arguments[4:], ["1843.278659", "1591.828942", "93.680946"])
        self.assertEqual(
            Path(arguments[1]).name,
            "tbc243-azeroth-full-v3",
        )
        self.assertFalse(any("WoW TBC 2.4.3\\Data" in item for item in arguments))

    def test_external_ui_refuses_3d_viewer_without_player_position(self) -> None:
        snapshot = movement_ui.MovementLabSnapshot(
            observed_monotonic_s=1.0,
            tracking_state="LOST",
            target_identity_crc16=None,
            target_error_x_normalized=None,
        )
        with self.assertRaisesRegex(ValueError, "poziția"):
            movement_ui._nav_viewer_arguments(snapshot)

    def test_fresh_hud_position_supersedes_stale_journey_position_for_3d_viewer(self) -> None:
        snapshot = movement_ui.MovementLabSnapshot(
            observed_monotonic_s=1.0,
            tracking_state="LOST",
            target_identity_crc16=None,
            target_error_x_normalized=None,
            player_world_x=100.0,
            player_world_y=200.0,
            player_world_z=93.5,
        )
        arguments = movement_ui._nav_viewer_arguments(
            snapshot, fresh_world_position=(1845.125, 1594.75),
        )
        self.assertEqual(arguments[4:], ["1845.125000", "1594.750000", "93.500000"])

    def test_live_3d_viewer_receives_atomic_state_path_after_z_placeholder(self) -> None:
        snapshot = movement_ui.MovementLabSnapshot(
            observed_monotonic_s=1.0,
            tracking_state="LOST",
            target_identity_crc16=None,
            target_error_x_normalized=None,
            player_world_x=1845.125,
            player_world_y=1594.75,
        )
        state_path = Path("nav-viewer-state.txt")
        arguments = movement_ui._nav_viewer_arguments(
            snapshot, live_state_path=state_path,
        )
        self.assertEqual(arguments[4:7], ["1845.125000", "1594.750000", "auto"])
        self.assertEqual(Path(arguments[7]), state_path)

    def test_live_viewer_state_protocol_is_bounded_and_read_only(self) -> None:
        state = nav_viewer_bridge.bridge_state_text(
            sequence=7,
            observed_monotonic_s=42.5,
            world_x=1843.25,
            world_y=1591.75,
            facing_rad=1.25,
            facing_source="COORDINATE_HUD_EXACT",
            facing_confidence=1.0,
            corridor=((1843.25, 1591.75), (1845.0, 1593.0)),
            awareness_walls=((1.0, 2.0, 3.0, 4.0, 5.0, 6.0),),
            awareness_egresses=((7.0, 8.0, 9.0, 10.0, 11.0, 12.0),),
        )
        self.assertEqual(state.splitlines()[0], "PA_NAV_VIEWER_STATE 2")
        self.assertIn("sequence 7", state)
        self.assertIn("corridor 2", state)
        self.assertIn("walls 1", state)
        self.assertIn("egresses 1", state)
        self.assertIn("\nend\n", state)
        self.assertIn("facing_source COORDINATE_HUD_EXACT", state)
        source = (RUNNER_PATH / "run_nav_viewer_live_bridge.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("SendInput", source)
        self.assertNotIn("execution_gateway", source)

    def test_live_viewer_bridge_defaults_to_viewer_bound_lifetime(self) -> None:
        args = nav_viewer_bridge.build_parser().parse_args(["--viewer-pid", "123"])
        self.assertEqual(args.maximum_duration_s, 0.0)
        source = (RUNNER_PATH / "run_nav_viewer_live_bridge.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("args.maximum_duration_s == 0.0", source)

    def test_control_center_live_map_renews_before_read_authority_expires(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            authorization = Path(directory) / "authorization.json"
            authorization.write_text(json.dumps({
                "approval": {
                    "expires_at": "2026-09-03T20:30:00Z",
                },
            }), encoding="utf-8")
            remaining = movement_ui._session_authorization_remaining_s(
                authorization,
                now=datetime(2026, 9, 3, 20, 25, tzinfo=timezone.utc),
            )
        self.assertEqual(remaining, 300.0)
        source = (RUNNER_PATH / "run_movement_engine_client.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("_schedule_live_map_session_renewal()", source)
        renewal = source[
            source.index("def _renew_live_map_session") :
            source.index("def _consume_live_map_session_renewal")
        ]
        self.assertIn('"--renewal-parent-sha256", parent_sha', renewal)
        self.assertIn('"-AcknowledgeSessionIdentity"', renewal)

    def test_live_viewer_bridge_accepts_map_bound_transform_selection(self) -> None:
        args = nav_viewer_bridge.build_parser().parse_args([
            "--viewer-pid", "123", "--map-id", "1", "--expected-zone-index", "14",
        ])
        self.assertEqual(args.map_id, 1)
        self.assertEqual(args.expected_zone_index, 14)

    def test_live_viewer_protocol_three_separates_conditional_boundaries(self) -> None:
        boundary = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
        state = nav_viewer_bridge.bridge_state_text(
            sequence=8,
            observed_monotonic_s=43.0,
            world_x=-187.2,
            world_y=2139.88,
            facing_rad=1.0,
            facing_source="COORDINATE_HUD_EXACT",
            corridor=(),
            conditional_boundaries=(boundary,),
            protocol_version=3,
        )

        self.assertEqual(state.splitlines()[0], "PA_NAV_VIEWER_STATE 3")
        self.assertIn("conditional_boundaries 1", state)
        self.assertIn("conditional_boundary 1.000000 2.000000", state)
        with self.assertRaises(ValueError):
            nav_viewer_bridge.bridge_state_text(
                sequence=8,
                observed_monotonic_s=43.0,
                world_x=0,
                world_y=0,
                facing_rad=None,
                corridor=(),
                conditional_boundaries=(boundary,),
                protocol_version=2,
            )

    def test_live_viewer_bridge_receives_standalone_async_awareness_inputs(self) -> None:
        snapshot = movement_ui.MovementLabSnapshot(
            observed_monotonic_s=1.0,
            tracking_state="LOST",
            target_identity_crc16=None,
            target_error_x_normalized=None,
            player_world_x=2220.9,
            player_world_y=629.19,
            player_world_z=33.74,
        )
        launch = SimpleNamespace(
            nav_root=Path("world-pack/nav"), internal_name="Azeroth", map_id=0,
        )

        arguments = movement_ui._nav_viewer_bridge_arguments(
            viewer_pid=1234, snapshot=snapshot, launch=launch,
        )

        self.assertEqual(arguments[arguments.index("--state-protocol") + 1], "5")
        self.assertEqual(
            Path(arguments[arguments.index("--awareness-nav-root") + 1]),
            launch.nav_root,
        )
        self.assertEqual(
            arguments[arguments.index("--initial-world-z") + 1], "33.74",
        )
        self.assertEqual(arguments[arguments.index("--map-id") + 1], "0")
        self.assertIn("--zone-transform-catalog", arguments)

    def test_live_viewer_protocol_four_separates_plan_from_observed_trail(self) -> None:
        state = nav_viewer_bridge.bridge_state_text(
            sequence=9,
            observed_monotonic_s=44.0,
            world_x=10.0,
            world_y=20.0,
            facing_rad=0.5,
            facing_source="COORDINATE_HUD_EXACT",
            corridor=((10.0, 20.0), (12.0, 20.0)),
            traversed_path=((8.0, 19.0), (10.0, 20.0)),
            protocol_version=4,
        )

        self.assertEqual(state.splitlines()[0], "PA_NAV_VIEWER_STATE 4")
        self.assertIn("corridor 2", state)
        self.assertIn("trail 2", state)
        self.assertIn("trail_point 8.000000 19.000000", state)

    def test_live_viewer_protocol_five_separates_body_and_camera_yaw(self) -> None:
        state = nav_viewer_bridge.bridge_state_text(
            sequence=10,
            observed_monotonic_s=45.0,
            world_x=10.0,
            world_y=20.0,
            facing_rad=0.5,
            facing_source="MINIMAP_VISION_FALLBACK",
            facing_confidence=0.8,
            camera_yaw_estimate_rad=0.8,
            corridor=(),
            protocol_version=5,
        )

        self.assertEqual(state.splitlines()[0], "PA_NAV_VIEWER_STATE 5")
        self.assertIn("facing 0.500000000", state)
        self.assertIn("camera_yaw 0.800000000", state)
        self.assertIn("facing_source MINIMAP_VISION_FALLBACK", state)
        with self.assertRaises(ValueError):
            nav_viewer_bridge.bridge_state_text(
                sequence=10,
                observed_monotonic_s=45.0,
                world_x=10.0,
                world_y=20.0,
                facing_rad=0.5,
                camera_yaw_estimate_rad=0.8,
                corridor=(),
                protocol_version=4,
            )

    def test_live_viewer_decimates_long_trail_without_losing_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "movement-lab.json"
            points = [[float(index), float(index % 7)] for index in range(900)]
            path.write_text(json.dumps({
                "observed_monotonic_s": 100.0,
                "traversed_path_world": points,
            }), encoding="utf-8")

            trail = nav_viewer_bridge._fresh_traversed_path(
                path, now_s=100.5,
            )

        self.assertEqual(
            len(trail), nav_viewer_bridge.VIEWER_TRAIL_MAX_POINTS,
        )
        self.assertEqual(trail[0], (0.0, 0.0))
        self.assertEqual(trail[-1], (899.0, 3.0))

    def test_live_viewer_reuses_fresh_navigation_pose_without_second_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "movement-lab.json"
            path.write_text(json.dumps({
                "observed_monotonic_s": 100.0,
                "player_world": [1845.25, 1594.75, 92.0],
                "player_facing_rad": 0.25,
                "body_facing_rad": 1.5,
                "body_facing_source": "COORDINATE_HUD_EXACT",
                "camera_yaw_estimate_rad": 1.25,
                "camera_yaw_source": "MOUSE_INTEGRATED_ESTIMATE",
                "topographic_brain": {
                    "actor": {
                        "body_facing_rad": 1.5,
                        "body_facing_source": "COORDINATE_HUD_EXACT",
                    },
                },
            }), encoding="utf-8")

            fresh = nav_viewer_bridge._fresh_movement_pose(path, now_s=100.5)
            stale = nav_viewer_bridge._fresh_movement_pose(path, now_s=101.0)

        self.assertEqual(
            fresh,
            (
                100.0, 1845.25, 1594.75, 1.5,
                "COORDINATE_HUD_EXACT", 1.0, 1.25,
            ),
        )
        self.assertIsNone(stale)

    def test_live_viewer_never_labels_controller_heading_as_body_facing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "movement-lab.json"
            path.write_text(json.dumps({
                "observed_monotonic_s": 100.0,
                "player_world": [1845.25, 1594.75, 92.0],
                "player_facing_rad": 0.25,
                "topographic_brain": {
                    "actor": {
                        "body_facing_rad": None,
                        "body_facing_source": "UNAVAILABLE",
                    },
                },
            }), encoding="utf-8")
            pose = nav_viewer_bridge._fresh_movement_pose(path, now_s=100.5)

        self.assertEqual(
            pose,
            (100.0, 1845.25, 1594.75, None, None, None, None),
        )

    def test_live_viewer_yields_capture_during_navigation_startup_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "continuity.json"
            path.write_text(json.dumps({"status": "STARTING"}), encoding="utf-8")
            modified = path.stat().st_mtime

            active = nav_viewer_bridge._navigation_owns_capture(
                path, now_wall_s=modified + 1.0,
            )
            stale = nav_viewer_bridge._navigation_owns_capture(
                path, now_wall_s=modified + 6.0,
            )

        self.assertTrue(active)
        self.assertFalse(stale)

    def test_live_awareness_frame_preserves_persistent_server_topology(self) -> None:
        frame = nav_viewer_bridge._awareness_frame_from_server_response({
            "status": "OK",
            "sequence": 7,
            "source": [10.0, 20.0, 30.25],
            "resolved": [10.0, 20.0, 30.0],
            "walls": [[[8.0, 19.0, 30.0], [8.0, 22.0, 30.0]]],
            "transitions": [[[14.0, 19.0, 30.0], [14.0, 22.0, 30.0]]],
            "egresses": [[[14.0, 19.0, 30.0], [14.0, 22.0, 30.0]]],
        }, expected_sequence=7, observed_monotonic_s=42.0)

        self.assertEqual(frame.resolved_z, 30.0)
        self.assertEqual(frame.walls, ((8.0, 19.0, 30.0, 8.0, 22.0, 30.0),))
        self.assertEqual(len(frame.transitions), 1)
        self.assertEqual(len(frame.egresses), 1)

    def test_awareness_sampling_is_driven_by_pose_change_not_a_timer(self) -> None:
        probe = nav_viewer_bridge.AsyncLocalAwarenessProbe.__new__(
            nav_viewer_bridge.AsyncLocalAwarenessProbe
        )
        probe._last_requested = (10.0, 20.0, 30.0)
        probe._movement_threshold_yards = 1.5
        probe._floor_threshold_yards = 0.5

        self.assertFalse(probe._needs_sample(10.0, 20.0, 30.0))
        self.assertFalse(probe._needs_sample(10.5, 20.5, 30.2))
        self.assertTrue(probe._needs_sample(11.5, 20.0, 30.0))
        self.assertTrue(probe._needs_sample(10.0, 20.0, 30.5))

    def test_awareness_bridge_uses_one_persistent_native_server(self) -> None:
        source = (RUNNER_PATH / "persistent_navmesh_awareness.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"--awareness-server"', source)
        self.assertIn("creationflags=nav_worker_creation_flags()", source)
        self.assertIn('process.stdin.write("QUIT\\n")', source)
        self.assertNotIn("subprocess.run(", source)

    def test_persistent_awareness_worker_receives_below_normal_priority(self) -> None:
        class FakeProcess:
            pid = 1234

            def __init__(self) -> None:
                self.stdin = io.StringIO()
                self.stdout = io.StringIO('{"status":"READY","protocol":1}\n')

            def poll(self) -> int | None:
                return None

            def wait(self, timeout: float | None = None) -> int:
                return 0

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.exe"
            worker.write_bytes(b"fixture")
            with patch.object(
                persistent_awareness.subprocess,
                "Popen",
                return_value=FakeProcess(),
            ) as launch:
                service = persistent_awareness.PersistentNavmeshAwarenessService(
                    worker=worker,
                    nav_root=root,
                    map_name="Azeroth",
                )
                service.close()
            self.assertEqual(
                launch.call_args.kwargs["creationflags"],
                persistent_awareness.nav_worker_creation_flags(),
            )

    def test_persistent_awareness_supplies_full_controller_environment(self) -> None:
        radial = [
            {
                "bearing_rad": index * tau / 16,
                "clearance_yards": 4.0,
                "navmesh_reachable": True,
            }
            for index in range(16)
        ]
        sample = persistent_awareness.awareness_sample_from_server_response({
            "status": "OK",
            "sequence": 3,
            "vertical_candidates": {
                "schema_version": 1,
                "source": "CLIENT_ASSET_HEIGHT_QUERY",
                "exhaustive": False,
                "selected_surface_z": 30.25,
                "heights": [30.25, 42.0],
            },
            "source": [10.0, 20.0, 30.25],
            "resolved": [10.0, 20.0, 30.0],
            "awareness": {
                "physical_surfaces": ["wmo"],
                "probe_radius_yards": 12.0,
                "overhead_clear": False,
                "radial_probes": radial,
                "topology_radius_yards": 60.0,
                "component_polygon_count": 14,
                "component_truncated": False,
                "wall_segments_truncated": False,
                "surface_transition_portals_truncated": False,
                "egress_inference_complete": True,
                "egress_portals_truncated": False,
                "wall_segments": [],
                "surface_transition_portals": [],
                "egress_portals": [],
            },
        }, expected_sequence=3, observed_monotonic_s=42.0)

        self.assertEqual(sample.resolved.z, 30.0)
        self.assertEqual(sample.vertical_candidates.heights, (30.25, 42.0))
        self.assertIsNone(sample.vertical_candidates.to_record()["confirmed_floor_id"])
        self.assertEqual(
            sample.awareness.environment_class, "WMO_STRUCTURE_OR_TRANSITION"
        )
        self.assertEqual(sample.awareness.physical_surfaces, frozenset({"wmo"}))

    def test_roaming_applies_live_awareness_before_each_steering_decision(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        apply_index = source.index("local_sample = live_awareness.poll(")
        decide_index = source.index("intent = engine.decide(", apply_index)
        self.assertLess(apply_index, decide_index)
        self.assertIn("start_awareness=local_sample.awareness", source)
        self.assertIn("live_awareness.close()", source)

    def test_stationary_floor_hint_uses_spatial_not_temporal_applicability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "movement.json"
            state.write_text(json.dumps({
                "observed_monotonic_s": 1.0,
                "player_world": [100.5, 200.5, 33.75],
            }), encoding="utf-8")

            nearby = nav_viewer_bridge._movement_floor_hint(
                state, world_x=100.0, world_y=200.0, fallback_z=10.0,
            )
            far = nav_viewer_bridge._movement_floor_hint(
                state, world_x=120.0, world_y=220.0, fallback_z=10.0,
            )

        self.assertEqual(nearby, 33.75)
        self.assertEqual(far, 10.0)

    def test_external_overlay_has_graceful_revisioned_shutdown(self) -> None:
        source = (RUNNER_PATH / "run_movement_engine_client.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('self._write_overlay_command("STOP")', source)
        self.assertIn('"--control-file", str(OVERLAY_CONTROL)', source)
        self.assertLess(
            source.index('self._write_overlay_command("STOP")'),
            source.index("self.overlay_process.terminate()"),
        )

    def test_live_viewer_treats_pose_decode_errors_as_transient(self) -> None:
        source = (RUNNER_PATH / "run_nav_viewer_live_bridge.py").read_text(
            encoding="utf-8"
        )
        loop = source[source.index("while (") : source.index("finally:", source.index("while ("))]
        self.assertLess(loop.index("try:"), loop.index("_position("))
        self.assertLess(loop.index("_position("), loop.index("except ("))
        self.assertIn("ValueError,", loop)
        self.assertIn("KeyError,", loop)
        self.assertIn("OSError,", loop)

    def test_live_viewer_session_fingerprint_changes_with_rotated_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            authorization = root / "authorization.json"
            receipt = root / "receipt.json"
            authorization.write_text('{"generation":1}', encoding="utf-8")
            receipt.write_text('{"generation":1}', encoding="utf-8")
            before = nav_viewer_bridge._session_binding_fingerprint(
                authorization, receipt,
            )
            receipt.write_text('{"generation":2}', encoding="utf-8")
            after = nav_viewer_bridge._session_binding_fingerprint(
                authorization, receipt,
            )
        self.assertNotEqual(before, after)

    def test_live_viewer_retries_when_session_rotates_while_opening(self) -> None:
        first_source = Mock()
        second_source = Mock()
        with (
            patch.object(
                nav_viewer_bridge,
                "_session_binding_fingerprint",
                side_effect=[("auth-1", "receipt-1"), ("auth-2", "receipt-2"),
                             ("auth-2", "receipt-2"), ("auth-2", "receipt-2")],
            ),
            patch.object(nav_viewer_bridge, "_read_object", return_value={}),
            patch.object(
                nav_viewer_bridge,
                "LiveCoordinatePoseSource",
                side_effect=[first_source, second_source],
            ) as source_factory,
        ):
            source, fingerprint = nav_viewer_bridge._open_pose_source(
                authorization_file=Path("authorization.json"),
                receipt_file=Path("receipt.json"),
            )
        self.assertIs(source, second_source)
        self.assertEqual(fingerprint, ("auth-2", "receipt-2"))
        first_source.close.assert_called_once_with()
        second_source.open.assert_called_once_with()
        self.assertEqual(source_factory.call_count, 2)
        self.assertTrue(
            all(
                call.kwargs["require_foreground_capture"] is False
                for call in source_factory.call_args_list
            )
        )

    def test_live_bridge_retries_a_transient_windows_atomic_replace_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.txt"
            with (
                patch.object(
                    nav_viewer_bridge.os,
                    "replace",
                    side_effect=[PermissionError("busy"), None],
                ) as replace,
                patch.object(nav_viewer_bridge.time, "sleep") as sleep,
            ):
                nav_viewer_bridge._atomic_text(path, "state\n")
            self.assertEqual(replace.call_count, 2)
            sleep.assert_called_once_with(0.005)

    def test_native_viewer_allows_atomic_live_state_replacement(self) -> None:
        source = Path(
            r"E:\WoWserver\PerfectAssassin-Dependencies\navigation\namigator"
            r"\MapViewer\main.cpp"
        ).read_text(encoding="utf-8")
        live_reader = source[
            source.index("bool ReadLiveViewerState") :
            source.index("// this is the main message handler")
        ]
        self.assertIn("FILE_SHARE_DELETE", live_reader)
        self.assertIn("CreateFileW", live_reader)
        self.assertNotIn("std::ifstream input(", live_reader)

    def test_native_viewer_marks_and_auto_centers_the_live_predator_pose(self) -> None:
        root = Path(
            r"E:\WoWserver\PerfectAssassin-Dependencies\navigation\namigator"
            r"\MapViewer"
        )
        source = (root / "main.cpp").read_text(encoding="utf-8")
        renderer = (root / "Renderer.hpp").read_text(encoding="utf-8")
        self.assertIn("PlayerGeometry", renderer)
        self.assertIn("void UpdatePlayerMarker()", source)
        self.assertIn("gRenderer->AddPlayerMarker", source)
        self.assertIn("gCameraOrbitOffset", source)
        self.assertIn("gCameraOrbitTargetOffset", source)
        self.assertIn("ViewerCameraFacing() + PI", source)
        self.assertIn("SegmentOccluded", renderer)
        self.assertIn("Renderer::CollidableGeometryFlag", source)
        self.assertIn("SelectComboItem(Controls::MapsCombo, startupMap)", source)
        self.assertIn(
            "if (!firstLiveState && !poseChanged && !facingChanged &&\n"
            "        !cameraYawChanged && !corridorChanged &&\n"
            "        !trailChanged &&\n        !awarenessChanged)",
            source,
        )
        self.assertIn("if (firstLiveState && gFollowPlayer)", source)
        self.assertIn("EnsureAdtNeighborhoodLoaded(startupX, startupY)", source)
        self.assertIn("EnsureAdtNeighborhoodLoaded(state.WorldX, state.WorldY)", source)
        self.assertIn("PlayerOutlineGeometry", renderer)
        self.assertIn("PlayerOutlineColor", renderer)
        self.assertIn("CameraDirectionGeometry", renderer)
        self.assertIn("CameraDirectionColor", renderer)
        self.assertIn("gRenderer->AddCameraDirection", source)
        self.assertIn('key != "camera_yaw"', source)
        self.assertIn('line != "PA_NAV_VIEWER_STATE 5"', source)
        self.assertIn("AwarenessWallGeometry", renderer)
        self.assertIn("AwarenessTransitionGeometry", renderer)
        self.assertIn("AwarenessEgressGeometry", renderer)
        self.assertIn("SetRenderAwareness", renderer)
        self.assertIn("UpdateAwarenessGeometry", source)
        self.assertIn('"Local awareness (walls / exits)"', source)
        renderer_source = (root / "Renderer.cpp").read_text(encoding="utf-8")
        self.assertIn("D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST", renderer_source)
        self.assertIn("m_awarenessDepthStencilState", renderer_source)
        self.assertIn(
            "m_deviceContext->OMSetDepthStencilState(m_depthStencilState, 0)",
            renderer_source,
        )
        self.assertIn("const auto makeArrow", source)
        self.assertIn("makeArrow(7.f, 0.65f, 1.9f, 0.82f", source)
        self.assertIn("makeArrow(5.9f, 0.55f, 1.4f, 0.48f", source)
        self.assertIn("result.reserve(8)", source)
        self.assertIn("{0.12f, 0.55f, 1.0f, 1.f}", renderer)
        self.assertNotIn("m_overlayDepthStencilState", renderer)
        self.assertIn("constexpr float groundLift = 1.2f", source)
        self.assertIn('gLivePoseFresh ? "LIVE" : "LAST KNOWN"', source)
        self.assertNotIn("beaconHeight", source)
        self.assertIn("DiscoverAvailableMapLabels", source)
        self.assertIn('entry.path().extension() != ".map"', source)
        self.assertIn("parser::sMpqManager.GetMapId(internalName)", source)
        self.assertNotIn('maps.emplace_back("571 Northrend")', source)
        self.assertIn("CenterCameraOnPlayer();", source)
        self.assertIn("DrawNavMeshPhysicalClass", source)
        self.assertIn("Renderer::MeshSurface::Ground", source)
        self.assertIn("Renderer::MeshSurface::Wmo", source)
        self.assertIn("Renderer::MeshSurface::Doodad", source)
        self.assertIn("MeshLiquidColor", renderer)
        self.assertIn("MeshWmoColor", renderer)
        self.assertIn("MeshDoodadColor", renderer)
        self.assertIn("{0.05f, 0.92f, 0.88f, 0.72f}", renderer)
        self.assertIn('"Player view (game)"', source)
        self.assertIn("CameraMode::PlayerView", source)
        self.assertIn("CameraAimPoint", source)
        self.assertIn("gHasCameraOrbitFacing ? gCameraOrbitFacing", source)
        self.assertIn("#define START_WIDTH  800", source)
        self.assertIn("#define START_HEIGHT 560", source)
        self.assertIn("rect->bottom + 10", source)
        self.assertIn("DrawNavMeshPhysicalClass", source)
        self.assertIn("Renderer::MeshSurface::Ground", source)
        self.assertIn("Renderer::MeshSurface::Wmo", source)
        self.assertIn("Renderer::MeshSurface::Doodad", source)
        self.assertIn("MeshLiquidColor", renderer)
        self.assertIn("MeshWmoColor", renderer)
        self.assertIn("MeshDoodadColor", renderer)
        self.assertIn("{0.05f, 0.92f, 0.88f, 0.72f}", renderer)

    def test_live_viewer_rejects_stale_corridor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "movement.json"
            state_path.write_text(json.dumps({
                "observed_monotonic_s": 10.0,
                "corridor_centerline_world": [[1.0, 2.0], [3.0, 4.0]],
            }), encoding="utf-8")
            self.assertEqual(
                nav_viewer_bridge._fresh_corridor(state_path, now_s=11.001), ()
            )
            self.assertEqual(
                nav_viewer_bridge._fresh_corridor(state_path, now_s=10.5),
                ((1.0, 2.0), (3.0, 4.0)),
            )

    def test_live_viewer_reads_only_fresh_bounded_awareness_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "movement.json"
            state_path.write_text(json.dumps({
                "observed_monotonic_s": 10.0,
                "local_static_awareness": {
                    "available": True,
                    "wall_segments": [{
                        "left": [1.0, 2.0, 3.0],
                        "right": [4.0, 5.0, 6.0],
                    }],
                    "surface_transition_portals": [{
                        "left": [7.0, 8.0, 9.0],
                        "right": [10.0, 11.0, 12.0],
                    }],
                    "egress_portals": [{
                        "left": [13.0, 14.0, 15.0],
                        "right": [16.0, 17.0, 18.0],
                    }],
                },
            }), encoding="utf-8")

            walls, transitions, egresses = (
                nav_viewer_bridge._fresh_awareness_segments(
                    state_path, now_s=10.5,
                )
            )

            self.assertEqual(walls, ((1.0, 2.0, 3.0, 4.0, 5.0, 6.0),))
            self.assertEqual(transitions[0][0], 7.0)
            self.assertEqual(egresses[0][-1], 18.0)
            self.assertEqual(
                nav_viewer_bridge._fresh_awareness_segments(
                    state_path, now_s=11.001,
                ),
                ((), (), ()),
            )

    def test_nav_viewer_pose_once_is_read_only_and_uses_exact_atlas_transform(self) -> None:
        observation = {
            "timing": {"observed_monotonic_s": 42.5},
            "position": {"x": 0.5, "y": 0.5, "facing_rad": 1.25},
        }
        record = nav_viewer_pose.pose_record(observation, expected_zone_index=25)
        expected = tbc243_zone_transform(2, 25).world_from_normalized(0.5, 0.5)
        self.assertEqual(record["record_type"], "nav_viewer_pose")
        self.assertEqual(record["world_position"], list(expected))
        self.assertEqual(record["source"], "visible_coordinate_hud_read_only")
        self.assertIs(record["execution_authority"], False)
        source = (RUNNER_PATH / "run_nav_viewer_pose_once.py").read_text(encoding="utf-8")
        self.assertNotIn("SendInput", source)
        self.assertNotIn("execution_gateway", source)

    def test_nav_viewer_pose_once_resolves_non_tirisfal_map_transform(self) -> None:
        observation = {
            "timing": {"observed_monotonic_s": 42.5},
            "position": {
                "x": 0.5,
                "y": 0.5,
                "facing_rad": 1.25,
                "continent_index": 1,
            },
        }
        record = nav_viewer_pose.pose_record(
            observation,
            expected_zone_index=14,
            map_id=1,
            map_name="Kalimdor",
        )
        transform = _load_zone_transform(
            Path(__file__).parents[1]
            / "config/pose/world-map-zone-transforms-tbc243-8606.json",
            map_id=1,
            zone_index=14,
        )
        expected = transform.world_from_normalized(0.5, 0.5)
        self.assertEqual(record["map_name"], "Kalimdor")
        self.assertEqual(record["continent_index"], 1)
        self.assertEqual(record["zone_index"], 14)
        self.assertEqual(record["world_position"], list(expected))

    def test_external_ui_loads_all_semantic_destinations_from_exact_atlas_catalog(self) -> None:
        locations = movement_ui.MovementEngineClient._load_semantic_locations()
        self.assertEqual(locations["settlement:brill"], ("Brill", 2259.25, 290.43))
        self.assertEqual(
            locations["landmark:brill-south-road-bend"],
            ("Brill South Road Bend", 2043.75, 285.416656),
        )

    def test_catalog_exposes_reviewed_road_landmarks_as_semantic_destinations(self) -> None:
        locations = movement_ui.MovementEngineClient._load_semantic_locations()
        expected = {
            "landmark:deathknell-south-gate": ("Deathknell South Gate", 1900.0, 1400.0),
        }
        for destination_id, location in expected.items():
            self.assertEqual(locations[destination_id], location)

    def test_live_semantic_gate_is_bound_to_exact_world_pack_and_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile.json"
            profile.write_text("{}", encoding="utf-8")
            worker = root / "worker.exe"
            worker.write_bytes(b"worker")
            result = root / "result.json"
            result.write_text('{"status":"PASS"}', encoding="utf-8")
            gate = root / "gate.json"
            expected = movement_ui.SemanticLiveGateIdentity(
                world_pack_profile=str(profile.resolve()),
                world_pack_profile_sha256=hashlib.sha256(profile.read_bytes()).hexdigest(),
                world_pack_profile_id="worldpack-runtime:test:v1",
                world_pack_id="wow.test.pack-v1",
                world_pack_content_sha256="a" * 64,
                target_profile="test_lab",
                client_version="2.5.5",
                client_build="2.5.5.12345",
                nav_profile_id="test-nav-v1",
                worker=str(worker.resolve()),
                worker_sha256=hashlib.sha256(worker.read_bytes()).hexdigest(),
            )
            record = movement_ui.build_semantic_live_gate_record(
                expected,
                validation_result=result,
                status="PASS",
                live_authority_enabled=True,
            )
            gate.write_text(json.dumps(record), encoding="utf-8")
            with (
                patch.object(movement_ui, "SEMANTIC_GATE", gate),
                patch.object(movement_ui, "WORLD_PACK_PROFILE", profile),
                patch.object(movement_ui, "WORKER", worker),
                patch.object(movement_ui, "load_world_pack_runtime_profile"),
                patch.object(movement_ui, "semantic_live_gate_identity", return_value=expected),
            ):
                self.assertTrue(movement_ui.MovementEngineClient._semantic_gate_open())
                record["world_pack_content_sha256"] = "b" * 64
                gate.write_text(json.dumps(record), encoding="utf-8")
                self.assertFalse(movement_ui.MovementEngineClient._semantic_gate_open())

    def test_navmesh_identity_covers_every_active_adt_tile_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            nav = Path(directory) / "Nav" / "Azeroth"
            nav.mkdir(parents=True)
            (nav / "30_28.nav").write_bytes(b"second")
            (nav / "29_28.nav").write_bytes(b"first")
            initial = _navmesh_map_sha256(Path(directory), map_name="Azeroth")
            (nav / "30_28.nav").write_bytes(b"changed")
            changed = _navmesh_map_sha256(Path(directory), map_name="Azeroth")
            self.assertEqual(len(initial), 64)
            self.assertNotEqual(initial, changed)

    def test_failed_local_detour_backtracks_only_over_verified_breadcrumbs(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        start = source.index("breadcrumb_backtrack_corridor: NavCorridor")
        end = source.index("# Detour queries are bounded", start)
        recovery = source[start:end]
        self.assertIn("if local_recovery_attempts >= 3:", source)
        self.assertIn("deferred_resume_goal = (", source)
        self.assertIn("blocker_route_accepted = False", source)
        self.assertIn("recovery_local_goals = []", recovery)
        self.assertIn("safe_retreat_trail.reversed_corridor", recovery)
        self.assertIn("maximum_retreat_world=12.0", recovery)
        self.assertIn("VERIFIED_BREADCRUMB_BACKTRACK_PLANNED", recovery)
        self.assertIn("observed_blockers = candidate_blockers", recovery)
        self.assertNotIn("Reset-LabPlayerToSpawn", recovery)

    def test_collision_during_recovery_replans_to_original_mission(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        start = source.index("deferred_resume_goal = (")
        end = source.index("# Detour queries are bounded", start)
        recovery = source[start:end]

        self.assertIn(
            "replan_goal_x, replan_goal_y = deferred_resume_goal",
            recovery,
        )
        self.assertIn("goal_x=replan_goal_x", recovery)
        self.assertIn("goal_y=replan_goal_y", recovery)
        self.assertIn("stop_x=replan_goal_x", recovery)
        self.assertIn("stop_y=replan_goal_y", recovery)
        self.assertIn("recovery_resume_goal = None", recovery)

    def test_runtime_arm_expiry_releases_and_persists_resume_checkpoint(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        start = source.index("except ContinuousMotionAuthorityError as error:")
        end = source.index("except CombatHandoffRequired as error:", start)
        block = source[start:end]
        self.assertIn("motion.release_all()", block)
        self.assertIn("keyboard.release_all()", block)
        self.assertIn("mouse.release_all()", block)
        self.assertIn('"kind": "CONTINUOUS_MOTION_AUTHORITY_EXPIRED"', block)
        self.assertIn('"status": "RUNTIME_ARM_EXPIRED"', block)
        self.assertIn(
            '"resume_policy": "REISSUE_RUNTIME_ARM_AND_REPLAN_FROM_FRESH_LIVE_POSITION"',
            block,
        )
        self.assertIn("_write_json_atomic(result_path, result)", block)
        self.assertIn('publish_continuity("RUNTIME_ARM_EXPIRED")', block)

    def test_normalized_destination_does_not_index_empty_semantic_queue(self) -> None:
        source = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        start = source.index("if semantic_goals:")
        end = source.index("if initial_goal_projected:", start)
        block = source[start:end]
        self.assertIn("_plan_semantic_goal_or_forward_projection(", block)
        self.assertIn("corridor = engine.plan(", block)
        self.assertIn("goal_x=goal_x", block)
        self.assertIn("goal_y=goal_y", block)


if __name__ == "__main__":
    unittest.main()
