"""Replay recorded visible heading evidence through the bounded TBC fusion.

This script is deliberately read-only with respect to the game.  It consumes a
retained ``navmesh_roaming_result`` JSON file and replays the recorded minimap
marker plus mouse command timing through ``VisibleHeadingObserver``.  It does
not send input, open a client, query a server, or rebuild a WorldPack.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from math import isfinite, pi
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.execution.windows_continuous_motion import (
    CONTINUOUS_LEASE_TIMEOUT_MS,
)
from perfect_assassin.movement.heading_estimator import VisibleHeadingObserver
from perfect_assassin.movement.predictive_steering import PredictiveSteeringController


ACTIVE_HEADING_LEASE_S = CONTINUOUS_LEASE_TIMEOUT_MS / 1000.0
KNOWN_CLIENT_FACING_SOURCES = frozenset(
    {
        "COORDINATE_HUD_EXACT",
        "MINIMAP_VISION_FALLBACK",
    }
)


def _wrap_angle(value: float) -> float:
    while value > pi:
        value -= 2.0 * pi
    while value < -pi:
        value += 2.0 * pi
    return value


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _has_usable_client_facing_source(action: dict[str, Any]) -> bool:
    source = action.get("client_facing_source")
    if (
        not isinstance(source, str)
        or source.strip() not in KNOWN_CLIENT_FACING_SOURCES
    ):
        return False
    # ``player_facing_rad`` is the raw value from the labelled client-facing
    # channel.  The runner reserves ``body_yaw_observation_rad`` for exact
    # coordinate-HUD evidence, so a minimap frame must not pass by borrowing
    # that field.
    raw_yaw = action.get("player_facing_rad")
    if raw_yaw is None and source == "COORDINATE_HUD_EXACT":
        raw_yaw = action.get("body_yaw_observation_rad")
    return _finite_number(raw_yaw)


def replay_heading_actions(result: dict[str, Any]) -> dict[str, Any]:
    """Replay visible heading observations from one retained runtime result."""

    actions = result.get("actions")
    if result.get("record_type") != "navmesh_roaming_result" or not isinstance(actions, list):
        raise ValueError("result is not a navmesh_roaming_result with actions")

    recorded_sources: Counter[str] = Counter()
    recorded_client_sources: Counter[str] = Counter()
    replayed_sources: Counter[str] = Counter()
    corrections: list[float] = []
    replayed_frames = 0
    visible_frames = 0
    malformed_frames = 0
    frames_missing_client_source = 0
    invalid_client_source_frames = 0
    previous_observed_s: float | None = None
    heading: float | None = None
    observer = VisibleHeadingObserver()

    for action in actions:
        if not isinstance(action, dict) or action.get("kind") != "CONTINUOUS_FRAME":
            continue
        source = action.get("heading_source")
        if isinstance(source, str):
            recorded_sources[source] += 1
        client_source = action.get("client_facing_source")
        if _has_usable_client_facing_source(action):
            recorded_client_sources[client_source] += 1
        else:
            frames_missing_client_source += 1
            if isinstance(client_source, str) and client_source.strip():
                invalid_client_source_frames += 1
        visible = action.get("player_facing_rad")
        observed_s = action.get("observed_monotonic_s")
        velocity = action.get("mouse_velocity_x_px_s", 0.0)
        if not (_finite_number(visible) and _finite_number(observed_s) and _finite_number(velocity)):
            malformed_frames += 1
            continue
        visible_frames += 1
        predicted: float | None = None
        if heading is not None and previous_observed_s is not None:
            dt_s = max(0.0, min(float(observed_s) - previous_observed_s, ACTIVE_HEADING_LEASE_S))
            predicted = _wrap_angle(
                heading
                - float(velocity)
                * dt_s
                * PredictiveSteeringController.MOUSE_YAW_RAD_PER_PIXEL
            )
        replayed, replayed_source = observer.observe(
            predicted_heading_rad=predicted,
            visible_heading_rad=float(visible),
            displacement_heading_rad=None,
        )
        if replayed is None:
            malformed_frames += 1
            continue
        replayed_frames += 1
        replayed_sources[replayed_source] += 1
        if predicted is not None:
            corrections.append(abs(_wrap_angle(replayed - predicted)))
        heading = replayed
        previous_observed_s = float(observed_s)

    recorded_fused = sum(
        count
        for source, count in recorded_sources.items()
        if source.startswith("VISIBLE_CLIENT_HEADING")
    )
    replayed_fused = sum(
        count
        for source, count in replayed_sources.items()
        if source.startswith("VISIBLE_CLIENT_HEADING")
    )
    return {
        "run_id": result.get("run_id"),
        "status": result.get("status"),
        "recorded_control_frames": sum(
            1 for action in actions if isinstance(action, dict) and action.get("kind") == "CONTINUOUS_FRAME"
        ),
        "visible_heading_frames": visible_frames,
        "replayed_frames": replayed_frames,
        "malformed_frames": malformed_frames,
        "recorded_heading_sources": dict(recorded_sources),
        "recorded_client_facing_sources": dict(recorded_client_sources),
        "frames_missing_client_facing_source": frames_missing_client_source,
        "invalid_client_facing_source_frames": invalid_client_source_frames,
        "client_facing_source_complete": frames_missing_client_source == 0,
        "replayed_heading_sources": dict(replayed_sources),
        "recorded_visible_fused_frames": recorded_fused,
        "replayed_visible_fused_frames": replayed_fused,
        "replayed_fused_fraction": (
            replayed_fused / replayed_frames if replayed_frames else 0.0
        ),
        "max_bounded_correction_rad": max(corrections, default=0.0),
        "mean_bounded_correction_rad": (
            sum(corrections) / len(corrections) if corrections else 0.0
        ),
        "active_heading_lease_s": ACTIVE_HEADING_LEASE_S,
        "mouse_yaw_rad_per_pixel": PredictiveSteeringController.MOUSE_YAW_RAD_PER_PIXEL,
        "input_emitted": False,
        "server_truth_used": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay retained heading evidence through bounded visual fusion (offline only).",
    )
    parser.add_argument("result", type=Path, nargs="+")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    reports = []
    for path in arguments.result:
        result = json.loads(path.read_text(encoding="utf-8"))
        report = replay_heading_actions(result)
        report["result"] = str(path)
        reports.append(report)
    rendered = json.dumps(reports[0] if len(reports) == 1 else reports, indent=2, ensure_ascii=False) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
