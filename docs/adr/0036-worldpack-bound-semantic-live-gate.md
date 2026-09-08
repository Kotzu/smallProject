# ADR 0036: WorldPack-bound semantic live gate

## Status

Accepted.

## Context

The semantic road regression originally wrote a live gate bound to an absolute
loose navmesh directory and a worker path. Movement Engine later migrated to a
verified standalone WorldPack, but that older gate could still approve Start
without proving that the validated geometry, catalog, semantics, client build,
and runtime pack were the assets actually opened by the planner.

This is especially unsafe across client families. The legacy LAB uses
`2.4.3.8606`, while TBC Anniversary is based on the modern `2.5.5+` client line
and requires CASC/DB2-WDC adapters and its own exact content bake.

## Decision

The semantic movement gate is upgraded to schema `2.0`. A live-enabled record
pins all of:

- WorldPack runtime profile path and SHA-256;
- profile ID, pack ID, aggregate WorldPack SHA-256, and target profile;
- exact client version/build and nav profile ID;
- Detour worker path and SHA-256;
- semantic validation result path and SHA-256.

Before enabling Start, the external UI independently re-opens and verifies the
sealed WorldPack, derives the expected identity, hashes the profile and worker,
and verifies that the validation evidence is still byte-identical. A mismatch,
missing artifact, failed validation, old schema, or disabled authority fails
closed.

The validation command uses the WorldPack profile/store by default. Loose nav
assets are available only behind `--legacy-loose-nav-assets` for offline
rollback comparison; that mode cannot emit a live gate.

## Controlled evidence

The Tirisfal pack `wow.tbc.2.4.3.8606.tirisfal-worldpack-v2`, aggregate SHA-256
`fd2eb93eccc75f5c297d5a17bab52bd9d2f96a9d0f5cfb87fdb6d655c3f35d30`,
passed all five semantic cases from the pack root: crypt spawn → Brill,
Deathknell → Brill, Brill → Deathknell, Brill → south-road holdout, and the
expected fail-closed hill fixture. The generated v2 gate passed its JSON
contract and the external UI's independent runtime check.

## Consequences

- A copied gate cannot authorize modified validation evidence or a rebuilt
  worker.
- A `2.4.3.8606` result cannot authorize Anniversary or another realm-specific
  content build.
- Deploying another target requires an independently imported WorldPack and a
  fresh semantic regression; Movement Engine itself remains shared.
- The gate grants no server/emulator knowledge and changes no client-integrity
  boundary.
