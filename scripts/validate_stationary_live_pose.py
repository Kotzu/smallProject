from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.stationary_pose import (
    evaluate_stationary_pose,
    load_expected_stationary_location,
    read_live_pose_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate fresh stationary Predator localization without input."
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=ROOT / "data" / "runtime" / "operator" / "nav-viewer-live-state.txt",
    )
    parser.add_argument("--duration", type=float, default=4.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--semantic-catalog",
        type=Path,
        default=ROOT / "config" / "movement-lab" / "semantic-destinations-tbc243.json",
    )
    parser.add_argument(
        "--expected-location-id",
        default="landmark:deathknell-crypt",
    )
    args = parser.parse_args()
    if not 2.0 <= args.duration <= 30.0:
        raise SystemExit("duration must be between 2 and 30 seconds")
    deadline = time.monotonic() + args.duration
    samples = []
    last_sequence = 0
    while time.monotonic() < deadline:
        now = time.monotonic()
        sample = read_live_pose_file(
            args.state_file, now_monotonic_s=now, maximum_age_s=0.60,
        )
        if sample is not None and sample.sequence > last_sequence:
            samples.append(sample)
            last_sequence = sample.sequence
        time.sleep(0.05)
    expected_location = load_expected_stationary_location(
        args.semantic_catalog,
        location_id=args.expected_location_id,
    )
    report = evaluate_stationary_pose(
        samples,
        expected_location=expected_location,
    ).to_record()
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
