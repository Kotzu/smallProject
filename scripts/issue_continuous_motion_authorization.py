from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.execution.continuous_motion_authorization import (
    issue_continuous_motion_authorization_snapshot,
)


AUTH_SCHEMA = ROOT / "contracts" / "execution-target-authorization.schema.json"
FIXED_UI_TEMPLATE = ROOT / "config" / "execution-targets" / "tbc_243_lab.json"
DEFAULT_OUTPUT = ROOT / "data" / "runtime" / "navigation-f3b" / "continuous-motion-authorization.json"


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Issue the bounded local F4a continuous-navigation authorization; no input is sent."
    )
    parser.add_argument("--fixed-ui-template", type=Path, default=FIXED_UI_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence-ref", action="append", default=[])
    parser.add_argument("--acknowledge-continuous-motion", action="store_true")
    parser.add_argument("--renewal-parent-sha256")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.acknowledge_continuous_motion is not True:
        raise SystemExit("--acknowledge-continuous-motion is required")
    evidence_refs = tuple(args.evidence_ref) or ("operator:continuous-navigation-review",)
    raw = issue_continuous_motion_authorization_snapshot(
        args.fixed_ui_template.read_bytes(),
        schema_path=AUTH_SCHEMA,
        now_utc=datetime.now(timezone.utc),
        evidence_refs=evidence_refs,
        acknowledge_continuous_motion=True,
        renewal_parent_sha256=args.renewal_parent_sha256,
    )
    _atomic_write(args.output, raw)
    print(f"CONTINUOUS_MOTION_AUTHORIZATION={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
