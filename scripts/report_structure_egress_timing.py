"""Separate recorded egress handoff timing from destination arrival.

Read-only trace analysis, no game input. A planner flyby is NOT proof that the
whole actor crossed an exit. Missing visual exit evidence stays unknown.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from math import isfinite
from pathlib import Path


def timing_report(record: dict) -> dict:
    actions = record["actions"]
    indexed = [(i, action) for i, action in enumerate(actions)
               if action.get("kind") == "CONTINUOUS_FRAME"]
    if not indexed:
        raise ValueError("no control frames")
    frames = [frame for _, frame in indexed]
    decision_start = float(frames[0]["decision_observation"]["observed_monotonic_s"])
    observed = [float(frame["observed_monotonic_s"]) for frame in frames]
    if not all(isfinite(t) for t in [decision_start, *observed]):
        raise ValueError("nonfinite clock")
    if decision_start > observed[0] or any(a > b for a, b in zip(observed, observed[1:])):
        raise ValueError("unordered clock")
    events = []
    for index, action in enumerate(actions):
        if action.get("kind") != "STRUCTURE_EGRESS_FLYBY":
            continue
        before = next((f for i, f in reversed(indexed) if i < index), None)
        after = next((f for i, f in indexed if i > index), None)
        events.append({
            "opening_id": action.get("opening_id"),
            "event": "planner_handoff_near_opening_not_completed_exit",
            "preceding_frame": None if before is None else before["frame_index"],
            "following_frame": None if after is None else after["frame_index"],
            "elapsed_lower_s": None if before is None else before["observed_monotonic_s"] - decision_start,
            "elapsed_upper_s": None if after is None else after["observed_monotonic_s"] - decision_start,
            "remaining_to_opening_yards": action.get("remaining_to_opening_world"),
            "whole_body_exit_confirmed": False,
        })
    return {
        "record_type": "structure_egress_timing_audit",
        "run_id": record.get("run_id"),
        "source": "recorded_client_trace_not_new_live_test",
        "time_origin": "first_control_decision_observation",
        "first_to_last_post_observation_s": observed[-1] - observed[0],
        "first_decision_to_last_observation_s": observed[-1] - decision_start,
        "destination_status": record.get("status"),
        "destination_name": record.get("semantic_destination_name"),
        "egress_handoffs": events,
        "completed_exit_elapsed_s": None,
        "start_click_to_first_motion_s": None,
        "human_reference_comparable": False,
        "humanlike_certified": False,
        "execution_authority": False,
        "next_evidence": "synchronized video: same start, first movement, entire body beyond exit",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raw = args.trace.read_bytes()
    result = timing_report(json.loads(raw))
    result["trace_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
