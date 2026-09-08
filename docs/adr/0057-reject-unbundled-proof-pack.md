# ADR-0057: Rebuild proof packs with a bundled runtime catalog

## Status

Accepted — 2026-08-31

## Context

The offline bake queue marks `RazorfenKraulInstance` (`map_id=47`) and
`Karazahn` (`map_id=532`) complete. The original v2 proof pack had no
`identity/client-world-catalog.json`, which is required by the runtime loader.

## Decision

Reject v2 and build a separate v3 candidate with a schema-valid bundled
catalog, matching hashes, and no mutation of v2. Bind v3 in Control Center only
as `OBSERVE_ONLY` because its catalog is partial and it has no semantic/access
promotion evidence. Autonomous readiness remains fail-closed.

## Consequences

- A stale or legacy pack cannot appear runtime-ready merely because nav tiles
  exist.
- Control Center can inspect the new v3 profile while the 83-map inventory
  remains authoritative for identity.
- Releasing these maps autonomously still requires semantic/access validation;
  no live input or client mutation is part of this decision.

## Evidence

- `data/runtime/client-catalog/tbc243-8606/bake-queue.json`
- `E:/WoWserver/PerfectAssassin-Runtime/worldpacks/tbc243-8606-proof-worldpack-v2/manifest.json`
- `E:/WoWserver/PerfectAssassin-Runtime/worldpacks/tbc243-8606-proof-worldpack-v3/manifest.json`
- `config/navigation/world-pack-runtime-tbc243-proof-v3.json`
- `src/perfect_assassin/movement/world_pack_runtime.py`
- `docs/movement-engine-problem-log.md` (ME-118)
