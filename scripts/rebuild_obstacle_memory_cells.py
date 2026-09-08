from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from perfect_assassin.movement.obstacle_memory import (
    LOCAL_CLEARANCE_EVIDENCE,
    LearnedObstacleMemory,
)


def rebuild(*, memory_path: Path, results_root: Path, client_build: int) -> dict[str, object]:
    original_record = json.loads(memory_path.read_text(encoding="utf-8"))
    memory = LearnedObstacleMemory.from_record(
        original_record, expected_client_build=client_build,
    )
    recovered = 0
    source_files = 0
    for result_path in sorted(results_root.glob("navmesh-roaming-*.json")):
        try:
            record = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        blockers = [
            action.get("blocker")
            for action in record.get("actions", ())
            if action.get("kind") == "LEARNED_LOCAL_OBSTACLE_PERSISTED"
        ]
        blockers = [item for item in blockers if isinstance(item, list) and len(item) == 4]
        if not blockers:
            continue
        source_files += 1
        observed_at = datetime.fromtimestamp(
            result_path.stat().st_mtime, tz=timezone.utc,
        )
        for blocker in blockers:
            memory = memory.observe(
                map_name=str(record["map"]),
                zone_index=int(record["zone_index"]),
                blocker=tuple(float(value) for value in blocker),
                run_id=str(record["run_id"]),
                observed_at=observed_at,
                evidence=LOCAL_CLEARANCE_EVIDENCE,
            )
            recovered += 1
    output = memory.to_record()
    temporary = memory_path.with_suffix(memory_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(memory_path)
    return {
        "record_type": "learned_obstacle_cell_rebuild_result",
        "source_files": source_files,
        "recovered_contact_events": recovered,
        "obstacle_count_before": len(original_record.get("obstacles", ())),
        "obstacle_count_after": len(memory.obstacles),
        "legacy_records_preserved": sum(
            item.get("representation") is None
            for item in original_record.get("obstacles", ())
        ),
        "execution_authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--client-build", type=int, default=8606)
    args = parser.parse_args()
    print(json.dumps(rebuild(
        memory_path=args.memory,
        results_root=args.results_root,
        client_build=args.client_build,
    ), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
