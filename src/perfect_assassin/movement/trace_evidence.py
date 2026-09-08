"""Read-only provenance for decisions and asset geometry; never grants input."""
from __future__ import annotations

from math import isfinite

from .client_navmesh import LocalStaticAwareness
from .predictive_steering import SteeringState


def control_cycle_timing_record(*, previous_observed_s: float,
                                decision_observed_s: float,
                                post_observed_s: float,
                                checkpoints: list[tuple[str, float]]) -> dict[str, object]:
    """Account for refreshed observations without erasing inter-frame latency.

    Stage durations are wall time on the control thread, not CPU attribution.
    A stage may include scheduling/GIL waits; its name does not prove the cause.
    The first interval also includes the preceding frame's post-processing.
    """
    times = [previous_observed_s, decision_observed_s, post_observed_s]
    times.extend(stamp for _, stamp in checkpoints)
    if not all(isfinite(t) for t in times):
        raise ValueError('control timing requires finite timestamps')
    if not previous_observed_s <= decision_observed_s <= post_observed_s:
        raise ValueError('control observation timestamps are not chronological')
    stages = {}
    last = previous_observed_s
    for name, stamp in checkpoints:
        if not name or name in stages or stamp < last:
            raise ValueError('control checkpoints must be ordered and uniquely named')
        stages[name] = (stamp - last) * 1000.0
        last = stamp
    return {
        'previous_observed_monotonic_s': previous_observed_s,
        'post_to_post_ms': (post_observed_s - previous_observed_s) * 1000.0,
        'before_decision_sample_ms': (decision_observed_s - previous_observed_s) * 1000.0,
        'decision_to_post_ms': (post_observed_s - decision_observed_s) * 1000.0,
        'stage_wall_ms': stages,
        'stage_semantics': 'WALL_TIME_INCLUDES_SCHEDULING_NOT_CPU_CAUSALITY',
        'execution_authority': False,
    }


def decision_observation_record(state: SteeringState, *, observed_monotonic_s: float,
                                heading_source: str) -> dict[str, object]:
    """Copy the input sample before deciding, not the next observed position.

    The existing CONTINUOUS_FRAME coordinates are the post-command observation.
    Cross-track/progress/lookahead belong to this earlier decision sample. No
    Z is invented: corridor-projected height is not a client observation.
    """
    return {
        "observed_monotonic_s": observed_monotonic_s,
        "world_x": state.x,
        "world_y": state.y,
        "heading_rad": state.heading_rad,
        "heading_source": heading_source,
        "speed_world_per_s": state.speed_world_per_s,
        "no_progress_s": state.no_progress_s,
        "position_source": "client_visible_pose",
        "execution_authority": False,
    }


def local_boundary_trace_record(awareness: LocalStaticAwareness, *,
                                observed_monotonic_s: float) -> dict[str, object]:
    """Retain the worker's bounded geometry, with omissions explicit.

    Navmesh boundaries/radial probes are evidence, not a physical collision
    certificate. In particular, a truncated set cannot prove free space.
    """
    return {
        "source": "client_asset_navmesh_awareness",
        "observed_monotonic_s": observed_monotonic_s,
        "topology_radius_yards": awareness.topology_radius_yards,
        "component_truncated": awareness.component_truncated,
        "wall_segments_truncated": awareness.wall_segments_truncated,
        "wall_segments": [
            {"left": [w.left.x, w.left.y, w.left.z],
             "right": [w.right.x, w.right.y, w.right.z],
             "distance_yards": w.distance_yards}
            for w in awareness.wall_segments
        ],
        "radial_probes": [
            {"bearing_rad": p.bearing_rad, "clearance_yards": p.clearance_yards,
             "navmesh_reachable": p.navmesh_reachable}
            for p in awareness.radial_probes
        ],
        "physical_contact_proven": False,
        "execution_authority": False,
    }
