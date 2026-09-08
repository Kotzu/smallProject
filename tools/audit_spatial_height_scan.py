"""Read-only native comparison on client assets; no client/server interaction."""

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "integrations/windows-input")]
from persistent_navmesh_awareness import PersistentNavmeshAwarenessService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-worker", type=Path, required=True)
    parser.add_argument("--candidate-worker", type=Path, required=True)
    parser.add_argument("--pack-root", type=Path, required=True)
    args = parser.parse_args()
    services = []
    try:
        for worker, scan in (
            (args.reference_worker, False),
            (args.candidate_worker, True),
        ):
            services.append(
                PersistentNavmeshAwarenessService(
                    worker=worker,
                    nav_root=args.pack_root,
                    map_name="Azeroth",
                    protocol_timeout_s=5,
                    spatial_scan=scan,
                )
            )
        results = []
        # Archived reference poses, not a hardcoded navigation route.
        for xyz in (
            (1809.5842615, 1592.7942659, 100),
            (1676.369629, 1677.466919, 121.797379),
            (1676.369629, 1677.466919, 138.729095),
        ):
            before = services[0].sample(*xyz)
            started = time.monotonic()
            after = services[1].sample(*xyz)
            elapsed = time.monotonic() - started
            if (
                replace(
                    after,
                    height_scan=None,
                    observed_monotonic_s=before.observed_monotonic_s,
                )
                != before
            ):
                raise RuntimeError("legacy awareness changed")
            bands = {}
            for height in (0.25, 0.6, 1.2, 1.8):
                rays = [
                    r
                    for r in after.height_scan.rays
                    if abs(r.height_offset_yards - height) < 1e-6
                ]
                blocked = [r for r in rays if r.blocked_by_yards is not None]
                bands[str(height)] = {
                    "blocked": len(blocked),
                    "nearest_clear_prefix": min(
                        (r.clear_prefix_yards for r in blocked), default=None
                    ),
                }
            for old, new in zip(
                before.awareness.radial_probes, after.height_scan.rays[32:48]
            ):
                if abs(old.clearance_yards - new.clear_prefix_yards) > 1e-6:
                    raise RuntimeError(
                        "1.20 yd scan disagrees with existing radial probe"
                    )
            results.append(
                {
                    "pose": xyz,
                    "query_seconds": elapsed,
                    "legacy_equal": True,
                    "bands": bands,
                    "scan_bytes": len(json.dumps(after.height_scan.to_record())),
                }
            )
        print(json.dumps(results))
    finally:
        for service in services:
            service.close()


if __name__ == "__main__":
    main()
