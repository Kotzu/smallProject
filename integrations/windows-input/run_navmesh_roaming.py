from __future__ import annotations

import argparse
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from math import atan2, cos, hypot, isfinite, pi, sin
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable, Mapping
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
CAPTURE_INTEGRATION = ROOT / "integrations" / "windows-capture"
if str(CAPTURE_INTEGRATION) not in sys.path:
    sys.path.insert(0, str(CAPTURE_INTEGRATION))

from continuous_provider import ContinuousCaptureConfig, DxcamWindowCaptureProvider
from print_window_provider import Win32PrintWindowCaptureProvider
from combat_hud_detector import (
    CombatHudDetectionError,
    CombatHudDetector,
    load_profile as load_combat_profile,
)
from coordinate_hud_detector import CoordinateHudDetector
from player_actor_detector import (
    PlayerActorAnchorDetector,
    PlayerActorAnchorError,
    load_profile as load_player_actor_profile,
)
from visible_entity_detector import (
    VisibleEntityDetectorError,
    VisibleEntityNameplateDetector,
    load_profile as load_visible_entity_profile,
)
from minimap_detector import (
    MarkerCandidate,
    MinimapVisionDetector,
    load_profile as load_minimap_profile,
    world_heading_from_marker,
)
from pause_hotkey import PauseHotkeySource
from probe_coordinate_hud import bgra_view_from_packet, load_pinned_profile
from send_input_backend import CtypesWin32KeyboardBackend
from target_identity import (
    SCREEN_CAPTURE_READ_ONLY,
    VISIBLE_COORDINATE_HUD_READ_ONLY,
    load_capture_target_identity,
    verify_capture_process_identity,
)
from window_locator import WindowQuery, WindowSelectionError, locate_window
from perfect_assassin.capture import (
    CaptureDeadlineExceededError,
    CaptureStreamError,
    NoFreshCaptureFrameError,
)
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.knowledge import load_leveling_plan
from perfect_assassin.execution import SystemMonotonicClock
from perfect_assassin.domain.motion import ContinuousMotionFrame
from perfect_assassin.execution.contracts import (
    AuthorityBinding,
)
from perfect_assassin.execution.operator_control import (
    FileOperatorCombatControl,
    OperatorStopRequested,
)
from perfect_assassin.execution.ports import (
    CooperativeCancellation,
    SinkExecutionBudget,
)
from perfect_assassin.execution.windows_mouse_turn import WindowsMouseTurnSink
from perfect_assassin.execution.windows_continuous_motion import (
    CONTINUOUS_LEASE_TIMEOUT_MS,
)
from perfect_assassin.execution.continuous_motion_gateway import (
    CONTINUOUS_NAVIGATION_AUTHORIZATION_ID,
    ContinuousMotionAuthority,
    ContinuousMotionAuthorityError,
    ContinuousMotionExecutionGateway,
    load_continuous_motion_authority,
)
from perfect_assassin.execution.windows_send_input import (
    WindowsHotTargetSnapshot,
    WindowsInputSinkError,
    WindowsInputTargetBinding,
    WindowsSendInputSink,
)
from client_navmesh_backend import ClientAssetNavmeshQuery
from persistent_navmesh_awareness import AsyncPersistentNavmeshAwareness
from perfect_assassin.movement.trace_evidence import (
    decision_observation_record, local_boundary_trace_record, control_cycle_timing_record,
)
from perfect_assassin.movement.client_navmesh import (
    ClientNavmeshError,
    NavCorridor,
    NavPoint,
)
from perfect_assassin.movement.conditional_portal import (
    infer_conditional_traversal_frontier,
)
from perfect_assassin.movement.client_world_catalog import (
    load_client_world_catalog,
    verify_client_world_catalog,
)
from perfect_assassin.movement.camera_pivot import (
    CameraPivotController,
    CameraPivotIntent,
    nearest_navmesh_physical_surfaces,
)
from perfect_assassin.movement.camera_integrity import (
    assess_camera_integrity,
    navigation_camera_is_level,
)
from perfect_assassin.movement.client_continuity import (
    VisibleClientState,
    VisibleClientStateObservation,
    classify_visible_client_state,
    observation_to_record,
)
from perfect_assassin.movement.engine import MovementEngine, StructureEgressPlan
from perfect_assassin.movement.dynamic_avoidance import (
    DynamicAvoidanceDecision,
    DynamicCollisionAvoidance,
    DynamicEntityTrack,
    DynamicEntityTracker,
    ScreenEntityObservation,
)
from perfect_assassin.movement.dynamic_experience import (
    DynamicExperienceStore,
    encounter_from_track,
)
from perfect_assassin.movement.continuous_trajectory_follower import (
    ContinuousTrajectoryFollower,
)
from perfect_assassin.movement.adaptive_steering import (
    AdaptiveTrajectorySteeringController,
)
from perfect_assassin.movement.heading_estimator import (
    DisplacementHeadingEstimator,
    VisibleHeadingObserver,
    assess_initial_forward_direction,
)
from perfect_assassin.movement.heading_integrity import (
    MAX_HEADING_EVIDENCE_AGE_S,
    assess_heading_integrity,
    is_current_visual_heading,
)
from perfect_assassin.movement.live_preflight import (
    MAX_EXACT_BODY_HEADING_DISAGREEMENT_RAD,
    build_live_preflight_record,
)
from perfect_assassin.movement.movement_lab import MovementLabSnapshot
from perfect_assassin.movement.manual_path_recording import ManualPathRecording
from perfect_assassin.movement.mppi_steering import (
    AsyncMppiSteeringController,
    MppiConfiguration,
    PathIntegralSteeringPlanner,
)
from perfect_assassin.movement.observed_journey_trace import ObservedJourneyTrace
from perfect_assassin.movement.observation_port import MovementObservationPort
from perfect_assassin.movement.obstacle_memory import (
    BOUNDED_CELL_REPRESENTATION,
    DEFAULT_ACTOR_CLEARANCE_WORLD,
    DETOUR_EXCLUSION_EVIDENCE,
    LOCAL_CLEARANCE_EVIDENCE,
    LearnedObstacle,
    LearnedObstacleMemory,
)
from perfect_assassin.movement.recovery_memory import (
    LOCAL_CLEARANCE_STRATEGY,
    RecoveryStrategyMemory,
)
from perfect_assassin.movement.operator_path import OperatorAuthoredPath
from perfect_assassin.movement.predictive_steering import (
    CorridorProgressGate,
    PredictiveSteeringController,
    SteeringIntent,
    SteeringState,
    observed_motion_is_continuous,
)
from perfect_assassin.movement.trajectory_smoothing import (
    SmoothedTrajectory,
    smooth_navmesh_corridor,
)
from perfect_assassin.movement.road_semantic_planner import (
    ClientRoadSemanticPlanner,
    RoadWorldPoint,
    SemanticRoadRoute,
)
from perfect_assassin.movement.risk_aware_route_policy import (
    RiskAwareRoutePolicy,
    TravelCapability,
)
from perfect_assassin.movement.safe_retreat import SafeRetreatTrail
from perfect_assassin.movement.semantic_navigation import (
    select_risk_aware_semantic_route,
)
from perfect_assassin.movement.world_model import LayeredWorldModel
from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)
from perfect_assassin.movement.world_structure_index import (
    load_world_structure_index,
)
from perfect_assassin.runtime_paths import external_runtime_root
from perfect_assassin.movement.structure_access_graph import (
    load_structure_access_graph,
)
from perfect_assassin.movement.zone_transform import tbc243_zone_transform
from perfect_assassin.adapter.world_map_zone_catalog import (
    WorldMapZoneTransform,
    WorldMapZoneTransformCatalogError,
    load_world_map_zone_transform_catalog,
)


PIVOT_HEADING_PROGRESS_RAD = 0.08
PIVOT_STALL_TIMEOUT_S = 3.5
# A clearance anchor is a geometric turning point, not a destination.  A
# player-sized 1.5 yd arrival bubble handed the controller to the next leg
# before the capsule had actually cleared a post, so pure pursuit cut the
# inside of the bend.  Commit to within one bounded steering tick instead.
LOCAL_CLEARANCE_ARRIVAL_RADIUS_WORLD = 0.5
# A breadcrumb backtrack returns to a freshly observed safe pose.  The live
# HUD has roughly two yards of position jitter near a wall; requiring the
# clearance-anchor precision used by a side/pass maneuver can leave the
# controller circling just outside the anchor forever.  Keep this larger
# radius only for the verified breadcrumb return, then replan the original
# mission from the fresh pose.
BREADCRUMB_BACKTRACK_ARRIVAL_RADIUS_WORLD = 2.25
STRUCTURE_EGRESS_ARRIVAL_RADIUS_WORLD = 0.75
STRUCTURE_EGRESS_BLOCKER_ROUTE_MAX_OVERRUN_WORLD = 2.0
STUCK_PROGRESS_EVIDENCE_S = 1.8
COLLISION_SLIDE_EVIDENCE_S = 0.45
MAX_CORRIDOR_RECENTER_REPLANS_WITHOUT_PROGRESS = 3
# Start the replacement corridor while the current one is still safely
# drivable. The native client-navmesh query takes about 1.3 s on the LAB
# WorldPack; waiting for the old 2 yd divergence left only about 0.6 s before
# the confined-stall guard needed the result and forced a visible stop. This is
# a generic trajectory margin, not a coordinate or named-place exception.
CORRIDOR_RECENTER_PREPLAN_CROSS_TRACK_WORLD = 1.25
# The follower performs one global projection when adopting a new corridor, so
# an asynchronously planned start may safely sit behind the live actor. At
# normal run speed the measured 1.3 s query advances about 10-11 yd; accepting
# 15 yd preserves that completed work while the controller still rejects any
# pose that is actually off the returned corridor.
CORRIDOR_RECENTER_PREPLAN_MAX_START_DRIFT_WORLD = 15.0
# A legacy TBC client can rotate the camera before it rotates the avatar.  One
# forward chord is therefore not always enough to prove that W follows the
# planned tangent.  Keep the extra calibration bounded so a bad visual heading
# cannot create an endless live loop.
MAX_INITIAL_DIRECTION_PROBE_REALIGNS = 3
# Keep the displacement-derived heading authoritative for a few bounded
# ticks after a clean first-chord correction.  Otherwise the noisy minimap
# fallback can immediately overwrite it before the stationary pivot finishes.
INITIAL_DIRECTION_CALIBRATION_HOLD_FRAMES = 12
# A clean first chord that disagrees with the corridor can move the actor
# toward a nearby wall before calibration finishes.  Rebuild the corridor once
# from that freshly observed pose, without inventing collision evidence.  The
# bound prevents a bad client heading from becoming a replan loop.
MAX_INITIAL_DIRECTION_CORRIDOR_REPLANS = 1
# Ignore a visual heading sample unless the client has shown a meaningful
# forward chord.  Tiny capture jitter is not movement evidence.
INITIAL_FORWARD_DIRECTION_MIN_DISPLACEMENT_WORLD = 0.75
# A first-chord heading sample is useful only while the actor remains near the
# validated corridor; a wide miss is treated as unrelated collision evidence.
INITIAL_FORWARD_DIRECTION_MAX_CROSS_TRACK_WORLD = 1.75
# A clean first-chord correction normally leaves the actor inside the already
# validated corridor.  Rebuilding that corridor for a sub-two-yard offset can
# spend seconds in a synchronous native query and create a live-only pause.
# Only request the expensive pose replan once the actor is outside the normal
# recenter envelope; the stationary pivot still corrects heading immediately.
INITIAL_DIRECTION_REPLAN_MIN_CROSS_TRACK_WORLD = 2.0
# A displacement may be physically large while still being a sideways slide
# along a wall.  Usually only let a heading realignment replace the camera
# estimate when the observed chord has a small forward projection onto the
# planned corridor tangent.  The very first chord gets one bounded exception:
# when no collision evidence exists, it can repair a stale camera/avatar
# orientation before the client reaches a wall.
MIN_DIRECTION_REALIGN_TANGENT_PROJECTION = 0.25
# A legacy client can lose the relation between continuous RMB yaw and the
# avatar's real forward chord after a camera/contact disturbance.  Treat one
# large, client-observed divergence as a bounded heading reacquisition, not as
# permission to keep W pushing into the same wall.  The limit is per corridor
# and never grants additional input authority.
MAX_LIVE_HEADING_DIVERGENCE_REALIGNS = 2
LIVE_HEADING_DIVERGENCE_THRESHOLD_RAD = 1.25


def _allow_initial_direction_realignment(
    *,
    tangent_projection: float | None,
    initial_realignment_count: int,
    cross_track_error_world: float,
    collision_slide_s: float,
    collision_evidence: bool,
    verified_breadcrumb_recovery: bool = False,
) -> bool:
    """Allow one clean first-chord calibration before treating a slide as a wall.

    A stale TBC camera can make the first W chord point almost opposite the
    corridor even in an open room.  That chord is valuable facing evidence when
    no collision has been observed.  Once a collision/slide is known, the old
    tangent-projection guard remains authoritative so a wall slide cannot
    overwrite the integrated yaw.  A single fresh client-visible breadcrumb
    return is the bounded exception: those positions already prove a short
    safe reverse corridor, so one new forward chord may reacquire a stale
    camera/avatar relation.
    """

    if tangent_projection is not None and tangent_projection >= MIN_DIRECTION_REALIGN_TANGENT_PROJECTION:
        return True
    return (
        initial_realignment_count == 1
        and collision_slide_s < COLLISION_SLIDE_EVIDENCE_S
        and cross_track_error_world <= INITIAL_FORWARD_DIRECTION_MAX_CROSS_TRACK_WORLD
        and (
            not collision_evidence
            or verified_breadcrumb_recovery
        )
    )


HUD_PROBE = ROOT / "integrations" / "windows-capture" / "probe_coordinate_hud.py"
DEFAULT_RECEIPT = (
    ROOT / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
)
EXTERNAL_RUNTIME_ROOT = external_runtime_root(ROOT)
DEFAULT_NAV_ROOT = (
    EXTERNAL_RUNTIME_ROOT / "navigation" / "tbc243-human-road-corridor-v6"
)
DEFAULT_WORLD_CATALOG = (
    ROOT / "config" / "navigation" / "client-world-catalog-tbc243-8606.json"
)
DEFAULT_WORLD_CATALOG_ASSET = (
    ROOT / "data" / "runtime" / "client-catalog" / "tbc243-8606" / "Map.dbc"
)
WORLD_CATALOG_SCHEMA = ROOT / "contracts" / "client-world-catalog.schema.json"
DEFAULT_ZONE_TRANSFORM_CATALOG = (
    ROOT / "config" / "pose" / "world-map-zone-transforms-tbc243-8606.json"
)
ZONE_TRANSFORM_CATALOG_SCHEMA = (
    ROOT / "contracts" / "world-map-zone-transform-catalog.schema.json"
)
DEFAULT_NAV_PROFILE_ID = "tbc243-azeroth-full-v3"
DEFAULT_WORLD_PACK_PROFILE = (
    ROOT / "config" / "navigation" / "world-pack-runtime-tbc243-azeroth-full-v3.json"
)
DEFAULT_WORLD_PACK_STORE = EXTERNAL_RUNTIME_ROOT / "worldpacks"
DEFAULT_WORLD_STRUCTURE_INDEX = (
    ROOT
    / "data"
    / "runtime"
    / "client-catalog"
    / "tbc243-8606"
    / "azeroth-full-v3-world-structure-index-v1.json"
)
DEFAULT_STRUCTURE_ACCESS_GRAPH: Path | None = None
WORLD_PACK_PROFILE_SCHEMA = (
    ROOT / "contracts" / "world-pack-runtime-profile.schema.json"
)
WORLD_PACK_SCHEMA = ROOT / "contracts" / "standalone-world-pack.schema.json"
WORLD_STRUCTURE_INDEX_SCHEMA = ROOT / "contracts" / "world-structure-index.schema.json"
STRUCTURE_ACCESS_GRAPH_SCHEMA = (
    ROOT / "contracts" / "structure-access-graph.schema.json"
)
DEFAULT_WORKER = (
    ROOT
    / "data"
    / "runtime"
    / "native-build"
    / "pa_nav_probe-v34"
    / "Debug"
    / "pa_nav_probe.exe"
)
DEFAULT_SEMANTIC_CATALOG = (
    ROOT / "config" / "movement-lab" / "semantic-destinations-tbc243.json"
)
RESULT_ROOT = ROOT / "data" / "runtime" / "navigation-f3b" / "results"
CONTINUITY_STATE = (
    ROOT / "data" / "runtime" / "navigation-f3b" / "continuity" / "latest.json"
)
MOVEMENT_LAB_STATE = ROOT / "data" / "runtime" / "movement-lab" / "latest.json"
DEFAULT_DYNAMIC_EXPERIENCE_STORE = (
    EXTERNAL_RUNTIME_ROOT / "memory" / "dynamic-experience-v1.sqlite3"
)
LEARNED_OBSTACLE_MEMORY = (
    ROOT / "data" / "runtime" / "navigation-f3b" / "learned-obstacles-tbc243.json"
)
RECOVERY_STRATEGY_MEMORY = (
    ROOT / "data" / "runtime" / "navigation-f3b" / "recovery-strategy-memory-tbc243.json"
)
DEFAULT_TRAVERSED_SURFACE_PRIOR = (
    ROOT / "data" / "runtime" / "movement-lab" / "manual-path-recording.json"
)
CAPTURE_SCHEMA = ROOT / "contracts" / "capture-frame.schema.json"
COORDINATE_SCHEMA = ROOT / "contracts" / "coordinate-hud.schema.json"
COMBAT_SCHEMA = ROOT / "contracts" / "combat-hud.schema.json"
MINIMAP_SCHEMA = ROOT / "contracts" / "minimap-vision.schema.json"
DYNAMIC_ENCOUNTER_SCHEMA = (
    ROOT / "contracts" / "dynamic-encounter-observation.schema.json"
)
DYNAMIC_EXPERIENCE_SUMMARY_SCHEMA = (
    ROOT / "contracts" / "dynamic-experience-summary.schema.json"
)
LIVE_PREFLIGHT_SCHEMA = ROOT / "contracts" / "live-observation-preflight.schema.json"
AUTHORIZATION_SCHEMA = ROOT / "contracts" / "execution-target-authorization.schema.json"
CONTINUOUS_MOTION_ARM_SCHEMA = (
    ROOT / "contracts" / "continuous-motion-runtime-arm.schema.json"
)
RECEIPT_SCHEMA = ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
COORDINATE_PROFILE = ROOT / "config" / "pose" / "coordinate-hud-tbc243-v1.json"
PLAYER_ACTOR_PROFILE = (
    ROOT / "config" / "pose" / "player-actor-anchor-tbc243-predator-v2.json"
)
COMBAT_PROFILE = ROOT / "config" / "combat" / "combat-hud-tbc243-v2.json"
MINIMAP_PROFILE = ROOT / "config" / "pose" / "minimap-tbc243-8606.json"
VISIBLE_ENTITY_PROFILE = (
    ROOT / "config" / "navigation" / "visible-entity-nameplates-tbc243-v1.json"
)
# Long, straight surfaces such as roads, bridges and hallways are one travel
# lane, not a chain of micro-destinations.  Corners are still retained by the
# chord-deviation gate below; only collinear raster samples are coalesced.
# A 40-yard chord can require two sequential Detour queries when the first
# physical corridor leaves the semantic road surface: one to discover the
# deviation and one to validate the inserted route midpoint.  At running
# speed that dependency can finish after the actor reaches the shared point.
# A 25-yard generic horizon keeps straight roads coalesced while making the
# first physical query local enough that runtime refinement is exceptional.
SEMANTIC_LOCAL_GOAL_SPACING_WORLD = 25.0
SEMANTIC_LOCAL_GOAL_MIN_CORNER_SPACING_WORLD = 8.0
SEMANTIC_LOCAL_GOAL_MIN_GENTLE_BEND_SPACING_WORLD = 20.0
SEMANTIC_LOCAL_GOAL_MAX_CHORD_DEVIATION_WORLD = 2.0
SEMANTIC_LOCAL_GOAL_SHARP_TURN_RAD = 0.55
# DXGI acquisition is still required to be fresh and bounded, but the LAB
# desktop occasionally adds a single compositor frame while WoW remains the
# foreground window.  Keep navigation's deadline below one control period and
# leave the stricter 250 ms profile for one-shot coordinate probes.
NAVIGATION_CAPTURE_DEADLINE_MS = 300.0
# The continuous actuator releases W/RMB after this bounded lease when a
# fresh client frame is late.  Heading integration must never pretend that a
# mouse velocity stayed active through a longer capture/planner stall.
MOUSE_HEADING_ACTIVE_LEASE_S = CONTINUOUS_LEASE_TIMEOUT_MS / 1000.0
# A long semantic chord is only a proposal.  Detour may legally leave the
# atlas route to avoid a doodad or shorten a bend because all nearby ground is
# walkable.  Refine that proposal through the original fine A* samples when
# the physical corridor wanders too far or becomes disproportionately long.
# This is global geometry, not a bridge/forest coordinate exception.
SEMANTIC_CORRIDOR_MAX_ROUTE_DEVIATION_WORLD = 4.0
SEMANTIC_CORRIDOR_MAX_ROUTE_STRETCH = 1.30
SEMANTIC_REFINEMENT_MIN_SPACING_WORLD = 6.0
# Intermediate semantic points are a road prior, not places where the actor
# should stop and look back. Prepare the next Detour leg while the current one
# is still being followed.  The prepared leg starts at the shared semantic
# road point, never at an earlier live pose: planning from the actor 35 yards
# early allowed the next leg to bypass the junction and caused 90-140 degree
# camera snaps at hand-off.  Switch only at player-sized distance from the
# shared point and only when the new corridor already agrees with current yaw.
# At the measured travel speed the preplan radius still leaves several seconds
# for the isolated worker; live LAB queries measured 0.38-0.77 seconds.
SEMANTIC_PREPLAN_RADIUS_WORLD = 35.0
# The default helper threshold remains intentionally small for unit-level
# policy checks.  Runtime Detour queries can take several seconds on a cold
# WorldPack tile, so the live loop starts them farther ahead while the current
# corridor is still authoritative.
SEMANTIC_RUNTIME_PREPLAN_RADIUS_WORLD = 140.0
SEMANTIC_FLYBY_RADIUS_WORLD = 3.0
SEMANTIC_HANDOFF_MAX_CROSS_TRACK_WORLD = 4.0
SEMANTIC_HANDOFF_MAX_HEADING_ERROR_RAD = 0.90
SEMANTIC_HANDOFF_LOOKAHEAD_WORLD = 6.0
# Cached Detour legs are prepared from the exact semantic waypoint while the
# live actor can reach that handoff a few yards off-centre. A loop in cached
# guidance can then make nearest-segment projection select a tangent which
# initially points behind the next semantic goal. Permit broad clearance arcs,
# but require a fresh query from the live pose for a greater-than-100-degree
# retreat.
SEMANTIC_HANDOFF_MAX_GOAL_DIVERGENCE_RAD = 1.7453292519943295
# A large static prop can cover more than one coalesced semantic goal.  When a
# frontier repeats, permit a bounded number of additional fine atlas samples
# beyond the next coarse goal so Detour can reach the first sample outside the
# prop.  The samples remain semantic evidence and each candidate is revalidated
# by the client navmesh before it can be selected.
SEMANTIC_STATIC_FRONTIER_MAX_FORWARD_WAYPOINTS = 8
# Native frontier probes are independent read-only client-navmesh requests.
# A bounded fan-out lets the dedicated frontier worker validate the ordered
# candidate horizon without serializing every failed candidate into a visible
# input-lease gap.  The local v4 frontier batch is ten probes; four workers
# took about 3.2 s, while ten workers took about 1.5 s on the pinned client
# WorldPack.  Keep the value explicit and below the reviewed candidate cap.
SEMANTIC_STATIC_FRONTIER_WORKER_QUERY_CONCURRENCY = 10
# The forward-bypass helper extends through the next coalesced semantic goal
# and then by the reviewed forward horizon.  That inclusive range can contain
# one more candidate than the extension bound itself (the live trace measured
# nine candidates with an eight-cell extension).  Keep the worker bound aligned
# with the helper's explicit maximum instead of rejecting a valid bounded batch
# and falling back to a synchronous query at the frontier.
SEMANTIC_STATIC_FRONTIER_MAX_CANDIDATES = 32
# Semantic road samples inside one known enclosure are guidance, not mandatory
# stops. Scan only a small forward horizon for the first graph-backed,
# navmesh-revalidated exit instead of walking deeper and then reversing.
STRUCTURE_EGRESS_SEMANTIC_LOOKAHEAD_GOALS = 8
RECOVERY_BUDGET_RESET_DISTANCE_WORLD = 15.0
CLIENT_BUILD = 8606
VISIBLE_STATE_REACQUISITION_ATTEMPTS = 5
VISIBLE_STATE_REACQUISITION_INTERVAL_S = 0.05
# Restoring a saved 2.4.3 camera view is asynchronous.  Inside a WMO the
# first frames can show only the top of the avatar while the client resolves
# its collision-composed third-person view.  Give that read-only compositor
# transition a bounded window, but require several consecutive visible frames
# before arming movement.  No key is held during this wait.
CAMERA_STARTUP_SETTLE_ATTEMPTS = 40
CAMERA_STARTUP_SETTLE_INTERVAL_S = 0.10
CAMERA_STARTUP_STABLE_VISIBLE_FRAMES = 3
# A fresh route slice must have a client-visible heading before it can lease
# forward input.  The coordinate HUD can briefly omit facing while the camera
# settles; bounded read-only reacquisition handles that compositor window.
# If the heading remains unavailable, fail closed instead of asking the
# controller for its legacy natural-forward calibration stride.
INITIAL_HEADING_REACQUISITION_ATTEMPTS = 4
INITIAL_HEADING_REACQUISITION_INTERVAL_S = 0.05
# Nameplate awareness is read-only context, not the pose/control clock. Four
# control frames keep it at roughly 5 Hz while staying below the dynamic-track
# 0.8 s TTL; this bounds full-frame copies and Python component extraction so
# they cannot regularly contend with DXGI pose acquisition.
DYNAMIC_DETECTION_INTERVAL_FRAMES = 4
# Keep the pre-actuator pose budget just below the 300 ms capture deadline;
# this prevents a stale decision without rejecting a frame during one bounded
# compositor interval.
MAXIMUM_CONTROL_OBSERVATION_AGE_MS = 295.0
# Refresh before the actuator's hard 175 ms rejection boundary.  Windows
# scheduling and the final steering/avoidance composition still consume a few
# milliseconds after this check; checking at the same value creates a race.
PRECONTROL_POSE_REFRESH_AGE_MS = 120.0
# A stale command is never sent: the Windows sink releases every owned input
# and raises.  One transient scheduler/compositor delay must not discard the
# whole journey, though.  Reacquire a fresh client-visible pose and recompute
# the frame, with a small consecutive cap so persistent overload still fails
# closed instead of looping forever.
MAX_CONSECUTIVE_STALE_CONTROL_FRAME_RETRIES = 3
EXACT_BODY_HEADING_SOURCE = "COORDINATE_HUD_EXACT"
MINIMAP_BODY_HEADING_SOURCE = "MINIMAP_VISION_FALLBACK"
CAMERA_YAW_CONTROL_SOURCE = "RMB_MOUSE_INTEGRATED_FROM_VISIBLE_BODY"
# The raw HUD value and the heading handed to the controller originate in the
# same observation.  A disagreement larger than this is therefore evidence
# of a stale/mixed frame, not a harmless camera offset.  The check is a
# consistency gate; it does not claim that a legacy client exposes more
# precision than its HUD protocol provides.
# A post-plan pose refresh can briefly omit the facing field even though no
# input was sent while planning. Keep the last exact body yaw for that one
# bounded refresh, but label it as preserved evidence so an exact-heading
# gate never mistakes it for a fresh HUD proof.
PRESERVED_EXACT_BODY_HEADING_SOURCE = "COORDINATE_HUD_EXACT_PRESERVED"
# These sources are all client-visible estimates.  Before the first W, the
# local navmesh tangent may resolve the minimap marker's two-ended axis; after
# motion starts they remain ordinary fused heading evidence.
VISUAL_FALLBACK_HEADING_SOURCES = frozenset(
    {
        "MINIMAP_VISION_FALLBACK",
        "MOUSE_INTEGRATED_MINIMAP_FALLBACK",
        "DISPLACEMENT_HEADING_CONFIRMED_MINIMAP_FALLBACK",
        "VISIBLE_CLIENT_HEADING_INITIAL",
        "VISIBLE_CLIENT_HEADING_FUSED",
        "VISIBLE_CLIENT_HEADING_AXIAL_FLIP_FUSED",
    }
)


def _routine_aggro_travel_allowed(
    *,
    enabled: bool,
    in_combat: bool | None,
    health_fraction: float | None,
    minimum_health_fraction: float,
) -> bool:
    """Keep a journey objective through incidental aggro, never through danger."""

    return bool(
        enabled
        and in_combat is True
        and health_fraction is not None
        and health_fraction >= minimum_health_fraction
    )


class ClientVisibleStateError(RuntimeError):
    """A fail-closed transition observed from the exact client window."""

    def __init__(
        self,
        observation: VisibleClientStateObservation,
        *,
        last_valid_pose: dict[str, object] | None,
    ) -> None:
        super().__init__(
            f"visible client state is {observation.state.value} "
            f"at confidence {observation.confidence:.3f}"
        )
        self.observation = observation
        self.last_valid_pose = last_valid_pose


class CaptureObservationError(RuntimeError):
    """A fresh exact-window observation could not be acquired safely."""

    def __init__(
        self,
        cause: BaseException,
        *,
        last_valid_pose: dict[str, object] | None,
    ) -> None:
        super().__init__(str(cause))
        self.cause_type = type(cause).__name__
        self.detail = str(cause)
        self.last_valid_pose = last_valid_pose


class CombatHandoffRequired(RuntimeError):
    """Fresh visible combat state requires the separate combat authority."""

    def __init__(
        self,
        observation: dict[str, object],
        *,
        target_identity_crc16: int | None,
    ) -> None:
        super().__init__("visible combat requires movement-to-combat handoff")
        self.observation = observation
        self.target_identity_crc16 = target_identity_crc16


class LiveCoordinatePoseSource:
    """One in-process DXGI stream for the 20 Hz navigation feedback loop."""

    def __init__(
        self,
        *,
        authorization_file: Path,
        receipt_file: Path,
        receipt: dict[str, object],
        session_id: str,
        allow_ghost_navigation: bool = False,
        continue_through_routine_aggro: bool = False,
        minimum_travel_health_fraction: float = 0.55,
        enforce_combat_handoff: bool = True,
        require_player_anchor: bool = False,
        require_foreground_capture: bool = True,
        on_capture_stall: Callable[[], None] | None = None,
        observe_afk: bool = False,
        observe_location: bool = False,
    ) -> None:
        self._receipt_file = receipt_file
        self._observe_afk = observe_afk
        self.latest_afk_packet = None
        self._observe_location = observe_location
        self.latest_location_labels = None
        self._location_stream = None
        if observe_location:
            from perfect_assassin.adapter.location_hud import LocationStream
            self._location_stream = LocationStream(
                f"{receipt['pid']}:{receipt['process_creation_filetime_utc']}"
            )
        self._receipt = receipt
        self._counter = 0
        self._allow_ghost_navigation = allow_ghost_navigation
        self._continue_through_routine_aggro = bool(continue_through_routine_aggro)
        self._enforce_combat_handoff = bool(enforce_combat_handoff)
        if type(require_player_anchor) is not bool:
            raise ValueError("require_player_anchor must be boolean")
        if type(require_foreground_capture) is not bool:
            raise ValueError("require_foreground_capture must be boolean")
        self._require_player_anchor = require_player_anchor
        self._camera_integrity_gate_armed = False
        self._last_camera_settle_attempts = 0
        self._last_camera_settle_visible_frames = 0
        if not 0.25 <= minimum_travel_health_fraction <= 0.90:
            raise ValueError("minimum travel health fraction is invalid")
        self._minimum_travel_health_fraction = float(minimum_travel_health_fraction)
        self._routine_aggro_observation_count = 0
        self._on_capture_stall = on_capture_stall
        self._capture_restart_count = 0
        self._last_capture_latency_ms: float | None = None
        self._last_observation_latency_ms: float | None = None
        self._capture_validator = ContractValidator(CAPTURE_SCHEMA)
        self._observation_validator = ContractValidator(COORDINATE_SCHEMA)
        self._combat_validator = ContractValidator(COMBAT_SCHEMA)
        self._minimap_validator = ContractValidator(MINIMAP_SCHEMA)
        profile, _profile_sha256 = load_pinned_profile(COORDINATE_PROFILE)
        self._detector = CoordinateHudDetector(
            profile,
            self._capture_validator,
            self._observation_validator,
            search_window_fraction=(0.015, 0.11, 0.19, 0.24),
            reuse_marker_geometry=True,
        )
        self._player_actor_detector = PlayerActorAnchorDetector(
            load_player_actor_profile(PLAYER_ACTOR_PROFILE)
        )
        self._combat_detector = CombatHudDetector(
            load_combat_profile(COMBAT_PROFILE),
            self._capture_validator,
            self._combat_validator,
            search_window_fraction=(0.015, 0.11, 0.19, 0.24),
            reuse_marker_geometry=True,
        )
        self._visible_entity_detector = VisibleEntityNameplateDetector(
            load_visible_entity_profile(VISIBLE_ENTITY_PROFILE)
        )
        self._dynamic_detection_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="visible-entity-read-only",
        )
        self._dynamic_detection_future: Future[
            tuple[ScreenEntityObservation, ...]
        ] | None = None
        self._dynamic_detection_frame_counter = 0
        self._latest_dynamic_observations: tuple[ScreenEntityObservation, ...] = ()
        self._latest_dynamic_detection_error: str | None = None
        self._latest_in_combat: bool | None = None
        self._latest_combat_target_identity_crc16: int | None = None
        self._latest_travel_capability: TravelCapability | None = None
        self._latest_facing_source = "UNAVAILABLE"
        self._latest_facing_confidence: float | None = None
        self._last_player_alive: bool | None = None
        self._last_player_ghost: bool | None = None
        self._last_valid_observation: dict[str, object] | None = None
        self._latest_camera_integrity: dict[str, object] | None = None
        self._minimap_profile = load_minimap_profile(
            MINIMAP_PROFILE,
            self._minimap_validator,
        )
        self._minimap_detector = MinimapVisionDetector(
            self._minimap_profile,
            self._capture_validator,
            self._minimap_validator,
        )
        self._identity = load_capture_target_identity(
            authorization_file,
            AUTHORIZATION_SCHEMA,
            Path(str(receipt["executable_path"])),
            str(receipt["client_build"]),
            required_capabilities=(
                SCREEN_CAPTURE_READ_ONLY,
                VISIBLE_COORDINATE_HUD_READ_ONLY,
            ),
        )
        self._query = WindowQuery(
            pid=int(receipt["pid"]),
            hwnd=int(str(receipt["hwnd"]), 16),
            title_exact=str(receipt["window_title"]),
            class_exact=str(receipt["window_class"]),
            require_foreground=require_foreground_capture,
        )
        capture_config = ContinuousCaptureConfig(
                query=self._query,
                session_id=session_id,
                target_profile=self._identity.target_profile,
                instance_id=self._identity.instance_id,
                actor_role=self._identity.actor_role,
                actor_id=self._identity.actor_id,
                decision_context=self._identity.decision_context,
                memory_namespace=self._identity.memory_namespace,
                expected_character_name=self._identity.expected_character_name,
                credential_alias=self._identity.credential_alias,
                binding_assurance_state=self._identity.binding_assurance_state,
                binding_assurance_evidence_refs=self._identity.binding_assurance_evidence_refs,
                authorization_sha256=self._identity.authorization_sha256,
                client_build=self._identity.client_build,
                build_signature=self._identity.build_signature,
                identity_evidence_ref=self._identity.evidence_ref,
                actor_evidence_ref=self._identity.actor_evidence_ref,
                backend=("dxgi" if require_foreground_capture else "printwindow"),
                device_index=0,
                output_index=0,
                buffer_capacity=1,
                capture_deadline_ms=NAVIGATION_CAPTURE_DEADLINE_MS,
        )
        provider_type = (
            DxcamWindowCaptureProvider
            if require_foreground_capture
            else Win32PrintWindowCaptureProvider
        )
        self._provider = provider_type(
            capture_config,
            self._capture_validator,
            window_locator=locate_window,
        )

    def _verify_identity(self) -> None:
        verify_capture_process_identity(
            int(self._receipt["pid"]),
            Path(str(self._receipt["executable_path"])),
            self._identity,
            hwnd=int(str(self._receipt["hwnd"]), 16),
            expected_title=str(self._receipt["window_title"]),
            expected_class=str(self._receipt["window_class"]),
            receipt_path=self._receipt_file,
            receipt_schema_path=RECEIPT_SCHEMA,
            window_resolver=lambda: locate_window(self._query),
        )

    def open(self) -> None:
        self._verify_identity()
        self._provider.open()

    def close(self) -> None:
        self._provider.close()
        if self._dynamic_detection_future is not None:
            self._dynamic_detection_future.cancel()
        self._dynamic_detection_executor.shutdown(wait=False, cancel_futures=True)

    @property
    def capture_restart_count(self) -> int:
        return self._capture_restart_count

    @property
    def latest_dynamic_observations(
        self,
    ) -> tuple[ScreenEntityObservation, ...]:
        return self._latest_dynamic_observations

    @property
    def latest_dynamic_detection_error(self) -> str | None:
        return self._latest_dynamic_detection_error

    @property
    def latest_in_combat(self) -> bool | None:
        return getattr(self, "_latest_in_combat", None)

    @property
    def latest_combat_target_identity_crc16(self) -> int | None:
        return getattr(self, "_latest_combat_target_identity_crc16", None)

    @property
    def latest_travel_capability(self) -> TravelCapability | None:
        return getattr(self, "_latest_travel_capability", None)

    @property
    def latest_facing_source(self) -> str:
        return getattr(self, "_latest_facing_source", "UNAVAILABLE")

    @property
    def latest_facing_confidence(self) -> float | None:
        return getattr(self, "_latest_facing_confidence", None)

    @property
    def latest_camera_integrity(self) -> dict[str, object] | None:
        """Return the last screen-space actor-anchor evidence."""

        return getattr(self, "_latest_camera_integrity", None)

    @property
    def last_capture_latency_ms(self) -> float | None:
        """Wall-clock acquisition time for the most recent capture attempt."""

        return self._last_capture_latency_ms

    @property
    def last_observation_latency_ms(self) -> float | None:
        """Wall-clock time for capture plus bounded visual decoding."""

        return self._last_observation_latency_ms

    def arm_camera_integrity_gate(self) -> None:
        """Require a visible player anchor before any later control frame.

        Startup deliberately arms this only after the saved camera composition
        has been restored.  A stale ceiling view can therefore be normalized
        once, while every subsequent actor disappearance releases movement and
        fails closed.
        """

        self._camera_integrity_gate_armed = True

    @property
    def last_camera_settle_attempts(self) -> int:
        """Number of read-only frames used by the latest startup settle."""

        return int(getattr(self, "_last_camera_settle_attempts", 0))

    @property
    def last_camera_settle_visible_frames(self) -> int:
        """Consecutive visible frames reached by the latest startup settle."""

        return int(getattr(self, "_last_camera_settle_visible_frames", 0))

    def wait_for_camera_integrity(
        self,
        *,
        max_attempts: int = CAMERA_STARTUP_SETTLE_ATTEMPTS,
        interval_s: float = CAMERA_STARTUP_SETTLE_INTERVAL_S,
        required_visible_frames: int = CAMERA_STARTUP_STABLE_VISIBLE_FRAMES,
    ) -> dict[str, object]:
        """Wait for a settled, visible actor before arming navigation.

        The camera-home chat command can take more than one compositor frame
        to finish, especially at a WMO doorway.  During this bounded wait the
        actor gate is intentionally still unarmed, so observations are
        read-only.  A fresh actor anchor must be visible for a short streak;
        otherwise this method raises the same fail-closed error used after
        movement starts.  It never falls back to HUD-only evidence.
        """

        if type(max_attempts) is not int or not 1 <= max_attempts <= 80:
            raise ValueError("camera startup settle attempt bound is invalid")
        if (
            isinstance(interval_s, bool)
            or not isinstance(interval_s, (int, float))
            or not isfinite(float(interval_s))
            or not 0.01 <= float(interval_s) <= 1.0
        ):
            raise ValueError("camera startup settle interval is invalid")
        if (
            type(required_visible_frames) is not int
            or not 1 <= required_visible_frames <= 8
        ):
            raise ValueError("camera startup visible-frame bound is invalid")

        self._last_camera_settle_attempts = 0
        self._last_camera_settle_visible_frames = 0
        visible_streak = 0
        last_observation: dict[str, object] | None = None
        for attempt in range(1, max_attempts + 1):
            last_observation = self.next_observation()
            camera_integrity = getattr(self, "_latest_camera_integrity", None)
            decision = assess_camera_integrity(
                camera_integrity,
                require_visible_anchor=True,
            )
            if decision.allow_control and decision.tracking_state == "VISIBLE":
                visible_streak += 1
                self._last_camera_settle_visible_frames = visible_streak
                if visible_streak >= required_visible_frames:
                    self._last_camera_settle_attempts = attempt
                    return last_observation
            else:
                visible_streak = 0
                self._last_camera_settle_visible_frames = 0
            self._last_camera_settle_attempts = attempt
            if attempt < max_attempts:
                time.sleep(float(interval_s))

        latest_camera = getattr(self, "_latest_camera_integrity", None)
        raw_confidence = (
            latest_camera.get("confidence")
            if isinstance(latest_camera, dict)
            else None
        )
        camera_confidence = (
            float(raw_confidence)
            if isinstance(raw_confidence, (int, float))
            and not isinstance(raw_confidence, bool)
            and isfinite(float(raw_confidence))
            else 0.0
        )
        camera_state = VisibleClientStateObservation(
            state=VisibleClientState.UNKNOWN,
            confidence=0.0,
            evidence={
                "coordinate_hud_crc_valid": bool(
                    isinstance(last_observation, dict)
                    and last_observation.get("tracking_state") == "VALID"
                ),
                "player_actor_anchor_visible": False,
                "camera_integrity_confidence": (
                    camera_confidence
                ),
            },
        )
        raise ClientVisibleStateError(
            camera_state,
            last_valid_pose=last_observation,
        )

    @property
    def routine_aggro_observation_count(self) -> int:
        return self._routine_aggro_observation_count

    def _next_capture_packet(self):
        """Acquire a frame, releasing movement before one bounded restart."""

        started_s = time.monotonic()
        last_error: CaptureStreamError | None = None
        try:
            for restart_attempt in range(2):
                for capture_attempt in range(3):
                    self._verify_identity()
                    try:
                        return self._provider.next_frame()
                    except NoFreshCaptureFrameError as error:
                        last_error = error
                        if capture_attempt < 2:
                            time.sleep(0.025)
                    except CaptureDeadlineExceededError as error:
                        # A busy desktop compositor can make one DXGI acquisition
                        # exceed the nominal frame budget. Retry the same bounded
                        # observation before restarting or failing closed; never
                        # continue from an old frame.
                        last_error = error
                        if capture_attempt < 2:
                            time.sleep(0.025)
                if restart_attempt == 0:
                    # Never keep W/RMB leased while DXGI is being restarted.  A
                    # successful fresh observation is required before the caller
                    # can submit another motion frame.
                    if self._on_capture_stall is not None:
                        self._on_capture_stall()
                    self._provider.close()
                    self._verify_identity()
                    self._provider.open()
                    self._capture_restart_count += 1
            assert last_error is not None
            raise last_error
        finally:
            elapsed_ms = max(0.0, (time.monotonic() - started_s) * 1000.0)
            self._last_capture_latency_ms = elapsed_ms
            # A capture retry/restart can outlive the actuator lease even when
            # the final frame is valid. Keep the release-only safety callback
            # explicit so a late frame can never imply that old controls were
            # still held continuously.
            if elapsed_ms > CONTINUOUS_LEASE_TIMEOUT_MS and self._on_capture_stall is not None:
                self._on_capture_stall()

    def next_observation(self) -> dict[str, object]:
        started_s = time.monotonic()
        try:
            return self._next_observation_impl()
        finally:
            elapsed_ms = max(0.0, (time.monotonic() - started_s) * 1000.0)
            self._last_observation_latency_ms = elapsed_ms
            # Capture is only one part of a live observation.  Detector work
            # or a compositor stall can also outlive the actuator lease.  The
            # callback is release-only and idempotent; it never grants a new
            # frame or extends authority.
            if elapsed_ms > CONTINUOUS_LEASE_TIMEOUT_MS and self._on_capture_stall is not None:
                self._on_capture_stall()

    def _next_observation_impl(self) -> dict[str, object]:
        """Return one fresh pose after bounded, motion-safe visual reacquisition.

        A single incomplete DXGI frame can make either CRC HUD temporarily
        unavailable while the client is otherwise still in world. Movement
        must never continue from that frame, but treating the first pose or
        combat-marker miss as terminal makes a long journey depend on every
        individual capture. Release all leased controls and reacquire a small
        fixed number of entirely new frames. The final detector/visible-state
        error is preserved unchanged if the client does not recover inside
        this bounded window.
        """

        last_reacquisition_error: (
            ClientVisibleStateError | CombatHudDetectionError | None
        ) = None
        for attempt in range(VISIBLE_STATE_REACQUISITION_ATTEMPTS):
            try:
                observation = self._next_fresh_observation()
                if getattr(self, "_latest_in_combat", None) is True:
                    # Read-only observers such as the operator demonstration
                    # recorder must keep measuring while the human handles an
                    # aggro encounter. Only an input-owning movement runtime
                    # requires the fail-closed combat authority handoff.
                    if not self._enforce_combat_handoff:
                        return observation
                    capability = getattr(self, "_latest_travel_capability", None)
                    if _routine_aggro_travel_allowed(
                        enabled=self._continue_through_routine_aggro,
                        in_combat=True,
                        health_fraction=(
                            None if capability is None else capability.health_fraction
                        ),
                        minimum_health_fraction=(self._minimum_travel_health_fraction),
                    ):
                        # Travel aggro is not a destination change. Keep the
                        # already validated topographic corridor and let the
                        # pursuing NPC leash naturally. A health breach still
                        # releases movement and hands off fail-closed.
                        self._routine_aggro_observation_count += 1
                        return observation
                    raise CombatHandoffRequired(
                        observation,
                        target_identity_crc16=(
                            getattr(
                                self,
                                "_latest_combat_target_identity_crc16",
                                None,
                            )
                        ),
                    )
                return observation
            except (ClientVisibleStateError, CombatHudDetectionError) as error:
                last_reacquisition_error = error
                if self._on_capture_stall is not None:
                    self._on_capture_stall()
                if attempt + 1 >= VISIBLE_STATE_REACQUISITION_ATTEMPTS:
                    raise
                time.sleep(VISIBLE_STATE_REACQUISITION_INTERVAL_S)
            except (CaptureStreamError, WindowSelectionError) as error:
                # Window identity/foreground loss and an exhausted fresh-frame
                # budget are capture-source failures, not steering failures.
                # Release every leased control immediately and preserve the
                # last CRC-valid pose so the top-level runner can publish a
                # bounded forensic result instead of losing the trace in an
                # unhandled traceback.
                if self._on_capture_stall is not None:
                    self._on_capture_stall()
                raise CaptureObservationError(
                    error,
                    last_valid_pose=self._last_valid_observation,
                ) from error
        assert last_reacquisition_error is not None
        raise last_reacquisition_error

    def _next_fresh_observation(self) -> dict[str, object]:
        self.latest_afk_packet = None
        self.latest_location_labels = None
        for freshness_attempt in range(2):
            self._counter += 1
            packet = self._next_capture_packet()
            frame = bgra_view_from_packet(
                packet,
                maximum_frame_pixels=8_847_360,
                validator=self._capture_validator,
            )
            try:
                observation = self._detector.detect(
                    dict(packet.manifest),
                    frame,
                    observation_id=f"nav-pose:{self._counter}:{uuid4()}",
                )
                coordinate_valid = observation.get("tracking_state") == "VALID"
                if coordinate_valid and getattr(self, "_observe_location", False):
                    from location_hud_detector import detect_location_strip
                    try:
                        location_packet = detect_location_strip(
                            frame, self._detector._cached_markers,
                            observation["protocol"]["sequence"],
                        )
                        self.latest_location_labels = self._location_stream.observe(
                            location_packet, observation["timing"]["observed_monotonic_s"],
                        )
                    except (KeyError, ValueError, TypeError, IndexError):
                        # This optional display channel never gates navigation.
                        self.latest_location_labels = None
                if coordinate_valid and getattr(self, "_observe_afk", False):
                    from afk_hud_detector import detect_afk_strip
                    self.latest_afk_packet = detect_afk_strip(
                        frame, self._detector._cached_markers,
                    )
                player_state = observation.get("player_state")
                if coordinate_valid and isinstance(player_state, dict):
                    dead_or_ghost = player_state.get("dead_or_ghost")
                    player_ghost = player_state.get("ghost")
                    if type(dead_or_ghost) is bool and type(player_ghost) is bool:
                        self._last_player_alive = not dead_or_ghost
                        self._last_player_ghost = player_ghost
                if coordinate_valid:
                    combat = self._combat_detector.detect(
                        dict(packet.manifest),
                        frame,
                        observation_id=f"nav-combat:{self._counter}:{uuid4()}",
                    )
                    player = combat.get("player")
                    if (
                        combat.get("tracking_state") == "VALID"
                        and isinstance(player, dict)
                        and isinstance(player.get("alive"), bool)
                    ):
                        self._last_player_alive = bool(player["alive"])
                        self._last_player_ghost = None
                        combat_state = combat.get("combat")
                        target_state = combat.get("target")
                        self._latest_in_combat = (
                            bool(combat_state["in_combat"])
                            if isinstance(combat_state, dict)
                            and type(combat_state.get("in_combat")) is bool
                            else None
                        )
                        self._latest_combat_target_identity_crc16 = (
                            int(target_state["identity_crc16"])
                            if isinstance(target_state, dict)
                            and type(target_state.get("identity_crc16")) is int
                            else None
                        )
                        # Health capability is per-frame evidence. Clear the
                        # previous value before decoding this frame so a
                        # missing/invalid health marker can never inherit an
                        # older healthy value during combat.
                        self._latest_travel_capability = None
                        level = player.get("level")
                        health_pct = player.get("health_pct")
                        if (
                            type(level) is int
                            and isinstance(health_pct, (int, float))
                            and 1 <= level <= 100
                            and 5 <= float(health_pct) <= 100
                        ):
                            # Stealth/escape readiness is not present in the
                            # current visible HUD contract. Unknown capability
                            # is deliberately scored as unavailable.
                            self._latest_travel_capability = TravelCapability(
                                level=level,
                                health_fraction=float(health_pct) / 100.0,
                                stealth_ready=False,
                                escape_ready=False,
                            )
                    else:
                        self._latest_in_combat = None
                        self._latest_combat_target_identity_crc16 = None
                        self._latest_travel_capability = None
                client_state = classify_visible_client_state(
                    frame,
                    coordinate_hud_valid=coordinate_valid,
                    player_alive=self._last_player_alive,
                    player_ghost=self._last_player_ghost,
                )
                # Corpse navigation is deliberately ghost-only.  If the
                # character becomes alive before the corpse goal is reached,
                # stop this runner and let the supervisor resume the semantic
                # mission instead of treating an alive frame as authorization
                # to press the corpse-retrieval confirmation key.
                allowed_state = (
                    client_state.state is VisibleClientState.GHOST_IN_WORLD
                    if self._allow_ghost_navigation
                    else client_state.state is VisibleClientState.IN_WORLD
                )
                if not allowed_state:
                    raise ClientVisibleStateError(
                        client_state,
                        last_valid_pose=(
                            observation
                            if coordinate_valid
                            else self._last_valid_observation
                        ),
                    )
                observed_monotonic_s = float(
                    observation["timing"]["observed_monotonic_s"]
                )
                try:
                    camera_integrity = self._player_actor_detector.detect(
                        frame,
                        observed_at_s=observed_monotonic_s,
                    )
                except PlayerActorAnchorError as error:
                    # A detector deadline/profile error is evidence loss, not
                    # permission to continue. Preserve a contract-shaped
                    # UNKNOWN record so the armed gate releases motion and
                    # the terminal journal explains why. Keep the actual
                    # sampled dimensions: the old fallback of 1x1 made a
                    # detector timeout look like a tiny capture frame.
                    actor_sample_stride = int(
                        self._player_actor_detector.profile["sample_stride"]
                    )
                    sampled_height = max(
                        1, (int(frame.shape[0]) + actor_sample_stride - 1) // actor_sample_stride
                    )
                    sampled_width = max(
                        1, (int(frame.shape[1]) + actor_sample_stride - 1) // actor_sample_stride
                    )
                    camera_integrity = self._player_actor_detector.failure_record(
                        observed_at_s=observed_monotonic_s,
                        reason=(
                            f"actor_detector_error:{type(error).__name__}:{error}"
                        ),
                        sampled_width=sampled_width,
                        sampled_height=sampled_height,
                    )
                self._latest_camera_integrity = camera_integrity
                observation["camera_integrity"] = camera_integrity
                # The camera/actor evidence is part of the same validated
                # client-visible observation. It never grants authority.
                self._observation_validator.validate(observation)
                camera_decision = assess_camera_integrity(
                    camera_integrity,
                    require_visible_anchor=(
                        self._require_player_anchor
                        and self._camera_integrity_gate_armed
                    ),
                )
                if not camera_decision.allow_control:
                    camera_state = VisibleClientStateObservation(
                        state=VisibleClientState.UNKNOWN,
                        confidence=0.0,
                        evidence={
                            "coordinate_hud_crc_valid": coordinate_valid,
                            "player_actor_anchor_visible": False,
                            "camera_integrity_confidence": camera_decision.confidence,
                        },
                    )
                    raise ClientVisibleStateError(
                        camera_state,
                        last_valid_pose=observation,
                    )
                position = observation.get("position")
                # GetPlayerFacing() in the CRC HUD is both exact and already
                # available in this frame. Running full minimap segmentation
                # anyway added roughly 80-100 ms before the freshness gate and
                # made every otherwise valid pose stale. Image inference is a
                # true fallback, so do not even execute it when exact facing
                # exists.
                if isinstance(position, dict) and "facing_rad" in position:
                    self._latest_facing_source = EXACT_BODY_HEADING_SOURCE
                    self._latest_facing_confidence = 1.0
                else:
                    self._latest_facing_source = "UNAVAILABLE"
                    self._latest_facing_confidence = None
                if isinstance(position, dict) and "facing_rad" not in position:
                    minimap = self._minimap_detector.detect(
                        dict(packet.manifest),
                        frame,
                        observation_id=f"nav-heading:{self._counter}:{uuid4()}",
                    )
                    marker = minimap.get("player_marker")
                    if (
                        minimap.get("tracking_state") == "FOUND"
                        and _minimap_heading_is_fallback_only(position, marker)
                    ):
                        assert isinstance(marker, dict)
                        position["facing_rad"] = world_heading_from_marker(
                            MarkerCandidate(
                                center_x_px=float(marker["center_x_px"]),
                                center_y_px=float(marker["center_y_px"]),
                                orientation_deg_screen=float(
                                    marker["orientation_deg_screen"]
                                ),
                                pixel_count=int(marker["pixel_count"]),
                                confidence=float(marker["confidence"]),
                                detection_model=str(marker["detection_model"]),
                            ),
                            self._minimap_profile,
                        )
                        self._latest_facing_source = MINIMAP_BODY_HEADING_SOURCE
                        self._latest_facing_confidence = float(marker["confidence"])
                        self._observation_validator.validate(observation)
                # Nameplate scanning is useful dynamic awareness, but it is
                # not part of the pose needed to steer this frame. At 4K it can
                # consume the complete 180 ms actuator freshness window. Run
                # one read-only scan ahead on an owned frame copy and consume
                # only completed results; locomotion never waits for it.
                if (
                    self._dynamic_detection_future is not None
                    and self._dynamic_detection_future.done()
                ):
                    try:
                        self._latest_dynamic_observations = (
                            self._dynamic_detection_future.result()
                        )
                        self._latest_dynamic_detection_error = None
                    except VisibleEntityDetectorError as error:
                        self._latest_dynamic_observations = ()
                        self._latest_dynamic_detection_error = str(error)
                    finally:
                        self._dynamic_detection_future = None
                self._dynamic_detection_frame_counter += 1
                if (
                    self._dynamic_detection_future is None
                    and self._dynamic_detection_frame_counter
                    >= DYNAMIC_DETECTION_INTERVAL_FRAMES
                ):
                    self._dynamic_detection_frame_counter = 0
                    entity_frame = frame.copy()
                    observed_at_s = float(
                        observation["timing"]["observed_monotonic_s"]
                    )
                    self._dynamic_detection_future = (
                        self._dynamic_detection_executor.submit(
                            self._visible_entity_detector.detect,
                            entity_frame,
                            observed_at_s=observed_at_s,
                        )
                    )
                self._last_valid_observation = observation
            finally:
                del frame
                packet = None
            if observation.get("tracking_state") != "VALID":
                raise RuntimeError(
                    "continuous coordinate HUD pose is unavailable: "
                    + str(observation.get("reason"))
                )
            age_ms = (
                time.monotonic() - float(observation["timing"]["observed_monotonic_s"])
            ) * 1000.0
            if age_ms <= MAXIMUM_CONTROL_OBSERVATION_AGE_MS:
                return observation
            # The first full-scene marker acquisition may be deliberately
            # slower. No input has been sent yet; acquire one new frame using
            # the now-verified marker geometry instead of returning stale pose.
            if freshness_attempt == 1:
                raise RuntimeError(
                    f"continuous coordinate HUD pose remained stale at {age_ms:.1f} ms"
                )
        raise RuntimeError("continuous coordinate HUD did not return an observation")


def _write_json_atomic(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(
                record,
                stream,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            stream.flush()
            os.fsync(stream.fileno())
        for replace_attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if replace_attempt == 5:
                    raise
                # Windows readers can briefly hold the destination without
                # FILE_SHARE_DELETE.  Keep the publication atomic and retry
                # the same already-fsynced file instead of writing in place.
                time.sleep(0.010 * (replace_attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def _publish_movement_lab(
    path: Path,
    snapshot: MovementLabSnapshot,
    *,
    local_static_awareness: dict[str, object] | None = None,
    local_environment_awareness: dict[str, object] | None = None,
    local_environment_applicability: dict[str, object] | None = None,
    structure_access_awareness: dict[str, object] | None = None,
    dynamic_entity_awareness: dict[str, object] | None = None,
    dynamic_experience_summary: dict[str, object] | None = None,
    topographic_brain: dict[str, object] | None = None,
    location_labels: dict[str, object] | None = None,
) -> None:
    record = snapshot.to_record()
    record["location_labels"] = location_labels
    if local_static_awareness is not None:
        record["local_static_awareness"] = local_static_awareness
    if local_environment_awareness is not None:
        record["local_environment_awareness"] = local_environment_awareness
    if local_environment_applicability is not None:
        record["local_environment_applicability"] = local_environment_applicability
    if structure_access_awareness is not None:
        record["structure_access_awareness"] = structure_access_awareness
    if dynamic_entity_awareness is not None:
        record["dynamic_entity_awareness"] = dynamic_entity_awareness
    if dynamic_experience_summary is not None:
        record["dynamic_experience_summary"] = dynamic_experience_summary
    if topographic_brain is not None:
        record["topographic_brain"] = topographic_brain
    _write_json_atomic(path, record)


def _dynamic_entity_awareness_record(
    tracks: tuple[DynamicEntityTrack, ...],
    *,
    observed_at_s: float,
    adapter_error: str | None,
    visibility_ceiling_yards: float = 100.0,
) -> dict[str, object]:
    """Publish observable tracks without inventing world position or range."""

    if not isfinite(observed_at_s) or observed_at_s < 0:
        raise ValueError("dynamic awareness observation time is invalid")
    if (
        not isfinite(visibility_ceiling_yards)
        or not 1.0 <= visibility_ceiling_yards <= 500.0
    ):
        raise ValueError("dynamic awareness visibility ceiling is invalid")
    if adapter_error is not None and len(adapter_error) > 512:
        adapter_error = adapter_error[:512]
    return {
        "record_type": "dynamic_entity_awareness",
        "schema_version": "1.0",
        "observed_monotonic_s": observed_at_s,
        "observation_scope": "CURRENT_VIEWPORT_WITHIN_SERVER_VISIBILITY_SET",
        "visibility_ceiling_yards": visibility_ceiling_yards,
        "position_semantics": "SCREEN_SPACE_ONLY",
        "distance_semantics": "UNKNOWN_UNLESS_SELECTED_TARGET_RANGE_WITNESS",
        "track_count": len(tracks),
        "tracks": [
            {
                "track_id": item.track_id,
                "reaction": item.reaction,
                "first_observed_at_s": item.first_observed_at_s,
                "last_observed_at_s": item.last_observed_at_s,
                "expires_at_s": item.expires_at_s,
                "center_x_normalized": item.center_x_normalized,
                "center_y_normalized": item.center_y_normalized,
                "velocity_x_normalized_per_s": item.velocity_x_normalized_per_s,
                "velocity_y_normalized_per_s": item.velocity_y_normalized_per_s,
                "width_normalized": item.width_normalized,
                "height_normalized": item.height_normalized,
                "position_uncertainty_normalized": (
                    item.position_uncertainty_normalized
                ),
                "confidence": item.confidence,
                "observation_count": item.observation_count,
                "source_key": item.source_key,
                "world_position": None,
                "distance_yards": None,
            }
            for item in tracks
        ],
        "adapter_error": adapter_error,
        "execution_authority": False,
    }


def _local_static_awareness_record(corridor: NavCorridor) -> dict[str, object]:
    awareness = corridor.start_awareness
    if awareness is None:
        return {
            "available": False,
            "reason": "worker_did_not_supply_start_awareness",
            "execution_authority": False,
        }
    collision_clear_count = sum(
        item.clearance_yards >= awareness.probe_radius_yards * 0.95
        for item in awareness.radial_probes
    )
    record: dict[str, object] = {
        "available": True,
        "environment_class": awareness.environment_class,
        "physical_surfaces": sorted(awareness.physical_surfaces),
        "probe_radius_yards": awareness.probe_radius_yards,
        "probe_count": len(awareness.radial_probes),
        "collision_clear_count": collision_clear_count,
        "detour_confirmed_opening_count": len(awareness.candidate_opening_bearings_rad),
        "candidate_opening_bearings_rad": list(
            awareness.candidate_opening_bearings_rad
        ),
        "overhead_clear": awareness.overhead_clear,
        "topology_radius_yards": awareness.topology_radius_yards,
        "component_polygon_count": awareness.component_polygon_count,
        "component_truncated": awareness.component_truncated,
        "wall_segments_truncated": awareness.wall_segments_truncated,
        "surface_transition_portals_truncated": (
            awareness.surface_transition_portals_truncated
        ),
        "egress_inference_complete": awareness.egress_inference_complete,
        "egress_portals_truncated": awareness.egress_portals_truncated,
        "wall_segments": [
            {
                "left": [item.left.x, item.left.y, item.left.z],
                "right": [item.right.x, item.right.y, item.right.z],
                "distance_yards": item.distance_yards,
            }
            for item in awareness.wall_segments
        ],
        "surface_transition_portals": [
            {
                "left": [item.left.x, item.left.y, item.left.z],
                "right": [item.right.x, item.right.y, item.right.z],
                "width_yards": item.width_yards,
                "distance_yards": item.distance_yards,
                "from_surfaces": sorted(item.from_surfaces),
                "to_surfaces": sorted(item.to_surfaces),
            }
            for item in awareness.surface_transition_portals
        ],
        "egress_portals": [
            {
                "left": [item.left.x, item.left.y, item.left.z],
                "right": [item.right.x, item.right.y, item.right.z],
                "width_yards": item.width_yards,
                "distance_yards": item.distance_yards,
                "route_distance_yards": item.route_distance_yards,
                "from_overhead_clear": item.from_overhead_clear,
                "to_overhead_clear": item.to_overhead_clear,
                "from_surfaces": sorted(item.from_surfaces),
                "to_surfaces": sorted(item.to_surfaces),
                "route_verified": True,
            }
            for item in awareness.egress_portals
        ],
        "radial_probes": [
            {
                "bearing_rad": item.bearing_rad,
                "clearance_yards": item.clearance_yards,
                "navmesh_reachable": item.navmesh_reachable,
            }
            for item in awareness.radial_probes
        ],
        "source": "client_asset_collision_and_detour",
        "execution_authority": False,
    }
    conditional = infer_conditional_traversal_frontier(corridor)
    if conditional is not None:
        record["conditional_traversal_frontier"] = {
            "kind": conditional.kind,
            "frontier": [
                conditional.frontier.x,
                conditional.frontier.y,
                conditional.frontier.z,
            ],
            "requested_stop": [
                conditional.requested_stop.x,
                conditional.requested_stop.y,
                conditional.requested_stop.z,
            ],
            "remaining_distance_yards": conditional.remaining_distance_yards,
            "requested_vertical_delta_yards": (
                conditional.requested_vertical_delta_yards
            ),
            "boundary_segments": [
                {
                    "left": [item.left.x, item.left.y, item.left.z],
                    "right": [item.right.x, item.right.y, item.right.z],
                    "distance_yards": item.distance_yards,
                }
                for item in conditional.boundary_segments
            ],
            "requires_live_visible_confirmation": True,
            "source": conditional.source,
            "execution_authority": False,
        }
    return record


def _wrap_angle(angle: float) -> float:
    while angle > 3.141592653589793:
        angle -= 6.283185307179586
    while angle < -3.141592653589793:
        angle += 6.283185307179586
    return angle


def _update_pivot_stall_clock(
    *,
    elapsed_s: float,
    anchor_error_rad: float | None,
    dt_s: float,
    controller_state: str,
    waypoint_error_rad: float | None,
) -> tuple[float, float | None]:
    """Count only a pivot that is not measurably converging on its bearing."""
    if any(not isfinite(value) or value < 0 for value in (elapsed_s, dt_s)):
        raise ValueError("pivot stall timing is invalid")
    if controller_state != "PIVOT":
        return 0.0, None
    if waypoint_error_rad is None or not isfinite(waypoint_error_rad):
        return elapsed_s + dt_s, anchor_error_rad
    current_error = abs(waypoint_error_rad)
    if (
        anchor_error_rad is None
        or current_error <= anchor_error_rad - PIVOT_HEADING_PROGRESS_RAD
    ):
        return 0.0, current_error
    return elapsed_s + dt_s, anchor_error_rad


def _replan_is_corridor_recenter_only(
    *,
    intent_reason: str,
    no_progress_s: float,
    collision_slide_s: float,
) -> bool:
    """Keep geometric divergence separate from observed collision evidence."""
    if any(
        not isfinite(value) or value < 0 for value in (no_progress_s, collision_slide_s)
    ):
        raise ValueError("replan evidence timing is invalid")
    if intent_reason == "confined_forward_stall_realign":
        # This deliberately fires before the collision-learning threshold.
        # Re-acquire the corridor and heading, but do not turn a transient
        # wall press into permanent standalone world knowledge.
        return no_progress_s < STUCK_PROGRESS_EVIDENCE_S
    return (
        intent_reason
        in {
            "persistent_corridor_divergence",
            "trajectory_loop_detected",
        }
        and no_progress_s < STUCK_PROGRESS_EVIDENCE_S
        and collision_slide_s < COLLISION_SLIDE_EVIDENCE_S
    )


def _corridor_recenter_no_progress_evidence(
    *,
    intent_reason: str,
    no_progress_s: float,
    accumulated_confined_stall_s: float,
) -> float:
    """Carry physical W-without-motion evidence across geometric realignments."""
    if any(
        not isfinite(value) or value < 0
        for value in (no_progress_s, accumulated_confined_stall_s)
    ):
        raise ValueError("corridor recenter progress evidence is invalid")
    if intent_reason == "confined_forward_stall_realign":
        return accumulated_confined_stall_s + no_progress_s
    return no_progress_s


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    return value


def _load_learned_obstacle_memory(path: Path) -> LearnedObstacleMemory:
    if not path.exists():
        return LearnedObstacleMemory.empty(client_build=CLIENT_BUILD)
    try:
        return LearnedObstacleMemory.from_record(
            _read_json(path),
            expected_client_build=CLIENT_BUILD,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"invalid learned obstacle memory: {error}") from error


def _load_recovery_strategy_memory(path: Path) -> RecoveryStrategyMemory:
    if not path.exists():
        return RecoveryStrategyMemory.empty(client_build=CLIENT_BUILD)
    try:
        return RecoveryStrategyMemory.from_record(
            _read_json(path),
            expected_client_build=CLIENT_BUILD,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"invalid recovery strategy memory: {error}") from error


def _bounded_blocker_union(
    *groups: tuple[tuple[float, float, float, float], ...],
    origin_x: float,
    origin_y: float,
    limit: int = 8,
) -> tuple[tuple[float, float, float, float], ...]:
    if not 1 <= limit <= 8:
        raise ValueError("observed blocker limit is invalid")
    merged: list[tuple[float, float, float, float]] = []
    for group in groups:
        for blocker in group:
            if any(
                hypot(blocker[0] - prior[0], blocker[1] - prior[1]) < 1.0
                and abs(blocker[2] - prior[2]) < 2.5
                for prior in merged
            ):
                continue
            merged.append(blocker)
    merged.sort(
        key=lambda blocker: (
            hypot(blocker[0] - origin_x, blocker[1] - origin_y),
            blocker,
        )
    )
    return tuple(merged[:limit])


def _suppress_learned_blockers_containing_pose(
    blockers: tuple[tuple[float, float, float, float], ...],
    *,
    start_x: float,
    start_y: float,
    start_z: float,
    maximum_vertical_delta: float = 2.5,
) -> tuple[
    tuple[tuple[float, float, float, float], ...],
    tuple[tuple[float, float, float, float], ...],
]:
    """Keep stale learned discs from sealing the polygon the actor occupies.

    A learned disc is useful only as a *nearby* collision prior.  A previous
    run can have recorded that disc while the actor was sliding or standing
    inside the same client polygon.  Feeding it back at the next start makes
    Detour report a false partial corridor before the first control frame.
    Keep the memory record intact, but do not apply a disc whose own footprint
    contains the fresh client-visible pose on the same vertical layer.
    """

    if not all(isfinite(value) for value in (start_x, start_y, start_z)):
        raise ValueError("learned blocker pose is not finite")
    if not isfinite(maximum_vertical_delta) or maximum_vertical_delta < 0.0:
        raise ValueError("learned blocker vertical bound is invalid")
    retained: list[tuple[float, float, float, float]] = []
    suppressed: list[tuple[float, float, float, float]] = []
    for blocker in blockers:
        if len(blocker) != 4 or not all(isfinite(value) for value in blocker):
            raise ValueError("learned blocker is malformed")
        x, y, z, radius = blocker
        if radius < 0.0:
            raise ValueError("learned blocker radius is invalid")
        if (
            abs(z - start_z) <= maximum_vertical_delta
            and hypot(x - start_x, y - start_y) <= radius
        ):
            suppressed.append(blocker)
        else:
            retained.append(blocker)
    return tuple(retained), tuple(suppressed)


def _load_semantic_destination(
    path: Path,
    *,
    destination_id: str,
    expected_zone_index: int,
    expected_map_name: str = "Azeroth",
    expected_map_id: int = 0,
    transform_catalog: Path = DEFAULT_ZONE_TRANSFORM_CATALOG,
) -> tuple[float, float, float, str]:
    catalog = _read_json(path)
    atlas_calibration = (
        catalog.get("atlas_calibration")
        if isinstance(catalog, dict)
        else None
    )
    expected_internal_name = None
    if isinstance(atlas_calibration, str) and atlas_calibration.startswith(
        "WorldMapArea.dbc:"
    ):
        expected_internal_name = atlas_calibration.split(":", 1)[1]
    try:
        zone_transform = _load_zone_transform(
            transform_catalog,
            map_id=expected_map_id,
            zone_index=expected_zone_index,
            expected_internal_name=expected_internal_name,
        )
    except (OSError, ValueError, TypeError, WorldMapZoneTransformCatalogError) as error:
        raise RuntimeError(
            "semantic destination catalog has no reviewed client atlas transform"
        ) from error
    if (
        catalog.get("record_type") != "semantic_location_catalog"
        or catalog.get("schema_version") != "1.0"
        or catalog.get("map_name") != expected_map_name
        or catalog.get("zone_index") != expected_zone_index
        or catalog.get("coordinate_system") != "tbc243_client_world_xy"
        or catalog.get("atlas_calibration")
        != f"WorldMapArea.dbc:{zone_transform.internal_name}"
    ):
        raise RuntimeError(
            "semantic destination catalog is not bound to the exact client atlas"
        )
    locations = catalog.get("locations")
    if not isinstance(locations, list):
        raise RuntimeError("semantic destination catalog has no locations")
    matches = [
        item
        for item in locations
        if isinstance(item, dict) and item.get("id") == destination_id
    ]
    if len(matches) != 1:
        raise RuntimeError("semantic destination id is not unique in the client atlas")
    location = matches[0]
    world = location.get("world")
    radius = location.get("arrival_radius_yards")
    if (
        not isinstance(world, list)
        or len(world) != 2
        or not all(isinstance(value, (int, float)) for value in world)
        or not isinstance(radius, (int, float))
        or not 2.0 <= float(radius) <= 100.0
    ):
        raise RuntimeError("semantic destination geometry is malformed")
    return (
        float(world[0]),
        float(world[1]),
        float(radius),
        str(location.get("name", destination_id)),
    )


def _load_zone_transform(
    path: Path,
    *,
    map_id: int,
    zone_index: int,
    expected_internal_name: str | None = None,
) -> WorldMapZoneTransform:
    """Resolve one immutable client WorldMapArea transform by map/area ID.

    The legacy helper only carried the two Tirisfal transforms used by the
    first LAB slice.  RouteTeacher destinations can legitimately bind to
    Kalimdor or Outland, so the runtime must resolve their 2D conversion from
    the hash-pinned client catalog instead of silently reusing Tirisfal.
    The catalog has no height or execution authority; navmesh validation still
    remains the source of traversability.
    """

    if type(map_id) is not int or map_id < 0:
        raise ValueError("map_id is invalid")
    if type(zone_index) is not int or zone_index < 0:
        raise ValueError("zone_index is invalid")
    catalog = load_world_map_zone_transform_catalog(
        path,
        schema_path=ZONE_TRANSFORM_CATALOG_SCHEMA,
    )
    try:
        return catalog.resolve(map_id=map_id, area_id=zone_index)
    except WorldMapZoneTransformCatalogError as direct_error:
        # WorldMapArea.dbc area IDs and the legacy coordinate-HUD zone index
        # are not identical for every Azeroth zone (Tirisfal is 25 vs 85,
        # Undercity 26 vs 1497). Prefer an explicit catalog calibration name
        # when supplied, then retain the two reviewed legacy aliases.
        if expected_internal_name:
            matches = tuple(
                zone
                for zone in catalog.zones
                if zone.map_id == map_id
                and zone.internal_name == expected_internal_name
            )
            if len(matches) == 1:
                return matches[0]
        try:
            legacy = tbc243_zone_transform(2, zone_index)
        except ValueError:
            raise direct_error
        matches = tuple(
            zone
            for zone in catalog.zones
            if zone.map_id == map_id and zone.internal_name == legacy.name
        )
        if len(matches) != 1:
            raise direct_error
        return matches[0]


def _load_operator_path_journey(
    path: Path,
    *,
    expected_map_name: str = "Azeroth",
) -> OperatorAuthoredPath:
    try:
        journey = OperatorAuthoredPath.from_record(_read_json(path))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"operator path is invalid: {error}") from error
    if journey.map_name != expected_map_name:
        raise RuntimeError("operator path is bound to another client map")
    if not journey.waypoints:
        raise RuntimeError("operator path has no waypoints")
    return journey


def _operator_goal_queue(
    journey: OperatorAuthoredPath,
    *,
    start_x: float,
    start_y: float,
) -> tuple[int, tuple[RoadWorldPoint, ...]]:
    start_index = journey.resume_index_nearest_to(x=start_x, y=start_y)
    return start_index, tuple(
        RoadWorldPoint(point.x, point.y) for point in journey.waypoints[start_index:]
    )


def _semantic_goal_queue(
    *,
    planner: ClientRoadSemanticPlanner,
    start_x: float,
    start_y: float,
    destination_x: float,
    destination_y: float,
    route: SemanticRoadRoute | None = None,
) -> tuple[SemanticRoadRoute, tuple[RoadWorldPoint, ...]]:
    if route is None:
        route = planner.plan(
            start_x=start_x,
            start_y=start_y,
            destination_x=destination_x,
            destination_y=destination_y,
        )
    # Texture-road cells are a global prior, not executable micro-waypoints.
    # Coalesce straight raster runs, but never replace a visible road bend with
    # one long Detour chord through the inside grass.  Every selected horizon
    # is still projected and validated by the local 3D navmesh.
    goals: list[RoadWorldPoint] = []
    anchor = RoadWorldPoint(start_x, start_y)
    pending: list[RoadWorldPoint] = []
    for candidate in route.waypoints:
        pending.append(candidate)
        if len(pending) >= 2:
            maximum_chord_deviation = max(
                _point_segment_distance_2d(point, anchor, candidate)
                for point in pending[:-1]
            )
            corner = pending[-2]
            incoming_x = corner.x - anchor.x
            incoming_y = corner.y - anchor.y
            outgoing_x = candidate.x - corner.x
            outgoing_y = candidate.y - corner.y
            turn_rad = abs(
                atan2(
                    incoming_x * outgoing_y - incoming_y * outgoing_x,
                    incoming_x * outgoing_x + incoming_y * outgoing_y,
                )
            )
            corner_spacing = hypot(
                corner.x - anchor.x,
                corner.y - anchor.y,
            )
            if (
                turn_rad >= SEMANTIC_LOCAL_GOAL_SHARP_TURN_RAD
                and corner_spacing >= SEMANTIC_LOCAL_GOAL_MIN_CORNER_SPACING_WORLD
            ) or (
                maximum_chord_deviation > SEMANTIC_LOCAL_GOAL_MAX_CHORD_DEVIATION_WORLD
                and corner_spacing >= SEMANTIC_LOCAL_GOAL_MIN_GENTLE_BEND_SPACING_WORLD
            ):
                goals.append(corner)
                anchor = corner
                pending = [candidate]
                continue
        if (
            hypot(candidate.x - anchor.x, candidate.y - anchor.y)
            < SEMANTIC_LOCAL_GOAL_SPACING_WORLD
        ):
            continue
        goals.append(candidate)
        anchor = candidate
        pending = []
    if (
        not goals
        or hypot(
            goals[-1].x - route.road_exit.x,
            goals[-1].y - route.road_exit.y,
        )
        > 0.05
    ):
        goals.append(route.road_exit)
    destination = RoadWorldPoint(destination_x, destination_y)
    if hypot(goals[-1].x - destination.x, goals[-1].y - destination.y) > 0.05:
        goals.append(destination)
    if not goals:
        goals.append(destination)
    return route, tuple(goals)


def _point_segment_distance_2d(
    point: RoadWorldPoint,
    start: RoadWorldPoint,
    stop: RoadWorldPoint,
) -> float:
    dx, dy = stop.x - start.x, stop.y - start.y
    length_squared = dx * dx + dy * dy
    if length_squared <= 1.0e-9:
        return hypot(point.x - start.x, point.y - start.y)
    fraction = max(
        0.0,
        min(
            1.0,
            ((point.x - start.x) * dx + (point.y - start.y) * dy) / length_squared,
        ),
    )
    projected_x = start.x + dx * fraction
    projected_y = start.y + dy * fraction
    return hypot(point.x - projected_x, point.y - projected_y)


def _segment_aabb_distance_2d(
    start: RoadWorldPoint,
    stop: RoadWorldPoint,
    *,
    minimum_x: float,
    minimum_y: float,
    maximum_x: float,
    maximum_y: float,
) -> float:
    """Return the exact 2D distance from a segment to an axis-aligned box."""

    if minimum_x > maximum_x or minimum_y > maximum_y:
        raise ValueError("axis-aligned bounds are inverted")
    dx = stop.x - start.x
    dy = stop.y - start.y
    t_min, t_max = 0.0, 1.0
    for origin, direction, lower, upper in (
        (start.x, dx, minimum_x, maximum_x),
        (start.y, dy, minimum_y, maximum_y),
    ):
        if abs(direction) <= 1.0e-12:
            if origin < lower or origin > upper:
                break
            continue
        first = (lower - origin) / direction
        second = (upper - origin) / direction
        if first > second:
            first, second = second, first
        t_min = max(t_min, first)
        t_max = min(t_max, second)
        if t_min > t_max:
            break
    else:
        return 0.0

    def point_box_distance(point: RoadWorldPoint) -> float:
        return hypot(
            max(minimum_x - point.x, 0.0, point.x - maximum_x),
            max(minimum_y - point.y, 0.0, point.y - maximum_y),
        )

    corners = (
        RoadWorldPoint(minimum_x, minimum_y),
        RoadWorldPoint(minimum_x, maximum_y),
        RoadWorldPoint(maximum_x, minimum_y),
        RoadWorldPoint(maximum_x, maximum_y),
    )
    return min(
        point_box_distance(start),
        point_box_distance(stop),
        *(_point_segment_distance_2d(corner, start, stop) for corner in corners),
    )


def _route_static_structure_blockers(
    *,
    structures,
    start: NavPoint,
    goals: list[RoadWorldPoint],
    maximum_goals: int = 8,
    maximum_blockers: int = 8,
) -> tuple[tuple[float, float, float, float], ...]:
    """Derive bounded, map-evidence obstacle discs ahead of the actor.

    Client map structures (posts, lamps, carts and building enclosures) can
    occupy a valid Detour polygon without being represented as a route
    boundary. Query only the next semantic horizon, keep candidates whose
    immutable bounds overlap that horizon, and let the client navmesh prove
    the resulting corridor. This is not a waypoint or asset-name rule; it is
    local static WorldPack evidence and remains capped to avoid route-wide
    overfitting.
    """

    if structures is None or not goals or not 1 <= maximum_goals <= 16:
        return ()
    if not 1 <= maximum_blockers <= 16:
        raise ValueError("static structure blocker bound is invalid")
    points = [start, *(
        NavPoint(goal.x, goal.y, start.z)
        for goal in goals[:maximum_goals]
    )]
    # A WMO can be a valid starting surface (for example the Crypt interior)
    # and must not be fed back as a circular blocker while its verified egress
    # plan is active.  Other enclosures on the upcoming horizon still need to
    # participate: a coarse nav polygon can otherwise steer the actor through
    # a building corner that the client collision rejects.
    start_inside_wmo_ids = {
        hit.structure.structure_id
        for hit in structures.nearby(
            x=start.x,
            y=start.y,
            z=start.z,
            radius_yards=0.5,
            kinds=("WMO",),
        )
        if hit.contains_3d
    }
    candidates: dict[str, tuple[float, float, float, float]] = {}
    distances: dict[str, float] = {}
    for left, right in zip(points, points[1:]):
        segment_start = RoadWorldPoint(left.x, left.y)
        segment_stop = RoadWorldPoint(right.x, right.y)
        segment_length = left.distance_2d(right)
        probes = (left, right)
        if segment_length > 2.0:
            probes += (
                NavPoint(
                    (left.x + right.x) * 0.5,
                    (left.y + right.y) * 0.5,
                    start.z,
                ),
            )
        for probe in probes:
            for hit in structures.nearby(
                x=probe.x,
                y=probe.y,
                z=probe.z,
                radius_yards=18.0,
                # Include enclosures encountered on the horizon.  A WMO that
                # contains the route start is handled by the dedicated
                # structure-egress/topology path and is excluded below.
                kinds=("DOODAD", "WMO"),
            ):
                item = hit.structure
                if item.kind == "WMO" and item.structure_id in start_inside_wmo_ids:
                    continue
                if hit.vertical_distance_yards is not None and hit.vertical_distance_yards > 12.0:
                    continue
                bounds_distance = _segment_aabb_distance_2d(
                    segment_start,
                    segment_stop,
                    minimum_x=float(item.bounds.minimum.x),
                    minimum_y=float(item.bounds.minimum.y),
                    maximum_x=float(item.bounds.maximum.x),
                    maximum_y=float(item.bounds.maximum.y),
                )
                if bounds_distance > DEFAULT_ACTOR_CLEARANCE_WORLD + 1.0:
                    continue
                # The nav probe accepts bounded discs.  Use the source
                # geometry's footprint only after the AABB has intersected the
                # route.  A circumscribed radius is too broad for a long,
                # shallow outpost: it can cover later road samples that are
                # already outside the prop.  For broad props, bound the disc
                    # by the narrowest horizontal half-extent while retaining
                    # the source radius for ordinary objects.  The nav worker
                    # already applies actor clearance; adding it here would
                    # turn the footprint into a second, oversized shell.
                source_radius = float(item.horizontal_radius_yards)
                radius = min(max(source_radius, 1.25), 30.0)
                if item.kind in {"DOODAD", "WMO"}:
                    half_width = abs(
                        float(item.bounds.maximum.x) - float(item.bounds.minimum.x)
                    ) * 0.5
                    half_height = abs(
                        float(item.bounds.maximum.y) - float(item.bounds.minimum.y)
                    ) * 0.5
                    # Keep a small geometric margin below the exact half
                    # extent. The worker adds actor clearance and treats a
                    # disc touching the boundary as blocked; using a WMO's
                    # circumscribed radius can otherwise seal a road which is
                    # visibly outside the measured building bounds.
                    narrow_radius = min(half_width, half_height) * 0.90
                    if (
                        isfinite(narrow_radius)
                        and narrow_radius > 0.0
                        and source_radius > narrow_radius * 1.35
                    ):
                        radius = min(radius, max(narrow_radius, 1.25))
                candidates[item.structure_id] = (
                    float(item.center.x),
                    float(item.center.y),
                    float(item.center.z),
                    radius,
                )
                distances[item.structure_id] = min(
                    distances.get(item.structure_id, float("inf")),
                    hypot(item.center.x - start.x, item.center.y - start.y),
                )
    return tuple(
        candidates[key]
        for key in sorted(
            candidates,
            key=lambda item: (distances[item], item),
        )[:maximum_blockers]
    )


def _semantic_goal_overlaps_static_structure(
    *,
    structures,
    goal: RoadWorldPoint,
    z: float,
    actor_clearance_world: float = DEFAULT_ACTOR_CLEARANCE_WORLD,
) -> bool:
    """Reject an atlas goal that would place the actor inside a static prop.

    WorldPack bounds are evidence about occupancy, while the client navmesh
    remains authoritative for the route between points.  This small predicate
    prevents a semantic sample inside a large doodad from being accepted just
    because a coarse navmesh polygon is technically reachable.  It is used
    only for bounded forward-bypass candidates; it never creates a waypoint.
    """

    if (
        structures is None
        or not isfinite(z)
        or not isfinite(actor_clearance_world)
        or actor_clearance_world < 0.0
        or actor_clearance_world > 10.0
    ):
        return False
    for hit in structures.nearby(
        x=goal.x,
        y=goal.y,
        z=z,
        radius_yards=actor_clearance_world,
        kinds=("DOODAD",),
    ):
        if hit.vertical_distance_yards is not None and hit.vertical_distance_yards > 12.0:
            continue
        if hit.contains_horizontal or hit.horizontal_distance_yards <= actor_clearance_world:
            return True
    return False


def _merge_static_structure_horizon_blockers(
    *,
    structures,
    observed_blockers: tuple[tuple[float, float, float, float], ...],
    start: NavPoint,
    goals: list[RoadWorldPoint] | tuple[RoadWorldPoint, ...],
    maximum_goals: int = 1,
) -> tuple[
    tuple[tuple[float, float, float, float], ...],
    tuple[tuple[float, float, float, float], ...],
]:
    """Add immutable map obstacles on the next semantic horizon.

    Static structure awareness must roll with the semantic queue.  Checking
    only the initial eight goals misses props encountered later (for example a
    cart at the end of the Deathknell road), while querying the whole route
    would overfit the mission.  Keep this bounded to the immediate handoff.
    """

    candidates = _route_static_structure_blockers(
        structures=structures,
        start=start,
        goals=list(goals),
        maximum_goals=maximum_goals,
    )
    if not candidates:
        return observed_blockers, ()
    merged = _bounded_blocker_union(
        observed_blockers,
        candidates,
        origin_x=start.x,
        origin_y=start.y,
    )
    added = tuple(
        blocker
        for blocker in candidates
        if not any(
            hypot(blocker[0] - prior[0], blocker[1] - prior[1]) < 1.0
            and abs(blocker[2] - prior[2]) < 2.5
            for prior in observed_blockers
        )
    )
    return merged, added


def _suppress_proven_wmo_horizon_blockers(
    *,
    horizon_blockers: tuple[tuple[float, float, float, float], ...],
    added_blockers: tuple[tuple[float, float, float, float], ...],
    proven_for_goal: set[tuple[tuple[float, float, float, float], int]],
    next_waypoint_index: int,
) -> tuple[
    tuple[tuple[float, float, float, float], ...],
    tuple[tuple[float, float, float, float], ...],
]:
    """Do not re-submit the same WMO baseline for one semantic handoff.

    A completed baseline pass is scoped to the local semantic goal.  The
    structure merge can discover that same WMO again on every control frame;
    suppressing it here prevents an unbounded evidence/replan churn while
    still allowing a fresh check when the next semantic goal changes.
    """

    accepted = {
        candidate
        for candidate in added_blockers
        if (candidate, next_waypoint_index) in proven_for_goal
    }
    if not accepted:
        return horizon_blockers, added_blockers
    filtered_horizon = tuple(
        blocker for blocker in horizon_blockers if blocker not in accepted
    )
    filtered_added = tuple(
        blocker for blocker in added_blockers if blocker not in accepted
    )
    return filtered_horizon, filtered_added


def _inject_static_structure_clearance_priors(
    *,
    structures,
    route_start: RoadWorldPoint,
    start_z: float,
    goals: tuple[RoadWorldPoint, ...],
    query: ClientAssetNavmeshQuery,
    map_name: str,
    maximum_blockers: int = 4,
) -> tuple[tuple[RoadWorldPoint, ...], tuple[dict[str, object], ...]]:
    """Insert navmesh-proven local anchors around an occupied road sample.

    The semantic atlas remains the source of the mission route.  When a
    WorldPack structure makes the next semantic leg partial, derive a bounded
    sidestep from that structure's measured center/radius and require complete
    client-navmesh corridors for the sidestep, pass and rejoin legs.  This is
    local geometry evidence, not a destination-specific waypoint.
    """

    if structures is None or not goals or not map_name.strip():
        return goals, ()
    blockers = _route_static_structure_blockers(
        structures=structures,
        start=NavPoint(route_start.x, route_start.y, start_z),
        goals=list(goals),
        maximum_goals=min(16, len(goals)),
        maximum_blockers=maximum_blockers,
    )
    if not blockers:
        return goals, ()
    augmented = list(goals)
    actions: list[dict[str, object]] = []
    for blocker in blockers:
        bx, by, bz, radius = blocker
        obstacle = RoadWorldPoint(bx, by)
        polyline = (route_start, *augmented)
        nearest: tuple[float, int, float] | None = None
        for index, (left, right) in enumerate(zip(polyline, polyline[1:])):
            dx, dy = right.x - left.x, right.y - left.y
            length_squared = dx * dx + dy * dy
            if length_squared <= 1.0e-9:
                continue
            fraction = max(
                0.0,
                min(
                    1.0,
                    ((bx - left.x) * dx + (by - left.y) * dy)
                    / length_squared,
                ),
            )
            candidate = (
                _point_segment_distance_2d(obstacle, left, right),
                index,
                fraction,
            )
            if nearest is None or candidate < nearest:
                nearest = candidate
        if nearest is None:
            continue
        distance, segment_index, fraction = nearest
        route_overlap = radius + DEFAULT_ACTOR_CLEARANCE_WORLD + 0.25
        if distance > route_overlap or not 0.05 <= fraction <= 0.95:
            continue
        segment_start, segment_stop = polyline[segment_index], polyline[segment_index + 1]
        dx, dy = segment_stop.x - segment_start.x, segment_stop.y - segment_start.y
        length = hypot(dx, dy)
        if length <= 1.0e-6:
            continue
        forward_x, forward_y = dx / length, dy / length
        lateral_x, lateral_y = -forward_y, forward_x
        clearance = max(2.25, radius + 0.75)
        valid: list[tuple[float, NavPoint, NavPoint]] = []
        for sign in (-1.0, 1.0):
            side = NavPoint(
                bx - forward_x * clearance + lateral_x * clearance * sign,
                by - forward_y * clearance + lateral_y * clearance * sign,
                bz,
            )
            passed = NavPoint(
                bx + forward_x * clearance + lateral_x * clearance * sign,
                by + forward_y * clearance + lateral_y * clearance * sign,
                bz,
            )
            try:
                side_corridor = query.find_corridor(
                    map_name=map_name,
                    start=NavPoint(route_start.x, route_start.y, bz),
                    stop_x=side.x,
                    stop_y=side.y,
                    stop_z=side.z,
                )
                if not _local_clearance_leg_is_valid(
                    side_corridor,
                    requested_start=NavPoint(route_start.x, route_start.y, bz),
                    requested_stop=side,
                    maximum_detour_extra_world=max(
                        1.0, min(8.0, radius + 0.25)
                    ),
                ):
                    continue
                resolved_side = side_corridor.stop
                pass_corridor = query.find_corridor(
                    map_name=map_name,
                    start=resolved_side,
                    stop_x=passed.x,
                    stop_y=passed.y,
                    stop_z=passed.z,
                )
                if not _local_clearance_leg_is_valid(
                    pass_corridor,
                    requested_start=resolved_side,
                    requested_stop=passed,
                    maximum_detour_extra_world=max(
                        1.0, min(8.0, radius + 0.25)
                    ),
                ):
                    continue
                rejoin = query.find_corridor(
                    map_name=map_name,
                    start=pass_corridor.stop,
                    stop_x=segment_stop.x,
                    stop_y=segment_stop.y,
                    stop_z=pass_corridor.stop.z,
                )
            except RuntimeError:
                continue
            if not rejoin.complete or abs(rejoin.start.z - pass_corridor.stop.z) > 2.5:
                continue
            route_length = sum(
                sum(
                    left.distance_2d(right)
                    for left, right in zip(
                        corridor.guidance_points(), corridor.guidance_points()[1:]
                    )
                )
                for corridor in (side_corridor, pass_corridor, rejoin)
            )
            valid.append((route_length, side, passed))
        if not valid:
            actions.append(
                {
                    "kind": "STATIC_STRUCTURE_CLEARANCE_UNRESOLVED",
                    "blocker_world": [bx, by, bz, radius],
                    "reason": "no_navmesh_validated_local_clearance",
                    "execution_authority": False,
                }
            )
            continue
        _, side, passed = min(valid, key=lambda item: (item[0], item[1].x, item[1].y))
        insertion = segment_index
        augmented[insertion:insertion] = [
            RoadWorldPoint(side.x, side.y),
            RoadWorldPoint(passed.x, passed.y),
        ]
        actions.append(
            {
                "kind": "STATIC_STRUCTURE_CLEARANCE_APPLIED",
                "blocker_world": [bx, by, bz, radius],
                "side_anchor_world": [side.x, side.y, side.z],
                "pass_anchor_world": [passed.x, passed.y, passed.z],
                "source": "worldpack_structure_bounds_plus_client_navmesh",
                "execution_authority": False,
            }
        )
        break
    return tuple(augmented), tuple(actions)


def _filter_traversable_wmo_horizon_blockers(
    *,
    structures,
    horizon_blockers: tuple[tuple[float, float, float, float], ...],
    added_blockers: tuple[tuple[float, float, float, float], ...],
    query_factory: Callable[[tuple[tuple[float, float, float, float], ...]], object],
    map_name: str,
    start: NavPoint,
    goal: RoadWorldPoint,
    current_waypoint_index: int,
    next_waypoint_index: int,
    local_goal_radius: float,
) -> tuple[
    tuple[tuple[float, float, float, float], ...],
    tuple[tuple[float, float, float, float], ...],
    tuple[dict[str, object], ...],
]:
    """Keep a WMO blocker only when it is needed by the local navmesh.

    A covered bridge is static WMO geometry but also a valid walkable surface.
    A baseline corridor without the newly added WMO exclusion is authoritative
    evidence that the actor may remain on that surface.  The check is bounded
    to the next semantic leg and never weakens pre-existing obstacle evidence.
    """

    retained = list(horizon_blockers)
    retained_added: list[tuple[float, float, float, float]] = []
    actions: list[dict[str, object]] = []
    for candidate in added_blockers:
        hits = structures.nearby(
            x=candidate[0],
            y=candidate[1],
            z=candidate[2],
            radius_yards=0.5,
            kinds=("WMO",),
        )
        if not hits:
            retained_added.append(candidate)
            continue
        baseline_blockers = tuple(item for item in retained if item != candidate)
        baseline_query = query_factory(baseline_blockers)
        try:
            baseline_corridor = baseline_query.find_corridor(
                map_name=map_name,
                start=start,
                stop_x=goal.x,
                stop_y=goal.y,
            )
        except RuntimeError:
            baseline_corridor = None
        if (
            baseline_corridor is not None
            and _corridor_reaches_local_goal(
                baseline_corridor,
                goal_x=goal.x,
                goal_y=goal.y,
                radius_world=local_goal_radius,
            )
        ):
            retained = list(baseline_blockers)
            actions.append(
                {
                    "kind": "SEMANTIC_HORIZON_WMO_BASELINE_PASS",
                    "blocker_world": list(candidate),
                    "current_waypoint_index": current_waypoint_index,
                    "next_waypoint_index": next_waypoint_index,
                    "reason": "complete_client_navmesh_leg_without_new_wmo_exclusion",
                    "execution_authority": False,
                }
            )
        else:
            retained_added.append(candidate)
    return tuple(retained), tuple(retained_added), tuple(actions)


def _semantic_corridor_refinement(
    *,
    route: SemanticRoadRoute,
    corridor: NavCorridor,
    start_x: float,
    start_y: float,
    target_x: float,
    target_y: float,
    minimum_route_index: int = 0,
) -> tuple[int, RoadWorldPoint, float, float] | None:
    """Return the next fine A* point when a long local chord wanders.

    The navmesh is authoritative for what is physically walkable, while the
    semantic A* polyline is authoritative for the selected travel corridor.
    A long local goal may use the whole surface width, but it must not turn a
    road bend into a forest excursion or route around an unrelated prop and
    then return to the same road.  Only an existing forward point from the
    current atlas route can be inserted.
    """

    fine = route.waypoints
    if not corridor.complete or len(fine) < 3:
        return None
    minimum = max(0, min(int(minimum_route_index), len(fine) - 1))
    start_index = min(
        range(minimum, len(fine)),
        key=lambda index: hypot(
            fine[index].x - start_x,
            fine[index].y - start_y,
        ),
    )
    target_index = min(
        range(start_index, len(fine)),
        key=lambda index: hypot(
            fine[index].x - target_x,
            fine[index].y - target_y,
        ),
    )
    if target_index <= start_index + 1:
        return None
    semantic_polyline = (
        RoadWorldPoint(start_x, start_y),
        *fine[start_index + 1 : target_index + 1],
    )
    semantic_length = sum(
        hypot(right.x - left.x, right.y - left.y)
        for left, right in zip(semantic_polyline, semantic_polyline[1:])
    )
    guidance = corridor.guidance_points()
    corridor_length = sum(
        left.distance_2d(right) for left, right in zip(guidance, guidance[1:])
    )
    maximum_deviation = max(
        min(
            _point_segment_distance_2d(
                RoadWorldPoint(point.x, point.y),
                left,
                right,
            )
            for left, right in zip(semantic_polyline, semantic_polyline[1:])
        )
        for point in guidance
    )
    stretch = corridor_length / max(semantic_length, 0.01)
    if (
        maximum_deviation <= SEMANTIC_CORRIDOR_MAX_ROUTE_DEVIATION_WORLD
        and stretch <= SEMANTIC_CORRIDOR_MAX_ROUTE_STRETCH
    ):
        return None
    candidate = _semantic_refinement_midpoint(
        route=route,
        start_x=start_x,
        start_y=start_y,
        target_x=target_x,
        target_y=target_y,
        minimum_route_index=minimum_route_index,
    )
    if candidate is not None:
        route_index, point = candidate
        return route_index, point, maximum_deviation, stretch
    return None


def _semantic_refinement_midpoint(
    *,
    route: SemanticRoadRoute,
    start_x: float,
    start_y: float,
    target_x: float,
    target_y: float,
    minimum_route_index: int = 0,
) -> tuple[int, RoadWorldPoint] | None:
    """Select the deterministic fine-route midpoint for speculative planning.

    Selection depends only on the current semantic A* route.  A caller may
    therefore prepare this bounded candidate in parallel with the coarse
    Detour leg.  The candidate remains non-authoritative unless the completed
    coarse corridor later proves the route-deviation refinement gate.
    """

    fine = route.waypoints
    if len(fine) < 3:
        return None
    minimum = max(0, min(int(minimum_route_index), len(fine) - 1))
    start_index = min(
        range(minimum, len(fine)),
        key=lambda index: hypot(
            fine[index].x - start_x,
            fine[index].y - start_y,
        ),
    )
    target_index = min(
        range(start_index, len(fine)),
        key=lambda index: hypot(
            fine[index].x - target_x,
            fine[index].y - target_y,
        ),
    )
    candidates = [
        (route_index, fine[route_index])
        for route_index in range(start_index + 1, target_index)
        if hypot(
            fine[route_index].x - start_x,
            fine[route_index].y - start_y,
        )
        >= SEMANTIC_REFINEMENT_MIN_SPACING_WORLD
    ]
    if candidates:
        # Split near the middle, not at the first raster sample.  A 12-yard
        # leg is shorter than two isolated Detour queries on this client and
        # can reach its endpoint before the refined continuation is ready,
        # causing a visible one-second W lease gap.  A midpoint preserves the
        # bend while leaving enough moving time for rolling preplanning.
        direct = hypot(target_x - start_x, target_y - start_y)
        return min(
            candidates,
            key=lambda item: (
                abs(hypot(item[1].x - start_x, item[1].y - start_y) - direct * 0.5),
                -hypot(item[1].x - start_x, item[1].y - start_y),
            ),
        )
    return None


def _semantic_fallback_candidates(
    *,
    route: SemanticRoadRoute,
    start_x: float,
    start_y: float,
    target_x: float,
    target_y: float,
    minimum_route_index: int = 0,
) -> tuple[tuple[int, RoadWorldPoint], ...]:
    """Return fine road cells ahead of the actor up to one coarse target.

    A 30-yard semantic horizon is normally preferable, but a disconnected
    local Detour component can make that horizon partial even when the ordered
    fine semantic cells are individually reachable.  This is an adaptive
    hierarchy fallback, not a coded route: candidates come exclusively from
    the current atlas-derived A* result and progress monotonically.
    """

    waypoints = route.waypoints
    if not waypoints:
        return ()
    minimum = max(0, min(int(minimum_route_index), len(waypoints) - 1))
    start_index = min(
        range(minimum, len(waypoints)),
        key=lambda index: hypot(
            waypoints[index].x - start_x,
            waypoints[index].y - start_y,
        ),
    )
    target_index = min(
        range(start_index, len(waypoints)),
        key=lambda index: hypot(
            waypoints[index].x - target_x,
            waypoints[index].y - target_y,
        ),
    )
    return tuple(
        (index, waypoints[index])
        for index in range(start_index + 1, target_index + 1)
        if hypot(
            waypoints[index].x - start_x,
            waypoints[index].y - start_y,
        )
        >= 3.0
    )


def _semantic_forward_bypass_candidates(
    *,
    route: SemanticRoadRoute,
    start_x: float,
    start_y: float,
    blocked_target_x: float,
    blocked_target_y: float,
    limit_x: float,
    limit_y: float,
    minimum_route_index: int = 0,
    maximum_forward_waypoints: int = 0,
) -> tuple[tuple[int, RoadWorldPoint], ...]:
    """Return road cells just beyond an unreachable semantic horizon.

    A texture-road sample can land inside a client doodad even though the road
    continues around it. Once Detour has twice reached the same partial
    frontier, probe only the ordered atlas cells between that sample and the
    next coarse horizon. A candidate is executable only when a fresh
    client-navmesh query proves a complete route to it.
    """

    if not 0 <= maximum_forward_waypoints <= 32:
        raise ValueError("semantic forward bypass bound is invalid")
    waypoints = route.waypoints
    if not waypoints:
        return ()
    minimum = max(0, min(int(minimum_route_index), len(waypoints) - 1))
    start_index = min(
        range(minimum, len(waypoints)),
        key=lambda index: hypot(
            waypoints[index].x - start_x,
            waypoints[index].y - start_y,
        ),
    )
    blocked_index = min(
        range(start_index, len(waypoints)),
        key=lambda index: hypot(
            waypoints[index].x - blocked_target_x,
            waypoints[index].y - blocked_target_y,
        ),
    )
    limit_index = min(
        range(blocked_index, len(waypoints)),
        key=lambda index: hypot(
            waypoints[index].x - limit_x,
            waypoints[index].y - limit_y,
        ),
    )
    if maximum_forward_waypoints:
        # The next coalesced goal may itself be covered by a single large prop.
        # Extend only by a small number of ordered atlas samples; never scan
        # the complete route or invent a geometric bypass.
        limit_index = min(
            len(waypoints) - 1,
            limit_index + maximum_forward_waypoints,
        )
    return tuple(
        (index, waypoints[index])
        for index in range(blocked_index + 1, limit_index + 1)
        if hypot(
            waypoints[index].x - start_x,
            waypoints[index].y - start_y,
        )
        >= 3.0
    )


def _semantic_should_preplan(
    *,
    remaining_world: float,
    has_next: bool,
    radius_world: float = SEMANTIC_PREPLAN_RADIUS_WORLD,
) -> bool:
    if not isfinite(remaining_world) or remaining_world < 0:
        raise ValueError("semantic preplan distance is invalid")
    if not isfinite(radius_world) or not 1.0 <= radius_world <= 240.0:
        raise ValueError("semantic preplan radius is invalid")
    return has_next and remaining_world <= radius_world


def _semantic_should_fly_by(
    *,
    remaining_world: float,
    has_next: bool,
    next_corridor_ready: bool,
) -> bool:
    return (
        has_next
        and next_corridor_ready
        and remaining_world <= SEMANTIC_FLYBY_RADIUS_WORLD
    )


def _portal_recenter_candidates(
    corridor: NavCorridor,
    *,
    world_x: float,
    world_y: float,
    limit: int = 8,
) -> tuple[NavPoint, ...]:
    """Return forward topology centers after a confirmed local collision.

    Funnel paths are excellent for open navigation, but a client doodad such
    as a torch can occupy their shortest line inside a WMO.  The Detour portal
    sequence is ordered and already bound to the current corridor.  Advancing
    through a later portal center lets a blocker-aware query prove a real
    clearance route without blind jump/strafe macros or coded coordinates.
    """

    if (
        not corridor.geometry_aware
        or not all(isfinite(value) for value in (world_x, world_y))
        or not 1 <= limit <= 16
    ):
        return ()
    midpoints = tuple(
        NavPoint(
            (portal.left.x + portal.right.x) * 0.5,
            (portal.left.y + portal.right.y) * 0.5,
            (portal.left.z + portal.right.z) * 0.5,
        )
        for portal in corridor.portals
    )
    if not midpoints:
        return ()
    nearest_index = min(
        range(len(midpoints)),
        key=lambda index: midpoints[index].distance_2d(
            NavPoint(world_x, world_y, midpoints[index].z)
        ),
    )
    return tuple(
        point
        for point in midpoints[nearest_index + 1 : nearest_index + 1 + limit]
        if hypot(point.x - world_x, point.y - world_y) >= 2.0
    )


def _local_clearance_anchor_pairs(
    *,
    world_x: float,
    world_y: float,
    world_z: float,
    blocker: tuple[float, float, float, float],
) -> tuple[tuple[NavPoint, NavPoint], ...]:
    """Build geometry-relative two-leg paths around an observed obstacle.

    A small doodad can sit inside a valid Detour polygon, so excluding that
    whole polygon can disconnect a narrow indoor corridor.  These candidates
    are derived from the observed collision vector: first move away from the
    blocked ray, then pass beyond it.  Both sides are returned and must still
    be proven against the client navmesh before execution.
    """

    bx, by, bz, radius = blocker
    if (
        any(
            not isfinite(value)
            for value in (
                world_x,
                world_y,
                world_z,
                bx,
                by,
                bz,
                radius,
            )
        )
        or radius <= 0.0
    ):
        return ()
    dx, dy = bx - world_x, by - world_y
    distance = hypot(dx, dy)
    if distance < 0.25:
        return ()
    forward_x, forward_y = dx / distance, dy / distance
    lateral_x, lateral_y = -forward_y, forward_x
    lateral_clearance = max(2.25, radius + 0.75)
    forward_clearance = max(2.25, radius + 0.75)
    candidates: list[tuple[NavPoint, NavPoint]] = []
    for lateral_sign in (-1.0, 1.0):
        offset_x = lateral_x * lateral_clearance * lateral_sign
        offset_y = lateral_y * lateral_clearance * lateral_sign
        side_anchor = NavPoint(
            world_x + offset_x,
            world_y + offset_y,
            world_z,
        )
        pass_anchor = NavPoint(
            bx + forward_x * forward_clearance + offset_x,
            by + forward_y * forward_clearance + offset_y,
            world_z,
        )
        candidates.append((side_anchor, pass_anchor))
    return tuple(candidates)


def _collision_approach_heading(
    intent: SteeringIntent,
    *,
    world_x: float,
    world_y: float,
    observed_heading_rad: float | None,
    goal_x: float,
    goal_y: float,
) -> float:
    """Return the physical ray that actually met collision geometry.

    When facing is known, a railing or wall lies in that physical direction,
    not on the intended lookahead ray.  Projecting a steering mistake onto the
    commanded path creates a fake obstacle in the middle of an otherwise clear
    bridge.  Lookahead remains the fallback when facing is unavailable.
    """

    if observed_heading_rad is not None and isfinite(observed_heading_rad):
        return observed_heading_rad
    lookahead = intent.lookahead
    if (
        lookahead is not None
        and hypot(lookahead.x - world_x, lookahead.y - world_y) >= 0.25
    ):
        return atan2(lookahead.y - world_y, lookahead.x - world_x)
    return atan2(goal_y - world_y, goal_x - world_x)


def _local_clearance_leg_is_valid(
    corridor: NavCorridor,
    *,
    requested_start: NavPoint,
    requested_stop: NavPoint,
    maximum_vertical_delta: float = 4.0,
    maximum_detour_extra_world: float = 1.0,
) -> bool:
    """Reject wrong-floor projections and long topology detours."""

    if (
        not isfinite(maximum_detour_extra_world)
        or not 0.5 <= maximum_detour_extra_world <= 8.0
    ):
        raise ValueError("local clearance detour allowance is invalid")

    direct = requested_start.distance_2d(requested_stop)
    guidance = corridor.guidance_points()
    path_length = sum(
        first.distance_2d(second) for first, second in zip(guidance, guidance[1:])
    )
    return (
        corridor.complete
        # A local bypass anchor becomes a real movement command.  Accepting a
        # projection as far as one yard away proves only that Detour found a
        # nearby polygon, not that the requested body-safe point is reachable.
        and corridor.start.distance_2d(requested_start) <= 0.10
        and corridor.stop.distance_2d(requested_stop) <= 0.10
        and abs(corridor.start.z - requested_start.z) <= 2.5
        and abs(corridor.stop.z - corridor.start.z) <= maximum_vertical_delta
        # A small circular blocker needs a short arc.  Its arc can be a
        # little longer than the straight chord even when every point is on
        # the client navmesh.  The allowance is bounded and comes from the
        # observed blocker size; it is not a free route-length multiplier.
        and path_length <= direct * 1.75 + max(
            1.0, min(8.0, maximum_detour_extra_world)
        )
    )


def _corridor_preserves_obstacle_clearance(
    corridor: NavCorridor,
    obstacle: LearnedObstacle,
) -> bool:
    """Check every resolved guidance segment against the remembered body envelope.

    Safe endpoints do not imply a safe chord. Use the actual navmesh guidance,
    including projected endpoints, so interior bends cannot consume clearance.
    This is a local horizontal-envelope proof, not a full 3D collision sweep.
    """
    guidance = corridor.guidance_points()
    if not corridor.complete or len(guidance) < 2:
        return False
    center = RoadWorldPoint(obstacle.x, obstacle.y)
    required = obstacle.radius + DEFAULT_ACTOR_CLEARANCE_WORLD
    points = (corridor.start, *guidance, corridor.stop)
    return all(
        _point_segment_distance_2d(
            center, RoadWorldPoint(start.x, start.y), RoadWorldPoint(stop.x, stop.y),
        ) + 1.0e-6 >= required
        for start, stop in zip(points, points[1:])
    )


def _prepare_continuous_trajectory(
    *,
    query: ClientAssetNavmeshQuery,
    map_name: str,
    corridor: NavCorridor,
) -> tuple[NavCorridor, SmoothedTrajectory]:
    """Round a final Detour corridor while keeping Detour authoritative.

    This deliberately runs only during planning/preplanning, never in the
    control-frame loop.  Every chord introduced by a fillet must itself resolve
    to a short, complete corridor on the same active client-asset navmesh.
    """

    def validate_segment(start: NavPoint, stop: NavPoint) -> bool:
        try:
            segment = query.find_corridor(
                map_name=map_name,
                start=start,
                stop_x=stop.x,
                stop_y=stop.y,
                stop_z=stop.z,
            )
        except ClientNavmeshError:
            return False
        return _local_clearance_leg_is_valid(
            segment,
            requested_start=start,
            requested_stop=stop,
            maximum_vertical_delta=max(4.0, abs(stop.z - start.z) + 1.0),
        )

    trajectory = smooth_navmesh_corridor(
        corridor,
        validate_segment=validate_segment,
        minimum_turn_radius_world=2.25,
        sample_spacing_world=1.10,
    )
    prepared = replace(
        corridor,
        points=trajectory.points,
        source=f"{corridor.source}+continuous_trajectory_v1",
    )
    return prepared, trajectory


def _find_and_prepare_continuous_trajectory(
    *,
    query: ClientAssetNavmeshQuery,
    map_name: str,
    start: NavPoint,
    stop_x: float,
    stop_y: float,
) -> tuple[NavCorridor, SmoothedTrajectory]:
    corridor = query.find_corridor(
        map_name=map_name,
        start=start,
        stop_x=stop_x,
        stop_y=stop_y,
    )
    return _prepare_continuous_trajectory(
        query=query,
        map_name=map_name,
        corridor=corridor,
    )


def _semantic_preplan_in_worker_process(
    *,
    worker_path: str,
    nav_root_path: str,
    observed_blockers: tuple[tuple[float, float, float, float], ...],
    map_name: str,
    start: NavPoint,
    stop_x: float,
    stop_y: float,
    prepare_trajectory: bool,
) -> NavCorridor | tuple[NavCorridor, SmoothedTrajectory]:
    """Run a semantic Detour preplan outside the realtime capture process.

    The nav worker is already isolated from the game client, but JSON parsing
    and corridor smoothing still execute Python code. A thread doing that work
    can delay the pose loop long enough to create a false-looking movement
    pause. A bounded process-pool call keeps the capture/control thread free;
    the child owns a fresh, immutable query adapter and cannot issue input.
    """

    query = ClientAssetNavmeshQuery(
        worker=Path(worker_path),
        nav_root=Path(nav_root_path),
        observed_blockers=observed_blockers,
    )
    if prepare_trajectory:
        return _find_and_prepare_continuous_trajectory(
            query=query,
            map_name=map_name,
            start=start,
            stop_x=stop_x,
            stop_y=stop_y,
        )
    return query.find_corridor(
        map_name=map_name,
        start=start,
        stop_x=stop_x,
        stop_y=stop_y,
    )


def _semantic_forward_bypass_in_worker_process(
    *,
    worker_path: str,
    nav_root_path: str,
    observed_blockers: tuple[tuple[float, float, float, float], ...],
    map_name: str,
    start: NavPoint,
    candidates: tuple[tuple[int, float, float], ...],
    local_goal_radius: float,
) -> tuple[int, NavCorridor] | None:
    """Prepare the bounded atlas-forward frontier bypass off the control loop.

    Candidate points are supplied by the semantic A* route; this worker only
    validates them against the immutable client navmesh.  It never invents a
    lateral coordinate and it has no actuator access.  Returning the first
    complete candidate preserves the same ordered fallback semantics as the
    synchronous path while letting the actor finish the already-proven
    corridor before a frontier handoff.
    """

    if not candidates or len(candidates) > SEMANTIC_STATIC_FRONTIER_MAX_CANDIDATES:
        raise ValueError("semantic frontier candidate bound is invalid")
    if not isfinite(local_goal_radius) or local_goal_radius <= 0:
        raise ValueError("semantic frontier goal radius is invalid")
    query = ClientAssetNavmeshQuery(
        worker=Path(worker_path),
        nav_root=Path(nav_root_path),
        observed_blockers=observed_blockers,
    )
    for route_index, stop_x, stop_y in candidates:
        if not isinstance(route_index, int) or any(
            not isfinite(value) for value in (stop_x, stop_y)
        ):
            raise ValueError("semantic frontier candidate is invalid")

    def validate_candidate(
        candidate: tuple[int, float, float],
    ) -> tuple[int, NavCorridor] | None:
        route_index, stop_x, stop_y = candidate
        try:
            corridor = query.find_corridor(
                map_name=map_name,
                start=start,
                stop_x=stop_x,
                stop_y=stop_y,
            )
        except RuntimeError:
            return None
        if not _corridor_reaches_local_goal(
            corridor,
            goal_x=stop_x,
            goal_y=stop_y,
            radius_world=local_goal_radius,
        ):
            return None
        return route_index, corridor

    # The first candidate is the closest ordered road cell beyond the blocked
    # target and is the common fast path.  Probe it alone before fanning out:
    # returning from a ThreadPoolExecutor context waits for every speculative
    # child, even after the first ordered result is already valid.  On a cold
    # WorldPack that tail latency can hold the caller's control-loop lease for
    # seconds and surface as an unexplained observation gap.  A single bounded
    # query keeps the usual path cheap without changing candidate ordering.
    first_result = validate_candidate(candidates[0])
    if first_result is not None:
        return first_result
    if len(candidates) == 1:
        return None

    # Keep the ordered fallback semantics for the remaining candidates: probes
    # may run concurrently, but the result is selected by candidate order,
    # never by completion order.  The bounded context manager waits for these
    # read-only children before returning, avoiding orphaned probes in the
    # less common multi-failure path.
    with ThreadPoolExecutor(
        max_workers=min(
            SEMANTIC_STATIC_FRONTIER_WORKER_QUERY_CONCURRENCY,
            len(candidates) - 1,
        ),
        thread_name_prefix="pa-frontier-probe",
    ) as executor:
        futures = [
            executor.submit(validate_candidate, candidate)
            for candidate in candidates[1:]
        ]
        for future in futures:
            result = future.result()
            if result is not None:
                return result
    return None


def _async_worker_pool_warmup() -> bool:
    """Return a picklable no-op used to start a process-pool worker early.

    ``ProcessPoolExecutor`` starts its child processes lazily on the first
    submitted job.  Starting that child while the navigation loop is already
    holding the capture/control lease can create a false observation gap.  A
    no-op keeps the warmup side-effect free: the worker has no client handle,
    navmesh query or actuator authority.
    """

    return True


def _warm_process_pool(
    executor: ProcessPoolExecutor,
    *,
    pool_name: str,
    worker_count: int,
    timeout_s: float = 15.0,
) -> None:
    """Start all bounded read-only pool workers before realtime input.

    The warmup is deliberately fail-closed.  If a child cannot start or does
    not complete the no-op within the bounded deadline, the caller raises
    before opening the pose source or sending any input.
    """

    if worker_count <= 0:
        raise ValueError(f"{pool_name} worker count must be positive")
    if not isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError(f"{pool_name} warmup timeout must be positive")
    futures = [
        executor.submit(_async_worker_pool_warmup)
        for _ in range(worker_count)
    ]
    deadline = time.monotonic() + timeout_s
    for future in futures:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"{pool_name} worker pool warmup timed out")
        if future.result(timeout=remaining) is not True:
            raise RuntimeError(f"{pool_name} worker pool warmup failed")


def _wmo_baseline_reaches_local_goal_in_worker_process(
    *,
    worker_path: str,
    nav_root_path: str,
    observed_blockers: tuple[tuple[float, float, float, float], ...],
    map_name: str,
    start: NavPoint,
    stop_x: float,
    stop_y: float,
    local_goal_radius: float,
) -> bool:
    """Check one WMO baseline without holding the realtime control loop.

    WMO filtering is evidence gathering, not steering.  Keep the native
    worker and JSON/corridor work in the same process pool as semantic
    preplans; the caller applies the result only after ``Future.done()``.
    """

    query = ClientAssetNavmeshQuery(
        worker=Path(worker_path),
        nav_root=Path(nav_root_path),
        observed_blockers=observed_blockers,
    )
    try:
        corridor = query.find_corridor(
            map_name=map_name,
            start=start,
            stop_x=stop_x,
            stop_y=stop_y,
        )
    except RuntimeError:
        return False
    return _corridor_reaches_local_goal(
        corridor,
        goal_x=stop_x,
        goal_y=stop_y,
        radius_world=local_goal_radius,
    )


def _unpack_preplanned_corridor(
    value: NavCorridor | tuple[NavCorridor, SmoothedTrajectory],
) -> tuple[NavCorridor, SmoothedTrajectory | None]:
    if isinstance(value, NavCorridor):
        return value, None
    corridor, trajectory = value
    return corridor, trajectory


def _inject_confirmed_clearance_priors(
    *,
    route_start: RoadWorldPoint,
    goals: tuple[RoadWorldPoint, ...],
    obstacles: tuple[LearnedObstacle, ...],
    query: ClientAssetNavmeshQuery,
    map_name: str,
    terminal_goal_radius_world: float | None = None,
    route_start_z: float | None = None,
    continuation_cache: dict[tuple[float, float, float, float], NavCorridor]
    | None = None,
) -> tuple[tuple[RoadWorldPoint, ...], tuple[dict[str, object], ...]]:
    """Turn confirmed collision experience into proactive route geometry.

    No destination or map coordinate is encoded here.  Every remembered
    obstacle is matched geometrically against the newly planned semantic
    polyline.  Both lateral bypasses are generated from that line, every leg
    is freshly validated by the active client navmesh, and only the shortest
    valid candidate is inserted.  Unconfirmed observations never steer.
    """

    if not goals or not map_name.strip():
        return goals, ()
    if (
        terminal_goal_radius_world is not None
        and (
            not isfinite(terminal_goal_radius_world)
            or not 2.0 <= terminal_goal_radius_world <= 100.0
        )
    ):
        raise ValueError("terminal goal radius is invalid")
    if route_start_z is not None and (
        not isfinite(route_start_z) or not -500.0 <= route_start_z <= 5000.0
    ):
        raise ValueError("route start height is invalid")
    augmented = list(goals)
    applied: list[dict[str, object]] = []
    for obstacle in obstacles:
        if (
            not obstacle.planning_confirmed
            or obstacle.evidence != LOCAL_CLEARANCE_EVIDENCE
            or obstacle.map_name != map_name
        ):
            continue
        # Road semantic points carry XY only, while the client navmesh can
        # expose several stacked surfaces at the same XY.  A remembered prop
        # on a nearby, different floor must not seal the current route before
        # the selected local layer is planned.  Limit this check to the local
        # start horizon; hills and bridges farther along the route can change
        # altitude and are still validated by their own navmesh corridors.
        if (
            route_start_z is not None
            and hypot(obstacle.x - route_start.x, obstacle.y - route_start.y) <= 96.0
            and abs(obstacle.z - route_start_z) > 8.0
        ):
            applied.append(
                {
                    "kind": "CONFIRMED_CLEARANCE_PRIOR_SKIPPED_VERTICAL_LAYER",
                    "obstacle_id": obstacle.obstacle_id,
                    "observations": obstacle.observations,
                    "obstacle_z": obstacle.z,
                    "route_start_z": route_start_z,
                    "reason": "nearby_confirmed_geometry_is_on_different_client_surface",
                    "source": "confirmed_client_observed_geometry",
                }
            )
            continue
        # A confirmed obstacle inside the terminal semantic arrival area is
        # not a reason to chase the catalog point through a doorway, wall or
        # interior prop.  The destination contract explicitly permits arrival
        # anywhere in that bounded radius; leave this geometry to the final
        # navmesh corridor instead of manufacturing an impossible bypass.
        if (
            terminal_goal_radius_world is not None
            and hypot(
                obstacle.x - goals[-1].x,
                obstacle.y - goals[-1].y,
            ) <= terminal_goal_radius_world
        ):
            applied.append(
                {
                    "kind": "CONFIRMED_CLEARANCE_PRIOR_WITHIN_TERMINAL_RADIUS",
                    "obstacle_id": obstacle.obstacle_id,
                    "observations": obstacle.observations,
                    "terminal_goal_radius_world": terminal_goal_radius_world,
                    "source": "confirmed_client_observed_geometry",
                }
            )
            continue
        polyline = (route_start, *augmented)
        segment_candidates: list[tuple[float, int, float]] = []
        obstacle_point = RoadWorldPoint(obstacle.x, obstacle.y)
        for index, (start, stop) in enumerate(zip(polyline, polyline[1:])):
            dx, dy = stop.x - start.x, stop.y - start.y
            length_squared = dx * dx + dy * dy
            if length_squared <= 1.0e-9:
                continue
            fraction = max(
                0.0,
                min(
                    1.0,
                    ((obstacle.x - start.x) * dx + (obstacle.y - start.y) * dy)
                    / length_squared,
                ),
            )
            segment_candidates.append(
                (
                    _point_segment_distance_2d(obstacle_point, start, stop),
                    index,
                    fraction,
                )
            )
        if not segment_candidates:
            continue
        distance, segment_index, fraction = min(segment_candidates)
        # The tolerance covers road-raster quantization, not arbitrary nearby
        # scenery.  An obstacle must overlap the current route tube and lie
        # within the segment rather than merely beside an endpoint.
        route_overlap = obstacle.radius + DEFAULT_ACTOR_CLEARANCE_WORLD + 0.25
        if distance > route_overlap or not 0.05 <= fraction <= 0.95:
            continue
        clearance = max(2.25, obstacle.radius + DEFAULT_ACTOR_CLEARANCE_WORLD)
        # A coarse road sample can be geometrically valid yet sit inside the
        # clearance envelope of the newly confirmed object.  Keeping it would
        # command the actor to visit the blocker first and only then start the
        # bypass.  Remove every affected raster sample and recompute the local
        # segment from the untouched road points on both sides.  This is the
        # generic equivalent of anticipating a corner instead of touching it.
        retained_goals = [
            goal
            for goal in augmented
            if hypot(goal.x - obstacle.x, goal.y - obstacle.y) > clearance
        ]
        removed_goal_count = len(augmented) - len(retained_goals)
        if not retained_goals:
            applied.append(
                {
                    "kind": "CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED",
                    "obstacle_id": obstacle.obstacle_id,
                    "observations": obstacle.observations,
                    "reason": "confirmed_obstacle_consumed_remaining_route_samples",
                    "source": "confirmed_client_observed_geometry",
                }
            )
            continue
        augmented = retained_goals
        polyline = (route_start, *augmented)
        segment_candidates = []
        for index, (start, stop) in enumerate(zip(polyline, polyline[1:])):
            dx, dy = stop.x - start.x, stop.y - start.y
            length_squared = dx * dx + dy * dy
            if length_squared <= 1.0e-9:
                continue
            segment_candidates.append(
                (
                    _point_segment_distance_2d(obstacle_point, start, stop),
                    index,
                )
            )
        if not segment_candidates:
            applied.append(
                {
                    "kind": "CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED",
                    "obstacle_id": obstacle.obstacle_id,
                    "observations": obstacle.observations,
                    "reason": "no_route_segment_remained_after_clearance_filter",
                    "source": "confirmed_client_observed_geometry",
                }
            )
            continue
        _, segment_index = min(segment_candidates)
        segment_start, segment_stop = (
            polyline[segment_index],
            polyline[segment_index + 1],
        )
        dx, dy = segment_stop.x - segment_start.x, segment_stop.y - segment_start.y
        length = hypot(dx, dy)
        forward_x, forward_y = dx / length, dy / length
        lateral_x, lateral_y = -forward_y, forward_x
        probe_distance = clearance * 1.5
        before = NavPoint(
            obstacle.x - forward_x * probe_distance,
            obstacle.y - forward_y * probe_distance,
            obstacle.z,
        )
        after = NavPoint(
            obstacle.x + forward_x * probe_distance,
            obstacle.y + forward_y * probe_distance,
            obstacle.z,
        )
        # A bounded cell is a collision *boundary sample*, not the centre of
        # a circular prop.  Requiring the same 2.25-yard arc around such a
        # sample can seal a valid stair or doorway.  Prefer the widest safe
        # arc, then reduce it only when every leg remains valid on the active
        # client navmesh.  True polygon/disc geometry keeps the conservative
        # clearance and never receives this fallback.
        clearance_profiles = [clearance]
        if obstacle.representation == BOUNDED_CELL_REPRESENTATION:
            # Never validate only the centre line. The smallest candidate is
            # the actor's horizontal body clearance; anything narrower can
            # be traversable for a Detour point while the visible shoulders
            # still collide with the same boundary.
            clearance_profiles.extend(
                (1.75, 1.5, DEFAULT_ACTOR_CLEARANCE_WORLD)
            )
        clearance_profiles = list(dict.fromkeys(
            round(value, 6)
            for value in clearance_profiles
            if value <= clearance + 1.0e-6
        ))
        valid_candidates: list[
            tuple[
                float, float, NavPoint, NavPoint, NavPoint,
                tuple[NavCorridor, ...],
            ]
        ] = []
        selected_clearance: float | None = None
        for candidate_clearance in clearance_profiles:
            # ``candidate_clearance`` is applied on both the forward and the
            # lateral axis below.  The actual distance from the remembered
            # boundary cell is therefore the diagonal of those components.
            # Do not accept a Detour centre line that leaves less room than
            # the observed cell radius plus the actor's horizontal body
            # clearance.  The live ME-503 failure exposed exactly this gap.
            if hypot(candidate_clearance, candidate_clearance) + 1.0e-6 < (
                obstacle.radius + DEFAULT_ACTOR_CLEARANCE_WORLD
            ):
                continue
            profile_candidates: list[
                tuple[
                    float, float, NavPoint, NavPoint, NavPoint,
                    tuple[NavCorridor, ...],
                ]
            ] = []
            candidate_probe_distance = candidate_clearance * 1.5
            candidate_before = NavPoint(
                obstacle.x - forward_x * candidate_probe_distance,
                obstacle.y - forward_y * candidate_probe_distance,
                obstacle.z,
            )
            candidate_after = NavPoint(
                obstacle.x + forward_x * candidate_probe_distance,
                obstacle.y + forward_y * candidate_probe_distance,
                obstacle.z,
            )
            for lateral_sign in (-1.0, 1.0):
                offset_x = lateral_x * candidate_clearance * lateral_sign
                offset_y = lateral_y * candidate_clearance * lateral_sign
                side = NavPoint(
                    obstacle.x - forward_x * candidate_clearance + offset_x,
                    obstacle.y - forward_y * candidate_clearance + offset_y,
                    obstacle.z,
                )
                passed = NavPoint(
                    obstacle.x + forward_x * candidate_clearance + offset_x,
                    obstacle.y + forward_y * candidate_clearance + offset_y,
                    obstacle.z,
                )
                legs: list[NavCorridor] = []
                valid = True
                for leg_start, leg_stop in (
                    (candidate_before, side),
                    (side, passed),
                    (passed, candidate_after),
                ):
                    corridor = query.find_corridor(
                        map_name=map_name,
                        start=leg_start,
                        stop_x=leg_stop.x,
                        stop_y=leg_stop.y,
                        stop_z=leg_stop.z,
                    )
                    if not _local_clearance_leg_is_valid(
                        corridor,
                        requested_start=leg_start,
                        requested_stop=leg_stop,
                        maximum_detour_extra_world=max(
                            1.0, min(8.0, obstacle.radius + 0.25)
                        ),
                    ) or not _corridor_preserves_obstacle_clearance(corridor, obstacle):
                        valid = False
                        break
                    legs.append(corridor)
                if valid:
                    # Execute the points resolved by the active navmesh, not
                    # merely the requested samples.  The strict projection
                    # bound above keeps these equivalent while preserving the
                    # correct surface height in stacked interiors.
                    resolved_side = legs[0].stop
                    resolved_passed = legs[1].stop
                    resolved_after = legs[2].stop
                    route_length = sum(
                        sum(
                            first.distance_2d(second)
                            for first, second in zip(
                                corridor.guidance_points(),
                                corridor.guidance_points()[1:],
                            )
                        )
                        for corridor in legs
                    )
                    profile_candidates.append((
                        route_length,
                        candidate_clearance,
                        resolved_side,
                        resolved_passed,
                        resolved_after,
                        tuple(legs),
                    ))
            if profile_candidates:
                selected_clearance = candidate_clearance
                valid_candidates = profile_candidates
                before = candidate_before
                after = candidate_after
                break
        if not valid_candidates:
            distance_from_route_start = hypot(
                obstacle.x - route_start.x,
                obstacle.y - route_start.y,
            )
            # The three short clearance legs are a local proof.  A resumed
            # journey can meet the same remembered object from the opposite
            # direction, hundreds of yards before its real terrain layer is
            # reached.  In that case ask Detour for the road segment itself
            # with the remembered actor-sized blocker applied.  This remains
            # client-asset geometry; no destination coordinate or authored
            # bypass is introduced.
            if distance_from_route_start > 96.0:
                global_blockers = _bounded_blocker_union(
                    query.observed_blockers,
                    (obstacle.planning_blocker(),),
                    origin_x=obstacle.x,
                    origin_y=obstacle.y,
                )
                global_query = query.with_observed_blockers(global_blockers)
                global_corridor = global_query.find_corridor(
                    map_name=map_name,
                    start=NavPoint(
                        segment_start.x, segment_start.y, obstacle.z,
                    ),
                    stop_x=segment_stop.x,
                    stop_y=segment_stop.y,
                    stop_z=obstacle.z,
                )
                guidance = global_corridor.guidance_points()
                if (
                    _corridor_reaches_local_goal(
                        global_corridor,
                        goal_x=segment_stop.x,
                        goal_y=segment_stop.y,
                        radius_world=2.0,
                    )
                    and len(guidance) > 2
                    and continuation_cache is not None
                    and _corridor_preserves_obstacle_clearance(global_corridor, obstacle)
                ):
                    # Keep Detour's complete corridor as one executable leg.
                    # Expanding every funnel point into a semantic waypoint
                    # makes the controller stop/replan at each tiny point and
                    # turns one smooth avoidance arc into dozens of robotic
                    # handoffs. The immutable corridor already contains all
                    # geometry needed to clear the remembered object safely.
                    continuation_cache[
                        (
                            round(segment_start.x, 6),
                            round(segment_start.y, 6),
                            round(segment_stop.x, 6),
                            round(segment_stop.y, 6),
                        )
                    ] = global_corridor
                    applied.append(
                        {
                            "kind": (
                                "CONFIRMED_CLEARANCE_PRIOR_APPLIED_BY_GLOBAL_"
                                "NAVMESH"
                            ),
                            "obstacle_id": obstacle.obstacle_id,
                            "observations": obstacle.observations,
                            "distance_from_route_start_world": (
                                distance_from_route_start
                            ),
                            "detour_point_count": len(guidance) - 2,
                            "semantic_waypoints_inserted": 0,
                            "reason": (
                                "opposite_direction_local_arc_replaced_by_one_"
                                "cached_client_navmesh_corridor"
                            ),
                            "source": "confirmed_client_observed_geometry",
                        }
                    )
                    continue
            applied.append(
                {
                    "kind": "CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED",
                    "obstacle_id": obstacle.obstacle_id,
                    "observations": obstacle.observations,
                    "reason": "no_navmesh_validated_bypass_for_confirmed_geometry",
                    "source": "confirmed_client_observed_geometry",
                }
            )
            continue
        route_length, used_clearance, side, passed, after, clearance_legs = min(
            valid_candidates,
            key=lambda item: (item[0], item[2].x, item[2].y),
        )
        if continuation_cache is not None:
            # The final bypass leg was already validated from `passed` to
            # `after` above. Validate one more bounded leg to the untouched
            # route point and retain the joined corridor. This removes a
            # synchronous query at a tiny clearance anchor without turning
            # the prior into an executable operator waypoint.
            resume_corridor = query.find_corridor(
                map_name=map_name,
                start=after,
                stop_x=segment_stop.x,
                stop_y=segment_stop.y,
                stop_z=after.z,
            )
            if _local_clearance_leg_is_valid(
                resume_corridor,
                requested_start=after,
                requested_stop=segment_stop,
                maximum_detour_extra_world=max(
                    1.0, min(8.0, obstacle.radius + 0.25)
                ),
            ) and _corridor_preserves_obstacle_clearance(resume_corridor, obstacle):
                continuation = _joined_semantic_preview_corridor(
                    clearance_legs[2],
                    resume_corridor,
                )
                if continuation is not None and _corridor_preserves_obstacle_clearance(
                    continuation, obstacle,
                ):
                    continuation_cache[
                        (
                            round(passed.x, 6),
                            round(passed.y, 6),
                            round(segment_stop.x, 6),
                            round(segment_stop.y, 6),
                        )
                    ] = continuation
        insertion_index = segment_index
        augmented[insertion_index:insertion_index] = [
            RoadWorldPoint(side.x, side.y),
            RoadWorldPoint(passed.x, passed.y),
        ]
        applied.append(
            {
                "kind": "CONFIRMED_CLEARANCE_PRIOR_APPLIED",
                "obstacle_id": obstacle.obstacle_id,
                "observations": obstacle.observations,
                "route_distance_world": route_length,
                "side_anchor_world": [side.x, side.y, side.z],
                "pass_anchor_world": [passed.x, passed.y, passed.z],
                "clearance_world": used_clearance,
                "clearance_profile": (
                    "adaptive_boundary_sample"
                    if selected_clearance != clearance
                    else "conservative"
                ),
                "source": "confirmed_client_observed_geometry",
                "superseded_route_sample_count": removed_goal_count,
            }
        )
    return tuple(augmented), tuple(applied)


def _confirmed_local_corridor_clearance(
    *,
    corridor: NavCorridor,
    obstacles: tuple[LearnedObstacle, ...],
    query: ClientAssetNavmeshQuery,
    map_name: str,
    route_start_z: float,
) -> tuple[tuple[RoadWorldPoint, RoadWorldPoint] | None, tuple[dict[str, object], ...]]:
    """Find a proactive bypass on the corridor the actor will really walk.

    The semantic road is intentionally coarse.  Indoors, its straight chord
    can miss a stair/table contact that exists on Detour's actual local
    corridor.  Reuse the same geometry-only proof against that local corridor
    and return only the two validated bypass anchors, never its funnel samples
    as operator-authored waypoints.
    """

    guidance = corridor.guidance_points()
    if len(guidance) < 2 or not obstacles:
        return None, ()
    ordered_obstacles = tuple(sorted(
        obstacles,
        key=lambda item: guidance[0].distance_2d(
            NavPoint(item.x, item.y, item.z)
        ),
    ))
    _, evidence = _inject_confirmed_clearance_priors(
        route_start=RoadWorldPoint(guidance[0].x, guidance[0].y),
        goals=tuple(RoadWorldPoint(point.x, point.y) for point in guidance[1:]),
        obstacles=ordered_obstacles,
        query=query,
        map_name=map_name,
        route_start_z=route_start_z,
    )
    for item in evidence:
        if item["kind"] != "CONFIRMED_CLEARANCE_PRIOR_APPLIED":
            continue
        side = item["side_anchor_world"]
        passed = item["pass_anchor_world"]
        return (
            RoadWorldPoint(float(side[0]), float(side[1])),
            RoadWorldPoint(float(passed[0]), float(passed[1])),
        ), evidence
    return None, evidence


def _inject_traversed_surface_prior(
    *,
    route_start: RoadWorldPoint,
    goals: tuple[RoadWorldPoint, ...],
    obstacles: tuple[LearnedObstacle, ...],
    recording: ManualPathRecording | None,
) -> tuple[
    tuple[RoadWorldPoint, ...],
    tuple[str, ...],
    dict[str, object] | None,
]:
    """Repair one false local chord from positively observed free space."""

    if recording is None or recording.status not in {"COMPLETE", "IMPORTED"}:
        return goals, (), None
    if not goals or len(recording.vertices) < 3:
        return goals, (), None
    first_goal = goals[0]
    intersecting = tuple(
        obstacle
        for obstacle in obstacles
        if obstacle.planning_confirmed
        and _point_segment_distance_2d(
            RoadWorldPoint(obstacle.x, obstacle.y), route_start, first_goal,
        ) <= obstacle.radius + 0.5
    )
    if not intersecting:
        return goals, (), None

    def clear_to_goal(point: RoadWorldPoint, goal: RoadWorldPoint) -> bool:
        return all(
            _point_segment_distance_2d(
                RoadWorldPoint(obstacle.x, obstacle.y), point, goal,
            ) > obstacle.radius + 0.5
            and hypot(goal.x - obstacle.x, goal.y - obstacle.y)
            > obstacle.radius + 0.5
            for obstacle in intersecting
        )

    vertices = recording.vertices
    starts = tuple(
        index
        for index, vertex in enumerate(vertices[:-2])
        if hypot(vertex.x - route_start.x, vertex.y - route_start.y) <= 2.5
    )
    candidates: list[tuple[float, int, int, int]] = []
    quality_rejections: list[dict[str, float | int | str]] = []
    # A human demonstration is positive traversability evidence, not an
    # executable route.  Only a locally coherent prefix may be promoted to a
    # route repair; a recording that wanders several times farther than the
    # straight displacement is almost certainly operator hesitation, a camera
    # correction, or a loop at a boundary.  Keeping this ratio generic avoids
    # encoding any crypt/zone coordinates while preventing those loops from
    # becoming the next run's waypoints.
    maximum_detour_ratio = 3.0
    for start_index in starts:
        travelled = 0.0
        previous = vertices[start_index]
        for stop_index in range(start_index + 1, len(vertices)):
            current = vertices[stop_index]
            step = hypot(current.x - previous.x, current.y - previous.y)
            previous = current
            if step > 15.0:
                break
            travelled += step
            if travelled > 300.0:
                break
            if travelled >= 6.0:
                point = RoadWorldPoint(current.x, current.y)
                rejoin_index = next((
                    index
                    for index, goal in enumerate(goals)
                    if hypot(point.x - goal.x, point.y - goal.y) <= 8.0
                    and clear_to_goal(point, goal)
                ), None)
                if rejoin_index is not None:
                    direct_distance = hypot(
                        current.x - route_start.x,
                        current.y - route_start.y,
                    )
                    start_basin_revisits = sum(
                        hypot(vertex.x - route_start.x, vertex.y - route_start.y)
                        <= 2.5
                        for vertex in vertices[:start_index]
                    )
                    reversal_count = 0
                    for left, middle, right in zip(
                        vertices[start_index:stop_index - 1],
                        vertices[start_index + 1:stop_index],
                        vertices[start_index + 2:stop_index + 1],
                    ):
                        first_x, first_y = middle.x - left.x, middle.y - left.y
                        second_x, second_y = right.x - middle.x, right.y - middle.y
                        first_length = hypot(first_x, first_y)
                        second_length = hypot(second_x, second_y)
                        if (
                            first_length >= 0.5
                            and second_length >= 0.5
                            and first_x * second_x + first_y * second_y
                            < -0.25 * first_length * second_length
                        ):
                            reversal_count += 1
                    if start_basin_revisits >= 2:
                        quality_rejections.append(
                            {
                                "start_index": start_index,
                                "stop_index": stop_index,
                                "travelled_world": travelled,
                                "direct_displacement_world": direct_distance,
                                "detour_ratio": (
                                    float("inf")
                                    if direct_distance <= 1.0e-9
                                    else travelled / direct_distance
                                ),
                                "maximum_detour_ratio": maximum_detour_ratio,
                                "start_basin_revisits": start_basin_revisits,
                                "reason": "recording_reentered_start_basin",
                            }
                        )
                    elif reversal_count >= 2:
                        quality_rejections.append(
                            {
                                "start_index": start_index,
                                "stop_index": stop_index,
                                "travelled_world": travelled,
                                "direct_displacement_world": direct_distance,
                                "detour_ratio": (
                                    float("inf")
                                    if direct_distance <= 1.0e-9
                                    else travelled / direct_distance
                                ),
                                "maximum_detour_ratio": maximum_detour_ratio,
                                "backtrack_reversal_count": reversal_count,
                                "reason": "recording_backtracking_detected",
                            }
                        )
                    elif (
                        direct_distance >= 1.0
                        and travelled <= maximum_detour_ratio * direct_distance
                    ):
                        candidates.append(
                            (travelled, start_index, stop_index, rejoin_index)
                        )
                    else:
                        quality_rejections.append(
                            {
                                "start_index": start_index,
                                "stop_index": stop_index,
                                "travelled_world": travelled,
                                "direct_displacement_world": direct_distance,
                                "detour_ratio": (
                                    float("inf")
                                    if direct_distance <= 1.0e-9
                                    else travelled / direct_distance
                                ),
                                "maximum_detour_ratio": maximum_detour_ratio,
                                "reason": "recording_detour_ratio_exceeded",
                            }
                        )
                    break
    if not candidates:
        if quality_rejections:
            best = min(
                quality_rejections,
                key=lambda item: float(item["detour_ratio"]),
            )
            # The recording is allowed to contradict the coarse obstacle
            # envelope even when it is too noisy to execute.  It only
            # suppresses that false-chord memory; it never supplies movement
            # points.  This is the safe distinction between evidence and
            # execution authority for a locally observed passage.
            demonstrated = tuple(item.obstacle_id for item in intersecting)
            return (
                goals,
                demonstrated,
                {
                    "kind": "TRAVERSED_SURFACE_TOPOLOGY_PRIOR_REJECTED",
                    "recording_id": recording.recording_id,
                    "local_point_count": 0,
                    "local_distance_world": best["travelled_world"],
                    "rejoined_goal_index": None,
                    "reason": best["reason"],
                    "detour_ratio": best["detour_ratio"],
                    "maximum_detour_ratio": maximum_detour_ratio,
                    "start_basin_revisits": best.get("start_basin_revisits", 0),
                    "backtrack_reversal_count": best.get("backtrack_reversal_count", 0),
                    "superseded_false_chord_obstacle_ids": list(demonstrated),
                    "source": "operator_observed_continuous_traversability",
                    "execution_authority": False,
                },
            )
        return goals, (), None
    travelled, start_index, stop_index, rejoin_index = min(
        candidates,
        key=lambda item: (
            item[0] + hypot(
                vertices[item[2]].x - goals[item[3]].x,
                vertices[item[2]].y - goals[item[3]].y,
            ),
            -item[1],
        ),
    )
    prefix: list[RoadWorldPoint] = []
    last = route_start
    for vertex in vertices[start_index + 1:stop_index + 1]:
        point = RoadWorldPoint(vertex.x, vertex.y)
        if hypot(point.x - last.x, point.y - last.y) >= 1.25:
            prefix.append(point)
            last = point
    final = RoadWorldPoint(vertices[stop_index].x, vertices[stop_index].y)
    if not prefix or prefix[-1] != final:
        prefix.append(final)
    bypassed = tuple(item.obstacle_id for item in intersecting)
    # A COMPLETE demonstration can disprove a learned collision envelope, but
    # it never becomes the next executable route.  Returning its vertices here
    # silently converted an operator recording into hardcoded waypoints.  Keep
    # the autonomous semantic goals unchanged; the active client navmesh will
    # rebuild the corridor after the contradicted blocker is suppressed.
    return (
        goals,
        bypassed,
        {
            "kind": "TRAVERSED_SURFACE_TOPOLOGY_PRIOR_APPLIED",
            "recording_id": recording.recording_id,
            "local_point_count": 0,
            "observed_point_count": len(prefix),
            "local_distance_world": travelled,
            "rejoined_goal_index": rejoin_index,
            "rejoined_goal_world": [
                goals[rejoin_index].x, goals[rejoin_index].y,
            ],
            "superseded_false_chord_obstacle_ids": list(bypassed),
            "source": "operator_observed_continuous_traversability",
            "reason": "successful_traversal_contradicts_obstacle_only",
            "execution_authority": False,
        },
    )


def _corridor_remaining_length(
    corridor: NavCorridor,
    *,
    world_x: float,
    world_y: float,
) -> float:
    """Return path distance after the nearest projection on its guidance."""

    guidance = corridor.guidance_points()
    if len(guidance) < 2:
        return 0.0
    segment_lengths = tuple(
        first.distance_2d(second) for first, second in zip(guidance, guidance[1:])
    )
    suffix = [0.0] * (len(segment_lengths) + 1)
    for index in range(len(segment_lengths) - 1, -1, -1):
        suffix[index] = suffix[index + 1] + segment_lengths[index]
    best_distance = float("inf")
    best_remaining = suffix[0]
    for index, (start, stop) in enumerate(zip(guidance, guidance[1:])):
        dx, dy = stop.x - start.x, stop.y - start.y
        length_squared = dx * dx + dy * dy
        if length_squared <= 1.0e-9:
            continue
        fraction = max(
            0.0,
            min(
                1.0,
                ((world_x - start.x) * dx + (world_y - start.y) * dy) / length_squared,
            ),
        )
        projected_x = start.x + dx * fraction
        projected_y = start.y + dy * fraction
        distance = hypot(world_x - projected_x, world_y - projected_y)
        if distance < best_distance:
            best_distance = distance
            best_remaining = (
                segment_lengths[index] * (1.0 - fraction) + suffix[index + 1]
            )
    return best_remaining


def _blocker_route_quality(
    candidate: NavCorridor,
    baseline: NavCorridor,
    *,
    world_x: float,
    world_y: float,
    goal_x: float,
    goal_y: float,
    blocker_radius: float,
) -> tuple[bool, float, float, float]:
    """Bound global detour inflation caused by one small observed blocker.

    Excluding every polygon touched by a 1.5-yard collision disc can disconnect
    a road corridor and still yield a technically complete, map-scale loop.
    Such a route is not a humanlike local avoidance maneuver.  Prefer the
    geometry-relative clearance legs; accept global exclusion only when its
    remaining length stays near the already validated baseline corridor.
    """

    candidate_length = _corridor_remaining_length(
        candidate,
        world_x=world_x,
        world_y=world_y,
    )
    baseline_length = _corridor_remaining_length(
        baseline,
        world_x=world_x,
        world_y=world_y,
    )
    direct = hypot(goal_x - world_x, goal_y - world_y)
    local_allowance = max(12.0, blocker_radius * 8.0)
    maximum_length = min(
        baseline_length + local_allowance,
        max(direct * 3.0, direct + local_allowance),
    )
    accepted = (
        candidate.complete
        and candidate.start.distance_2d(NavPoint(world_x, world_y, candidate.start.z))
        <= 2.0
        and candidate_length <= maximum_length
    )
    return accepted, candidate_length, baseline_length, maximum_length


def _allow_bounded_blocker_exclusion(
    blocker_route_accepted: bool,
    *,
    local_recovery_attempts: int,
    structure_egress_active: bool,
    candidate_complete: bool = False,
    excluded_polygons: int = 0,
    route_length_world: float | None = None,
    route_maximum_length_world: float | None = None,
) -> bool:
    """Keep a verified egress detour available after local retries.

    Ordinary road recovery stops using whole-polygon exclusion after three
    local attempts; that protects the planner from learning a large loop from
    one bad collision.  A known-structure egress is different: its opening
    and continuation were already verified by the access graph and client
    navmesh.  If the bounded route-quality check still accepts a small
    exclusion, it is the safe way out of the concavity and must not be
    replaced by a breadcrumb backtrack to the same wall. A route that is only
    a little longer than the local allowance is also accepted when the active
    client navmesh actually excluded polygons. A route with no excluded
    polygons is never promoted by this fallback.
    """

    if (
        type(blocker_route_accepted) is not bool
        or type(local_recovery_attempts) is not int
        or local_recovery_attempts < 0
        or type(structure_egress_active) is not bool
        or type(candidate_complete) is not bool
        or type(excluded_polygons) is not int
        or excluded_polygons < 0
        or (
            route_length_world is not None
            and not isfinite(route_length_world)
        )
        or (
            route_maximum_length_world is not None
            and not isfinite(route_maximum_length_world)
        )
    ):
        raise ValueError("bounded blocker exclusion inputs are invalid")
    if local_recovery_attempts >= 3 and not structure_egress_active:
        return False
    if (
        not blocker_route_accepted
        and structure_egress_active
        and candidate_complete
        and excluded_polygons > 0
        and route_length_world is not None
        and route_maximum_length_world is not None
        and route_length_world
        <= route_maximum_length_world + STRUCTURE_EGRESS_BLOCKER_ROUTE_MAX_OVERRUN_WORLD
    ):
        return True
    return blocker_route_accepted


def _corridor_reaches_local_goal(
    corridor: NavCorridor,
    *,
    goal_x: float,
    goal_y: float,
    radius_world: float,
) -> bool:
    return (
        corridor.complete
        and corridor.stop.distance_2d(NavPoint(goal_x, goal_y, corridor.stop.z))
        <= radius_world
    )


def _reachable_semantic_lookahead(
    *,
    engine: MovementEngine,
    start: NavPoint,
    goals: list[RoadWorldPoint],
    blocked_index: int,
    radius_world: float,
    maximum_skipped_goals: int = 8,
) -> tuple[int, NavCorridor] | None:
    """Find a later atlas goal reachable by one verified local corridor."""

    if not 1 <= maximum_skipped_goals <= 16:
        raise ValueError("semantic lookahead bound is invalid")
    stop_index = min(
        len(goals),
        blocked_index + maximum_skipped_goals + 1,
    )
    for index in range(blocked_index + 1, stop_index):
        candidate = goals[index]
        try:
            corridor = engine.plan(
                start=start,
                goal_x=candidate.x,
                goal_y=candidate.y,
            )
        except ClientNavmeshError:
            continue
        if _corridor_reaches_local_goal(
            corridor,
            goal_x=candidate.x,
            goal_y=candidate.y,
            radius_world=radius_world,
        ):
            return index, corridor
    return None


def _plan_semantic_goal_or_forward_projection(
    *,
    engine: MovementEngine,
    start: NavPoint,
    goals: list[RoadWorldPoint],
    goal_index: int,
    radius_world: float,
) -> tuple[int, NavCorridor, bool]:
    """Plan one atlas goal, or project forward to a valid road sample.

    Texture raster centers can land inside a prop footprint or a tiny navmesh
    hole. A semantic waypoint is not a physical destination, so the bounded
    fallback skips only forward on the same atlas-derived route and accepts
    the first point reached by a complete Detour corridor. It never invents a
    lateral coordinate.
    """

    if not 0 <= goal_index < len(goals):
        raise ValueError("semantic goal index is outside the route")
    goal = goals[goal_index]
    try:
        corridor = engine.plan(
            start=start,
            goal_x=goal.x,
            goal_y=goal.y,
        )
    except ClientNavmeshError:
        lookahead = _reachable_semantic_lookahead(
            engine=engine,
            start=start,
            goals=goals,
            blocked_index=goal_index,
            radius_world=radius_world,
        )
        if lookahead is None:
            raise
        selected_index, selected_corridor = lookahead
        return selected_index, selected_corridor, True
    return goal_index, corridor, False


def _verified_structure_egress_plan(
    *,
    engine: MovementEngine,
    direct_corridor: NavCorridor,
    goal_x: float,
    goal_y: float,
    observed_monotonic_s: float,
    excluded_opening_ids: frozenset[str] = frozenset(),
) -> StructureEgressPlan | None:
    """Convert durable structure knowledge into a navmesh-verified proposal."""

    awareness = engine.environment_at_corridor_start(
        direct_corridor,
        observed_monotonic_s=(
            direct_corridor.awareness_observed_monotonic_s
            if direct_corridor.awareness_observed_monotonic_s is not None
            else observed_monotonic_s
        ),
    )
    if awareness is None:
        return None
    return engine.plan_via_known_structure_egress(
        awareness=awareness,
        direct_corridor=direct_corridor,
        goal_x=goal_x,
        goal_y=goal_y,
        excluded_opening_ids=excluded_opening_ids,
    )


def _scope_query_for_structure_egress(
    *,
    query: ClientAssetNavmeshQuery,
    structures: Any,
    proposal: StructureEgressPlan,
) -> ClientAssetNavmeshQuery:
    """Keep one verified structure exit from reusing stale interior blockers."""

    if structures is None:
        return query
    get_structure = getattr(structures, "get", None)
    structure = get_structure(proposal.structure_id) if callable(get_structure) else None
    if structure is None:
        return query
    bounds = structure.bounds
    return query.for_structure_egress(
        bounds=(
            bounds.minimum.x,
            bounds.minimum.y,
            bounds.minimum.z,
            bounds.maximum.x,
            bounds.maximum.y,
            bounds.maximum.z,
        )
    )


def _corridor_requested_stop_z(corridor: NavCorridor) -> float | None:
    """Keep a replan on the corridor's proven vertical layer.

    ``find_corridor`` is intentionally 2D-compatible when no height is given.
    That fallback is unsafe for an active structure egress: a fresh query to
    the anchor XY can resolve the covered floor instead of the stair/door
    transition proved by the original floor-aware corridor. Replans carry
    forward the requested stop height when the corridor provides it; ordinary
    outdoor corridors simply return ``None`` and retain legacy 2D behavior.
    """

    requested_stop = corridor.requested_stop
    if requested_stop is None or not isfinite(requested_stop.z):
        return None
    return float(requested_stop.z)


def _forward_structure_egress_plan(
    *,
    engine: MovementEngine,
    direct_corridor: NavCorridor,
    goals: list[RoadWorldPoint],
    goal_index: int,
    goal_x: float,
    goal_y: float,
    observed_monotonic_s: float,
    excluded_opening_ids: frozenset[str] = frozenset(),
    maximum_goal_lookahead: int = STRUCTURE_EGRESS_SEMANTIC_LOOKAHEAD_GOALS,
) -> tuple[int, StructureEgressPlan] | None:
    """Select the first bounded semantic goal with a verified WMO exit.

    Interior road raster samples remain evidence about route shape, but they
    must not force a detour deeper into the same immutable structure before a
    known exit. Every skipped candidate is still proposed by the semantic
    route, and the selected opening plus both physical legs are revalidated by
    the active standalone navmesh.
    """

    if (
        not 0 <= goal_index < len(goals)
        or not 1 <= maximum_goal_lookahead <= 32
    ):
        raise ValueError("structure egress semantic lookahead is invalid")
    current = (
        _verified_structure_egress_plan(
            engine=engine,
            direct_corridor=direct_corridor,
            goal_x=goal_x,
            goal_y=goal_y,
            observed_monotonic_s=observed_monotonic_s,
            excluded_opening_ids=excluded_opening_ids,
        )
        if direct_corridor.complete
        else None
    )
    if current is not None:
        return goal_index, current
    if engine.structures is None or engine.structure_access is None:
        return None
    awareness = engine.environment_at_corridor_start(
        direct_corridor,
        observed_monotonic_s=observed_monotonic_s,
    )
    if awareness is None or len(awareness.containing_structures) != 1:
        return None
    staging_corridor = direct_corridor
    if not direct_corridor.complete:
        # A stacked WMO can expose a partial lower-floor corridor even though
        # its validated frontier reaches a stair/door transition. Reacquire
        # the local surface at that frontier before asking the graph for an
        # egress, then prepend the already validated prefix to the approach.
        try:
            staging_corridor = engine.plan(
                start=direct_corridor.stop,
                goal_x=direct_corridor.stop.x,
                goal_y=direct_corridor.stop.y,
                goal_z=direct_corridor.stop.z,
            )
        except (ClientNavmeshError, TypeError, ValueError):
            return None
        if not staging_corridor.complete:
            return None

    def prepend_prefix(
        proposal: StructureEgressPlan,
    ) -> StructureEgressPlan | None:
        if direct_corridor.complete:
            return proposal
        prefix_points = direct_corridor.guidance_points()
        suffix_points = proposal.approach.guidance_points()
        if (
            not prefix_points
            or not suffix_points
            or prefix_points[-1].distance_2d(suffix_points[0]) > 2.0
            or abs(prefix_points[-1].z - suffix_points[0].z) > 2.5
        ):
            return None
        combined_points = list(prefix_points)
        for point in suffix_points:
            if (
                combined_points[-1].distance_2d(point) > 0.01
                or abs(combined_points[-1].z - point.z) > 0.01
            ):
                combined_points.append(point)
        combined_approach = replace(
            proposal.approach,
            start=direct_corridor.start,
            points=tuple(combined_points),
            polygons=(),
            portals=(),
            source="client_asset_navmesh_composite",
            start_awareness=direct_corridor.start_awareness,
            awareness_observed_monotonic_s=(
                direct_corridor.awareness_observed_monotonic_s
            ),
        )
        return replace(proposal, approach=combined_approach)

    stop_index = min(
        len(goals),
        goal_index + 1 + maximum_goal_lookahead,
    )
    for candidate_index in range(
        goal_index if not direct_corridor.complete else goal_index + 1,
        stop_index,
    ):
        candidate_goal = goals[candidate_index]
        try:
            candidate_corridor = engine.plan(
                start=staging_corridor.start,
                goal_x=candidate_goal.x,
                goal_y=candidate_goal.y,
            )
        except ClientNavmeshError:
            continue
        proposal = _verified_structure_egress_plan(
            engine=engine,
            direct_corridor=candidate_corridor,
            goal_x=candidate_goal.x,
            goal_y=candidate_goal.y,
            observed_monotonic_s=observed_monotonic_s,
            excluded_opening_ids=excluded_opening_ids,
        )
        if proposal is not None:
            proposal = prepend_prefix(proposal)
            if proposal is not None:
                return candidate_index, proposal
    return None


def _structure_egress_action(
    proposal: StructureEgressPlan,
    *,
    deferred_goal: tuple[float, float],
    graph_id: str | None,
    graph_content_sha256: str | None,
) -> dict[str, object]:
    return {
        "kind": "STRUCTURE_EGRESS_PLANNED",
        "structure_id": proposal.structure_id,
        "opening_id": proposal.opening_id,
        "opening_world": [
            proposal.opening.x,
            proposal.opening.y,
            proposal.opening.z,
        ],
        "exit_anchor_world": [
            proposal.movement_target.x,
            proposal.movement_target.y,
            proposal.movement_target.z,
        ],
        "deferred_goal_world": list(deferred_goal),
        "direct_frontier_remaining_yards": (proposal.direct_frontier_remaining_yards),
        "continuation_frontier_remaining_yards": (
            proposal.continuation_frontier_remaining_yards
        ),
        "continuation_complete": proposal.continuation.complete,
        "graph_id": graph_id,
        "graph_content_sha256": graph_content_sha256,
        "knowledge_source": "standalone_worldpack_structure_access_graph",
        "route_revalidation": "active_client_asset_navmesh",
        "execution_authority": False,
    }


def _corridor_forward_bearing(
    corridor: NavCorridor,
    *,
    world_x: float,
    world_y: float,
    lookahead_world: float = SEMANTIC_HANDOFF_LOOKAHEAD_WORLD,
) -> tuple[float, float] | None:
    """Return cross-track error and forward bearing on a prepared corridor.

    A rolling Detour query is planned before the actor reaches its shared road
    point.  This projection verifies that the eventual live pose is actually
    on that same leg and looks forward along it, rather than accepting a
    topologically valid route that would demand an abrupt camera reversal.
    """

    points = corridor.guidance_points()
    if len(points) < 2 or not isfinite(lookahead_world) or lookahead_world <= 0:
        return None
    best_distance = float("inf")
    best_progress = 0.0
    cumulative = 0.0
    for start, stop in zip(points, points[1:]):
        dx, dy = stop.x - start.x, stop.y - start.y
        length_squared = dx * dx + dy * dy
        if length_squared <= 1e-9:
            continue
        segment_length = length_squared**0.5
        t = max(
            0.0,
            min(
                1.0,
                ((world_x - start.x) * dx + (world_y - start.y) * dy) / length_squared,
            ),
        )
        projected_x = start.x + t * dx
        projected_y = start.y + t * dy
        distance = hypot(world_x - projected_x, world_y - projected_y)
        if distance < best_distance:
            best_distance = distance
            best_progress = cumulative + t * segment_length
        cumulative += segment_length
    if not isfinite(best_distance):
        return None
    target_progress = best_progress + lookahead_world
    cumulative = 0.0
    target = points[-1]
    for start, stop in zip(points, points[1:]):
        segment_length = start.distance_2d(stop)
        if segment_length <= 1e-9:
            continue
        if cumulative + segment_length >= target_progress:
            t = (target_progress - cumulative) / segment_length
            target = NavPoint(
                start.x + (stop.x - start.x) * t,
                start.y + (stop.y - start.y) * t,
                start.z + (stop.z - start.z) * t,
            )
            break
        cumulative += segment_length
    if hypot(target.x - world_x, target.y - world_y) <= 0.05:
        return None
    return best_distance, atan2(target.y - world_y, target.x - world_x)


def _semantic_handoff_is_continuous(
    corridor: NavCorridor,
    *,
    world_x: float,
    world_y: float,
    heading_rad: float | None,
) -> bool:
    if heading_rad is None or not isfinite(heading_rad):
        return False
    projection = _corridor_forward_bearing(
        corridor,
        world_x=world_x,
        world_y=world_y,
    )
    if projection is None:
        return False
    cross_track_world, bearing_rad = projection
    return (
        cross_track_world <= SEMANTIC_HANDOFF_MAX_CROSS_TRACK_WORLD
        and abs(_wrap_angle(bearing_rad - heading_rad))
        <= SEMANTIC_HANDOFF_MAX_HEADING_ERROR_RAD
    )


def _semantic_corridor_goal_divergence(
    corridor: NavCorridor,
    *,
    world_x: float,
    world_y: float,
    goal_x: float,
    goal_y: float,
) -> tuple[float, float, float] | None:
    """Measure whether a cached local leg initially advances toward its goal.

    This is a cache-admission check, not a global path-shape restriction. A
    fresh Detour query may still prove a required hairpin from the actor's exact
    pose; an off-centre preplan may not silently turn the actor around.
    """

    projection = _corridor_forward_bearing(
        corridor,
        world_x=world_x,
        world_y=world_y,
    )
    goal_dx = goal_x - world_x
    goal_dy = goal_y - world_y
    if projection is None or hypot(goal_dx, goal_dy) <= 0.05:
        return None
    _cross_track_world, corridor_bearing_rad = projection
    goal_bearing_rad = atan2(goal_dy, goal_dx)
    divergence_rad = abs(_wrap_angle(corridor_bearing_rad - goal_bearing_rad))
    return divergence_rad, corridor_bearing_rad, goal_bearing_rad


def _semantic_cached_corridor_advances_toward_goal(
    corridor: NavCorridor,
    *,
    world_x: float,
    world_y: float,
    goal_x: float,
    goal_y: float,
) -> bool:
    divergence = _semantic_corridor_goal_divergence(
        corridor,
        world_x=world_x,
        world_y=world_y,
        goal_x=goal_x,
        goal_y=goal_y,
    )
    return (
        divergence is not None
        and divergence[0] <= SEMANTIC_HANDOFF_MAX_GOAL_DIVERGENCE_RAD
    )


def _joined_semantic_preview_corridor(
    current: NavCorridor,
    continuation: NavCorridor,
) -> NavCorridor | None:
    """Join two proven local corridors for steering look-ahead only.

    The executable route remains the two Detour corridors.  This view lets the
    controller see the next bend before it reaches the shared semantic point,
    avoiding a sequence of point turns at bridges, gates, roads and interiors.
    It uses topology and bearings only; no location or coordinate is special.
    """

    # A partial corridor ends at a Detour frontier, not at its requested stop.
    # Joining across that frontier would visually hide an unproven topology
    # gap and also violate NavCorridor's evidence contract.  Let the ordinary
    # partial-frontier replanner advance it instead; preview joins are only
    # allowed when both legs are independently complete.
    if not current.complete or not continuation.complete:
        return None
    current_points = current.guidance_points()
    next_points = continuation.guidance_points()
    if len(current_points) < 2 or len(next_points) < 2:
        return None
    if current_points[-1].distance_2d(next_points[0]) > 1.5:
        return None
    incoming = atan2(
        current_points[-1].y - current_points[-2].y,
        current_points[-1].x - current_points[-2].x,
    )
    outgoing = atan2(
        next_points[1].y - next_points[0].y,
        next_points[1].x - next_points[0].x,
    )
    if abs(_wrap_angle(outgoing - incoming)) >= (
        PredictiveSteeringController.OPEN_GROUND_PIVOT_THRESHOLD_RAD
    ):
        return None
    if _continuation_revisits_current_surface(
        current_points=current_points,
        continuation_points=next_points,
    ):
        return None
    joined_points = current_points + (
        next_points[1:]
        if current_points[-1].distance_2d(next_points[0]) <= 0.05
        else next_points
    )
    return replace(
        current,
        stop=continuation.stop,
        points=joined_points,
        requested_stop=None,
        source=f"{current.source}+rolling_semantic_preview",
    )


def _continuation_revisits_current_surface(
    *,
    current_points: tuple[NavPoint, ...],
    continuation_points: tuple[NavPoint, ...],
    revisit_radius_world: float = 1.0,
    floor_tolerance_world: float = 0.85,
) -> bool:
    """Reject a look-ahead join that folds back over the completed surface.

    Adjacent samples around the shared endpoint are deliberately excluded.
    Returning over an earlier point on another height remains legal because
    stairs, bridges and stacked WMO floors can overlap in XY.  The rule is
    entirely geometric and therefore applies to every map and structure.
    """

    if len(current_points) < 3 or len(continuation_points) < 3:
        return False
    earlier_surface = current_points[:-2]
    future_surface = continuation_points[2:]
    return any(
        earlier.distance_2d(future) <= revisit_radius_world
        and abs(earlier.z - future.z) <= floor_tolerance_world
        for earlier in earlier_surface
        for future in future_surface
    )


def _recovery_budget_can_reset(
    *,
    world_x: float,
    world_y: float,
    last_collision_world: tuple[float, float] | None,
) -> bool:
    return (
        last_collision_world is not None
        and hypot(
            world_x - last_collision_world[0],
            world_y - last_collision_world[1],
        )
        >= RECOVERY_BUDGET_RESET_DISTANCE_WORLD
    )


def _semantic_destination_reached(
    *,
    world_x: float,
    world_y: float,
    destination_x: float,
    destination_y: float,
    radius_world: float | None,
) -> bool:
    """Honor the destination catalog's semantic arrival radius.

    A settlement is an area, not a single mathematically exact coordinate.
    This prevents a successful journey from continuing into an unnecessary
    local manoeuvre merely to touch the catalog marker at its centre.
    """

    values = (world_x, world_y, destination_x, destination_y)
    if any(not isfinite(value) for value in values):
        raise ValueError("semantic destination position is invalid")
    if radius_world is None:
        return False
    if not isfinite(radius_world) or radius_world <= 0.0:
        raise ValueError("semantic destination radius is invalid")
    return (
        hypot(
            destination_x - world_x,
            destination_y - world_y,
        )
        <= radius_world
    )


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _navmesh_map_sha256(nav_root: Path, *, map_name: str) -> str:
    nav_directory = nav_root.resolve() / "Nav" / map_name
    files = sorted(nav_directory.glob("*.nav"), key=lambda item: item.name)
    if not files:
        raise RuntimeError("navmesh map has no immutable ADT tiles")
    digest = hashlib.sha256()
    for path in files:
        encoded_name = path.name.encode("ascii", "strict")
        digest.update(len(encoded_name).to_bytes(2, "little"))
        digest.update(encoded_name)
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest().upper()


def _probe(
    *,
    receipt: dict[str, object],
    authorization: Path,
    session_id: str,
    expected_zone_index: int,
) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(HUD_PROBE),
            "--backend",
            "dxgi",
            "--window-pid",
            str(receipt["pid"]),
            "--window-hwnd",
            str(receipt["hwnd"]),
            "--window-title-exact",
            str(receipt["window_title"]),
            "--window-class-exact",
            str(receipt["window_class"]),
            "--session-id",
            session_id,
            "--observation-id",
            f"nav:{uuid4()}",
            "--samples",
            "1",
            "--client-build",
            str(receipt["client_build"]),
            "--authorization-file",
            str(authorization),
            "--client-executable",
            str(receipt["executable_path"]),
            "--lab-launch-receipt",
            str(DEFAULT_RECEIPT),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=3.0,
        check=False,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode != 0 or not lines:
        raise RuntimeError("coordinate HUD probe failed closed")
    record = json.loads(lines[-1])
    position = record.get("position")
    if (
        record.get("tracking_state") != "VALID"
        or record.get("map_position_available") is not True
        or not isinstance(position, dict)
        or position.get("continent_index") != 2
        or position.get("zone_index") != expected_zone_index
    ):
        raise RuntimeError("coordinate HUD does not expose the exact Tirisfal position")
    return record


def _position(
    observation: dict[str, object],
    *,
    expected_zone_index: int,
    transform: WorldMapZoneTransform | None = None,
    expected_map_id: int = 0,
) -> tuple[float, float, float, float]:
    position = observation["position"]
    assert isinstance(position, dict)
    normalized_x = float(position["x"])
    normalized_y = float(position["y"])
    resolved_transform = transform or _load_zone_transform(
        DEFAULT_ZONE_TRANSFORM_CATALOG,
        map_id=expected_map_id,
        zone_index=expected_zone_index,
    )
    world_x, world_y = resolved_transform.world_from_normalized(
        normalized_x, normalized_y
    )
    return normalized_x, normalized_y, world_x, world_y


def _player_facing(observation: dict[str, object]) -> float | None:
    position = observation.get("position")
    if not isinstance(position, dict) or "facing_rad" not in position:
        return None
    facing = float(position["facing_rad"])
    if not isfinite(facing) or not 0.0 <= facing <= 2 * pi:
        raise RuntimeError("coordinate HUD player facing is invalid")
    return 0.0 if facing == 2 * pi else facing


def _exact_body_yaw_observation(
    observation: dict[str, object],
    *,
    client_facing_source: str,
) -> float | None:
    """Keep the raw body channel separate from the minimap camera estimate.

    ``position.facing_rad`` is exact body-facing only when the coordinate HUD
    supplied it.  The runner may add a minimap-derived facing value to the
    same position object for bounded steering, but that value is a camera
    estimate and must never be recorded as body yaw.
    """

    if client_facing_source != EXACT_BODY_HEADING_SOURCE:
        return None
    return _player_facing(observation)


def _body_yaw_observation(
    observation: dict[str, object],
    *,
    client_facing_source: str,
) -> float | None:
    """Return a labelled body-yaw observation without overstating precision.

    The 2.4.3 client predates ``GetPlayerFacing``.  Its north-up minimap player
    arrow still depicts character facing, not camera facing, so the calibrated
    visual adapter is usable as a bounded body-yaw observation.  The source
    label remains ``MINIMAP_VISION_FALLBACK``; only the HUD API path is exact.
    """

    if client_facing_source not in {
        EXACT_BODY_HEADING_SOURCE,
        MINIMAP_BODY_HEADING_SOURCE,
    }:
        return None
    return _player_facing(observation)


def _body_camera_yaw_delta(
    body_yaw_observation_rad: float | None,
    camera_yaw_estimate_rad: float | None,
) -> float | None:
    """Compare exact body-facing evidence with the control-camera estimate.

    ``body_yaw_observation_rad`` is populated only by the exact coordinate HUD
    channel.  A minimap value can still be recorded as ``player_facing_rad``
    and used by the bounded heading fusion, but it is not a body/camera
    separation measurement.  ``camera_yaw_estimate_rad`` is the bounded
    mouse-integrated heading used by the controller, never a direct camera
    read or server truth.
    """

    if body_yaw_observation_rad is None or camera_yaw_estimate_rad is None:
        return None
    if any(
        not isfinite(float(value))
        for value in (body_yaw_observation_rad, camera_yaw_estimate_rad)
    ):
        raise RuntimeError("body/camera yaw evidence is not finite")
    return abs(
        _wrap_angle(
            float(body_yaw_observation_rad) - float(camera_yaw_estimate_rad)
        )
    )


def _hot_target_matches_target(
    snapshot: object,
    target: WindowsInputTargetBinding,
) -> bool:
    """Compare the metadata-only hot snapshot with the exact input target."""

    return isinstance(snapshot, WindowsHotTargetSnapshot) and bool(
        snapshot.hwnd == target.hwnd
        and snapshot.foreground_hwnd == target.hwnd
        and snapshot.owner_pid == target.pid
        and snapshot.process_creation_time_100ns
        == target.process_creation_time_100ns
        and snapshot.process_alive
        and snapshot.visible
        and not snapshot.minimized
    )


def _select_initial_vertical_layer(
    engine: MovementEngine,
    *,
    start_x: float,
    start_y: float,
    seed_z: float,
    goal_x: float,
    goal_y: float,
) -> tuple[float, NavCorridor, tuple[dict[str, object], ...]]:
    """Resolve stacked floors from topology instead of one arbitrary Z hint.

    The client HUD supplies exact XY but legacy TBC exposes no portable player
    altitude.  Detour does expose how many walkable heights exist at that XY.
    Probe bounded offsets around the first resolved surface, deduplicate the
    returned layers, and prefer a complete corridor on the locally matching
    surface before comparing route stretch toward the already-selected semantic
    goal.  No map name, structure, or coordinate is encoded here.
    """

    offsets = (0.0, 32.0, -32.0, 64.0, -64.0, 128.0, -128.0, 256.0, -256.0)
    candidates: dict[int, NavCorridor] = {}
    expected_count = 1
    for offset in offsets:
        try:
            corridor = engine.plan(
                start=NavPoint(start_x, start_y, seed_z + offset),
                goal_x=goal_x,
                goal_y=goal_y,
            )
        except ClientNavmeshError:
            # A guessed Z can legitimately land outside every polygon.  The
            # next bounded layer probe may still resolve the actor's floor;
            # one failed probe must not abort the whole read-only preflight.
            continue
        expected_count = max(expected_count, corridor.height_candidate_count)
        candidates.setdefault(round(corridor.start.z * 100), corridor)
        if len(candidates) >= expected_count:
            break

    if not candidates:
        raise ClientNavmeshError(
            "no walkable vertical layer was found at the observed client position"
        )

    def score(corridor: NavCorridor) -> tuple[float, float, float, float, int, float]:
        points = corridor.guidance_points()
        distance = sum(
            first.distance_2d(second) for first, second in zip(points, points[1:])
        )
        direct = max(0.01, corridor.start.distance_2d(corridor.stop))
        awareness = corridor.start_awareness
        # A stacked WMO/ground query can return a short, complete route on a
        # roof or exterior surface even while the actor is inside a building.
        # Preserve the surface that matches the locally observed enclosure;
        # route length must not override the actor's current topological layer.
        interior_mismatch = 0.5
        if awareness is not None:
            interior_mismatch = 0.0 if (
                "wmo" in awareness.physical_surfaces
                or not awareness.overhead_clear
            ) else 1.0
        height_delta = abs(corridor.start.z - seed_z)
        # A complete corridor on a different stacked surface is not useful:
        # it can steer a player who is visibly inside a WMO onto an exterior
        # floor. Local client-visible surface evidence wins before
        # completeness; a partial corridor on the current surface can still
        # be advanced by the verified egress/frontier path.
        return (
            interior_mismatch,
            0.0 if corridor.complete else 1.0,
            height_delta,
            distance / direct,
            len(corridor.polygons),
            distance,
        )

    selected = min(candidates.values(), key=score)
    evidence = tuple(
        {
            "resolved_z": corridor.start.z,
            "complete": corridor.complete,
            "guidance_point_count": len(corridor.guidance_points()),
            "polygon_count": len(corridor.polygons),
            "score": list(score(corridor)),
        }
        for corridor in sorted(candidates.values(), key=lambda item: item.start.z)
    )
    return selected.start.z, selected, evidence


def _observe_player_heading(
    pose_source: MovementObservationPort,
    observer: VisibleHeadingObserver,
    *,
    predicted_heading_rad: float | None,
    observation: dict[str, object],
    displacement_heading_rad: float | None = None,
    allow_displacement_fusion: bool = False,
) -> tuple[float | None, str]:
    """Use exact HUD facing directly; otherwise use bounded visual fusion.

    The verified older run used ``VISIBLE_CLIENT_HEADING_FUSED``: the
    mouse-integrated yaw supplied the continuous prediction and the visible
    minimap marker closed drift with a small correction.  A later conservative
    branch bypassed that observer and returned
    ``MOUSE_INTEGRATED_MINIMAP_FALLBACK`` on every minimap frame.  That removed
    the correction which had made the older Crypt egress work.

    ``VisibleHeadingObserver`` resolves the minimap's two-ended PCA axis
    against the continuous prediction and bounds the correction.  A
    displacement chord is retained as calibration/diagnostic evidence by the
    caller, but it never overrides this heading here: a character can slide
    sideways along a wall while still facing the wall.
    """

    visible_heading = _player_facing(observation)
    if (
        visible_heading is not None
        and pose_source.latest_facing_source == EXACT_BODY_HEADING_SOURCE
    ):
        return visible_heading, EXACT_BODY_HEADING_SOURCE
    if (
        visible_heading is not None
        and pose_source.latest_facing_source == "MINIMAP_VISION_FALLBACK"
    ):
        # The caller supplies displacement only while W is producing
        # continuous, corridor-consistent motion with no collision evidence.
        # In that bounded state the chord is the best available body-yaw
        # witness on TBC 2.4.3; the minimap remains the absolute low-frequency
        # reference.  During a wall slide the caller passes None, so collision
        # tangent can never masquerade as facing.
        return observer.observe(
            predicted_heading_rad=predicted_heading_rad,
            visible_heading_rad=visible_heading,
            displacement_heading_rad=(
                displacement_heading_rad if allow_displacement_fusion else None
            ),
        )
    return observer.observe(
        predicted_heading_rad=predicted_heading_rad,
        visible_heading_rad=visible_heading,
        displacement_heading_rad=displacement_heading_rad,
    )


def _require_exact_body_heading(
    observation: dict[str, object],
    *,
    heading: float | None,
    heading_source: str,
    phase: str,
) -> None:
    """Fail closed unless this frame proves body yaw through the HUD contract.

    TBC 2.4.3 can publish exact normalized X/Y through the observer HUD, but
    its legacy API does not normally publish ``GetPlayerFacing``.  A minimap
    axis, mouse integration, or displacement chord is therefore an estimate,
    not an exact combat-ready body orientation.  This opt-in gate prevents a
    caller from accidentally treating any of those fallbacks as exact.
    """

    position = observation.get("position")
    if (
        observation.get("tracking_state") != "VALID"
        or not isinstance(position, dict)
        or not isinstance(position.get("x"), (int, float))
        or isinstance(position.get("x"), bool)
        or not isinstance(position.get("y"), (int, float))
        or isinstance(position.get("y"), bool)
        or not isinstance(position.get("facing_rad"), (int, float))
        or isinstance(position.get("facing_rad"), bool)
        or heading is None
        or heading_source != EXACT_BODY_HEADING_SOURCE
    ):
        raise RuntimeError(
            "exact visible body pose unavailable at "
            f"{phase}; refusing movement/combat orientation claim"
        )
    body_yaw = float(position["facing_rad"])
    # Do not let a caller combine an exact HUD witness with a different
    # preserved, camera-integrated, or otherwise stale heading. Both values
    # must describe the same body orientation before movement or combat may
    # proceed in strict mode.
    disagreement = abs(_wrap_angle(body_yaw - float(heading)))
    if disagreement > MAX_EXACT_BODY_HEADING_DISAGREEMENT_RAD:
        raise RuntimeError(
            "exact visible body heading disagrees with controller heading at "
            f"{phase} by {disagreement:.6f} rad"
        )


def _acquire_initial_visible_heading(
    pose_source: MovementObservationPort,
    observer: VisibleHeadingObserver,
    *,
    observation: dict[str, object],
    predicted_heading_rad: float | None,
    max_attempts: int = INITIAL_HEADING_REACQUISITION_ATTEMPTS,
    previous_heading_rad: float | None = None,
    previous_heading_source: str | None = None,
    preserve_previous_exact: bool = False,
    require_exact_body_heading: bool = False,
) -> tuple[dict[str, object], float, str, int]:
    """Acquire a fresh visible heading before any locomotion input.

    A missing facing value is a temporary observation limitation, not a
    steering instruction.  The old path allowed this state to reach the
    controller, which intentionally sent one natural forward stride and then
    inferred yaw from displacement.  At a semantic handoff that stride can be
    in the wrong direction (as the Brill return trace demonstrated).  Retry
    only read-only observations while no controls are held; if no heading
    exists and exact HUD or the bounded minimap fallback never supplies one,
    fail closed.  When strict body heading is requested, a minimap estimate is
    never returned as the initial result; it is only a reason to retry a fresh
    read-only frame.  A previously proven heading is preserved through a
    single post-plan refresh even when that refresh omits the facing field.
    """

    if type(max_attempts) is not int or not 1 <= max_attempts <= 8:
        raise ValueError("initial heading reacquisition bound is invalid")
    if type(preserve_previous_exact) is not bool:
        raise ValueError("preserve_previous_exact must be boolean")
    if type(require_exact_body_heading) is not bool:
        raise ValueError("require_exact_body_heading must be boolean")
    if previous_heading_rad is not None and (
        not isinstance(previous_heading_rad, (int, float))
        or isinstance(previous_heading_rad, bool)
        or not isfinite(float(previous_heading_rad))
    ):
        raise ValueError("previous heading is invalid")
    if preserve_previous_exact and (
        previous_heading_rad is None
        or previous_heading_source != EXACT_BODY_HEADING_SOURCE
    ):
        raise ValueError(
            "preserved exact heading requires a previous exact body heading"
        )
    current = observation
    for attempt in range(1, max_attempts + 1):
        heading, source = _observe_player_heading(
            pose_source,
            observer,
            predicted_heading_rad=predicted_heading_rad,
            observation=current,
            displacement_heading_rad=None,
        )
        # Route planning does not send input, so a previously exact body yaw
        # remains valid for this single post-plan refresh. Do not silently
        # replace it with a missing/noisy minimap or mouse-only estimate; the
        # caller records the preserved status and can still require a fresh
        # exact proof when that policy is enabled.
        if (
            preserve_previous_exact
            and previous_heading_rad is not None
            and previous_heading_source == EXACT_BODY_HEADING_SOURCE
            and pose_source.latest_facing_source != EXACT_BODY_HEADING_SOURCE
        ):
            return (
                current,
                float(previous_heading_rad),
                PRESERVED_EXACT_BODY_HEADING_SOURCE,
                attempt,
            )
        # A minimap or mouse estimate is useful after a proven exact heading,
        # but it cannot satisfy the strict startup contract.  Wait for a new
        # HUD witness while no controls are held; the caller's exact gate then
        # receives a coherent body pose instead of failing immediately after
        # the camera-home compositor settles.
        if require_exact_body_heading and source != EXACT_BODY_HEADING_SOURCE:
            if attempt < max_attempts:
                time.sleep(INITIAL_HEADING_REACQUISITION_INTERVAL_S)
                current = dict(pose_source.next_observation())
                continue
            raise RuntimeError(
                "exact visible body heading unavailable; refusing natural "
                "calibration stride"
            )
        if heading is not None:
            return current, heading, source, attempt
        if attempt < max_attempts:
            time.sleep(INITIAL_HEADING_REACQUISITION_INTERVAL_S)
            current = dict(pose_source.next_observation())
    raise RuntimeError(
        "initial visible heading unavailable; refusing natural calibration stride"
    )


def _corridor_direction_probe_signature(
    corridor: NavCorridor,
    *,
    goal_x: float,
    goal_y: float,
) -> tuple[object, ...]:
    """Identify one planned corridor for the first-forward direction probe."""

    points = corridor.guidance_points()
    return (
        round(float(goal_x), 3),
        round(float(goal_y), 3),
        tuple(
            (round(point.x, 3), round(point.y, 3), round(point.z, 3))
            for point in points
        ),
    )


def _corridor_initial_direction(
    corridor: NavCorridor,
    *,
    fallback: float | None = None,
) -> float | None:
    """Return the first non-zero client-navmesh tangent, if one exists."""

    points = corridor.guidance_points()
    for start, stop in zip(points, points[1:]):
        if start.distance_2d(stop) > 1.0e-6:
            return _wrap_angle(atan2(stop.y - start.y, stop.x - start.x))
    return fallback


def _orient_initial_fallback_heading_to_corridor(
    heading: float | None,
    *,
    heading_source: str,
    corridor: NavCorridor,
) -> tuple[float | None, str, bool]:
    """Detect a visual fallback's two possible directions before the first W.

    The legacy minimap marker is a tiny principal axis.  Its arrow can be
    returned at either end of that axis while the actor is stationary.  If the
    current fallback heading is almost opposite the first client-navmesh
    tangent, report the ambiguity but preserve the observed physical end.  A
    route tangent cannot rotate the avatar by changing a number in memory; the
    ordinary RMB controller must perform that turn and the first displacement
    probe must verify it. Exact coordinate-HUD facing is never replaced.
    """

    if heading is None or heading_source not in VISUAL_FALLBACK_HEADING_SOURCES:
        return heading, heading_source, False
    tangent = _corridor_initial_direction(corridor)
    if tangent is None:
        return heading, heading_source, False
    direct_error = abs(_wrap_angle(tangent - heading))
    flipped_heading = _wrap_angle(heading + pi)
    flipped_error = abs(_wrap_angle(tangent - flipped_heading))
    # Require a clear axial ambiguity: a normal 90-120 degree route bend must
    # still be handled by the ordinary stationary pivot controller.
    if direct_error < 2.20 or flipped_error > 0.85:
        return heading, heading_source, False
    # Keep the genuine, current visual provenance.  The ambiguity is a
    # separate planning fact, not a loss of heading evidence.  Replacing the
    # source label made the fail-closed preflight reject the frame before the
    # ordinary controller could perform its RMB-only stationary pivot.
    return heading, heading_source, True


def _minimap_heading_is_fallback_only(
    position: dict[str, object],
    marker: object,
) -> bool:
    """Never replace the exact addon facing with minimap image inference.

    The coordinate HUD carries ``GetPlayerFacing()`` quantized over sixteen
    bits. The neutral-MDX marker remains useful when that API value is truly
    unavailable, but its few rendered pixels are too noisy for an RMB servo.
    Replacing the exact value caused the live Deathknell left/right balance.
    """

    return bool(
        "facing_rad" not in position
        and isinstance(marker, dict)
        and marker.get("orientation_deg_screen") is not None
        and marker.get("detection_model") == "neutral_mdx"
    )


def _heading_from_calibration(path: Path) -> tuple[float, float]:
    record = _read_json(path)
    if record.get("status") != "PROVEN_DISPLACEMENT":
        raise RuntimeError("heading calibration did not prove displacement")
    pre = record.get("pre_observation")
    post = record.get("post_observation")
    if not isinstance(pre, dict) or not isinstance(post, dict):
        raise RuntimeError("heading calibration observations are missing")
    transform = tbc243_zone_transform(2, 25)
    before = transform.world_from_normalized(float(pre["x"]), float(pre["y"]))
    after = transform.world_from_normalized(float(post["x"]), float(post["y"]))
    dx, dy = after[0] - before[0], after[1] - before[1]
    distance = hypot(dx, dy)
    if distance <= 0.25:
        raise RuntimeError("heading calibration displacement is too small")
    return atan2(dy, dx), distance / 0.1


def _latest_calibration(
    result_root: Path = ROOT / "data" / "runtime" / "movement-f3a" / "results",
) -> Path:
    candidates = sorted(
        result_root.glob("single-forward-pulse-*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        try:
            if _read_json(candidate).get("status") == "PROVEN_DISPLACEMENT":
                return candidate
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
    raise RuntimeError("no proven heading calibration result exists")


def _resume_heading(path: Path) -> tuple[tuple[float, float], float]:
    record = _read_json(path)
    final_world = record.get("final_world")
    actions = record.get("actions")
    if (
        record.get("record_type") != "navmesh_roaming_result"
        or not isinstance(final_world, list)
        or len(final_world) != 2
        or not isinstance(actions, list)
    ):
        raise RuntimeError("resume result is not an exact navmesh roaming result")
    heading: float | None = None
    previous_position: tuple[float, float] | None = None
    for action in actions:
        if not isinstance(action, dict):
            raise RuntimeError("resume result contains a malformed action")
        kind = action.get("kind")
        if kind == "MOUSE_TURN" and heading is not None:
            heading -= (
                int(action["delta_x"])
                * PredictiveSteeringController.MOUSE_YAW_RAD_PER_PIXEL
            )
        elif kind in {"FORWARD", "STUCK_RECOVERY", "CONTINUOUS_FRAME"}:
            current = (float(action["world_x"]), float(action["world_y"]))
            if (
                kind in {"FORWARD", "CONTINUOUS_FRAME"}
                and previous_position is not None
                and float(action["progress_world"])
                > (0.08 if kind == "CONTINUOUS_FRAME" else 0.35)
            ):
                heading = atan2(
                    current[1] - previous_position[1],
                    current[0] - previous_position[0],
                )
            previous_position = current
    if heading is None:
        raise RuntimeError("resume result does not prove a current camera heading")
    return (float(final_world[0]), float(final_world[1])), heading


def _resume_position(path: Path) -> tuple[float, float]:
    record = _read_json(path)
    final_world = record.get("final_world")
    actions = record.get("actions")
    if (
        record.get("record_type") != "navmesh_roaming_result"
        or not isinstance(final_world, list)
        or len(final_world) != 2
        or not isinstance(actions, list)
    ):
        raise RuntimeError("resume result is not an exact navmesh roaming result")
    return float(final_world[0]), float(final_world[1])


def _resume_z_hint(path: Path, *, fallback: float) -> float:
    record = _read_json(path)
    value = record.get("final_world_z_hint")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return float(fallback)
    result = float(value)
    if not isfinite(result) or not -500.0 <= result <= 5000.0:
        raise RuntimeError("resume result contains an invalid navmesh height hint")
    return result


def _resume_observed_blocker(
    path: Path,
    *,
    goal_x: float,
    goal_y: float,
) -> tuple[tuple[float, float, float, float], ...]:
    stuck_statuses = {"STUCK_REPLAN_REQUIRED", "PARTIAL_CORRIDOR_FRONTIER_STUCK"}
    record = _read_json(path)
    if record.get("status") not in stuck_statuses:
        return ()
    prior_blockers = record.get("observed_blockers")
    if isinstance(prior_blockers, list):
        parsed = tuple(
            (float(item[0]), float(item[1]), float(item[2]), float(item[3]))
            for item in prior_blockers
            if isinstance(item, list) and len(item) == 4
        )
        if parsed:
            return parsed[-8:]
    x, y = _resume_position(path)
    heading = None
    actions = record.get("actions")
    if isinstance(actions, list):
        for action in reversed(actions):
            if not isinstance(action, dict):
                continue
            value = action.get("player_facing_rad")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                heading = float(value)
                break
    if heading is None:
        heading = atan2(goal_y - y, goal_x - x)
    z = _resume_z_hint(path, fallback=100.0)
    # The collision surface is one player-radius ahead. Excluding a 24-yard
    # region here used to destroy legitimate gate/road alternatives; one local
    # capsule is sufficient evidence and keeps the start polygon usable.
    return ((x + cos(heading) * 1.25, y + sin(heading) * 1.25, z, 1.5),)


def _budget(
    clock: SystemMonotonicClock, hold_ms: int, envelope_ms: int
) -> SinkExecutionBudget:
    started = clock.now_ms()
    return SinkExecutionBudget(
        clock_id=clock.clock_id,
        started_at_monotonic_ms=started,
        absolute_deadline_monotonic_ms=started + envelope_ms,
        remaining_ms=float(envelope_ms),
        hold_duration_ms=hold_ms,
        max_execution_envelope_ms=envelope_ms,
    )


def _apply_navigation_camera_profile(
    backend: CtypesWin32KeyboardBackend,
    *,
    view_index: int,
    smart_pivot: bool = False,
) -> None:
    """Restore the operator-reviewed native camera view without rebuilding it."""
    backend.send_stand_command()
    time.sleep(0.100)
    backend.send_camera_home_command(
        view_index=view_index,
        smart_pivot=smart_pivot,
    )
    time.sleep(0.150)


def _apply_camera_pivot_intent(
    backend: CtypesWin32KeyboardBackend,
    intent: CameraPivotIntent,
    *,
    hwnd: int,
) -> None:
    """Apply one debounced scene transition while no motion key is held."""

    backend.send_camera_pivot_profile(
        camera_distance_max_factor=intent.camera_distance_max_factor,
        # Smart Pivot can lift the 2.4.3 camera into an interior ceiling.
        smart_pivot=False,
    )
    time.sleep(0.100)


class _PreflightMotionRelease:
    """Release-only placeholder used before the short F4a arm is bound.

    Route planning and camera recovery may need a safe ``release_all`` callback,
    but they must not have an actuator before the read-only preflight is done.
    The real gateway replaces this object immediately before the control loop.
    """

    held_controls: tuple[str, ...] = ()
    mouse_look_held = False

    def release_all(self) -> None:
        return None

    def apply_frame(
        self,
        frame: ContinuousMotionFrame,
        cancellation: CooperativeCancellation,
    ) -> None:
        raise RuntimeError(
            "continuous motion was requested before the F4a runtime arm was bound"
        )

    def revoke(self) -> None:
        return None

    def close(self) -> None:
        return None


def _load_runtime_motion_authority_after_preflight(
    *,
    arm_file: Path,
    authorization_raw: bytes,
    session_receipt_raw: bytes,
    realm_revalidation_file: Path,
    target: WindowsInputTargetBinding,
    clock: SystemMonotonicClock,
    schema_path: Path,
    authorization_schema_path: Path,
    wait_seconds: float,
) -> ContinuousMotionAuthority:
    """Bind F4a after read-only planning, optionally waiting for a fresh arm.

    The issuer remains separate: this helper only retries validation.  It never
    creates, renews, or broadens authority.  A zero timeout keeps the original
    fail-closed behavior; a positive bounded timeout lets the operator replace
    an expired arm after the runner prints its preflight-ready marker.
    """

    deadline = time.monotonic() + wait_seconds
    announced_wait = False
    last_error: Exception | None = None
    while True:
        try:
            return load_continuous_motion_authority(
                arm_file.read_bytes(),
                authorization_raw=authorization_raw,
                session_receipt_raw=session_receipt_raw,
                realm_revalidation_raw=realm_revalidation_file.read_bytes(),
                target=target,
                clock=clock,
                schema_path=schema_path,
                authorization_schema_path=authorization_schema_path,
            )
        except (OSError, ValueError, TypeError, KeyError) as error:
            last_error = error
            if wait_seconds <= 0.0 or time.monotonic() >= deadline:
                raise
            if not announced_wait:
                print(
                    json.dumps(
                        {
                            "record_type": "continuous_motion_arm_wait",
                            "schema_version": "0.1",
                            "status": "WAITING_FOR_FRESH_F4A_ARM",
                            "wait_seconds": wait_seconds,
                            "reason": "preflight_completed_but_current_arm_is_not_valid",
                            "execution_authority": False,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                announced_wait = True
            time.sleep(min(0.250, max(0.025, deadline - time.monotonic())))
    # The loop either returns or raises.  Keep a defensive error for static
    # analyzers if the control flow is ever changed.
    raise RuntimeError(f"continuous motion arm could not be loaded: {last_error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Follow one client-asset Detour corridor with closed-loop visible pose feedback."
    )
    parser.add_argument("--session-authorization-file", type=Path, required=True)
    parser.add_argument(
        "--continuous-motion-authorization-file",
        type=Path,
        help=(
            "approved F4a movement authorization; fixed-UI authorization is "
            "never upgraded into movement"
        ),
    )
    parser.add_argument(
        "--continuous-motion-arm-file",
        type=Path,
        help="short-lived F4a runtime arm issued for this exact client process",
    )
    parser.add_argument(
        "--continuous-motion-revalidation-file",
        type=Path,
        help="fresh realm binding used when the F4a arm was issued",
    )
    parser.add_argument(
        "--runtime-arm-wait-seconds",
        type=float,
        default=0.0,
        help=(
            "bounded wait after read-only preflight for the operator to replace "
            "an expired F4a arm; zero keeps immediate fail-closed behavior"
        ),
    )
    parser.add_argument("--session-receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--worker", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--structure-probe-worker", type=Path,
                        help="Exact producer artifact for the immutable structure graph; defaults to --worker")
    parser.add_argument(
        "--world-pack-profile", type=Path, default=DEFAULT_WORLD_PACK_PROFILE
    )
    parser.add_argument(
        "--world-pack-store", type=Path, default=DEFAULT_WORLD_PACK_STORE
    )
    parser.add_argument(
        "--world-structure-index",
        type=Path,
        default=DEFAULT_WORLD_STRUCTURE_INDEX,
    )
    parser.add_argument(
        "--structure-access-graph",
        type=Path,
        default=DEFAULT_STRUCTURE_ACCESS_GRAPH,
    )
    parser.add_argument(
        "--skip-structure-awareness",
        action="store_true",
        help=(
            "bounded diagnostic slice: skip the expensive local structure/egress "
            "scan; direct navmesh steering remains active"
        ),
    )
    parser.add_argument(
        "--legacy-loose-nav-assets",
        action="store_true",
        help="explicit rollback only: use loose map/nav/catalog paths",
    )
    parser.add_argument("--nav-root", type=Path)
    parser.add_argument("--world-catalog", type=Path)
    parser.add_argument(
        "--world-catalog-asset",
        type=Path,
    )
    parser.add_argument("--nav-profile-id", default=DEFAULT_NAV_PROFILE_ID)
    parser.add_argument("--map-id", type=int, default=0)
    parser.add_argument("--goal-normalized-x", type=float)
    parser.add_argument("--goal-normalized-y", type=float)
    parser.add_argument("--semantic-destination-id")
    parser.add_argument(
        "--leveling-plan-file", type=Path,
        help="read-only RouteTeacher leveling plan attached to this navigation leg",
    )
    parser.add_argument(
        "--semantic-catalog", type=Path, default=DEFAULT_SEMANTIC_CATALOG
    )
    parser.add_argument("--road-semantic-root", type=Path)
    parser.add_argument(
        "--operator-path",
        type=Path,
        help="ordered external-tool route; every leg is still validated by Detour",
    )
    parser.add_argument(
        "--expected-zone-index", type=int, choices=range(0, 65_536), default=25,
        help="client WorldMapArea ID resolved through the immutable transform catalog",
    )
    parser.add_argument(
        "--zone-transform-catalog", type=Path,
        default=DEFAULT_ZONE_TRANSFORM_CATALOG,
        help="hash-pinned client WorldMapArea transform catalog",
    )
    parser.add_argument("--start-world-z-hint", type=float, default=100.0)
    parser.add_argument("--resume-result", type=Path)
    parser.add_argument(
        "--learned-obstacle-memory",
        type=Path,
        default=LEARNED_OBSTACLE_MEMORY,
    )
    parser.add_argument(
        "--recovery-strategy-memory",
        type=Path,
        default=RECOVERY_STRATEGY_MEMORY,
        help=(
            "bounded client-observed memory of repeated recovery strategy "
            "failures; it never grants execution authority"
        ),
    )
    parser.add_argument(
        "--traversed-surface-prior",
        type=Path,
        default=DEFAULT_TRAVERSED_SURFACE_PRIOR,
        help=(
            "operator recording used only as validated local evidence; it never "
            "provides executable waypoints"
        ),
    )
    parser.add_argument("--dismiss-ui-at-start", action="store_true")
    parser.add_argument("--dismiss-ui-only", action="store_true")
    parser.add_argument("--recover-camera-pitch-only", action="store_true")
    parser.add_argument("--camera-pitch-delta-y", type=int, default=120)
    parser.add_argument("--recover-camera-zoom-only", action="store_true")
    parser.add_argument("--camera-zoom-wheel-steps", type=int, default=3)
    parser.add_argument("--recover-camera-home-only", action="store_true")
    parser.add_argument("--snapshot-camera-view-only", action="store_true")
    parser.add_argument("--recover-standing-only", action="store_true")
    parser.add_argument("--camera-home-view-index", type=int, default=3)
    parser.add_argument("--camera-home-zoom-out-steps", type=int, default=1)
    parser.add_argument("--camera-home-pitch-delta-y", type=int, default=5)
    parser.add_argument("--max-forward-actions", type=int, default=18)
    parser.add_argument("--max-control-frames", type=int, default=600)
    parser.add_argument("--lookahead-world", type=float)
    parser.add_argument("--arrival-radius-world", type=float, default=2.0)
    parser.add_argument(
        "--steering-controller",
        choices=(
            "geometric_predictive_v1",
            "continuous_trajectory_v1",
            "adaptive_trajectory_v1",
            "pa_mppi_v1",
        ),
        default="geometric_predictive_v1",
    )
    parser.add_argument("--mppi-batch-size", type=int, default=1_000)
    parser.add_argument("--mppi-time-steps", type=int, default=56)
    parser.add_argument("--operator-control-file", type=Path)
    parser.add_argument("--acknowledge-navmesh-roaming", action="store_true")
    parser.add_argument("--activate-stealth", action="store_true")
    parser.add_argument("--allow-ghost-navigation", action="store_true")
    parser.add_argument(
        "--continue-through-routine-aggro",
        action="store_true",
        help=(
            "keep following the validated travel corridor while routine aggro "
            "is visible and player health remains above the travel threshold"
        ),
    )
    parser.add_argument(
        "--minimum-travel-health-fraction",
        type=float,
        default=0.55,
    )
    parser.add_argument("--require-open-search-vantage", action="store_true")
    parser.add_argument(
        "--require-player-anchor",
        action="store_true",
        help=(
            "diagnostic-only strict mode: fail closed unless the calibrated "
            "third-person player silhouette remains visible; normal navigation "
            "keeps this detector as telemetry because window size, camera and "
            "armor changes make the pixel profile non-authoritative"
        ),
    )
    parser.add_argument(
        "--require-exact-body-heading",
        action="store_true",
        help=(
            "fail closed unless the fresh coordinate HUD proves body yaw; "
            "minimap, mouse and displacement estimates are not exact"
        ),
    )
    parser.add_argument(
        "--movement-lab-state-file",
        type=Path,
        default=MOVEMENT_LAB_STATE,
    )
    parser.add_argument(
        "--dynamic-experience-store",
        type=Path,
        default=DEFAULT_DYNAMIC_EXPERIENCE_STORE,
    )
    parser.add_argument(
        "--continuity-state-file",
        type=Path,
        default=CONTINUITY_STATE,
    )
    return parser


def _default_pose_source_factory(
    *,
    authorization_file: Path,
    receipt_file: Path,
    receipt: Mapping[str, object],
    session_id: str,
    allow_ghost_navigation: bool,
    continue_through_routine_aggro: bool,
    minimum_travel_health_fraction: float,
    require_player_anchor: bool,
    on_capture_stall: Callable[[], None],
) -> MovementObservationPort:
    """Keep the current optical adapter outside the movement package."""

    return LiveCoordinatePoseSource(
        authorization_file=authorization_file,
        receipt_file=receipt_file,
        receipt=dict(receipt),
        session_id=session_id,
        allow_ghost_navigation=allow_ghost_navigation,
        continue_through_routine_aggro=continue_through_routine_aggro,
        minimum_travel_health_fraction=minimum_travel_health_fraction,
        # The calibrated pixel silhouette remains useful telemetry, but it is
        # not a stable source of movement authority across window sizes,
        # cameras, equipment and environments. Strict diagnostic runs can opt
        # into it explicitly.
        require_player_anchor=require_player_anchor,
        on_capture_stall=on_capture_stall,
        observe_location=True,
    )


def _build_mission_steering(
    *,
    controller_id: str,
    arrival_radius_world: float,
    lookahead_world: float | None,
    mppi_batch_size: int,
    mppi_time_steps: int,
) -> PredictiveSteeringController:
    """Bind reviewed runtime tuning to the selected controller.

    The adaptive profile owns an asynchronous MPPI instance for narrow sharp
    topology.  It must receive the same bounded configuration exposed by the
    CLI; otherwise the Control Center can report 128x24 while the live worker
    silently runs the library defaults.
    """

    mppi_configuration = MppiConfiguration(
        batch_size=mppi_batch_size,
        time_steps=mppi_time_steps,
    )
    adaptive_mppi_configuration = MppiConfiguration(
        batch_size=mppi_batch_size,
        time_steps=mppi_time_steps,
        yaw_smoothness_weight=6.0,
    )
    if controller_id == "continuous_trajectory_v1":
        return ContinuousTrajectoryFollower(
            arrival_radius_world=arrival_radius_world,
        )
    if controller_id == "adaptive_trajectory_v1":
        return AdaptiveTrajectorySteeringController(
            arrival_radius_world=arrival_radius_world,
            mppi_factory=lambda: AsyncMppiSteeringController(
                planner=PathIntegralSteeringPlanner(adaptive_mppi_configuration),
                lookahead_world=lookahead_world,
                arrival_radius_world=arrival_radius_world,
                replan_interval_ticks=3,
            ),
        )
    if controller_id == "pa_mppi_v1":
        return AsyncMppiSteeringController(
            planner=PathIntegralSteeringPlanner(mppi_configuration),
            lookahead_world=lookahead_world,
            arrival_radius_world=arrival_radius_world,
        )
    return PredictiveSteeringController(
        lookahead_world=lookahead_world,
        arrival_radius_world=arrival_radius_world,
    )


def run(
    argv=None,
    *,
    pose_source_factory: Callable[..., MovementObservationPort] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if args.acknowledge_navmesh_roaming is not True:
        raise SystemExit("--acknowledge-navmesh-roaming is required")
    if not 1 <= args.max_forward_actions <= 30:
        raise SystemExit("--max-forward-actions must be in [1, 30]")
    if not 20 <= args.max_control_frames <= 18_000:
        raise SystemExit("--max-control-frames must be in [20, 18000]")
    if not -500.0 <= args.start_world_z_hint <= 5000.0:
        raise SystemExit("--start-world-z-hint is outside the reviewed world bound")
    if args.lookahead_world is not None and not 1.0 <= args.lookahead_world <= 30.0:
        raise SystemExit("--lookahead-world must be in [1, 30]")
    if not 0.5 <= args.arrival_radius_world <= 100.0:
        raise SystemExit("--arrival-radius-world must be in [0.5, 100]")
    if not 32 <= args.mppi_batch_size <= 20_000:
        raise SystemExit("--mppi-batch-size must be in [32, 20000]")
    if not 12 <= args.mppi_time_steps <= 160:
        raise SystemExit("--mppi-time-steps must be in [12, 160]")
    if not 0.25 <= args.minimum_travel_health_fraction <= 0.90:
        raise SystemExit("--minimum-travel-health-fraction must be in [0.25, 0.90]")
    if not 0.0 <= args.runtime_arm_wait_seconds <= 300.0:
        raise SystemExit("--runtime-arm-wait-seconds must be in [0, 300]")
    if (
        args.camera_pitch_delta_y == 0
        or abs(args.camera_pitch_delta_y) > 120
        or args.camera_pitch_delta_y % 5 != 0
    ):
        raise SystemExit(
            "--camera-pitch-delta-y must be a non-zero 5-pixel pitch step "
            "between -120 and 120"
        )
    if args.camera_zoom_wheel_steps == 0 or not -8 <= args.camera_zoom_wheel_steps <= 8:
        raise SystemExit(
            "--camera-zoom-wheel-steps must be a non-zero integer in [-8, 8]"
        )
    if not 2 <= args.camera_home_view_index <= 5:
        raise SystemExit("--camera-home-view-index must be in [2, 5]")
    if not 0 <= args.camera_home_zoom_out_steps <= 10:
        raise SystemExit("--camera-home-zoom-out-steps must be in [0, 10]")
    if (
        args.camera_home_pitch_delta_y == 0
        or abs(args.camera_home_pitch_delta_y) > 60
        or args.camera_home_pitch_delta_y % 5 != 0
    ):
        raise SystemExit(
            "--camera-home-pitch-delta-y must be a non-zero 5-pixel pitch step "
            "between -60 and 60"
        )
    if (
        sum(
            (
                args.recover_camera_pitch_only,
                args.recover_camera_zoom_only,
                args.recover_camera_home_only,
                args.recover_standing_only,
            )
        )
        > 1
    ):
        raise SystemExit("choose exactly one bounded presentation recovery operation")
    normalized_goal_complete = (
        args.goal_normalized_x is not None and args.goal_normalized_y is not None
    )
    if (args.goal_normalized_x is None) != (args.goal_normalized_y is None):
        raise SystemExit("normalized goal requires both X and Y")
    destination_choice_count = sum(
        (
            normalized_goal_complete,
            args.semantic_destination_id is not None,
            args.operator_path is not None,
        )
    )
    if destination_choice_count != 1:
        raise SystemExit(
            "choose exactly one normalized, semantic, or operator-path destination"
        )
    if args.allow_ghost_navigation and (
        args.semantic_destination_id is not None or args.operator_path is not None
    ):
        raise SystemExit("ghost navigation requires one exact normalized corpse goal")
    if args.allow_ghost_navigation and args.activate_stealth:
        raise SystemExit("ghost navigation cannot activate stealth")
    leveling_plan = None
    if args.leveling_plan_file is not None:
        try:
            leveling_plan = load_leveling_plan(args.leveling_plan_file)
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise SystemExit(f"invalid leveling plan: {error}") from error
        if leveling_plan.status != "READY" or leveling_plan.next_goal is None:
            raise SystemExit("leveling plan has no executable client-validated goal candidate")
        if leveling_plan.map_id != args.map_id:
            raise SystemExit("leveling plan map does not match the selected WorldPack map")
        if args.goal_normalized_x is None or args.goal_normalized_y is None:
            raise SystemExit("leveling plan requires a normalized goal pair")
        if (
            abs(float(args.goal_normalized_x) - float(leveling_plan.next_goal[0])) > 1e-6
            or abs(float(args.goal_normalized_y) - float(leveling_plan.next_goal[1])) > 1e-6
        ):
            raise SystemExit("normalized goal does not match the leveling plan")
    authorization_raw = args.session_authorization_file.read_bytes()
    authorization = json.loads(authorization_raw)
    receipt = _read_json(args.session_receipt)
    expiry = datetime.fromisoformat(
        str(authorization["approval"]["expires_at"]).replace("Z", "+00:00")
    )
    if expiry <= datetime.now(timezone.utc):
        raise SystemExit("session authorization is expired")
    actor = authorization["actor_binding"]
    if not isinstance(actor, dict) or receipt.get("pid") is None:
        raise SystemExit("session actor or receipt is invalid")
    receipt_client_build = str(receipt.get("client_build", ""))
    if receipt_client_build.count(".") < 3:
        raise SystemExit("session receipt has no versioned client build")
    client_version = receipt_client_build.rsplit(".", 1)[0]
    loose_paths = (args.nav_root, args.world_catalog, args.world_catalog_asset)
    structure_spatial = None
    structure_access_spatial = None
    runtime_structure_access_graph_id = None
    runtime_structure_access_graph_sha256 = None
    runtime_world_pack_id = None
    runtime_world_pack_content_sha256 = None
    if args.legacy_loose_nav_assets:
        if any(path is None for path in loose_paths):
            raise SystemExit(
                "legacy loose-nav rollback requires --nav-root, --world-catalog, "
                "and --world-catalog-asset"
            )
        client_world_catalog = load_client_world_catalog(
            args.world_catalog,
            schema_path=WORLD_CATALOG_SCHEMA,
        )
        verified_client_world = verify_client_world_catalog(
            client_world_catalog,
            target_profile=str(receipt.get("target_profile", "")),
            client_version=client_version,
            client_build=receipt_client_build,
            nav_profile_id=args.nav_profile_id,
            nav_root=args.nav_root,
            world_catalog_asset_path=args.world_catalog_asset,
        )
        active_catalog = verified_client_world.catalog
        runtime_world_source = "EXPLICIT_LEGACY_LOOSE_NAV_ROLLBACK"
    else:
        if any(path is not None for path in loose_paths):
            raise SystemExit(
                "loose navigation paths are denied without --legacy-loose-nav-assets"
            )
        world_pack_binding = load_world_pack_runtime_profile(
            args.world_pack_profile,
            store_root=args.world_pack_store,
            profile_schema_path=WORLD_PACK_PROFILE_SCHEMA,
            pack_schema_path=WORLD_PACK_SCHEMA,
            catalog_schema_path=WORLD_CATALOG_SCHEMA,
        )
        active_catalog = world_pack_binding.pack.catalog
        expected_identity = (
            (
                "target profile",
                active_catalog.target_profile,
                str(receipt.get("target_profile", "")),
            ),
            ("client version", active_catalog.client_version, client_version),
            ("client build", active_catalog.client_build, receipt_client_build),
            ("nav profile", active_catalog.nav_profile_id, args.nav_profile_id),
        )
        for label, actual, expected in expected_identity:
            if actual != expected:
                raise SystemExit(f"WorldPack {label} does not match the armed client")
        args.nav_root = world_pack_binding.pack.nav_root
        if args.road_semantic_root is None:
            args.road_semantic_root = args.nav_root / "semantics"
        if not args.skip_structure_awareness:
            loaded_structure_index = load_world_structure_index(
                args.world_structure_index,
                schema_path=WORLD_STRUCTURE_INDEX_SCHEMA,
                pack=world_pack_binding.pack,
            )
            if int(loaded_structure_index.record["map_id"]) != args.map_id:
                raise SystemExit("WorldPack structure index does not match --map-id")
            structure_spatial = loaded_structure_index.spatial
        if not args.skip_structure_awareness and args.structure_access_graph is not None:
            from worker_roles import structure_probe_worker_sha256
            loaded_structure_access = load_structure_access_graph(
                args.structure_access_graph,
                schema_path=STRUCTURE_ACCESS_GRAPH_SCHEMA,
                pack=world_pack_binding.pack,
                structure_index_record=loaded_structure_index.record,
                expected_probe_worker_sha256=structure_probe_worker_sha256(
                    args.worker, getattr(args, "structure_probe_worker", None),
                ),
            )
            structure_access_spatial = loaded_structure_access
            runtime_structure_access_graph_id = str(
                loaded_structure_access.record["graph_id"]
            )
            runtime_structure_access_graph_sha256 = str(
                loaded_structure_access.record["content_sha256"]
            )
        runtime_world_source = "VERIFIED_STANDALONE_WORLD_PACK"
        runtime_world_pack_id = str(world_pack_binding.pack.manifest["pack_id"])
        runtime_world_pack_content_sha256 = str(
            world_pack_binding.pack.manifest["content_sha256"]
        )
    active_world_map = active_catalog.map_by_id(args.map_id)
    active_map_name = active_world_map.internal_name
    if leveling_plan is not None:
        if leveling_plan.target_profile != str(receipt.get("target_profile", "")):
            raise SystemExit("leveling plan target profile does not match the armed client")
        if leveling_plan.map_name != active_map_name:
            raise SystemExit("leveling plan map name does not match the WorldPack map")

    presentation_only = any(
        (
            args.dismiss_ui_only,
            args.recover_camera_pitch_only,
            args.recover_camera_zoom_only,
            args.recover_camera_home_only,
            args.recover_standing_only,
            args.snapshot_camera_view_only,
        )
    )
    continuous_authorization_raw: bytes | None = None
    if not presentation_only:
        arm_files_required_before_preflight = args.runtime_arm_wait_seconds <= 0.0
        if (
            args.continuous_motion_authorization_file is None
            or args.continuous_motion_arm_file is None
            or args.continuous_motion_revalidation_file is None
            or not args.continuous_motion_authorization_file.is_file()
            or (
                arm_files_required_before_preflight
                and (
                    not args.continuous_motion_arm_file.is_file()
                    or not args.continuous_motion_revalidation_file.is_file()
                )
            )
        ):
            raise SystemExit(
                "continuous navigation is fail-closed: an approved F4a authorization "
                "and runtime arm are required; fixed-UI auth cannot move Predator"
            )
        continuous_authorization_raw = (
            args.continuous_motion_authorization_file.read_bytes()
        )
        try:
            continuous_authorization_record = json.loads(
                continuous_authorization_raw
            )
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise SystemExit(
                f"invalid continuous motion authorization: {error}"
            ) from error
        if (
            continuous_authorization_record.get("authorization_id")
            != CONTINUOUS_NAVIGATION_AUTHORIZATION_ID
        ):
            raise SystemExit(
                "continuous motion authorization is not the reviewed F4a profile"
            )

    binding = AuthorityBinding(
        actor_id=str(actor["actor_id"]),
        actor_instance_id=str(actor["instance_id"]),
        actor_role=str(actor["actor_role"]),
        decision_context=str(actor["decision_context"]),
        target_profile=str(receipt["target_profile"]),
        target_instance_id=(
            f"client:windows:{receipt['pid']}:{receipt['process_creation_filetime_utc']}"
        ),
        authorization_id=(
            CONTINUOUS_NAVIGATION_AUTHORIZATION_ID
            if continuous_authorization_raw is not None
            else "execution:tbc243-lab:navigation-f3b-client-navmesh"
        ),
        authorization_sha256=(
            _sha256(continuous_authorization_raw)
            if continuous_authorization_raw is not None
            else _sha256(authorization_raw)
        ),
    )
    target = WindowsInputTargetBinding(
        authority_binding=binding,
        pid=int(receipt["pid"]),
        hwnd=int(str(receipt["hwnd"]), 16),
        process_creation_time_100ns=int(receipt["process_creation_filetime_utc"]),
        executable_path=str(receipt["executable_path"]),
        executable_sha256=str(receipt["executable_sha256"]),
        window_class_exact=str(receipt["window_class"]),
        window_title_exact=str(receipt["window_title"]),
    )
    clock = SystemMonotonicClock("clock:windows:monotonic")
    backend = CtypesWin32KeyboardBackend()
    backend.focus_bound_target(target)
    if args.recover_standing_only:
        backend.send_stand_command()
        time.sleep(0.150)
        print(
            json.dumps(
                {
                    "record_type": "bounded_avatar_posture_recovery",
                    "schema_version": "0.1",
                    "status": "STAND_COMMAND_SUBMITTED",
                    "execution_authority": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.recover_camera_pitch_only:
        placement = backend.prepare_world_drag_cursor(hwnd=target.hwnd)
        turn_mode_down = False
        try:
            backend.send_turn_mode_key(key_up=False)
            turn_mode_down = True
            time.sleep(0.025)
            backend.send_relative_mouse(delta_x=0, delta_y=args.camera_pitch_delta_y)
            time.sleep(0.050)
        finally:
            if turn_mode_down:
                backend.send_turn_mode_key(key_up=True)
            # The 2.4.3 client consumes RMB-up asynchronously.  Cursor restore
            # must not become a second pitch drag.
            time.sleep(0.100)
            backend.restore_cursor_position(placement)
        print(
            json.dumps(
                {
                    "record_type": "bounded_camera_pitch_recovery",
                    "schema_version": "0.1",
                    "status": "ONE_CAMERA_PITCH_STEP_SUBMITTED",
                    "delta_y": args.camera_pitch_delta_y,
                    "execution_authority": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.recover_camera_zoom_only:
        backend.send_mouse_wheel(steps=args.camera_zoom_wheel_steps)
        time.sleep(0.100)
        print(
            json.dumps(
                {
                    "record_type": "bounded_camera_zoom_recovery",
                    "schema_version": "0.1",
                    "status": "ONE_CAMERA_ZOOM_STEP_SUBMITTED",
                    "wheel_steps": args.camera_zoom_wheel_steps,
                    "execution_authority": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.recover_camera_home_only:
        _apply_navigation_camera_profile(
            backend,
            view_index=args.camera_home_view_index,
        )
        print(
            json.dumps(
                {
                    "record_type": "bounded_camera_home_recovery",
                    "schema_version": "0.1",
                    "status": "OPERATOR_CAMERA_VIEW_RESTORED",
                    "view_index": args.camera_home_view_index,
                    "execution_authority": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.snapshot_camera_view_only:
        backend.send_camera_view_snapshot(view_index=args.camera_home_view_index)
        time.sleep(0.100)
        print(
            json.dumps(
                {
                    "record_type": "bounded_camera_view_snapshot",
                    "schema_version": "0.1",
                    "status": "OPERATOR_CAMERA_VIEW_SAVED",
                    "view_index": args.camera_home_view_index,
                    "execution_authority": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.dismiss_ui_at_start or args.dismiss_ui_only:
        backend.send_escape_key()
    if args.dismiss_ui_only:
        print(
            json.dumps(
                {
                    "record_type": "bounded_ui_dismissal",
                    "schema_version": "0.1",
                    "status": "ESCAPE_SUBMITTED",
                    "execution_authority": False,
                },
                sort_keys=True,
            )
        )
        return 0
    keyboard = WindowsSendInputSink(target=target, backend=backend, clock=clock)
    mouse = WindowsMouseTurnSink(target=target, backend=backend, clock=clock)
    cancellation = CooperativeCancellation()
    session_id = f"session:f3b:{uuid4()}"
    # No actuator is created until all read-only world/route planning is done.
    # This prevents the short F4a arm from expiring while the preflight scans
    # structures and prepares the first corridor.
    motion: _PreflightMotionRelease | ContinuousMotionExecutionGateway = (
        _PreflightMotionRelease()
    )
    observation_factory = pose_source_factory or _default_pose_source_factory
    pose_source: MovementObservationPort = observation_factory(
        authorization_file=args.session_authorization_file,
        receipt_file=args.session_receipt,
        receipt=receipt,
        session_id=session_id,
        allow_ghost_navigation=args.allow_ghost_navigation,
        continue_through_routine_aggro=args.continue_through_routine_aggro,
        minimum_travel_health_fraction=args.minimum_travel_health_fraction,
        require_player_anchor=args.require_player_anchor,
        on_capture_stall=lambda: motion.release_all(),
    )
    semantic_transform_name: str | None = None
    if args.semantic_destination_id is not None:
        semantic_catalog_record = _read_json(args.semantic_catalog)
        atlas_calibration = semantic_catalog_record.get("atlas_calibration")
        if isinstance(atlas_calibration, str) and atlas_calibration.startswith(
            "WorldMapArea.dbc:"
        ):
            semantic_transform_name = atlas_calibration.split(":", 1)[1]
    transform = _load_zone_transform(
        args.zone_transform_catalog,
        map_id=args.map_id,
        zone_index=args.expected_zone_index,
        expected_internal_name=semantic_transform_name,
    )
    semantic_destination_name: str | None = None
    semantic_destination_radius: float | None = None
    operator_journey: OperatorAuthoredPath | None = None
    operator_resume_index: int | None = None
    if args.semantic_destination_id is not None:
        (
            destination_x,
            destination_y,
            semantic_destination_radius,
            semantic_destination_name,
        ) = _load_semantic_destination(
            args.semantic_catalog,
            destination_id=args.semantic_destination_id,
            expected_zone_index=args.expected_zone_index,
            expected_map_name=active_map_name,
            expected_map_id=args.map_id,
            transform_catalog=args.zone_transform_catalog,
        )
    elif args.operator_path is not None:
        operator_journey = _load_operator_path_journey(
            args.operator_path,
            expected_map_name=active_map_name,
        )
        final_waypoint = operator_journey.waypoints[-1]
        destination_x, destination_y = final_waypoint.x, final_waypoint.y
    else:
        assert args.goal_normalized_x is not None and args.goal_normalized_y is not None
        destination_x, destination_y = transform.world_from_normalized(
            args.goal_normalized_x, args.goal_normalized_y
        )
    goal_x, goal_y = destination_x, destination_y
    # A heading measured before a previous roaming slice becomes stale as soon
    # as that slice turns the camera.  Keep only the proven movement speed and
    # establish the current heading from this slice's first natural stride.
    _, speed = _heading_from_calibration(_latest_calibration())
    resume_position = None
    current_z_hint = float(args.start_world_z_hint)
    observed_blockers: tuple[tuple[float, float, float, float], ...] = ()
    learned_obstacles_loaded = 0
    learned_obstacles_persisted = 0
    # Keep the telemetry list defined for every destination mode.  Semantic
    # routes fill it after the client floor is selected; operator-authored and
    # normalized routes still reach the shared telemetry builder.
    learned_clearance_actions: list[dict[str, Any]] = []
    recovery_strategy_memory = _load_recovery_strategy_memory(
        args.recovery_strategy_memory,
    )
    recovery_strategy_failures_persisted = 0
    recovery_strategy_skips = 0
    heading = None
    if args.resume_result is not None:
        # The result proves continuity of position, but its last tiny movement
        # delta is not reliable evidence of the camera's current yaw.  Resume
        # with a fresh natural stride and infer heading from observed motion.
        resume_position = _resume_position(args.resume_result)
        current_z_hint = _resume_z_hint(
            args.resume_result,
            fallback=current_z_hint,
        )
        observed_blockers = _resume_observed_blocker(
            args.resume_result,
            goal_x=goal_x,
            goal_y=goal_y,
        )
    learned_obstacle_memory = _load_learned_obstacle_memory(
        args.learned_obstacle_memory,
    )
    query = ClientAssetNavmeshQuery(
        worker=args.worker,
        nav_root=args.nav_root,
        observed_blockers=observed_blockers,
    )
    nav_sha = active_world_map.nav_tiles_sha256.upper()
    model = LayeredWorldModel(
        map_name=active_map_name,
        static_navmesh_sha256=nav_sha,
    )
    mission_steering = _build_mission_steering(
        controller_id=args.steering_controller,
        arrival_radius_world=args.arrival_radius_world,
        lookahead_world=args.lookahead_world,
        mppi_batch_size=args.mppi_batch_size,
        mppi_time_steps=args.mppi_time_steps,
    )
    structure_egress_steering = (
        ContinuousTrajectoryFollower(
            arrival_radius_world=STRUCTURE_EGRESS_ARRIVAL_RADIUS_WORLD,
        )
        if args.steering_controller in {
            "continuous_trajectory_v1",
            "adaptive_trajectory_v1",
        }
        else PredictiveSteeringController(
            lookahead_world=args.lookahead_world,
            arrival_radius_world=STRUCTURE_EGRESS_ARRIVAL_RADIUS_WORLD,
        )
    )
    engine = MovementEngine(
        navigator=query,
        steering=mission_steering,
        world=model,
        structures=structure_spatial,
        structure_access=structure_access_spatial,
    )
    dynamic_tracker = DynamicEntityTracker(ttl_s=0.80)
    # WoW units/nameplates are awareness and combat inputs, not solid movement
    # geometry. Static client collision remains governed by navmesh/WMO/M2.
    dynamic_avoidance = DynamicCollisionAvoidance(
        units_physically_block_movement=False,
    )
    dynamic_tracks: tuple[DynamicEntityTrack, ...] = ()
    dynamic_decision = DynamicAvoidanceDecision(
        "CLEAR",
        None,
        0,
        0.0,
        None,
        None,
        None,
        None,
        "dynamic_entity_adapter_not_observed_yet",
    )
    run_control = (
        None
        if args.operator_control_file is None
        else FileOperatorCombatControl(args.operator_control_file.resolve())
    )
    run_id = f"run:f3b:{uuid4()}"
    dynamic_experience_store: DynamicExperienceStore | None = None
    dynamic_experience_summary: dict[str, object] | None = None
    experienced_dynamic_track_ids: set[str] = set()
    dynamic_encounter_validator = ContractValidator(DYNAMIC_ENCOUNTER_SCHEMA)
    dynamic_experience_summary_validator = ContractValidator(
        DYNAMIC_EXPERIENCE_SUMMARY_SCHEMA
    )
    live_preflight_validator = ContractValidator(LIVE_PREFLIGHT_SCHEMA)

    def remember_dynamic_experience(
        tracks: tuple[DynamicEntityTrack, ...],
        *,
        observer_x: float,
        observer_y: float,
        observer_facing_rad: float | None,
    ) -> None:
        nonlocal dynamic_experience_summary
        if dynamic_experience_store is None:
            raise RuntimeError("dynamic experience store is not open")
        changed = False
        for track in tracks:
            if (
                track.observation_count < 2
                or track.track_id in experienced_dynamic_track_ids
            ):
                continue
            encounter = encounter_from_track(
                track,
                session_id=run_id,
                map_name=active_map_name,
                navmesh_sha256=nav_sha,
                observed_at_utc=(
                    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                ),
                observer_world_x=observer_x,
                observer_world_y=observer_y,
                # Coordinate HUD proves X/Y. Z remains a navmesh hint and is
                # deliberately not persisted as an observed coordinate.
                observer_world_z=None,
                observer_facing_rad=observer_facing_rad,
            )
            dynamic_encounter_validator.validate(encounter.to_record())
            dynamic_experience_store.append(encounter)
            experienced_dynamic_track_ids.add(track.track_id)
            changed = True
        if changed or dynamic_experience_summary is None:
            dynamic_experience_summary = dynamic_experience_store.summary_record(
                map_name=active_map_name,
                navmesh_sha256=nav_sha,
            )
            dynamic_experience_summary_validator.validate(dynamic_experience_summary)

    actions: list[dict[str, object]] = []
    actions.append(
        {
            "kind": "STEERING_CONTROLLER_SELECTED",
            "controller_id": args.steering_controller,
            "mppi_batch_size": (
                args.mppi_batch_size
                if args.steering_controller
                in {"adaptive_trajectory_v1", "pa_mppi_v1"}
                else None
            ),
            "mppi_time_steps": (
                args.mppi_time_steps
                if args.steering_controller
                in {"adaptive_trajectory_v1", "pa_mppi_v1"}
                else None
            ),
            "reason": "explicit_runtime_controller_selection",
            "execution_authority": False,
        }
    )
    if leveling_plan is not None:
        actions.append(
            {
                "kind": "LEVELING_GUIDE_ATTACHED",
                "plan_id": leveling_plan.plan_id,
                "catalog_id": leveling_plan.catalog_id,
                "current_level": leveling_plan.current_level,
                "map_id": leveling_plan.map_id,
                "step_count": len(leveling_plan.steps),
                "next_step_order": leveling_plan.next_step_order,
                "next_step_id": (
                    None
                    if leveling_plan.next_position_step is None
                    else leveling_plan.next_position_step.entry_id
                ),
                "source": "route_teacher",
                "execution_authority": False,
            }
        )
    forward_actions = 0
    control_frames = 0
    consecutive_stale_control_frame_retries = 0
    no_progress_s = 0.0
    pivot_without_heading_progress_s = 0.0
    pivot_heading_error_anchor_rad: float | None = None
    collision_slide_s = 0.0
    corridor_recenter_replans = 0
    corridor_recenter_stall_evidence_s = 0.0
    recovery_attempts = 0
    local_recovery_attempts = 0
    last_recovery_collision_world: tuple[float, float] | None = None
    partial_replans = 0
    cancelled = False
    heading_estimator = DisplacementHeadingEstimator()
    visible_heading_observer = VisibleHeadingObserver()
    # A mouse-integrated heading may bridge one missed visual frame, but it
    # must not authorize an unlimited blind stride.  The timestamp is updated
    # only by a current exact/fused client-facing observation.
    last_visible_heading_observed_s: float | None = None
    direction_probe_signature: tuple[object, ...] | None = None
    initial_direction_probe_pending = True
    initial_direction_probe_realignment_count = 0
    calibration_heading_hold_frames = 0
    initial_direction_replan_pending = False
    initial_direction_replan_attempts = 0
    live_heading_divergence_realignment_count = 0
    progress_gate = CorridorProgressGate(minimum_progress_world=0.50)
    camera_pivot = CameraPivotController()
    deferred_camera_intent: CameraPivotIntent | None = None
    semantic_route: SemanticRoadRoute | None = None
    semantic_goals: list[RoadWorldPoint] = []
    traversed_surface_local_count = 0
    ordered_goal_queue_active = False
    semantic_goal_index = 0
    semantic_route_progress_index = 0
    # Semantic Detour work is isolated in child processes so JSON decoding,
    # topology parsing and optional trajectory smoothing cannot hold the GIL
    # of the realtime pose/control loop. The child has no actuator handles.
    semantic_preplan_executor = ProcessPoolExecutor(
        max_workers=2,
    )
    # Keep evidence-only WMO baselines and speculative refinement probes away
    # from the primary next-goal preplan queue. A slow advisory query must not
    # postpone the complete corridor needed for a smooth semantic handoff.
    semantic_advisory_executor = ProcessPoolExecutor(
        max_workers=2,
    )
    # Keep the frontier validator on its own bounded worker.  WMO baselines
    # and ordinary next-goal/refinement plans are advisory work; they must not
    # queue the one query that can preserve continuity at a partial frontier.
    # This process still has no actuator handles and returns only a validated
    # client-navmesh corridor.
    semantic_frontier_preplan_executor = ProcessPoolExecutor(
        max_workers=1,
    )
    semantic_preplan_future: Future[
        NavCorridor | tuple[NavCorridor, SmoothedTrajectory]
    ] | None = None
    semantic_preplan_goal_index: int | None = None
    semantic_preplan_query: ClientAssetNavmeshQuery | None = None
    semantic_preplan_failed_goal_index: int | None = None
    # A repeated partial frontier is expected on the static signpost/cart
    # edges. Prepare the ordered atlas-forward bypass from the proven frontier
    # while the actor is still consuming the current corridor; the completed
    # result is applied only when the live pose is still close to that start.
    semantic_frontier_preplan_future: Future[tuple[int, NavCorridor] | None] | None = None
    semantic_frontier_preplan_query: ClientAssetNavmeshQuery | None = None
    semantic_frontier_preplan_goal_index: int | None = None
    semantic_frontier_preplan_start: NavPoint | None = None
    semantic_frontier_preplan_candidates: tuple[tuple[int, float, float], ...] = ()
    semantic_frontier_preplan_result_materialized = False
    # Persistent geometric divergence is likewise prepared before the strict
    # replan threshold. A ready corridor lets us retain the current movement
    # lease for one frame; an in-flight/invalid result still fails closed into
    # the existing synchronous replan path.
    corridor_recenter_preplan_future: Future[
        NavCorridor | tuple[NavCorridor, SmoothedTrajectory]
    ] | None = None
    corridor_recenter_preplan_query: ClientAssetNavmeshQuery | None = None
    corridor_recenter_preplan_start: NavPoint | None = None
    corridor_recenter_preplan_goal: tuple[float, float] | None = None
    # WMO baseline checks are evidence-only native queries.  Keep them off the
    # realtime control path and apply a completed result at the next frame.
    wmo_baseline_futures: dict[
        tuple[float, float, float, float], Future[bool]
    ] = {}
    wmo_baseline_context: dict[
        tuple[float, float, float, float], tuple[int, int]
    ] = {}
    wmo_baseline_proven_for_goal: set[
        tuple[tuple[float, float, float, float], int]
    ] = set()
    semantic_preview_goal_index: int | None = None
    semantic_refinement_preplan_future: Future[
        NavCorridor | tuple[NavCorridor, SmoothedTrajectory]
    ] | None = None
    semantic_refinement_preplan_point: RoadWorldPoint | None = None
    semantic_handoff_cache: dict[int, NavCorridor] = {}
    semantic_clearance_continuation_cache: dict[
        tuple[float, float, float, float], NavCorridor
    ] = {}
    # The overlay is diagnostic and must never share the realtime input
    # critical path. Atomic JSON publication can occasionally block on a
    # Windows reader or fsync for hundreds of milliseconds; publish only the
    # newest eligible snapshot on an isolated worker and skip intermediate UI
    # frames while that worker is busy.
    movement_lab_publish_executor = ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="pa-movement-lab-publish",
    )
    movement_lab_publish_future: Future[None] | None = None
    live_awareness = AsyncPersistentNavmeshAwareness(
        worker=args.worker,
        nav_root=args.nav_root,
        map_name=active_map_name,
        initial_z=current_z_hint,
    )
    last_live_awareness_observed_s: float | None = None
    recovery_resume_goal: tuple[float, float] | None = None
    recovery_local_goals: list[NavPoint] = []
    recovery_pending_blocker: tuple[float, float, float, float] | None = None
    recovery_strategy: str | None = None
    structure_resume_goal: tuple[float, float] | None = None
    structure_egress_opening_id: str | None = None
    structure_egress_continuation: NavCorridor | None = None
    attempted_structure_egress_ids: set[str] = set()
    verified_breadcrumb_direction_probe_pending = False
    world_x: float | None = None if resume_position is None else resume_position[0]
    world_y: float | None = None if resume_position is None else resume_position[1]
    safe_retreat_trail = SafeRetreatTrail(map_name=active_map_name)
    observed_journey_trace = ObservedJourneyTrace()

    def observe_traversal(point: NavPoint) -> None:
        safe_retreat_trail.observe(point)
        observed_journey_trace.observe(point)

    def safe_retreat_context() -> dict[str, object]:
        record = safe_retreat_trail.record()
        return {
            "map": record.map_name,
            "points": [[point.x, point.y, point.z] for point in record.points],
            "sampled_distance_world": record.sampled_distance_world,
            "source": "fresh_client_visible_positions",
            "execution_authority": False,
        }

    def remember_visible_heading(
        *, observed_s: float, heading_source: str | None
    ) -> None:
        """Remember only a current adapter-backed heading observation."""

        nonlocal last_visible_heading_observed_s
        client_source = getattr(
            pose_source, "latest_facing_source", "UNAVAILABLE"
        )
        if is_current_visual_heading(
            heading_source=heading_source,
            client_facing_source=client_source,
        ):
            last_visible_heading_observed_s = float(observed_s)

    def publish_continuity(
        status_value: str,
        *,
        visible_state: VisibleClientStateObservation | None = None,
    ) -> None:
        _write_json_atomic(
            args.continuity_state_file,
            {
                "record_type": "navigation_continuity_checkpoint",
                "schema_version": "1.0",
                "run_id": run_id,
                "status": status_value,
                "map": active_map_name,
                "zone_index": args.expected_zone_index,
                "semantic_destination_id": args.semantic_destination_id,
                "semantic_destination_name": semantic_destination_name,
                "operator_path_id": (
                    None if operator_journey is None else operator_journey.path_id
                ),
                "operator_resume_index": operator_resume_index,
                "destination_world": [destination_x, destination_y],
                "active_local_goal_world": [goal_x, goal_y],
                "last_known_world": (
                    None if world_x is None or world_y is None else [world_x, world_y]
                ),
                "last_known_z_hint": current_z_hint,
                "semantic_goal_index": semantic_goal_index,
                "observed_blockers": [list(item) for item in observed_blockers],
                "visible_client_state": (
                    None
                    if visible_state is None
                    else observation_to_record(visible_state)
                ),
                "updated_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "execution_authority": False,
            },
        )

    def takeover() -> bool:
        nonlocal cancelled
        cancelled = True
        cancellation.cancel()
        motion.release_all()
        keyboard.release_all()
        mouse.release_all()
        return True

    disarm = PauseHotkeySource().arm(takeover)
    publish_continuity("STARTING")
    try:
        dynamic_experience_store = DynamicExperienceStore(args.dynamic_experience_store)
        remember_dynamic_experience(
            (),
            observer_x=0.0,
            observer_y=0.0,
            observer_facing_rad=None,
        )
        # ProcessPoolExecutor creates child workers lazily.  Pay that startup
        # cost before opening the pose/control clock so the first semantic
        # preplan, frontier bypass or WMO advisory cannot create a cold-start
        # observation gap while movement input is active.  These no-op jobs
        # have no client or actuator access and remain strictly fail-closed.
        warmup_started_s = time.monotonic()
        _warm_process_pool(
            semantic_preplan_executor,
            pool_name="semantic_preplan",
            worker_count=2,
        )
        _warm_process_pool(
            semantic_advisory_executor,
            pool_name="semantic_advisory",
            worker_count=2,
        )
        _warm_process_pool(
            semantic_frontier_preplan_executor,
            pool_name="semantic_frontier_preplan",
            worker_count=1,
        )
        actions.append(
            {
                "kind": "ASYNC_WORKER_POOLS_WARMED",
                "pool_workers": {
                    "semantic_preplan": 2,
                    "semantic_advisory": 2,
                    "semantic_frontier_preplan": 1,
                },
                "duration_ms": round(
                    (time.monotonic() - warmup_started_s) * 1000.0,
                    3,
                ),
                "reason": "prestart_lazy_process_pool_workers_before_pose_clock",
                "execution_authority": False,
            }
        )
        pose_source.open()
        # Observe first.  If the client is already in combat, next_observation()
        # raises CombatHandoffRequired before navigation emits any input.  The
        # combat runner owns a separate authorization and must receive control
        # before even idempotent posture/camera setup is attempted.
        observation = pose_source.next_observation()
        # Reset/death recovery can leave the avatar seated, so begin with the
        # idempotent stand command. Preserve the operator's current camera
        # composition during normal navigation; SetView is reserved for the
        # explicit bounded camera-recovery operation.
        backend.send_stand_command()
        time.sleep(0.100)
        backend.send_navigation_camera_preferences()
        actions.append(
            {
                "kind": "START_CAMERA_PREFERENCES_APPLIED",
                "smart_pivot": False,
                "reason": "preserve_operator_composition_before_first_motion",
                "execution_authority": False,
            }
        )
        time.sleep(0.100)
        if args.require_player_anchor:
            # Strict silhouette validation is an explicit calibration test,
            # never an implicit prerequisite for autonomous navigation.
            settle_camera = getattr(pose_source, "wait_for_camera_integrity", None)
            if callable(settle_camera):
                observation = settle_camera()
                actions.append(
                    {
                        "kind": "CAMERA_STARTUP_STABILIZED",
                        "attempts": int(
                            getattr(pose_source, "last_camera_settle_attempts", 0)
                        ),
                        "required_visible_frames": CAMERA_STARTUP_STABLE_VISIBLE_FRAMES,
                        "camera_integrity": getattr(
                            pose_source, "latest_camera_integrity", None
                        ),
                        "reason": "explicit_strict_player_anchor_diagnostic",
                        "execution_authority": False,
                    }
                )
            arm_camera_gate = getattr(pose_source, "arm_camera_integrity_gate", None)
            if callable(arm_camera_gate):
                arm_camera_gate()
        else:
            actions.append(
                {
                    "kind": "CAMERA_ACTOR_DIAGNOSTIC_ONLY",
                    "camera_integrity": getattr(
                        pose_source, "latest_camera_integrity", None
                    ),
                    "reason": "pixel_silhouette_is_not_navigation_authority",
                    "execution_authority": False,
                }
            )
        if args.activate_stealth:
            backend.send_stealth_command()
        # Posture/camera setup can take long enough for a combat transition;
        # reacquire one fresh frame before deriving the first route position.
        observation = pose_source.next_observation()
        observation, heading, heading_source, heading_attempts = (
            _acquire_initial_visible_heading(
                pose_source,
                visible_heading_observer,
                observation=observation,
                predicted_heading_rad=heading,
                require_exact_body_heading=args.require_exact_body_heading,
            )
        )
        remember_visible_heading(
            observed_s=float(observation["timing"]["observed_monotonic_s"]),
            heading_source=heading_source,
        )
        if args.require_exact_body_heading:
            _require_exact_body_heading(
                observation,
                heading=heading,
                heading_source=heading_source,
                phase="initial pre-control",
            )
        initial_client_facing_source = getattr(
            pose_source, "latest_facing_source", "UNAVAILABLE"
        )
        initial_body_yaw_observation_rad = _body_yaw_observation(
            observation,
            client_facing_source=initial_client_facing_source,
        )
        actions.append(
            {
                "kind": "HEADING_READY_BEFORE_CONTROL",
                "attempts": heading_attempts,
                "heading_source": heading_source,
                "client_facing_source": initial_client_facing_source,
                "body_yaw_observation_rad": initial_body_yaw_observation_rad,
                "body_yaw_observation_source": (
                    initial_client_facing_source
                    if initial_body_yaw_observation_rad is not None
                    else "UNAVAILABLE"
                ),
                "camera_yaw_estimate_rad": heading,
                "camera_yaw_source": CAMERA_YAW_CONTROL_SOURCE,
                "body_camera_yaw_delta_rad": _body_camera_yaw_delta(
                    initial_body_yaw_observation_rad, heading
                ),
                "reason": "read_only_reacquisition_before_first_motion_input",
                "execution_authority": False,
            }
        )
        _, _, world_x, world_y = _position(
            observation,
            expected_zone_index=args.expected_zone_index,
            transform=transform,
            expected_map_id=args.map_id,
        )
        observe_traversal(NavPoint(world_x, world_y, current_z_hint))
        heading_estimator.reset(x=world_x, y=world_y)
        learned_nearby = learned_obstacle_memory.nearby(
            map_name=active_map_name,
            zone_index=args.expected_zone_index,
            x=world_x,
            y=world_y,
            now=datetime.now(timezone.utc),
        )
        learned_polygon_obstacles = tuple(
            item
            for item in learned_nearby
            if (
                item.evidence == DETOUR_EXCLUSION_EVIDENCE
                and item.confidence == "confirmed"
            )
        )
        learned_polygon_blockers = tuple(
            item.planning_blocker() for item in learned_polygon_obstacles
        )
        learned_local_clearance = tuple(
            item
            for item in learned_obstacle_memory.obstacles
            if (
                item.map_name == active_map_name
                and item.zone_index == args.expected_zone_index
                and item.evidence == LOCAL_CLEARANCE_EVIDENCE
                and item.planning_confirmed
            )
        )
        # Semantic movement may have a COMPLETE operator observation which
        # proves that an old collision disc was a steering artefact rather
        # than physical geometry.  Delay those learned discs until that
        # contradiction check below.  Normalized/operator routes retain the
        # previous immediate behavior.
        if args.semantic_destination_id is None:
            observed_blockers = _bounded_blocker_union(
                observed_blockers,
                learned_polygon_blockers,
                origin_x=world_x,
                origin_y=world_y,
            )
        learned_obstacles_loaded = len(learned_nearby)
        query = ClientAssetNavmeshQuery(
            worker=args.worker,
            nav_root=args.nav_root,
            observed_blockers=observed_blockers,
        )
        engine.navigator = query
        if learned_obstacles_loaded:
            actions.append(
                {
                    "kind": "LEARNED_OBSTACLES_LOADED",
                    "count": learned_obstacles_loaded,
                    "polygon_exclusion_count": len(learned_polygon_blockers),
                    "local_clearance_count": len(learned_local_clearance),
                    "memory_file": str(args.learned_obstacle_memory.resolve()),
                    "maximum_distance_world": 300.0,
                    "execution_authority": False,
                }
            )
        if (
            resume_position is not None
            and hypot(world_x - resume_position[0], world_y - resume_position[1]) > 2.5
        ):
            raise RuntimeError(
                "live position does not match the requested resume result"
            )
        if args.semantic_destination_id is not None:
            road_semantic_root = (
                args.road_semantic_root
                if args.road_semantic_root is not None
                else args.nav_root / "semantics"
            )
            road_planner = ClientRoadSemanticPlanner(
                sidecar_root=road_semantic_root,
                map_name=active_map_name,
            )
            travel_capability = (
                pose_source.latest_travel_capability
                or TravelCapability(
                    level=1,
                    health_fraction=0.05,
                    stealth_ready=False,
                    escape_ready=False,
                )
            )
            historical_risk_areas = dynamic_experience_store.historical_risk_areas(
                map_name=active_map_name,
                navmesh_sha256=nav_sha,
            )
            risk_selection = select_risk_aware_semantic_route(
                planner=road_planner,
                policy=RiskAwareRoutePolicy(),
                start_x=world_x,
                start_y=world_y,
                destination_x=destination_x,
                destination_y=destination_y,
                capability=travel_capability,
                historical_risk_areas=historical_risk_areas,
                now_s=float(observation["timing"]["observed_monotonic_s"]),
            )
            semantic_route, queued_semantic_goals = _semantic_goal_queue(
                planner=road_planner,
                start_x=world_x,
                start_y=world_y,
                destination_x=destination_x,
                destination_y=destination_y,
                route=risk_selection.route,
            )
            traversed_surface_recording = None
            if (
                args.traversed_surface_prior is not None
                and args.traversed_surface_prior.is_file()
            ):
                traversed_surface_recording = ManualPathRecording.from_record(
                    _read_json(args.traversed_surface_prior)
                )
            (
                queued_semantic_goals,
                demonstrated_obstacle_ids,
                traversed_surface_action,
            ) = _inject_traversed_surface_prior(
                route_start=RoadWorldPoint(world_x, world_y),
                goals=queued_semantic_goals,
                obstacles=tuple(
                    item for item in learned_nearby if item.planning_confirmed
                ),
                recording=traversed_surface_recording,
            )
            if traversed_surface_action is not None:
                actions.append(traversed_surface_action)
                traversed_surface_local_count = int(
                    traversed_surface_action["local_point_count"]
                )
            active_learned_polygon_blockers = tuple(
                item.planning_blocker()
                for item in learned_polygon_obstacles
                if item.obstacle_id not in demonstrated_obstacle_ids
            )
            observed_blockers = _bounded_blocker_union(
                observed_blockers,
                active_learned_polygon_blockers,
                origin_x=world_x,
                origin_y=world_y,
            )
            query = query.with_observed_blockers(observed_blockers)
            engine.navigator = query
            suppressed_polygon_ids = tuple(
                item.obstacle_id
                for item in learned_polygon_obstacles
                if item.obstacle_id in demonstrated_obstacle_ids
            )
            if suppressed_polygon_ids:
                actions.append(
                    {
                        "kind": (
                            "LEARNED_POLYGON_BLOCKER_SUPPRESSED_BY_COMPLETE_"
                            "TRAVERSAL"
                        ),
                        "obstacle_ids": list(suppressed_polygon_ids),
                        "reason": (
                            "complete_client_observed_traversal_contradicts_"
                            "learned_collision_envelope"
                        ),
                        "source": "operator_observed_continuous_traversability",
                        "execution_authority": False,
                    }
                )
            # Confirmed clearance priors are applied after the initial client
            # vertical layer is selected below.  Applying them while the
            # conservative seed Z is still active can mistake a ceiling or an
            # upper crypt floor for an obstacle on the actor's current floor.
            semantic_goals = list(queued_semantic_goals)
            ordered_goal_queue_active = True
            static_structure_blockers = _route_static_structure_blockers(
                structures=structure_spatial,
                start=NavPoint(world_x, world_y, current_z_hint),
                goals=semantic_goals,
            )
            if static_structure_blockers:
                observed_blockers = _bounded_blocker_union(
                    observed_blockers,
                    static_structure_blockers,
                    origin_x=world_x,
                    origin_y=world_y,
                )
                query = query.with_observed_blockers(observed_blockers)
                engine.navigator = query
                actions.append(
                    {
                        "kind": "STATIC_STRUCTURE_BLOCKERS_CONSIDERED",
                        "count": len(static_structure_blockers),
                        "blockers_world": [
                            list(item) for item in static_structure_blockers
                        ],
                        "horizon_goal_count": min(8, len(semantic_goals)),
                        "source": "WORLD_PACK_STRUCTURE_INDEX_PLUS_DETOUR",
                        "execution_authority": False,
                    }
                )
            goal_x, goal_y = semantic_goals[0].x, semantic_goals[0].y
            actions.append(
                {
                    "kind": "SEMANTIC_ROUTE_PLANNED",
                    "destination_id": args.semantic_destination_id,
                    "destination_name": semantic_destination_name,
                    "waypoint_count": len(semantic_goals),
                    "road_cells": semantic_route.road_cell_count,
                    "near_road_cells": semantic_route.near_road_cell_count,
                    "bridge_cells": semantic_route.offroad_bridge_cell_count,
                    "route_profile_id": semantic_route.profile_id,
                    "risk_policy_reason": risk_selection.decision.reason,
                    "risk_budget": risk_selection.decision.risk_budget,
                    "selected_risk_score": risk_selection.decision.selected.risk_score,
                    "selected_expected_arrival_seconds": (
                        risk_selection.decision.selected.expected_arrival_seconds
                    ),
                    "player_level": travel_capability.level,
                    "player_health_fraction": travel_capability.health_fraction,
                    "stealth_ready": travel_capability.stealth_ready,
                    "escape_ready": travel_capability.escape_ready,
                    "historical_risk_area_count": len(historical_risk_areas),
                    "route_alternatives": [
                        {
                            "route_id": item.route_id,
                            "distance_yards": item.distance_yards,
                            "risk_score": item.risk_score,
                            "expected_arrival_seconds": item.expected_arrival_seconds,
                            "within_risk_budget": item.within_risk_budget,
                            "topographically_eligible": (item.topographically_eligible),
                        }
                        for item in risk_selection.decision.alternatives
                    ],
                    "coordinate_system": "tbc243_client_world_xy",
                    "confirmed_clearance_priors": sum(
                        item["kind"] == "CONFIRMED_CLEARANCE_PRIOR_APPLIED"
                        for item in learned_clearance_actions
                    ),
                }
            )
        elif operator_journey is not None:
            operator_resume_index, queued_operator_goals = _operator_goal_queue(
                operator_journey,
                start_x=world_x,
                start_y=world_y,
            )
            semantic_goals = list(queued_operator_goals)
            ordered_goal_queue_active = True
            goal_x, goal_y = semantic_goals[0].x, semantic_goals[0].y
            actions.append(
                {
                    "kind": "OPERATOR_ROUTE_RESUMED",
                    "path_id": operator_journey.path_id,
                    "path_name": operator_journey.name,
                    "resume_waypoint_order": (
                        operator_journey.waypoints[operator_resume_index].order
                    ),
                    "remaining_waypoint_count": len(semantic_goals),
                    "coordinate_system": "tbc243_client_world_xy",
                    "navmesh_validation_required": True,
                    "execution_authority": False,
                }
            )
        (
            selected_initial_z,
            _selected_layer_corridor,
            vertical_layer_evidence,
        ) = _select_initial_vertical_layer(
            engine,
            start_x=world_x,
            start_y=world_y,
            seed_z=current_z_hint,
            goal_x=goal_x,
            goal_y=goal_y,
        )
        if len(vertical_layer_evidence) > 1:
            actions.append(
                {
                    "kind": "INITIAL_VERTICAL_LAYER_SELECTED",
                    "seed_z": current_z_hint,
                    "selected_z": selected_initial_z,
                    "candidate_count": len(vertical_layer_evidence),
                    "candidates": list(vertical_layer_evidence),
                    "selection_policy": (
                        "matching_local_surface_then_complete_then_height_"
                        "delta_then_minimum_route_stretch_and_topology"
                    ),
                    "execution_authority": False,
                }
            )
        current_z_hint = selected_initial_z
        if args.semantic_destination_id is not None:
            queued_semantic_goals, learned_clearance_actions = (
                _inject_confirmed_clearance_priors(
                    route_start=RoadWorldPoint(world_x, world_y),
                    goals=tuple(semantic_goals),
                    obstacles=tuple(
                        item
                        for item in learned_local_clearance
                        if item.obstacle_id not in demonstrated_obstacle_ids
                    ),
                    query=query,
                    map_name=active_map_name,
                    terminal_goal_radius_world=semantic_destination_radius,
                    route_start_z=current_z_hint,
                    continuation_cache=semantic_clearance_continuation_cache,
                )
            )
            actions.extend(learned_clearance_actions)
            unresolved_clearance = tuple(
                item
                for item in learned_clearance_actions
                if item["kind"] == "CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED"
            )
            if unresolved_clearance:
                raise RuntimeError(
                    "confirmed client-observed geometry blocks the planned route "
                    "and no validated bypass exists: "
                    + ",".join(
                        str(item.get("obstacle_id", "unknown"))
                        for item in unresolved_clearance
                    )
                )
            semantic_goals = list(queued_semantic_goals)
        # The initial start-z hint is deliberately conservative and may be far
        # from the actor's local stacked surface.  Re-evaluate any learned
        # discs only after that surface is selected; otherwise a resume disc
        # from the current polygon can look like a blocker on an unrelated Z
        # layer and seal the first corridor.
        observed_blockers, suppressed_start_blockers = (
            _suppress_learned_blockers_containing_pose(
                observed_blockers,
                start_x=world_x,
                start_y=world_y,
                start_z=current_z_hint,
            )
        )
        if suppressed_start_blockers:
            query = query.with_observed_blockers(observed_blockers)
            engine.navigator = query
            actions.append(
                {
                    "kind": "LEARNED_BLOCKER_SUPPRESSED_AT_CURRENT_POSE",
                    "count": len(suppressed_start_blockers),
                    "reason": (
                        "learned_disc_contains_fresh_client_pose;_keep_memory_"
                        "record_but_do_not_seal_start_polygon"
                    ),
                    "suppressed_blockers": [
                        list(item) for item in suppressed_start_blockers
                    ],
                    "selected_z": current_z_hint,
                    "execution_authority": False,
                }
            )
        # The first structure scan runs before the client floor is known and
        # therefore uses the bounded start-z hint (usually 100).  That hint
        # can hide ordinary ground props from the vertical filter.  Refresh
        # the same bounded WorldPack horizon after selecting the actual local
        # layer, before the first corridor is planned or any input is sent.
        if structure_spatial is not None and semantic_goals:
            observed_blockers, layer_added_blockers = (
                _merge_static_structure_horizon_blockers(
                    structures=structure_spatial,
                    observed_blockers=observed_blockers,
                    start=NavPoint(world_x, world_y, current_z_hint),
                    goals=semantic_goals,
                    maximum_goals=8,
                )
            )
            if layer_added_blockers:
                query = query.with_observed_blockers(observed_blockers)
                engine.navigator = query
                actions.append(
                    {
                        "kind": "STATIC_STRUCTURE_BLOCKERS_REFRESHED_AFTER_LAYER",
                        "count": len(layer_added_blockers),
                        "blockers_world": [list(item) for item in layer_added_blockers],
                        "horizon_goal_count": min(8, len(semantic_goals)),
                        "selected_z": current_z_hint,
                        "source": "WORLD_PACK_STRUCTURE_INDEX_PLUS_SELECTED_CLIENT_LAYER",
                        "execution_authority": False,
                    }
                )
        if semantic_goals:
            initial_clearance_corridor = (
                semantic_clearance_continuation_cache.pop(
                    (
                        round(world_x, 6),
                        round(world_y, 6),
                        round(semantic_goals[0].x, 6),
                        round(semantic_goals[0].y, 6),
                    ),
                    None,
                )
            )
            if (
                initial_clearance_corridor is not None
                and initial_clearance_corridor.complete
                and initial_clearance_corridor.start.distance_2d(
                    NavPoint(world_x, world_y, current_z_hint)
                ) <= 3.0
                and _corridor_reaches_local_goal(
                    initial_clearance_corridor,
                    goal_x=semantic_goals[0].x,
                    goal_y=semantic_goals[0].y,
                    radius_world=max(args.arrival_radius_world, 3.0),
                )
            ):
                semantic_goal_index = 0
                corridor = initial_clearance_corridor
                initial_goal_projected = False
                actions.append(
                    {
                        "kind": "CONFIRMED_CLEARANCE_CORRIDOR_REUSED_INITIAL",
                        "waypoint_index": 0,
                        "world_x": world_x,
                        "world_y": world_y,
                        "reason": (
                            "complete_navmesh_clearance_leg_reused_without_"
                            "semantic_micro_waypoints"
                        ),
                        "execution_authority": False,
                    }
                )
            else:
                semantic_goal_index, corridor, initial_goal_projected = (
                    _plan_semantic_goal_or_forward_projection(
                        engine=engine,
                        start=NavPoint(world_x, world_y, current_z_hint),
                        goals=semantic_goals,
                        goal_index=semantic_goal_index,
                        radius_world=max(args.arrival_radius_world, 3.0),
                    )
                )
        else:
            # Normalized/operator-free destinations have no semantic queue.
            # Replan the exact client-validated goal after all local blocker
            # and layer filters, instead of asking the semantic helper to
            # index an empty list.
            corridor = engine.plan(
                start=NavPoint(world_x, world_y, current_z_hint),
                goal_x=goal_x,
                goal_y=goal_y,
            )
            semantic_goal_index = 0
            initial_goal_projected = False
        if initial_goal_projected:
            goal_x = semantic_goals[semantic_goal_index].x
            goal_y = semantic_goals[semantic_goal_index].y
            actions.append(
                {
                    "kind": "SEMANTIC_ENDPOINT_PROJECTED_FORWARD",
                    "selected_goal_index": semantic_goal_index,
                    "selected_goal_world": [goal_x, goal_y],
                    "reason": (
                        "atlas_raster_center_had_no_polygon_use_next_"
                        "detour_reachable_route_sample"
                    ),
                    "execution_authority": False,
                }
            )
        if semantic_route is not None:
            initial_refinement = _semantic_corridor_refinement(
                route=semantic_route,
                corridor=corridor,
                start_x=world_x,
                start_y=world_y,
                target_x=goal_x,
                target_y=goal_y,
                minimum_route_index=semantic_route_progress_index,
            )
            if initial_refinement is not None:
                (
                    refinement_route_index,
                    refinement_goal,
                    maximum_route_deviation,
                    route_stretch,
                ) = initial_refinement
                semantic_goals.insert(semantic_goal_index, refinement_goal)
                goal_x, goal_y = refinement_goal.x, refinement_goal.y
                corridor = engine.plan(
                    start=NavPoint(world_x, world_y, current_z_hint),
                    goal_x=goal_x,
                    goal_y=goal_y,
                )
                actions.append(
                    {
                        "kind": "SEMANTIC_CORRIDOR_REFINED",
                        "route_waypoint_index": refinement_route_index,
                        "requested_x": goal_x,
                        "requested_y": goal_y,
                        "maximum_route_deviation_world": maximum_route_deviation,
                        "route_stretch": route_stretch,
                        "reason": ("long_local_chord_left_selected_semantic_surface"),
                        "execution_authority": False,
                    }
                )
        already_applied_clearance_ids = {
            str(item["obstacle_id"])
            for item in learned_clearance_actions
            if item.get("kind") in {
                "CONFIRMED_CLEARANCE_PRIOR_APPLIED",
                "CONFIRMED_CLEARANCE_PRIOR_APPLIED_BY_GLOBAL_NAVMESH",
            }
        }
        local_clearance_anchors, local_clearance_evidence = (
            _confirmed_local_corridor_clearance(
                corridor=corridor,
                obstacles=tuple(
                    item
                    for item in learned_local_clearance
                    if item.obstacle_id not in demonstrated_obstacle_ids
                    and item.obstacle_id not in already_applied_clearance_ids
                ),
                query=query,
                map_name=active_map_name,
                route_start_z=current_z_hint,
            )
        )
        if local_clearance_anchors is not None:
            side_anchor, pass_anchor = local_clearance_anchors
            original_goal = RoadWorldPoint(goal_x, goal_y)
            if semantic_goals:
                semantic_goals[semantic_goal_index:semantic_goal_index] = [
                    side_anchor,
                    pass_anchor,
                ]
            else:
                semantic_goals = [side_anchor, pass_anchor, original_goal]
                semantic_goal_index = 0
            goal_x, goal_y = side_anchor.x, side_anchor.y
            corridor = engine.plan(
                start=NavPoint(world_x, world_y, current_z_hint),
                goal_x=goal_x,
                goal_y=goal_y,
            )
            applied_local = next(
                item
                for item in local_clearance_evidence
                if item["kind"] == "CONFIRMED_CLEARANCE_PRIOR_APPLIED"
            )
            actions.append(
                {
                    **applied_local,
                    "kind": "CONFIRMED_LOCAL_CORRIDOR_CLEARANCE_APPLIED",
                    "deferred_goal_world": [original_goal.x, original_goal.y],
                    "reason": (
                        "confirmed_boundary_sample_intersects_actual_client_"
                        "navmesh_corridor"
                    ),
                    "execution_authority": False,
                }
            )
        elif any(
            item["kind"] == "CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED"
            for item in local_clearance_evidence
        ):
            unresolved_ids = [
                str(item.get("obstacle_id", "unknown"))
                for item in local_clearance_evidence
                if item["kind"] == "CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED"
            ]
            raise RuntimeError(
                "confirmed geometry intersects the actual local corridor and "
                "no client-navmesh bypass exists: " + ",".join(unresolved_ids)
            )
        if args.steering_controller == "continuous_trajectory_v1":
            raw_guidance_point_count = len(corridor.guidance_points())
            corridor, initial_trajectory = _prepare_continuous_trajectory(
                query=query,
                map_name=active_map_name,
                corridor=corridor,
            )
            actions.append(
                {
                    "kind": "CONTINUOUS_TRAJECTORY_PREPARED",
                    "phase": "initial_plan",
                    "raw_guidance_point_count": raw_guidance_point_count,
                    "smoothed_guidance_point_count": len(
                        initial_trajectory.points
                    ),
                    "rounded_corner_count": (
                        initial_trajectory.rounded_corner_count
                    ),
                    "rejected_corner_count": (
                        initial_trajectory.rejected_corner_count
                    ),
                    "navmesh_validation_count": (
                        initial_trajectory.validation_count
                    ),
                    "execution_authority": False,
                }
            )
        initial_egress_selection = (
            None
            if args.skip_structure_awareness
            else (
                _forward_structure_egress_plan(
                    engine=engine,
                    direct_corridor=corridor,
                    goals=semantic_goals,
                    goal_index=semantic_goal_index,
                    goal_x=goal_x,
                    goal_y=goal_y,
                    observed_monotonic_s=float(
                        observation["timing"]["observed_monotonic_s"]
                    ),
                    excluded_opening_ids=frozenset(
                        attempted_structure_egress_ids
                    ),
                )
                if semantic_route is not None
                else (
                    semantic_goal_index,
                    _verified_structure_egress_plan(
                        engine=engine,
                        direct_corridor=corridor,
                        goal_x=goal_x,
                        goal_y=goal_y,
                        observed_monotonic_s=float(
                            observation["timing"]["observed_monotonic_s"]
                        ),
                        excluded_opening_ids=frozenset(
                            attempted_structure_egress_ids
                        ),
                    ),
                )
            )
        )
        if (
            initial_egress_selection is not None
            and initial_egress_selection[1] is None
        ):
            initial_egress_selection = None
        initial_egress = (
            None
            if initial_egress_selection is None
            else initial_egress_selection[1]
        )
        if initial_egress is not None:
            selected_goal_index = initial_egress_selection[0]
            if selected_goal_index != semantic_goal_index:
                previous_goal_index = semantic_goal_index
                semantic_goal_index = selected_goal_index
                goal_x = semantic_goals[semantic_goal_index].x
                goal_y = semantic_goals[semantic_goal_index].y
                actions.append(
                    {
                        "kind": "SEMANTIC_STRUCTURE_EGRESS_LOOKAHEAD",
                        "previous_goal_index": previous_goal_index,
                        "selected_goal_index": semantic_goal_index,
                        "skipped_inside_goal_count": (
                            semantic_goal_index - previous_goal_index
                        ),
                        "selected_goal_world": [goal_x, goal_y],
                        "reason": (
                            "bounded_forward_semantic_goal_exits_known_"
                            "structure_via_revalidated_opening"
                        ),
                        "execution_authority": False,
                    }
                )
            structure_resume_goal = (goal_x, goal_y)
            structure_egress_opening_id = initial_egress.opening_id
            structure_egress_continuation = initial_egress.continuation
            attempted_structure_egress_ids.add(initial_egress.opening_id)
            # The graph midpoint is a topology witness, not always a safe
            # actor pose.  When the client-asset query proves an outside
            # anchor, drive the approach to that revalidated movement target
            # instead of stopping on the covered side of the WMO boundary.
            goal_x, goal_y = (
                initial_egress.movement_target.x,
                initial_egress.movement_target.y,
            )
            corridor = initial_egress.approach
            query = _scope_query_for_structure_egress(
                query=query,
                structures=structure_spatial,
                proposal=initial_egress,
            )
            engine.navigator = query
            engine.steering = structure_egress_steering
            actions.append(
                _structure_egress_action(
                    initial_egress,
                    deferred_goal=structure_resume_goal,
                    graph_id=runtime_structure_access_graph_id,
                    graph_content_sha256=runtime_structure_access_graph_sha256,
                )
            )
        local_goal_radius = max(args.arrival_radius_world, 3.0)
        if (
            initial_egress is None
            and ordered_goal_queue_active
            and not _corridor_reaches_local_goal(
                corridor,
                goal_x=goal_x,
                goal_y=goal_y,
                radius_world=local_goal_radius,
            )
        ):
            lookahead = _reachable_semantic_lookahead(
                engine=engine,
                start=NavPoint(world_x, world_y, current_z_hint),
                goals=semantic_goals,
                blocked_index=semantic_goal_index,
                radius_world=local_goal_radius,
            )
            if lookahead is not None:
                blocked_index = semantic_goal_index
                blocked_goal = semantic_goals[blocked_index]
                semantic_goal_index, corridor = lookahead
                goal_x = semantic_goals[semantic_goal_index].x
                goal_y = semantic_goals[semantic_goal_index].y
                actions.append(
                    {
                        "kind": "SEMANTIC_UNREACHABLE_HORIZON_SKIPPED",
                        "blocked_goal_world": [blocked_goal.x, blocked_goal.y],
                        "selected_goal_world": [goal_x, goal_y],
                        "skipped_goal_count": semantic_goal_index - blocked_index,
                        "reason": (
                            "later_atlas_goal_has_complete_client_navmesh_corridor"
                        ),
                        "execution_authority": False,
                    }
                )
        local_static_awareness = (
            {
                "available": False,
                "reason": "operator_requested_bounded_direct_navmesh_slice",
                "execution_authority": False,
            }
            if args.skip_structure_awareness
            else _local_static_awareness_record(corridor)
        )
        actions.append(
            {
                "kind": "LOCAL_STATIC_AWARENESS",
                **local_static_awareness,
            }
        )
        search_vantage_corridor = (
            initial_egress.continuation if initial_egress is not None else corridor
        )
        search_vantage_rejection = (
            search_vantage_corridor.search_vantage_rejection()
            if args.require_open_search_vantage
            else None
        )
        search_vantage_evidence = {
            "required": args.require_open_search_vantage,
            "evaluated_on_structure_continuation": initial_egress is not None,
            "accepted": (
                not args.require_open_search_vantage or search_vantage_rejection is None
            ),
            "rejection": search_vantage_rejection,
            "requested_endpoint_physical_surfaces": sorted(
                search_vantage_corridor.search_vantage_physical_surfaces
            ),
            "radial_clear_count": (
                search_vantage_corridor.search_vantage_radial_clear_count
            ),
            "radial_probe_count": (
                search_vantage_corridor.search_vantage_radial_probe_count
            ),
            "radial_probe_radius": (
                search_vantage_corridor.search_vantage_radial_probe_radius
            ),
            "overhead_clear": search_vantage_corridor.search_vantage_overhead_clear,
            "source": "client_asset_collision_and_navmesh",
            "execution_authority": False,
        }
        actions.append(
            {
                "kind": (
                    "SEARCH_VANTAGE_ACCEPTED"
                    if search_vantage_rejection is None
                    else "SEARCH_VANTAGE_REJECTED"
                ),
                **search_vantage_evidence,
            }
        )
        # Detour planning is bounded but can outlive a control-frame freshness
        # window. Refresh the unchanged start pose after planning and before
        # any held input begins.
        observation = pose_source.next_observation()
        previous_heading_rad = heading
        previous_heading_source = heading_source
        observation, heading, heading_source, heading_attempts = (
            _acquire_initial_visible_heading(
                pose_source,
                visible_heading_observer,
                observation=observation,
                predicted_heading_rad=heading,
                previous_heading_rad=previous_heading_rad,
                previous_heading_source=previous_heading_source,
                preserve_previous_exact=(
                    previous_heading_source == EXACT_BODY_HEADING_SOURCE
                ),
                require_exact_body_heading=args.require_exact_body_heading,
            )
        )
        remember_visible_heading(
            observed_s=float(observation["timing"]["observed_monotonic_s"]),
            heading_source=heading_source,
        )
        if args.require_exact_body_heading:
            _require_exact_body_heading(
                observation,
                heading=heading,
                heading_source=heading_source,
                phase="post-plan pre-control",
            )
        heading, heading_source, minimap_axis_flipped = (
            _orient_initial_fallback_heading_to_corridor(
                heading,
                heading_source=heading_source,
                corridor=corridor,
            )
        )
        post_plan_client_facing_source = getattr(
            pose_source, "latest_facing_source", "UNAVAILABLE"
        )
        post_plan_body_yaw_observation_rad = _body_yaw_observation(
            observation,
            client_facing_source=post_plan_client_facing_source,
        )
        actions.append(
            {
                "kind": "HEADING_READY_BEFORE_CONTROL",
                "attempts": heading_attempts,
                "heading_source": heading_source,
                "client_facing_source": post_plan_client_facing_source,
                "body_yaw_observation_rad": post_plan_body_yaw_observation_rad,
                "body_yaw_observation_source": (
                    post_plan_client_facing_source
                    if post_plan_body_yaw_observation_rad is not None
                    else "UNAVAILABLE"
                ),
                "camera_yaw_estimate_rad": heading,
                "camera_yaw_source": CAMERA_YAW_CONTROL_SOURCE,
                "body_camera_yaw_delta_rad": _body_camera_yaw_delta(
                    post_plan_body_yaw_observation_rad, heading
                ),
                "reason": "read_only_reacquisition_after_route_planning",
                "execution_authority": False,
            }
        )
        if heading_source == PRESERVED_EXACT_BODY_HEADING_SOURCE:
            actions.append(
                {
                    "kind": "EXACT_HEADING_PRESERVED_AFTER_POST_PLAN_MISS",
                    "reason": (
                        "no_input_was_sent_during_planning;_retained_one_"
                        "bounded_exact_body_heading_instead_of_fallback"
                    ),
                    "execution_authority": False,
                }
            )
        if minimap_axis_flipped:
            actions.append(
                {
                    "kind": "INITIAL_MINIMAP_AXIS_AMBIGUITY_DETECTED",
                    "heading_source": heading_source,
                    "reason": (
                        "route_tangent_cannot_flip_physical_avatar;_preserve_"
                        "observed_end_and_require_rmb_pivot_plus_displacement_probe"
                    ),
                    "execution_authority": False,
                }
            )
        _, _, world_x, world_y = _position(
            observation,
            expected_zone_index=args.expected_zone_index,
            transform=transform,
            expected_map_id=args.map_id,
        )
        progress_gate.reset(
            path_progress_world=0.0,
            goal_distance_world=hypot(goal_x - world_x, goal_y - world_y),
        )
        reset_required = (
            ordered_goal_queue_active
            and not corridor.complete
            and corridor.stop.distance_2d(NavPoint(goal_x, goal_y, corridor.stop.z))
            > local_goal_radius
        )
        search_vantage_rejected = (
            args.require_open_search_vantage and search_vantage_rejection is not None
        )
        status = (
            "SEARCH_VANTAGE_REJECTED"
            if search_vantage_rejected
            else "RESET_REQUIRED"
            if reset_required
            else "CONTROL_FRAME_BUDGET_EXHAUSTED"
        )
        last_observed_s = float(observation["timing"]["observed_monotonic_s"])
        initial_camera_intent = camera_pivot.observe(
            observed_monotonic_s=last_observed_s,
            physical_surfaces=nearest_navmesh_physical_surfaces(
                corridor.polygons,
                world_x=world_x,
                world_y=world_y,
            ),
        )
        if initial_camera_intent is not None:
            motion.release_all()
            _apply_camera_pivot_intent(
                backend,
                initial_camera_intent,
                hwnd=int(str(receipt["hwnd"]), 16),
            )
            actions.append(
                {
                    "kind": "CAMERA_PIVOT_PROFILE",
                    "mode": initial_camera_intent.mode,
                    "restore_composition": initial_camera_intent.restore_composition,
                    "reason": initial_camera_intent.reason,
                }
            )
            observation = pose_source.next_observation()
            _, _, world_x, world_y = _position(
                observation,
                expected_zone_index=args.expected_zone_index,
                transform=transform,
                expected_map_id=args.map_id,
            )
            observe_traversal(NavPoint(world_x, world_y, current_z_hint))
            last_observed_s = float(observation["timing"]["observed_monotonic_s"])
        # Before binding the short-lived F4a arm, publish one explicit
        # read-only diagnosis of the four live dependencies: current pose,
        # visible actor/camera, current heading, and exact foreground target.
        # This makes a live stop explainable without pretending that a clean
        # offline route proves client input.
        live_preflight_record: dict[str, object] | None = None
        live_preflight_ready = False
        foreground_matches_target: bool | None = None
        foreground_preflight_error: str | None = None
        try:
            hot_snapshot = keyboard.inspect_hot_target()
            foreground_matches_target = _hot_target_matches_target(
                hot_snapshot,
                target,
            )
            if not foreground_matches_target:
                foreground_preflight_error = "hot_target_snapshot_mismatch"
        except Exception as error:
            # A read-only diagnostic failure is recorded as unavailable; it
            # must never be converted into permission to submit input.
            foreground_preflight_error = (
                f"{type(error).__name__}:{str(error)[:128]}"
            )
        live_preflight_record = build_live_preflight_record(
            observation=observation,
            camera_integrity=getattr(pose_source, "latest_camera_integrity", None),
            heading_rad=heading,
            heading_source=heading_source,
            client_facing_source=getattr(
                pose_source,
                "latest_facing_source",
                "UNAVAILABLE",
            ),
            now_monotonic_s=time.monotonic(),
            capture_latency_ms=getattr(
                pose_source,
                "last_capture_latency_ms",
                None,
            ),
            observation_latency_ms=getattr(
                pose_source,
                "last_observation_latency_ms",
                None,
            ),
            foreground_matches_target=foreground_matches_target,
            evidence_refs=(
                "capture:coordinate_hud",
                "capture:player_actor_anchor",
                f"run:{run_id}",
            ),
            capture_origin="window_capture",
            maximum_observation_age_ms=MAXIMUM_CONTROL_OBSERVATION_AGE_MS,
            require_exact_body_heading=args.require_exact_body_heading,
            require_visible_player_anchor=args.require_player_anchor,
        )
        live_preflight_validator.validate(live_preflight_record)
        live_preflight_ready = bool(live_preflight_record["ready"])
        preflight_action = dict(live_preflight_record)
        preflight_action["kind"] = "LIVE_OBSERVATION_PREFLIGHT"
        if foreground_preflight_error is not None:
            preflight_action["foreground_preflight_error"] = (
                foreground_preflight_error
            )
        actions.append(preflight_action)
        print(
            json.dumps(
                {
                    "record_type": "continuous_motion_preflight",
                    "schema_version": "0.1",
                    "status": (
                        "PREFLIGHT_READY"
                        if live_preflight_ready
                        else "PREFLIGHT_REJECTED"
                    ),
                    "live_observation_preflight": live_preflight_record,
                    "execution_authority": False,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if (
            not live_preflight_ready
            and not reset_required
            and not search_vantage_rejected
        ):
            status = "LIVE_PREFLIGHT_REJECTED"
        if (
            not reset_required
            and not search_vantage_rejected
            and live_preflight_ready
        ):
            if args.runtime_arm_wait_seconds > 0.0:
                print(
                    json.dumps(
                        {
                            "record_type": "continuous_motion_preflight",
                            "schema_version": "0.1",
                            "status": "PREFLIGHT_READY",
                            "wait_seconds": args.runtime_arm_wait_seconds,
                            "reason": "read_only_world_and_route_planning_complete",
                            "execution_authority": False,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            try:
                continuous_authority = (
                    _load_runtime_motion_authority_after_preflight(
                        arm_file=args.continuous_motion_arm_file,
                        authorization_raw=continuous_authorization_raw,
                        session_receipt_raw=args.session_receipt.read_bytes(),
                        realm_revalidation_file=args.continuous_motion_revalidation_file,
                        target=target,
                        clock=clock,
                        schema_path=CONTINUOUS_MOTION_ARM_SCHEMA,
                        authorization_schema_path=AUTHORIZATION_SCHEMA,
                        wait_seconds=args.runtime_arm_wait_seconds,
                    )
                )
            except (OSError, ValueError, TypeError, KeyError) as error:
                raise SystemExit(
                    f"invalid continuous motion runtime arm after preflight: {error}"
                ) from error
            motion = ContinuousMotionExecutionGateway(
                authority=continuous_authority,
                target=target,
                backend=backend,
                clock=clock,
            )
            next_motion_authority_refresh_s = time.monotonic() + 0.250
            last_motion_authority_refresh_error: str | None = None
            actions.append(
                {
                    "kind": "CONTINUOUS_MOTION_ARM_BOUND_AFTER_PREFLIGHT",
                    "wait_seconds": args.runtime_arm_wait_seconds,
                    "reason": "bind_short_lived_F4a_only_after_read_only_planning",
                    "execution_authority": True,
                }
            )
        # Do not publish a misleading RUNNING checkpoint when the read-only
        # live preflight rejected the observation.  The movement loop is
        # intentionally skipped in that case, so the continuity state must
        # expose the same fail-closed reason to the supervisor/operator.
        publish_continuity(
            "RESET_REQUIRED"
            if reset_required
            else "SEARCH_VANTAGE_REJECTED"
            if search_vantage_rejected
            else "RUNNING"
            if live_preflight_ready
            else "LIVE_PREFLIGHT_REJECTED"
        )
        while (
            not reset_required
            and not search_vantage_rejected
            and live_preflight_ready
            and control_frames < args.max_control_frames
            and not cancelled
        ):
            cycle_previous_observed_s = last_observed_s
            cycle_checkpoints = [("loop_entry", time.monotonic())]
            current_direction_probe_signature = _corridor_direction_probe_signature(
                corridor,
                goal_x=goal_x,
                goal_y=goal_y,
            )
            if current_direction_probe_signature != direction_probe_signature:
                heading_estimator.reset(x=world_x, y=world_y)
                direction_probe_signature = current_direction_probe_signature
                initial_direction_probe_pending = True
                initial_direction_probe_realignment_count = 0
                live_heading_divergence_realignment_count = 0
                actions.append(
                    {
                        "kind": "INITIAL_FORWARD_DIRECTION_PROBE_ARMED",
                        "goal_world": [goal_x, goal_y],
                        "reason": "new_validated_corridor_or_semantic_handoff",
                        "execution_authority": False,
                    }
                )
            try:
                resumed = (
                    False
                    if run_control is None
                    else run_control.checkpoint(motion.release_all)
                )
            except OperatorStopRequested:
                motion.release_all()
                status = "OPERATOR_STOPPED"
                break
            if resumed:
                observation = pose_source.next_observation()
                _, _, world_x, world_y = _position(
                    observation,
                    expected_zone_index=args.expected_zone_index,
                    transform=transform,
                    expected_map_id=args.map_id,
                )
                heading, heading_source = _observe_player_heading(
                    pose_source,
                    visible_heading_observer,
                    predicted_heading_rad=heading,
                    observation=observation,
                    displacement_heading_rad=None,
                )
                last_observed_s = float(observation["timing"]["observed_monotonic_s"])
                no_progress_s = 0.0
                pivot_without_heading_progress_s = 0.0
                pivot_heading_error_anchor_rad = None
                progress_gate.reset(
                    path_progress_world=0.0,
                    goal_distance_world=hypot(goal_x - world_x, goal_y - world_y),
                )
                continue

            if (
                args.semantic_destination_id is not None
                and _semantic_destination_reached(
                    world_x=world_x,
                    world_y=world_y,
                    destination_x=destination_x,
                    destination_y=destination_y,
                    radius_world=semantic_destination_radius,
                )
            ):
                motion.release_all()
                status = "ARRIVED"
                actions.append(
                    {
                        "kind": "SEMANTIC_DESTINATION_RADIUS_REACHED",
                        "destination_id": args.semantic_destination_id,
                        "world_x": world_x,
                        "world_y": world_y,
                        "destination_world": [destination_x, destination_y],
                        "radius_world": semantic_destination_radius,
                        "reason": "catalog_area_reached_without_exact_point_chasing",
                    }
                )
                break

            camera_intent = camera_pivot.observe(
                observed_monotonic_s=last_observed_s,
                physical_surfaces=nearest_navmesh_physical_surfaces(
                    corridor.polygons,
                    world_x=world_x,
                    world_y=world_y,
                ),
            )
            if camera_intent is not None:
                # Chat-driven CVar/view restoration takes 250-500 ms and used
                # to release W in the middle of a bridge/WMO transition.  The
                # native Smart Pivot remains active throughout navigation, so
                # retain only the newest presentation profile and apply it
                # after movement has already stopped for its terminal status.
                deferred_camera_intent = camera_intent
                actions.append(
                    {
                        "kind": "CAMERA_PIVOT_PROFILE_DEFERRED",
                        "mode": camera_intent.mode,
                        "restore_composition": camera_intent.restore_composition,
                        "reason": camera_intent.reason,
                        "world_x": world_x,
                        "world_y": world_y,
                        "execution_authority": False,
                    }
                )

            if local_recovery_attempts > 0 and _recovery_budget_can_reset(
                world_x=world_x,
                world_y=world_y,
                last_collision_world=last_recovery_collision_world,
            ):
                assert last_recovery_collision_world is not None
                actions.append(
                    {
                        "kind": "LOCAL_RECOVERY_BUDGET_RESET",
                        "world_x": world_x,
                        "world_y": world_y,
                        "distance_from_last_collision_world": hypot(
                            world_x - last_recovery_collision_world[0],
                            world_y - last_recovery_collision_world[1],
                        ),
                        "reason": "new_obstacle_neighborhood_after_proven_progress",
                    }
                )
                local_recovery_attempts = 0
                last_recovery_collision_world = None

            # Roll the semantic horizon forward before the current road point
            # falls behind the actor.  The isolated Detour worker is slower
            # than one control lease, so run it in parallel while the current
            # corridor remains authoritative.  Handover is allowed only after
            # the complete next corridor is already proven.
            has_next_semantic_goal = (
                structure_resume_goal is None
                and ordered_goal_queue_active
                and semantic_goal_index + 1 < len(semantic_goals)
            )
            remaining_current_semantic_goal = hypot(
                goal_x - world_x,
                goal_y - world_y,
            )
            next_semantic_goal_index = semantic_goal_index + 1
            if (
                semantic_frontier_preplan_future is not None
                and semantic_frontier_preplan_query is not query
            ):
                semantic_frontier_preplan_future.cancel()
                semantic_frontier_preplan_future = None
                semantic_frontier_preplan_query = None
                semantic_frontier_preplan_goal_index = None
                semantic_frontier_preplan_start = None
                semantic_frontier_preplan_candidates = ()
                semantic_frontier_preplan_result_materialized = False
            if (
                corridor_recenter_preplan_future is not None
                and corridor_recenter_preplan_query is not query
            ):
                corridor_recenter_preplan_future.cancel()
                corridor_recenter_preplan_future = None
                corridor_recenter_preplan_query = None
                corridor_recenter_preplan_start = None
                corridor_recenter_preplan_goal = None
            # Apply only completed WMO baseline evidence.  ``Future.result``
            # is safe here because ``done()`` is true; an in-flight native
            # query never stalls the pose/control clock.
            for candidate, baseline_future in tuple(wmo_baseline_futures.items()):
                if not baseline_future.done():
                    continue
                wmo_baseline_futures.pop(candidate, None)
                current_index, next_index = wmo_baseline_context.pop(
                    candidate,
                    (semantic_goal_index, next_semantic_goal_index),
                )
                try:
                    baseline_passed = bool(baseline_future.result())
                except BaseException:
                    baseline_passed = False
                if not baseline_passed or candidate not in observed_blockers:
                    if not baseline_passed:
                        actions.append(
                            {
                                "kind": "SEMANTIC_HORIZON_WMO_BASELINE_REJECTED",
                                "blocker_world": list(candidate),
                                "current_waypoint_index": current_index,
                                "next_waypoint_index": next_index,
                                "reason": "baseline_corridor_not_complete",
                                "execution_authority": False,
                            }
                        )
                    continue
                observed_blockers = tuple(
                    item for item in observed_blockers if item != candidate
                )
                wmo_baseline_proven_for_goal.add((candidate, next_index))
                query = ClientAssetNavmeshQuery(
                    worker=args.worker,
                    nav_root=args.nav_root,
                    observed_blockers=observed_blockers,
                )
                engine.navigator = query
                # A preplan launched with the old blocker set is stale.  It
                # is cancelled without waiting; the next frame may submit a
                # replacement against the filtered evidence.
                if semantic_preplan_future is not None:
                    semantic_preplan_future.cancel()
                    semantic_preplan_future = None
                    semantic_preplan_goal_index = None
                    semantic_preplan_query = None
                    semantic_preplan_failed_goal_index = None
                    semantic_preview_goal_index = None
                actions.append(
                    {
                        "kind": "SEMANTIC_HORIZON_WMO_BASELINE_PASS",
                        "blocker_world": list(candidate),
                        "current_waypoint_index": current_index,
                        "next_waypoint_index": next_index,
                        "reason": "complete_client_navmesh_leg_without_new_wmo_exclusion",
                        "asynchronous": True,
                        "execution_authority": False,
                    }
                )
            if (
                semantic_preplan_future is not None
                and semantic_preplan_query is not query
            ):
                semantic_preplan_future.cancel()
                if semantic_refinement_preplan_future is not None:
                    semantic_refinement_preplan_future.cancel()
                semantic_preplan_future = None
                semantic_preplan_goal_index = None
                semantic_preplan_query = None
                semantic_preplan_failed_goal_index = None
                semantic_refinement_preplan_future = None
                semantic_refinement_preplan_point = None
            if (
                _semantic_should_preplan(
                    remaining_world=remaining_current_semantic_goal,
                    has_next=has_next_semantic_goal,
                    radius_world=SEMANTIC_RUNTIME_PREPLAN_RADIUS_WORLD,
                )
                and corridor.complete
                and semantic_preplan_future is None
                and semantic_preplan_failed_goal_index != next_semantic_goal_index
            ):
                next_goal = semantic_goals[next_semantic_goal_index]
                if structure_spatial is not None:
                    (
                        horizon_blocked_obstacles,
                        added_horizon_blockers,
                    ) = _merge_static_structure_horizon_blockers(
                        structures=structure_spatial,
                        observed_blockers=observed_blockers,
                        start=NavPoint(goal_x, goal_y, corridor.stop.z),
                        goals=(next_goal,),
                    )
                    (
                        horizon_blocked_obstacles,
                        added_horizon_blockers,
                    ) = _suppress_proven_wmo_horizon_blockers(
                        horizon_blockers=horizon_blocked_obstacles,
                        added_blockers=added_horizon_blockers,
                        proven_for_goal=wmo_baseline_proven_for_goal,
                        next_waypoint_index=next_semantic_goal_index,
                    )
                    if added_horizon_blockers:
                        observed_blockers = horizon_blocked_obstacles
                        query = ClientAssetNavmeshQuery(
                            worker=args.worker,
                            nav_root=args.nav_root,
                            observed_blockers=observed_blockers,
                        )
                        engine.navigator = query
                        for candidate in added_horizon_blockers:
                            if candidate in wmo_baseline_futures:
                                continue
                            hits = structure_spatial.nearby(
                                x=candidate[0],
                                y=candidate[1],
                                z=candidate[2],
                                radius_yards=0.5,
                                kinds=("WMO",),
                            )
                            if not hits:
                                continue
                            baseline_blockers = tuple(
                                item
                                for item in horizon_blocked_obstacles
                                if item != candidate
                            )
                            wmo_baseline_futures[candidate] = (
                                semantic_advisory_executor.submit(
                                    _wmo_baseline_reaches_local_goal_in_worker_process,
                                    worker_path=str(args.worker),
                                    nav_root_path=str(args.nav_root),
                                    observed_blockers=baseline_blockers,
                                    map_name=active_map_name,
                                    start=NavPoint(
                                        goal_x,
                                        goal_y,
                                        corridor.stop.z,
                                    ),
                                    stop_x=next_goal.x,
                                    stop_y=next_goal.y,
                                    local_goal_radius=local_goal_radius,
                                )
                            )
                            wmo_baseline_context[candidate] = (
                                semantic_goal_index,
                                next_semantic_goal_index,
                            )
                            actions.append(
                                {
                                    "kind": "SEMANTIC_HORIZON_WMO_BASELINE_STARTED",
                                    "blocker_world": list(candidate),
                                    "current_waypoint_index": semantic_goal_index,
                                    "next_waypoint_index": next_semantic_goal_index,
                                    "reason": "bounded_client_navmesh_baseline_in_worker",
                                    "execution_authority": False,
                                }
                            )
                        actions.append(
                            {
                                "kind": "SEMANTIC_HORIZON_STRUCTURE_BLOCKERS_CONSIDERED",
                                "count": len(added_horizon_blockers),
                                "current_waypoint_index": semantic_goal_index,
                                "next_waypoint_index": next_semantic_goal_index,
                                "source": "WORLD_PACK_STRUCTURE_INDEX_PLUS_DETOUR",
                                "execution_authority": False,
                            }
                        )
                semantic_preplan_goal_index = next_semantic_goal_index
                semantic_preplan_query = query
                preplan_arguments = {
                    "map_name": active_map_name,
                    # Both legs share this atlas-derived road point. Starting
                    # at the earlier live pose let the next query legally
                    # bypass the point and made hand-off bearings discontinuous.
                    "start": NavPoint(goal_x, goal_y, corridor.stop.z),
                    "stop_x": next_goal.x,
                    "stop_y": next_goal.y,
                }
                if args.steering_controller == "continuous_trajectory_v1":
                    semantic_preplan_future = semantic_preplan_executor.submit(
                        _semantic_preplan_in_worker_process,
                        worker_path=str(args.worker),
                        nav_root_path=str(args.nav_root),
                        observed_blockers=observed_blockers,
                        prepare_trajectory=True,
                        **preplan_arguments,
                    )
                else:
                    semantic_preplan_future = semantic_preplan_executor.submit(
                        _semantic_preplan_in_worker_process,
                        worker_path=str(args.worker),
                        nav_root_path=str(args.nav_root),
                        observed_blockers=observed_blockers,
                        prepare_trajectory=False,
                        **preplan_arguments,
                    )
                if semantic_refinement_preplan_future is not None:
                    semantic_refinement_preplan_future.cancel()
                semantic_refinement_preplan_future = None
                semantic_refinement_preplan_point = None
                speculative_refinement = (
                    None
                    if semantic_route is None
                    else _semantic_refinement_midpoint(
                        route=semantic_route,
                        start_x=goal_x,
                        start_y=goal_y,
                        target_x=next_goal.x,
                        target_y=next_goal.y,
                        minimum_route_index=semantic_route_progress_index,
                    )
                )
                if speculative_refinement is not None:
                    _, speculative_point = speculative_refinement
                    if hypot(
                        speculative_point.x - next_goal.x,
                        speculative_point.y - next_goal.y,
                    ) > 0.05:
                        speculative_arguments = {
                            "map_name": active_map_name,
                            "start": NavPoint(goal_x, goal_y, corridor.stop.z),
                            "stop_x": speculative_point.x,
                            "stop_y": speculative_point.y,
                        }
                        if args.steering_controller == "continuous_trajectory_v1":
                            semantic_refinement_preplan_future = (
                                semantic_advisory_executor.submit(
                                    _semantic_preplan_in_worker_process,
                                    worker_path=str(args.worker),
                                    nav_root_path=str(args.nav_root),
                                    observed_blockers=observed_blockers,
                                    prepare_trajectory=True,
                                    **speculative_arguments,
                                )
                            )
                        else:
                            semantic_refinement_preplan_future = (
                                semantic_advisory_executor.submit(
                                    _semantic_preplan_in_worker_process,
                                    worker_path=str(args.worker),
                                    nav_root_path=str(args.nav_root),
                                    observed_blockers=observed_blockers,
                                    prepare_trajectory=False,
                                    **speculative_arguments,
                                )
                            )
                        semantic_refinement_preplan_point = speculative_point
                actions.append(
                    {
                        "kind": "SEMANTIC_CORRIDOR_PREPLAN_STARTED",
                        "current_waypoint_index": semantic_goal_index,
                        "next_waypoint_index": next_semantic_goal_index,
                        "world_x": world_x,
                        "world_y": world_y,
                        "remaining_current_world": remaining_current_semantic_goal,
                        "shared_start_x": goal_x,
                        "shared_start_y": goal_y,
                    }
                )
            next_corridor_ready = (
                semantic_preplan_future is not None
                and semantic_preplan_goal_index == next_semantic_goal_index
                and semantic_preplan_query is query
                and semantic_preplan_future.done()
            )
            if next_corridor_ready and semantic_route is not None:
                assert semantic_preplan_future is not None
                try:
                    refinement_corridor, _ = _unpack_preplanned_corridor(
                        semantic_preplan_future.result()
                    )
                except BaseException:
                    refinement_corridor = None
                if refinement_corridor is not None:
                    next_goal = semantic_goals[next_semantic_goal_index]
                    refinement = _semantic_corridor_refinement(
                        route=semantic_route,
                        corridor=refinement_corridor,
                        start_x=goal_x,
                        start_y=goal_y,
                        target_x=next_goal.x,
                        target_y=next_goal.y,
                        minimum_route_index=semantic_route_progress_index,
                    )
                    if refinement is not None:
                        (
                            refinement_route_index,
                            refinement_goal,
                            maximum_route_deviation,
                            route_stretch,
                        ) = refinement
                        semantic_goals.insert(
                            next_semantic_goal_index,
                            refinement_goal,
                        )
                        actions.append(
                            {
                                "kind": "SEMANTIC_CORRIDOR_REFINED",
                                "route_waypoint_index": refinement_route_index,
                                "requested_x": refinement_goal.x,
                                "requested_y": refinement_goal.y,
                                "deferred_x": next_goal.x,
                                "deferred_y": next_goal.y,
                                "maximum_route_deviation_world": (
                                    maximum_route_deviation
                                ),
                                "route_stretch": route_stretch,
                                "reason": (
                                    "long_local_chord_left_selected_semantic_surface"
                                ),
                                "execution_authority": False,
                            }
                        )
                        reuse_speculative = (
                            semantic_refinement_preplan_future is not None
                            and semantic_refinement_preplan_point is not None
                            and hypot(
                                semantic_refinement_preplan_point.x
                                - refinement_goal.x,
                                semantic_refinement_preplan_point.y
                                - refinement_goal.y,
                            )
                            <= 0.05
                        )
                        if reuse_speculative:
                            semantic_preplan_future = (
                                semantic_refinement_preplan_future
                            )
                            semantic_preplan_goal_index = next_semantic_goal_index
                            semantic_preplan_query = query
                        else:
                            if semantic_refinement_preplan_future is not None:
                                semantic_refinement_preplan_future.cancel()
                            semantic_preplan_future = None
                            semantic_preplan_goal_index = None
                            semantic_preplan_query = None
                        semantic_refinement_preplan_future = None
                        semantic_refinement_preplan_point = None
                        semantic_preplan_failed_goal_index = None
                        semantic_preview_goal_index = None
                        semantic_handoff_cache.clear()
                        next_corridor_ready = bool(
                            reuse_speculative
                            and semantic_preplan_future is not None
                            and semantic_preplan_future.done()
                        )
            steering_corridor = corridor
            if next_corridor_ready:
                assert semantic_preplan_future is not None
                try:
                    (
                        preview_continuation,
                        preview_trajectory,
                    ) = _unpack_preplanned_corridor(
                        semantic_preplan_future.result()
                    )
                except BaseException:
                    preview_continuation = None
                    preview_trajectory = None
                if preview_continuation is not None:
                    next_goal = semantic_goals[next_semantic_goal_index]
                    if _corridor_reaches_local_goal(
                        preview_continuation,
                        goal_x=next_goal.x,
                        goal_y=next_goal.y,
                        radius_world=local_goal_radius,
                    ):
                        joined_preview = _joined_semantic_preview_corridor(
                            corridor,
                            preview_continuation,
                        )
                        if joined_preview is not None:
                            steering_corridor = joined_preview
                            if semantic_preview_goal_index != next_semantic_goal_index:
                                if preview_trajectory is not None:
                                    actions.append(
                                        {
                                            "kind": "CONTINUOUS_TRAJECTORY_PREPARED",
                                            "phase": "semantic_preplan",
                                            "smoothed_guidance_point_count": len(
                                                preview_trajectory.points
                                            ),
                                            "rounded_corner_count": (
                                                preview_trajectory.rounded_corner_count
                                            ),
                                            "rejected_corner_count": (
                                                preview_trajectory.rejected_corner_count
                                            ),
                                            "navmesh_validation_count": (
                                                preview_trajectory.validation_count
                                            ),
                                            "execution_authority": False,
                                        }
                                    )
                                actions.append(
                                    {
                                        "kind": "SEMANTIC_ROLLING_PREVIEW_READY",
                                        "current_waypoint_index": semantic_goal_index,
                                        "next_waypoint_index": next_semantic_goal_index,
                                        "joined_guidance_point_count": len(
                                            joined_preview.guidance_points()
                                        ),
                                        "reason": "generic_multi_corridor_curve_lookahead",
                                    }
                                )
                                semantic_preview_goal_index = next_semantic_goal_index
            if (
                structure_resume_goal is not None
                and structure_egress_continuation is not None
            ):
                structure_preview = _joined_semantic_preview_corridor(
                    corridor,
                    structure_egress_continuation,
                )
                if structure_preview is not None:
                    steering_corridor = structure_preview
                remaining_structure_egress = hypot(
                    goal_x - world_x,
                    goal_y - world_y,
                )
                if (
                    structure_egress_continuation.complete
                    and remaining_structure_egress <= SEMANTIC_FLYBY_RADIUS_WORLD
                    and _semantic_handoff_is_continuous(
                        structure_egress_continuation,
                        world_x=world_x,
                        world_y=world_y,
                        heading_rad=heading,
                    )
                ):
                    reached_opening = structure_egress_opening_id
                    deferred_goal = structure_resume_goal
                    prepared_continuation = structure_egress_continuation
                    goal_x, goal_y = deferred_goal
                    structure_resume_goal = None
                    structure_egress_opening_id = None
                    structure_egress_continuation = None
                    corridor = prepared_continuation
                    engine.steering = mission_steering
                    actions.append(
                        {
                            "kind": "STRUCTURE_EGRESS_FLYBY",
                            "opening_id": reached_opening,
                            "world_x": world_x,
                            "world_y": world_y,
                            "remaining_to_opening_world": (remaining_structure_egress),
                            "resumed_goal_world": [goal_x, goal_y],
                            "reason": (
                                "prevalidated_structure_continuation_handed_off_"
                                "without_stop_pulse"
                            ),
                            "execution_authority": False,
                        }
                    )
                    no_progress_s = 0.0
                    pivot_without_heading_progress_s = 0.0
                    pivot_heading_error_anchor_rad = None
                    partial_replans = 0
                    progress_gate.reset(
                        path_progress_world=0.0,
                        goal_distance_world=hypot(
                            goal_x - world_x,
                            goal_y - world_y,
                        ),
                    )
                    # Input remains continuously leased; the next fresh frame
                    # adjusts W+RMB against the already-proven continuation.
                    continue
            if _semantic_should_fly_by(
                remaining_world=remaining_current_semantic_goal,
                has_next=has_next_semantic_goal,
                next_corridor_ready=next_corridor_ready,
            ):
                assert semantic_preplan_future is not None
                try:
                    prepared_corridor, _ = _unpack_preplanned_corridor(
                        semantic_preplan_future.result()
                    )
                except BaseException as error:
                    actions.append(
                        {
                            "kind": "SEMANTIC_CORRIDOR_PREPLAN_REJECTED",
                            "next_waypoint_index": next_semantic_goal_index,
                            "reason": type(error).__name__,
                        }
                    )
                    semantic_preplan_failed_goal_index = next_semantic_goal_index
                else:
                    next_goal = semantic_goals[next_semantic_goal_index]
                    if _corridor_reaches_local_goal(
                        prepared_corridor,
                        goal_x=next_goal.x,
                        goal_y=next_goal.y,
                        radius_world=local_goal_radius,
                    ) and _semantic_handoff_is_continuous(
                        prepared_corridor,
                        world_x=world_x,
                        world_y=world_y,
                        heading_rad=heading,
                    ):
                        actions.append(
                            {
                                "kind": "SEMANTIC_WAYPOINT_FLYBY",
                                "waypoint_index": semantic_goal_index,
                                "world_x": world_x,
                                "world_y": world_y,
                                "requested_x": goal_x,
                                "requested_y": goal_y,
                                "remaining_world": remaining_current_semantic_goal,
                                "next_waypoint_index": next_semantic_goal_index,
                                "reason": "shared_point_detour_handoff_with_continuous_heading",
                            }
                        )
                        semantic_goal_index = next_semantic_goal_index
                        goal_x, goal_y = next_goal.x, next_goal.y
                        attempted_structure_egress_ids.clear()
                        corridor = prepared_corridor
                        no_progress_s = 0.0
                        pivot_without_heading_progress_s = 0.0
                        pivot_heading_error_anchor_rad = None
                        partial_replans = 0
                        progress_gate.reset(
                            path_progress_world=0.0,
                            goal_distance_world=hypot(
                                goal_x - world_x,
                                goal_y - world_y,
                            ),
                        )
                        semantic_preplan_future = None
                        semantic_preplan_goal_index = None
                        semantic_preplan_query = None
                        semantic_preplan_failed_goal_index = None
                        semantic_preview_goal_index = None
                        if semantic_frontier_preplan_future is not None:
                            semantic_frontier_preplan_future.cancel()
                        semantic_frontier_preplan_future = None
                        semantic_frontier_preplan_query = None
                        semantic_frontier_preplan_goal_index = None
                        semantic_frontier_preplan_start = None
                        semantic_frontier_preplan_candidates = ()
                        if corridor_recenter_preplan_future is not None:
                            corridor_recenter_preplan_future.cancel()
                        corridor_recenter_preplan_future = None
                        corridor_recenter_preplan_query = None
                        corridor_recenter_preplan_start = None
                        corridor_recenter_preplan_goal = None
                        if semantic_refinement_preplan_future is not None:
                            semantic_refinement_preplan_future.cancel()
                        semantic_refinement_preplan_future = None
                        semantic_refinement_preplan_point = None
                        # The previously held continuous input remains leased;
                        # the next fresh frame adjusts it without a stop pulse.
                        continue
                    actions.append(
                        {
                            "kind": "SEMANTIC_CORRIDOR_PREPLAN_REJECTED",
                            "next_waypoint_index": next_semantic_goal_index,
                            "reason": (
                                "next_corridor_is_partial_or_misses_local_goal"
                                if not _corridor_reaches_local_goal(
                                    prepared_corridor,
                                    goal_x=next_goal.x,
                                    goal_y=next_goal.y,
                                    radius_world=local_goal_radius,
                                )
                                else "next_corridor_heading_or_cross_track_is_discontinuous"
                            ),
                        }
                    )
                    # The corridor is already complete and reaches the next
                    # semantic point.  It was rejected only for a fly-by at
                    # the actor's current heading/cross-track.  Preserve it
                    # for the exact shared-point handoff instead of throwing
                    # away valid Detour work and synchronously querying the
                    # same leg a second time after ARRIVED.
                    if _corridor_reaches_local_goal(
                        prepared_corridor,
                        goal_x=next_goal.x,
                        goal_y=next_goal.y,
                        radius_world=local_goal_radius,
                    ):
                        semantic_handoff_cache[next_semantic_goal_index] = (
                            prepared_corridor
                        )
                    semantic_preplan_failed_goal_index = next_semantic_goal_index
                semantic_preplan_future = None
                semantic_preplan_goal_index = None
                semantic_preplan_query = None
                semantic_preview_goal_index = None
                if semantic_refinement_preplan_future is not None:
                    semantic_refinement_preplan_future.cancel()
                semantic_refinement_preplan_future = None
                semantic_refinement_preplan_point = None
            # If the current Detour corridor is partial, prepare the bounded
            # forward atlas samples from its proven frontier.  This work is
            # deliberately independent of the normal next-goal preplan: a
            # partial corridor may still be the authoritative road leg while
            # the first complete bypass is being validated in the worker.
            frontier_preplan_needed = (
                ordered_goal_queue_active
                and structure_resume_goal is None
                and semantic_route is not None
                and not corridor.complete
                and corridor.stop.distance_2d(
                    NavPoint(goal_x, goal_y, corridor.stop.z)
                )
                > local_goal_radius
                and semantic_goal_index < len(semantic_goals)
            )
            if not frontier_preplan_needed:
                if semantic_frontier_preplan_future is not None:
                    semantic_frontier_preplan_future.cancel()
                semantic_frontier_preplan_future = None
                semantic_frontier_preplan_query = None
                semantic_frontier_preplan_goal_index = None
                semantic_frontier_preplan_start = None
                semantic_frontier_preplan_candidates = ()
            elif semantic_frontier_preplan_future is None:
                bypass_limit = semantic_goals[
                    min(semantic_goal_index + 1, len(semantic_goals) - 1)
                ]
                frontier_candidates: list[tuple[int, float, float]] = []
                for route_index, candidate in _semantic_forward_bypass_candidates(
                    route=semantic_route,
                    start_x=world_x,
                    start_y=world_y,
                    blocked_target_x=goal_x,
                    blocked_target_y=goal_y,
                    limit_x=bypass_limit.x,
                    limit_y=bypass_limit.y,
                    minimum_route_index=semantic_route_progress_index,
                    maximum_forward_waypoints=SEMANTIC_STATIC_FRONTIER_MAX_FORWARD_WAYPOINTS,
                ):
                    if _semantic_goal_overlaps_static_structure(
                        structures=structure_spatial,
                        goal=candidate,
                        z=current_z_hint,
                    ):
                        continue
                    frontier_candidates.append((route_index, candidate.x, candidate.y))
                if frontier_candidates:
                    frontier_start = NavPoint(
                        corridor.stop.x,
                        corridor.stop.y,
                        corridor.stop.z,
                    )
                    semantic_frontier_preplan_future = (
                        semantic_frontier_preplan_executor.submit(
                            _semantic_forward_bypass_in_worker_process,
                            worker_path=str(args.worker),
                            nav_root_path=str(args.nav_root),
                            observed_blockers=observed_blockers,
                            map_name=active_map_name,
                            start=frontier_start,
                            candidates=tuple(frontier_candidates),
                            local_goal_radius=local_goal_radius,
                        )
                    )
                    semantic_frontier_preplan_query = query
                    semantic_frontier_preplan_goal_index = semantic_goal_index
                    semantic_frontier_preplan_start = frontier_start
                    semantic_frontier_preplan_candidates = tuple(frontier_candidates)
                    semantic_frontier_preplan_result_materialized = False
                    actions.append(
                        {
                            "kind": "SEMANTIC_STATIC_FRONTIER_BYPASS_PREPLAN_STARTED",
                            "semantic_goal_index": semantic_goal_index,
                            "frontier_world": [
                                frontier_start.x,
                                frontier_start.y,
                                frontier_start.z,
                            ],
                            "candidate_count": len(frontier_candidates),
                            "reason": "ordered_route_candidates_validated_off_control_loop",
                            "execution_authority": False,
                        }
                    )
            # ProcessPoolExecutor completes the native query in a child, but
            # the first ``Future.result()`` can still pay result handoff and
            # object materialization on the control thread. Consume a ready
            # frontier result while the current corridor is still active so
            # that the semantic handoff cannot create a stationary freshness
            # gap at the frontier. The result is consumed again later only as
            # a zero-cost read from the already materialized Future.
            if (
                semantic_frontier_preplan_future is not None
                and not semantic_frontier_preplan_result_materialized
                and semantic_frontier_preplan_future.done()
            ):
                materialize_started_s = time.monotonic()
                try:
                    semantic_frontier_preplan_future.result()
                    materialize_status = "READY"
                except BaseException:
                    materialize_status = "FAILED"
                semantic_frontier_preplan_result_materialized = True
                actions.append(
                    {
                        "kind": "SEMANTIC_STATIC_FRONTIER_BYPASS_RESULT_MATERIALIZED",
                        "semantic_goal_index": semantic_frontier_preplan_goal_index,
                        "duration_ms": round(
                            (time.monotonic() - materialize_started_s) * 1000.0,
                            3,
                        ),
                        "status": materialize_status,
                        "reason": "consume_ready_frontier_result_before_handoff",
                        "execution_authority": False,
                    }
                )
            cycle_checkpoints.append(("planning", time.monotonic()))
            local_sample = live_awareness.poll(
                world_x=world_x,
                world_y=world_y,
                now_s=time.monotonic(),
                z_hint=current_z_hint,
            )
            if local_sample is not None:
                current_z_hint = local_sample.resolved.z
                steering_corridor = replace(
                    steering_corridor,
                    start_awareness=local_sample.awareness,
                    awareness_observed_monotonic_s=(local_sample.observed_monotonic_s),
                )
                if last_live_awareness_observed_s != local_sample.observed_monotonic_s:
                    actions.append(
                        {
                            "kind": "LIVE_LOCAL_AWARENESS_APPLIED",
                            "source_world": [
                                local_sample.source.x,
                                local_sample.source.y,
                                local_sample.source.z,
                            ],
                            "resolved_world": [
                                local_sample.resolved.x,
                                local_sample.resolved.y,
                                local_sample.resolved.z,
                            ],
                            "environment_class": (
                                local_sample.awareness.environment_class
                            ),
                            "physical_surfaces": sorted(
                                local_sample.awareness.physical_surfaces
                            ),
                            "wall_count": len(local_sample.awareness.wall_segments),
                            "transition_count": len(
                                local_sample.awareness.surface_transition_portals
                            ),
                            "egress_count": len(local_sample.awareness.egress_portals),
                            "service_pid": live_awareness.service_pid,
                            "query_count": live_awareness.query_count,
                            "applied_to_pose_observed_monotonic_s": last_observed_s,
                            "boundary_evidence": local_boundary_trace_record(
                                local_sample.awareness,
                                observed_monotonic_s=local_sample.observed_monotonic_s,
                            ),
                            "reason": (
                                "event_driven_client_asset_topology_at_live_pose"
                            ),
                            "execution_authority": False,
                        }
                    )
                    last_live_awareness_observed_s = local_sample.observed_monotonic_s
            cycle_checkpoints.append(("local_awareness", time.monotonic()))
            engine.observe_position(x=world_x, y=world_y, observed_at_s=last_observed_s)
            decision_state = SteeringState(world_x, world_y, heading, speed, no_progress_s)
            decision_observation = decision_observation_record(
                decision_state, observed_monotonic_s=last_observed_s,
                heading_source=heading_source,
            )
            intent = engine.decide(
                decision_state,
                steering_corridor,
            )
            initial_direction_replan_forced = False
            if initial_direction_replan_pending:
                # The first physical chord was useful heading evidence but it
                # also moved the actor away from the corridor's original start.
                initial_direction_replan_pending = False
                if (
                    intent.cross_track_error_world
                    >= INITIAL_DIRECTION_REPLAN_MIN_CROSS_TRACK_WORLD
                ):
                    # Request the existing clean corridor-recenter path only
                    # after the actor really left the validated corridor.  A
                    # small calibration offset keeps the old corridor and the
                    # controller's already-requested stationary pivot; this
                    # avoids a needless synchronous query in the live loop.
                    initial_direction_replan_forced = True
                    intent = SteeringIntent(
                        "REPLAN",
                        0,
                        0,
                        None,
                        "trajectory_loop_detected",
                        intent.progress_world,
                        intent.cross_track_error_world,
                        intent.projected_z_world,
                    )
                else:
                    actions.append(
                        {
                            "kind": "INITIAL_DIRECTION_CORRIDOR_REPLAN_SKIPPED",
                            "cross_track_error_world": intent.cross_track_error_world,
                            "threshold_world": (
                                INITIAL_DIRECTION_REPLAN_MIN_CROSS_TRACK_WORLD
                            ),
                            "reason": (
                                "calibration_offset_remained_inside_validated_"
                                "corridor;_stationary_pivot_kept_without_sync_query"
                            ),
                            "execution_authority": False,
                        }
                    )
            if intent.projected_z_world is not None:
                current_z_hint = intent.projected_z_world
            remaining_now = hypot(goal_x - world_x, goal_y - world_y)
            meaningful_progress = progress_gate.observe(
                path_progress_world=intent.progress_world,
                goal_distance_world=remaining_now,
            )
            if meaningful_progress:
                no_progress_s = 0.0
                corridor_recenter_replans = 0
                corridor_recenter_stall_evidence_s = 0.0
                if (
                    intent.state == "REPLAN"
                    and not initial_direction_replan_forced
                ):
                    decision_state = SteeringState(world_x, world_y, heading, speed, 0.0)
                    decision_observation = decision_observation_record(
                        decision_state, observed_monotonic_s=last_observed_s,
                        heading_source=heading_source,
                    )
                    intent = engine.decide(
                        decision_state,
                        steering_corridor,
                    )
            cycle_checkpoints.append(("steering", time.monotonic()))
            dynamic_tracks = dynamic_tracker.update(
                pose_source.latest_dynamic_observations,
                now_s=last_observed_s,
            )
            remember_dynamic_experience(
                dynamic_tracks,
                observer_x=world_x,
                observer_y=world_y,
                observer_facing_rad=heading,
            )
            dynamic_decision = dynamic_avoidance.decide(
                dynamic_tracks,
                now_s=last_observed_s,
                heading_rad=heading,
                static_awareness=steering_corridor.start_awareness,
            )
            intent = dynamic_avoidance.apply(
                intent,
                dynamic_decision,
                maximum_mouse_delta=(
                    PredictiveSteeringController.FOLLOW_MAX_MOUSE_DELTA
                ),
            )
            cycle_checkpoints.append(("dynamic_observation_and_memory", time.monotonic()))
            recenter_preplan_needed = (
                engine.steering is mission_steering
                and corridor.complete
                and intent.state != "REPLAN"
                and intent.cross_track_error_world
                >= CORRIDOR_RECENTER_PREPLAN_CROSS_TRACK_WORLD
            )
            if (
                corridor_recenter_preplan_future is not None
                and corridor_recenter_preplan_query is not query
            ):
                corridor_recenter_preplan_future.cancel()
                corridor_recenter_preplan_future = None
                corridor_recenter_preplan_query = None
                corridor_recenter_preplan_start = None
                corridor_recenter_preplan_goal = None
            if not recenter_preplan_needed:
                if corridor_recenter_preplan_future is not None:
                    corridor_recenter_preplan_future.cancel()
                corridor_recenter_preplan_future = None
                corridor_recenter_preplan_query = None
                corridor_recenter_preplan_start = None
                corridor_recenter_preplan_goal = None
            elif corridor_recenter_preplan_future is None:
                recenter_start = NavPoint(world_x, world_y, current_z_hint)
                corridor_recenter_preplan_future = semantic_preplan_executor.submit(
                    _semantic_preplan_in_worker_process,
                    worker_path=str(args.worker),
                    nav_root_path=str(args.nav_root),
                    observed_blockers=observed_blockers,
                    map_name=active_map_name,
                    start=recenter_start,
                    stop_x=goal_x,
                    stop_y=goal_y,
                    prepare_trajectory=(
                        args.steering_controller == "continuous_trajectory_v1"
                    ),
                )
                corridor_recenter_preplan_query = query
                corridor_recenter_preplan_start = recenter_start
                corridor_recenter_preplan_goal = (goal_x, goal_y)
                actions.append(
                    {
                        "kind": "CORRIDOR_RECENTER_PREPLAN_STARTED",
                        "world_x": world_x,
                        "world_y": world_y,
                        "goal_world": [goal_x, goal_y],
                        "cross_track_error_world": intent.cross_track_error_world,
                        "reason": "early_geometric_divergence_plan_off_control_loop",
                        "execution_authority": False,
                    }
                )
            waypoint_error = None
            if heading is not None and intent.lookahead is not None:
                waypoint_error = _wrap_angle(
                    atan2(intent.lookahead.y - world_y, intent.lookahead.x - world_x)
                    - heading
                )
            if (
                movement_lab_publish_future is not None
                and movement_lab_publish_future.done()
            ):
                try:
                    movement_lab_publish_future.result()
                except BaseException as error:
                    actions.append(
                        {
                            "kind": "MOVEMENT_LAB_PUBLICATION_FAILED",
                            "reason": type(error).__name__,
                            "execution_authority": False,
                        }
                    )
                movement_lab_publish_future = None
            if control_frames % 2 == 0 and movement_lab_publish_future is None:
                topographic_facing_source = getattr(
                    pose_source, "latest_facing_source", "UNAVAILABLE"
                )
                topographic_body_yaw = _body_yaw_observation(
                    observation,
                    client_facing_source=topographic_facing_source,
                )
                environment_awareness = None
                environment_applicability = None
                structure_access_awareness = None
                if corridor.awareness_observed_monotonic_s is not None:
                    environment_awareness = engine.environment_at_corridor_start(
                        corridor,
                        observed_monotonic_s=(corridor.awareness_observed_monotonic_s),
                    )
                if environment_awareness is not None:
                    horizontal_offset = corridor.start.distance_2d(
                        NavPoint(world_x, world_y, current_z_hint)
                    )
                    vertical_offset = abs(corridor.start.z - current_z_hint)
                    environment_applicability = {
                        "horizontal_offset_yards": horizontal_offset,
                        "vertical_offset_yards": vertical_offset,
                        "validity_radius_yards": 3.0,
                        "applicable_to_live_pose": (
                            horizontal_offset <= 3.0 and vertical_offset <= 2.5
                        ),
                        "source_position": [
                            corridor.start.x,
                            corridor.start.y,
                            corridor.start.z,
                        ],
                        "execution_authority": False,
                    }
                    known_openings = engine.known_structure_openings(
                        environment_awareness,
                    )
                    structure_access_awareness = {
                        "graph_id": runtime_structure_access_graph_id,
                        "graph_content_sha256": (runtime_structure_access_graph_sha256),
                        "coverage_state": (
                            None
                            if structure_access_spatial is None
                            else structure_access_spatial.record["coverage_state"]
                        ),
                        "source_position": [
                            corridor.start.x,
                            corridor.start.y,
                            corridor.start.z,
                        ],
                        "applicable_to_live_pose": (
                            environment_applicability["applicable_to_live_pose"]
                        ),
                        "known_opening_count": len(known_openings),
                        "known_openings": list(known_openings),
                        "physical_door_semantics": "UNKNOWN_NOT_INFERRED",
                        "execution_authority": False,
                    }
                movement_lab_publish_future = movement_lab_publish_executor.submit(
                    _publish_movement_lab,
                    args.movement_lab_state_file,
                    MovementLabSnapshot(
                        observed_monotonic_s=last_observed_s,
                        tracking_state="LOST",
                        target_identity_crc16=None,
                        target_error_x_normalized=None,
                        player_world_x=world_x,
                        player_world_y=world_y,
                        player_world_z=current_z_hint,
                        player_facing_rad=heading,
                        body_facing_rad=topographic_body_yaw,
                        body_facing_source=(
                            topographic_facing_source
                            if topographic_body_yaw is not None
                            else None
                        ),
                        camera_yaw_estimate_rad=heading,
                        camera_yaw_source=CAMERA_YAW_CONTROL_SOURCE,
                        body_camera_yaw_delta_rad=_body_camera_yaw_delta(
                            topographic_body_yaw, heading,
                        ),
                        waypoint_error_rad=waypoint_error,
                        controller_state=intent.state,
                        navmesh_polygons_world=tuple(
                            tuple((vertex.x, vertex.y) for vertex in polygon.vertices)
                            for polygon in corridor.polygons
                        ),
                        corridor_centerline_world=tuple(
                            (point.x, point.y) for point in corridor.guidance_points()
                        ),
                        planned_waypoints_world=tuple(
                            (point.x, point.y)
                            for point in semantic_goals[
                                semantic_goal_index : semantic_goal_index + 12
                            ]
                        ),
                        traversed_path_world=tuple(
                            (point.x, point.y)
                            for point in observed_journey_trace.points
                        ),
                    ),
                    local_static_awareness=(_local_static_awareness_record(corridor)),
                    location_labels=getattr(pose_source, "latest_location_labels", None),
                    local_environment_awareness=(
                        None
                        if environment_awareness is None
                        else environment_awareness.to_record()
                    ),
                    local_environment_applicability=(environment_applicability),
                    structure_access_awareness=structure_access_awareness,
                    dynamic_entity_awareness=_dynamic_entity_awareness_record(
                        dynamic_tracks,
                        observed_at_s=last_observed_s,
                        adapter_error=pose_source.latest_dynamic_detection_error,
                    ),
                    dynamic_experience_summary=dynamic_experience_summary,
                    topographic_brain=engine.topographic_context(
                        observed_monotonic_s=last_observed_s,
                        actor=NavPoint(world_x, world_y, current_z_hint),
                        actor_facing_rad=topographic_body_yaw,
                        actor_position_source="COORDINATE_HUD_WORLD_TRANSFORM",
                        actor_facing_source=(
                            topographic_facing_source
                            if topographic_body_yaw is not None
                            else "UNAVAILABLE"
                        ),
                        controller_heading_rad=heading,
                        destination=NavPoint(
                            destination_x,
                            destination_y,
                            (
                                corridor.requested_stop.z
                                if corridor.requested_stop is not None
                                else corridor.stop.z
                            ),
                        ),
                        corridor=corridor,
                        environment=(
                            environment_awareness
                            if environment_applicability is not None
                            and bool(
                                environment_applicability["applicable_to_live_pose"]
                            )
                            else None
                        ),
                        semantic_route_profile=(
                            None
                            if semantic_route is None
                            else semantic_route.profile_id
                        ),
                        semantic_goal_index=semantic_goal_index,
                        semantic_goal_count=len(semantic_goals),
                        visible_dynamic_entity_count=len(dynamic_tracks),
                        routine_aggro_travel_enabled=(
                            args.continue_through_routine_aggro
                        ),
                        minimum_travel_health_fraction=(
                            args.minimum_travel_health_fraction
                        ),
                    ).to_record(),
                )
            cycle_checkpoints.append(("overlay_preparation", time.monotonic()))
            if intent.state == "ARRIVED":
                # A completed local corridor is not necessarily the end of the
                # semantic journey.  If the next semantic leg is already in
                # the queue, keep the existing W lease while the bounded
                # handoff selects the next corridor.  Releasing here created
                # a visible pause at otherwise smooth landmarks (notably the
                # bridge exit).  Terminal/recovery/egress paths still release
                # immediately and the actuator watchdog remains fail-closed.
                semantic_waypoint_continuation = (
                    ordered_goal_queue_active
                    and recovery_resume_goal is None
                    and structure_resume_goal is None
                    and semantic_goal_index + 1 < len(semantic_goals)
                )
                if not semantic_waypoint_continuation:
                    motion.release_all()
                else:
                    actions.append(
                        {
                            "kind": "SEMANTIC_HANDOFF_MOTION_HELD",
                            "waypoint_index": semantic_goal_index,
                            "reason": "bounded_next_corridor_handoff_without_stop_pulse",
                            "execution_authority": False,
                        }
                    )
                if recovery_resume_goal is not None:
                    recovery_point = (goal_x, goal_y)
                    if recovery_local_goals:
                        next_recovery_goal = recovery_local_goals.pop(0)
                        goal_x, goal_y = next_recovery_goal.x, next_recovery_goal.y
                        action_kind = "LOCAL_CLEARANCE_WAYPOINT_REACHED"
                        action_reason = (
                            "observed_obstacle_clearance_leg_reached_on_navmesh"
                        )
                    else:
                        goal_x, goal_y = recovery_resume_goal
                        recovery_resume_goal = None
                        engine.steering = (
                            structure_egress_steering
                            if structure_resume_goal is not None
                            else mission_steering
                        )
                        action_kind = "LOCAL_CLEARANCE_COMPLETE"
                        action_reason = (
                            "observed_obstacle_bypassed_then_mission_goal_resumed"
                        )
                        if recovery_pending_blocker is not None:
                            success_x, success_y = (
                                last_recovery_collision_world
                                if last_recovery_collision_world is not None
                                else (
                                    recovery_pending_blocker[0],
                                    recovery_pending_blocker[1],
                                )
                            )
                            recovery_strategy_memory = recovery_strategy_memory.resolve_success(
                                map_name=active_map_name,
                                zone_index=args.expected_zone_index,
                                x=success_x,
                                y=success_y,
                                strategy=LOCAL_CLEARANCE_STRATEGY,
                            )
                            _write_json_atomic(
                                args.recovery_strategy_memory,
                                recovery_strategy_memory.to_record(),
                            )
                            learned_obstacle_memory = learned_obstacle_memory.observe(
                                map_name=active_map_name,
                                zone_index=args.expected_zone_index,
                                blocker=recovery_pending_blocker,
                                run_id=run_id,
                                observed_at=datetime.now(timezone.utc),
                                evidence=LOCAL_CLEARANCE_EVIDENCE,
                            )
                            _write_json_atomic(
                                args.learned_obstacle_memory,
                                learned_obstacle_memory.to_record(),
                            )
                            learned_obstacles_persisted += 1
                            actions.append(
                                {
                                    "kind": "LEARNED_LOCAL_OBSTACLE_PERSISTED",
                                    "blocker": list(recovery_pending_blocker),
                                    "memory_file": str(
                                        args.learned_obstacle_memory.resolve()
                                    ),
                                    "execution_authority": False,
                                }
                            )
                            recovery_pending_blocker = None
                        recovery_strategy = None
                    actions.append(
                        {
                            "kind": action_kind,
                            "world_x": world_x,
                            "world_y": world_y,
                            "recovery_world": list(recovery_point),
                            "next_goal_world": [goal_x, goal_y],
                            "remaining_clearance_legs": len(recovery_local_goals),
                            "reason": action_reason,
                        }
                    )
                    corridor = engine.plan(
                        start=NavPoint(world_x, world_y, current_z_hint),
                        goal_x=goal_x,
                        goal_y=goal_y,
                    )
                    if (
                        not corridor.complete
                        and corridor.stop.distance_2d(
                            NavPoint(goal_x, goal_y, corridor.stop.z)
                        )
                        > local_goal_radius
                    ):
                        status = "RESET_REQUIRED"
                        break
                    observation = pose_source.next_observation()
                    _, _, world_x, world_y = _position(
                        observation,
                        expected_zone_index=args.expected_zone_index,
                        transform=transform,
                        expected_map_id=args.map_id,
                    )
                    heading, heading_source = _observe_player_heading(
                        pose_source,
                        visible_heading_observer,
                        predicted_heading_rad=heading,
                        observation=observation,
                        displacement_heading_rad=None,
                    )
                    last_observed_s = float(
                        observation["timing"]["observed_monotonic_s"]
                    )
                    no_progress_s = 0.0
                    pivot_without_heading_progress_s = 0.0
                    pivot_heading_error_anchor_rad = None
                    partial_replans = 0
                    progress_gate.reset(
                        path_progress_world=0.0,
                        goal_distance_world=hypot(goal_x - world_x, goal_y - world_y),
                    )
                    continue
                if structure_resume_goal is not None:
                    reached_opening = structure_egress_opening_id
                    reached_world = (goal_x, goal_y)
                    goal_x, goal_y = structure_resume_goal
                    structure_resume_goal = None
                    structure_egress_opening_id = None
                    structure_egress_continuation = None
                    query = query.without_structure_egress_scope()
                    engine.navigator = query
                    engine.steering = mission_steering
                    actions.append(
                        {
                            "kind": "STRUCTURE_EGRESS_REACHED",
                            "opening_id": reached_opening,
                            "opening_world": list(reached_world),
                            "world_x": world_x,
                            "world_y": world_y,
                            "resumed_goal_world": [goal_x, goal_y],
                            "reason": (
                                "verified_structure_exit_anchor_reached_then_"
                                "original_goal_resumed"
                            ),
                            "execution_authority": False,
                        }
                    )
                    corridor = engine.plan(
                        start=NavPoint(world_x, world_y, current_z_hint),
                        goal_x=goal_x,
                        goal_y=goal_y,
                    )
                    next_egress = _verified_structure_egress_plan(
                        engine=engine,
                        direct_corridor=corridor,
                        goal_x=goal_x,
                        goal_y=goal_y,
                        observed_monotonic_s=last_observed_s,
                        excluded_opening_ids=frozenset(attempted_structure_egress_ids),
                    )
                    if next_egress is not None:
                        structure_resume_goal = (goal_x, goal_y)
                        structure_egress_opening_id = next_egress.opening_id
                        structure_egress_continuation = next_egress.continuation
                        attempted_structure_egress_ids.add(next_egress.opening_id)
                        goal_x, goal_y = (
                            next_egress.movement_target.x,
                            next_egress.movement_target.y,
                        )
                        corridor = next_egress.approach
                        query = _scope_query_for_structure_egress(
                            query=query,
                            structures=structure_spatial,
                            proposal=next_egress,
                        )
                        engine.navigator = query
                        engine.steering = structure_egress_steering
                        actions.append(
                            _structure_egress_action(
                                next_egress,
                                deferred_goal=structure_resume_goal,
                                graph_id=runtime_structure_access_graph_id,
                                graph_content_sha256=(
                                    runtime_structure_access_graph_sha256
                                ),
                            )
                        )
                    elif args.steering_controller == "continuous_trajectory_v1":
                        corridor, _ = _prepare_continuous_trajectory(
                            query=query,
                            map_name=active_map_name,
                            corridor=corridor,
                        )
                    elif (
                        not corridor.complete
                        and corridor.stop.distance_2d(
                            NavPoint(goal_x, goal_y, corridor.stop.z)
                        )
                        > local_goal_radius
                        and ordered_goal_queue_active
                    ):
                        status = "RESET_REQUIRED"
                        break
                    observation = pose_source.next_observation()
                    _, _, world_x, world_y = _position(
                        observation,
                        expected_zone_index=args.expected_zone_index,
                        transform=transform,
                        expected_map_id=args.map_id,
                    )
                    heading, heading_source = _observe_player_heading(
                        pose_source,
                        visible_heading_observer,
                        predicted_heading_rad=heading,
                        observation=observation,
                        displacement_heading_rad=None,
                    )
                    last_observed_s = float(
                        observation["timing"]["observed_monotonic_s"]
                    )
                    no_progress_s = 0.0
                    pivot_without_heading_progress_s = 0.0
                    pivot_heading_error_anchor_rad = None
                    partial_replans = 0
                    progress_gate.reset(
                        path_progress_world=0.0,
                        goal_distance_world=hypot(goal_x - world_x, goal_y - world_y),
                    )
                    continue
                local_goal_reached = (
                    hypot(goal_x - world_x, goal_y - world_y) <= local_goal_radius
                )
                if corridor.complete or (
                    ordered_goal_queue_active and local_goal_reached
                ):
                    if semantic_goal_index + 1 < len(semantic_goals):
                        actions.append(
                            {
                                "kind": "SEMANTIC_WAYPOINT_REACHED",
                                "waypoint_index": semantic_goal_index,
                                "world_x": world_x,
                                "world_y": world_y,
                                "requested_x": goal_x,
                                "requested_y": goal_y,
                                "bounded_partial_frontier": not corridor.complete,
                            }
                        )
                        next_goal = semantic_goals[semantic_goal_index + 1]
                        # The learned-clearance corridor was built with the
                        # confirmed actor-sized blocker. Give that exact leg
                        # priority over an ordinary speculative preplan.
                        cached_continuation = (
                            semantic_clearance_continuation_cache.pop(
                                (
                                    round(goal_x, 6),
                                    round(goal_y, 6),
                                    round(next_goal.x, 6),
                                    round(next_goal.y, 6),
                                ),
                                None,
                            )
                        )
                        prepared_waypoint_corridor = None
                        if cached_continuation is not None:
                            cache_start = cached_continuation.start
                            if (
                                hypot(
                                    world_x - cache_start.x,
                                    world_y - cache_start.y,
                                )
                                <= 3.0
                                and cached_continuation.complete
                            ):
                                prepared_waypoint_corridor = cached_continuation
                                actions.append(
                                    {
                                        "kind": (
                                            "CONFIRMED_CLEARANCE_CONTINUATION_"
                                            "CACHE_REUSED"
                                        ),
                                        "waypoint_index": semantic_goal_index + 1,
                                        "world_x": world_x,
                                        "world_y": world_y,
                                        "cache_start_world": [
                                            cache_start.x,
                                            cache_start.y,
                                            cache_start.z,
                                        ],
                                        "reason": (
                                            "immutable_navmesh_validated_"
                                            "clearance_corridor"
                                        ),
                                        "execution_authority": False,
                                    }
                                )
                        if prepared_waypoint_corridor is None:
                            prepared_waypoint_corridor = semantic_handoff_cache.pop(
                                semantic_goal_index + 1,
                                None,
                            )
                        # A complete next-goal preplan may already be ready
                        # even when the stricter fly-by bearing check was not
                        # satisfied. Reuse that immutable corridor at the
                        # exact shared point instead of issuing a synchronous
                        # Detour query in the input loop.
                        if (
                            prepared_waypoint_corridor is None
                            and semantic_preplan_future is not None
                            and semantic_preplan_goal_index == semantic_goal_index + 1
                            and semantic_preplan_query is query
                            and semantic_preplan_future.done()
                        ):
                            try:
                                preplanned_waypoint, _ = _unpack_preplanned_corridor(
                                    semantic_preplan_future.result()
                                )
                            except BaseException:
                                preplanned_waypoint = None
                            if preplanned_waypoint is not None:
                                if _corridor_reaches_local_goal(
                                    preplanned_waypoint,
                                    goal_x=next_goal.x,
                                    goal_y=next_goal.y,
                                    radius_world=local_goal_radius,
                                ):
                                    prepared_waypoint_corridor = preplanned_waypoint
                                    actions.append(
                                        {
                                            "kind": (
                                                "SEMANTIC_CORRIDOR_PREPLAN_REUSED_"
                                                "AT_HANDOFF"
                                            ),
                                            "waypoint_index": semantic_goal_index + 1,
                                            "world_x": world_x,
                                            "world_y": world_y,
                                            "reason": (
                                                "complete_next_goal_corridor_"
                                                "reused_without_synchronous_query"
                                            ),
                                            "execution_authority": False,
                                        }
                                    )
                        if prepared_waypoint_corridor is not None:
                            cached_divergence = _semantic_corridor_goal_divergence(
                                prepared_waypoint_corridor,
                                world_x=world_x,
                                world_y=world_y,
                                goal_x=next_goal.x,
                                goal_y=next_goal.y,
                            )
                            if not _semantic_cached_corridor_advances_toward_goal(
                                prepared_waypoint_corridor,
                                world_x=world_x,
                                world_y=world_y,
                                goal_x=next_goal.x,
                                goal_y=next_goal.y,
                            ):
                                actions.append(
                                    {
                                        "kind": (
                                            "SEMANTIC_CORRIDOR_CACHE_REJECTED_"
                                            "AT_HANDOFF"
                                        ),
                                        "waypoint_index": semantic_goal_index + 1,
                                        "world_x": world_x,
                                        "world_y": world_y,
                                        "goal_world": [next_goal.x, next_goal.y],
                                        "divergence_rad": (
                                            cached_divergence[0]
                                            if cached_divergence is not None
                                            else None
                                        ),
                                        "corridor_bearing_rad": (
                                            cached_divergence[1]
                                            if cached_divergence is not None
                                            else None
                                        ),
                                        "goal_bearing_rad": (
                                            cached_divergence[2]
                                            if cached_divergence is not None
                                            else None
                                        ),
                                        "reason": (
                                            "cached_first_tangent_does_not_"
                                            "advance_toward_next_semantic_goal"
                                        ),
                                        "execution_authority": False,
                                    }
                                )
                                prepared_waypoint_corridor = None
                        if semantic_preplan_future is not None:
                            semantic_preplan_future.cancel()
                        if semantic_refinement_preplan_future is not None:
                            semantic_refinement_preplan_future.cancel()
                        semantic_preplan_future = None
                        semantic_preplan_goal_index = None
                        semantic_preplan_query = None
                        semantic_preplan_failed_goal_index = None
                        semantic_refinement_preplan_future = None
                        semantic_refinement_preplan_point = None
                        if semantic_frontier_preplan_future is not None:
                            semantic_frontier_preplan_future.cancel()
                        semantic_frontier_preplan_future = None
                        semantic_frontier_preplan_query = None
                        semantic_frontier_preplan_goal_index = None
                        semantic_frontier_preplan_start = None
                        semantic_frontier_preplan_candidates = ()
                        if corridor_recenter_preplan_future is not None:
                            corridor_recenter_preplan_future.cancel()
                        corridor_recenter_preplan_future = None
                        corridor_recenter_preplan_query = None
                        corridor_recenter_preplan_start = None
                        corridor_recenter_preplan_goal = None
                        semantic_goal_index += 1
                        goal_x = semantic_goals[semantic_goal_index].x
                        goal_y = semantic_goals[semantic_goal_index].y
                        attempted_structure_egress_ids.clear()
                        requested_goal_index = semantic_goal_index
                        if prepared_waypoint_corridor is not None:
                            corridor = prepared_waypoint_corridor
                            goal_projected = False
                            actions.append(
                                {
                                    "kind": "SEMANTIC_CORRIDOR_CACHE_REUSED",
                                    "waypoint_index": semantic_goal_index,
                                    "reason": (
                                        "complete_detour_leg_deferred_until_"
                                        "exact_shared_point_handoff"
                                    ),
                                    "execution_authority": False,
                                }
                            )
                        else:
                            semantic_goal_index, corridor, goal_projected = (
                                _plan_semantic_goal_or_forward_projection(
                                    engine=engine,
                                    start=NavPoint(
                                        world_x,
                                        world_y,
                                        current_z_hint,
                                    ),
                                    goals=semantic_goals,
                                    goal_index=semantic_goal_index,
                                    radius_world=local_goal_radius,
                                )
                            )
                        if goal_projected:
                            goal_x = semantic_goals[semantic_goal_index].x
                            goal_y = semantic_goals[semantic_goal_index].y
                            actions.append(
                                {
                                    "kind": "SEMANTIC_ENDPOINT_PROJECTED_FORWARD",
                                    "blocked_goal_index": requested_goal_index,
                                    "selected_goal_index": semantic_goal_index,
                                    "selected_goal_world": [goal_x, goal_y],
                                    "skipped_goal_count": (
                                        semantic_goal_index - requested_goal_index
                                    ),
                                    "reason": (
                                        "atlas_raster_center_had_no_polygon_use_"
                                        "next_detour_reachable_route_sample"
                                    ),
                                    "execution_authority": False,
                                }
                            )
                        waypoint_egress_selection = (
                            _forward_structure_egress_plan(
                                engine=engine,
                                direct_corridor=corridor,
                                goals=semantic_goals,
                                goal_index=semantic_goal_index,
                                goal_x=goal_x,
                                goal_y=goal_y,
                                observed_monotonic_s=last_observed_s,
                            )
                            if semantic_route is not None
                            else (
                                semantic_goal_index,
                                _verified_structure_egress_plan(
                                    engine=engine,
                                    direct_corridor=corridor,
                                    goal_x=goal_x,
                                    goal_y=goal_y,
                                    observed_monotonic_s=last_observed_s,
                                ),
                            )
                        )
                        if (
                            waypoint_egress_selection is not None
                            and waypoint_egress_selection[1] is None
                        ):
                            waypoint_egress_selection = None
                        waypoint_egress = (
                            None
                            if waypoint_egress_selection is None
                            else waypoint_egress_selection[1]
                        )
                        if waypoint_egress is not None:
                            selected_goal_index = waypoint_egress_selection[0]
                            if selected_goal_index != semantic_goal_index:
                                previous_goal_index = semantic_goal_index
                                semantic_goal_index = selected_goal_index
                                goal_x = semantic_goals[semantic_goal_index].x
                                goal_y = semantic_goals[semantic_goal_index].y
                                actions.append(
                                    {
                                        "kind": (
                                            "SEMANTIC_STRUCTURE_EGRESS_LOOKAHEAD"
                                        ),
                                        "previous_goal_index": previous_goal_index,
                                        "selected_goal_index": semantic_goal_index,
                                        "skipped_inside_goal_count": (
                                            semantic_goal_index - previous_goal_index
                                        ),
                                        "selected_goal_world": [goal_x, goal_y],
                                        "reason": (
                                            "bounded_forward_semantic_goal_exits_"
                                            "known_structure_via_revalidated_opening"
                                        ),
                                        "execution_authority": False,
                                    }
                                )
                            structure_resume_goal = (goal_x, goal_y)
                            structure_egress_opening_id = waypoint_egress.opening_id
                            structure_egress_continuation = waypoint_egress.continuation
                            attempted_structure_egress_ids.add(
                                waypoint_egress.opening_id
                            )
                            goal_x, goal_y = (
                                waypoint_egress.movement_target.x,
                                waypoint_egress.movement_target.y,
                            )
                            corridor = waypoint_egress.approach
                            query = _scope_query_for_structure_egress(
                                query=query,
                                structures=structure_spatial,
                                proposal=waypoint_egress,
                            )
                            engine.navigator = query
                            engine.steering = structure_egress_steering
                            actions.append(
                                _structure_egress_action(
                                    waypoint_egress,
                                    deferred_goal=structure_resume_goal,
                                    graph_id=runtime_structure_access_graph_id,
                                    graph_content_sha256=(
                                        runtime_structure_access_graph_sha256
                                    ),
                                )
                            )
                        elif args.steering_controller == "continuous_trajectory_v1":
                            corridor, _ = _prepare_continuous_trajectory(
                                query=query,
                                map_name=active_map_name,
                                corridor=corridor,
                            )
                        if (
                            not corridor.complete
                            and corridor.stop.distance_2d(
                                NavPoint(goal_x, goal_y, corridor.stop.z)
                            )
                            > local_goal_radius
                        ):
                            actions.append(
                                {
                                    "kind": "SEMANTIC_FRONTIER_REPLAN_REQUIRED",
                                    "world_x": world_x,
                                    "world_y": world_y,
                                    "requested_x": goal_x,
                                    "requested_y": goal_y,
                                    "frontier_x": corridor.stop.x,
                                    "frontier_y": corridor.stop.y,
                                    "reason": (
                                        "next_semantic_leg_requires_fresh_global_"
                                        "plan_from_reached_partial_frontier"
                                    ),
                                    "execution_authority": False,
                                }
                            )
                            # Keep the bounded partial corridor alive.  The
                            # controller will reach its proven frontier and
                            # enter the local forward-bypass/replan logic
                            # below; aborting here forced the supervisor to
                            # restart the same frontier and could exhaust its
                            # navigation-cycle budget without trying a valid
                            # forward road sample.
                        observation = pose_source.next_observation()
                        _, _, world_x, world_y = _position(
                            observation,
                            expected_zone_index=args.expected_zone_index,
                            transform=transform,
                            expected_map_id=args.map_id,
                        )
                        heading, heading_source = _observe_player_heading(
                            pose_source,
                            visible_heading_observer,
                            predicted_heading_rad=heading,
                            observation=observation,
                            displacement_heading_rad=None,
                        )
                        last_observed_s = float(
                            observation["timing"]["observed_monotonic_s"]
                        )
                        no_progress_s = 0.0
                        pivot_without_heading_progress_s = 0.0
                        pivot_heading_error_anchor_rad = None
                        progress_gate.reset(
                            path_progress_world=0.0,
                            goal_distance_world=hypot(
                                goal_x - world_x, goal_y - world_y
                            ),
                        )
                        partial_replans = 0
                        continue
                    status = "ARRIVED"
                    break
                partial_replans += 1
                # A positive operator traversal is allowed to bridge a small
                # client-navmesh hole that was already walked in this exact
                # build. Keep the bridge short and local; the next semantic
                # goal is still planned by Detour after re-entry.
                if (
                    traversed_surface_local_count > 0
                    and semantic_goal_index < traversed_surface_local_count
                    and hypot(goal_x - world_x, goal_y - world_y) <= 4.5
                ):
                    observed_start = NavPoint(world_x, world_y, current_z_hint)
                    observed_stop = NavPoint(goal_x, goal_y, current_z_hint)
                    corridor = NavCorridor(
                        active_map_name,
                        corridor.adt_x,
                        corridor.adt_y,
                        observed_start,
                        observed_stop,
                        (observed_start, observed_stop),
                        source="operator_observed_traversability_frontier",
                        requested_stop=observed_stop,
                    )
                    actions.append(
                        {
                            "kind": "OBSERVED_SURFACE_FRONTIER_BRIDGED",
                            "semantic_goal_index": semantic_goal_index,
                            "distance_world": hypot(
                                goal_x - world_x, goal_y - world_y,
                            ),
                            "source": "operator_observed_continuous_traversability",
                            "execution_authority": False,
                        }
                    )
                    partial_replans = 0
                    no_progress_s = 0.0
                    progress_gate.reset(
                        path_progress_world=0.0,
                        goal_distance_world=hypot(
                            goal_x - world_x, goal_y - world_y,
                        ),
                    )
                    continue
                if partial_replans > 12:
                    status = "PARTIAL_CORRIDOR_REPLAN_BUDGET_EXHAUSTED"
                    break
                previous_frontier = corridor.stop
                # Keep a worker result that was started from this exact
                # frontier alive through the repeated partial replan.  The
                # handoff block below can then reuse a completed corridor
                # instead of cancelling it and issuing the same synchronous
                # candidate scan inside the control loop.  A future that is
                # stale, incomplete, or from another query is still cleared
                # by the handoff block's fail-closed checks.
                corridor = engine.plan(
                    start=NavPoint(world_x, world_y, current_z_hint),
                    goal_x=goal_x,
                    goal_y=goal_y,
                )
                frontier_egress = (
                    None
                    if structure_resume_goal is not None
                    else _verified_structure_egress_plan(
                        engine=engine,
                        direct_corridor=corridor,
                        goal_x=goal_x,
                        goal_y=goal_y,
                        observed_monotonic_s=last_observed_s,
                        excluded_opening_ids=frozenset(attempted_structure_egress_ids),
                    )
                )
                if frontier_egress is not None:
                    structure_resume_goal = (goal_x, goal_y)
                    structure_egress_opening_id = frontier_egress.opening_id
                    structure_egress_continuation = frontier_egress.continuation
                    attempted_structure_egress_ids.add(frontier_egress.opening_id)
                    goal_x, goal_y = (
                        frontier_egress.movement_target.x,
                        frontier_egress.movement_target.y,
                    )
                    corridor = frontier_egress.approach
                    query = _scope_query_for_structure_egress(
                        query=query,
                        structures=structure_spatial,
                        proposal=frontier_egress,
                    )
                    engine.navigator = query
                    engine.steering = structure_egress_steering
                    actions.append(
                        _structure_egress_action(
                            frontier_egress,
                            deferred_goal=structure_resume_goal,
                            graph_id=runtime_structure_access_graph_id,
                            graph_content_sha256=(
                                runtime_structure_access_graph_sha256
                            ),
                        )
                    )
                    observation = pose_source.next_observation()
                    _, _, world_x, world_y = _position(
                        observation,
                        expected_zone_index=args.expected_zone_index,
                        transform=transform,
                        expected_map_id=args.map_id,
                    )
                    heading, heading_source = _observe_player_heading(
                        pose_source,
                        visible_heading_observer,
                        predicted_heading_rad=heading,
                        observation=observation,
                        displacement_heading_rad=None,
                    )
                    last_observed_s = float(
                        observation["timing"]["observed_monotonic_s"]
                    )
                    no_progress_s = 0.0
                    pivot_without_heading_progress_s = 0.0
                    pivot_heading_error_anchor_rad = None
                    partial_replans = 0
                    progress_gate.reset(
                        path_progress_world=0.0,
                        goal_distance_world=hypot(goal_x - world_x, goal_y - world_y),
                    )
                    continue
                frontier_handoff_matches = (
                    corridor.stop.distance_2d(previous_frontier) < 0.75
                )
                if frontier_handoff_matches:
                    fine_fallback_applied = False
                    deferred_coarse_x, deferred_coarse_y = goal_x, goal_y
                    # Prefer a completed route prepared from the same proven
                    # frontier.  The actor is allowed to keep the current
                    # movement lease through this handoff; a fresh query is
                    # still mandatory when the future is stale or incomplete.
                    if (
                        semantic_frontier_preplan_future is not None
                        and semantic_frontier_preplan_goal_index == semantic_goal_index
                        and semantic_frontier_preplan_query is query
                        and semantic_frontier_preplan_start is not None
                        and hypot(
                            world_x - semantic_frontier_preplan_start.x,
                            world_y - semantic_frontier_preplan_start.y,
                        )
                        <= 4.0
                        and semantic_frontier_preplan_future.done()
                    ):
                        try:
                            preplanned_bypass = semantic_frontier_preplan_future.result()
                        except BaseException:
                            preplanned_bypass = None
                        preplan_start = semantic_frontier_preplan_start
                        semantic_frontier_preplan_future = None
                        semantic_frontier_preplan_query = None
                        semantic_frontier_preplan_goal_index = None
                        semantic_frontier_preplan_start = None
                        semantic_frontier_preplan_candidates = ()
                        if preplanned_bypass is not None:
                            route_index, candidate_corridor = preplanned_bypass
                            candidate = RoadWorldPoint(
                                candidate_corridor.requested_stop.x
                                if candidate_corridor.requested_stop is not None
                                else candidate_corridor.stop.x,
                                candidate_corridor.requested_stop.y
                                if candidate_corridor.requested_stop is not None
                                else candidate_corridor.stop.y,
                            )
                            blocked_goal = semantic_goals[semantic_goal_index]
                            semantic_goals[semantic_goal_index] = candidate
                            if (
                                semantic_goal_index + 1 < len(semantic_goals)
                                and hypot(
                                    semantic_goals[semantic_goal_index + 1].x
                                    - candidate.x,
                                    semantic_goals[semantic_goal_index + 1].y
                                    - candidate.y,
                                )
                                <= 0.05
                            ):
                                del semantic_goals[semantic_goal_index + 1]
                            semantic_route_progress_index = route_index
                            goal_x, goal_y = candidate.x, candidate.y
                            corridor = candidate_corridor
                            partial_replans = 0
                            actions.append(
                                {
                                    "kind": "SEMANTIC_STATIC_FRONTIER_BYPASS_PREPLANNED",
                                    "route_waypoint_index": route_index,
                                    "world_x": world_x,
                                    "world_y": world_y,
                                    "blocked_goal_world": [
                                        blocked_goal.x,
                                        blocked_goal.y,
                                    ],
                                    "bypass_goal_world": [candidate.x, candidate.y],
                                    "planned_frontier_world": [
                                        preplan_start.x,
                                        preplan_start.y,
                                        preplan_start.z,
                                    ],
                                    "reason": "completed_ordered_route_bypass_reused_at_frontier",
                                    "asynchronous": True,
                                    "execution_authority": False,
                                }
                            )
                            fine_fallback_applied = True
                    if not fine_fallback_applied and semantic_frontier_preplan_future is not None:
                        semantic_frontier_preplan_future.cancel()
                        semantic_frontier_preplan_future = None
                        semantic_frontier_preplan_query = None
                        semantic_frontier_preplan_goal_index = None
                        semantic_frontier_preplan_start = None
                        semantic_frontier_preplan_candidates = ()
                    if semantic_route is not None:
                        if fine_fallback_applied:
                            # The completed worker result above is already
                            # authoritative for this frontier; do not run a
                            # second synchronous candidate scan.
                            pass
                        else:
                            for route_index, candidate in _semantic_fallback_candidates(
                                route=semantic_route,
                                start_x=world_x,
                                start_y=world_y,
                                target_x=goal_x,
                                target_y=goal_y,
                                minimum_route_index=semantic_route_progress_index,
                            ):
                                candidate_corridor = engine.plan(
                                    start=NavPoint(world_x, world_y, current_z_hint),
                                    goal_x=candidate.x,
                                    goal_y=candidate.y,
                                )
                                if (
                                    not candidate_corridor.complete
                                    or candidate_corridor.stop.distance_2d(
                                        NavPoint(
                                            candidate.x,
                                            candidate.y,
                                            candidate_corridor.stop.z,
                                        )
                                    )
                                    > local_goal_radius
                                ):
                                    continue
                                semantic_goals.insert(semantic_goal_index, candidate)
                                if semantic_preplan_future is not None:
                                    semantic_preplan_future.cancel()
                                semantic_preplan_future = None
                                semantic_preplan_goal_index = None
                                semantic_preplan_query = None
                                semantic_preplan_failed_goal_index = None
                                semantic_route_progress_index = route_index
                                goal_x, goal_y = candidate.x, candidate.y
                                corridor = candidate_corridor
                                partial_replans = 0
                                actions.append(
                                    {
                                        "kind": "SEMANTIC_FINE_FALLBACK",
                                        "route_waypoint_index": route_index,
                                        "world_x": world_x,
                                        "world_y": world_y,
                                        "requested_x": candidate.x,
                                        "requested_y": candidate.y,
                                        "deferred_coarse_x": deferred_coarse_x,
                                        "deferred_coarse_y": deferred_coarse_y,
                                        "reason": "coarse_detour_frontier_repeated",
                                    }
                                )
                                fine_fallback_applied = True
                                break
                    # Normalized-coordinate and operator paths do not build a
                    # semantic goal queue.  They still share this frontier
                    # handoff branch, so never index an empty list while no
                    # semantic route exists.
                    if not fine_fallback_applied and semantic_goals:
                        bypass_limit = semantic_goals[
                            min(
                                semantic_goal_index + 1,
                                len(semantic_goals) - 1,
                            )
                        ]
                        if semantic_route is not None:
                            for (
                                route_index,
                                candidate,
                            ) in _semantic_forward_bypass_candidates(
                                route=semantic_route,
                                start_x=world_x,
                                start_y=world_y,
                                blocked_target_x=goal_x,
                                blocked_target_y=goal_y,
                                limit_x=bypass_limit.x,
                                limit_y=bypass_limit.y,
                                minimum_route_index=(semantic_route_progress_index),
                                maximum_forward_waypoints=(
                                    SEMANTIC_STATIC_FRONTIER_MAX_FORWARD_WAYPOINTS
                                ),
                            ):
                                if _semantic_goal_overlaps_static_structure(
                                    structures=structure_spatial,
                                    goal=candidate,
                                    z=current_z_hint,
                                ):
                                    actions.append(
                                        {
                                            "kind": "SEMANTIC_STATIC_GOAL_SKIPPED",
                                            "route_waypoint_index": route_index,
                                            "goal_world": [candidate.x, candidate.y],
                                            "reason": (
                                                "world_pack_doodad_bounds_overlap_"
                                                "forward_bypass_candidate"
                                            ),
                                            "execution_authority": False,
                                        }
                                    )
                                    continue
                                candidate_corridor = engine.plan(
                                    start=NavPoint(
                                        world_x,
                                        world_y,
                                        current_z_hint,
                                    ),
                                    goal_x=candidate.x,
                                    goal_y=candidate.y,
                                )
                                if not _corridor_reaches_local_goal(
                                    candidate_corridor,
                                    goal_x=candidate.x,
                                    goal_y=candidate.y,
                                    radius_world=local_goal_radius,
                                ):
                                    continue
                                blocked_goal = semantic_goals[semantic_goal_index]
                                semantic_goals[semantic_goal_index] = candidate
                                if (
                                    semantic_goal_index + 1 < len(semantic_goals)
                                    and hypot(
                                        semantic_goals[semantic_goal_index + 1].x
                                        - candidate.x,
                                        semantic_goals[semantic_goal_index + 1].y
                                        - candidate.y,
                                    )
                                    <= 0.05
                                ):
                                    del semantic_goals[semantic_goal_index + 1]
                                if semantic_preplan_future is not None:
                                    semantic_preplan_future.cancel()
                                semantic_preplan_future = None
                                semantic_preplan_goal_index = None
                                semantic_preplan_query = None
                                semantic_preplan_failed_goal_index = None
                                semantic_route_progress_index = route_index
                                goal_x, goal_y = candidate.x, candidate.y
                                corridor = candidate_corridor
                                partial_replans = 0
                                actions.append(
                                    {
                                        "kind": ("SEMANTIC_STATIC_FRONTIER_BYPASS"),
                                        "route_waypoint_index": route_index,
                                        "world_x": world_x,
                                        "world_y": world_y,
                                        "blocked_goal_world": [
                                            blocked_goal.x,
                                            blocked_goal.y,
                                        ],
                                        "bypass_goal_world": [
                                            candidate.x,
                                            candidate.y,
                                        ],
                                        "reason": (
                                            "repeated_partial_frontier_bypassed_"
                                            "by_forward_road_cell_with_complete_"
                                            "client_navmesh_route"
                                        ),
                                        "execution_authority": False,
                                    }
                                )
                                fine_fallback_applied = True
                                break
                    if not fine_fallback_applied:
                        if structure_spatial is not None:
                            static_clearance_goals, static_clearance_actions = (
                                _inject_static_structure_clearance_priors(
                                    structures=structure_spatial,
                                    route_start=RoadWorldPoint(world_x, world_y),
                                    start_z=current_z_hint,
                                    goals=(RoadWorldPoint(goal_x, goal_y),),
                                    query=query,
                                    map_name=active_map_name,
                                )
                            )
                            actions.extend(static_clearance_actions)
                            if len(static_clearance_goals) > 1:
                                semantic_goals[
                                    semantic_goal_index:semantic_goal_index + 1
                                ] = list(static_clearance_goals)
                                goal_x, goal_y = (
                                    static_clearance_goals[0].x,
                                    static_clearance_goals[0].y,
                                )
                                try:
                                    clearance_corridor = engine.plan(
                                        start=NavPoint(
                                            world_x,
                                            world_y,
                                            current_z_hint,
                                        ),
                                        goal_x=goal_x,
                                        goal_y=goal_y,
                                    )
                                except RuntimeError:
                                    clearance_corridor = None
                                if (
                                    clearance_corridor is not None
                                    and _corridor_reaches_local_goal(
                                        clearance_corridor,
                                        goal_x=goal_x,
                                        goal_y=goal_y,
                                        radius_world=local_goal_radius,
                                    )
                                ):
                                    if semantic_preplan_future is not None:
                                        semantic_preplan_future.cancel()
                                    semantic_preplan_future = None
                                    semantic_preplan_goal_index = None
                                    semantic_preplan_query = None
                                    semantic_preplan_failed_goal_index = None
                                    corridor = clearance_corridor
                                    partial_replans = 0
                                    actions.append(
                                        {
                                            "kind": "SEMANTIC_STATIC_CLEARANCE_REPLAN",
                                            "world_x": world_x,
                                            "world_y": world_y,
                                            "goal_world": [goal_x, goal_y],
                                            "reason": "occupied_static_frontier_"
                                            "replaced_by_navmesh_validated_anchors",
                                            "execution_authority": False,
                                        }
                                    )
                                    fine_fallback_applied = True
                    if not fine_fallback_applied:
                        engine.mark_stuck(
                            x=world_x,
                            y=world_y,
                            observed_at_s=last_observed_s,
                        )
                        status = "PARTIAL_CORRIDOR_FRONTIER_STUCK"
                        break
                elif semantic_frontier_preplan_future is not None:
                    # A replan that moved to a different frontier cannot
                    # consume work prepared from the old one.  Invalidate the
                    # stale future before the next loop can schedule or reuse
                    # it under the new corridor context.
                    semantic_frontier_preplan_future.cancel()
                    semantic_frontier_preplan_future = None
                    semantic_frontier_preplan_query = None
                    semantic_frontier_preplan_goal_index = None
                    semantic_frontier_preplan_start = None
                    semantic_frontier_preplan_candidates = ()
                if (
                    args.steering_controller == "continuous_trajectory_v1"
                    and engine.steering is mission_steering
                ):
                    corridor, _ = _prepare_continuous_trajectory(
                        query=query,
                        map_name=active_map_name,
                        corridor=corridor,
                    )
                no_progress_s = 0.0
                pivot_without_heading_progress_s = 0.0
                pivot_heading_error_anchor_rad = None
                progress_gate.reset(
                    path_progress_world=0.0,
                    goal_distance_world=hypot(goal_x - world_x, goal_y - world_y),
                )
                heading, heading_source = _observe_player_heading(
                    pose_source,
                    visible_heading_observer,
                    predicted_heading_rad=heading,
                    observation=observation,
                    displacement_heading_rad=None,
                )
                continue
            recenter_no_progress_evidence_s = (
                _corridor_recenter_no_progress_evidence(
                    intent_reason=intent.reason,
                    no_progress_s=no_progress_s,
                    accumulated_confined_stall_s=(
                        corridor_recenter_stall_evidence_s
                    ),
                )
            )
            if intent.state == "REPLAN" and _replan_is_corridor_recenter_only(
                intent_reason=intent.reason,
                no_progress_s=recenter_no_progress_evidence_s,
                collision_slide_s=collision_slide_s,
            ):
                previous_corridor = corridor
                preplanned_recenter: NavCorridor | None = None
                recenter_future_ready = (
                    corridor_recenter_preplan_future is not None
                    and corridor_recenter_preplan_query is query
                    and corridor_recenter_preplan_start is not None
                    and corridor_recenter_preplan_goal == (goal_x, goal_y)
                    and hypot(
                        world_x - corridor_recenter_preplan_start.x,
                        world_y - corridor_recenter_preplan_start.y,
                    )
                    <= CORRIDOR_RECENTER_PREPLAN_MAX_START_DRIFT_WORLD
                    and corridor_recenter_preplan_future.done()
                )
                if recenter_future_ready:
                    assert corridor_recenter_preplan_future is not None
                    try:
                        preplanned_recenter, _ = _unpack_preplanned_corridor(
                            corridor_recenter_preplan_future.result()
                        )
                    except BaseException:
                        preplanned_recenter = None
                    if (
                        preplanned_recenter is not None
                        and _corridor_reaches_local_goal(
                            preplanned_recenter,
                            goal_x=goal_x,
                            goal_y=goal_y,
                            radius_world=local_goal_radius,
                        )
                    ):
                        # The future was planned from a nearby live pose and
                        # reached the same semantic goal. Keep W/RMB leased
                        # across the handoff; the next fresh observation below
                        # is still required before the following actuator call.
                        corridor = preplanned_recenter
                    else:
                        preplanned_recenter = None
                if corridor_recenter_preplan_future is not None:
                    corridor_recenter_preplan_future.cancel()
                corridor_recenter_preplan_future = None
                corridor_recenter_preplan_query = None
                corridor_recenter_preplan_start = None
                corridor_recenter_preplan_goal = None
                recenter_preplanned_applied = preplanned_recenter is not None
                if not recenter_preplanned_applied:
                    motion.release_all()
                if (
                    corridor_recenter_replans
                    >= MAX_CORRIDOR_RECENTER_REPLANS_WITHOUT_PROGRESS
                ):
                    actions.append(
                        {
                            "kind": "CORRIDOR_RECENTER_REPLAN_REJECTED",
                            "world_x": world_x,
                            "world_y": world_y,
                            "cross_track_error_world": intent.cross_track_error_world,
                            "attempt": corridor_recenter_replans,
                            "reason": "recenter_budget_exhausted_without_progress",
                            "collision_evidence": False,
                        }
                    )
                    status = "CORRIDOR_RECENTER_REPLAN_BUDGET_EXHAUSTED"
                    break
                corridor_recenter_replans += 1
                if not recenter_preplanned_applied:
                    try:
                        recenter_goal_z = _corridor_requested_stop_z(corridor)
                        corridor = engine.plan(
                            start=NavPoint(world_x, world_y, current_z_hint),
                            goal_x=goal_x,
                            goal_y=goal_y,
                            goal_z=recenter_goal_z,
                        )
                        if args.steering_controller == "continuous_trajectory_v1":
                            corridor, _ = _prepare_continuous_trajectory(
                                query=query,
                                map_name=active_map_name,
                                corridor=corridor,
                            )
                    except RuntimeError as error:
                        actions.append(
                            {
                                "kind": "CORRIDOR_RECENTER_REPLAN_REJECTED",
                                "world_x": world_x,
                                "world_y": world_y,
                                "cross_track_error_world": intent.cross_track_error_world,
                                "attempt": corridor_recenter_replans,
                                "reason": type(error).__name__,
                                "collision_evidence": False,
                            }
                        )
                        status = "CORRIDOR_RECENTER_REPLAN_FAILED"
                        break
                actions.append(
                    {
                        "kind": "CORRIDOR_RECENTER_REPLAN",
                        "world_x": world_x,
                        "world_y": world_y,
                        "cross_track_error_world": intent.cross_track_error_world,
                        "attempt": corridor_recenter_replans,
                        "previous_start_world": [
                            previous_corridor.start.x,
                            previous_corridor.start.y,
                            previous_corridor.start.z,
                        ],
                        "new_start_world": [
                            corridor.start.x,
                            corridor.start.y,
                            corridor.start.z,
                        ],
                        "new_complete": corridor.complete,
                        "reason": (
                            "early_worker_plan_applied_without_releasing_motion_lease"
                            if recenter_preplanned_applied
                            else "live_pose_trajectory_loop_replanned_without_fake_blocker"
                            if intent.reason == "trajectory_loop_detected"
                            else "live_pose_corridor_recentering_without_obstacle_inference"
                        ),
                        "controller_reason": intent.reason,
                        "collision_evidence": False,
                        "learned_obstacle": False,
                        "asynchronous": recenter_preplanned_applied,
                        "preplanned": recenter_preplanned_applied,
                    }
                )
                pivot_without_heading_progress_s = 0.0
                pivot_heading_error_anchor_rad = None
                progress_gate.reset(
                    path_progress_world=0.0,
                    goal_distance_world=hypot(goal_x - world_x, goal_y - world_y),
                )
                # Planning is outside the input lease. Refresh the visible pose
                # before the next controller decision; the replan itself never
                # authorizes a movement pulse.
                observation = pose_source.next_observation()
                _, _, world_x, world_y = _position(
                    observation,
                    expected_zone_index=args.expected_zone_index,
                    transform=transform,
                    expected_map_id=args.map_id,
                )
                heading_estimator.reset(x=world_x, y=world_y)
                heading, heading_source = _observe_player_heading(
                    pose_source,
                    visible_heading_observer,
                    predicted_heading_rad=heading,
                    observation=observation,
                    displacement_heading_rad=None,
                )
                if intent.reason == "confined_forward_stall_realign":
                    request_stationary_pivot = getattr(
                        engine.steering,
                        "request_stationary_pivot",
                        None,
                    )
                    if callable(request_stationary_pivot):
                        request_stationary_pivot()
                    actions.append(
                        {
                            "kind": "CONFINED_FORWARD_STALL_REALIGN_ARMED",
                            "world_x": world_x,
                            "world_y": world_y,
                            "no_progress_s": no_progress_s,
                            "learned_obstacle": False,
                        }
                    )
                    # The controller needs a fresh short clock after the
                    # stationary realignment, while the independent cumulative
                    # clock retains the physical W-without-displacement proof.
                    corridor_recenter_stall_evidence_s = (
                        recenter_no_progress_evidence_s
                    )
                    no_progress_s = 0.0
                    collision_slide_s = 0.0
                last_observed_s = float(observation["timing"]["observed_monotonic_s"])
                continue
            if intent.state == "REPLAN":
                motion.release_all()
                engine.mark_stuck(x=world_x, y=world_y, observed_at_s=last_observed_s)
                if local_recovery_attempts >= 4:
                    status = "STUCK_REPLAN_REQUIRED"
                    break
                local_recovery_attempts += 1
                recovery_attempts += 1
                deferred_resume_goal = (
                    recovery_resume_goal
                    if recovery_resume_goal is not None
                    else (goal_x, goal_y)
                )
                # A collision during a clearance maneuver must replan toward
                # the original mission, never toward the now-failed temporary
                # side/pass anchor. Replanning to that local anchor caused the
                # controller to alternate sides, backtrack, and circle the
                # same object as each recovery became the next recovery goal.
                replan_goal_x, replan_goal_y = deferred_resume_goal
                collision_x, collision_y = world_x, world_y
                last_recovery_collision_world = (collision_x, collision_y)
                # Preserve a floor-aware egress target.  A 2D replan to the
                # anchor XY can silently resolve the covered Crypt floor and
                # discard the stair/door transition that the first query
                # proved. Ordinary outdoor corridors return ``None`` here and
                # keep the legacy 2D worker contract.
                replan_goal_z = _corridor_requested_stop_z(corridor)
                if recovery_strategy == LOCAL_CLEARANCE_STRATEGY:
                    recovery_strategy_memory = (
                        recovery_strategy_memory.observe_failure(
                            map_name=active_map_name,
                            zone_index=args.expected_zone_index,
                            x=collision_x,
                            y=collision_y,
                            strategy=LOCAL_CLEARANCE_STRATEGY,
                            run_id=run_id,
                            observed_at=datetime.now(timezone.utc),
                        )
                    )
                    _write_json_atomic(
                        args.recovery_strategy_memory,
                        recovery_strategy_memory.to_record(),
                    )
                    recovery_strategy_failures_persisted += 1
                    actions.append(
                        {
                            "kind": "LEARNED_RECOVERY_STRATEGY_FAILURE",
                            "strategy": LOCAL_CLEARANCE_STRATEGY,
                            "collision_world": [collision_x, collision_y],
                            "memory_file": str(
                                args.recovery_strategy_memory.resolve()
                            ),
                            "execution_authority": False,
                        }
                    )
                blocker_heading = _collision_approach_heading(
                    intent,
                    world_x=world_x,
                    world_y=world_y,
                    observed_heading_rad=heading,
                    goal_x=goal_x,
                    goal_y=goal_y,
                )
                blocker_distance = 1.25
                blocker_radius = 1.5 + (local_recovery_attempts - 1) * 0.5
                blocker = (
                    collision_x + cos(blocker_heading) * blocker_distance,
                    collision_y + sin(blocker_heading) * blocker_distance,
                    current_z_hint,
                    blocker_radius,
                )

                candidate_blockers = _bounded_blocker_union(
                    observed_blockers,
                    (blocker,),
                    origin_x=world_x,
                    origin_y=world_y,
                )
                candidate_query = query.with_observed_blockers(candidate_blockers)
                engine.navigator = candidate_query
                candidate_corridor = engine.plan(
                    start=NavPoint(world_x, world_y, current_z_hint),
                    goal_x=replan_goal_x,
                    goal_y=replan_goal_y,
                    goal_z=replan_goal_z,
                )
                (
                    blocker_route_accepted,
                    blocker_route_path_length,
                    baseline_remaining_path_length,
                    blocker_route_maximum_path_length,
                ) = _blocker_route_quality(
                    candidate_corridor,
                    corridor,
                    world_x=world_x,
                    world_y=world_y,
                    goal_x=replan_goal_x,
                    goal_y=replan_goal_y,
                    blocker_radius=blocker_radius,
                )
                blocker_route_accepted = (
                    blocker_route_accepted
                    and abs(candidate_corridor.start.z - current_z_hint) <= 2.5
                )
                local_clearance_anchors: tuple[NavPoint, NavPoint] | None = None
                local_clearance_corridors: tuple[NavCorridor, NavCorridor] | None = None
                requested_start = NavPoint(world_x, world_y, current_z_hint)
                local_clearance_failure = recovery_strategy_memory.should_skip(
                    map_name=active_map_name,
                    zone_index=args.expected_zone_index,
                    x=collision_x,
                    y=collision_y,
                    strategy=LOCAL_CLEARANCE_STRATEGY,
                    now=datetime.now(timezone.utc),
                )
                if local_clearance_failure is not None:
                    recovery_strategy_skips += 1
                    actions.append(
                        {
                            "kind": "LEARNED_RECOVERY_STRATEGY_SKIPPED",
                            "strategy": LOCAL_CLEARANCE_STRATEGY,
                            "reason": "same_bounded_cell_failed_twice_before",
                            "failure_observations": (
                                local_clearance_failure.observations
                            ),
                            "execution_authority": False,
                        }
                    )
                # Prefer a small, collision-relative sidestep over excluding
                # whole navmesh polygons.  Every leg and its mission rejoin are
                # still proven by the client-asset Detour worker.
                for side_anchor, pass_anchor in (
                    ()
                    if local_clearance_failure is not None
                    else _local_clearance_anchor_pairs(
                        world_x=world_x,
                        world_y=world_y,
                        world_z=current_z_hint,
                        blocker=blocker,
                    )
                ):
                    try:
                        side_corridor = candidate_query.find_corridor(
                            map_name=active_map_name,
                            start=requested_start,
                            stop_x=side_anchor.x,
                            stop_y=side_anchor.y,
                            stop_z=side_anchor.z,
                        )
                        if not _local_clearance_leg_is_valid(
                            side_corridor,
                            requested_start=requested_start,
                            requested_stop=side_anchor,
                            maximum_detour_extra_world=max(
                                1.0, min(8.0, blocker[3] + 0.25)
                            ),
                        ):
                            continue
                        resolved_side = side_corridor.stop
                        pass_corridor = candidate_query.find_corridor(
                            map_name=active_map_name,
                            start=resolved_side,
                            stop_x=pass_anchor.x,
                            stop_y=pass_anchor.y,
                            stop_z=pass_anchor.z,
                        )
                        if not _local_clearance_leg_is_valid(
                            pass_corridor,
                            requested_start=resolved_side,
                            requested_stop=pass_anchor,
                            maximum_detour_extra_world=max(
                                1.0, min(8.0, blocker[3] + 0.25)
                            ),
                        ):
                            continue
                        mission_probe = candidate_query.find_corridor(
                            map_name=active_map_name,
                            start=pass_corridor.stop,
                            stop_x=replan_goal_x,
                            stop_y=replan_goal_y,
                            stop_z=replan_goal_z,
                        )
                    except RuntimeError:
                        continue
                    if (
                        mission_probe.complete
                        and abs(mission_probe.start.z - pass_corridor.stop.z) <= 2.5
                    ):
                        local_clearance_anchors = (
                            side_corridor.stop,
                            pass_corridor.stop,
                        )
                        local_clearance_corridors = (
                            side_corridor,
                            pass_corridor,
                        )
                        break
                # Two independently validated sidesteps that both failed in the
                # real client are stronger evidence than the same incomplete
                # mesh. Do not invent a third local arc from that geometry;
                # leave the concavity over freshly observed breadcrumbs and
                # replan the original mission goal from clear ground.
                if local_recovery_attempts >= 3:
                    local_clearance_anchors = None
                    local_clearance_corridors = None
                    blocker_route_accepted = _allow_bounded_blocker_exclusion(
                        blocker_route_accepted,
                        local_recovery_attempts=local_recovery_attempts,
                        structure_egress_active=structure_resume_goal is not None,
                        candidate_complete=candidate_corridor.complete,
                        excluded_polygons=(
                            candidate_corridor.observed_blocker_polygons_excluded
                        ),
                        route_length_world=blocker_route_path_length,
                        route_maximum_length_world=(
                            blocker_route_maximum_path_length
                        ),
                    )
                portal_recenter_target: NavPoint | None = None
                portal_recenter_corridor: NavCorridor | None = None
                if (
                    local_recovery_attempts < 3
                    and local_clearance_corridors is None
                    and not blocker_route_accepted
                ):
                    for portal_target in _portal_recenter_candidates(
                        corridor,
                        world_x=world_x,
                        world_y=world_y,
                    ):
                        try:
                            proposed = candidate_query.find_corridor(
                                map_name=active_map_name,
                                start=NavPoint(world_x, world_y, current_z_hint),
                                stop_x=portal_target.x,
                                stop_y=portal_target.y,
                                stop_z=portal_target.z,
                            )
                        except RuntimeError:
                            continue
                        if (
                            proposed.complete
                            and proposed.start.distance_2d(
                                NavPoint(world_x, world_y, current_z_hint)
                            )
                            <= 2.0
                            and abs(proposed.start.z - current_z_hint) <= 2.5
                        ):
                            portal_recenter_target = portal_target
                            portal_recenter_corridor = proposed
                            break
                breadcrumb_backtrack_corridor: NavCorridor | None = None
                if (
                    local_clearance_corridors is None
                    and not blocker_route_accepted
                    and portal_recenter_corridor is None
                ):
                    try:
                        breadcrumb_backtrack_corridor = (
                            safe_retreat_trail.reversed_corridor(
                                current=NavPoint(
                                    world_x,
                                    world_y,
                                    current_z_hint,
                                ),
                                maximum_retreat_world=12.0,
                            )
                        )
                    except ValueError:
                        breadcrumb_backtrack_corridor = None
                # A validated local maneuver supersedes a global polygon
                # exclusion even if the latter is technically complete.
                if local_clearance_corridors is not None:
                    blocker_route_accepted = False
                topology_recovery_accepted = (
                    blocker_route_accepted
                    or portal_recenter_corridor is not None
                    or local_clearance_corridors is not None
                    or breadcrumb_backtrack_corridor is not None
                )
                if topology_recovery_accepted:
                    if blocker_route_accepted:
                        observed_blockers = candidate_blockers
                        query = candidate_query
                        engine.navigator = query
                        corridor = candidate_corridor
                        if structure_resume_goal is not None:
                            # A local clearance controller is deliberately
                            # short-lived.  Once the verified egress route is
                            # accepted, restart the geometry-aware egress
                            # follower so its fresh corridor signature forces
                            # a stationary heading alignment before W.  Keeping
                            # the recovery controller here made it carry old
                            # yaw momentum back into the opening and turn into
                            # the same concavity again.
                            engine.steering = structure_egress_steering
                            actions.append(
                                {
                                    "kind": "STRUCTURE_EGRESS_STEERING_RESET",
                                    "reason": (
                                        "verified_egress_replaces_local_recovery_"
                                        "controller_with_fresh_geometry_alignment"
                                    ),
                                    "execution_authority": False,
                                }
                            )
                        goal_x, goal_y = replan_goal_x, replan_goal_y
                        recovery_resume_goal = None
                        recovery_local_goals = []
                        recovery_pending_blocker = None
                        recovery_strategy = None
                    elif portal_recenter_corridor is not None:
                        assert portal_recenter_target is not None
                        observed_blockers = candidate_blockers
                        query = candidate_query
                        engine.navigator = query
                        recovery_resume_goal = deferred_resume_goal
                        goal_x, goal_y = (
                            portal_recenter_target.x,
                            portal_recenter_target.y,
                        )
                        corridor = portal_recenter_corridor
                        recovery_strategy = None
                        actions.append(
                            {
                                "kind": "PORTAL_RECENTER_PLANNED",
                                "attempt": recovery_attempts,
                                "local_attempt": local_recovery_attempts,
                                "collision_world": [collision_x, collision_y],
                                "recenter_world": [goal_x, goal_y],
                                "deferred_goal_world": list(recovery_resume_goal),
                                "blocker": list(blocker),
                                "reason": (
                                    "forward_detour_portal_center_validated_after_collision"
                                ),
                                "execution_authority": False,
                            }
                        )
                    elif breadcrumb_backtrack_corridor is not None:
                        observed_blockers = candidate_blockers
                        query = candidate_query
                        engine.navigator = query
                        recovery_resume_goal = deferred_resume_goal
                        recovery_local_goals = []
                        recovery_pending_blocker = blocker
                        goal_x, goal_y = (
                            breadcrumb_backtrack_corridor.stop.x,
                            breadcrumb_backtrack_corridor.stop.y,
                        )
                        corridor = breadcrumb_backtrack_corridor
                        verified_breadcrumb_direction_probe_pending = True
                        recovery_strategy = None
                        engine.steering = PredictiveSteeringController(
                            lookahead_world=1.5,
                            min_lookahead_world=0.5,
                            max_lookahead_world=4.0,
                            arrival_radius_world=(
                                BREADCRUMB_BACKTRACK_ARRIVAL_RADIUS_WORLD
                            ),
                        )
                        actions.append(
                            {
                                "kind": "VERIFIED_BREADCRUMB_BACKTRACK_PLANNED",
                                "attempt": recovery_attempts,
                                "local_attempt": local_recovery_attempts,
                                "collision_world": [collision_x, collision_y],
                                "backtrack_world": [goal_x, goal_y],
                                "deferred_goal_world": list(recovery_resume_goal),
                                "blocker": list(blocker),
                                "reason": (
                                    "leave_obstacle_concavity_over_freshly_"
                                    "traversed_positions_before_replan"
                                ),
                                "execution_authority": False,
                            }
                        )
                    else:
                        assert local_clearance_anchors is not None
                        assert local_clearance_corridors is not None
                        side_anchor, pass_anchor = local_clearance_anchors
                        continuous_clearance = _joined_semantic_preview_corridor(
                            local_clearance_corridors[0],
                            local_clearance_corridors[1],
                        )
                        recovery_resume_goal = deferred_resume_goal
                        recovery_local_goals = (
                            [] if continuous_clearance is not None else [pass_anchor]
                        )
                        recovery_pending_blocker = blocker
                        goal_x, goal_y = (
                            (pass_anchor.x, pass_anchor.y)
                            if continuous_clearance is not None
                            else (side_anchor.x, side_anchor.y)
                        )
                        corridor = (
                            continuous_clearance
                            if continuous_clearance is not None
                            else local_clearance_corridors[0]
                        )
                        recovery_strategy = LOCAL_CLEARANCE_STRATEGY
                        engine.navigator = query
                        engine.steering = PredictiveSteeringController(
                            lookahead_world=1.5,
                            min_lookahead_world=0.5,
                            max_lookahead_world=4.0,
                            arrival_radius_world=(LOCAL_CLEARANCE_ARRIVAL_RADIUS_WORLD),
                        )
                        actions.append(
                            {
                                "kind": "LOCAL_CLEARANCE_PLANNED",
                                "attempt": recovery_attempts,
                                "local_attempt": local_recovery_attempts,
                                "collision_world": [collision_x, collision_y],
                                "side_anchor_world": [
                                    side_anchor.x,
                                    side_anchor.y,
                                    side_anchor.z,
                                ],
                                "pass_anchor_world": [
                                    pass_anchor.x,
                                    pass_anchor.y,
                                    pass_anchor.z,
                                ],
                                "deferred_goal_world": list(recovery_resume_goal),
                                "blocker": list(blocker),
                                "continuous_clearance_corridor": (
                                    continuous_clearance is not None
                                ),
                                "reason": (
                                    "collision_relative_continuous_clearance_"
                                    "validated_on_client_navmesh"
                                    if continuous_clearance is not None
                                    else "collision_relative_two_leg_clearance_"
                                    "validated_on_client_navmesh"
                                ),
                                "execution_authority": False,
                            }
                        )
                else:
                    engine.navigator = query
                    status = "RESET_REQUIRED"
                actions.append(
                    {
                        "kind": "OBSERVED_COLLISION_REPLAN",
                        "attempt": recovery_attempts,
                        "local_attempt": local_recovery_attempts,
                        "world_x": collision_x,
                        "world_y": collision_y,
                        "blocker": list(blocker),
                        "excluded_polygons": (
                            candidate_corridor.observed_blocker_polygons_excluded
                        ),
                        "blocker_route_path_length_world": blocker_route_path_length,
                        "baseline_remaining_path_length_world": (
                            baseline_remaining_path_length
                        ),
                        "blocker_route_maximum_path_length_world": (
                            blocker_route_maximum_path_length
                        ),
                        "blocker_route_accepted": blocker_route_accepted,
                        "portal_recenter_accepted": portal_recenter_corridor
                        is not None,
                        "portal_recenter_world": (
                            None
                            if portal_recenter_target is None
                            else [portal_recenter_target.x, portal_recenter_target.y]
                        ),
                        "local_clearance_accepted": local_clearance_corridors
                        is not None,
                        "breadcrumb_backtrack_accepted": (
                            breadcrumb_backtrack_corridor is not None
                        ),
                        "local_clearance_anchors_world": (
                            None
                            if local_clearance_anchors is None
                            else [
                                [point.x, point.y, point.z]
                                for point in local_clearance_anchors
                            ]
                        ),
                        "candidate_complete": candidate_corridor.complete,
                        "candidate_start_z": candidate_corridor.start.z,
                        "reason": (
                            "collision_relative_local_clearance_validated"
                            if local_clearance_corridors is not None
                            else (
                                "fresh_breadcrumb_backtrack_then_obstacle_replan"
                                if breadcrumb_backtrack_corridor is not None
                                else (
                                    "collision_exclusion_then_topology_validated_replan"
                                    if topology_recovery_accepted
                                    else "no_navmesh_validated_clearance_route_requires_reset"
                                )
                            )
                        ),
                    }
                )
                if blocker_route_accepted or portal_recenter_corridor is not None:
                    learned_obstacle_memory = learned_obstacle_memory.observe(
                        map_name=active_map_name,
                        zone_index=args.expected_zone_index,
                        blocker=blocker,
                        run_id=run_id,
                        observed_at=datetime.now(timezone.utc),
                        evidence=DETOUR_EXCLUSION_EVIDENCE,
                    )
                    _write_json_atomic(
                        args.learned_obstacle_memory,
                        learned_obstacle_memory.to_record(),
                    )
                    learned_obstacles_persisted += 1
                    actions.append(
                        {
                            "kind": "LEARNED_OBSTACLE_PERSISTED",
                            "blocker": list(blocker),
                            "memory_file": str(args.learned_obstacle_memory.resolve()),
                            "execution_authority": False,
                        }
                    )
                elif (
                    local_clearance_corridors is None
                    and breadcrumb_backtrack_corridor is None
                ):
                    break
                # Detour queries are bounded but are not part of the 175 ms
                # control-frame lease.  Refresh the live pose after planning;
                # never carry the pre-query timestamp into the next input.
                observation = pose_source.next_observation()
                _, _, world_x, world_y = _position(
                    observation,
                    expected_zone_index=args.expected_zone_index,
                    transform=transform,
                    expected_map_id=args.map_id,
                )
                heading_estimator.reset(x=world_x, y=world_y)
                heading, heading_source = _observe_player_heading(
                    pose_source,
                    visible_heading_observer,
                    predicted_heading_rad=heading,
                    observation=observation,
                    displacement_heading_rad=None,
                )
                last_observed_s = float(observation["timing"]["observed_monotonic_s"])
                no_progress_s = 0.0
                pivot_without_heading_progress_s = 0.0
                pivot_heading_error_anchor_rad = None
                collision_slide_s = 0.0
                progress_gate.reset(
                    path_progress_world=0.0,
                    goal_distance_world=hypot(goal_x - world_x, goal_y - world_y),
                )
                continue

            cycle_checkpoints.append(("recovery_and_handoffs", time.monotonic()))
            before_x, before_y = world_x, world_y
            remaining_before = hypot(goal_x - before_x, goal_y - before_y)
            control_age_ms = (time.monotonic() - last_observed_s) * 1000.0
            if control_age_ms > PRECONTROL_POSE_REFRESH_AGE_MS:
                # Publishing a large external overlay snapshot can briefly
                # outlive the 175 ms input lease on Windows. No stale pose may
                # authorize input: refresh read-only state, recompute steering,
                # and only then continue to the actuator.
                # Keep the already-authorized held state during a bounded
                # read-only pose refresh.  The 450 ms actuator watchdog is the
                # fail-safe if capture stalls; releasing here turned every
                # ordinary refresh into a visible W/RMB pulse.
                observation = pose_source.next_observation()
                _, _, world_x, world_y = _position(
                    observation,
                    expected_zone_index=args.expected_zone_index,
                    transform=transform,
                    expected_map_id=args.map_id,
                )
                last_observed_s = float(observation["timing"]["observed_monotonic_s"])
                heading, heading_source = _observe_player_heading(
                    pose_source,
                    visible_heading_observer,
                    predicted_heading_rad=heading,
                    observation=observation,
                    displacement_heading_rad=None,
                )
                engine.observe_position(
                    x=world_x,
                    y=world_y,
                    observed_at_s=last_observed_s,
                )
                decision_state = SteeringState(world_x, world_y, heading, speed, no_progress_s)
                decision_observation = decision_observation_record(
                    decision_state, observed_monotonic_s=last_observed_s,
                    heading_source=heading_source,
                )
                intent = engine.decide(
                    decision_state,
                    steering_corridor,
                )
                dynamic_tracks = dynamic_tracker.update(
                    pose_source.latest_dynamic_observations,
                    now_s=last_observed_s,
                )
                remember_dynamic_experience(
                    dynamic_tracks,
                    observer_x=world_x,
                    observer_y=world_y,
                    observer_facing_rad=heading,
                )
                dynamic_decision = dynamic_avoidance.decide(
                    dynamic_tracks,
                    now_s=last_observed_s,
                    heading_rad=heading,
                    static_awareness=steering_corridor.start_awareness,
                )
                intent = dynamic_avoidance.apply(
                    intent,
                    dynamic_decision,
                    maximum_mouse_delta=(
                        PredictiveSteeringController.FOLLOW_MAX_MOUSE_DELTA
                    ),
                )
                if intent.projected_z_world is not None:
                    current_z_hint = intent.projected_z_world
                before_x, before_y = world_x, world_y
                remaining_before = hypot(goal_x - before_x, goal_y - before_y)
                actions.append(
                    {
                        "kind": "PRECONTROL_POSE_REFRESHED",
                        "stale_age_ms": control_age_ms,
                        "world_x": world_x,
                        "world_y": world_y,
                        "reason": "overlay_publication_outlived_control_pose_lease",
                    }
                )
                control_age_ms = (time.monotonic() - last_observed_s) * 1000.0
                if control_age_ms > MAXIMUM_CONTROL_OBSERVATION_AGE_MS:
                    raise RuntimeError(
                        "refreshed continuous navigation pose still exceeds the "
                        f"control budget at {control_age_ms:.1f} ms"
                    )
            cycle_checkpoints.append(("pose_refresh", time.monotonic()))
            heading_integrity = assess_heading_integrity(
                heading_rad=heading,
                heading_source=heading_source,
                client_facing_source=getattr(
                    pose_source, "latest_facing_source", "UNAVAILABLE"
                ),
                observed_monotonic_s=last_observed_s,
                last_visible_observed_s=last_visible_heading_observed_s,
                maximum_evidence_age_s=MAX_HEADING_EVIDENCE_AGE_S,
            )
            if not heading_integrity.allow_control:
                motion.release_all()
                actions.append(
                    {
                        "kind": "HEADING_EVIDENCE_LOST",
                        "state": heading_integrity.state,
                        "client_facing_source": (
                            heading_integrity.client_facing_source
                        ),
                        "heading_source": heading_integrity.heading_source,
                        "evidence_age_s": heading_integrity.evidence_age_s,
                        "reason": heading_integrity.reason,
                        "world_x": world_x,
                        "world_y": world_y,
                        "execution_authority": False,
                    }
                )
                status = "HEADING_EVIDENCE_LOST"
                break
            # Strict facing is a per-frame gate, not only a startup check.  A
            # fresh camera estimate may remain numerically valid after the
            # client stops publishing the exact body yaw, or after the body
            # and controller heading diverge.  Never lease another movement
            # frame in that state; release first and leave an explicit trace.
            if args.require_exact_body_heading:
                try:
                    _require_exact_body_heading(
                        observation,
                        heading=heading,
                        heading_source=heading_source,
                        phase=f"control frame {control_frames + 1}",
                    )
                except RuntimeError as error:
                    motion.release_all()
                    actions.append(
                        {
                            "kind": "EXACT_BODY_HEADING_LOST",
                            "frame_index": control_frames + 1,
                            "heading_source": heading_source,
                            "client_facing_source": getattr(
                                pose_source,
                                "latest_facing_source",
                                "UNAVAILABLE",
                            ),
                            "reason": str(error),
                            "world_x": world_x,
                            "world_y": world_y,
                            "execution_authority": False,
                        }
                    )
                    status = "EXACT_BODY_HEADING_LOST"
                    break
            navigation_frame = ContinuousMotionFrame(
                observed_monotonic_s=last_observed_s,
                movement=("MOVE_FORWARD" if intent.forward_hold_ms else None),
                strafe=intent.strafe,
                mouse_look=True,
                mouse_velocity_x_px_s=float(
                    intent.mouse_delta_x
                    * PredictiveSteeringController.MOUSE_COMMAND_VELOCITY_SCALE_HZ
                ),
                reason="continuous_navmesh_corridor_follow",
            )
            refresh_now_s = time.monotonic()
            if refresh_now_s >= next_motion_authority_refresh_s:
                next_motion_authority_refresh_s = refresh_now_s + 0.250
                try:
                    refreshed_authorization_raw = (
                        args.continuous_motion_authorization_file.read_bytes()
                    )
                    refreshed_authority = load_continuous_motion_authority(
                        args.continuous_motion_arm_file.read_bytes(),
                        authorization_raw=refreshed_authorization_raw,
                        session_receipt_raw=args.session_receipt.read_bytes(),
                        realm_revalidation_raw=(
                            args.continuous_motion_revalidation_file.read_bytes()
                        ),
                        target=target,
                        clock=clock,
                        schema_path=CONTINUOUS_MOTION_ARM_SCHEMA,
                        authorization_schema_path=AUTHORIZATION_SCHEMA,
                        prior_authorization_raw=continuous_authorization_raw,
                    )
                    renewed_live = motion.renew_authority(refreshed_authority)
                except (OSError, ValueError, TypeError, KeyError) as error:
                    refresh_error = f"{type(error).__name__}: {error}"
                    if refresh_error != last_motion_authority_refresh_error:
                        actions.append(
                            {
                                "kind": "CONTINUOUS_MOTION_ARM_RENEWAL_REJECTED",
                                "detail": refresh_error,
                                "reason": (
                                    "keep_current_valid_arm_and_fail_closed_if_no_"
                                    "valid_replacement_arrives"
                                ),
                                "execution_authority": False,
                            }
                        )
                    last_motion_authority_refresh_error = refresh_error
                else:
                    last_motion_authority_refresh_error = None
                    if renewed_live:
                        continuous_authorization_raw = refreshed_authorization_raw
                        actions.append(
                            {
                                "kind": "CONTINUOUS_MOTION_ARM_RENEWED_LIVE",
                                "expires_at_monotonic_ms": (
                                    refreshed_authority.expires_at_monotonic_ms
                                ),
                                "reason": (
                                    "new_exact_arm_adopted_without_releasing_held_"
                                    "movement"
                                ),
                                "execution_authority": True,
                            }
                        )
            if not navigation_camera_is_level(
                mouse_delta_y=navigation_frame.mouse_delta_y,
                mouse_velocity_y_px_s=navigation_frame.mouse_velocity_y_px_s,
            ):
                raise RuntimeError(
                    "navigation frame attempted vertical camera motion; refusing input"
                )
            try:
                cycle_checkpoints.append(("authority_and_preinput", time.monotonic()))
                receipt_frame = motion.apply_frame(navigation_frame, cancellation)
            except WindowsInputSinkError as error:
                if (
                    str(error) != "continuous motion frame is stale"
                    or consecutive_stale_control_frame_retries
                    >= MAX_CONSECUTIVE_STALE_CONTROL_FRAME_RETRIES
                ):
                    raise
                consecutive_stale_control_frame_retries += 1
                actions.append(
                    {
                        "kind": "STALE_CONTROL_FRAME_REACQUIRE",
                        "attempt": consecutive_stale_control_frame_retries,
                        "maximum_attempts": (
                            MAX_CONSECUTIVE_STALE_CONTROL_FRAME_RETRIES
                        ),
                        "reason": (
                            "input_released_then_reacquire_visible_pose_and_"
                            "recompute_without_sending_stale_command"
                        ),
                        "execution_authority": False,
                    }
                )
                observation = pose_source.next_observation()
                _, _, world_x, world_y = _position(
                    observation,
                    expected_zone_index=args.expected_zone_index,
                    transform=transform,
                    expected_map_id=args.map_id,
                )
                last_observed_s = float(
                    observation["timing"]["observed_monotonic_s"]
                )
                heading, heading_source = _observe_player_heading(
                    pose_source,
                    visible_heading_observer,
                    predicted_heading_rad=heading,
                    observation=observation,
                    displacement_heading_rad=None,
                )
                engine.observe_position(
                    x=world_x,
                    y=world_y,
                    observed_at_s=last_observed_s,
                )
                observe_traversal(NavPoint(world_x, world_y, current_z_hint))
                continue
            consecutive_stale_control_frame_retries = 0
            control_frames += 1
            if intent.forward_hold_ms:
                forward_actions += 1
            observation = pose_source.next_observation()
            cycle_checkpoints.append(("input_and_observation", time.monotonic()))
            observed_s = float(observation["timing"]["observed_monotonic_s"])
            _, _, world_x, world_y = _position(
                observation,
                expected_zone_index=args.expected_zone_index,
                transform=transform,
                expected_map_id=args.map_id,
            )
            observe_traversal(NavPoint(world_x, world_y, current_z_hint))
            dt_s = max(0.001, observed_s - last_observed_s)
            last_observed_s = observed_s
            if heading is not None and receipt_frame.mouse_velocity_x_px_s:
                heading_integration_dt_s = min(
                    dt_s,
                    MOUSE_HEADING_ACTIVE_LEASE_S,
                )
                if heading_integration_dt_s < dt_s:
                    actions.append(
                        {
                            "kind": "MOUSE_HEADING_INTEGRATION_CLAMPED",
                            "observed_gap_s": dt_s,
                            "active_lease_s": heading_integration_dt_s,
                            "reason": (
                                "continuous_motion_watchdog_releases_velocity_"
                                "during_capture_or_planner_stall"
                            ),
                            "execution_authority": False,
                        }
                    )
                heading = _wrap_angle(
                    heading
                    - receipt_frame.mouse_velocity_x_px_s
                    * heading_integration_dt_s
                    * PredictiveSteeringController.MOUSE_YAW_RAD_PER_PIXEL
                )
            dx, dy = world_x - before_x, world_y - before_y
            progress = hypot(dx, dy)
            remaining_after = hypot(goal_x - world_x, goal_y - world_y)
            physical_motion_continuous = observed_motion_is_continuous(
                displacement_world=progress,
                observation_interval_s=dt_s,
                forward_requested=bool(intent.forward_hold_ms),
            )
            # A projected corridor advance must not reset the no-progress
            # clock when the client visibly paused during a long observation
            # gap.  Keep the evidence explicit in the append-only trace.
            if meaningful_progress and not physical_motion_continuous:
                meaningful_progress = False
            observed_heading = heading_estimator.observe(x=world_x, y=world_y)
            heading_before_visible_refresh = heading
            displacement_heading_for_fusion = (
                observed_heading
                if (
                    intent.forward_hold_ms
                    and physical_motion_continuous
                    and observed_heading is not None
                    and intent.cross_track_error_world <= 1.25
                    and collision_slide_s <= 0.0
                    and no_progress_s <= 0.0
                )
                else None
            )
            heading, heading_source = _observe_player_heading(
                pose_source,
                visible_heading_observer,
                predicted_heading_rad=heading,
                observation=observation,
                displacement_heading_rad=displacement_heading_for_fusion,
                allow_displacement_fusion=(
                    displacement_heading_for_fusion is not None
                ),
            )
            remember_visible_heading(
                observed_s=observed_s,
                heading_source=heading_source,
            )
            if calibration_heading_hold_frames > 0:
                if pose_source.latest_facing_source == EXACT_BODY_HEADING_SOURCE:
                    calibration_heading_hold_frames = 0
                elif heading_source.startswith("VISIBLE_CLIENT_HEADING"):
                    # The fused visible client heading is the primary
                    # observation.  A bounded displacement hold is only a
                    # fallback for the frames in which the minimap/HUD gives
                    # no usable heading; never overwrite a fresh visual
                    # fusion result with a wall-slide-prone chord.
                    calibration_heading_hold_frames -= 1
                elif heading_before_visible_refresh is not None:
                    heading = heading_before_visible_refresh
                    heading_source = "DISPLACEMENT_INITIAL_DIRECTION_CALIBRATION"
                    calibration_heading_hold_frames -= 1
            if progress > 0.08:
                measured_speed = max(2.0, min(12.0, progress / dt_s))
                speed = speed * 0.80 + measured_speed * 0.20
            # Compare the first observed chord with the corridor's own first
            # tangent.  A moving lookahead can already point around a sharp
            # bend and would turn that ordinary curvature into a false
            # cold-start mismatch.
            expected_initial_direction = _corridor_initial_direction(
                corridor,
                fallback=None,
            )
            direction_probe_status, direction_probe_error = (
                assess_initial_forward_direction(
                    expected_heading_rad=expected_initial_direction,
                    observed_heading_rad=observed_heading,
                    # ``DisplacementHeadingEstimator`` already waits for its
                    # bounded chord before returning ``observed_heading``;
                    # pass that chord length rather than only the latest
                    # capture-to-capture step.
                    displacement_world=(
                        heading_estimator.last_displacement_world
                        if observed_heading is not None
                        else progress
                    ),
                    physical_motion_continuous=physical_motion_continuous,
                    forward_requested=bool(intent.forward_hold_ms),
                    cross_track_error_world=intent.cross_track_error_world,
                )
            )
            direction_probe_tangent_projection = (
                None
                if direction_probe_error is None
                else cos(direction_probe_error)
            )
            if (
                initial_direction_probe_pending
                and direction_probe_status in {"ALIGNED", "REALIGN"}
            ):
                exact_client_facing = (
                    pose_source.latest_facing_source == EXACT_BODY_HEADING_SOURCE
                )
                initial_direction_probe_realignment_count += int(
                    direction_probe_status == "REALIGN"
                    and not exact_client_facing
                )
                allow_realignment = _allow_initial_direction_realignment(
                    tangent_projection=direction_probe_tangent_projection,
                    initial_realignment_count=(
                        initial_direction_probe_realignment_count
                    ),
                    cross_track_error_world=intent.cross_track_error_world,
                    collision_slide_s=collision_slide_s,
                    collision_evidence=last_recovery_collision_world is not None,
                    verified_breadcrumb_recovery=(
                        verified_breadcrumb_direction_probe_pending
                    ),
                )
                # The breadcrumb exception is deliberately one-shot.  Any
                # later probe on this corridor must again prove a positive
                # tangent projection before replacing the integrated heading.
                verified_breadcrumb_direction_probe_pending = False
                # A verified structure egress already owns a fresh, bounded
                # corridor from the live pose to its opening.  On legacy TBC
                # the first minimap-only chord can be on the wrong camera end;
                # keep that chord as heading evidence, stop W, and let the
                # follower pivot back onto the proven egress tangent.  A
                # second corridor rebuild here discarded the stair route and
                # recreated the same local loop.  Ordinary mission corridors
                # retain the existing bounded probe/replan behavior.
                structure_egress_initial_calibration = (
                    structure_egress_opening_id is not None
                )
                retry_direction_probe = (
                    direction_probe_status == "REALIGN"
                    and not exact_client_facing
                    and observed_heading is not None
                    and initial_direction_probe_realignment_count
                    < MAX_INITIAL_DIRECTION_PROBE_REALIGNS
                    and allow_realignment
                    and not structure_egress_initial_calibration
                )
                initial_direction_probe_pending = retry_direction_probe
                if (
                    direction_probe_status == "REALIGN"
                    and not exact_client_facing
                    and observed_heading is not None
                    and allow_realignment
                ):
                    # The first physical chord disproved the saved/minimap
                    # orientation.  Retain that chord as the current heading
                    # so the next controller tick enters its ordinary bounded
                    # pivot toward the corridor tangent, with W released.
                    heading = _wrap_angle(observed_heading)
                    heading_source = "DISPLACEMENT_INITIAL_DIRECTION_CALIBRATION"
                    calibration_heading_hold_frames = (
                        INITIAL_DIRECTION_CALIBRATION_HOLD_FRAMES
                    )
                    request_stationary_pivot = getattr(
                        engine.steering,
                        "request_stationary_pivot",
                        None,
                    )
                    if callable(request_stationary_pivot):
                        request_stationary_pivot()
                    actions.append(
                        {
                            "kind": "INITIAL_FORWARD_DIRECTION_REALIGNED",
                            "expected_heading_rad": expected_initial_direction,
                            "observed_displacement_heading_rad": observed_heading,
                            "error_rad": direction_probe_error,
                            "tangent_projection": direction_probe_tangent_projection,
                            "cross_track_error_world": intent.cross_track_error_world,
                            "stationary_pivot_requested": callable(
                                request_stationary_pivot
                            ),
                            "realignment_count": initial_direction_probe_realignment_count,
                            "retry_probe": retry_direction_probe,
                            "reason": (
                                "first_continuous_forward_chord_disagreed_with_"
                                "corridor_tangent;_next_tick_pivots_before_forward_motion_"
                                "within_bounded_probe_limit"
                            ),
                            "clean_first_chord_exception": (
                                direction_probe_tangent_projection is None
                                or direction_probe_tangent_projection
                                < MIN_DIRECTION_REALIGN_TANGENT_PROJECTION
                            ),
                            "execution_authority": False,
                        }
                    )
                    if (
                        not structure_egress_initial_calibration
                        and initial_direction_replan_attempts
                        < MAX_INITIAL_DIRECTION_CORRIDOR_REPLANS
                    ):
                        initial_direction_replan_attempts += 1
                        initial_direction_replan_pending = True
                        actions.append(
                            {
                                "kind": "INITIAL_DIRECTION_CORRIDOR_REPLAN_REQUESTED",
                                "observed_displacement_heading_rad": observed_heading,
                                "cross_track_error_world": intent.cross_track_error_world,
                                "attempt": initial_direction_replan_attempts,
                                "reason": (
                                    "rebuild_corridor_from_fresh_client_pose_after_"
                                    "clean_first_chord_calibration"
                                ),
                                "execution_authority": False,
                            }
                        )
                elif (
                    direction_probe_status == "REALIGN"
                    and not exact_client_facing
                    and observed_heading is not None
                ):
                    # A large chord that points away from the planned tangent
                    # is most often a wall slide.  Do not replace the
                    # integrated camera heading or request another pivot.
                    actions.append(
                        {
                            "kind": "INITIAL_FORWARD_DIRECTION_REALIGNMENT_SKIPPED",
                            "expected_heading_rad": expected_initial_direction,
                            "observed_displacement_heading_rad": observed_heading,
                            "error_rad": direction_probe_error,
                            "tangent_projection": direction_probe_tangent_projection,
                            "cross_track_error_world": intent.cross_track_error_world,
                            "reason": (
                                "forward_chord_had_insufficient_projection_onto_"
                                "corridor_tangent;_retained_integrated_heading"
                            ),
                            "execution_authority": False,
                        }
                    )
                else:
                    actions.append(
                        {
                            "kind": "INITIAL_FORWARD_DIRECTION_CONFIRMED",
                            "expected_heading_rad": expected_initial_direction,
                            "observed_displacement_heading_rad": observed_heading,
                            "error_rad": direction_probe_error,
                            "tangent_projection": direction_probe_tangent_projection,
                            "exact_client_facing": exact_client_facing,
                            "reason": (
                                "first_continuous_forward_chord_agreed_with_"
                                "corridor_tangent_or_exact_client_facing_won"
                            ),
                            "execution_authority": False,
                        }
                    )
            # TBC 2.4.3 has no GetPlayerFacing.  Displacement establishes the
            # initial heading exactly once; it must never overwrite or blend
            # the mouse-integrated yaw afterwards.  A character sliding along
            # WMO collision is moving sideways while still facing the wall.
            # Treat that chord as collision evidence, not as a camera heading.
            heading_divergence = (
                None
                if observed_heading is None or heading is None
                else abs(_wrap_angle(observed_heading - heading))
            )
            heading_divergence_before_realign = heading_divergence
            # A large disagreement after the first calibration means that the
            # client avatar no longer follows the mouse-integrated yaw.  On a
            # short geometry corridor, reacquire from the real displacement
            # and let the follower pivot with W released.  This is deliberately
            # bounded and skipped when an exact HUD facing is available, or
            # when the actor is already far outside the corridor where the
            # chord could simply be a wall slide.
            if (
                intent.forward_hold_ms
                and physical_motion_continuous
                and observed_heading is not None
                and heading is not None
                and pose_source.latest_facing_source != EXACT_BODY_HEADING_SOURCE
                and heading_divergence is not None
                and heading_divergence
                >= LIVE_HEADING_DIVERGENCE_THRESHOLD_RAD
                and direction_probe_tangent_projection is not None
                and direction_probe_tangent_projection
                >= MIN_DIRECTION_REALIGN_TANGENT_PROJECTION
                and heading_estimator.last_displacement_world
                >= INITIAL_FORWARD_DIRECTION_MIN_DISPLACEMENT_WORLD
                and intent.cross_track_error_world
                <= INITIAL_FORWARD_DIRECTION_MAX_CROSS_TRACK_WORLD
                and len(corridor.guidance_points()) <= 3
                and live_heading_divergence_realignment_count
                < MAX_LIVE_HEADING_DIVERGENCE_REALIGNS
            ):
                live_heading_divergence_realignment_count += 1
                heading_before_live_realign = heading
                heading = _wrap_angle(observed_heading)
                heading_source = "DISPLACEMENT_LIVE_DIVERGENCE_REALIGNMENT"
                calibration_heading_hold_frames = (
                    INITIAL_DIRECTION_CALIBRATION_HOLD_FRAMES
                )
                request_stationary_pivot = getattr(
                    engine.steering,
                    "request_stationary_pivot",
                    None,
                )
                if callable(request_stationary_pivot):
                    request_stationary_pivot()
                # The displacement is now the new bounded heading evidence;
                # do not also count the same chord as a wall slide.
                collision_slide_s = 0.0
                actions.append(
                    {
                        "kind": "LIVE_HEADING_DIVERGENCE_REALIGNED",
                        "observed_displacement_heading_rad": observed_heading,
                        "heading_before_realignment_rad": (
                            heading_before_live_realign
                        ),
                        "heading_divergence_rad": heading_divergence_before_realign,
                        "cross_track_error_world": intent.cross_track_error_world,
                        "realignment_count": live_heading_divergence_realignment_count,
                        "stationary_pivot_requested": callable(
                            request_stationary_pivot
                        ),
                        "reason": (
                            "continuous_forward_chord_disagreed_with_integrated_"
                            "yaw_on_short_geometry_corridor"
                        ),
                        "execution_authority": False,
                    }
                )
                heading_divergence = 0.0
            if (
                intent.forward_hold_ms
                and progress > 0.04
                and intent.cross_track_error_world
                >= PredictiveSteeringController.OFF_CORRIDOR_THRESHOLD_WORLD
                and heading_divergence is not None
                and heading_divergence >= 0.90
            ):
                collision_slide_s += dt_s
            else:
                collision_slide_s = max(0.0, collision_slide_s - dt_s * 2.0)
            if meaningful_progress:
                no_progress_s = 0.0
            elif intent.forward_hold_ms:
                no_progress_s += dt_s
            (
                pivot_without_heading_progress_s,
                pivot_heading_error_anchor_rad,
            ) = _update_pivot_stall_clock(
                elapsed_s=pivot_without_heading_progress_s,
                anchor_error_rad=pivot_heading_error_anchor_rad,
                dt_s=dt_s,
                controller_state=intent.state,
                waypoint_error_rad=waypoint_error,
            )
            if pivot_without_heading_progress_s >= PIVOT_STALL_TIMEOUT_S:
                no_progress_s = max(no_progress_s, STUCK_PROGRESS_EVIDENCE_S)
            if collision_slide_s >= COLLISION_SLIDE_EVIDENCE_S:
                no_progress_s = max(no_progress_s, STUCK_PROGRESS_EVIDENCE_S)
            mppi_telemetry = getattr(engine.steering, "mppi_telemetry", None)
            client_facing_source = getattr(
                pose_source, "latest_facing_source", "UNAVAILABLE"
            )
            client_facing_yaw_observation_rad = _player_facing(observation)
            body_yaw_observation_rad = _body_yaw_observation(
                observation,
                client_facing_source=client_facing_source,
            )
            actions.append(
                {
                    "kind": "CONTINUOUS_FRAME",
                    "frame_index": control_frames,
                    "control_cycle_timing": control_cycle_timing_record(
                        previous_observed_s=cycle_previous_observed_s,
                        decision_observed_s=decision_observation["observed_monotonic_s"],
                        post_observed_s=observed_s,
                        checkpoints=cycle_checkpoints,
                    ),
                    "decision_observation": decision_observation,
                    "decision_metrics_reference": "decision_observation",
                    "position_phase": "post_command_observation",
                    "projected_z_source": "decision_corridor_projection_not_observed_z",
                    "controller_state": intent.state,
                    "controller_reason": intent.reason,
                    "mppi": (
                        None
                        if mppi_telemetry is None
                        else {
                            "state": mppi_telemetry.state,
                            "snapshot_id": mppi_telemetry.snapshot_id,
                            "plan_age_s": mppi_telemetry.plan_age_s,
                            "planning_duration_ms": (
                                mppi_telemetry.planning_duration_ms
                            ),
                            "sample_count": mppi_telemetry.sample_count,
                            "feasible_sample_count": (
                                mppi_telemetry.feasible_sample_count
                            ),
                            "fallback_reason": mppi_telemetry.fallback_reason,
                        }
                    ),
                    "held_controls": list(receipt_frame.held_controls),
                    "strafe": intent.strafe,
                    "mouse_look_held": receipt_frame.mouse_look_held,
                    "requested_mouse_delta_x": intent.mouse_delta_x,
                    "mouse_delta_x": receipt_frame.mouse_delta_x,
                    "mouse_delta_y": receipt_frame.mouse_delta_y,
                    "mouse_velocity_x_px_s": receipt_frame.mouse_velocity_x_px_s,
                    "mouse_velocity_y_px_s": receipt_frame.mouse_velocity_y_px_s,
                    "camera_integrity_state": (
                        None
                        if not isinstance(
                            getattr(pose_source, "latest_camera_integrity", None),
                            dict,
                        )
                        else getattr(pose_source, "latest_camera_integrity")[
                            "tracking_state"
                        ]
                    ),
                    "camera_integrity_confidence": (
                        None
                        if not isinstance(
                            getattr(pose_source, "latest_camera_integrity", None),
                            dict,
                        )
                        else getattr(pose_source, "latest_camera_integrity")[
                            "confidence"
                        ]
                    ),
                    "progress_world": progress,
                    "physical_motion_continuous": physical_motion_continuous,
                    "world_x": world_x,
                    "world_y": world_y,
                    "projected_z_world": current_z_hint,
                    "goal_distance_before": remaining_before,
                    "goal_distance_after": remaining_after,
                    "goal_distance_delta": remaining_before - remaining_after,
                    "corridor_progress_world": intent.progress_world,
                    "cross_track_error_world": intent.cross_track_error_world,
                    "lookahead_world": (
                        None
                        if intent.lookahead is None
                        else [
                            intent.lookahead.x,
                            intent.lookahead.y,
                            intent.lookahead.z,
                        ]
                    ),
                    "waypoint_error_rad": waypoint_error,
                    "meaningful_progress": meaningful_progress,
                    "no_progress_s": no_progress_s,
                    "player_facing_rad": client_facing_yaw_observation_rad,
                    "client_facing_source": client_facing_source,
                    # Keep raw body-facing evidence apart from the
                    # mouse-integrated camera/control estimate. The latter is
                    # an estimate, never a direct camera read or server truth.
                    "body_yaw_observation_rad": body_yaw_observation_rad,
                    "body_yaw_observation_source": (
                        client_facing_source
                        if body_yaw_observation_rad is not None
                        else "UNAVAILABLE"
                    ),
                    "camera_yaw_estimate_rad": heading,
                    "camera_yaw_source": CAMERA_YAW_CONTROL_SOURCE,
                    "camera_control_integrity_state": (
                        "RMB_LEVEL_LOCKED"
                        if receipt_frame.mouse_look_held
                        and navigation_camera_is_level(
                            mouse_delta_y=receipt_frame.mouse_delta_y,
                            mouse_velocity_y_px_s=(
                                receipt_frame.mouse_velocity_y_px_s
                            ),
                        )
                        else "UNSAFE"
                    ),
                    "body_camera_yaw_delta_rad": _body_camera_yaw_delta(
                        body_yaw_observation_rad, heading
                    ),
                    "heading_integrity_state": heading_integrity.state,
                    "heading_integrity_evidence_age_s": (
                        heading_integrity.evidence_age_s
                    ),
                    "heading_integrity_reason": heading_integrity.reason,
                    "estimated_heading_rad": heading,
                    "observed_displacement_heading_rad": observed_heading,
                    "heading_divergence_rad": heading_divergence,
                    "collision_slide_s": collision_slide_s,
                    "heading_source": heading_source,
                    "dynamic_avoidance": {
                        "state": dynamic_decision.state,
                        "side": dynamic_decision.side,
                        "risk": dynamic_decision.risk,
                        "track_id": dynamic_decision.track_id,
                        "predicted_x_normalized": (
                            dynamic_decision.predicted_x_normalized
                        ),
                        "predicted_y_normalized": (
                            dynamic_decision.predicted_y_normalized
                        ),
                        "expires_at_s": dynamic_decision.expires_at_s,
                        "reason": dynamic_decision.reason,
                        "active_track_count": len(dynamic_tracks),
                        "adapter_error": (pose_source.latest_dynamic_detection_error),
                        "static_world_mutation": False,
                    },
                    # Keep the live-only timing evidence beside the control
                    # frame.  Offline replay has no DXGI/compositor, so these
                    # values show whether a real pause came from capture or
                    # from the rest of the live loop.
                    "observation_gap_s": dt_s,
                    "observation_latency_ms": getattr(
                        pose_source, "last_observation_latency_ms", None
                    ),
                    "capture_latency_ms": getattr(
                        pose_source, "last_capture_latency_ms", None
                    ),
                    "observed_monotonic_s": observed_s,
                }
            )
            if control_frames % 25 == 0:
                publish_continuity("RUNNING")
        motion.release_all()
        if deferred_camera_intent is not None:
            try:
                _apply_camera_pivot_intent(
                    backend,
                    deferred_camera_intent,
                    hwnd=int(str(receipt["hwnd"]), 16),
                )
            except OSError as error:
                actions.append(
                    {
                        "kind": "DEFERRED_CAMERA_PIVOT_PROFILE_FAILED",
                        "mode": deferred_camera_intent.mode,
                        "reason": type(error).__name__,
                        "execution_authority": False,
                    }
                )
            else:
                actions.append(
                    {
                        "kind": "DEFERRED_CAMERA_PIVOT_PROFILE_APPLIED",
                        "mode": deferred_camera_intent.mode,
                        "restore_composition": (
                            deferred_camera_intent.restore_composition
                        ),
                        "reason": "movement_terminal_before_presentation_restore",
                        "execution_authority": False,
                    }
                )
        actions.append(
            {
                "kind": "TERMINAL_CAMERA_COMPOSITION_PRESERVED",
                "reason": "automatic_setview_is_reserved_for_explicit_recovery",
                "execution_authority": False,
            }
        )
        if cancelled:
            status = "MANUAL_TAKEOVER"
        remaining = hypot(destination_x - world_x, destination_y - world_y)
        ordered_waypoints_completed = (
            0
            if not ordered_goal_queue_active
            else (len(semantic_goals) if status == "ARRIVED" else semantic_goal_index)
        )
        semantic_waypoints_completed = (
            ordered_waypoints_completed if semantic_route is not None else 0
        )
        operator_waypoints_completed = (
            ordered_waypoints_completed if operator_journey is not None else 0
        )
        result = {
            "record_type": "navmesh_roaming_result",
            "schema_version": "0.1",
            "run_id": run_id,
            "status": status,
            "map": active_map_name,
            "runtime_world_source": runtime_world_source,
            "world_pack_id": runtime_world_pack_id,
            "world_pack_content_sha256": runtime_world_pack_content_sha256,
            "structure_access_graph_id": runtime_structure_access_graph_id,
            "structure_access_graph_content_sha256": (
                runtime_structure_access_graph_sha256
            ),
            "zone_index": args.expected_zone_index,
            "start_world_z_hint": args.start_world_z_hint,
            "resumed_from": None
            if args.resume_result is None
            else str(args.resume_result.resolve()),
            "navmesh_sha256": nav_sha,
            "recast_pin": "9f4ce64458dfae86e1239c525ddc219c4e9e06f1",
            "goal_world": [destination_x, destination_y],
            "active_local_goal_world": [goal_x, goal_y],
            "final_world": [world_x, world_y],
            "final_world_z_hint": current_z_hint,
            "remaining_world": remaining,
            "forward_actions": forward_actions,
            "control_frames": control_frames,
            "discrete_turn_actions": 0,
            "continuous_input": True,
            "recovery_attempts": recovery_attempts,
            "local_recovery_attempts": local_recovery_attempts,
            "observed_blockers": [list(item) for item in observed_blockers],
            "learned_obstacle_memory": str(args.learned_obstacle_memory.resolve()),
            "learned_obstacles_loaded": learned_obstacles_loaded,
            "learned_obstacles_persisted": learned_obstacles_persisted,
            "recovery_strategy_memory": str(
                args.recovery_strategy_memory.resolve()
            ),
            "recovery_strategy_failures_persisted": (
                recovery_strategy_failures_persisted
            ),
            "recovery_strategy_skips": recovery_strategy_skips,
            "live_awareness_service_pid": live_awareness.service_pid,
            "live_awareness_query_count": live_awareness.query_count,
            "live_awareness_last_error": live_awareness.last_error,
            "partial_replans": partial_replans,
            "arrival_radius_world": args.arrival_radius_world,
            "semantic_destination_id": args.semantic_destination_id,
            "semantic_destination_name": semantic_destination_name,
            "semantic_destination_radius_world": semantic_destination_radius,
            "semantic_waypoint_count": (
                len(semantic_goals) if semantic_route is not None else 0
            ),
            "semantic_waypoints_completed": semantic_waypoints_completed,
            "semantic_coordinate_system": (
                None if semantic_route is None else "tbc243_client_world_xy"
            ),
            "operator_path_id": (
                None if operator_journey is None else operator_journey.path_id
            ),
            "operator_path_name": (
                None if operator_journey is None else operator_journey.name
            ),
            "operator_resume_index": operator_resume_index,
            "operator_waypoint_count": (
                0 if operator_journey is None else len(semantic_goals)
            ),
            "operator_waypoints_completed": operator_waypoints_completed,
            "ordered_waypoints_completed": ordered_waypoints_completed,
            "search_vantage": search_vantage_evidence,
            "local_static_awareness": _local_static_awareness_record(corridor),
            "operator_controlled": run_control is not None,
            "operator_paused_ms": (
                0.0 if run_control is None else run_control.total_paused_ms
            ),
            "actions": actions,
            "manual_takeover_hotkey": "Pause",
            "static_knowledge": model.static_knowledge,
            "dynamic_knowledge": model.dynamic_knowledge,
            "dynamic_experience": dynamic_experience_summary,
            "safe_retreat_context": safe_retreat_context(),
            "execution_authority": False,
        }
        RESULT_ROOT.mkdir(parents=True, exist_ok=True)
        result_path = RESULT_ROOT / f"navmesh-roaming-{run_id.rsplit(':', 1)[-1]}.json"
        _write_json_atomic(result_path, result)
        publish_continuity(status)
        print(json.dumps({"result_path": str(result_path), **result}, sort_keys=True))
        return 0 if status == "ARRIVED" else 3
    except ContinuousMotionAuthorityError as error:
        # The F4a runtime arm is intentionally short-lived.  When it expires
        # during a bounded slice, release every control and keep the exact
        # client-visible checkpoint so the next slice can re-arm and resume.
        # Do not extend the arm or turn expiry into an execution permission.
        motion.release_all()
        keyboard.release_all()
        mouse.release_all()
        final_world = None
        if observation is not None:
            try:
                _, _, observed_x, observed_y = _position(
                    observation,
                    expected_zone_index=args.expected_zone_index,
                    transform=transform,
                    expected_map_id=args.map_id,
                )
            except (KeyError, TypeError, ValueError, AssertionError):
                observed_x = observed_y = None
            else:
                world_x, world_y = observed_x, observed_y
                observe_traversal(NavPoint(world_x, world_y, current_z_hint))
                final_world = [world_x, world_y]
        actions.append(
            {
                "kind": "CONTINUOUS_MOTION_AUTHORITY_EXPIRED",
                "detail": str(error),
                "world_x": None if final_world is None else final_world[0],
                "world_y": None if final_world is None else final_world[1],
                "reason": (
                    "bounded_runtime_arm_expired_after_controls_were_released"
                ),
                "execution_authority": False,
            }
        )
        result = {
            "record_type": "navmesh_roaming_result",
            "schema_version": "0.1",
            "run_id": run_id,
            "status": "RUNTIME_ARM_EXPIRED",
            "arm_expiry_detail": str(error),
            "map": active_map_name,
            "runtime_world_source": runtime_world_source,
            "world_pack_id": runtime_world_pack_id,
            "world_pack_content_sha256": runtime_world_pack_content_sha256,
            "structure_access_graph_id": runtime_structure_access_graph_id,
            "structure_access_graph_content_sha256": (
                runtime_structure_access_graph_sha256
            ),
            "zone_index": args.expected_zone_index,
            "start_world_z_hint": args.start_world_z_hint,
            "resumed_from": (
                None
                if args.resume_result is None
                else str(args.resume_result.resolve())
            ),
            "navmesh_sha256": nav_sha,
            "recast_pin": "9f4ce64458dfae86e1239c525ddc219c4e9e06f1",
            "goal_world": [destination_x, destination_y],
            "active_local_goal_world": [goal_x, goal_y],
            "final_world": final_world,
            "final_world_z_hint": current_z_hint,
            "remaining_world": (
                None
                if final_world is None
                else hypot(destination_x - final_world[0], destination_y - final_world[1])
            ),
            "forward_actions": forward_actions,
            "control_frames": control_frames,
            "discrete_turn_actions": 0,
            "continuous_input": True,
            "recovery_attempts": recovery_attempts,
            "local_recovery_attempts": local_recovery_attempts,
            "observed_blockers": [list(item) for item in observed_blockers],
            "learned_obstacle_memory": str(args.learned_obstacle_memory.resolve()),
            "learned_obstacles_loaded": learned_obstacles_loaded,
            "learned_obstacles_persisted": learned_obstacles_persisted,
            "recovery_strategy_memory": str(
                args.recovery_strategy_memory.resolve()
            ),
            "recovery_strategy_failures_persisted": (
                recovery_strategy_failures_persisted
            ),
            "recovery_strategy_skips": recovery_strategy_skips,
            "partial_replans": partial_replans,
            "arrival_radius_world": args.arrival_radius_world,
            "semantic_destination_id": args.semantic_destination_id,
            "semantic_destination_name": semantic_destination_name,
            "semantic_destination_radius_world": semantic_destination_radius,
            "semantic_waypoint_count": (
                len(semantic_goals) if semantic_route is not None else 0
            ),
            "semantic_waypoints_completed": (
                semantic_goal_index if semantic_route is not None else 0
            ),
            "semantic_coordinate_system": (
                None if semantic_route is None else "tbc243_client_world_xy"
            ),
            "operator_controlled": run_control is not None,
            "operator_paused_ms": (
                0.0 if run_control is None else run_control.total_paused_ms
            ),
            "actions": actions,
            "resume_policy": "REISSUE_RUNTIME_ARM_AND_REPLAN_FROM_FRESH_LIVE_POSITION",
            "manual_takeover_hotkey": "Pause",
            "static_knowledge": model.static_knowledge,
            "dynamic_knowledge": model.dynamic_knowledge,
            "dynamic_experience": dynamic_experience_summary,
            "safe_retreat_context": safe_retreat_context(),
            "execution_authority": False,
        }
        RESULT_ROOT.mkdir(parents=True, exist_ok=True)
        result_path = RESULT_ROOT / f"navmesh-roaming-{run_id.rsplit(':', 1)[-1]}.json"
        _write_json_atomic(result_path, result)
        publish_continuity("RUNTIME_ARM_EXPIRED")
        print(json.dumps({"result_path": str(result_path), **result}, sort_keys=True))
        return 8
    except CombatHandoffRequired as error:
        motion.release_all()
        keyboard.release_all()
        mouse.release_all()
        travel_capability_at_handoff = pose_source.latest_travel_capability
        try:
            _, _, world_x, world_y = _position(
                error.observation,
                expected_zone_index=args.expected_zone_index,
                transform=transform,
                expected_map_id=args.map_id,
            )
        except (KeyError, TypeError, ValueError, AssertionError):
            world_x = world_y = None
        if world_x is not None and world_y is not None:
            observe_traversal(NavPoint(world_x, world_y, current_z_hint))
        actions.append(
            {
                "kind": "COMBAT_HANDOFF_REQUIRED",
                "target_identity_crc16": error.target_identity_crc16,
                "world_x": world_x,
                "world_y": world_y,
                "reason": "movement_released_before_separate_combat_authority",
                "in_combat": True,
                "health_fraction": (
                    None
                    if travel_capability_at_handoff is None
                    else travel_capability_at_handoff.health_fraction
                ),
                "minimum_travel_health_fraction": (
                    args.minimum_travel_health_fraction
                ),
            }
        )
        result = {
            "record_type": "navmesh_roaming_result",
            "schema_version": "0.1",
            "run_id": run_id,
            "status": "COMBAT_HANDOFF_REQUIRED",
            "map": active_map_name,
            "runtime_world_source": runtime_world_source,
            "world_pack_id": runtime_world_pack_id,
            "world_pack_content_sha256": runtime_world_pack_content_sha256,
            "structure_access_graph_id": runtime_structure_access_graph_id,
            "structure_access_graph_content_sha256": (
                runtime_structure_access_graph_sha256
            ),
            "zone_index": args.expected_zone_index,
            "navmesh_sha256": nav_sha,
            "goal_world": [destination_x, destination_y],
            "active_local_goal_world": [goal_x, goal_y],
            "final_world": (
                None if world_x is None or world_y is None else [world_x, world_y]
            ),
            "target_identity_crc16": error.target_identity_crc16,
            "in_combat": True,
            "health_fraction": (
                None
                if travel_capability_at_handoff is None
                else travel_capability_at_handoff.health_fraction
            ),
            "minimum_travel_health_fraction": (
                args.minimum_travel_health_fraction
            ),
            "semantic_destination_id": args.semantic_destination_id,
            "operator_path_id": (
                None if operator_journey is None else operator_journey.path_id
            ),
            "operator_waypoint_index": (
                semantic_goal_index if operator_journey is not None else None
            ),
            "resume_policy": "REPLAN_FROM_FRESH_LIVE_POSITION",
            "actions": actions,
            "dynamic_experience": dynamic_experience_summary,
            "safe_retreat_context": safe_retreat_context(),
            "manual_takeover_hotkey": "Pause",
            "execution_authority": False,
        }
        RESULT_ROOT.mkdir(parents=True, exist_ok=True)
        result_path = RESULT_ROOT / f"navmesh-roaming-{run_id.rsplit(':', 1)[-1]}.json"
        _write_json_atomic(result_path, result)
        publish_continuity("COMBAT_HANDOFF_REQUIRED")
        print(json.dumps({"result_path": str(result_path), **result}, sort_keys=True))
        return 6
    except ClientVisibleStateError as error:
        motion.release_all()
        keyboard.release_all()
        mouse.release_all()
        if error.last_valid_pose is not None:
            try:
                _, _, world_x, world_y = _position(
                    error.last_valid_pose,
                    expected_zone_index=args.expected_zone_index,
                    transform=transform,
                    expected_map_id=args.map_id,
                )
            except (KeyError, TypeError, ValueError, AssertionError):
                world_x = world_y = None
        state_record = observation_to_record(error.observation)
        camera_integrity = None
        if isinstance(error.last_valid_pose, dict):
            candidate_camera_integrity = error.last_valid_pose.get("camera_integrity")
            if isinstance(candidate_camera_integrity, dict):
                camera_integrity = candidate_camera_integrity
        camera_anchor_lost = (
            isinstance(camera_integrity, dict)
            and camera_integrity.get("tracking_state") != "VISIBLE"
        )
        if camera_anchor_lost:
            actions.append(
                {
                    "kind": "CAMERA_ACTOR_ANCHOR_LOST",
                    "camera_integrity": camera_integrity,
                    "reason": "movement_input_released_when_player_left_screen",
                    "execution_authority": False,
                }
            )
        actions.append(
            {
                "kind": "VISIBLE_CLIENT_STATE",
                "state": error.observation.state.value,
                "confidence": error.observation.confidence,
                "evidence": dict(error.observation.evidence),
                "world_x": world_x,
                "world_y": world_y,
                "reason": "movement_input_released_fail_closed",
            }
        )
        terminal_status = "CAMERA_ACTOR_LOST" if camera_anchor_lost else error.observation.state.value
        result = {
            "record_type": "navmesh_roaming_result",
            "schema_version": "0.1",
            "run_id": run_id,
            "status": terminal_status,
            "map": active_map_name,
            "runtime_world_source": runtime_world_source,
            "world_pack_id": runtime_world_pack_id,
            "world_pack_content_sha256": runtime_world_pack_content_sha256,
            "structure_access_graph_id": runtime_structure_access_graph_id,
            "structure_access_graph_content_sha256": (
                runtime_structure_access_graph_sha256
            ),
            "zone_index": args.expected_zone_index,
            "start_world_z_hint": args.start_world_z_hint,
            "resumed_from": (
                None
                if args.resume_result is None
                else str(args.resume_result.resolve())
            ),
            "navmesh_sha256": nav_sha,
            "recast_pin": "9f4ce64458dfae86e1239c525ddc219c4e9e06f1",
            "goal_world": [destination_x, destination_y],
            "active_local_goal_world": [goal_x, goal_y],
            "final_world": (
                None if world_x is None or world_y is None else [world_x, world_y]
            ),
            "final_world_z_hint": current_z_hint,
            "remaining_world": (
                None
                if world_x is None or world_y is None
                else hypot(destination_x - world_x, destination_y - world_y)
            ),
            "forward_actions": forward_actions,
            "control_frames": control_frames,
            "discrete_turn_actions": 0,
            "continuous_input": True,
            "recovery_attempts": recovery_attempts,
            "local_recovery_attempts": local_recovery_attempts,
            "observed_blockers": [list(item) for item in observed_blockers],
            "learned_obstacle_memory": str(args.learned_obstacle_memory.resolve()),
            "learned_obstacles_loaded": learned_obstacles_loaded,
            "learned_obstacles_persisted": learned_obstacles_persisted,
            "recovery_strategy_memory": str(
                args.recovery_strategy_memory.resolve()
            ),
            "recovery_strategy_failures_persisted": (
                recovery_strategy_failures_persisted
            ),
            "recovery_strategy_skips": recovery_strategy_skips,
            "partial_replans": partial_replans,
            "arrival_radius_world": args.arrival_radius_world,
            "semantic_destination_id": args.semantic_destination_id,
            "semantic_destination_name": semantic_destination_name,
            "semantic_destination_radius_world": semantic_destination_radius,
            "semantic_waypoint_count": (
                len(semantic_goals) if semantic_route is not None else 0
            ),
            "semantic_waypoints_completed": (
                semantic_goal_index if semantic_route is not None else 0
            ),
            "semantic_coordinate_system": (
                None if semantic_route is None else "tbc243_client_world_xy"
            ),
            "operator_path_id": (
                None if operator_journey is None else operator_journey.path_id
            ),
            "operator_path_name": (
                None if operator_journey is None else operator_journey.name
            ),
            "operator_resume_index": operator_resume_index,
            "operator_waypoint_count": (
                0 if operator_journey is None else len(semantic_goals)
            ),
            "operator_waypoints_completed": (
                semantic_goal_index if operator_journey is not None else 0
            ),
            "visible_client_state": state_record,
            "camera_integrity": camera_integrity,
            "operator_controlled": run_control is not None,
            "operator_paused_ms": (
                0.0 if run_control is None else run_control.total_paused_ms
            ),
            "actions": actions,
            "manual_takeover_hotkey": "Pause",
            "static_knowledge": model.static_knowledge,
            "dynamic_knowledge": model.dynamic_knowledge,
            "dynamic_experience": dynamic_experience_summary,
            "execution_authority": False,
        }
        RESULT_ROOT.mkdir(parents=True, exist_ok=True)
        result_path = RESULT_ROOT / f"navmesh-roaming-{run_id.rsplit(':', 1)[-1]}.json"
        _write_json_atomic(result_path, result)
        publish_continuity(
            terminal_status, visible_state=error.observation
        )
        print(json.dumps({"result_path": str(result_path), **result}, sort_keys=True))
        return 4
    except CaptureObservationError as error:
        motion.release_all()
        keyboard.release_all()
        mouse.release_all()
        if error.last_valid_pose is not None:
            try:
                _, _, world_x, world_y = _position(
                    error.last_valid_pose,
                    expected_zone_index=args.expected_zone_index,
                    transform=transform,
                    expected_map_id=args.map_id,
                )
            except (KeyError, TypeError, ValueError, AssertionError):
                pass
        actions.append(
            {
                "kind": "CAPTURE_SOURCE_STOP",
                "error_type": error.cause_type,
                "detail": error.detail[-512:],
                "capture_restart_count": int(
                    getattr(pose_source, "capture_restart_count", 0)
                ),
                "world_x": world_x,
                "world_y": world_y,
                "reason": "movement_input_released_and_trace_preserved_fail_closed",
                "execution_authority": False,
            }
        )
        result = {
            "record_type": "navmesh_roaming_result",
            "schema_version": "0.1",
            "run_id": run_id,
            "status": "CAPTURE_SOURCE_LOST",
            "capture_error_type": error.cause_type,
            "capture_error_detail": error.detail[-512:],
            "capture_restart_count": int(
                getattr(pose_source, "capture_restart_count", 0)
            ),
            "map": active_map_name,
            "runtime_world_source": runtime_world_source,
            "world_pack_id": runtime_world_pack_id,
            "world_pack_content_sha256": runtime_world_pack_content_sha256,
            "structure_access_graph_id": runtime_structure_access_graph_id,
            "structure_access_graph_content_sha256": (
                runtime_structure_access_graph_sha256
            ),
            "zone_index": args.expected_zone_index,
            "start_world_z_hint": args.start_world_z_hint,
            "resumed_from": (
                None
                if args.resume_result is None
                else str(args.resume_result.resolve())
            ),
            "navmesh_sha256": nav_sha,
            "recast_pin": "9f4ce64458dfae86e1239c525ddc219c4e9e06f1",
            "goal_world": [destination_x, destination_y],
            "active_local_goal_world": [goal_x, goal_y],
            "final_world": (
                None if world_x is None or world_y is None else [world_x, world_y]
            ),
            "final_world_z_hint": current_z_hint,
            "remaining_world": (
                None
                if world_x is None or world_y is None
                else hypot(destination_x - world_x, destination_y - world_y)
            ),
            "forward_actions": forward_actions,
            "control_frames": control_frames,
            "discrete_turn_actions": 0,
            "continuous_input": True,
            "recovery_attempts": recovery_attempts,
            "local_recovery_attempts": local_recovery_attempts,
            "observed_blockers": [list(item) for item in observed_blockers],
            "learned_obstacle_memory": str(args.learned_obstacle_memory.resolve()),
            "learned_obstacles_loaded": learned_obstacles_loaded,
            "learned_obstacles_persisted": learned_obstacles_persisted,
            "recovery_strategy_memory": str(
                args.recovery_strategy_memory.resolve()
            ),
            "recovery_strategy_failures_persisted": (
                recovery_strategy_failures_persisted
            ),
            "recovery_strategy_skips": recovery_strategy_skips,
            "partial_replans": partial_replans,
            "arrival_radius_world": args.arrival_radius_world,
            "semantic_destination_id": args.semantic_destination_id,
            "semantic_destination_name": semantic_destination_name,
            "semantic_destination_radius_world": semantic_destination_radius,
            "semantic_waypoint_count": (
                len(semantic_goals) if semantic_route is not None else 0
            ),
            "semantic_waypoints_completed": (
                semantic_goal_index if semantic_route is not None else 0
            ),
            "semantic_coordinate_system": (
                None if semantic_route is None else "tbc243_client_world_xy"
            ),
            "operator_path_id": (
                None if operator_journey is None else operator_journey.path_id
            ),
            "operator_path_name": (
                None if operator_journey is None else operator_journey.name
            ),
            "operator_resume_index": operator_resume_index,
            "operator_waypoint_count": (
                0 if operator_journey is None else len(semantic_goals)
            ),
            "operator_waypoints_completed": (
                semantic_goal_index if operator_journey is not None else 0
            ),
            "operator_controlled": run_control is not None,
            "operator_paused_ms": (
                0.0 if run_control is None else run_control.total_paused_ms
            ),
            "actions": actions,
            "manual_takeover_hotkey": "Pause",
            "static_knowledge": model.static_knowledge,
            "dynamic_knowledge": model.dynamic_knowledge,
            "dynamic_experience": dynamic_experience_summary,
            "safe_retreat_context": safe_retreat_context(),
            "execution_authority": False,
        }
        RESULT_ROOT.mkdir(parents=True, exist_ok=True)
        result_path = RESULT_ROOT / f"navmesh-roaming-{run_id.rsplit(':', 1)[-1]}.json"
        _write_json_atomic(result_path, result)
        publish_continuity("CAPTURE_SOURCE_LOST")
        print(json.dumps({"result_path": str(result_path), **result}, sort_keys=True))
        return 7
    finally:
        try:
            close_steering = getattr(mission_steering, "close", None)
            if close_steering is not None:
                close_steering()
        finally:
            try:
                if dynamic_experience_store is not None:
                    dynamic_experience_store.close()
            finally:
                try:
                    live_awareness.close()
                finally:
                    try:
                        semantic_preplan_executor.shutdown(
                            wait=True,
                            cancel_futures=True,
                        )
                    finally:
                        try:
                            semantic_advisory_executor.shutdown(
                                wait=True,
                                cancel_futures=True,
                            )
                        finally:
                            try:
                                semantic_frontier_preplan_executor.shutdown(
                                    wait=True,
                                    cancel_futures=True,
                                )
                            finally:
                                try:
                                    movement_lab_publish_executor.shutdown(
                                        wait=True,
                                        cancel_futures=True,
                                    )
                                finally:
                                    try:
                                        disarm()
                                    finally:
                                        try:
                                            motion.close()
                                        finally:
                                            try:
                                                pose_source.close()
                                            finally:
                                                keyboard.close()
                                                mouse.close()


if __name__ == "__main__":
    raise SystemExit(run())
