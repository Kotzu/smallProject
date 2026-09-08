# ADR 0034: Standalone client-world brain and conditional portals

## Status

Accepted.

## Decision

Predator's navigation brain is an external, standalone stack. Runtime planning
must not depend on CMaNGOS, playerbots, a realm database, server coordinates,
server visibility, or server movement APIs.

The versioned client adapter supplies immutable world assets. The external
stack owns extraction, road semantics, Recast/Detour navigation, the 3D world
viewer, multi-floor endpoint selection, local static awareness, steering, and
experience memory. A client build or expansion is supported through a pinned
adapter and catalog; the movement brain remains unchanged.

Client assets are an offline import source, not a runtime dependency. A
completed import is sealed as a versioned WorldPack containing the map,
navigation, road-semantic, and static-collision artifacts plus their hashes.
Movement Engine opens that self-contained WorldPack and must not discover or
read a live WoW installation, emulator tree, realm database, or server process.

Emulator data may be used only as a LAB evaluator. It cannot enter a Champion
runtime decision, generated route, target choice, or required deployment
dependency.

## Conditional topology

A partial Detour path inside a WMO is not permission to cross a disconnected
boundary. A stalled WMO frontier is represented as one of:

- `POSSIBLE_WMO_DOOR_OR_GATE`;
- `POSSIBLE_WMO_DOOR_GATE_OR_FLOOR_TRANSITION`.

Both records have `execution_authority: false` and require fresh,
client-visible confirmation before interaction and a new navmesh query after
the topology changes. A violet viewer boundary is diagnostic only. A green
egress remains reserved for a route-verified covered-to-open transition.

## Full-content bake pipeline

The client asset inventory for TBC 2.4.3 build 8606 contains 35 maps with WDT
and ADT terrain, totaling 3,610 ADTs. `build_client_world_bake_queue.py`
maintains a deterministic map-by-map queue so extraction, semantic sidecars,
and navmesh generation are resumable and independently auditable.

`run_client_world_map_bake.py` advances one exact map from its structural queue
state. It records every offline command, fails closed on inconsistent or
non-progressing artifacts, and labels the result with
`world_source: PINNED_CLIENT_ASSETS_ONLY`, `server_dependency: false`, and
`emulator_dependency: false`. Global BVH artifacts may grow while maps are
baked, so the immutable WorldPack manifest is sealed only after the selected
coverage set is complete.

The WorldPack keeps Namigator's runtime layout (`*.map`, `Nav/`, `BVH/`, and
`semantics/`) so the Detour worker can open the pack root directly. It also
bundles the pinned world-map catalog under `identity/`; every artifact and the
ordered set have SHA-256 identities. Absolute source paths and runtime process
dependencies are absent from the manifest.

The first generic instance proof is `RazorfenKraulInstance`: 6 extracted ADTs,
6 road sidecars, 6 nav files, and a 1,536-subtile MapBuilder completion. This
proof used only the pinned client MPQs and external tools.

The second proof is the multi-surface interior map `Karazahn`: all 9 inventoried
ADTs, 9 semantic sidecars, and 9 nav tiles advanced from
`READY_FOR_EXTRACTION` to `COMPLETE`. Its validated bake receipt records both
server and emulator dependencies as false. Together the two proofs exercise the
same generic runner without a map-specific route or emulator-side geometry.

The third proof is `Shadowfang`: the same generic runner completed all 25
inventoried ADTs, all 25 road-semantic sidecars, and all 25 nav files. A scoped
catalog selected only the declared map from the shared staging root, while the
sealed runtime pack was independently re-opened under the normal strict
artifact rules. `wow.tbc.2.4.3.8606.shadowfang-worldpack-v1` contains 916
artifacts with aggregate SHA-256
`eaa1ac8cc14a1188041227af57ab5927b976a45500046721836a12bcb1a71a19`.

The packed map's own WMO instance table identifies
`world\wmo\dungeon\ld_shadowfang\ld_shadowfanginterior.wmo` and its world-space
bounds. This provides a data-derived interior search region rather than a
hardcoded route or emulator coordinate. A direct v27 Detour query at the
resolved WMO floor `(−202.410004, 2179.989990, 79.908943)` completed a four-yard
route on the same level, reported two vertical height candidates, a local
component of 1,279 polygons, physical surface `wmo`, complete egress inference,
and zero unresolved doodad segments.

The first runtime-compatible proof pack,
`wow.tbc.2.4.3.8606.proof-worldpack-v2`, contains the declared Razorfen Kraul
and Karazahn coverage plus the static BVH set. It sealed 825 artifacts with
aggregate SHA-256
`d2dac1272c7e19272810a4619cc27773ec7c99f2662c8dbb1385eb27258c0588`.
An independent verification passed, followed by a direct Detour query against
only that pack root on `RazorfenKraulInstance`; it returned a complete
three-point corridor from the resolved surface at `(2400, 2400, 103.987503)`.

The active Tirisfal profile is sealed separately as
`wow.tbc.2.4.3.8606.tirisfal-worldpack-v2`. It contains the verified partial
Azeroth catalog, 8 nav tiles, 8 road semantics, and the stable BVH set: 332
manifested artifacts, aggregate SHA-256
`fd2eb93eccc75f5c297d5a17bab52bd9d2f96a9d0f5cfb87fdb6d655c3f35d30`.
Its bundled catalog and map table open successfully without workspace or client
paths. The complete semantic gate passed from the pack alone for crypt spawn to
Brill, Deathknell to Brill, Brill to Deathknell, the south-road holdout, and the
expected fail-closed hill fixture. A direct v27 query at Deathknell also returned
a complete two-point corridor with zero unresolved doodad segments.

The first complete three-continent runtime pack is
`wow.tbc.2.4.3.8606.world-continents-v1`. A clean deterministic build produced
all declared Azeroth (687), Kalimdor (1,018), and Expansion01 (800) ADTs. The
deep Detour audit validated all 641,280 inner spatial records with zero failed
ADT artifacts. No historical replacement tile or emulator-derived repair was
carried into the pack. It contains 9,514 manifested artifacts, aggregate
SHA-256 `d8a1b65e71602e6513b0d8e711001a23cdfc98ceb2109834ba8a86fa5ef689ac`,
and reopens through `world-pack-runtime-tbc243-world-continents-v1.json`
without a client installation, client process, server, or emulator.

The external tool resolves this pack through the portable profile
`world-pack-runtime-tbc243-tirisfal-v2.json`. The profile stores only the pack
directory name and exact identity/content pins; the operator supplies the local
WorldPack store root. The runtime loader constrains the resolved directory to
that store, revalidates the pack and bundled catalog, and exposes the pack root
as the navigation root. No workstation drive path is embedded in the profile.

The semantic movement live gate is version 2 and is bound to the same verified
runtime boundary. It pins the WorldPack profile file hash, profile ID, pack ID,
aggregate pack SHA-256, target profile, exact client version/build, nav profile,
Detour worker path/hash, and validation-result path/hash. The external UI
re-opens the WorldPack and recomputes the mutable artifact hashes before Start.
The previous gate that trusted only a loose nav root is intentionally rejected;
loose assets remain an explicit offline rollback mode and cannot write a live
gate.

## Standalone 3D viewer

The external 3D viewer has two explicitly separated asset modes. Its legacy
mode opens a WoW `Data` directory to reconstruct decorated ADT/WMO/doodad
geometry. Its WorldPack mode receives `--world-pack`, never initializes the MPQ
reader, discovers maps from the sealed `*.map` artifacts, streams the required
Detour ADTs around the live pose, and renders the loaded mesh through Recast
DebugUtils. The Movement Engine button uses the second mode through the
verified runtime profile.

The WorldPack viewer launch is fail-closed: the profile, pack manifest,
aggregate content hash, bundled client catalog, selected map, executable, and
finite world position must validate before the process is created. Its launch
receipt declares `client_installation_required: false` and
`execution_authority: false`.

The first controlled proof opened the Tirisfal WorldPack at Deathknell in the
separate v3 candidate binary without passing or opening a client `Data`
directory. The rendered result preserved 3D walkable relief, excluded geometry
around static obstructions, the live-position compass marker, and the existing
read-only live-state bridge. The previous Stable viewer binary remained
available as the rollback artifact during validation.

## Cross-expansion evidence boundary

The MPQ/WDBC adapter is implemented and tested. CASC/DB2-WDC remains a research
candidate, not supported functionality. The adapter direction is based on the
primary CascLib repository, TrinityCore's current CASC `map_extractor`, and
Recast Navigation's tiled-mesh interface:

- https://github.com/ladislav-zezula/CascLib
- https://github.com/TrinityCore/TrinityCore/blob/master/src/tools/map_extractor/System.cpp
- https://github.com/recastnavigation/recastnavigation

`2.5.5` is not treated as a permanent Anniversary identity. Blizzard's July
2026 notice states that Burning Crusade Classic Anniversary advanced from
`2.5.5` to `2.5.6` and that Classic clients share modern WoW code. Therefore a
future Anniversary importer is pinned to the full observed build and its
verified CASC/DB2 schemas; a realm label or expansion name is insufficient.

- https://us.forums.blizzard.com/en/wow/t/user-interface-updates-in-classic/2325408/

## Consequences

- A private server is useful for controlled evaluation but optional at runtime.
- Custom realms require a compatible client-build/content adapter, not a fork
  of Movement Engine.
- Missing client assets or unsupported formats fail closed per map.
- Server-side playerbot shortcuts and direct world-state access are never
  copied into the standalone runtime.
- A gate validated for `2.4.3.8606` cannot authorize an Anniversary `2.5.5+`
  client or a different private-realm content build.
