"""Replay recorded spatial evidence without starting WoW, CC or a nav worker."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from perfect_assassin.adapter.spatial_trace import replay_spatial_evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    with args.trace.open("rb") as stream:
        raw = stream.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024:
        parser.error("trace exceeds the 64 MiB replay limit")
    report = replay_spatial_evidence(
        json.loads(raw), trace_sha256=hashlib.sha256(raw).hexdigest()
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "frames"}, ensure_ascii=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
