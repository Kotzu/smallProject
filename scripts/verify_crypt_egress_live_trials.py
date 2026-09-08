from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.live_baseline import verify_movement_live_baseline
from perfect_assassin.movement.live_trial_gate import verify_movement_live_trials


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the filmed Crypt exit trial set.")
    parser.add_argument(
        "--baseline", type=Path,
        default=ROOT / "config" / "movement-lab" / "crypt-egress-live-baseline-v1.json",
    )
    parser.add_argument(
        "--trials", type=Path,
        default=ROOT / "config" / "movement-lab" / "crypt-egress-live-trials.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    baseline_report = verify_movement_live_baseline(
        baseline, repository_root=ROOT,
    )
    trials = json.loads(args.trials.read_text(encoding="utf-8"))
    trial_report = verify_movement_live_trials(
        trials,
        repository_root=ROOT,
        expected_baseline_id=baseline_report.baseline_id,
    )
    record = trial_report.to_record()
    record["baseline_intact"] = baseline_report.passed
    record["promotion_eligible"] = bool(
        baseline_report.passed and record["promotion_eligible"]
    )
    if not baseline_report.passed:
        record["failures"] = ["baseline_not_intact", *record["failures"]]
    rendered = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if record["promotion_eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
