from __future__ import annotations

from dataclasses import replace
import json
from math import cos, sin, tau
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from perfect_assassin.movement.client_navmesh import (
    ClientNavmeshError, LocalStaticAwareness, LocalSurfaceTransitionPortal,
    LocalTopologicalEgressPortal, LocalWallSegment, NavCorridor, NavPoint,
    NavPolygon, NavPortal, RadialClearanceProbe,
)

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_INPUT = ROOT / "integrations" / "windows-input"
if str(WINDOWS_INPUT) not in sys.path:
    sys.path.insert(0, str(WINDOWS_INPUT))
import client_navmesh_backend
from client_navmesh_backend import ClientAssetNavmeshQuery, nav_worker_creation_flags
from run_navmesh_roaming import (
    _build_mission_steering,
    CaptureObservationError,
    CombatHandoffRequired,
    DYNAMIC_DETECTION_INTERVAL_FRAMES,
    LiveCoordinatePoseSource,
    MAX_CONSECUTIVE_STALE_CONTROL_FRAME_RETRIES,
    MAXIMUM_CONTROL_OBSERVATION_AGE_MS,
    _joined_semantic_preview_corridor,
    _forward_structure_egress_plan,
    _minimap_heading_is_fallback_only,
    _orient_initial_fallback_heading_to_corridor,
    _require_exact_body_heading,
    _plan_semantic_goal_or_forward_projection,
    _reachable_semantic_lookahead,
    _routine_aggro_travel_allowed,
    _semantic_destination_reached,
)
from perfect_assassin.movement.adaptive_steering import (
    AdaptiveTrajectorySteeringController,
)
from perfect_assassin.capture import CaptureDeadlineExceededError
from window_locator import WindowSelectionError
from perfect_assassin.movement.road_semantic_planner import RoadWorldPoint
from perfect_assassin.movement.predictive_steering import (
    CorridorProgressGate, PredictiveSteeringController, SteeringState,
    TrajectoryLoopGuard, observed_motion_is_continuous,
)
from perfect_assassin.movement.heading_estimator import select_heading_observation
from perfect_assassin.movement.world_model import (
    EntityTrack, LayeredWorldModel, StaticWorldFeature,
)
from perfect_assassin.movement.engine import StructureEgressPlan
from perfect_assassin.movement.risk_aware_route_policy import TravelCapability


START_AWARENESS_JSON = json.dumps({
    "physical_surfaces": ["ground"],
    "probe_radius_yards": 12.0,
    "overhead_clear": True,
    "radial_probes": [
        {
            "bearing_rad": index * tau / 16,
            "clearance_yards": 12.0,
            "navmesh_reachable": True,
        }
        for index in range(16)
    ],
    "topology_radius_yards": 60.0,
    "component_polygon_count": 0,
    "component_truncated": False,
    "wall_segments_truncated": False,
    "surface_transition_portals_truncated": False,
    "egress_inference_complete": True,
    "egress_portals_truncated": False,
    "wall_segments": [],
    "surface_transition_portals": [],
    "egress_portals": [],
}, separators=(",", ":"))


class ClientNavigationRuntimeTests(unittest.TestCase):
    def test_stale_control_retry_is_bounded_before_input_failure_escapes(self) -> None:
        self.assertEqual(MAX_CONSECUTIVE_STALE_CONTROL_FRAME_RETRIES, 3)
        source = (WINDOWS_INPUT / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        recovery = source[source.index('"STALE_CONTROL_FRAME_REACQUIRE"') - 900:]
        self.assertIn("except WindowsInputSinkError as error:", recovery)
        self.assertIn('str(error) != "continuous motion frame is stale"', recovery)
        self.assertIn("pose_source.next_observation()", recovery)
        self.assertIn("observe_traversal", recovery)
        self.assertIn("continue", recovery)

    def test_exact_body_heading_gate_accepts_coordinate_hud_proof(self) -> None:
        observation = {
            "tracking_state": "VALID",
            "position": {"x": 0.25, "y": 0.75, "facing_rad": 1.25},
        }
        _require_exact_body_heading(
            observation,
            heading=1.25,
            heading_source="COORDINATE_HUD_EXACT",
            phase="test",
        )

    def test_exact_body_heading_gate_rejects_minimap_estimate(self) -> None:
        observation = {
            "tracking_state": "VALID",
            "position": {"x": 0.25, "y": 0.75, "facing_rad": 1.25},
        }
        with self.assertRaisesRegex(RuntimeError, "exact visible body pose unavailable"):
            _require_exact_body_heading(
                observation,
                heading=1.25,
                heading_source="MOUSE_INTEGRATED_MINIMAP_FALLBACK",
                phase="test",
            )

    def test_exact_body_heading_gate_rejects_mixed_stale_heading(self) -> None:
        observation = {
            "tracking_state": "VALID",
            "position": {"x": 0.25, "y": 0.75, "facing_rad": 1.25},
        }
        with self.assertRaisesRegex(RuntimeError, "disagrees with controller heading"):
            _require_exact_body_heading(
                observation,
                heading=1.40,
                heading_source="COORDINATE_HUD_EXACT",
                phase="test",
            )

    def test_exact_body_heading_gate_wraps_near_zero_without_false_rejection(self) -> None:
        observation = {
            "tracking_state": "VALID",
            "position": {"x": 0.25, "y": 0.75, "facing_rad": 0.01},
        }
        _require_exact_body_heading(
            observation,
            heading=6.28,
            heading_source="COORDINATE_HUD_EXACT",
            phase="test",
        )

    def test_initial_minimap_axis_ambiguity_preserves_observed_end(self) -> None:
        corridor = NavCorridor(
            "PortableMap",
            0,
            0,
            NavPoint(0, 0, 5),
            NavPoint(10, 0, 5),
            (NavPoint(0, 0, 5), NavPoint(10, 0, 5)),
        )
        heading, source, flipped = _orient_initial_fallback_heading_to_corridor(
            3.05,
            heading_source="MOUSE_INTEGRATED_MINIMAP_FALLBACK",
            corridor=corridor,
        )
        self.assertTrue(flipped)
        self.assertEqual(source, "MOUSE_INTEGRATED_MINIMAP_FALLBACK")
        assert heading is not None
        self.assertAlmostEqual(heading, 3.05)

    def test_initial_fused_visual_heading_ambiguity_preserves_observation(self) -> None:
        corridor = NavCorridor(
            "PortableMap",
            0,
            0,
            NavPoint(0, 0, 5),
            NavPoint(10, 0, 5),
            (NavPoint(0, 0, 5), NavPoint(10, 0, 5)),
        )
        heading, source, flipped = _orient_initial_fallback_heading_to_corridor(
            3.05,
            heading_source="VISIBLE_CLIENT_HEADING_FUSED",
            corridor=corridor,
        )

        self.assertTrue(flipped)
        self.assertEqual(source, "VISIBLE_CLIENT_HEADING_FUSED")
        assert heading is not None
        self.assertAlmostEqual(heading, 3.05)

    def test_initial_minimap_axis_flip_does_not_replace_a_normal_route_bend(self) -> None:
        corridor = NavCorridor(
            "PortableMap",
            0,
            0,
            NavPoint(0, 0, 5),
            NavPoint(10, 0, 5),
            (NavPoint(0, 0, 5), NavPoint(10, 0, 5)),
        )
        heading, source, flipped = _orient_initial_fallback_heading_to_corridor(
            1.2,
            heading_source="MOUSE_INTEGRATED_MINIMAP_FALLBACK",
            corridor=corridor,
        )
        self.assertFalse(flipped)
        self.assertEqual(source, "MOUSE_INTEGRATED_MINIMAP_FALLBACK")
        self.assertEqual(heading, 1.2)

    def test_initial_minimap_axis_flip_never_replaces_exact_hud_heading(self) -> None:
        corridor = NavCorridor(
            "PortableMap",
            0,
            0,
            NavPoint(0, 0, 5),
            NavPoint(10, 0, 5),
            (NavPoint(0, 0, 5), NavPoint(10, 0, 5)),
        )
        heading, source, flipped = _orient_initial_fallback_heading_to_corridor(
            3.05,
            heading_source="COORDINATE_HUD_EXACT",
            corridor=corridor,
        )
        self.assertFalse(flipped)
        self.assertEqual(source, "COORDINATE_HUD_EXACT")
        self.assertEqual(heading, 3.05)

    def test_nav_worker_creation_flags_keep_asset_queries_below_capture_clock(self) -> None:
        with patch.object(
            client_navmesh_backend.subprocess,
            "CREATE_NO_WINDOW",
            0x08000000,
            create=True,
        ), patch.object(
            client_navmesh_backend.subprocess,
            "BELOW_NORMAL_PRIORITY_CLASS",
            0x00004000,
            create=True,
        ):
            self.assertEqual(nav_worker_creation_flags(), 0x08004000)

    def test_nav_query_passes_below_normal_worker_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.exe"
            worker.write_bytes(b"fixture")
            query = ClientAssetNavmeshQuery(worker=worker, nav_root=root)
            completed = type("Completed", (), {
                "returncode": 1, "stdout": "", "stderr": "fixture stop",
            })()
            with patch.object(
                client_navmesh_backend.subprocess,
                "CREATE_NO_WINDOW",
                0x08000000,
                create=True,
            ), patch.object(
                client_navmesh_backend.subprocess,
                "BELOW_NORMAL_PRIORITY_CLASS",
                0x00004000,
                create=True,
            ), patch.object(
                client_navmesh_backend.subprocess,
                "run",
                return_value=completed,
            ) as run:
                with self.assertRaisesRegex(ClientNavmeshError, "fixture stop"):
                    query.find_corridor(
                        map_name="Azeroth",
                        start=NavPoint(1, 2, 3),
                        stop_x=4,
                        stop_y=5,
                    )
            self.assertEqual(run.call_args.kwargs["creationflags"], 0x08004000)

    def test_combat_handoff_result_records_health_floor_evidence(self) -> None:
        source = (WINDOWS_INPUT / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        handoff = source[source.index("except CombatHandoffRequired as error:"):]
        self.assertIn('"health_fraction"', handoff)
        self.assertIn('"minimum_travel_health_fraction"', handoff)
        self.assertIn('"in_combat": True', handoff)

    def test_continuous_runner_requires_a_dedicated_runtime_arm(self) -> None:
        source = (WINDOWS_INPUT / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("--continuous-motion-authorization-file", source)
        self.assertIn("--continuous-motion-arm-file", source)
        self.assertIn("load_continuous_motion_authority", source)
        self.assertIn("ContinuousMotionExecutionGateway", source)
        self.assertIn("fixed-UI auth cannot move Predator", source)

    def test_adaptive_runtime_uses_requested_mppi_configuration(self) -> None:
        steering = _build_mission_steering(
            controller_id="adaptive_trajectory_v1",
            arrival_radius_world=1.2,
            lookahead_world=7.0,
            mppi_batch_size=128,
            mppi_time_steps=24,
        )
        try:
            self.assertIsInstance(
                steering,
                AdaptiveTrajectorySteeringController,
            )
            planner = steering._mppi._planner
            self.assertEqual(planner.configuration.batch_size, 128)
            self.assertEqual(planner.configuration.time_steps, 24)
            self.assertEqual(planner.configuration.yaw_smoothness_weight, 6.0)
            self.assertEqual(steering._mppi._replan_interval_ticks, 3)
        finally:
            steering.close()

    def test_semantic_structure_lookahead_skips_inside_guidance_point(self) -> None:
        start = NavPoint(0, 0, 5)
        inside = NavCorridor(
            "PortableMap", 0, 0, start, NavPoint(10, 0, 5),
            (start, NavPoint(10, 0, 5)),
        )
        outside = NavCorridor(
            "PortableMap", 0, 0, start, NavPoint(20, 0, 5),
            (start, NavPoint(20, 0, 5)),
        )
        selected_proposal = object()

        class Engine:
            structures = object()
            structure_access = object()

            def __init__(self):
                self.planned_goals: list[tuple[float, float]] = []

            def environment_at_corridor_start(self, corridor, **_kwargs):
                del corridor
                return type("Awareness", (), {
                    "containing_structures": (object(),),
                })()

            def plan(self, *, start, goal_x, goal_y):
                self.planned_goals.append((goal_x, goal_y))
                self.assert_start = start
                return outside

            def plan_via_known_structure_egress(
                self, *, goal_x, direct_corridor, **_kwargs,
            ):
                del direct_corridor
                return selected_proposal if goal_x == 20 else None

        engine = Engine()
        selection = _forward_structure_egress_plan(
            engine=engine,
            direct_corridor=inside,
            goals=[RoadWorldPoint(10, 0), RoadWorldPoint(20, 0)],
            goal_index=0,
            goal_x=10,
            goal_y=0,
            observed_monotonic_s=12.0,
        )

        self.assertEqual(selection, (1, selected_proposal))
        self.assertEqual(engine.planned_goals, [(20, 0)])
        self.assertEqual(engine.assert_start, start)

    def test_semantic_structure_lookahead_can_escape_from_partial_first_corridor(self) -> None:
        start = NavPoint(0, 0, 5)
        partial_inside = NavCorridor(
            "PortableMap", 0, 0, start, NavPoint(10, 0, 5),
            (start, NavPoint(10, 0, 5)),
            complete=False,
            requested_stop=NavPoint(10, 0, 5),
        )
        outside = NavCorridor(
            "PortableMap", 0, 0, start, NavPoint(20, 0, 5),
            (start, NavPoint(20, 0, 5)),
        )
        staged = NavPoint(10, 0, 5)
        opening = NavPoint(20, 0, 5)
        continuation_stop = NavPoint(30, 0, 5)
        staged_outside = NavCorridor(
            "PortableMap", 0, 0, staged, opening,
            (staged, opening),
        )
        selected_proposal = StructureEgressPlan(
            structure_id="structure",
            opening_id="opening",
            opening=opening,
            approach=staged_outside,
            continuation=NavCorridor(
                "PortableMap", 0, 0, opening, continuation_stop,
                (opening, continuation_stop),
            ),
            requested_goal=continuation_stop,
            direct_frontier_remaining_yards=20.0,
            continuation_frontier_remaining_yards=10.0,
        )

        class Engine:
            structures = object()
            structure_access = object()

            def __init__(self):
                self.planned_goals: list[tuple[float, float]] = []

            def environment_at_corridor_start(self, corridor, **_kwargs):
                del corridor
                return type("Awareness", (), {
                    "containing_structures": (object(),),
                })()

            def plan(self, *, start, goal_x, goal_y, goal_z=None):
                if goal_z is None:
                    self.planned_goals.append((goal_x, goal_y))
                self.assert_start = start
                return staged_outside

            def plan_via_known_structure_egress(
                self, *, goal_x, direct_corridor, **_kwargs,
            ):
                del direct_corridor
                return selected_proposal if goal_x == 20 else None

        engine = Engine()
        selection = _forward_structure_egress_plan(
            engine=engine,
            direct_corridor=partial_inside,
            goals=[RoadWorldPoint(10, 0), RoadWorldPoint(20, 0)],
            goal_index=0,
            goal_x=10,
            goal_y=0,
            observed_monotonic_s=12.0,
        )

        self.assertEqual(selection[0], 1)
        self.assertEqual(selection[1].opening_id, selected_proposal.opening_id)
        self.assertEqual(selection[1].approach.start, start)
        self.assertEqual(selection[1].approach.stop, opening)
        self.assertEqual(engine.planned_goals, [(10, 0), (20, 0)])
        self.assertEqual(engine.assert_start, staged)

    def test_foreground_loss_releases_input_and_preserves_last_pose(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        preserved = {"position": {"x": 17.0, "y": 23.0}}
        release_calls: list[str] = []

        def fail_observation():
            raise WindowSelectionError("target window is not the foreground window")

        source._next_fresh_observation = fail_observation
        source._on_capture_stall = lambda: release_calls.append("released")
        source._last_valid_observation = preserved

        with self.assertRaises(CaptureObservationError) as raised:
            source.next_observation()

        self.assertEqual(release_calls, ["released"])
        self.assertIs(raised.exception.last_valid_pose, preserved)
        self.assertEqual(raised.exception.cause_type, "WindowSelectionError")
        self.assertIn("foreground", raised.exception.detail)

    def test_exhausted_capture_deadline_becomes_forensic_stop(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        release_calls: list[str] = []

        def fail_observation():
            raise CaptureDeadlineExceededError("capture exceeded deadline")

        source._next_fresh_observation = fail_observation
        source._on_capture_stall = lambda: release_calls.append("released")
        source._last_valid_observation = None

        with self.assertRaises(CaptureObservationError) as raised:
            source.next_observation()

        self.assertEqual(release_calls, ["released"])
        self.assertIsNone(raised.exception.last_valid_pose)
        self.assertEqual(
            raised.exception.cause_type,
            "CaptureDeadlineExceededError",
        )

    def test_read_only_pose_observer_does_not_abort_on_visible_combat(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        observation = {"position": {"x": 1.0, "y": 2.0}}
        source._next_fresh_observation = lambda: observation
        source._latest_in_combat = True
        source._enforce_combat_handoff = False
        source._continue_through_routine_aggro = False
        source._minimum_travel_health_fraction = 0.55
        source._routine_aggro_observation_count = 0
        source._on_capture_stall = None

        self.assertIs(source.next_observation(), observation)

    def test_input_owning_pose_source_still_hands_off_visible_combat(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        observation = {"position": {"x": 1.0, "y": 2.0}}
        source._next_fresh_observation = lambda: observation
        source._latest_in_combat = True
        source._latest_travel_capability = None
        source._latest_combat_target_identity_crc16 = None
        source._enforce_combat_handoff = True
        source._continue_through_routine_aggro = False
        source._minimum_travel_health_fraction = 0.55
        source._routine_aggro_observation_count = 0
        source._on_capture_stall = None

        with self.assertRaises(CombatHandoffRequired):
            source.next_observation()

    def test_exact_addon_facing_is_never_overwritten_by_minimap_pixels(self) -> None:
        marker = {
            "orientation_deg_screen": 91.0,
            "detection_model": "neutral_mdx",
        }

        self.assertFalse(_minimap_heading_is_fallback_only(
            {"facing_rad": 1.25}, marker,
        ))
        self.assertTrue(_minimap_heading_is_fallback_only({}, marker))

    def test_semantic_destination_honors_catalog_area_radius(self) -> None:
        self.assertTrue(_semantic_destination_reached(
            world_x=27.0, world_y=0.0,
            destination_x=0.0, destination_y=0.0,
            radius_world=35.0,
        ))
        self.assertFalse(_semantic_destination_reached(
            world_x=36.0, world_y=0.0,
            destination_x=0.0, destination_y=0.0,
            radius_world=35.0,
        ))
        self.assertFalse(_semantic_destination_reached(
            world_x=0.0, world_y=0.0,
            destination_x=0.0, destination_y=0.0,
            radius_world=None,
        ))

    def test_routine_aggro_preserves_journey_only_above_health_floor(self) -> None:
        self.assertTrue(_routine_aggro_travel_allowed(
            enabled=True, in_combat=True, health_fraction=0.82,
            minimum_health_fraction=0.55,
        ))
        self.assertFalse(_routine_aggro_travel_allowed(
            enabled=True, in_combat=True, health_fraction=0.54,
            minimum_health_fraction=0.55,
        ))
        self.assertFalse(_routine_aggro_travel_allowed(
            enabled=False, in_combat=True, health_fraction=1.0,
            minimum_health_fraction=0.55,
        ))

    def test_input_owner_continues_routine_aggro_only_with_fresh_health_evidence(self) -> None:
        source = LiveCoordinatePoseSource.__new__(LiveCoordinatePoseSource)
        observation = {"position": {"x": 1.0, "y": 2.0}}
        source._next_fresh_observation = lambda: observation
        source._latest_in_combat = True
        source._latest_combat_target_identity_crc16 = 123
        source._enforce_combat_handoff = True
        source._continue_through_routine_aggro = True
        source._minimum_travel_health_fraction = 0.55
        source._routine_aggro_observation_count = 0
        source._on_capture_stall = None
        source._latest_travel_capability = TravelCapability(
            level=1, health_fraction=0.82,
            stealth_ready=False, escape_ready=False,
        )

        self.assertIs(source.next_observation(), observation)
        self.assertEqual(source.routine_aggro_observation_count, 1)

        source._latest_travel_capability = TravelCapability(
            level=1, health_fraction=0.54,
            stealth_ready=False, escape_ready=False,
        )
        with self.assertRaises(CombatHandoffRequired):
            source.next_observation()

    def test_capture_and_control_share_one_bounded_freshness_limit(self) -> None:
        self.assertEqual(MAXIMUM_CONTROL_OBSERVATION_AGE_MS, 295.0)

    def test_dynamic_nameplate_awareness_is_bounded_below_track_ttl(self) -> None:
        self.assertEqual(DYNAMIC_DETECTION_INTERVAL_FRAMES, 4)

    def test_unreachable_semantic_horizon_can_skip_to_verified_later_goal(self) -> None:
        incomplete = NavCorridor(
            map_name="Azeroth", adt_x=0, adt_y=0,
            start=NavPoint(0, 0, 0), stop=NavPoint(1, 0, 0),
            points=(NavPoint(0, 0, 0), NavPoint(1, 0, 0)),
            complete=False,
            requested_stop=NavPoint(20, 0, 0),
        )
        complete = NavCorridor(
            map_name="Azeroth", adt_x=0, adt_y=0,
            start=NavPoint(0, 0, 0), stop=NavPoint(30, 0, 0),
            points=(NavPoint(0, 0, 0), NavPoint(30, 0, 0)),
            complete=True,
        )

        class Engine:
            def plan(self, *, start, goal_x, goal_y):
                del start, goal_y
                if goal_x == 20:
                    raise ClientNavmeshError("fixture endpoint has no polygon")
                return complete if goal_x == 30 else incomplete

        result = _reachable_semantic_lookahead(
            engine=Engine(),
            start=NavPoint(0, 0, 0),
            goals=[
                RoadWorldPoint(10, 0),
                RoadWorldPoint(20, 0),
                RoadWorldPoint(30, 0),
            ],
            blocked_index=0,
            radius_world=3.0,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], 2)
        self.assertIs(result[1], complete)

    def corridor(self) -> NavCorridor:
        points = tuple(NavPoint(float(x), 0.0, 10.0) for x in (0, 5, 12, 24, 40))
        return NavCorridor("Azeroth", 28, 28, points[0], points[-1], points)

    def test_predictive_controller_uses_closed_loop_ticks_and_stuck_replan(self) -> None:
        controller = PredictiveSteeringController()
        calibration = controller.decide(SteeringState(0, 0, None, 7.0), self.corridor())
        self.assertEqual(calibration.state, "CALIBRATE_HEADING")
        self.assertEqual(calibration.forward_hold_ms, 300)

        following = controller.decide(SteeringState(0, 0, 0.0, 7.0), self.corridor())
        self.assertEqual(following.state, "FOLLOW")
        self.assertEqual(following.forward_hold_ms, 50)
        self.assertLessEqual(abs(following.mouse_delta_x), 8)

        stuck = controller.decide(SteeringState(0, 0, 0.0, 7.0, 1.8), self.corridor())
        self.assertEqual(stuck.state, "REPLAN")
        self.assertEqual(stuck.forward_hold_ms, 0)

    def test_straight_corridor_corrects_lateral_drift_without_camera_sway(self) -> None:
        controller = PredictiveSteeringController()
        corridor = self.corridor()
        intents = [
            controller.decide(SteeringState(0.0, 0.70, 0.0, 7.0), corridor)
            for _ in range(5)
        ]

        self.assertEqual(intents[-1].strafe, "STRAFE_RIGHT")
        self.assertEqual(intents[-1].mouse_delta_x, 0)
        self.assertEqual(
            intents[-1].reason,
            "topology_camera_stable_strafe_correction",
        )
        neutral = controller.decide(
            SteeringState(0.7, 0.28, 0.0, 7.0), corridor,
        )
        self.assertIsNone(neutral.strafe)
        self.assertEqual(neutral.mouse_delta_x, 0)

    def test_wmo_egress_uses_one_bounded_lateral_tap_when_wall_sliding(self) -> None:
        controller = PredictiveSteeringController()
        awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"wmo"}),
            probe_radius_yards=12.0,
            overhead_clear=False,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 12.0, True)
                for index in range(16)
            ),
        )
        corridor = replace(self.corridor(), start_awareness=awareness)

        first = controller.decide(
            SteeringState(0.0, 0.60, 0.0, 7.0), corridor,
        )
        second = controller.decide(
            SteeringState(0.0, 0.60, 0.0, 7.0), corridor,
        )

        self.assertIsNone(first.strafe)
        self.assertEqual(second.strafe, "STRAFE_RIGHT")
        self.assertEqual(second.mouse_delta_x, 0)
        self.assertEqual(
            second.reason,
            "topology_camera_stable_strafe_correction",
        )

    def test_semantic_endpoint_without_polygon_projects_forward_on_route(self) -> None:
        reachable = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(20, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(20, 0, 0)),
        )

        class Engine:
            def plan(self, *, start, goal_x, goal_y):
                if goal_x == 10:
                    raise ClientNavmeshError("corridor endpoint has no polygon")
                return reachable

        index, corridor, projected = _plan_semantic_goal_or_forward_projection(
            engine=Engine(),
            start=NavPoint(0, 0, 0),
            goals=[RoadWorldPoint(10, 0), RoadWorldPoint(20, 0)],
            goal_index=0,
            radius_world=3.0,
        )

        self.assertEqual(index, 1)
        self.assertIs(corridor, reachable)
        self.assertTrue(projected)

    def test_rolling_preview_joins_generic_connected_corridors(self) -> None:
        current = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(10, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(10, 0, 0)),
        )
        continuation = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(10, 0, 0), NavPoint(10, 20, 0),
            (NavPoint(10, 0, 0), NavPoint(10, 8, 0), NavPoint(10, 20, 0)),
        )

        preview = _joined_semantic_preview_corridor(current, continuation)

        self.assertIsNotNone(preview)
        assert preview is not None
        self.assertEqual(
            preview.guidance_points(),
            (
                NavPoint(0, 0, 0), NavPoint(10, 0, 0),
                NavPoint(10, 8, 0), NavPoint(10, 20, 0),
            ),
        )
        self.assertEqual(preview.stop, continuation.stop)

    def test_guidance_erases_same_floor_revisit_without_hardcoded_location(self) -> None:
        points = (
            NavPoint(0, 0, 10), NavPoint(4, 0, 10),
            NavPoint(4, 4, 10), NavPoint(0.3, 0.2, 10.2),
            NavPoint(0, -4, 10),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28, points[0], points[-1], points,
        )

        self.assertEqual(
            corridor.guidance_points(),
            (points[0], points[3], points[4]),
        )

    def test_guidance_preserves_height_separated_switchback(self) -> None:
        points = (
            NavPoint(0, 0, 10), NavPoint(4, 0, 12),
            NavPoint(4, 4, 14), NavPoint(0.3, 0.2, 16),
            NavPoint(0, -4, 18),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28, points[0], points[-1], points,
        )

        self.assertEqual(corridor.guidance_points(), points)

    def test_rolling_preview_rejects_disconnected_or_reverse_route(self) -> None:
        current = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(10, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(10, 0, 0)),
        )
        disconnected = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(15, 0, 0), NavPoint(20, 0, 0),
            (NavPoint(15, 0, 0), NavPoint(20, 0, 0)),
        )
        reverse = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(10, 0, 0), NavPoint(0, 0, 0),
            (NavPoint(10, 0, 0), NavPoint(0, 0, 0)),
        )

        self.assertIsNone(_joined_semantic_preview_corridor(current, disconnected))
        self.assertIsNone(_joined_semantic_preview_corridor(current, reverse))

    def test_rolling_preview_rejects_same_floor_fold_back(self) -> None:
        current = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 10), NavPoint(10, 0, 10),
            (
                NavPoint(0, 0, 10), NavPoint(5, 0, 10),
                NavPoint(10, 0, 10),
            ),
        )
        continuation = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(10, 0, 10), NavPoint(0.2, 0.1, 10.1),
            (
                NavPoint(10, 0, 10), NavPoint(14, 0, 10),
                NavPoint(14, 4, 10), NavPoint(0.2, 0.1, 10.1),
            ),
        )

        self.assertIsNone(
            _joined_semantic_preview_corridor(current, continuation)
        )

    def test_rolling_preview_preserves_height_separated_fold_back(self) -> None:
        current = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 10), NavPoint(10, 0, 12),
            (
                NavPoint(0, 0, 10), NavPoint(5, 0, 11),
                NavPoint(10, 0, 12),
            ),
        )
        continuation = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(10, 0, 12), NavPoint(0.2, 0.1, 18),
            (
                NavPoint(10, 0, 12), NavPoint(14, 0, 14),
                NavPoint(14, 4, 16), NavPoint(0.2, 0.1, 18),
            ),
        )

        self.assertIsNotNone(
            _joined_semantic_preview_corridor(current, continuation)
        )

    def test_rolling_preview_never_bridges_a_partial_navmesh_frontier(self) -> None:
        shared = NavPoint(10, 0, 0)
        requested = NavPoint(11, 0, 0)
        complete_current = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), shared,
            (NavPoint(0, 0, 0), shared),
        )
        partial_current = replace(
            complete_current,
            complete=False,
            requested_stop=requested,
        )
        complete_continuation = NavCorridor(
            "Azeroth", 28, 28,
            shared, NavPoint(20, 0, 0),
            (shared, NavPoint(20, 0, 0)),
        )
        partial_continuation = replace(
            complete_continuation,
            complete=False,
            requested_stop=NavPoint(21, 0, 0),
        )

        self.assertIsNone(
            _joined_semantic_preview_corridor(
                partial_current, complete_continuation,
            )
        )
        self.assertIsNone(
            _joined_semantic_preview_corridor(
                complete_current, partial_continuation,
            )
        )

    def test_semantic_arrival_radius_does_not_force_exact_city_center(self) -> None:
        controller = PredictiveSteeringController(arrival_radius_world=60.0)
        intent = controller.decide(
            SteeringState(45.0, 0.0, 0.0, 7.0),
            NavCorridor("Azeroth", 28, 28, NavPoint(45, 0, 0), NavPoint(0, 0, 0),
                        (NavPoint(45, 0, 0), NavPoint(0, 0, 0))),
        )
        self.assertEqual(intent.state, "ARRIVED")

    def test_unknown_heading_starts_with_one_natural_calibration_stride(self) -> None:
        intent = PredictiveSteeringController().decide(
            SteeringState(0.0, 0.0, None, 8.0), self.corridor()
        )

        self.assertEqual(intent.state, "CALIBRATE_HEADING")
        self.assertEqual(intent.forward_hold_ms, 300)
        self.assertEqual(intent.mouse_delta_x, 0)

    def test_lookahead_never_selects_a_passed_corridor_point(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=10.0)
        corridor = self.corridor()
        intent = controller.decide(SteeringState(20.0, 0.0, 0.0, 7.0), corridor)
        self.assertIsNotNone(intent.lookahead)
        assert intent.lookahead is not None
        self.assertGreaterEqual(intent.lookahead.x, 24.0)

    def test_follow_servo_cannot_flip_from_full_left_to_full_right_in_one_tick(self) -> None:
        controller = PredictiveSteeringController()
        corridor = self.corridor()
        first = controller.decide(SteeringState(0, 0, 0.5, 7.0), corridor)
        second = controller.decide(SteeringState(0, 0, -0.5, 7.0), corridor)
        self.assertLessEqual(abs(first.mouse_delta_x), 2)
        self.assertLessEqual(abs(second.mouse_delta_x - first.mouse_delta_x), 2)

    def test_yaw_momentum_brakes_before_crossing_the_corridor_bearing(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(30, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(30, 0, 0)),
        )

        first = controller.decide(
            SteeringState(2.0, 1.5, 0.70, 7.0), corridor,
        )
        second = controller.decide(
            SteeringState(2.0, 1.5, 0.35, 7.0), corridor,
        )
        brake = controller.decide(
            SteeringState(2.0, 1.5, 0.05, 7.0), corridor,
        )

        self.assertGreater(first.mouse_delta_x, 0)
        self.assertGreaterEqual(second.mouse_delta_x, 0)
        self.assertEqual(brake.mouse_delta_x, 0)

    def test_yaw_momentum_countersteers_once_instead_of_chasing_both_sides(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(30, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(30, 0, 0)),
        )
        samples = (
            SteeringState(2.0, 1.5, 0.70, 7.0),
            SteeringState(2.0, 1.5, 0.35, 7.0),
            SteeringState(2.0, 1.0, 0.05, 7.0),
            SteeringState(2.0, 0.4, -0.20, 7.0),
            SteeringState(2.0, -0.2, -0.30, 7.0),
        )

        commands = [
            controller.decide(sample, corridor).mouse_delta_x
            for sample in samples
        ]
        nonzero_signs = [
            1 if command > 0 else -1
            for command in commands if command != 0
        ]
        sign_changes = sum(
            left != right
            for left, right in zip(nonzero_signs, nonzero_signs[1:])
        )

        self.assertLessEqual(sign_changes, 1)
        self.assertIn(0, commands[2:])

    def test_straight_road_settled_micro_reversal_stays_neutral(self) -> None:
        controller = PredictiveSteeringController()
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(100, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(100, 0, 0)),
        )
        # This bounded heading sequence reproduces the neutral-tick-separated
        # +1/-1 requests observed on a locally straight road in live trace
        # 83ce7767.  The lateral offset is above the former curve-only
        # hysteresis envelope; it must not make a settled tangent correction
        # alternate the camera.
        headings = (-0.15, 0.10, -0.10, -0.15, -0.15, -0.15)

        commands = [
            controller.decide(
                SteeringState(float(index), 1.5, heading, 7.0), corridor,
            ).mouse_delta_x
            for index, heading in enumerate(headings, 1)
        ]
        nonzero_signs = [
            1 if command > 0 else -1 for command in commands if command
        ]

        self.assertEqual(commands[:3], [1, 2, 0])
        self.assertEqual(
            sum(
                left != right
                for left, right in zip(nonzero_signs, nonzero_signs[1:])
            ),
            0,
        )

    def test_straight_road_large_opposite_correction_is_not_filtered(self) -> None:
        controller = PredictiveSteeringController()
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(100, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(100, 0, 0)),
        )
        controller.decide(SteeringState(1.0, 0.0, -0.15, 7.0), corridor)
        controller.decide(SteeringState(2.0, 0.0, -0.15, 7.0), corridor)

        commands = [
            controller.decide(
                SteeringState(float(index), 0.0, 0.70, 7.0), corridor,
            ).mouse_delta_x
            for index in range(3, 9)
        ]

        self.assertTrue(any(command > 0 for command in commands))

    def test_straight_road_quantized_point_two_one_reversal_stays_neutral(self) -> None:
        controller = PredictiveSteeringController()
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(100, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(100, 0, 0)),
        )
        controller._last_nonzero_follow_delta = -1

        commands = [
            controller.decide(
                SteeringState(float(index), 0.0, 0.21, 7.0), corridor,
            ).mouse_delta_x
            for index in range(3, 9)
        ]

        self.assertFalse(any(command > 0 for command in commands))

    def test_open_bend_settled_micro_reversal_stays_neutral(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(30, 12, 0),
            (
                NavPoint(0, 0, 0),
                NavPoint(10, 0, 0),
                NavPoint(20, 6, 0),
                NavPoint(30, 12, 0),
            ),
        )
        headings = (0.05, -0.05, 0.05, -0.05, 0.05, -0.05)

        commands = [
            controller.decide(
                SteeringState(float(index), 0.5, heading, 7.0), corridor,
            ).mouse_delta_x
            for index, heading in enumerate(headings, 1)
        ]
        nonzero_signs = [
            1 if command > 0 else -1 for command in commands if command
        ]

        self.assertEqual(
            sum(
                left != right
                for left, right in zip(nonzero_signs, nonzero_signs[1:])
            ),
            0,
        )

    def test_small_second_counter_pulse_waits_for_camera_settling(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(100, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(100, 0, 0)),
        )
        controller._last_nonzero_follow_delta = 3
        controller._follow_reversal_settle_ticks = 6

        intent = controller.decide(
            SteeringState(10.0, 0.0, -0.12, 7.0), corridor,
        )

        self.assertEqual(intent.mouse_delta_x, 0)

    def test_large_second_counter_pulse_remains_authoritative(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(100, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(100, 0, 0)),
        )
        controller._last_nonzero_follow_delta = -3
        controller._follow_reversal_settle_ticks = 6

        intents = [
            controller.decide(
                SteeringState(float(index), 0.0, 0.75, 7.0), corridor,
            )
            for index in range(10, 15)
        ]

        self.assertTrue(any(intent.mouse_delta_x > 0 for intent in intents))

    def test_corridor_departure_allows_small_opposite_recovery_command(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(100, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(100, 0, 0)),
        )
        controller.decide(SteeringState(1.0, 0.0, -0.10, 7.0), corridor)
        controller.decide(SteeringState(2.0, 0.0, -0.10, 7.0), corridor)

        commands = [
            controller.decide(
                SteeringState(float(index), 3.25, 0.10, 7.0), corridor,
            ).mouse_delta_x
            for index in range(3, 9)
        ]

        self.assertTrue(any(command > 0 for command in commands))

    def test_rolling_corridor_handoff_preserves_mouse_acceleration_state(self) -> None:
        controller = PredictiveSteeringController()
        first_corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(0, 30, 0),
            (NavPoint(0, 0, 0), NavPoint(0, 30, 0)),
        )
        second_corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 1, 0), NavPoint(0, 31, 0),
            (NavPoint(0, 1, 0), NavPoint(0, 31, 0)),
        )

        first = controller.decide(SteeringState(0, 0, 0.0, 7.0), first_corridor)
        second = controller.decide(SteeringState(0, 1, 0.0, 7.0), second_corridor)

        self.assertEqual(abs(first.mouse_delta_x), 1)
        self.assertEqual(abs(second.mouse_delta_x), 2)

    def test_semantic_handoff_slews_the_desired_bearing_instead_of_snapping_camera(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        straight = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(20, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(20, 0, 0)),
        )
        # This is a plausible rolling horizon: the next valid corridor bends
        # gradually, but its first look-ahead would otherwise ask for a full
        # camera correction in a single 50 ms observation.
        bending = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(12.4, 15.6, 0),
            (NavPoint(0, 0, 0), NavPoint(12.4, 15.6, 0)),
        )

        first = controller.decide(SteeringState(0, 0, 0.0, 7.0), straight)
        second = controller.decide(SteeringState(0, 0, 0.0, 7.0), bending)
        third = controller.decide(SteeringState(0, 0, 0.0, 7.0), bending)

        self.assertEqual(first.mouse_delta_x, 0)
        self.assertEqual(second.state, "FOLLOW")
        self.assertLessEqual(abs(second.mouse_delta_x), 1)
        self.assertLessEqual(abs(third.mouse_delta_x), 2)

    def test_large_deviation_does_not_replan_while_turning_toward_corridor(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(40, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(40, 0, 0)),
        )

        for index in range(
            PredictiveSteeringController.PERSISTENT_OFF_CORRIDOR_REPLAN_TICKS + 2
        ):
            intent = controller.decide(
                SteeringState(2.0 + index * 0.1, 4.0, 0.0, 7.0), corridor,
            )
            self.assertEqual(intent.state, "PIVOT")

    def test_aligned_persistent_corridor_deviation_requests_clean_replan(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(40, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(40, 0, 0)),
        )
        replan = None
        for index in range(
            PredictiveSteeringController.PERSISTENT_OFF_CORRIDOR_REPLAN_TICKS
        ):
            replan = controller.decide(
                SteeringState(2.0 + index * 0.1, 4.0, -0.95, 7.0), corridor,
            )
        assert replan is not None
        self.assertEqual(replan.state, "REPLAN")
        self.assertEqual(replan.reason, "persistent_corridor_divergence")

    def test_captured_seventy_degree_road_error_keeps_running_rmb_turn(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(1845.7609, 1588.9330, 93.65),
            NavPoint(1906.25, 1585.4167, 91.0),
            (
                NavPoint(1845.7609, 1588.9330, 93.65),
                NavPoint(1906.25, 1585.4167, 91.0),
            ),
        )

        intent = controller.decide(
            SteeringState(1845.7609, 1588.9330, 1.10, 7.0), corridor,
        )

        self.assertEqual(intent.state, "FOLLOW")
        self.assertEqual(intent.forward_hold_ms, 50)

    def test_progress_gate_rejects_collision_slide_until_corridor_advances(self) -> None:
        gate = CorridorProgressGate(minimum_progress_world=0.5)
        self.assertTrue(gate.observe(path_progress_world=10.0, goal_distance_world=20.0))
        for index in range(1, 8):
            self.assertFalse(
                gate.observe(
                    path_progress_world=10.0,
                    goal_distance_world=20.0 + (0.03 if index % 2 else -0.03),
                )
            )
        self.assertTrue(gate.observe(path_progress_world=10.55, goal_distance_world=20.1))

    def test_long_observation_gap_cannot_hide_a_physical_pause(self) -> None:
        self.assertFalse(
            observed_motion_is_continuous(
                displacement_world=0.55,
                observation_interval_s=1.25,
                forward_requested=True,
            )
        )
        self.assertTrue(
            observed_motion_is_continuous(
                displacement_world=4.0,
                observation_interval_s=1.25,
                forward_requested=True,
            )
        )

    def test_no_forward_request_does_not_create_motion_failure(self) -> None:
        self.assertTrue(
            observed_motion_is_continuous(
                displacement_world=0.0,
                observation_interval_s=1.25,
                forward_requested=False,
            )
        )

    def test_collision_slide_cannot_replace_mouse_integrated_facing(self) -> None:
        calibrated, source = select_heading_observation(
            predicted_heading_rad=None,
            api_heading_rad=None,
            displacement_heading_rad=1.25,
        )
        self.assertEqual(source, "DISPLACEMENT_INITIAL_CALIBRATION")

        retained, source = select_heading_observation(
            predicted_heading_rad=calibrated,
            api_heading_rad=None,
            displacement_heading_rad=-0.40,
        )

        self.assertEqual(retained, calibrated)
        self.assertEqual(
            source, "MOUSE_INTEGRATED_AFTER_DISPLACEMENT_CALIBRATION",
        )

    def test_progress_projection_is_monotone_across_a_hairpin_neighborhood(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=4.0)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(0, 1, 0),
            (
                NavPoint(0, 0, 0), NavPoint(10, 0, 0),
                NavPoint(10, 1, 0), NavPoint(0, 1, 0),
            ),
        )
        first = controller.decide(SteeringState(9.5, 0.0, 0.0, 7.0), corridor)
        second = controller.decide(SteeringState(9.4, 1.0, 3.14, 7.0), corridor)
        self.assertGreaterEqual(second.progress_world, first.progress_world)
        self.assertGreater(second.lookahead.x, 0.0)

    def test_projection_reaches_outbound_strip_after_observed_corner(self) -> None:
        polygons = (
            NavPolygon(
                0, 0, 0, 0.0, NavPoint(10.0, 0.0, 0.0),
                (
                    NavPoint(0.0, -4.0, 0.0), NavPoint(20.0, -4.0, 0.0),
                    NavPoint(20.0, 4.0, 0.0), NavPoint(0.0, 4.0, 0.0),
                ),
            ),
            NavPolygon(
                1, 0, 0, 0.0, NavPoint(20.0, -10.0, 0.0),
                (
                    NavPoint(16.0, -1.0, 0.0), NavPoint(24.0, -1.0, 0.0),
                    NavPoint(24.0, -20.0, 0.0), NavPoint(16.0, -20.0, 0.0),
                ),
            ),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 30,
            NavPoint(0.0, 0.0, 0.0), NavPoint(20.0, -20.0, 0.0),
            (
                NavPoint(0.0, 0.0, 0.0), NavPoint(20.0, 0.0, 0.0),
                NavPoint(20.0, -20.0, 0.0),
            ),
            polygons=polygons,
            portals=(NavPortal(
                0, 1, NavPoint(20.0, -4.0, 0.0),
                NavPoint(20.0, 4.0, 0.0), 8.0,
            ),),
        )
        calibrating = PredictiveSteeringController().decide(
            SteeringState(17.0, 0.0, None, 7.0), corridor,
        )
        self.assertEqual(calibrating.state, "CALIBRATE_HEADING")
        controller = PredictiveSteeringController()
        first = controller.decide(
            SteeringState(17.0, 0.0, 0.0, 7.0), corridor,
        )
        second = controller.decide(
            SteeringState(19.5, -1.0, -1.57, 7.0), corridor,
        )

        normal_window = (
            first.progress_world
            + 7.0 * PredictiveSteeringController.PROJECTION_ADVANCE_TIME_S
        )
        self.assertGreater(second.progress_world, normal_window)
        self.assertLessEqual(
            second.progress_world - first.progress_world,
            PredictiveSteeringController.MAX_PROJECTION_ADVANCE_WORLD,
        )

        confined_awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"wmo"}),
            probe_radius_yards=12.0,
            overhead_clear=False,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 1.0, False)
                for index in range(16)
            ),
        )
        confined = replace(corridor, start_awareness=confined_awareness)
        confined_controller = PredictiveSteeringController()
        confined_first = confined_controller.decide(
            SteeringState(17.0, 0.0, 0.0, 7.0), confined,
        )
        confined_second = confined_controller.decide(
            SteeringState(19.5, -1.0, -1.57, 7.0), confined,
        )
        confined_window = (
            confined_first.progress_world
            + 7.0 * PredictiveSteeringController.PROJECTION_ADVANCE_TIME_S
        )
        self.assertLessEqual(confined_second.progress_world, confined_window)

    def test_projection_cannot_jump_to_an_overlapping_later_floor(self) -> None:
        controller = PredictiveSteeringController(arrival_radius_world=0.5)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 100), NavPoint(0, 1, 120),
            (
                NavPoint(0, 0, 100), NavPoint(10, 0, 105),
                NavPoint(10, 1, 115), NavPoint(0, 1, 120),
            ),
        )
        first = controller.decide(SteeringState(1, 0, 0.0, 7.0), corridor)
        # This XY is close to the later, upper return segment as well.  A 2D
        # global nearest-segment search used to jump almost the entire stair.
        second = controller.decide(SteeringState(1, 1, 0.0, 7.0), corridor)

        self.assertLessEqual(
            second.progress_world - first.progress_world,
            PredictiveSteeringController.MAX_PROJECTION_ADVANCE_WORLD,
        )
        self.assertLess(second.projected_z_world, 110.0)

    def test_projection_interpolates_current_navmesh_height(self) -> None:
        controller = PredictiveSteeringController()
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 100), NavPoint(10, 0, 110),
            (NavPoint(0, 0, 100), NavPoint(10, 0, 110)),
        )
        intent = controller.decide(SteeringState(2, 0, 0.0, 7.0), corridor)
        self.assertAlmostEqual(intent.projected_z_world, 102.0)

    def test_sharp_corner_caps_lookahead_before_it_cuts_the_inside_wall(self) -> None:
        controller = PredictiveSteeringController()
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(5, 5, 0),
            (NavPoint(0, 0, 0), NavPoint(5, 0, 0), NavPoint(5, 5, 0)),
        )
        intent = controller.decide(SteeringState(1, 0, 0.0, 7.0), corridor)
        self.assertIsNotNone(intent.lookahead)
        assert intent.lookahead is not None
        self.assertAlmostEqual(intent.lookahead.y, 0.0)
        self.assertLessEqual(intent.lookahead.x, 5.0)

    def test_wide_portal_previews_corner_with_running_rmb_arc(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        polygons = (
            NavPolygon(
                0, 0, 0, 0.0, NavPoint(2.5, 0.0, 0.0),
                (
                    NavPoint(0, -4, 0), NavPoint(5, -4, 0),
                    NavPoint(5, 4, 0), NavPoint(0, 4, 0),
                ),
            ),
            NavPolygon(
                1, 0, 0, 0.0, NavPoint(5.0, 2.5, 0.0),
                (
                    NavPoint(1, 0, 0), NavPoint(9, 0, 0),
                    NavPoint(9, 5, 0), NavPoint(1, 5, 0),
                ),
            ),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(5, 5, 0),
            (NavPoint(0, 0, 0), NavPoint(5, 0, 0), NavPoint(5, 5, 0)),
            polygons=polygons,
            portals=(NavPortal(
                0, 1, NavPoint(5, -4, 0), NavPoint(5, 4, 0), 8.0,
            ),),
        )

        intent = controller.decide(
            SteeringState(3.0, 0.0, 0.0, 7.0), corridor,
        )

        self.assertEqual(intent.state, "FOLLOW")
        self.assertEqual(intent.forward_hold_ms, 50)
        self.assertIsNotNone(intent.lookahead)
        assert intent.lookahead is not None
        self.assertAlmostEqual(intent.lookahead.y, 0.0)
        self.assertLess(intent.mouse_delta_x, 0)

    def test_remote_narrow_portal_does_not_disable_local_wide_curve(self) -> None:
        polygons = tuple(
            NavPolygon(
                index, 0, 0, 0.0, NavPoint(index * 4.0, 0.0, 0.0),
                (
                    NavPoint(index * 4.0 - 1, -1, 0),
                    NavPoint(index * 4.0 + 1, -1, 0),
                    NavPoint(index * 4.0, 1, 0),
                ),
            )
            for index in range(3)
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(8, 8, 0),
            (NavPoint(0, 0, 0), NavPoint(8, 0, 0), NavPoint(8, 8, 0)),
            polygons=polygons,
            portals=(
                NavPortal(
                    0, 1, NavPoint(4, -0.15, 0), NavPoint(4, 0.15, 0), 0.3,
                ),
                NavPortal(
                    1, 2, NavPoint(8, -4, 0), NavPoint(8, 4, 0), 8.0,
                ),
            ),
        )

        intent = PredictiveSteeringController().decide(
            SteeringState(6.0, 0.0, 0.0, 7.0), corridor,
        )

        self.assertEqual(corridor.minimum_portal_width, 0.3)
        self.assertEqual(intent.state, "FOLLOW")
        self.assertLess(intent.mouse_delta_x, 0)
        self.assertGreaterEqual(
            abs(intent.mouse_delta_x),
            PredictiveSteeringController.CURVE_MOUSE_ACCEL_SLEW_PER_TICK,
        )

    def test_curve_acceleration_requires_actor_capsule_inside_local_clearance(self) -> None:
        polygons = (
            NavPolygon(
                0, 0, 0, 0.0, NavPoint(4, 0, 0),
                (NavPoint(0, -4, 0), NavPoint(8, -4, 0), NavPoint(8, 4, 0)),
            ),
            NavPolygon(
                1, 0, 0, 0.0, NavPoint(8, 4, 0),
                (NavPoint(4, 0, 0), NavPoint(12, 0, 0), NavPoint(8, 8, 0)),
            ),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(8, 8, 0),
            (NavPoint(0, 0, 0), NavPoint(8, 0, 0), NavPoint(8, 8, 0)),
            polygons=polygons,
            portals=(NavPortal(
                0, 1, NavPoint(8, -4, 0), NavPoint(8, 4, 0), 8.0,
            ),),
        )

        inside = PredictiveSteeringController().decide(
            SteeringState(6.0, 0.0, 0.0, 7.0), corridor,
        )
        outside = PredictiveSteeringController().decide(
            SteeringState(6.0, 3.0, 0.0, 7.0), corridor,
        )

        self.assertGreaterEqual(
            abs(inside.mouse_delta_x),
            PredictiveSteeringController.CURVE_MOUSE_ACCEL_SLEW_PER_TICK,
        )
        self.assertLessEqual(
            abs(outside.mouse_delta_x),
            PredictiveSteeringController.MOUSE_ACCEL_SLEW_PER_TICK,
        )

    def test_open_road_off_corridor_heading_error_uses_running_turn(self) -> None:
        controller = PredictiveSteeringController()
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(20, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(20, 0, 0)),
        )
        intent = controller.decide(SteeringState(2, 2, 0.7, 7.0), corridor)
        self.assertEqual(intent.state, "FOLLOW")
        self.assertEqual(intent.forward_hold_ms, 50)

    def test_confined_recovery_envelope_keeps_running_rmb_turn(self) -> None:
        awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"wmo"}),
            probe_radius_yards=12.0,
            overhead_clear=False,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 1.0, False)
                for index in range(16)
            ),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(20, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(20, 0, 0)),
            start_awareness=awareness,
        )

        intent = PredictiveSteeringController().decide(
            SteeringState(2, 2, 0.7, 7.0), corridor,
        )

        self.assertEqual(intent.state, "FOLLOW")
        self.assertEqual(intent.forward_hold_ms, 50)

    def test_confined_moderate_hard_recenter_crossing_keeps_running(self) -> None:
        awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"wmo"}),
            probe_radius_yards=12.0,
            overhead_clear=False,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 1.0, False)
                for index in range(16)
            ),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(30, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(30, 0, 0)),
            start_awareness=awareness,
        )

        # Crossing the confined hard-recenter line is not, by itself, proof
        # that forward movement is unsafe.  Keep a running RMB correction in
        # the bounded soft band; reserve stationary pivot for the severe case.
        intent = PredictiveSteeringController().decide(
            SteeringState(2.0, 3.2, 0.0, 7.0), corridor,
        )

        self.assertEqual(intent.state, "FOLLOW")
        self.assertEqual(intent.forward_hold_ms, 50)

    def test_confined_severe_recenter_crossing_still_pivots(self) -> None:
        awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"wmo"}),
            probe_radius_yards=12.0,
            overhead_clear=False,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 1.0, False)
                for index in range(16)
            ),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(30, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(30, 0, 0)),
            start_awareness=awareness,
        )

        intent = PredictiveSteeringController().decide(
            SteeringState(2.0, 4.0, 0.0, 7.0), corridor,
        )

        self.assertEqual(intent.state, "PIVOT")
        self.assertEqual(intent.forward_hold_ms, 0)

    def test_partial_confined_corridor_never_runs_soft_recenter(self) -> None:
        awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"wmo"}),
            probe_radius_yards=12.0,
            overhead_clear=False,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 1.0, False)
                for index in range(16)
            ),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(20, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(20, 0, 0)),
            complete=False,
            requested_stop=NavPoint(20, 0, 0),
            start_awareness=awareness,
        )

        intent = PredictiveSteeringController().decide(
            SteeringState(2.0, 3.2, 0.0, 7.0), corridor,
        )

        self.assertEqual(intent.state, "PIVOT")
        self.assertEqual(intent.forward_hold_ms, 0)

    def test_confined_recovery_carrot_stays_ahead_of_one_movement_stride(self) -> None:
        awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"wmo"}),
            probe_radius_yards=12.0,
            overhead_clear=False,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 1.0, False)
                for index in range(16)
            ),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(20, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(20, 0, 0)),
            start_awareness=awareness,
        )
        controller = PredictiveSteeringController(lookahead_world=5.0)

        controller.decide(SteeringState(2.0, 0.4, 0.0, 7.0), corridor)
        recovery = controller.decide(
            SteeringState(2.0, 1.4, 0.0, 7.0), corridor,
        )

        self.assertIsNotNone(recovery.lookahead)
        assert recovery.lookahead is not None
        self.assertGreaterEqual(recovery.lookahead.x - 2.0, 3.1)

    def test_confined_recovery_horizon_scales_with_running_speed(self) -> None:
        awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"wmo"}),
            probe_radius_yards=12.0,
            overhead_clear=False,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 1.0, False)
                for index in range(16)
            ),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(30, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(30, 0, 0)),
            start_awareness=awareness,
        )

        slow = PredictiveSteeringController(lookahead_world=5.0).decide(
            SteeringState(2.0, 1.4, 0.0, 3.0), corridor,
        )
        running = PredictiveSteeringController(lookahead_world=5.0).decide(
            SteeringState(2.0, 1.4, 0.0, 7.0), corridor,
        )

        assert slow.lookahead is not None
        assert running.lookahead is not None
        self.assertGreater(running.lookahead.x, slow.lookahead.x + 1.7)

    def test_small_off_corridor_error_keeps_a_continuous_forward_horizon(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(20, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(20, 0, 0)),
        )
        just_inside = controller.decide(
            SteeringState(2, 0.84, 0.0, 7.0), corridor,
        )
        just_outside = controller.decide(
            SteeringState(2, 0.86, 0.0, 7.0), corridor,
        )

        self.assertEqual(just_outside.state, "FOLLOW")
        self.assertEqual(just_outside.forward_hold_ms, 50)
        self.assertIsNotNone(just_inside.lookahead)
        self.assertIsNotNone(just_outside.lookahead)
        assert just_inside.lookahead is not None
        assert just_outside.lookahead is not None
        self.assertLess(abs(just_outside.lookahead.x - just_inside.lookahead.x), 0.1)

    def test_one_yard_road_drift_does_not_put_pursuit_point_beside_actor(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=6.0)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(30, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(30, 0, 0)),
        )

        intent = controller.decide(
            SteeringState(5.0, 1.0, -0.15, 7.0), corridor,
        )

        self.assertEqual(intent.state, "FOLLOW")
        self.assertIsNotNone(intent.lookahead)
        assert intent.lookahead is not None
        self.assertGreaterEqual(intent.lookahead.x, 10.9)
        self.assertAlmostEqual(intent.lookahead.y, 0.0)

    def test_right_angle_open_road_target_keeps_running_while_camera_slews(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        straight = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(20, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(20, 0, 0)),
        )
        reversal = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(0, 20, 0),
            (NavPoint(0, 0, 0), NavPoint(0, 20, 0)),
        )
        controller.decide(SteeringState(0, 0, 0.0, 7.0), straight)

        intent = controller.decide(
            SteeringState(0, 0, 0.0, 7.0), reversal,
        )

        self.assertEqual(intent.state, "FOLLOW")
        self.assertEqual(intent.forward_hold_ms, 50)

    def test_open_ground_near_reversal_aligns_once_before_running(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        reversal = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(-20, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(-20, 0, 0)),
        )

        intent = controller.decide(
            SteeringState(0, 0, 0.0, 7.0), reversal,
        )

        self.assertEqual(intent.state, "PIVOT")
        self.assertEqual(intent.forward_hold_ms, 0)
        self.assertIsNone(intent.strafe)

    def test_open_ground_hundred_ten_degree_error_aligns_before_running(self) -> None:
        controller = PredictiveSteeringController(lookahead_world=5.0)
        corridor = NavCorridor(
            "Azeroth", 28, 28,
            NavPoint(0, 0, 0), NavPoint(20, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(20, 0, 0)),
        )

        intent = controller.decide(
            SteeringState(0, 0, 1.92, 7.0), corridor,
        )

        self.assertEqual(intent.state, "PIVOT")
        self.assertEqual(intent.forward_hold_ms, 0)
        self.assertIsNone(intent.strafe)

    def test_trajectory_guard_detects_unproductive_obstacle_orbit(self) -> None:
        guard = TrajectoryLoopGuard()
        evidence = None
        for degrees in range(0, 391, 10):
            angle = degrees * tau / 360.0
            evidence = guard.observe(
                x=4.0 * cos(angle),
                y=4.0 * sin(angle),
                goal_distance_world=40.0,
            )
            if evidence is not None:
                break

        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertGreaterEqual(evidence.path_length_world, 18.0)
        self.assertLessEqual(evidence.revisit_distance_world, 2.5)

    def test_trajectory_guard_does_not_reject_productive_hairpin(self) -> None:
        guard = TrajectoryLoopGuard()
        points = (
            tuple((float(x), 0.0) for x in range(0, 11))
            + tuple((float(x), 1.0) for x in range(10, -1, -1))
        )

        detected = [
            guard.observe(
                x=x, y=y,
                goal_distance_world=max(0.0, 30.0 - index * 1.5),
            )
            for index, (x, y) in enumerate(points)
        ]

        self.assertTrue(all(item is None for item in detected))

    def test_captured_crypt_deviation_steers_back_before_the_torch(self) -> None:
        controller = PredictiveSteeringController()
        # Reduced, immutable regression fixture from the client-asset corridor
        # at the Deathknell crypt staircase.  These values are evidence for the
        # controller test only; the runtime never contains a crypt route.
        points = tuple(
            NavPoint(x, y, 124.0)
            for x, y in (
                (1674.107178, 1675.892822),
                (1650.380859, 1677.044067),
                (1644.901001, 1675.976074),
                (1642.738403, 1672.486572),
            )
        )
        confined_awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"wmo"}),
            probe_radius_yards=12.0,
            overhead_clear=False,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 1.0, False)
                for index in range(16)
            ),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28, points[0], points[-1], points,
            start_awareness=confined_awareness,
        )

        intent = controller.decide(
            SteeringState(
                1650.2138965888712,
                1676.0879235458929,
                -3.1177017236122073,
                7.0,
            ),
            corridor,
        )

        self.assertAlmostEqual(intent.cross_track_error_world, 0.9065, places=3)
        self.assertEqual(intent.state, "FOLLOW")
        self.assertEqual(intent.forward_hold_ms, 50)
        self.assertIsNotNone(intent.lookahead)
        assert intent.lookahead is not None
        self.assertGreater(intent.lookahead.x, 1648.2)
        self.assertGreater(intent.lookahead.y, 1676.55)
        self.assertGreater(intent.mouse_delta_x, 0)

    def test_world_model_keeps_hostile_experience_after_live_track_expires(self) -> None:
        model = LayeredWorldModel(map_name="Azeroth", static_navmesh_sha256="A" * 64)
        model.observe_position(x=16, y=24, observed_at_s=1.0)
        heated = model.mark_stuck(x=16, y=24, observed_at_s=2.0)
        self.assertGreater(heated.stuck_heat, 0)
        model.upsert_track(EntityTrack(
            "wolf:visible:1", "HOSTILE_NPC", "Young Scavenger", "live_visible_bearing",
            2.0, 4.0, 0.95, 18.0, 25.0,
        ))
        self.assertEqual(model.static_knowledge, "CLIENT_ASSET_GEOMETRY_KNOWN")
        self.assertEqual(model.dynamic_knowledge, "OBSERVED_ONLY_FOG_OF_WAR")
        self.assertEqual(
            model.historical_knowledge,
            "PERMANENT_OBSERVED_EXPERIENCE_NOT_LIVE_POSITION",
        )
        self.assertEqual(len(model.active_tracks(now_s=3.0)), 1)
        self.assertEqual(model.active_tracks(now_s=4.0), ())
        observations = model.historical_observations()
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].name, "Young Scavenger")
        risks = model.historical_risk_areas()
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0].observation_count, 1)
        self.assertGreater(risks[0].risk_score, 0.0)

    def test_thousand_yard_awareness_keeps_static_priors_but_expires_players(self) -> None:
        model = LayeredWorldModel(map_name="Azeroth", static_navmesh_sha256="B" * 64)
        model.upsert_static_feature(StaticWorldFeature(
            "deathknell:crypt:exit", "EXIT", "Deathknell crypt exit",
            100.0, 0.0, 12.0, 2.0, 1.0, 1.0, "client_asset_world_model:v1",
        ))
        model.upsert_static_feature(StaticWorldFeature(
            "deathknell:bat:prior", "HOSTILE_SPAWN", "Young Night Web Bat spawn prior",
            300.0, 0.0, None, 80.0, 0.8, 1.0, "reviewed_spawn_dataset:v1",
        ))
        model.upsert_track(EntityTrack(
            "player:enemy:1", "PLAYER", "Enemy", "last_seen_area",
            5.0, 8.0, 0.7, 200.0, 0.0,
        ))
        model.upsert_track(EntityTrack(
            "player:enemy:visible", "PLAYER", "VisibleEnemy", "live_visible_bearing",
            5.0, 8.0, 1.0, 50.0, 0.0,
        ))
        current = model.local_awareness(
            x=0, y=0, static_radius_yards=1_000,
            dynamic_visibility_radius_yards=100, now_s=6.0,
        )
        self.assertEqual(len(current.static_features), 2)
        self.assertEqual(len(current.visible_dynamic_tracks), 1)
        self.assertEqual(len(current.remembered_dynamic_tracks), 1)
        expired = model.local_awareness(
            x=0, y=0, static_radius_yards=1_000,
            dynamic_visibility_radius_yards=100, now_s=9.0,
        )
        self.assertEqual(len(expired.static_features), 2)
        self.assertEqual(expired.visible_dynamic_tracks, ())
        self.assertEqual(expired.remembered_dynamic_tracks, ())

    def test_nav_query_rejects_non_exact_worker_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.exe"
            worker.write_bytes(b"fixture")
            query = ClientAssetNavmeshQuery(worker=worker, nav_root=root)
            completed = type("Completed", (), {
                "returncode": 0,
                "stdout": '{"status":"OK","path":[]}\n',
                "stderr": "",
            })()
            with patch("client_navmesh_backend.subprocess.run", return_value=completed):
                with self.assertRaises(ClientNavmeshError):
                    query.find_corridor(
                        map_name="Azeroth", start=NavPoint(1, 2, 3), stop_x=4, stop_y=5
                    )

    def test_nav_query_accepts_safe_exact_map_dbc_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.exe"
            worker.write_bytes(b"fixture")
            query = ClientAssetNavmeshQuery(worker=worker, nav_root=root)
            completed = type("Completed", (), {
                "returncode": 1, "stdout": "", "stderr": "fixture stop",
            })()
            for map_name in ("Zul'gurub", "Stratholme Raid"):
                with patch(
                    "client_navmesh_backend.subprocess.run",
                    return_value=completed,
                ) as run:
                    with self.assertRaisesRegex(ClientNavmeshError, "fixture stop"):
                        query.find_corridor(
                            map_name=map_name,
                            start=NavPoint(1, 2, 3),
                            stop_x=4,
                            stop_y=5,
                        )
                self.assertEqual(run.call_args.args[0][2], map_name)

            for map_name in ("../Shadowfang", "C:\\Shadowfang", "Bad*Map"):
                with self.assertRaisesRegex(ClientNavmeshError, "map name is invalid"):
                    query.find_corridor(
                        map_name=map_name,
                        start=NavPoint(1, 2, 3),
                        stop_x=4,
                        stop_y=5,
                    )

    def test_geometry_aware_corridor_preserves_funnel_path_for_guidance(self) -> None:
        polygon_a = NavPolygon(
            0, 0, 0, 0.0, NavPoint(1, 1, 0),
            (NavPoint(0, 0, 0), NavPoint(2, 0, 0), NavPoint(1, 2, 0)),
        )
        polygon_b = NavPolygon(
            1, 0, 0, 0.0, NavPoint(3, 1, 1),
            (NavPoint(2, 0, 1), NavPoint(4, 0, 1), NavPoint(3, 2, 1)),
        )
        corridor = NavCorridor(
            "Azeroth", 28, 28, NavPoint(0, 1, 0), NavPoint(4, 1, 1),
            (NavPoint(0, 1, 0), NavPoint(4, 1, 1)),
            (polygon_a, polygon_b),
            (NavPortal(0, 1, NavPoint(2, 0, 0.5), NavPoint(2, 2, 0.5), 2.0),),
        )
        self.assertTrue(corridor.geometry_aware)
        self.assertEqual(corridor.minimum_portal_width, 2.0)
        self.assertEqual(corridor.guidance_points(), corridor.points)

    def test_search_vantage_requires_open_ground_radial_and_overhead_clearance(self) -> None:
        polygon = NavPolygon(
            0, 0, 0, 0.0, NavPoint(3, 1, 0),
            (NavPoint(0, 0, 0), NavPoint(6, 0, 0), NavPoint(3, 4, 0)),
            frozenset({"ground"}),
        )
        open_corridor = NavCorridor(
            "Azeroth", 28, 28, NavPoint(1, 1, 0), NavPoint(3, 1, 0),
            (NavPoint(1, 1, 0), NavPoint(3, 1, 0)),
            polygons=(polygon,),
            search_vantage_radial_clear_count=12,
            search_vantage_radial_probe_count=16,
            search_vantage_radial_probe_radius=8.0,
            search_vantage_overhead_clear=True,
            search_vantage_physical_surfaces=frozenset({"ground"}),
        )
        self.assertIsNone(open_corridor.search_vantage_rejection())
        self.assertEqual(
            replace(open_corridor, search_vantage_radial_clear_count=11)
            .search_vantage_rejection(),
            "radial_clearance_is_occluded",
        )
        self.assertEqual(
            replace(
                open_corridor,
                search_vantage_physical_surfaces=frozenset({"ground", "wmo"}),
            ).search_vantage_rejection(),
            "requested_endpoint_is_not_open_terrain",
        )
        self.assertEqual(
            replace(open_corridor, search_vantage_overhead_clear=False)
            .search_vantage_rejection(),
            "camera_overhead_clearance_is_occluded",
        )

    def test_local_static_awareness_distinguishes_open_ground_and_wmo(self) -> None:
        probes = tuple(
            RadialClearanceProbe(index * tau / 16, 12.0, True)
            for index in range(16)
        )
        awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"ground"}),
            probe_radius_yards=12.0,
            overhead_clear=True,
            radial_probes=probes,
        )

        self.assertEqual(awareness.environment_class, "OPEN_GROUND")
        self.assertEqual(len(awareness.candidate_opening_bearings_rad), 16)
        self.assertEqual(
            replace(awareness, physical_surfaces=frozenset({"wmo"}))
            .environment_class,
            "WMO_STRUCTURE_OR_TRANSITION",
        )
        wmo_with_egress = replace(
            awareness,
            physical_surfaces=frozenset({"wmo"}),
            overhead_clear=False,
            component_polygon_count=4,
            wall_segments=(LocalWallSegment(
                NavPoint(0, 0, 0), NavPoint(0, 4, 0), 2.0,
            ),),
            surface_transition_portals=(LocalSurfaceTransitionPortal(
                NavPoint(4, 0, 0), NavPoint(4, 3, 0), 3.0, 4.0,
                frozenset({"wmo"}), frozenset({"ground"}),
            ),),
            egress_portals=(LocalTopologicalEgressPortal(
                NavPoint(8, 0, 1), NavPoint(8, 4, 1), 4.0, 8.0, 12.5,
                False, True, frozenset({"wmo"}), frozenset({"ground"}),
            ),),
        )
        self.assertEqual(
            wmo_with_egress.environment_class,
            "WMO_STRUCTURE_WITH_EGRESS",
        )
        raw_transition_only = replace(wmo_with_egress, egress_portals=())
        self.assertEqual(
            raw_transition_only.environment_class,
            "WMO_STRUCTURE_OR_TRANSITION",
        )
        confined = replace(
            awareness,
            overhead_clear=False,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 1.0, False)
                for index in range(16)
            ),
        )
        self.assertEqual(confined.environment_class, "CONFINED_STATIC_SPACE")

    def test_adapter_accepts_only_route_verified_covered_to_open_egress(self) -> None:
        value = json.loads(START_AWARENESS_JSON)
        value.update({
            "physical_surfaces": ["wmo"],
            "overhead_clear": False,
            "component_polygon_count": 205,
            "surface_transition_portals": [{
                "left": [4.0, 0.0, 1.0],
                "right": [4.0, 3.0, 1.0],
                "width_yards": 3.0,
                "distance_yards": 4.0,
                "from_surfaces": ["wmo"],
                "to_surfaces": ["ground"],
            }],
            "egress_portals": [{
                "left": [8.0, 0.0, 12.0],
                "right": [8.0, 4.0, 12.0],
                "width_yards": 4.0,
                "distance_yards": 8.0,
                "route_distance_yards": 64.6,
                "from_overhead_clear": False,
                "to_overhead_clear": True,
                "from_surfaces": ["wmo"],
                "to_surfaces": ["ground"],
            }],
        })

        awareness = ClientAssetNavmeshQuery._start_awareness(value)

        self.assertEqual(awareness.environment_class, "WMO_STRUCTURE_WITH_EGRESS")
        self.assertAlmostEqual(awareness.egress_portals[0].route_distance_yards, 64.6)
        malformed = json.loads(json.dumps(value))
        del malformed["egress_portals"][0]["route_distance_yards"]
        with self.assertRaises(ClientNavmeshError):
            ClientAssetNavmeshQuery._start_awareness(malformed)

    def test_nav_query_accepts_exact_geometry_worker_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.exe"
            worker.write_bytes(b"fixture")
            query = ClientAssetNavmeshQuery(worker=worker, nav_root=root)
            stdout = (
                '{"status":"OK","adt_x":28,"adt_y":28,'
                '"start":[0,1,0],"stop":[4,1,1],'
                '"requested_stop":[4,1,1],"complete":true,'
                '"doodad_avoidance_applied":false,"doodad_detour_count":0,'
                '"doodad_unresolved_segment_count":0,'
                '"doodad_unresolved_blockers":[],'
                '"clearance_inset_count":2,'
                '"steep_polygons_penalized":0,'
                '"observed_blocker_polygons_excluded":0,'
                '"impassable_uphill_polygons_excluded":0,'
                '"road_polygons_preferred":0,'
                '"nearest_road_polygon_to_start":-1,'
                '"road_polygon_bounds":[0,0,0,0],'
                '"height_candidates":1,"stop_height_candidates":1,'
                '"search_vantage_radial_clear_count":16,'
                '"search_vantage_radial_probe_count":16,'
                '"search_vantage_radial_probe_radius":8,'
                '"search_vantage_overhead_clear":true,'
                '"search_vantage_physical_surfaces":["ground"],'
                f'"start_awareness":{START_AWARENESS_JSON},'
                '"path":[[0,1,0],[4,1,1]],'
                '"polygons":['
                '{"index":0,"area":0,"type":0,"slope_degrees":0,'
                '"physical_surfaces":["ground"],'
                '"vertices":[[0,0,0],[2,0,0],[1,2,0]],"centroid":[1,1,0]},'
                '{"index":1,"area":0,"type":0,"slope_degrees":10,'
                '"physical_surfaces":["ground"],'
                '"vertices":[[2,0,1],[4,0,1],[3,2,1]],"centroid":[3,1,1]}],'
                '"portals":[{"from_index":0,"to_index":1,'
                '"left":[2,0,0.5],"right":[2,2,0.5],"width":2}]}\n'
            )
            completed = type("Completed", (), {
                "returncode": 0, "stdout": stdout, "stderr": "",
            })()
            with patch("client_navmesh_backend.subprocess.run", return_value=completed):
                corridor = query.find_corridor(
                    map_name="Azeroth", start=NavPoint(0, 1, 0), stop_x=4, stop_y=1
                )
        self.assertTrue(corridor.geometry_aware)
        self.assertEqual(len(corridor.polygons), 2)
        self.assertEqual(corridor.clearance_inset_count, 2)
        self.assertIsNotNone(corridor.start_awareness)
        assert corridor.start_awareness is not None
        self.assertEqual(corridor.start_awareness.environment_class, "OPEN_GROUND")

    def test_nav_query_passes_and_verifies_floor_aware_stop_height(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.exe"
            worker.write_bytes(b"fixture")
            query = ClientAssetNavmeshQuery(worker=worker, nav_root=root)
            stdout = (
                '{"status":"OK","adt_x":27,"adt_y":31,'
                '"start":[-228.191,2111.41,76.8904],'
                '"stop":[-76.7541,2152.41,155.708572],'
                '"requested_stop":[-76.7541,2152.41,155.708572],'
                '"requested_stop_z_hint":155.792,"complete":true,'
                '"topology_gap_direct_shortcut_applied":true,'
                '"doodad_avoidance_applied":false,"doodad_detour_count":0,'
                '"doodad_unresolved_segment_count":0,'
                '"doodad_unresolved_blockers":[],"clearance_inset_count":0,'
                '"steep_polygons_penalized":0,'
                '"doodad_polygons_penalized":7,'
                '"movement_path_shortcut_count":5,'
                '"observed_blocker_polygons_excluded":0,'
                '"impassable_uphill_polygons_excluded":0,'
                '"road_polygons_preferred":0,'
                '"nearest_road_polygon_to_start":-1,'
                '"road_polygon_bounds":[0,0,0,0],'
                '"height_candidates":1,"stop_height_candidates":2,'
                '"search_vantage_radial_clear_count":16,'
                '"search_vantage_radial_probe_count":16,'
                '"search_vantage_radial_probe_radius":8,'
                '"search_vantage_overhead_clear":false,'
                '"search_vantage_physical_surfaces":["wmo"],'
                f'"start_awareness":{START_AWARENESS_JSON},'
                '"path":[[-228.191,2111.41,76.8904],'
                '[-76.7541,2152.41,155.708572]],'
                '"polygons":[{"index":0,"area":0,"type":0,'
                '"slope_degrees":0,"physical_surfaces":["wmo"],'
                '"vertices":[[-229,2110,76.8],[-76,2151,155.7],'
                '[-77,2153,155.7]],"centroid":[-127,2138,129.4]}],'
                '"portals":[]}\n'
            )
            completed = type("Completed", (), {
                "returncode": 0, "stdout": stdout, "stderr": "",
            })()
            with patch(
                "client_navmesh_backend.subprocess.run", return_value=completed,
            ) as run:
                corridor = query.find_corridor(
                    map_name="Shadowfang",
                    start=NavPoint(-228.191, 2111.41, 76.8904),
                    stop_x=-76.7541,
                    stop_y=2152.41,
                    stop_z=155.792,
                )
            command = run.call_args.args[0]

        self.assertEqual(command[-2:], ["--stop-z", "155.792"])
        self.assertAlmostEqual(corridor.requested_stop.z, 155.708572)
        self.assertTrue(corridor.topology_gap_direct_shortcut_applied)
        self.assertEqual(corridor.doodad_polygons_penalized, 7)
        self.assertEqual(corridor.movement_path_shortcut_count, 5)

    def test_nav_query_rejects_mismatched_floor_aware_stop_height(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.exe"
            worker.write_bytes(b"fixture")
            query = ClientAssetNavmeshQuery(worker=worker, nav_root=root)
            completed = type("Completed", (), {
                "returncode": 0,
                "stdout": (
                    '{"status":"OK","requested_stop_z_hint":87.0}\n'
                ),
                "stderr": "",
            })()
            with patch("client_navmesh_backend.subprocess.run", return_value=completed):
                with self.assertRaisesRegex(
                    ClientNavmeshError, "worker output shape is not exact",
                ):
                    query.find_corridor(
                        map_name="Shadowfang", start=NavPoint(1, 2, 3),
                        stop_x=4, stop_y=5, stop_z=155.792,
                    )

    def test_nav_query_passes_bounded_observed_blocker_set_to_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.exe"
            worker.write_bytes(b"fixture")
            query = ClientAssetNavmeshQuery(
                worker=worker, nav_root=root,
                observed_blockers=(
                    (10.0, 20.0, 30.0, 6.0),
                    (40.0, 50.0, 60.0, 8.0),
                ),
            )
            completed = type("Completed", (), {
                "returncode": 1, "stdout": "", "stderr": "fixture stop",
            })()
            with patch(
                "client_navmesh_backend.subprocess.run", return_value=completed,
            ) as run:
                with self.assertRaises(ClientNavmeshError):
                    query.find_corridor(
                        map_name="Azeroth", start=NavPoint(1, 2, 3),
                        stop_x=4, stop_y=5,
                    )
            command = run.call_args.args[0]
        self.assertEqual(
            command[-8:], [
                "10.0", "20.0", "30.0", "6.0",
                "40.0", "50.0", "60.0", "8.0",
            ],
        )

    def test_structure_egress_scope_filters_only_inside_blocker_centres(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.exe"
            worker.write_bytes(b"fixture")
            query = ClientAssetNavmeshQuery(
                worker=worker,
                nav_root=root,
                timeout_seconds=4.0,
                observed_blockers=(
                    (0.0, 0.0, 5.0, 2.0),
                    (9.0, 9.0, 5.0, 2.0),
                    (20.0, 20.0, 5.0, 2.0),
                ),
            )

            scoped = query.for_structure_egress(
                bounds=(-10.0, -10.0, 0.0, 10.0, 10.0, 10.0),
            )

        self.assertIsNot(scoped, query)
        self.assertEqual(
            scoped._observed_blockers,
            ((20.0, 20.0, 5.0, 2.0),),
        )
        self.assertEqual(scoped._worker, query._worker)
        self.assertEqual(scoped._nav_root, query._nav_root)
        self.assertEqual(scoped._timeout_seconds, query._timeout_seconds)

    def test_observer_blocker_updates_keep_structure_egress_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.exe"
            worker.write_bytes(b"fixture")
            query = ClientAssetNavmeshQuery(
                worker=worker,
                nav_root=root,
                observed_blockers=((0.0, 0.0, 5.0, 2.0),),
            ).for_structure_egress(
                bounds=(-10.0, -10.0, 0.0, 10.0, 10.0, 10.0),
            )
            updated = query.with_observed_blockers(
                (
                    (1.0, 1.0, 5.0, 2.0),
                    (20.0, 20.0, 5.0, 2.0),
                )
            )
            reopened = updated.without_structure_egress_scope()

        self.assertEqual(updated._observed_blockers, ((20.0, 20.0, 5.0, 2.0),))
        self.assertEqual(
            updated.observed_blockers,
            ((20.0, 20.0, 5.0, 2.0),),
        )
        self.assertEqual(updated._structure_egress_bounds, (-10.0, -10.0, 0.0, 10.0, 10.0, 10.0))
        self.assertEqual(
            reopened._observed_blockers,
            ((20.0, 20.0, 5.0, 2.0),),
        )
        self.assertIsNone(reopened._structure_egress_bounds)

    def test_nav_query_replans_around_worker_discovered_doodad_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.exe"
            worker.write_bytes(b"fixture")
            query = ClientAssetNavmeshQuery(worker=worker, nav_root=root)
            resolved = (
                '{"status":"OK","adt_x":28,"adt_y":28,'
                '"start":[0,1,0],"stop":[4,1,1],'
                '"requested_stop":[4,1,1],"complete":true,'
                '"doodad_avoidance_applied":false,"doodad_detour_count":0,'
                '"doodad_unresolved_segment_count":0,'
                '"doodad_unresolved_blockers":[],'
                '"clearance_inset_count":0,"steep_polygons_penalized":0,'
                '"observed_blocker_polygons_excluded":1,'
                '"impassable_uphill_polygons_excluded":0,'
                '"road_polygons_preferred":0,'
                '"nearest_road_polygon_to_start":-1,'
                '"road_polygon_bounds":[0,0,0,0],'
                '"height_candidates":1,"stop_height_candidates":1,'
                '"search_vantage_radial_clear_count":16,'
                '"search_vantage_radial_probe_count":16,'
                '"search_vantage_radial_probe_radius":8,'
                '"search_vantage_overhead_clear":true,'
                '"search_vantage_physical_surfaces":["ground"],'
                f'"start_awareness":{START_AWARENESS_JSON},'
                '"path":[[0,1,0],[4,1,1]],'
                '"polygons":[{"index":0,"area":0,"type":0,'
                '"slope_degrees":0,"physical_surfaces":["ground"],'
                '"vertices":[[0,0,0],[4,0,1],[4,2,1]],'
                '"centroid":[2,1,0.5]}],"portals":[]}\n'
            )
            unresolved = resolved.replace(
                '"doodad_unresolved_segment_count":0,'
                '"doodad_unresolved_blockers":[],',
                '"doodad_unresolved_segment_count":1,'
                '"doodad_unresolved_blockers":[[2,1,0.5,1.5]],',
            ).replace(
                '"observed_blocker_polygons_excluded":1,',
                '"observed_blocker_polygons_excluded":0,',
            )
            responses = [
                type("Completed", (), {
                    "returncode": 0, "stdout": unresolved, "stderr": "",
                })(),
                type("Completed", (), {
                    "returncode": 0, "stdout": resolved, "stderr": "",
                })(),
            ]
            with patch(
                "client_navmesh_backend.subprocess.run", side_effect=responses,
            ) as run:
                corridor = query.find_corridor(
                    map_name="Azeroth", start=NavPoint(0, 1, 0),
                    stop_x=4, stop_y=1,
                )
        self.assertTrue(corridor.complete)
        self.assertEqual(corridor.doodad_unresolved_segment_count, 0)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[1].args[0][-4:], ["2.0", "1.0", "0.5", "1.5"])

    def test_nav_query_replans_around_post_funnel_unwalkable_grade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.exe"
            worker.write_bytes(b"fixture")
            query = ClientAssetNavmeshQuery(worker=worker, nav_root=root)
            resolved = (
                '{"status":"OK","adt_x":28,"adt_y":28,'
                '"start":[0,1,0],"stop":[4,1,1],'
                '"requested_stop":[4,1,1],"complete":true,'
                '"doodad_avoidance_applied":false,"doodad_detour_count":0,'
                '"doodad_unresolved_segment_count":0,'
                '"doodad_unresolved_blockers":[],'
                '"clearance_inset_count":0,"steep_polygons_penalized":0,'
                '"observed_blocker_polygons_excluded":1,'
                '"impassable_uphill_polygons_excluded":0,'
                '"road_polygons_preferred":0,'
                '"nearest_road_polygon_to_start":-1,'
                '"road_polygon_bounds":[0,0,0,0],'
                '"height_candidates":1,"stop_height_candidates":1,'
                '"search_vantage_radial_clear_count":16,'
                '"search_vantage_radial_probe_count":16,'
                '"search_vantage_radial_probe_radius":8,'
                '"search_vantage_overhead_clear":true,'
                '"search_vantage_physical_surfaces":["ground"],'
                f'"start_awareness":{START_AWARENESS_JSON},'
                '"path":[[0,1,0],[4,1,1]],'
                '"polygons":[{"index":0,"area":0,"type":0,'
                '"slope_degrees":0,"physical_surfaces":["ground"],'
                '"vertices":[[0,0,0],[4,0,1],[4,2,1]],'
                '"centroid":[2,1,0.5]}],"portals":[]}\n'
            )
            unsafe = resolved.replace(
                '"observed_blocker_polygons_excluded":1,',
                '"observed_blocker_polygons_excluded":0,',
            ).replace(
                '"path":[[0,1,0],[4,1,1]],',
                '"path":[[0,1,0],[1,1,2],[4,1,1]],',
            )
            responses = [
                type("Completed", (), {
                    "returncode": 0, "stdout": unsafe, "stderr": "",
                })(),
                type("Completed", (), {
                    "returncode": 0, "stdout": resolved, "stderr": "",
                })(),
            ]
            with patch(
                "client_navmesh_backend.subprocess.run", side_effect=responses,
            ) as run:
                corridor = query.find_corridor(
                    map_name="Azeroth", start=NavPoint(0, 1, 0),
                    stop_x=4, stop_y=1,
                )
        self.assertTrue(corridor.complete)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            run.call_args_list[1].args[0][-4:],
            ["0.5", "1.0", "1.0", "1.5"],
        )

    def test_nav_query_preserves_partial_frontier_and_requested_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.exe"
            worker.write_bytes(b"fixture")
            query = ClientAssetNavmeshQuery(worker=worker, nav_root=root)
            stdout = (
                '{"status":"OK","adt_x":28,"adt_y":28,'
                '"start":[0,0,0],"stop":[8,0,0],'
                '"requested_stop":[20,0,0],"complete":false,'
                '"doodad_avoidance_applied":true,"doodad_detour_count":1,'
                '"doodad_unresolved_segment_count":0,'
                '"doodad_unresolved_blockers":[],'
                '"clearance_inset_count":0,'
                '"steep_polygons_penalized":12,'
                '"observed_blocker_polygons_excluded":0,'
                '"impassable_uphill_polygons_excluded":0,'
                '"road_polygons_preferred":0,'
                '"nearest_road_polygon_to_start":-1,'
                '"road_polygon_bounds":[0,0,0,0],'
                '"height_candidates":1,"stop_height_candidates":1,'
                '"search_vantage_radial_clear_count":16,'
                '"search_vantage_radial_probe_count":16,'
                '"search_vantage_radial_probe_radius":8,'
                '"search_vantage_overhead_clear":true,'
                '"search_vantage_physical_surfaces":["ground"],'
                f'"start_awareness":{START_AWARENESS_JSON},'
                '"path":[[0,0,0],[8,0,0]],'
                '"polygons":[{"index":0,"area":0,"type":0,"slope_degrees":0,'
                '"physical_surfaces":["ground"],'
                '"vertices":[[0,-1,0],[8,-1,0],[8,1,0]],"centroid":[5,0,0]}],'
                '"portals":[]}\n'
            )
            completed = type("Completed", (), {
                "returncode": 0, "stdout": stdout, "stderr": "",
            })()
            with patch("client_navmesh_backend.subprocess.run", return_value=completed):
                corridor = query.find_corridor(
                    map_name="Azeroth", start=NavPoint(0, 0, 0), stop_x=20, stop_y=0
                )
        self.assertFalse(corridor.complete)
        self.assertEqual(corridor.stop, NavPoint(8, 0, 0))
        self.assertEqual(corridor.requested_stop, NavPoint(20, 0, 0))
        self.assertTrue(corridor.doodad_avoidance_applied)
        self.assertEqual(corridor.guidance_points(), corridor.points)


if __name__ == "__main__":
    unittest.main()
