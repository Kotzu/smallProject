from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.live_baseline import verify_movement_live_baseline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify immutable operator-reviewed MovementEngine evidence."
    )
    parser.add_argument(
        "baseline",
        nargs="?",
        type=Path,
        default=ROOT / "config" / "movement-lab" / "crypt-egress-live-baseline-v1.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    record = json.loads(args.baseline.read_text(encoding="utf-8"))
    report = verify_movement_live_baseline(record, repository_root=ROOT).to_record()
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
