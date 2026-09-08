from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.live_trace_quality import (
    evaluate_live_steering_trace,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reject arrived-but-robotic live steering traces.",
    )
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-client-facing-source",
        action="store_true",
        help="fail unless every continuous frame names a usable client-facing source",
    )
    parser.add_argument(
        "--require-body-camera-separation",
        action="store_true",
        help="fail unless every continuous frame records both yaw channels and their delta",
    )
    parser.add_argument(
        "--require-camera-integrity",
        action="store_true",
        help=(
            "fail unless every continuous frame proves either the visible "
            "actor anchor or the exact level-RMB camera-control receipt"
        ),
    )
    arguments = parser.parse_args()
    result = json.loads(arguments.result.read_text(encoding="utf-8"))
    quality = evaluate_live_steering_trace(
        result,
        require_client_facing_source=arguments.require_client_facing_source,
        require_body_camera_separation=arguments.require_body_camera_separation,
        require_camera_integrity=arguments.require_camera_integrity,
    ).to_record()
    rendered = json.dumps(quality, indent=2, ensure_ascii=False) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if quality["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
