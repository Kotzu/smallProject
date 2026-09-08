from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from time import monotonic_ns
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.execution.continuous_motion_authorization import (
    load_continuous_motion_authorization_profile,
)
from perfect_assassin.execution.continuous_motion_runtime_arm import (
    issue_continuous_motion_runtime_arm_snapshot,
)


AUTH_SCHEMA = ROOT / "contracts" / "execution-target-authorization.schema.json"
ARM_SCHEMA = ROOT / "contracts" / "continuous-motion-runtime-arm.schema.json"
RECEIPT_SCHEMA = ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
REALM_SCHEMA = ROOT / "contracts" / "local-realm-revalidation.schema.json"
DEFAULT_OUTPUT = ROOT / "data" / "runtime" / "navigation-f3b" / "continuous-motion-arm.json"
DEFAULT_SESSION_AUTH = ROOT / "data" / "runtime" / "operator" / "tbc_243_lab.active.json"
DEFAULT_RECEIPT = ROOT / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
DEFAULT_REALM = ROOT / "data" / "runtime" / "operator" / "movement-realm-revalidation.json"


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
        description="Issue one bounded F4a arm from exact client evidence; no input is sent."
    )
    parser.add_argument("--continuous-authorization-file", type=Path, required=True)
    parser.add_argument("--session-authorization-file", type=Path, default=DEFAULT_SESSION_AUTH)
    parser.add_argument("--session-receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--realm-revalidation-file", type=Path, default=DEFAULT_REALM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--clock-id", default="clock:windows:monotonic")
    parser.add_argument("--acknowledge-continuous-motion", action="store_true")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.acknowledge_continuous_motion is not True:
        raise SystemExit("--acknowledge-continuous-motion is required")
    authorization_raw = args.continuous_authorization_file.read_bytes()
    profile = load_continuous_motion_authorization_profile(
        authorization_raw,
        schema_path=AUTH_SCHEMA,
        now_utc=datetime.now(timezone.utc),
    )
    raw = issue_continuous_motion_runtime_arm_snapshot(
        authorization=profile,
        authorization_raw=authorization_raw,
        session_authorization_raw=args.session_authorization_file.read_bytes(),
        session_receipt_raw=args.session_receipt.read_bytes(),
        realm_revalidation_raw=args.realm_revalidation_file.read_bytes(),
        arm_schema_path=ARM_SCHEMA,
        authorization_schema_path=AUTH_SCHEMA,
        session_receipt_schema_path=RECEIPT_SCHEMA,
        realm_revalidation_schema_path=REALM_SCHEMA,
        now_utc=datetime.now(timezone.utc),
        now_monotonic_ms=monotonic_ns() / 1_000_000.0,
        clock_id=args.clock_id,
    )
    _atomic_write(args.output, raw)
    print(f"CONTINUOUS_MOTION_RUNTIME_ARM={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
