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

from perfect_assassin.execution.movement_runtime_arm import (
    issue_session_authorization_snapshot,
)


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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Issue a fresh temporal-only fixed-UI LAB authorization."
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=ROOT / "config" / "execution-targets" / "tbc_243_lab.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "runtime" / "operator" / "tbc_243_lab.active.json",
    )
    parser.add_argument("--acknowledge-fixed-ui-session", action="store_true")
    parser.add_argument(
        "--renewal-parent-sha256",
        help="Exact authorization SHA-256 from the current session receipt.",
    )
    args = parser.parse_args(argv)
    if args.acknowledge_fixed_ui_session is not True:
        raise SystemExit("--acknowledge-fixed-ui-session is required")
    raw = issue_session_authorization_snapshot(
        args.template.read_bytes(),
        schema_path=ROOT / "contracts" / "execution-target-authorization.schema.json",
        now_utc=datetime.now(timezone.utc),
        renewal_parent_sha256=args.renewal_parent_sha256,
    )
    _atomic_write(args.output, raw)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
