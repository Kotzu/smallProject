"""Replay the bounded live heading-integrity gate without opening the game.

The retained runtime JSON is treated as an observation trace only.  This
script never sends input and stops the replay at the first frame where the
same fail-closed policy used by the runner would release control.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from math import isfinite
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.heading_integrity import (
    KNOWN_CLIENT_FACING_SOURCES,
    MAX_HEADING_EVIDENCE_AGE_S,
    assess_heading_integrity,
    is_current_visual_heading,
)


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def _heading_value(frame: dict[str, Any]) -> float | None:
    """Read the heading that the runner would have passed to the gate."""

    for key in ("camera_yaw_estimate_rad", "estimated_heading_rad", "player_facing_rad"):
        value = frame.get(key)
        if value is None:
            continue
        return float(value) if _finite_number(value) else None
    return None


def _raw_client_facing_value(frame: dict[str, Any]) -> float | None:
    """Read the raw facing witness without borrowing the camera estimate.

    A visible-source label is meaningful only when the corresponding raw
    client-facing value is present in the same frame.  The exact HUD channel
    stores that value in ``body_yaw_observation_rad`` as a compatibility
    fallback for older traces; minimap frames must use ``player_facing_rad``.
    """

    source = frame.get("client_facing_source")
    if source not in KNOWN_CLIENT_FACING_SOURCES:
        # A numeric player_facing field without a known client source may be a
        # legacy camera estimate. Never expose it as raw facing evidence.
        return None
    raw = frame.get("player_facing_rad")
    if raw is None and source == "COORDINATE_HUD_EXACT":
        raw = frame.get("body_yaw_observation_rad")
    return float(raw) if _finite_number(raw) else None


def replay_heading_integrity(
    result: dict[str, Any],
    *,
    maximum_evidence_age_s: float = MAX_HEADING_EVIDENCE_AGE_S,
) -> dict[str, Any]:
    """Emulate the runtime gate until its first fail-closed decision."""

    actions = result.get("actions")
    if result.get("record_type") != "navmesh_roaming_result" or not isinstance(actions, list):
        raise ValueError("result is not a navmesh_roaming_result with actions")

    frames = [
        action
        for action in actions
        if isinstance(action, dict) and action.get("kind") == "CONTINUOUS_FRAME"
    ]
    state_counts: Counter[str] = Counter()
    heading_sources: Counter[str] = Counter()
    client_sources: Counter[str] = Counter()
    current_visual_frames = 0
    malformed_frames = 0
    last_visible_observed_s: float | None = None
    first_rejection: dict[str, Any] | None = None
    evaluated_frames = 0
    missing_raw_client_facing_frames = 0

    for frame in frames:
        heading_source = frame.get("heading_source")
        client_source = frame.get("client_facing_source", "UNAVAILABLE")
        if isinstance(heading_source, str):
            heading_sources[heading_source] += 1
        if isinstance(client_source, str):
            client_sources[client_source] += 1

    for frame in frames:
        evaluated_frames += 1
        heading_source = frame.get("heading_source")
        client_source = frame.get("client_facing_source", "UNAVAILABLE")
        observed_s = frame.get("observed_monotonic_s")
        heading_value = _heading_value(frame)
        raw_client_facing = _raw_client_facing_value(frame)
        client_source_is_known = (
            isinstance(client_source, str)
            and client_source in KNOWN_CLIENT_FACING_SOURCES
        )
        frame_malformed = heading_value is None
        if client_source_is_known and raw_client_facing is None:
            # Never let a retained camera estimate stand in for a missing
            # current visual facing witness.  This is the offline equivalent
            # of the runtime facing-first preflight gate.
            frame_malformed = True
            missing_raw_client_facing_frames += 1
            heading_value = None
        if not _finite_number(observed_s):
            frame_malformed = True
            observed_s_value = float("nan")
        else:
            observed_s_value = float(observed_s)
        if frame_malformed:
            malformed_frames += 1

        decision = assess_heading_integrity(
            heading_rad=heading_value,
            heading_source=heading_source if isinstance(heading_source, str) else None,
            client_facing_source=client_source if isinstance(client_source, str) else None,
            observed_monotonic_s=observed_s_value,
            last_visible_observed_s=last_visible_observed_s,
            maximum_evidence_age_s=maximum_evidence_age_s,
        )
        state_counts[decision.state] += 1
        if is_current_visual_heading(
            heading_source=heading_source if isinstance(heading_source, str) else None,
            client_facing_source=client_source if isinstance(client_source, str) else None,
        ) and decision.state == "VISIBLE":
            current_visual_frames += 1
            last_visible_observed_s = observed_s_value

        if not decision.allow_control:
            first_rejection = {
                "frame_index": frame.get("frame_index"),
                "evaluated_index": evaluated_frames,
                "state": decision.state,
                "client_facing_source": decision.client_facing_source,
                "heading_source": decision.heading_source,
                "raw_client_facing_available": raw_client_facing is not None,
                "evidence_age_s": decision.evidence_age_s,
                "reason": decision.reason,
                "observed_monotonic_s": (
                    None if not _finite_number(observed_s) else float(observed_s)
                ),
                "world_x": frame.get("world_x"),
                "world_y": frame.get("world_y"),
            }
            break

    source_complete_frames = sum(
        1
        for frame in frames
        if isinstance(frame.get("client_facing_source"), str)
        and frame.get("client_facing_source") in KNOWN_CLIENT_FACING_SOURCES
        and _raw_client_facing_value(frame) is not None
    )
    return {
        "record_type": "heading_integrity_replay_report",
        "run_id": result.get("run_id"),
        "source_status": result.get("status"),
        "recorded_control_frames": len(frames),
        "evaluated_frames_until_stop": evaluated_frames,
        "current_visual_heading_frames": current_visual_frames,
        "malformed_frames_seen": malformed_frames,
        "missing_raw_client_facing_frames": missing_raw_client_facing_frames,
        "heading_integrity_state_counts": dict(state_counts),
        "recorded_heading_sources": dict(heading_sources),
        "recorded_client_facing_sources": dict(client_sources),
        "raw_client_facing_source_complete_frames": source_complete_frames,
        "raw_client_facing_source_complete": source_complete_frames == len(frames),
        "first_rejection": first_rejection,
        "stopped_fail_closed": first_rejection is not None,
        "maximum_evidence_age_s": float(maximum_evidence_age_s),
        "input_emitted": False,
        "execution_authority": False,
        "server_truth_used": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay retained heading-integrity evidence (offline only)."
    )
    parser.add_argument("result", type=Path, nargs="+")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    reports = []
    for path in arguments.result:
        result = json.loads(path.read_text(encoding="utf-8"))
        report = replay_heading_integrity(result)
        report["result"] = str(path)
        reports.append(report)
    rendered = json.dumps(
        reports[0] if len(reports) == 1 else reports,
        indent=2,
        ensure_ascii=False,
    ) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
