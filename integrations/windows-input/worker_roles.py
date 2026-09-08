"""Keep graph-production provenance distinct from the current path planner."""
from __future__ import annotations

import hashlib
from pathlib import Path


def structure_probe_worker_sha256(
    navigation_worker: Path, structure_probe_worker: Path | None = None,
) -> str:
    # No claimed hash supplied by a graph or caller is accepted in place of
    # the actual producer artifact. Legacy callers retain same-worker binding.
    producer = structure_probe_worker if structure_probe_worker is not None else navigation_worker
    return hashlib.sha256(producer.resolve(strict=True).read_bytes()).hexdigest()
