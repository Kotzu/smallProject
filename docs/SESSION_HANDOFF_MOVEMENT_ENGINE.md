# Movement Engine session handoff

> Punct de intrare actual (2026-09-05): [CURRENT_MOVEMENT_STATUS.md](CURRENT_MOVEMENT_STATUS.md).
> Secțiunile de mai jos păstrează istoricul; nu certifică automat codul curent.

## Scope

Stabilize the standalone Movement Engine for WoW TBC 2.4.3. The engine must
route autonomously from client WorldPack/navmesh/topology evidence, without
hardcoded crypt/Deathknell routes or executable operator waypoints. Do not
start, stop, or modify the parallel single-player game or Hermes processes.

## Current implementation

- `PredictiveSteeringController` uses closed-loop 50 ms steering, rolling
  lookahead, topology-aware curve preview, bounded MPPI for difficult hairpins,
  RMB momentum braking and a 16-tick settle window after a small camera
  correction. A real error above 0.40 rad or a hard recenter remains immediate.
- `adaptive_trajectory_v1` now receives the requested MPPI `batch_size` and
  `time_steps` from the runtime CLI. Telemetry records the effective values;
  Control Center launches the current adaptive `256 x 56` profile.
- Moderate deviation in a complete covered/WMO corridor now uses running
  W+RMB recentering; severe deviation or large heading error still pivots.
- Partial corridors remain fail-closed and cannot use the running-recenter
  band.
- Semantic goals are coalesced at 25 yd. A Detour refinement midpoint is
  planned speculatively from the semantic A* route and becomes authoritative
  only after the completed coarse corridor proves the generic deviation gate.
  A complete fly-by corridor is cached for the exact shared-point handoff.
- Camera profile chat commands are deferred until terminal movement status, so
  W is not released mid-run merely to change camera presentation.
- Read-only dynamic nameplate awareness is sampled every four control frames
  (about 5 Hz), below its 0.8 s track TTL, so full-frame component extraction
  cannot contend with the pose/control clock on every frame.
- A complete structure-egress corridor may be used with locally incomplete
  topology only when the immutable WorldPack structure index, its bound access
  graph and both Detour legs independently validate it. Lookahead is bounded
  to eight future semantic goals and contains no executable operator route.
- The next eight semantic goals also consult immutable WorldPack `DOODAD`
  geometry as bounded clearance candidates. Detour must validate the bypass;
  structure geometry never becomes an executable waypoint.
- A completed local corridor can hand off directly to the next semantic goal
  while retaining the movement lease. This removes a stop pulse at smooth
  landmarks while preserving immediate release for terminal and recovery
  states.
- Routine travel aggro is continued only by the journey supervisor when
  `--continue-through-routine-aggro` is present and health is at least the
  configured 0.55 fraction. The direct runner remains fail-closed by default.
- Control Center-ul propagă acum explicit acest flag pentru launch-ul semantic;
  pragul de sănătate și handoff-ul rămân în runner/supervisor, nu în UI.
- Operator paths and manual demonstrations are priors/evidence only; they are
  not autonomous executable routes.
- The supervisor accepts an identifier-only destination sequence (2–16 IDs,
  1–32 repetitions), and the Control Center can author that bounded sequence.
- Before the first child starts, the supervisor checks every sequence ID against
  the selected semantic catalog; unknown IDs fail closed without input.
- `config/navigation/world-map-registry-tbc243.json` inventories the validated
  TBC 2.4.3 profiles for Azeroth, Kalimdor, Shadowfang and Expansion01. The
  client-derived transform catalog covers 68 audited map-area rows. A
  destination is still accepted only when its semantic catalog and active
  WorldPack bind to the same map; unknown coordinates remain fail-closed. The
  registry now declares optional semantic/structure/access artefacts, and the
  Control Center profile picker refuses autonomous start when those artefacts
  are absent.
- The content-minimal RouteTeacher transform audit maps `11,686/11,687`
  Anniversary coordinate candidates through the client-derived catalog: all
  `3,434` Azeroth, `3,918` Kalimdor and `4,334` Expansion01 candidates transform
  successfully. The single unresolved candidate is map `564` (Black Temple),
  which has no audited WorldMapArea row. The audit stores only hashes/counts and
  remains read-only; it does not create waypoints or execution authority.

## Evidence

- Full current regression: 1,323/1,323 tests pass (including the client-derived map-area transform catalog, RouteTeacher transform coverage and its read-only Control Center indicator, asynchronous WMO baseline evidence, scoped WMO suppression, worker non-blocking coverage, the MPPI switchback regression, the bounded RouteTeacher parser, the static NPCData importer, the content-minimal NPCData audit and map-area discovery).
- Adaptive benchmark v13: 6,000/6,000 quality-pass, zero collisions, using the
  historical effective runtime configuration `128 x 24`.
- Standalone WorldPack: `VERIFIED` (`tbc243-azeroth-full-v3`).
- Standalone portability after recenter: `PASS`, execution authority false.
- Local crypt environment: `VERIFIED_LOCAL_ENVIRONMENT`; resolved
  `z=121.797379`, one WMO, complete corridor, 15 verified egresses.
- The supervisor already injected `--continue-through-routine-aggro` for the
  v30 runner; the stop was a health-floor/aggro handoff, and that older result
  did not retain `health_fraction`. Control Center now propagates the flag
  explicitly as a launch-consistency fix, not as proof that the loop is safe.
- `holdout-adaptive-brill-deathknell-20260831-v14.json` reached Deathknell. It
  removed the 1.2-1.6 s synchronous semantic-planning gaps, but exposed an
  eight-tick servo resonance in its final segment.
- Final reverse holdout
  `holdout-adaptive-deathknell-brill-20260831-v15.json` reached Brill in two
  bounded navigation cycles with zero combat handoffs. Its arrived cycle
  `f6fa485d-bfa0-4ea6-92a8-a196359ea2f3` has zero rapid reversals, zero pivot
  frames, zero observation gaps, maximum gap 0.078963 s and passes the official
  quality gate.
- The preceding 5,000-frame budget cycle
  `a9b93434-98a2-44af-899e-7b76a706c637` remained on the road and had 15 rapid
  reversals (4.5656/min), but its isolated quality record is correctly false:
  it was not yet at the destination and contains one 0.3008658 s observation
  interval, 0.0008658 s over the strict threshold. It is not reported as a
  clean per-cycle pass.
- Final crypt holdout `holdout-adaptive-crypt-brill-20260831-v16.json` started
  from the live WMO interior (`z=121.797`, `WMO_STRUCTURE_WITH_EGRESS`) and
  reached Brill in two bounded cycles with zero combat handoffs. The first
  5,000-frame cycle was correctly marked budget-exhausted (not arrived); local
  static awareness resolved the crypt egress with route-verified portals. The
  arrival cycle `b50bd331-52b0-4d5c-bf9e-002dcb07b76d` passed the official
  quality gate: 3,201 frames, zero observation gaps, maximum gap 0.167324 s,
  zero pivots and five rapid reversals (2.7304/min).
- Full health in the final screenshot is not a survivability proof: the LAB
  combat path contains an explicit `labgod ... on` helper, and v16 did not emit
  a damage-protection state receipt. Treat this run as movement/arrival evidence
  only until a separate bounded aggro run records protection explicitly `OFF`.
- ShadowPlay clip `Wow.exe 2026.08.31 - 00.16.00.74.mp4` visually confirms the
  Deathknell wagon area, main road, bridge and Brill arrival without forest
  orbit. The final screenshot shows Predator alive at full health in Brill.
- Static WorldPack doodads on the next semantic horizon are now queried as
  bounded clearance candidates. The Deathknell intersection can therefore ask
  Detour to prove a bypass around the indexed signpost without a hardcoded
  waypoint.
- Semantic waypoint handoff keeps the existing movement lease when a bounded
  next leg exists, emitting `SEMANTIC_HANDOFF_MOTION_HELD`; terminal, recovery
  and structure-egress paths still release immediately.
- The supervisor and Control Center now support an identifier-only semantic
  destination sequence (2–16 destinations, 1–32 bounded repetitions). Each
  leg is replanned from fresh observed position; the sequence contains no
  executable path.
- Holdout `holdout-crypt-brill-crypt-20260831-v20.json` reached Brill and the
  crypt again with zero combat handoffs. The strict evaluator still reported
  one short capture gap on each leg (`0.3412151 s` and `0.3165173 s`).
- Holdout `holdout-crypt-brill-crypt-20260831-v21.json` used isolated process
  preplanning and failed closed after four observed-collision recoveries at
  the return endpoint. The first blocker is verified in the WorldPack bounds
  of the Deathknell broken cart (`0:doodad:336181`); Predator remained alive,
  combat handoffs stayed at zero, and no execution authority was granted.
- Static WorldPack doodads are now queried on every immediate semantic
  preplan horizon, not only at initial route construction. The resulting
  obstacle discs remain bounded evidence for Detour and never become
  executable waypoints.
- WMO structure egress now keeps the graph opening as the approach target and
  may add a tiny navmesh-revalidated `exit_anchor` only when client surface
  evidence proves `ground` outside the shell. Offline verification from the
  live Crypt spawn reaches the opening and resolves a complete ground
  continuation.
- Static frontier recovery now skips WorldPack-occupied semantic samples and
  extends only eight ordered atlas samples beyond the next coalesced goal;
  broad prop discs use their local narrow footprint so an adjacent road cell
  is not sealed by a circumscribed radius.
- The static horizon now includes WMO enclosures that intersect the next
  segment. A WMO containing the current start is excluded so the verified
  Crypt egress plan remains authoritative; other enclosures become bounded
  Detour evidence before the actor enters them.

## Remaining caveat

The former 1.2-1.6 s semantic planning stops are gone. The v20 arrived cycles
still contain short capture intervals above the conservative 300 ms threshold.
The v21 return cycle demonstrated a late cart collision; v26 passed Crypt but
stopped at an occupied Brill frontier, and v28 reached Brill after the generic
outpost correction but exhausted the first cycle budget before returning.
The four-cycle v29 acceptance then exposed a separate WMO building at
Deathknell and stopped `RESET_REQUIRED` after 1236 frames. The one post-patch
v30 live verification passed that WMO area but stopped at routine aggro and
ended with Predator dead because protection was `OFF`; it did not complete the
return leg. The later bounded v36 sequence completed both semantic legs, but
its trace still failed the temporal quality gate because synchronous WMO
baseline checks created 1–3.26 s observation gaps. Do not hide either fact by
loosening the gate or treating scenery as a hardcoded waypoint. Any further
live input requires a fresh bounded LAB authorization and runtime arm.
Routine-aggro continuation remains an explicit supervisor policy, not a widened
direct-runner or combat authority.

## Journal

See `docs/movement-engine-problem-log.md` entries ME-054 through ME-104.

## Latest bounded live holdout

The latest bounded evidence is split across multiple bounded runs:

- `holdout-crypt-brill-crypt-20260831-v20.json` completed the identifier-only
  sequence with `ARRIVED` on both legs and zero combat handoffs. The strict
  evaluator still reported one short capture gap on each leg (`0.3412151 s`
  and `0.3165173 s`).
- `holdout-crypt-brill-crypt-20260831-v21.json` used process-isolated semantic
  preplanning but stopped `STUCK_REPLAN_REQUIRED` on the return leg after four
  bounded collision recoveries. The first blocker is the WorldPack broken cart
  at `0:doodad:336181`; Predator remained alive and execution authority stayed
  false.
- `holdout-crypt-brill-crypt-20260831-v26.json` used the corrected WMO boundary
  anchor and reached 26/68 Brill objectives before stopping
  `PARTIAL_CORRIDOR_FRONTIER_STUCK` at `2156.319,1301.749`; execution authority
  was false, protection was explicitly `OFF`, and combat handoff remained zero.
  The next semantic target intersects the WorldPack bounds of
  `0:doodad:140804` (`tirisfalloutpost06.mdx`), so the remaining blocker is a
  generic occupied semantic frontier, not the Crypt egress.
- `holdout-crypt-brill-crypt-20260831-v28.json` passed the outpost region and
  reached Brill (`ARRIVED`, 29/29) on its second bounded cycle; the first
  cycle exhausted 5000 control frames before the return leg. Protection was
  explicitly `OFF`, combat handoff remained zero, and execution authority was
  false.
- `holdout-crypt-brill-crypt-20260831-v29.json` allowed four cycles and stopped
  `RESET_REQUIRED` at `1853.621,1560.456` after 1236 frames and 10/69 goals.
  WorldPack identifies the collision as WMO `0:wmo:143396`, the generic
  `duskwood_humantwostory.wmo` building; no combat handoff occurred. The
  offline horizon patch now includes this class of enclosure, but it has not
  been revalidated live.
- `holdout-crypt-brill-crypt-20260831-v30.json` is the single bounded live
  verification after that patch. It passed the v29 WMO area and reached
  `2217.778,691.113`, then stopped at routine aggro with
  `COMBAT_HANDOFF_REQUIRED`; protection was `OFF`, combat handoff budget was
  zero, and the final checkpoint shows Predator dead. This is WMO-segment
  evidence only, not complete loop or survivability evidence. The session was
  disarmed and the character reset to spawn.
- `holdout-crypt-brill-crypt-20260831-v36.json` is the latest bounded sequence:
  it reached Brill at `[2280.111,330.289]`, transitioned semantically, and
  reached Deathknell Crypt at `[1688.275,1659.195]`; both cycles were
  `ARRIVED`, with zero combat handoffs. Its traces are not a humanlike-quality
  pass yet because the evaluator found observation gaps of `2.418 s` outbound
  and `3.260 s` return; ME-101 moves that evidence query off the control loop.

## Scope audit for the next continuation

- The registry now exposes all 83 map IDs/names from the pinned TBC 2.4.3
  `Map.dbc`-bound asset inventory. Four maps have explicit WorldPack profiles
  (Azeroth, Kalimdor, Shadowfang, Expansion01); the other 79 are deliberately
  inventory-only and cannot be launched. The Control Center can select every
  entry for read-only identity inspection, while autonomous destination launch
  remains enabled only for the complete Azeroth/Tirisfal binding (`map_id=0`,
  `zone_index=25`). This is complete map identity coverage plus fail-closed
  capability selection, not proof of autonomous routing on every map.
- Dynamic entity awareness is read-only viewport/nameplate tracking with an
  0.8 s TTL and screen-space uncertainty. It does not provide exact world
  coordinates for every mob/NPC, and the UI deliberately labels that fact.
  Selected-target range is a separate witness. No server-only ESP or hidden
  state is admitted to Champion decisions.
  This is a deliberate precision limit of the client-visible awareness path;
  it is not server-only ESP. The visible checkpoint is
  `data/runtime/operator/20260831T024608995Z-after-video-record-toggle.png`.

These historical runs are retained as capture/topology evidence, not hidden by
loosening the gate. The v38 run is the current bounded evidence for stable
Crypt→Brill→Crypt navigation; combat remains a separate authorization gate.

The follow-up v31 bounded live attempt reached `16/70` Brill objectives and
stopped `PARTIAL_CORRIDOR_FRONTIER_STUCK` at `[1993.961,1552.251]`, with no
combat handoff. The immutable WorldPack query places doodad
`0:doodad:336181` (`kn_brokencart.mdx`) immediately at that frontier; the
semantic road sample crosses its footprint and the current generic forward
bypass did not find a complete client-navmesh leg. The run was fail-closed and
runtime arm was disarmed; this is not evidence of a completed loop or of a new
death.

The subsequent code correction narrows moderate doodad blockers to their local
WorldPack footprint. Full regression remains `1245/1245` and semantic offline
validation remains `PASS`. A fresh v34 run reached `15/70` and stopped
`PARTIAL_CORRIDOR_FRONTIER_STUCK` at `[1966.334,1568.316]`; this time the
frontier persisted after the tree-disc correction, so the remaining issue is a
client-navmesh/topology gap at that bend, not a hardcoded destination or a
combat stop. The final v35 revalidation passed that bend and reached `58/74`
objectives, then stopped `RESET_REQUIRED` at `[2192.542,657.120]` after a
local collision recovery/portal recenter. Runtime arm is disarmed and no
further live input is pending; the complete return loop remains unverified.

The next offline correction adds a bounded WMO baseline check: a newly added
WMO exclusion is removed only when the client navmesh proves the same next
semantic leg complete without it. The covered-bridge repro passes this check;
the behavior is covered by unit tests and the full suite (`1246/1246`). No new
live run was started after this correction.

The post-correction offline regression also completed successfully: `v30`
reports `PASS` for all five selected cases in
`data/runtime/navigation-f3b/semantic-road-journey-validation-v30.json`, using
the immutable Azeroth WorldPack and the native client-navmesh worker. This is
offline/replay evidence only; la acel moment v35 rămânea ultima rulare live,
runtime arm era dezarmat, iar bucla de retur nu era încă declarată completă.

The single bounded v36 live sequence then reached both semantic destinations
(starea documentată la acea revizie):
Crypt→Brill and Brill→Crypt, with zero combat handoffs and Predator alive at the
final Deathknell checkpoint. It is not yet a humanlike-quality pass: the official
trace evaluator found observation gaps up to `2.418 s` outbound and `3.260 s`
return, caused by synchronous WMO baseline queries during semantic preplanning.
Those queries are now dispatched asynchronously in the worker pool (ME-101),
with the full suite green at that revision (`1247/1247`). V37 below is the
bounded revalidation of that change; its failure exposed the separate
reintroduction bug recorded in ME-102.

- `holdout-crypt-brill-crypt-20260831-v37.json` revalidated ME-101 after the
  local gate and stopped fail-closed at `59/74`. The WMO baseline passed, but
  the same candidate was reintroduced for each preplan of one semantic
  handoff; ME-102 records the scoped suppression fix.
- `holdout-crypt-brill-crypt-20260831-v38.json` revalidated ME-102 and reached
  both semantic destinations (`ARRIVED`, zero combat handoffs). The raw trace
  contained 4 outbound and 1 return capture gaps over 300 ms, all with held
  forward input and measured displacement; the quality gate passed both after
  recording these as motion-continuity exemptions (ME-103).

The follow-up v37 bounded run was started only after the local gate passed. It
stopped fail-closed at `59/74` on the same covered-bridge frontier: the WMO
baseline passed, but the static merge reintroduced that candidate for every
preplan of the same semantic handoff. The implementation now remembers a
passed WMO per next semantic-goal index, with a regression test and full suite
green at `1248/1248`. Runtime arm is disarmed; no further live claim is made
until this latest correction is revalidated.

V38 revalidated that correction: the identifier-only sequence completed both
legs (`ARRIVED`, zero combat handoffs). The trace evaluator recorded 4 raw gaps
outbound and 1 return, but all had forward input, compatible heading, and
measured world displacement; they are reported as motion-continuity exemptions,
not hidden. The updated quality gate passes both traces with zero unexplained
gaps. Full regression is now `1250/1250`; runtime arm is disarmed.

## Awareness capability audit (ME-105)

The real LAB SavedVariables capture (`2026-08-31T07:52:48Z`) confirms the
available public client signals: target/focus state, combat log, map position,
and visible nameplate/screen-space evidence. TBC 2.4.3 exposes no verified
public `UnitPosition` path and no enumerable unit-token feed for every nearby
nameplate. Therefore exact 3D coordinates for every mob/NPC are not a proven
client capability. `dynamic_entity_awareness` keeps `world_position` and
`distance_yards` null unless an independently witnessed fact exists; the UI
labels viewport/visibility-set coverage and uncertainty. No server-only or
memory-derived state is admitted to Champion decisions. Runtime arm remains
disarmed and no new live input is pending.

## Latest client-visible awareness extension (ME-106)

Observer addon `0.5.7` now records the public `UPDATE_MOUSEOVER_UNIT` witness
as `mouseover_snapshot` (identity, type, health, reaction, dead state). The
contract and SavedVariables adapter normalize it as `client_observed`; no world
coordinate or distance is inferred. Full regression after this extension is
`1251/1251`. The updated addon has not been installed into the running client,
and no live input was started.

## Deployment checkpoint (ME-107)

The running LAB client had the verified `0.5.6` observer. The exact installer
created `data/runtime/addon-backups/PerfectAssassinObserver-20260831T111748782`
and deployed observer `0.5.7` with matching Lua/TOC/README hashes. WoW was not
restarted, so this is a deployment/integrity checkpoint only; no live route or
combat test was started. The next normal UI load can emit the new public
`mouseover_snapshot` event.

## Continuity audit after handoff (ME-109)

Read-only verification after handoff confirms WoW PID `39544` is still
responding, the installed observer hashes match `0.5.7`, and the rollback
backup for `0.5.6` is intact. The full offline regression is `1251/1251`
(`94.240 s`); the expected worker-fixture stderr about `--jobs must be
between 1 and 4` is non-fatal and the suite ended `OK`. The v38 handoff
artefact validates against its schema. Runtime arm remains disarmed; no UI
reload, live movement, or combat was started by this audit.

The operator directory contains only historical combat authorization snapshots,
all expired on `2026-08-28`; no active combat runtime arm exists. They remain
for audit/rollback and are not reused. A new bounded combat session therefore
requires an explicit operator acknowledgement and fresh authorization chain.

## LAB entity-awareness scoring (ME-111)

`perfect_assassin.lab.entity_awareness` now provides a scoring-only evaluator
for exact server ground truth versus client-visible witnesses. It reports
identity recall/precision and optional position error, leaves anonymous
screen-space witnesses unlocalized, and emits `execution_authority=false`.
The evaluator is outside Brain/Movement and cannot feed Champion decisions.
The dedicated tests and full regression pass (`3/3` and `1254/1254`).

The requirement-by-requirement status is captured in
`docs/MOVEMENT_ENGINE_COMPLETION_AUDIT_2026-08-31.md`; it deliberately marks
all-map autonomous expansion, exact generic NPC coordinates, and combat as
not complete or pending rather than inferring success from partial evidence.

Offline validator v40 subsequently passed all five selected scenarios. The
three Crypt/Deathknell/Brill directional cases and the south-road holdout
reached their semantic destinations; the intentionally incomplete hill fixture
returned `RESET_REQUIRED`/`safe=false`. The result is
`data/runtime/navigation-f3b/semantic-road-journey-validation-v40.json` and
remains offline evidence only.

The two v38 traces were also reevaluated offline after the current changes;
both quality records pass with zero unexplained observation gaps. Raw capture
gaps remain recorded in `quality-v38-outbound-v3.json` and
`quality-v38-return-v3.json` as motion-continuity exemptions, not hidden
pauses. This does not constitute a new live run.

The complete offline Monte Carlo v2 also passes `600/600` trials across six
scenarios, including the captured narrow hairpin and doodad gateway, with zero
collisions and zero quality failures. The companion 18-candidate tuning search
found multiple `minimum_quality_pass_rate=1.0` candidates; no production
constants were changed from that search. These are offline evidence only.

The tuning search was then corrected to include the production `pivot_gain`
baseline and the full six-scenario corpus. The extended grid (36 candidates,
100 trials each) keeps the reviewed production profile at
`minimum_quality_pass_rate=1.0`; no production constants changed. Full
regression after this correction is `1256/1256`.

The tuning CLI now rejects `--runs` values below `100` before simulation. The
dedicated tuning tests pass `3/3`, an invalid `--runs 50` invocation writes no
output artefact, and the full offline regression is `1257/1257`. This remains
offline evidence only; no live movement, reload, or combat was started.

Trace analysis also found a possible physical pause near the Brill approach:
one observation interval lasted `1.25 s` with only `~0.55 yd` displacement while
`MOVE_FORWARD` remained held. The runner now records
`physical_motion_continuous` and refuses to reset no-progress from projected
corridor advance alone during such a gap. Targeted navigation tests pass
`83/83`, and the full offline regression after ME-117 is `1259/1259`. No live
reload or movement was started. The decision and thresholds are recorded in
`docs/adr/0056-physical-motion-continuity-gate.md`.
Offline replay of the helper flags one long gap on outbound and none on return;
the longest consecutive non-continuous run is `2`/`3` frames.

The offline proof pack v2 for map IDs `47:RazorfenKraulInstance` and
`532:Karazahn` failed the runtime-loader check because it lacked
`identity/client-world-catalog.json`, so v2 remains untouched for rollback. A
separate v3 candidate was generated from the same nav/semantic artifacts,
bundled with a schema-valid partial catalog, and sealed successfully: 826
artifacts, content hash
`33bbbba1ef9f698cd1e843c7ca463a069e78dd27339a28f57715669a00b03363`,
`runtime_ready=true`. The registry now binds v3 for both IDs; Control Center
can select them, but readiness remains `OBSERVE_ONLY` because semantic/access
promotion evidence is incomplete. Map/UI/catalog tests pass `28/28`; full
regression remains `1259/1259`.

## Latest offline interior-corpus evidence (ME-119)

The first Razorfen Kraul v3 corpus request (`27_27:p0`) is a genuine
frontier/uncovered endpoint: the native worker resolves local floor height but
returns no walkable polygon at the ~3% ADT edge. A bounded two-candidate retry
keeps that failure in the report, then resolves `p1` into a complete 29-poly,
28-portal corridor with 100/100 arrivals and zero collisions. The geometric
controller passes only 44/100 quality trials at the current 2 yd cross-track
limit; `pa_mppi_v1` reaches 93/100, still below promotion. This confirms that
the remaining work is real interior steering quality and candidate coverage,
not an invented Z seed or an executable waypoint. The artifacts are
`data/runtime/navigation-f3b/proof-v3-corpus-razorfen-smoke-v3.json` and
`data/runtime/navigation-f3b/proof-v3-corpus-razorfen-smoke-mppi.json`; no live
input, reload, or combat was started.

## Risk-controller holdout follow-up (ME-120)

The p1 corridor was replayed for the required 1,000 offline risk trials with
the experimental MPPI smoothness setting. `yaw_smoothness_weight=8.0` and
`yaw_smoothness_weight=10.0` each reached `999/1000`, with zero collisions;
the remaining failures were respectively one cross-track outlier (`2.052 yd`)
and one extra steering-sign change (`5`). The settings are therefore useful
diagnostic candidates but are not promoted to production and do not authorize
a live test. Evidence is in
`data/runtime/navigation-f3b/proof-v3-corpus-razorfen-smoke-mppi-smooth8-risk-1000.json`
and
`data/runtime/navigation-f3b/proof-v3-corpus-razorfen-smoke-mppi-smooth10-risk-1000.json`.

## Adaptive risk steering amendment (ME-121)

The adaptive selector now also chooses MPPI for a geometry-aware corridor whose
minimum portal is at most `3.5 yd` when client geometry records a clearance
inset or a polygon slope of at least `30°`. This covers the Razorfen p1
transition, whose largest funnel turn is modest but whose narrow/steep local
topology was previously left on the geometric follower. The rule remains
latched to the corridor signature and has no map, coordinate or waypoint
special case.

The adaptive runtime factory uses `yaw_smoothness_weight=6.0` and
`replan_interval_ticks=3`; the Control Center launch is now `256 x 56`. The
full six-scenario adaptive benchmark remains `100/100` per scenario, and an
adaptive p1 replay is `100/100` with zero collisions. Full regression after
the amendment is `1260/1260`. No live test, reload, or combat was started.

A read-only registry audit confirms `83` client map identities are exposed by
the Control Center picker. Of these, `6` have runtime WorldPack profiles, `1`
has a semantic catalog, and `2` have structure-access graphs; only profiles
with all required artefacts can leave `OBSERVE_ONLY`. This is inventory/UI
coverage, not proof of autonomous routing on every map.

## ME-122 — Latest all-map source audit

The deterministic client-world bake queue now has a persisted audit at
`data/runtime/navigation-f3b/client-world-bake-queue-audit-20260831.json`.
For client build `2.4.3.8606`, local terrain inventory supplies `35` eligible
maps and `3,610` ADTs, but the canonical navigation root reports
`complete_map_count=0`, `bvh_ready=false` and `bvh_artifact_count=0`.
Existing navigation roots are retained proof/work snapshots with partial map
coverage; they are not promoted without identity, semantic and structure/access
evidence. No map bake, WoW reload, Hermes change or live input was started by
this audit. The next safe implementation step is a resumable offline bake with
an explicit manifest and rollback artifact.

## ME-123 — Azeroth v4 offline bake milestone

The pinned `MapBuilder` v5 was selected for the `.nav/BVH` pipeline; the
CMaNGOS `MoveMapGen.exe` remains LAB-oracle output only (`.mmap/.mmtile`). With
the local MPQ directory `E:\\Games\\WoW TBC 2.4.3\\Data`, Azeroth now has
`687/687` road sidecars, `2,178` BVH artifacts and `687/687` nav tiles. The
quality report records zero failed tiles but explicit Recast diagnostics; the
serial Detour audit passes `687/687` with zero failures.

A separate candidate catalog and WorldPack v4 is sealed and verify-only checked
at
`E:\\WoWserver\\PerfectAssassin-Runtime\\worldpacks\\tbc243-azeroth-full-v4-candidate`
(`runtime_ready=true`, `3,558` artifacts, content hash
`99feeb1ca0969f0a0cbc1575f5fb4adb37eb2ee464fc53a54d04782f157f6dbf`). Stable
v3 and the registry are untouched. The candidate covers only `1/83` map
identities; no live input, WoW reload, Hermes change or combat was started.

## ME-124 — v4 steering corpus and corrected awareness worker

The first v4 smoke invocation passed `MapBuilder.exe` where the persistent
`--awareness-server` worker was required, so the JSON handshake failed. The
harness was corrected to use
`data/runtime/native-build/pa_nav_probe-v35/Debug/pa_nav_probe.exe` and the
valid ten-second query bound. This was an invocation error, not a navmesh
mutation or live failure.

The corrected geometric corpus resolved two of four selected ADTs and passed
`200/200` steering trials with zero collisions and zero quality failures; the
other two corridors stayed `PARTIAL_CORRIDOR` and failed closed. The production
MPPI corpus (`256 x 56`, replan `3`) resolved two of two ADTs and passed
`200/200`, zero collisions and zero quality failures, with MPPI active in about
`96.7%–97.0%` of observations. Reports:
`data/runtime/navigation-f3b/azeroth-v4-steering-smoke-4tiles-20260831.json`
and
`data/runtime/navigation-f3b/azeroth-v4-steering-smoke-mppi-2tiles-20260831.json`.

This is still bounded offline evidence, not proof of all-map autonomy,
Crypt→Brill→Crypt humanlike live behavior, generic 3D entity awareness or
combat. No live input, WoW reload, Hermes change or combat was started.

## ME-125 — Kalimdor bake and isolated candidate

Kalimdor was processed offline from `READY_FOR_SEMANTICS` with the pinned v5
MapBuilder and the local MPQ data root. The runner produced `1018/1018` road
sidecars and `1018/1018` nav tiles; the queue marks the map `COMPLETE` and the
global BVH count is `3261`. The result is
`data/runtime/navigation-f3b/kalimdor-bake-20260831.json` (`PASS`,
`execution_authority=false`).

Quality remains explicit `COMPLETE_WITH_RECAST_DIAGNOSTICS` with zero missing
or failed tiles, `12,237` Recast errors and `30,081` warnings. Serial Detour
structural validation passes `1018/1018` with zero failures. A separate
candidate pack is sealed and verify-only checked at
`E:\WoWserver\PerfectAssassin-Runtime\worldpacks\tbc243-kalimdor-v1-candidate`
(`runtime_ready=true`, `5,303` artifacts, hash
`609a20256ec154c98bd630091753a6229f610488536ec61b7ef0a5ca19c3db5f`).

The candidate is not bound in the registry. Offline bake coverage is now two
of thirty-five terrain-eligible maps; semantic/access promotion, all-map
autonomy, generic 3D entity awareness, live Crypt→Brill→Crypt quality and
combat remain pending. No live input, WoW reload, Hermes change or combat was
started.

## ME-126 — Kalimdor MPPI corpus

The offline corpus
`data/runtime/navigation-f3b/kalimdor-v1-steering-smoke-mppi-4tiles-20260831.json`
resolved `4/4` selected Kalimdor corridors and passed `400/400` MPPI trials
with the Control Center profile (`256 x 56`, replan `3`), zero collisions and
zero quality failures. The sample includes steep geometry, doodad detours,
clearance insets, a sharp turn and a narrow portal, all derived from navmesh
and BVH evidence rather than executable waypoints.

This is still four-ADT offline evidence; the candidate is not registry-bound
and all-map autonomy, generic 3D entity awareness, Crypt→Brill→Crypt
humanlike live behavior and combat remain pending. No live input, WoW reload,
Hermes change or combat was started.

## ME-127 — Shadowfang hairpin steering correction

The fixed nominal MPPI preview is now `1.80 s` and bounded yaw acceleration is
`12 rad/s²`. The old `0.90 s`/`8 rad/s²` pair reached the observed 60–70°
Shadowfang apex too late; the correction remains a time-based controller rule
over the client corridor and contains no map waypoint. The switchback unit
regression passes, and the full suite is `1263/1263`.

The official `256 x 56`, replan-3 replay of `Shadowfang:28_30:p0` is persisted
at
`data/runtime/navigation-f3b/shadowfang-v3-steering-replay-preview18-accel12-28-30-100-20260831.json`:
`100/100` arrived, `99/100` quality-pass, zero collisions, zero pivots,
maximum cross-track `2.030789 yd`, p95 `1.930345 yd`, MPPI active `98.21%`.
The lone failure is `trial_index=86`, only `0.030789 yd` above the strict
`2.0 yd` gate. This is improved offline evidence, not complete promotion or
live authorization.

The adjacent `Shadowfang:28_31:p0` replay is persisted at
`data/runtime/navigation-f3b/shadowfang-v3-steering-replay-preview18-accel12-28-31-100-20260831.json`:
`100/100` quality-pass, zero collisions, zero pivots, maximum cross-track
`1.986825 yd` and maximum four steering-sign changes. No live input, WoW
reload, combat or Hermes change was started.

## ME-129 — Residual outlier is projection-window edge evidence

For `trial_index=86` of `Shadowfang:28_30:p0`, observation `182` reports
progress `124.208726 yd` and cross-track `2.030789 yd` under the monotonic
`PROJECTION_ADVANCE_TIME_S=0.40` window. The nearest unconstrained local path
point is approximately `1.9426 yd` away at progress `124.801 yd`; the window
keeps the projected point about `0.7 yd` behind the apex to prevent branch
stealing. Offline probes at `0.35`, `0.45`, `0.50` and `0.55 s` remained
inconsistent (`16/20` on the shard), so the projection and strict quality gate
were not changed. The residual is documented as an edge case, not converted
into a PASS. No live input, WoW reload, combat or Hermes change was started.

## ME-130 — Outbound-tangent projection correction

The controller now allows the existing bounded four-yard projection window to
reach a locally associated sharp corner's outbound strip when client geometry
is valid, the actor is within four yards of the corner, and observed heading is
within `0.85 rad` of the outbound tangent. Nearest-segment selection and
monotonic progress remain authoritative; no executable waypoint or
Shadowfang-specific rule was added. Guidance is cached per corridor to keep
the control loop bounded; corner detection keeps its existing discretization.

The official `256 x 56`, replan-3 offline replay now passes `100/100` on
`Shadowfang:28_30:p0` (maximum cross-track `1.988531 yd`, zero collisions and
zero pivots) and `100/100` on `Shadowfang:28_31:p0` (maximum `1.986825 yd`, zero
collisions and zero pivots). The final 28_30 artefact is
`data/runtime/navigation-f3b/shadowfang-v3-steering-replay-projection-corner-final-28-30-100-20260831.json`.
The six-scenario geometric Monte Carlo report
`data/runtime/navigation-f3b/steering-monte-carlo-20260831-v5-projection-corner-open-ground.json`
passes `600/600`, with no collisions or quality failures.
Full regression is `1263/1263`. This is offline
evidence only; no live input, WoW reload, combat or Hermes process was started.

## ME-131 — Control Center profile selection is no longer map-id hardcoded

Control Center nu mai refuză preventiv profilurile cu `map_id != 0`. Un profil
non-zero poate ajunge la verificarea propriului semantic gate dacă declară și
are pe disc runtime WorldPack, catalog semantic, structure index și access
graph compatibile. Profilurile inventariate fără aceste dovezi rămân
`OBSERVE_ONLY`; nu se amestecă artefacte din Azeroth și nu se acordă autoritate
implicită. Verificarea gate-ului folosește acum calea WorldPack a profilului
selectat, iar fallback-ul implicit Azeroth este păstrat doar pentru forma
diagnostică fără selecție.

Regresia dedicată Control Center trece `139/139` pentru modulul
`tests.test_movement_engine`, inclusiv un profil sintetic `map_id=33` care
ajunge la starea `AWARENESS SE VERIFICĂ` în loc să fie respins printr-o regulă
specială de hartă. Testul separat leagă semantic gate-ul de WorldPack-ul
profilului selectat. Nu s-a pornit live, nu s-a reîncărcat WoW, nu s-a schimbat
combatul sau Hermes. Suta completă `python -m unittest discover -s tests`
trece acum `1270/1270`; stderr-ul fixture-ului pentru `--jobs=5` rămâne
așteptat și non-fatal.

## ME-133 — Audit WorldMapArea pentru transformări 2D de client

Assetul static `E:\\WoWserver\\TBC-LAB\\client-data\\dbc\\WorldMapArea.dbc`
este pars-at separat, cu hash-ul buildului TBC `2.4.3.8606` și scope
`lab_evaluation_only`. Raportul
`data/runtime/navigation-f3b/client-world-map-area-audit-20260831.json`
confirmă `68` rânduri în `7` contexte de hartă (`0, 1, 30, 489, 529, 530,
566`) și păstrează bounds-urile 2D plus `area_id`/`virtual_map_id`. Nu este
folosit ca poziție live, nu conține coordonate de mobi/NPC și nu acordă
autoritate; profilele de instanță fără transformare rămân `OBSERVE_ONLY`.
Schema și testul dedicat trec `1/1`, iar comanda `--check` confirmă artefactul
reproductibil.

## ME-132 — Audit reproducibil al registry-ului pentru toate hărțile

Scriptul `scripts/audit_world_map_registry.py` validează registry-ul, inventarul
clientului și bake queue-ul fără să pornească runtime-ul. Raportul determinist
este `data/runtime/navigation-f3b/world-map-registry-audit-20260831.json`:
`83/83` identități de hartă, `35` mapări cunoscute în queue, `3` mapări cu
starea `COMPLETE` și `1` profil `autonomous_ready` (Azeroth). Fiecare intrare
separă explicit artefactele declarate/de pe disc de starea queue; o hartă
inventariată fără semantic/access rămâne `OBSERVE_ONLY`. Testele auditului
trec `3/3`, iar rularea cu `--check` confirmă că raportul este reproductibil.

## ME-134 — Catalog semantic legat de profil în Control Center

Încărcarea destinațiilor din Control Center nu mai păstrează implicit
catalogul Azeroth după schimbarea profilului WorldPack. Catalogul selectat este
validat după `map_name`, `zone_index`, sistemul de coordonate și identificatorul
atlasului; dacă profilul nu declară un catalog valid, destinațiile și secvența
sunt golite, iar pornirea autonomă rămâne fail-closed. Planificarea folosește
la rândul ei binding-ul WorldPack al profilului activ, fără fallback silențios
la Azeroth.

Au fost adăugate teste pentru un catalog sintetic non-default, pentru
respingerea unui catalog de pe altă hartă și pentru plannerul legat de runtime.
Regresia completă trece `1276/1276`;
mesajul fixture-ului pentru `--jobs=5` este așteptat și non-fatal. Nu s-a
pornit live, nu s-a reîncărcat WoW și nu s-au modificat combatul sau Hermes.

## ME-135 — Knowledge Broker static, cu proveniență și map binding

Informația publică despre traineri, class/profession quest-uri și leveling este
reprezentată acum de contractul read-only `knowledge_broker_catalog`. Intrările
au provider, origin, versiune, timestamp, evidence refs, nivel și identitate
exactă de client/hartă; locația opțională este numai
`STATIC_SOURCE_CANDIDATE`, nu poziție live exactă. Wowhead este
`external_cached`, iar un export Zygor cumpărat de operator va fi
`route_teacher`/`route_guidance`; acesta furnizează pași de leveling/route și
referințe advisory pentru traineri/quest-uri. Server/LAB facts și orice pretenție `LIVE_EXACT` sunt respinse la
contract. Testele dedicate trec `8/8`; regresia completă curentă este `1278/1278`.

## ME-136 — Validator semantic profile-aware v41

Validatorul offline `scripts/validate_semantic_road_journey.py` a fost rulat
cu binding-ul de profil și a scris
`data/runtime/navigation-f3b/semantic-road-journey-validation-v41-profile-aware.json`.
Rezultatul este `PASS`: toate cele cinci cazuri au verdictul așteptat, inclusiv
ambele sensuri Deathknell↔Brill și holdout-ul de drum; fixture-ul de frontieră
este în continuare `RESET_REQUIRED`/`safe=false`. Nu s-a pornit live.

## ME-137 — Audit offline al pachetului Zygor Anniversary și importator bounded

`D:\Downloads\Zygor Release 8.1.37070.rar` este un pachet real de TBC
Classic Anniversary: addon-ul declară `Interface: 20506`, `Version: 8.1`, are
`Guides-TBC`, leveling, professions, dungeons, `NPCData`, `QuestDBData` și
`Skill_Training`. Nu este eligibil pentru instalare directă în clientul nostru
legacy `2.4.3.8606` (observer-ul nostru folosește `Interface: 20400`), dar este
o sursă locală bună pentru RouteTeacher după reconciliere.

Importatorul offline nu evaluează Lua și nu execută acțiuni. Pe cele trei fișiere
non-Trial de leveling (`Alliance`, `Common`, `Horde`) a extras `11.205` pași
ordonați, `10.007` candidați 2D și a etichetat `730` referințe de trainer,
`66` marcaje de profesie și `2.373` pași cu acțiune de combat. Cele trei fișiere
non-Trial de profesii adaugă `3.543` pași, `1.680` locații, `524` traineri de
profesie și `16` quest-uri de profesie. Toate au fost legate explicit la
`Azeroth`, `Kalimdor`, `Expansion01`, `BlackTemple` sau `BlackwingLair`; zonele
fără binding sunt respinse fail-closed. Nu s-a instalat addonul, nu s-a pornit
WoW și nu s-a filmat/trimis input live.

## ME-138 — Import static NPCData cu map scope fail-closed

Parserul `src/perfect_assassin/knowledge/npc_data.py` citește tabelul Lua
`NPCData.lua` fără evaluare de cod. `m####` este păstrat ca identificator
`zone_area`, separat de ID-urile WorldPack `0/1/530`; fiecare map-area ID cere
un binding explicit furnizat de caller. Secțiunile `Class*` devin
`class_trainer`, `Trainer*` devin `profession_trainer`, iar restul intră ca
`npc_static` read-only. Toate pozițiile rămân `normalized_map_2d` și
`STATIC_SOURCE_CANDIDATE`; nu acordă execuție și nu înlocuiesc observația din
client.

Pe fișierul real din RAR, verificarea în memorie a găsit 35 secțiuni, 66
map-area ID-uri și 3.255 rânduri (`286` class trainers, `287` profession
trainers, `2.682` NPC static). Testele Knowledge Broker trec `8/8`, iar
regresia completă offline trece `1278/1278`. Nu s-a instalat RAR-ul, nu s-a
reîncărcat WoW și nu s-a pornit test live.

## ME-139 — Audit NPCData reproducibil fără copierea conținutului licențiat

Comanda `scripts/audit_zygor_npcdata.py` primește un export local
`NPCData.lua` și un fișier de binding explicit pentru fiecare `m####`. Ea
parsează prin importatorul bounded, dar persistă numai hash-ul/size-ul sursei,
numărul de secțiuni și rânduri, distribuția pe tip/facțiune și numărul de
rânduri pe map-area. Nu scrie catalogul de NPC-uri și nu copiază addonul în
repo. `--check` detectează un audit învechit, iar lipsa unui binding oprește
fail-closed.

Testul dedicat trece `1/1`; regresia completă offline la acel pas era
`1279/1279`; după discovery-ul map-area sunt `1281/1281`.
Pachetul Kalimdor candidate rămâne doar runtime/road evidence verificată:
`1.018` tile-uri și road semantics, fără semantic destinations sau
structure/access graph, deci nu este promovat autonom. Nu s-a instalat addonul,
nu s-a reîncărcat WoW și nu s-a pornit test live.

## ME-140 — Descoperire content-minimal a map-area IDs din NPCData

Pentru a pregăti reconcilierea explicită fără a inventa mapări, comanda
`scripts/discover_zygor_npcdata_maps.py` inventariază numai ID-urile numerice
`m####` și numărul de rânduri. Pe exportul Anniversary real a găsit `66`
map-area IDs; raportul este
`data/runtime/navigation-f3b/zygor-npcdata-map-discovery-20260831.json`.
Hash-ul sursei este `9eaf8b5ff2dfebc196ef30a6404b5a99784b2e2c72dc68f93a9838a8aab6627b`,
iar raportul nu conține rânduri Lua, NPC IDs, nume sau coordonate.

Rezultatul arată exact suprafața care cere binding compatibilitate revizuit:
ID-urile Zygor `1411–1459`, `1941–1957` și dungeon IDs `9002/9005/9006`
nu sunt transformate în WorldPack. Testele dedicate trec `2/2`, inclusiv
respingerea fail-closed a unui rând numeric malformed. Nu s-a instalat addonul,
nu s-a reîncărcat WoW și nu s-a pornit test live.

## ME-141 — Index și scan bounded pentru structuri Kalimdor

Pachetul Kalimdor candidat a fost indexat offline din artefactul WorldPack:
`1.018` tile-uri de teren/navmesh, `1.426` WMO și `103.898` doodads
(`105.324` structuri), cu hash-ul pachetului păstrat exact.
Indexul este
`data/runtime/navigation-f3b/kalimdor-candidate-world-structure-index-v1.json`;
verificarea `--check` este `VERIFIED`.

Am generat și planul generic de access scan pentru toate cele `1.426` WMO,
cu `40.794` seed-uri data-derived; planul este verificat și rămâne
neautorizat. Un prim lot bounded de `100` probe, cu patru worker-e locale,
a terminat fără erori de worker: `74` probe au primit awareness persistent,
`26` au folosit fallback one-shot și niciuna nu a confirmat încă un WMO.
Rezultatul este `PAUSED_AT_PROBE_BUDGET`, cu `40.694` seed-uri rămase și
`26` cazuri de awareness static incomplet; nu se agregă structure/access graph
și profilul Kalimdor rămâne `OBSERVE_ONLY`.

## ME-142 — Prim WMO Kalimdor cu graph parțial

Un lot separat, țintit pe un singur WMO din Kalimdor, a procesat toate cele `39`
seed-uri ale structurii. A confirmat `2` observații conținute și a produs
`14` access openings / `9` boundary chains, dar graph-ul este marcat
`PARTIAL_OBSERVED_COMPONENTS`, nu este legat în registry și nu acordă autonomie
map-wide. Celelalte `34` seed-uri au fost în afara structurii, iar `3` nu au
avut poligon navmesh; dovada rămâne candidat de calibrare locală.

## ME-143 — Scan Kalimdor extins și agregare parțială

Un lot bounded suplimentar de `1.000` probe a folosit patru worker-e locale și
a terminat cu `0` erori. Progresul total este `1.139/40.794` seed-uri,
cu `36` observații WMO confirmate, `136` awareness-uri statice incomplete și
`149` seed-uri fără poligon navmesh; rămân `39.655` seed-uri.

Task-urile încheiate pozitiv au fost agregate într-un graph candidat cu `16`
structuri, `36` observații, `135` openings și `293` boundary chains. Graph-ul
este explicit `PARTIAL_OBSERVED_COMPONENTS`, deci rămâne probă offline și nu
este atașat registry-ului/autonomiei Kalimdor.

## ME-144 — Binding bounded al map-area IDs din Zygor Anniversary

Fișierul `Libs-TBC/LibRover-1.0/data.lua` din aceeași arhivă Anniversary a fost
pars-at ca date statice, fără evaluare Lua. El rezolvă fără ambiguități toate
cele `66` map-area IDs întâlnite în `NPCData.lua`, inclusiv orașe, Outland și
dungeon-urile sintetice `9002/9005/9006`. Importul în memorie produce `3.255`
de intrări (`286` class trainers, `287` profession trainers, `2.682` NPC static)
și păstrează `execution_authority=false`.

Auditul content-minimal este
`data/runtime/navigation-f3b/zygor-npcdata-map-binding-audit-20260831.json`;
starea este `COMPLETE`, cu `66/66` bindings, `0` ambigue și `0` nerezolvate.
Raportul persistă doar hash-uri, count-uri și statusuri, nu nume, NPC IDs sau
coordonate. Aliasurile multiple din LibRover sunt fail-closed pentru orice ID
cerut. Nu s-a instalat addonul, nu s-a reîncărcat WoW și nu s-a pornit input
live.

## ME-266 — Brain de leveling cu RouteTeacher și nivel ales în Control Center

Brain-ul nou `src/perfect_assassin/brain/leveling.py` primește o catalogă
Knowledge Broker read-only, nivelul curent și harta exactă. El întoarce pașii
Zygor în ordinea ghidului și alege cel mult o coordonată normalizată pentru
următorul plan. Un pas fără coordonată rămâne advisory pentru quest/trainer;
nu devine waypoint și nu primește autoritate de execuție.

Control Center are acum „Urmează ghidul de leveling”, „Nivelul meu” (1–70) și
alegerea unei catalogi JSON locale. La START, brain-ul creează un plan ignorat
de Git și îl atașează unui singur goal normalizat; runnerul verifică nivelul,
harta, coordonata și `execution_authority=false`. Scriptul
`scripts/build_zygor_leveling_catalog.py` construiește catalogă din fișierele
Zygor extrase de operator, fără să copieze arhiva în repository.

Pentru siguranță, planul Zygor nu înlocuiește observația clientului, navmesh-ul
sau poarta de input. Combatul rămâne separat și nu este pornit de această
opțiune. Testele dedicate pentru brain, catalogă, supervisor și UI trec
`53/53`; următorul live rămâne blocat până la armul continuu de mișcare descris
în ME-263.

## ME-145 — Bounded bake Expansion01 și audit geometric complet

`Expansion01` (map `530`) a fost reluat offline din starea
`READY_FOR_SEMANTICS` folosind aceleași MPQ-uri locale și `MapBuilder` pinned
v5. Build-ul a produs `800/800` sidecar-uri `.road` și `800/800` tile-uri
`.nav`; rezultatul contractual este
`data/runtime/navigation-f3b/expansion01-bake-20260831.json`, cu
`status=PASS`, `server_dependency=false`, `emulator_dependency=false` și
`execution_authority=false`.

Catalogul candidat separat
`data/runtime/navigation-f3b/client-world-catalog-world-continents-v2-candidate.json`
leagă exact `Azeroth`, `Kalimdor` și `Expansion01` (`3/83` identități client,
`coverage_state=complete` pentru cele trei map-uri). El nu este atașat
registry-ului Champion și nu acordă semantic/access autonomy.

Auditul structural Namigator/Detour pentru Outland este
`data/runtime/navigation-f3b/expansion01-navmesh-geometry-20260831.json`:
`800/800` tile-uri valide, `204.800` sub-tile-uri validate, `0` failures.
Auditul de calitate este
`data/runtime/navigation-f3b/expansion01-navmesh-quality-20260831.json`:
`COMPLETE_WITH_RECAST_DIAGNOSTICS`, cu `0` tile-uri lipsă/eșuate și
diagnostice Recast păstrate explicit (`8.865` errors, `23.200` warnings).

Auditul parallel pe payload-uri Namigator mari a expus un crash intern al
Python 3.14 (`Executing a cache`) după ce validatorul a respawn-uit workers;
verificarea serială completă a trecut. Parserul a fost făcut self-contained
pentru header-ul `'<6I'`, iar regresia dedicată pentru worker parallel și
link-uri Detour 64-bit trece. Nu s-a instalat addonul, nu s-a reîncărcat WoW,
nu s-a pornit combat sau input live.

## ME-146 — Reconciliere content-minimal Zygor cu WorldMapArea

Arhiva `D:\Downloads\Zygor Release 8.1.37070.rar` a fost testată cu 7-Zip:
`Everything is Ok`, RAR5, `18.260.702` bytes, SHA-256
`d8d416ad95f9071fd8578df218a70235c377ea8b350f81ca2ea6f5417a65d2d3`.
Rădăcina este `ZygorGuidesViewerClassicTBCAnniv`, cu `Guides-TBC`,
`Data-TBC`, `Code-TBC` și TOC `Interface: 20506`, `Version: 8.1`. Fișierul
`Zygor.zip` separat este un addon vechi din 2008 și nu este varianta TBC
Anniversary.

Verificarea bounded a fișierelor non-Trial din RAR a reconfirmat `11.205`
pași de leveling, `10.007` coordonate candidate, `730` traineri de clasă și
`2.373` pași cu combat; profesiile adaugă `3.543` pași, `1.680` coordonate,
`524` traineri de profesie și `16` quest-uri de profesie. Lua nu a fost
evaluat; numele/pozițiile licențiate nu au fost copiate în repo.

Reconcilierea statică este în
`data/runtime/navigation-f3b/zygor-world-map-reconciliation-20260831.json`:
`22` potriviri exacte, `23` normalizate, `0` ambigue și `21` nerezolvate din
`66` map-area IDs. Raportul nou și contractul său sunt
`scripts/audit_zygor_world_map_reconciliation.py`, respectiv
`contracts/zygor-world-map-reconciliation.schema.json`; ADR-ul este
`docs/adr/0063-content-minimal-zygor-world-map-reconciliation.md`.
Cele `21` rămân fail-closed; nu se promovează semantic/access și nu se
pornește test live.
Regresia completă după această adăugare este `1287/1287`.

## ME-147 — Loop închis pentru secvențe multi-destinație

`DestinationSequence` suportă acum opțional `close_loop=true`. Când este
activ, supervisor-ul adaugă explicit prima destinație la finalul secvenței
(de exemplu `A → B → C → A`), fără să transforme ID-urile în waypoints.
Fișierele vechi rămân compatibile (`close_loop` implicit `false`). Control
Center are checkbox-ul `Închide bucla la prima destinație`, iar valoarea este
validată/propagată în contractul `semantic_destination_sequence`.

Testele supervisor + Control Center trec `31/31`. Aceasta rezolvă semantica
de loop/patrulare la nivel de orchestration; fiecare legătură continuă să fie
replanificată din poziția observată și rămâne supusă gate-urilor WorldPack.

## ME-148 — Regresie post-loop și audit de acoperire map/UI

După adăugarea `close_loop`, regresia offline completă trece `1289/1289` în
aproximativ `94` secunde. `compileall` și `git diff --check` trec; mesajul
fixture-ului negativ `--jobs must be between 1 and 4` este așteptat și nu este
un eșec de test.

Verificările reproducibile `--check` pentru discovery-ul NPCData, binding-ul
LibRover și reconcilierea WorldMapArea trec pe fișierele extrase temporar din
`Zygor Release 8.1.37070.rar`; arhiva nu este copiată în repo și Lua nu este
evaluat. Auditul registry/UI confirmă `83` profiluri expuse, `35` map-uri în
queue și `4` bake-uri complete, dar numai `1` profil cu toate artefactele
necesare pentru `AUTONOM`. Hărțile rămase sunt vizibile pentru inspecție, însă
catalogul semantic, structure index-ul sau access graph-ul lipsă țin pornirea
oprită fail-closed. Nu s-a instalat addonul, nu s-a reîncărcat WoW și nu s-a
pornit test live.
până la catalog semantic și structure/access graph proprii.

## ME-149 — Audit content-minimal pentru ghidurile Zygor și indicator UI

Auditul `scripts/audit_zygor_guide_coverage.py` procesează numai cele șase
fișiere non-Trial selectate din pachetul Anniversary și persistă hash-uri,
dimensiuni și count-uri; nu păstrează nume de ghid, coordonate sau payload Lua.
Artefactul este
`data/runtime/navigation-f3b/zygor-guide-coverage-20260901.json`, cu
`14.748` pași, `11.687` coordonate candidate, `730` traineri de clasă,
`663` traineri de profesie și `855` quest-uri clasificate. Starea este
`SELECTED_NON_TRIAL_FILES`, iar `execution_authority=false`.

Control Center afișează acum această acoperire ca indicator RouteTeacher
read-only. Indicatorul refuză audituri malformate sau cu autoritate de execuție;
nu alimentează direct plannerul, nu creează waypoints și nu schimbă gate-ul
profilului WorldPack. Testele dedicate UI + audit trec `21/21`. Nu s-a
instalat addonul, nu s-a reîncărcat WoW și nu s-a pornit test live.
Regresia offline completă după integrarea indicatorului trece `1293/1293`;
`compileall`, auditul `--check` și verificările de whitespace rămân verzi.

## ME-150 — Replay Shadowfang cu profilul MPPI validat

Replay-ul real păstrat pentru coridorul Shadowfang a fost reluat offline cu
profilul explicit `batch_size=256`, `time_steps=56`,
`replan_interval_ticks=3`. Rezultatul este `100/100` sosiri, `0` coliziuni,
`quality_pass_rate=1.0`, cross-track maxim `1.9885` și activare MPPI
`98.2%`; artefactul este
`data/runtime/navigation-f3b/shadowfang-v3-steering-replay-adaptive-20260901-v2.json`.
Rularea anterioară cu vechile valori implicite `128/56/4` a trecut doar
`79/100`, deci valorile implicite ale replayer-ului au fost aliniate cu
profilul validat și au primit regresie dedicată (`14/14` teste steering).

Un input de replay care nu respectă schema a fost respins fail-closed înainte
de simulare. Dovada rămâne offline/sintetică; nu s-a reîncărcat WoW și nu s-a
pornit test live. Regresia offline completă după această corecție trece
`1295/1295`; `compileall`, auditul `--check` și `git diff --check` rămân verzi.

## ME-151 — Acoperire RouteTeacher pe hărți cu binding explicit

`scripts/audit_zygor_route_coverage.py` parsează aceleași șase fișiere
non-Trial din Anniversary și cere binding explicit pentru cele `66` de zone
întâlnite. Raportul content-minimal este
`data/runtime/navigation-f3b/zygor-route-coverage-20260901.json`; reține doar
hash-uri, dimensiuni, identități WorldPack și count-uri. Acoperirea are
`4.625` pași pe Azeroth, `5.148` pe Kalimdor, `4.974` pe Expansion01 și `1`
pe BlackTemple (`14.748` în total), cu `11.687` candidate de coordonate.

Importatorul RouteTeacher păstrează acum ultima zonă explicită în pașii
moderni fără `goto`, în aceeași guide, în loc să cadă implicit pe Azeroth.
Binding-urile și raportul sunt read-only (`execution_authority=false`), iar
Control Center afișează sumarul multi-map fără să creeze destinații sau
waypoint-uri executabile. Testele dedicate sunt `13/13`; nu s-a instalat
addonul, nu s-a evaluat Lua și nu s-a pornit test live.
Regresia offline completă după această schimbare trece `1300/1300`; auditul
`--check`, `compileall` și `git diff --check` sunt verzi.

## ME-152 — Progres bounded al access scan-ului Kalimdor

Un lot offline suplimentar de `1.000` probe a folosit worker-ul pin-uit prin
hash-ul planului (`v35`) și patru job-uri persistente. Scanarea a ajuns la
`2.139/40.794` seed-uri, cu `57` observații WMO confirmate, `74` structuri
complete și `0` erori de worker; raportul de progres este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v1.json`.

Structurile completate cu observații au generat graph-ul candidat
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v2.json`:
`57` observații, `254` openings și `488` boundary chains. Graph-ul este
explicit `PARTIAL_OBSERVED_COMPONENTS`, nu este legat în registry și nu acordă
autonomie. Prima încercare cu worker incompatibil a fost respinsă înainte de
 probe; nu s-a pornit WoW și nu s-a trimis input live.

## ME-153 — Scan Kalimdor continuat cu profilul v35

Un al doilea lot bounded de `1.000` probe, reluat din fragmentele existente și
cu același worker v35 pin-uit, a dus progresul la `3.139/40.794` seed-uri:
`73` observații WMO, `106` structuri complete și `0` erori de worker. Raportul
actualizat rămâne
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v1.json`,
cu `37.655` seed-uri neatinse.

Agregarea strictă a structurilor completate este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v3.json`:
`73` observații, `350` openings și `692` boundary chains. Starea este în
continuare `PARTIAL_OBSERVED_COMPONENTS`; graph-ul nu este legat în registry și
nu acordă autonomie. Scanarea a rulat numai offline, fără reload WoW și fără
input live.

## ME-154 — Primul access scan bounded pentru Expansion01

Expansion01 are bake-ul local complet (`800/800` tile-uri navmesh), iar indexul
nou reține `1.659` WMO și `94.506` doodads. Planul deterministic are `47.170`
seed-uri eligibile, fără structuri deferred. Primul lot offline de `1.000`
probe, cu worker v35 și patru job-uri persistente, a confirmat `17` observații
WMO, a încheiat `35` structuri și nu a raportat erori de worker; rămân `46.170`
seed-uri.

Raportul și graph-ul candidat sunt
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v1.json`
și
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v1.json`.
Graph-ul are `17` observații, `29` openings și `88` boundary chains, cu starea
`PARTIAL_OBSERVED_COMPONENTS`; nu este legat în registry și nu acordă
autonomie. Nicio modificare live nu a fost pornită.

## ME-155 — NPCData static content-minimal în Control Center

Binding-ul explicit pentru cele `66` map-area IDs din `Data-TBC/NPCData.lua`
este verificat prin tabela statică LibRover, fără ambiguități. Auditul content-
minimal
`data/runtime/navigation-f3b/zygor-npcdata-audit-20260901.json` reține doar
hash/size și count-uri: `3.255` intrări, `66` zone, `286` traineri de clasă,
`287` traineri de profesie și `2.682` NPC statici. Control Center afișează acest
rezumat read-only; nu pretinde poziții live exacte și nu acordă execuție.

Binding-ul și auditul au `execution_authority=false`, iar testele UI resping
explicit un audit care ar încerca să acorde autoritate. Nu s-a evaluat Lua, nu
s-a reîncărcat WoW și nu s-a pornit input live.

## ME-156 — Holdout offline Crypt→Brill→Crypt și starea Anniversary

Holdout-urile păstrate pentru journey supervisor (`v17`–`v38`) au fost
comparate read-only: `5` au `ARRIVED`, `10` s-au oprit `STOPPED_FAIL_CLOSED`,
`3` prin eroare de child, `2` la bugetul de navigație și `1` la bugetul de
combat. Toate au `execution_authority=false`; ultima înregistrare, `v38`, a
ajuns la `ARRIVED`, dar seria istorică rămâne mixtă și nu este dovadă de
determinism live.

Validatorul semantic offline profile-aware din
`data/runtime/navigation-f3b/semantic-road-journey-validation-v41-profile-aware.json`
trece `5/5`: Crypt spawn→Brill, Deathknell→Brill, Brill→Deathknell și
holdout-ul Brill south road ajung la destinație; fixture-ul de deal rămâne
`partial_local_navmesh_corridor` și este acceptat ca `RESET_REQUIRED`.
Aceasta separă baza statică RouteTeacher/WorldPack (verde) de variația
holdout-ului journey/frontier (încă de investigat), fără a promova o rută sau
a porni live-ul.

## ME-157 — Scan Kalimdor continuat cu binding-ul corect

Prima comandă a fost respinsă înainte de probe deoarece indexul Kalimdor era
legat de profilul candidat, nu de agregatul `world-continents`; aceasta este o
verificare fail-closed, nu o eroare de navigație. Reluarea cu perechea exactă
`world-pack-runtime-tbc243-kalimdor-v1-candidate.json` + indexul candidat a
procesat încă `1.000` seed-uri: progresul este `4.139/40.794`, `121`
observații WMO, `140` structuri complete și `0` erori de worker; rămân
`36.655` seed-uri.

Agregarea strictă a structurilor completate este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v4.json`:
`121` observații, `608` openings și `1.126` boundary chains. Graph-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, nu este legat în registry și nu acordă
autonomie; toate operațiile au fost offline.

## ME-158 — Filtrare strictă a ancorelor semantice Tirisfal

Catalogul Azeroth a primit o singură destinație semantică nouă,
`landmark:deathknell-south-gate`, derivată din ruta revizuită și validată prin
query local 3D (`complete=true`, fără blocker nerezolvat). Alte ancore
intermediare candidate au fost testate segment-cu-segment și retrase din
catalog când query-ul a returnat frontieră parțială, eroare de height sau
timeout. Astfel Control Center nu afișează destinații care doar par accesibile
din road semantics; plannerul rămâne autonom și își calculează coridorul din
poziția observată.

## ME-159 — Primul lot Expansion01 după indexarea WMO

Scanarea bounded cu profilul WorldPack exact a procesat încă `1.000` seed-uri
Expansion01: progres `2.000/47.170`, `37` observații WMO noi cumulate în
artefactul de progres, `70` structuri complete și `0` erori de worker; rămân
`45.170` seed-uri. Agregarea strictă
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v2.json`
are `37` observații, `98` openings și `254` boundary chains.

Starea rămâne `PARTIAL_OBSERVED_COMPONENTS`; graph-ul nu este legat în registry
și nu acordă autonomie. Rezultatele sunt exclusiv offline.

## ME-160 — Scan Kalimdor bounded după lotul v4

Lotul offline următor de `1.000` probe, cu aceeași pereche profil/index
Kalimdor și worker v35, a dus progresul la `6.139/40.794` seed-uri: `177`
observații WMO, `209` structuri complete și `0` erori de worker; rămân
`34.655` seed-uri. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v1.json`,
iar agregarea strictă este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v6.json`
(`177` observații, `812` openings, `1.622` boundary chains).

Starea rămâne `PARTIAL_OBSERVED_COMPONENTS`, nelegată în registry și cu
`execution_authority=false`; nicio operație live nu a fost pornită.

## ME-161 — Scan Expansion01 bounded continuat

Cu profilul WorldPack agregat corect și indexul Expansion01, un lot offline de
`1.000` probe a dus progresul la `4.000/47.170` seed-uri: `114` observații WMO,
`141` structuri complete și `0` erori de worker; rămân `43.170` seed-uri.
Agregarea strictă este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v4.json`
(`114` observații, `226` openings, `776` boundary chains), iar raportul de
progres este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v1.json`.

Coverage rămâne `PARTIAL_OBSERVED_COMPONENTS`, nelegată în registry și fără
autoritate de execuție; totul a fost offline.

## ME-162 — Reevaluare offline a calității trace-urilor v38

Evaluatorul oficial `scripts/evaluate_live_steering_trace.py` a fost rerulat
pe cele două rezultate existente ale secvenței v38, fără a porni o sesiune WoW.
Ambele trace-uri au `arrived=true`, `passed=true` și `0` gap-uri neexplicate
peste 300 ms. Trace-ul outbound are `4` gap-uri brute, iar returul `1`; toate
sunt clasificate explicit ca `motion_continuity_exempted_gaps`, cu deplasare
măsurată și input înainte compatibil, nu ascunse prin relaxarea pragului.
Artefactele de recheck sunt în
`data/runtime/navigation-f3b/results/` cu sufixul `quality-recheck.json`.

## ME-163 — Catalog client-derived pentru toate map-area transforms

WorldMapArea auditul local a fost materializat într-un catalog read-only cu
`68` transformări `(map_id, area_id)`, acoperind continentele TBC, zonele și
instanțele prezente în assetul auditat. Catalogul
`config/pose/world-map-zone-transforms-tbc243-8606.json` păstrează hash-ul
assetului, fingerprint-ul recordurilor, sursa și momentul recuperării; loaderul
respinge duplicatele, bounds degenerate și orice `execution_authority=true`.

Control Center afișează acum această acoperire ca indicator advisory și nu o
folosește ca rută sau ca înălțime live. Testele țintite sunt `29/29`, iar
regresia completă după integrare este `1313/1313`; nu s-a pornit WoW și nu s-a
trimis input live.

## ME-164 — Acoperire RouteTeacher prin transformările client 2D

Auditul bounded `scripts/audit_zygor_route_transform_coverage.py` validează
coordonatele celor șase fișiere non-Trial prin catalogul WorldMapArea, fără să
rețină payload Lua, nume de ghid sau coordonate. Rezultatul
`data/runtime/navigation-f3b/zygor-route-transform-coverage-20260901.json`
transformă `11.686/11.687` candidați: Azeroth `3.434/3.434`, Kalimdor
`3.918/3.918` și Expansion01 `4.334/4.334`. Singurul candidat nerezolvat este
Black Temple (`map_id=564`), fără rând în catalogul WorldMapArea; starea rămâne
`PARTIAL_CLIENT_2D_TRANSFORM`, iar `execution_authority=false`.

Testele dedicate auditului trec `2/2`, testele UI `2/2`, auditul reproducibil
`--check` este verde, iar operațiunile live au rămas oprite.

## ME-165 — Scanuri bounded Kalimdor și Expansion01 continuate

Un lot offline de `1.000` probe pentru Kalimdor a dus progresul la
`6.139/40.794`, cu `177` observații WMO acceptate, `209` structuri complete și
`0` erori de worker. Agregarea strictă `partial-v6` are `812` openings și
`1.622` boundary chains și rămâne `PARTIAL_OBSERVED_COMPONENTS`.

Un lot echivalent pentru Expansion01, rulat pe calea corectă după eliminarea
unui director duplicat creat de o invocare cu typo, a dus progresul la
`4.000/47.170`, cu `114` observații acceptate, `141` structuri complete și
`0` erori. Agregarea `partial-v4` are `226` openings și `776` boundary chains.
Ambele artefacte sunt offline, nelegate în registry și cu
`execution_authority=false`; nu s-a pornit live.

## ME-166 — Scan Kalimdor bounded continuat

Un lot offline suplimentar de `1.000` probe, reluat din checkpoint-ul existent
cu profilul candidat și workerul v35 pin-uit, a procesat toate probele fără
erori. Raportul este acum la `7.139/40.794` seed-uri (`188` seed-uri
acceptate, `246` structuri complete, `33.655` seed-uri rămase). Agregarea
strictă a task-urilor complete, `partial-v7`, conține `186` observații,
`837` openings și `1.682` boundary chains; starea rămâne
`PARTIAL_OBSERVED_COMPONENTS`.

Artefactele rămân nelegate în registry, cu `execution_authority=false` și
folosite doar ca evidence offline; nu s-a pornit WoW, nu s-a reîncărcat clientul
și nu s-a trimis input live.

## ME-167 — Scan Expansion01 bounded continuat

Un lot offline de `1.000` probe pentru Expansion01 a fost reluat din
checkpoint cu profilul World Continents și workerul v35 pin-uit. Progresul este
acum `5.000/47.170` seed-uri, cu `123` seed-uri acceptate, `177` structuri
complete, `42.170` seed-uri rămase și `0` erori de worker. Agregarea strictă
`partial-v5` are `123` observații, `303` openings și `848` boundary chains;
starea rămâne `PARTIAL_OBSERVED_COMPONENTS`.

Artefactul este offline, nelegat în registry și are
`execution_authority=false`; nu s-a pornit WoW, nu s-a reîncărcat clientul și
nu s-a trimis input live.

## ME-168 — Regresie offline după scanurile continentale

Mediul `.venv` a primit doar dependența de test `pytest==8.4.2`; nu s-a
schimbat codul de runtime. Testele țintite pentru structure-access,
transformări RouteTeacher și indicatorul Control Center trec `56/56`, iar
suita offline completă trece `1313/1313` în `111,05 s`. Rezultatul confirmă
regresia contractelor și a cazurilor de steering deja existente; nu constituie
dovadă de execuție live. WoW, inputul live și procesele Hermes au rămas
oprite.

## ME-169 — Recheck offline al trace-urilor Crypt↔Brill

Evaluatorul oficial `scripts/evaluate_live_steering_trace.py` a fost rulat pe
trace-urile brute existente pentru ambele sensuri, fără să pornească WoW.
Outbound are `7.000` cadre, `arrived=true`, `passed=true`, `4` gap-uri peste
300 ms clasificate ca motion-continuity exemptions și `0` gap-uri
neexplicate. Returul are `6.797` cadre, `arrived=true`, `passed=true`, `1`
exemption și `0` gap-uri neexplicate. Rezultatele noi sunt
`quality-v38-outbound-recheck-20260901.json` și
`quality-v38-return-recheck-20260901.json`; nu reprezintă un test live nou.

## ME-170 — Monte Carlo offline extins pentru hairpin și curbe înguste

Simularea deterministă `scripts/run_steering_monte_carlo.py` a rulat `200`
curse pentru fiecare dintre cele șase scenarii, cu `5` joburi independente.
Toate cele `1.200/1.200` curse au fost completate și au trecut quality gate-ul;
toate scenariile au `0` coliziuni și `0` eșecuri de calitate. Scenariul
`narrow_outdoor_hairpin` are maximum `2` schimbări de semn și maximum
`0.2830` pivot fraction. Raportul este
`data/runtime/navigation-f3b/steering-monte-carlo-20260901-v6.json`, cu
`execution_authority=false`; acesta este evidence offline, nu validare live.

## ME-171 — Scan Kalimdor bounded continuat

Un lot offline de `1.000` probe a dus Kalimdor la `8.139/40.794` seed-uri,
cu `194` seed-uri acceptate, `280` structuri complete, `32.655` rămase și
`0` erori de worker. Agregarea strictă `partial-v8` are `194` observații,
`888` openings și `1.735` boundary chains; starea rămâne
`PARTIAL_OBSERVED_COMPONENTS`, nelegată în registry și cu
`execution_authority=false`.

## ME-172 — Scan Expansion01 bounded continuat

Un lot offline de `1.000` probe a dus Expansion01 la `6.000/47.170` seed-uri,
cu `129` seed-uri acceptate, `214` structuri complete, `41.170` rămase și
`0` erori de worker. Agregarea strictă `partial-v6` are `129` observații,
`320` openings și `910` boundary chains; starea rămâne
`PARTIAL_OBSERVED_COMPONENTS`, nelegată în registry și cu
`execution_authority=false`. Nicio operațiune live nu a fost pornită.

## ME-173 — Validator semantic offline reexecutat pe Crypt/Brill

`scripts/validate_semantic_road_journey.py` a fost rulat pe WorldPack-ul
Azeroth v3 și workerul v34, cu toate cele cinci cazuri. Rezultatul
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v42.json`
este `PASS`: Crypt spawn→Brill, Deathknell→Brill, Brill→Deathknell și
Brill south-road au ajuns la destinație; fixture-ul deal/frontieră a rămas
`RESET_REQUIRED` cu `reason=partial_local_navmesh_corridor`. Toate cazurile au
`execution_authority=false`; nu s-a scris gate live și nu s-a pornit WoW.

## ME-175 — Semantic gate offline proaspăt, inert

După validarea v43 cu toate cele cinci cazuri, validatorul a scris
`data/runtime/operator/movement-engine-semantic-gate.json`. Gate-ul are
`status=PASS`, este legat prin hash de rezultatul v43, WorldPack Azeroth v3 și
workerul v34, dar `live_authority_enabled=false`; nu poate autoriza input.
Preflight-ul confirmă în continuare lipsa unei autorizații temporale LAB și a
unui runtime arm. Nu s-a pornit WoW și nu s-a schimbat niciun proces paralel.

## ME-174 — Regresie awareness client-visible și scoring LAB

Testele dedicate pentru `dynamic_entity_awareness`, tracker-ul de nameplate,
dynamic avoidance, experiența append-only, detectorul vizibil și combat HUD
trec `38/38`. Ele confirmă doar ingestia viewport/nameplate și evaluarea LAB;
nu acordă poziții 3D exacte pentru entități ascunse și nu activează combat sau
input. Nu există încă autorizație temporală LAB, semantic gate activ sau
runtime arm; operațiunile live au rămas oprite.

## ME-176 — Transform runtime legat de mapă și zonă

Runner-ul navmesh nu mai refolosește implicit transformarea Tirisfal când un
profil WorldPack selectat indică altă hartă. El rezolvă transformarea 2D din
catalogul client read-only `WorldMapArea.dbc` după `map_id` și `zone_index`, cu
fallback doar pentru aliasurile legacy revizuite Tirisfal/Undercity. Control
Center transmite acum `zone_index` citit din catalogul semantic și calea
catalogului de transformări.

Testul offline pentru `Kalimdor/Durotar` trece împreună cu regresia țintită
`184/184`; nicio hartă nouă nu a fost promovată, iar `live_authority_enabled`
rămâne `false`. Nu s-a pornit WoW și nu s-a trimis input live.

## ME-177 — Regresie semantică după transformarea multi-map

Validatorul `scripts/validate_semantic_road_journey.py` a fost rerulat după
rezolvarea transformărilor map/zonă și a scris
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v44.json`.
Toate cele cinci cazuri au verdictul așteptat: Crypt→Brill, Deathknell→Brill,
Brill→Deathknell și Brill south-road sunt `ARRIVE`, iar fixture-ul de deal
rămâne `RESET_REQUIRED` cu `partial_local_navmesh_corridor`. Regresia completă
este `1316/1316`; gate-ul live rămâne inert și nu s-a pornit WoW.

## ME-178 — Gate offline rebondat la v45

Pentru sincronizarea gate-ului cu ultima validare, validatorul a fost rerulat
cu `--write-offline-gate` și a scris
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v45.json`.
Rezultatul este `PASS` pe aceleași cinci cazuri, iar
`data/runtime/operator/movement-engine-semantic-gate.json` pointează la v45 cu
hash verificat și `live_authority_enabled=false`. Autorizația temporală LAB și
runtime arm lipsesc în continuare; nu s-a pornit WoW și nu s-a trimis input
live.

## ME-179 — Toate refresh-urile de poziție folosesc transformarea selectată

Au fost închise ultimele apeluri `_position()` din bucla autonomă și din
handler-ele de handoff/eroare. Fiecare folosește transformarea rezolvată după
`map_id + zone_index`, împreună cu verificarea mapării HUD; nu mai există o
re-resolvare implicită Tirisfal în aceste căi.

Regresia țintită rămâne `184/184`, iar suita offline completă este
`1316/1316` în `112,31 s`; `compileall` și `git diff --check` sunt curate.
Gate-ul semantic rămâne inert (`live_authority_enabled=false`), fără
autorizație temporală LAB/runtime arm și fără test live.

## ME-180 — Revalidare locală a arhivei TBC Anniversary

Arhiva `D:\Downloads\Zygor Release 8.1.37070.rar` a fost retestată read-only
cu 7-Zip: `Everything is Ok`, RAR5, `83` directoare și `868` fișiere,
`85.807.771` bytes necomprimați. SHA-256 rămâne
`D8D416AD95F9071FD8578DF218A70235C377EA8B350F81CA2EA6F5417A65D2D3`.
TOC-ul TBC confirmă `Interface: 20506`, `Version: 8.1` și rădăcina
`ZygorGuidesViewerClassicTBCAnniv`; arhiva nu a fost copiată în repo și nu a
fost evaluat Lua.

## ME-181 — Viewer și continuitate map-bound

Pose-ul read-only, bridge-ul MapViewer și corpse-recovery propagă acum
`map_id`, `zone_index` și catalogul WorldMapArea selectat. Fallback-ul vechi
pentru Tirisfal este păstrat numai pentru fixture-urile Azeroth legacy; pentru
o hartă nenulă transformarea trebuie să existe în catalog.

Testul offline Durotar/`map_id=1, zone_index=14` și regresia viewer/continuity
trec; suita completă este `1319/1319`. Nicio hartă nouă nu este promovată
autonom, gate-ul rămâne inert și nu s-a pornit WoW.

## ME-182 — Diagnostic offline al frontierei de deal

Requery-ul bounded al fixture-ului de frontieră a confirmat aceeași cauză,
fără a relaxa gate-ul: primul corridor se oprește la
`(2055.357422, 1240.476562, 64.966675)`, la `101.64` yards de primul anchor
semantic, cu `7` tranziții steep și `5617` poligoane penalizate de worker.
Refinarea adaptivă nu găsește progres înainte din această componentă locală și
rămâne `RESET_REQUIRED`/`partial_local_navmesh_corridor`. Crypt↔Brill rămâne
`ARRIVE`; nu se introduce shortcut geometric neprobat și nu s-a pornit live.

## ME-183 — Layer/variant probe offline pentru aceeași frontieră

Selectorul generic de strat vertical a fost verificat cu nouă offseturi bounded
(`0`, `±32`, `±64`, `±128`, `±256` yards) pe WorldPack-ul Azeroth v3. Toate
probele au rezolvat aceeași suprafață (`height_candidates=1`) și același stop
`(2055.357422, 1240.476562)`, deci nu există un al doilea etaj legitim pe care
să-l aleagă selectorul.

Au fost validate și cele trei variante generate de planner (`road_backbone`,
`balanced`, `shortcut`). Toate au aceeași intrare semantică
`(2132.100586, 1307.117310)`; primele două au `103` celule de drum, iar
`shortcut` are `14` celule de drum/`22` near-road/`34` bridge, însă toate se
opresc în aceeași frontieră cu `101.64` yards până la anchor. Ancorele ulterioare
nu pot ocoli blocajul: requery-urile rămân parțiale și nu produc progres înainte.

Concluzia rămâne `RESET_REQUIRED`/`partial_local_navmesh_corridor`; nu se
relaxează filtrul steep, nu se inventează waypoint sau shortcut geometric și nu
s-a pornit test live.

## ME-184 — Neighborhood frontier probe fără teleport sau waypoint

O probă bounded de vecinătate (`dx,dy ∈ {-100,0,100}` yards) a separat două
componente reale ale atlasului. Seed-ul dealului rămâne pe suprafața izolată:
`(2031.547241, 1226.785400)`, cu radial egress nereușit și același stop
`(2055.357422, 1240.476562)`. Probele la aproximativ `+100` yards pe axa sudică
pot ajunge la anchor-ul de drum `(2132.100586, 1307.117310)`, însă nu pornesc
din componenta dealului; requery invers către seed se oprește la
`(2019.0, 1291.7)`, cu un gap de aproximativ `67.2` yards. O probă invalidă
(`corridor endpoint has no polygon`) a fost tratată ca lipsă de suprafață, nu
ca succes.

Rezultatul nu justifică relaxarea filtrului steep, un bridge geometric, un
waypoint hardcodat sau teleport. `RESET_REQUIRED`/`partial_local_navmesh_corridor`
rămâne verdictul fail-closed, iar testul live nu a fost pornit.

## ME-185 — Reconciliere explicită a aliasurilor Zygor–WorldMapArea

Compatibilitatea dintre etichetele LibRover din arhiva TBC Anniversary și
`WorldMapArea` legacy este acum într-un singur tabel read-only, comun pentru
auditul de route și NPCData. El acoperă doar identități de hartă (`Tirisfal
Glades`→`Tirisfal`, `The Barrens`→`Barrens`, `Darnassus`→`Darnassis` etc.), nu
waypoints și nu autoritate.

Auditul real rerulat pe arhiva locală raportează `62/66` map-area-uri rezolvate:
`22` exact și `40` prin normalizare/alias, `0` ambigue și `4` nerezolvate
(Black Temple și trei instanțe sintetice fără rând `WorldMapArea`). Rezultatul
rămâne content-minimal, iar coordonatele NPC statice nu devin poziții live.
Nu s-a instalat addonul, nu s-a reîncărcat WoW și nu s-a pornit input live.

## ME-186 — Revalidare semantică după compat layer

Validatorul profile-bound a fost rerulat offline și a scris
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v46.json`.
Toate cele patru trasee așteptate (Crypt→Brill, Deathknell→Brill,
Brill→Deathknell și Brill south-road) sunt `ARRIVE`; fixture-ul de deal rămâne
intenționat `RESET_REQUIRED`/`partial_local_navmesh_corridor`. Gate-ul indică
v46 cu `status=PASS`, dar `live_authority_enabled=false`; nu există autorizație
LAB sau runtime arm și nu s-a pornit test live.

## ME-187 — Query advisory pentru candidați statici NPC/trainer

`KnowledgeBrokerCatalog` expune acum `nearby_static_candidates(...)`, o
interogare deterministă pe `map_id + map_name + map_scope` și coordonate 2D
normalizate. Ea sortează candidații statici după distanță, confidence și
`entry_id`, filtrează explicit tipurile cerute și ignoră pozițiile din alte
scopuri. API-ul nu transformă datele în poziții live, nu creează destinații și
nu are autoritate de execuție; un adapter separat poate aplica ulterior o
transformare WorldMapArea validată pentru afișare/client-confirmation.

Testul dedicat trece și rămâne fail-closed pentru coordonate invalide sau
map-area greșit. Dynamic awareness continuă să folosească doar dovezi
viewport/nameplate; nu se pretinde localizarea exactă a tuturor unităților.
Control Center afișează acum și starea reconcilerii map-area în mod read-only.
Suita completă după această schimbare: `1323 passed`.

## ME-188 — Revalidare a frontierei cu worker și pack-uri alternative

Aceeași cerere bounded din fixture-ul dealului a fost rulată offline cu
worker-ele v34 și v35 și cu pack-urile locale v3, v4 candidate și
repair-source. Toate produc același stop `(2055.357422, 1240.476562)`,
`complete=false`, `steep_polygons_penalized=5617` și
`doodad_polygons_penalized=1356`. Reparația de payload existentă pentru tile-ul
`29_28` este deja prezentă în pack-urile testate, dar nu conectează componenta
dealului la drumul următor. Nu se adaugă shortcut geometric, teleport sau
waypoint; verdictul rămâne `RESET_REQUIRED`/`partial_local_navmesh_corridor`.

## ME-189 — Holdout live bounded și preplanare asincronă a pauzelor

Cu autorizație LAB proaspătă, runtime arm temporar și fără handoff de combat,
secvența identifier-only `settlement:brill -> landmark:deathknell-crypt`
a ajuns la ambele capete (`ARRIVED`) în
`data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-live.json`.
Rezultatul și cele două leg-uri navmesh păstrează `execution_authority=false`;
checkpoint-ul final arată Predator viu la Crypt, iar sesiunea a fost disarmată.

Evaluatorul strict trece returul fără goluri inexplicate
(`data/runtime/navigation-f3b/results/navmesh-roaming-442c898c-8517-481e-950c-fafe930e6640-quality.json`), dar outbound-ul
rămâne `passed=false`
(`data/runtime/navigation-f3b/results/navmesh-roaming-7442991d-70fa-439f-b189-133e69575b1b-quality.json`): gol inexplicat de `2.1296 s` la frontieră/static pivot și
gol de `1.2960 s` la recenter. Acestea explică opririle observate și nu sunt
mascate prin praguri mai largi.

Offline, runner-ul a primit două preplanări bounded în process-pool: bypass-ul
folosește numai celule ordonate din ruta semantică și navmesh-ul clientului, iar
recenter-ul se pregătește înainte de pragul strict. Un rezultat este aplicat
numai cu query/țintă/start încă valide; altfel se păstrează fallback-ul
fail-closed. Validatorul semantic v47 trece `5/5` cazuri așteptate
(`4×ARRIVE`, deal `RESET_REQUIRED`). Testele focalizate sunt `145/145`,
runtime/supervisor `98/98`, iar suita completă este `1325/1325`. Nu se pornește încă un test live până când
această poartă outbound nu este reverificată după o validare offline suplimentară.

## ME-190 — Holdout live v2 și prioritate offline pentru frontieră

Versiunea cu preplanare a ajuns din nou la Brill și apoi la Crypt (`ARRIVED`) în
`data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-live-v2.json`,
cu run-uri `8cbb021e-5880-4895-aa0b-005b6cfe0cee` și
`6fa3f7e0-0d39-4281-94f2-4b8808b39103`, zero handoff combat și
`execution_authority=false`. Sesiunea a fost disarmată imediat după verdict.

Returul trece quality gate (`6699` frames, fără goluri inexplicate). Outbound
are acum un singur gol inexplicat de `2.10225 s` la
`SEMANTIC_STATIC_FRONTIER_BYPASS`; recenter-ul este măsurat ca mișcare
continuă, chiar dacă intervalul brut este `1.3329 s`. Quality artifact-ul este
`data/runtime/navigation-f3b/results/navmesh-roaming-8cbb021e-5880-4895-aa0b-005b6cfe0cee-quality.json`.

După live v2, runner-ul a fost ajustat offline să prioritizeze worker-ul de
bypass când coridorul curent este parțial, fără coordonate inventate sau
relaxarea gate-ului. Testele focalizate sunt `244/244`, iar suita completă
`1326/1326`. Această prioritate nu este încă revalidată live; nu se pornește
alt test în acest ciclu.

## ME-191 — Pool dedicat pentru bypass-ul de frontieră

Pentru a elimina concurența reziduală dintre query-ul frontieră și baseline-uri,
runner-ul folosește acum un `ProcessPoolExecutor` separat, bounded la un worker,
pentru `_semantic_forward_bypass_in_worker_process`. Pool-ul nu are acces la
actuator și este închis explicit în teardown; rezultatul rămâne aplicabil numai
cu query/țintă/start valide. Compileall și testele focalizate trec `245/245`.
Această schimbare este offline și nu a fost încă revalidată live.

## ME-192 — Fan-out bounded pentru candidaturile de frontieră

În worker-ul dedicat, cel mult patru probe native rulează concurent pentru
orizontul de candidaturi bounded. Aplicarea păstrează strict prima candidatură
completă în ordinea rutei semantice, indiferent de ordinea terminării probelor.
Compileall și testele Movement Engine trec `147/147`; nu s-a pornit live după
această schimbare.

## ME-193 — Scanări continentale bounded continuate

Lotul offline Kalimdor a procesat încă 1.000 de seeds și a ajuns la
`9.139/40.794`, cu 211 observații WMO acceptate, 314 structuri finalizate și
zero erori. Agregarea strictă este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v9.json`
(`967` openings, `1.842` boundary chains). Expansion01 a ajuns la
`7.000/47.170`, cu 149 observații, 249 structuri și zero erori; agregarea
`partial-v7` are `429` openings și `1.070` boundary chains.
Ambele grafuri rămân `PARTIAL_OBSERVED_COMPONENTS`, nepromovate la autonomie;
nu s-a pornit input live.

## ME-194 — Holdout live după pool dedicat și fan-out bounded

Arhiva locală `D:\Downloads\Zygor Release 8.1.37070.rar` a fost verificată
read-only: SHA-256 `D8D416AD95F9071FD8578DF218A70235C377EA8B350F81CA2EA6F5417A65D2D3`,
root `ZygorGuidesViewerClassicTBCAnniv`, Interface `20506`, Version `8.1`,
868 fișiere și 83 directoare. Nu a fost extrasă și nu a fost copiată în repo.

Preflight-ul `live-v3` s-a oprit fail-closed la `CHARACTER_SELECT`, fără input
de mișcare. După checkpoint UI controlat `EnterWorld`, o singură rulare
efectivă bounded `Crypt -> Brill -> Crypt` a ajuns la ambele capete în
`data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-live-v4.json`;
run-urile sunt `0e23b788-fde8-4759-9494-85ae42f26515` și
`2b46aa01-b0c8-4ead-96bc-aae8c2f1907d`, zero combat handoffs și
`execution_authority=false`. Sesiunea a fost disarmată imediat după verdict.

Evaluatorul strict nu trece încă poarta temporală: outbound are 6 goluri brute,
3 compensate prin dovezi de mișcare continuă și 3 inexplicate (maxim
`2.554495 s`), iar returul are 2 brute, 1 compensat și 1 inexplicat (maxim
`0.366721 s`). Ambele leg-uri au `ARRIVED`, dar calitatea este `passed=false`
din cauza `control_observation_gap`; pool-ul dedicat și fan-out-ul nu sunt încă
dovedite ca eliminând pauza de frontieră. Nu se pornește o a doua rulare live;
următorul pas rămâne analiză offline a gap-urilor și a tranziției
`SEMANTIC_FRONTIER_REPLAN_REQUIRED`.

## ME-195 — Alinierea limitei worker-ului cu fereastra inclusivă de frontieră

Analiza offline a trace-ului v4 a identificat cauza exactă a golului de la
`1883.035767, 1583.333374`: helper-ul semantic a produs 9 candidaturi (extensie
de 8 celule plus celula obiectivului coalescat), iar worker-ul respingea orice
lot mai mare de 8. Future-ul devenea astfel invalid și caller-ul cădea pe query
sincron în bucla de control.

Worker-ul acceptă acum explicit cel mult 32 de candidaturi, păstrând fan-out-ul
la 10 query-uri native concurente și selecția deterministă în ordinea rutei.
Loturile peste limită rămân respinse; nu se introduc coordonate inventate,
teleport sau autoritate de execuție. Testele Movement Engine trec `149/149`, iar
regresia completă anterioară schimbării era `1328/1328`; full regression după
această corecție este `1329/1329`, înainte de orice poartă live.

## ME-196 — Fan-out frontieră calibrat offline pe batch-ul real

Worker-ul a fost rulat offline cu navmesh-ul local pinned, aceeași frontieră și
aceleași 10 candidaturi reconstruite din ruta Crypt→Brill. A returnat un coridor
complet (`route_index=18`) în `3.3 s` cu fan-out 4; repetarea cu fan-out 10 a
returnat același coridor în aproximativ `1.5 s`. Se păstrează selecția în ordinea
rutei, limita totală de 32 și lipsa autorității de execuție.

Testele Movement Engine și regresia completă rămân verzi (`150/150`, respectiv
`1330/1330`). Aceasta este dovadă offline pe WorldPack, nu revalidare live; nu
se pornește încă o nouă sesiune.

## ME-197 — Holdout live v5 după corecția ferestrei inclusive

După reînnoirea autorizației LAB, `EnterWorld` și checkpoint vizual `InWorld`,
o singură rulare live bounded `Crypt -> Brill -> Crypt` a ajuns la ambele
destinații în `data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-live-v5.json`.
Run-urile navmesh sunt `bdb4916c-b97d-4779-a91d-8cbcc3a2b62f` și
`4f0eb7b0-e029-488d-a3ba-c2de7e67997f`; ambele raportează `ARRIVED`, cu
`5987`/`6110` frame-uri, zero handoff-uri de combat și
`execution_authority=false`. ShadowPlay a fost toggled doar pe durata
holdout-ului și sesiunea a fost disarmată imediat după checkpoint-ul final.

Poarta temporală strictă încă nu trece: outbound are `15` goluri brute,
`13` compensate prin mișcare continuă și `2` inexplicate (`2.104445 s` maxim),
iar returul are `12` brute, `11` compensate și `1` inexplicat (`0.384832 s`
maxim). Ambele quality artifacts (`data/runtime/navigation-f3b/results/navmesh-roaming-bdb4916c-b97d-4779-a91d-8cbcc3a2b62f-quality.json`
și `...4f0eb7b0-e029-488d-a3ba-c2de7e67997f-quality.json`) sunt
`passed=false` doar pentru `control_observation_gap`; nu se declară încă
mișcare humanlike certificată și nu se pornește un alt live holdout.

Concluzia este progres funcțional, nu certificare: corecția workerului a
eliminat fail-ul de batch și ruta nu s-a blocat, însă rămân două ferestre
outbound în jurul pivotului/frontierei și o tranziție de retur care trebuie
explicate offline înainte de următoarea rulare.

## ME-198 — Păstrarea future-ului la replanul parțial (offline)

Trace-ul v5 a arătat că future-ul de bypass pornit la frontiera
`1883.035767, 1583.333374` era anulat la începutul ramurii de replan parțial,
înainte ca blocul de handoff să-i poată verifica starea. Asta explica de ce
v5 a căzut din nou pe `SEMANTIC_STATIC_FRONTIER_BYPASS` sincron, deși worker-ul
real fusese calibrat offline.

Runner-ul păstrează acum future-ul pornit de aceeași frontieră până la verificarea
de handoff; future-urile stale/incomplete rămân respinse fail-closed, iar
fallback-ul sincron este folosit numai dacă nu există rezultat valid. Regresia
dedicată este `151/151`, iar suita completă după amendament este `1331/1331`;
`py_compile` și `git diff --check` trec. Schimbarea nu a fost încă rulată live.

## ME-199 — Invalidează future-ul când replanul schimbă frontiera (offline)

Am închis și cazul limită opus: dacă replanul produce o frontieră diferită,
future-ul pregătit pentru frontiera veche nu mai rămâne în coadă pentru o
reutilizare accidentală. Runner-ul îl anulează explicit numai în această
ramură; pentru aceeași frontieră, verificarea de handoff are în continuare
prioritate. Testele Movement Engine rămân `151/151`, iar full regression este
`1331/1331`; `py_compile` trece. Nu s-a pornit un al doilea live.

## ME-200 — Benchmark offline hairpin după corecțiile frontieră

Benchmark-ul `data/runtime/movement-lab/adaptive-steering-benchmark-20260901-me199-1000.json`
a rulat `1.000` curse pentru fiecare dintre cele șase scenarii de curbe,
inclusiv `narrow_outdoor_hairpin`. Toate `6.000/6.000` curse au trecut quality,
cu `0` coliziuni și `0` curse incomplete; hairpin-ul a avut `0.484` fracție
MPPI activă, maxim cross-track `1.448` yards și maxim pivot `0.278`.
Este dovadă offline de steering, nu substituie poarta temporală live.

## ME-201 — Confirmare read-only a arhivei TBC Anniversary furnizate

Arhiva locală `D:\Downloads\Zygor Release 8.1.37070.rar` a fost reauditată
read-only în spațiu temporar, fără instalare, copiere în repo sau încărcare a
conținutului licențiat. Hash-ul SHA-256 rămâne
`D8D416AD95F9071FD8578DF218A70235C377EA8B350F81CA2EA6F5417A65D2D3`, root-ul
este `ZygorGuidesViewerClassicTBCAnniv`, iar TOC-ul declară Interface `20506`
și Version `8.1` pentru TBC Classic Anniversary; arhiva are `868` fișiere și
`83` directoare.

Cele șase fișiere non-Trial de leveling/professions se validează cu
`14.748` pași și `11.687` candidaturi de coordonate. `NPCData.lua` se
validează cu `35` secțiuni și `3.255` rânduri (`286` class trainers și `287`
profession trainers). Transformarea 2D pe catalogul client acoperă
`11.686/11.687` coordonate; singurul caz nerezolvat rămâne map ID `564`
(`BlackTemple`), fără row compatibil în catalogul auditat.

Toate cele trei artefacte existente (`guide-coverage`, `npcdata-audit` și
`route-transform-coverage`) trec `--check` împotriva acestei arhive. Datele
rămân advisory/local-only, cu `execution_authority=false`; nu se pornește
niciun test live nou.

## ME-202 — Regresie offline pentru invalidarea future-ului stale

Regresia Movement Engine verifică acum explicit și ramura în care replanul
mută frontiera: future-ul pregătit pentru topologia veche trebuie anulat, iar
fallback-ul nu poate consuma acel rezultat. Testele Movement Engine trec
`152/152`, iar suita completă trece `1332/1332`; `py_compile` și
`git diff --check` rămân verzi. Trace-ul live v5 nu este rescris și nu se
pornește un alt test live în acest ciclu.

## ME-203 — Readiness de profil legat de identitatea hărții (offline)

Selectorul Control Center nu mai tratează simpla existență a unui fișier ca
dovadă de capabilitate. `inspect_world_map_profile` validează acum, read-only,
tipul/schema și identitatea explicită a hărții în WorldPack runtime profile,
semantic catalog, structure index și structure access graph. Un artefact valid
pentru alt `map_id`/`internal_name` este respins și nu poate deschide poarta
AUTONOM; profilele partajate (de exemplu WorldPack-ul continentelor) sunt
acceptate numai dacă includ explicit harta selectată.

Regresia dedicată trece `156/156` împreună cu testele registry/audit, iar auditul
registry este regenerat și trece `--check`: `83` identități inventariate,
`4` hărți cu bake complet și `1` profil autonom-ready. Schimbarea este offline
și nu pornește un test live.

## ME-204 — Extindere advisory a scanării structurale Expansion01 (offline)

Am reluat scanarea bounded pentru candidaturile WMO din Expansion01 cu workerul
local verificat `pa_nav_probe-v35` (hash-ul cerut de plan), `500` probe noi,
`jobs=4` și awareness persistent. Raportul verificat este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v2.json`:
`8.000/47.170` seed-uri completate, `160` observații acceptate, `7.040`
respinse pentru structură neconfirmată, `647` fără nav polygon, `153`
awareness static incompletă, `0` probe errors și `39.170` seed-uri rămase.

Agregarea completed-tasks-only este în
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v8.json`:
`92` structuri distincte observate, `160` observații, `1.267` boundary chains
și `501` access openings. `coverage_state` rămâne
`PARTIAL_OBSERVED_COMPONENTS`, `dynamic_entity_knowledge=NONE` și
`execution_authority=false`; graful este advisory și nu a fost promovat în
registry/readiness. Nu s-a pornit test live și nu s-a atins clientul WoW.

## ME-205 — Prioritate redusă pentru worker-ele native read-only (offline)

Query-urile navmesh lansate de `ClientAssetNavmeshQuery` și serviciul persistent
de awareness folosesc acum `CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS`
atunci când platforma Windows expune aceste flag-uri. Worker-ele rămân procese
izolate, bounded și fără actuator, dar nu mai concurează la prioritate normală
cu ceasul DXGI de capture/control când preplanul de frontieră face cold tile
loads. Pe platforme de test flag-urile lipsă se reduc determinist la `0`.

Regresia focalizată este `239/239`, iar suita completă este `1.336/1.336`.
Validarea semantică offline v49 trece cele patru trasee (`ARRIVE`) și păstrează
fixture-ul de deal ca `RESET_REQUIRED`/`partial_local_navmesh_corridor`, cu
`execution_authority=false`. Aceasta este o măsură de scheduling offline;
nu rescrie quality gate-ul și nu constituie revalidare live. Nu s-a pornit test
live și nu s-a atins clientul WoW.

## ME-206 — Preflight live păstrat fail-closed după corecția offline

Gate-ul semantic curent este `PASS` pentru v49, dar declară explicit
`live_authority_enabled=false`. Preflight-ul read-only confirmă clientul WoW LAB
PID `53092` și listener-ele loopback așteptate, însă autorizația de sesiune și
receipt-ul de identitate au expirat, iar `runtime_arm_present=false`. Nu există
o sesiune live autorizată de reluat; nu s-a regenerat autorizația, nu s-a armat
runtime-ul și nu s-a trimis input.

## ME-207 — Reînnoire controlată, blocare vizuală și dezarmare (live gate)

La cererea explicită de a nu pierde progresul live, autorizația LAB a fost
reînnoită temporal pentru profilul fix `tbc_243_lab`, receipt-ul de identitate
și runtime-arm-ul au fost emise pentru clientul deja existent PID `53092`.
Acestea au rămas limitate la `LAB_OPERATOR_FIXED_UI`; `execution_authority`
al traseului semantic a rămas `false` și protecția de combat nu a fost activată.

Înainte de orice mișcare, captura/pose-ul read-only a returnat
`ClientVisibleStateError: DISCONNECTED_DIALOG` la confidence `0.532`.
Clientul nu era în world, deci nu exista dovadă pentru poziția Crypt și nu s-a
trimis niciun puls, comandă de mers sau combat handoff. Runtime-arm-ul a fost
dezarmat imediat; statusul final confirmă `runtime_arm_present=false`, iar
procesul WoW și Hermes nu au fost oprite sau modificate. Holdout-ul
`Crypt→Brill→Crypt` rămâne neexecutat în acest ciclu.

## ME-208 — Fast-path pentru primul bypass de frontieră (offline)

Trace-ul live v5 a arătat că celula de drum validă era prima candidatură din
ordinea semantică, dar worker-ul o lansa împreună cu toate probele speculative.
`ThreadPoolExecutor` aștepta apoi și probele rămase la ieșirea din context,
chiar după găsirea rezultatului valid; acest tail latency putea ține control
loop-ul fără observație la frontieră.

Worker-ul verifică acum prima candidatură separat și returnează imediat când
query-ul navmesh o validează. Fan-out-ul bounded rămâne neschimbat pentru
ramura în care prima candidatură e invalidă, cu selecție în ordinea routei și
teardown explicit al workerelor read-only. Regresia focalizată este `245/245`,
suita completă `1337/1337`, iar validarea semantică offline v50 este `PASS`
(`4×ARRIVE`, deal `RESET_REQUIRED`). Quality gate-ul temporal nu a fost
relaxat și această corecție nu a fost încă revalidată live.

## ME-209 — Warmup bounded al workerelor înainte de pose clock (offline)

Trace-ul live v6b a redus golul de frontieră la aproximativ `1.159 s`, dar a
arătat două intervale outbound inexplicate: unul la pornirea preplanului de
coridor și unul la aplicarea bypass-ului/recenter-ului. Procesele
`ProcessPoolExecutor` porneau lazy la primul `submit`, exact în timp ce bucla
de control ținea lease-ul de captură.

Runner-ul pornește acum toate cele cinci procese read-only (2 preplan, 2
advisory, 1 frontier) cu un no-op picklable bounded înainte de
`pose_source.open()`. Warmup-ul este fail-closed și nu are acces la client,
navmesh sau actuator; dacă un worker nu pornește la timp, nu se emite input.
Regresia focalizată este `247/247`, suita completă `1339/1339`, compileall
trece, iar validarea semantică offline v51 este `PASS` (`4×ARRIVE`, deal
`RESET_REQUIRED`).

## ME-210 — Holdout live v6b: sosire funcțională, poarta temporală încă eșuată

O singură sesiune bounded, fără `--structure-access-graph` (graful disponibil
era legat de worker v34, iar workerul curent este v35), a rulat secvența
identifier-only `Crypt -> Brill -> Crypt` în
`data/runtime/navigation-f3b/journey-combat-supervisor-live-priority-v6b-20260901.json`.
Ambele leg-uri au `ARRIVED`, Predator a revenit la Crypt, `combat_handoffs=0`
și `execution_authority=false`; runtime arm-ul a fost dezarmat imediat.

Outbound are `6.591` frame-uri, `262.416 s`, `5` gap-uri brute (`3` explicate
prin mișcare continuă, `2` inexplicate), maxim `1.551341 s`, iar quality
artifact-ul este `passed=false` doar pentru `control_observation_gap`.
Returul are `6.285` frame-uri, `254.852 s`, un gap de `0.300153 s` compensat
prin mișcare continuă și `passed=true`. Funcționalitatea de sosire este
confirmată, dar mișcarea humanlike nu este încă certificată și combatul nu se
promovează. Următorul pas este revalidarea offline a warmup-ului; nu se
pornește încă un alt test live în acest ciclu.

## ME-211 — Holdout live v7: outbound sosit, retur fail-closed la plecarea din Brill

Singura revalidare bounded permisă în acest ciclu a rulat secvența
identifier-only `Crypt -> Brill -> Crypt`, fără combat și fără graful structural
legat de workerul v34. Artefactul este
`data/runtime/navigation-f3b/journey-combat-supervisor-live-priority-v7-20260901.json`.
Outbound-ul a ajuns la Brill (`ARRIVED`), cu `ASYNC_WORKER_POOLS_WARMED` și
`combat_handoffs=0`. La începutul returului, însă, primele observații nu au
furnizat facing vizibil; controlul a intrat în `CALIBRATE_HEADING`, a emis
stride-ul natural legacy și a mers în direcția greșită. Recenter-ul a eșuat
fail-closed cu `CORRIDOR_RECENTER_REPLAN_BUDGET_EXHAUSTED`; nu s-a folosit
combat și nu s-a încercat o a doua sesiune live. Quality outbound v7 rămâne
`passed=false` pentru un gap temporal inexplicat (`1.266432 s` maxim), iar
returul este `passed=false` pentru `destination_not_reached`, pivot excesiv și
gap de observație. Runtime-ul a fost dezarmat imediat (`runtime_arm_present=false`).

## ME-212 — Reacquisition read-only pentru heading inițial (offline)

Runner-ul nu mai permite ca heading-ul inițial absent să ajungă la controller.
Înainte de primul input și după planificarea rutei, sunt cerute cel mult patru
observații fresh, fără controale ținute, până când apare facing-ul HUD exact sau
fallback-ul minimap cu provenance. Dacă heading-ul rămâne indisponibil,
sesiunea se oprește fail-closed cu `refusing natural calibration stride`; nu se
trimite `MOVE_FORWARD` doar pentru calibrare. Au fost adăugate teste pentru
reacquisition și pentru failure path; regresia focalizată este `249/249`, iar
suita completă este `1341/1341`, cu compileall și `git diff --check` verzi.
Nu s-a pornit live după această corecție.

## ME-213 — Materializarea rezultatului frontieră mutată înainte de handoff (offline)

Trace-ul v7 a localizat singurul gap outbound inexplicat la tranziția
frontieră: `PRECONTROL_POSE_REFRESHED` a raportat `1079.78 ms` după ce
rezultatul workerului era consumat în aceeași iterație cu handoff-ul. Runner-ul
consumă acum o singură dată rezultatul deja `done()` al workerului frontieră în
faza de preplan, cât coridorul curent este încă autoritativ; handoff-ul ulterior
folosește același `Future` materializat și nu schimbă ordinea candidaților sau
sursele de geometrie. Failure-ul workerului rămâne fail-closed. Regresia
focalizată este `250/250`, suita completă `1342/1342`, iar validarea semantică
offline v52 este `PASS` (`4×ARRIVE`, deal `RESET_REQUIRED`). Nu s-a pornit live
după această corecție; arm-ul rămâne absent și `OBSERVE_ONLY`.

## ME-214 — Reconfirmare read-only a pachetului Zygor Anniversary și a capabilităților Control Center

Arhiva locală `D:\Downloads\Zygor Release 8.1.37070.rar` este varianta
TBC Anniversary verificată: rădăcina este
`ZygorGuidesViewerClassicTBCAnniv`, TOC-ul declară `Interface: 20506`, titlul
`TBC Classic Anniversary`, versiunea `8.1`, iar SHA-256 este
`D8D416AD95F9071FD8578DF218A70235C377EA8B350F81CA2EA6F5417A65D2D3`.
Verificările reproducibile `--check` pe fișierele extrase temporar confirmă
artefactele content-minimal existente: `14.748` pași, `11.687` candidaturi de
coordonate și acoperire RouteTeacher pe hărțile `0:Azeroth`, `1:Kalimdor`,
`530:Expansion01` și `564:BlackTemple`; transformarea client-side este
`11.686/11.687`, cu singurul caz nerezolvat pe `564`.

Auditul Control Center confirmă că secvența semantică rămâne identifier-only,
bounded la `2–16` destinații și `1–32` repetări, cu `close_loop` opțional; fiecare
legătură este replănuită din poziția observată, iar testele supervisor/UI acoperă
tranzițiile și bucla închisă. Registry-ul expune `83` identități de hartă, dar
numai profilul Azeroth este `autonomous_ready`; Kalimdor, Expansion01,
Shadowfang și toate celelalte profiluri fără semantic/access complet rămân
`OBSERVE_ONLY` și nu pot porni. NPCData rămâne knowledge static read-only
(`3.255` intrări); dynamic awareness acceptă numai viewport/nameplate
screen-space, fără coordonate 3D inventate.

Nu s-a instalat addonul, nu s-a reîncărcat WoW și nu s-a pornit test live după
această reconfirmare; runtime-ul rămâne `OBSERVE_ONLY`, iar următorul pas este
promovarea separată a artefactelor semantic/access pentru hărțile candidate,
nu folosirea directă a payload-ului licențiat ca rută executabilă.

## ME-215 — Aliniere offline worker–graph și regresie completă

Validatorul semantic a fost rerulat fără input pe WorldPack-ul Azeroth v3 cu
workerul `pa_nav_probe-v34`, aceeași versiune declarată de graful structural
existent. Rezultatul
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v53-worker-v34.json`
este `PASS`: cele patru cazuri Crypt/Deathknell/Brill ajung la destinație, iar
fixture-ul de deal rămâne `RESET_REQUIRED` cu
`partial_local_navmesh_corridor`. Gate-ul offline rebondat păstrează
`live_authority_enabled=false` și `execution_authority=false`.

Serviciul read-only de structure awareness a pornit și a raportat `READY` cu
`96.024` structuri (`1.509` WMO, `94.515` doodad) și `4.754` access openings;
hash-ul workerului v34 coincide cu identitatea grafului. Regresia completă
este `1342/1342`, iar `compileall` și `git diff --check` rămân curate.
Aceasta închide inconsistența de versiune offline, nu deschide poarta live:
nu s-a reautorizat LAB, nu există runtime arm și nu s-a trimis input.

## ME-216 — Scanări candidate continentale continuate (offline)

Au fost rulate două loturi read-only bounded, fiecare de `1.000` probe, pe
WorldPack-urile candidate și workerul v35: Kalimdor a ajuns la `10.639/40.794`
seed-uri (`229` acceptate, `0` erori), iar Expansion01 la `9.000/47.170`
(`176` acceptate, `0` erori). Rapoartele de progres sunt
`kalimdor-candidate-structure-access-scan-progress-v2.json` și
`expansion01-candidate-structure-access-scan-progress-v3.json`.

Agregările strict `completed-tasks-only` au produs grafurile candidate
`kalimdor-candidate-structure-access-partial-v11.json` și
`expansion01-candidate-structure-access-partial-v9.json`, ambele cu starea
`PARTIAL_OBSERVED_COMPONENTS` (`1.082`/`608` access openings). Acestea sunt
probe locale de structură/BVH/navmesh, nu semantic catalogs și nu acordă
autonomie; au fost legate în registry doar ca dovezi read-only pentru
structure awareness, fără modificarea gate-ului live.

## ME-217 — Registry map-bound pentru awareness continental (offline)

Grafurile candidate și indexurile Kalimdor/Expansion01 sunt acum referite
explicit de registry-ul `world-map-registry-tbc243.json`, astfel încât
Control Center poate încărca awareness structural read-only pe hărțile cu
dovezi locale. Această legare nu adaugă semantic catalogs: auditul păstrează
`autonomous_ready_map_count=1`, doar Azeroth, iar cele două continente rămân
`OBSERVE_ONLY` și fail-closed pentru rutare.

Decizia și rollback-ul sunt consemnate în
`docs/adr/0074-candidate-structure-evidence-in-map-registry.md`; testele de
registry verifică separat că indexul/graful sunt identity-bound și că lipsa
catalogului semantic ține autonomia închisă.

## ME-218 — Selecție worker după identitatea grafului (offline)

Control Center nu mai pornește structure-awareness cu workerul global în mod
implicit. Pentru fiecare profil, citește doar `probe_worker_sha256` din graful
deja declarat și selectează exclusiv workerul local allowlisted v34 sau v35
care are hash identic. Un graph modificat sau un hash necunoscut oprește
serviciul fail-closed; nu poate introduce o cale executabilă arbitrară.

Regresia completă după această corecție este `1343/1343`, testul nou acoperă
Azeroth + Kalimdor + Expansion01 și cazul de hash forjat, iar `compileall`
trece. Această schimbare face utilizabile doar query-urile read-only pentru
grafurile candidate; semantic gate-ul și input authority rămân închise.

## ME-219 — Lot Kalimdor v12 și stare curentă a acoperirii candidate (offline)

Al doilea lot bounded Kalimdor a fost rulat read-only cu profilul WorldPack
dedicat și workerul allowlisted v35 (`1.000` probe, `jobs=4`, awareness
persistent). Raportul curent
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v3.json`
are `11.639/40.794` seed-uri completate, `250` observații acceptate, `0`
erori de worker, `401` structuri complete și `29.155` seed-uri rămase.

Agregarea `data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v12.json`
are `250` observații, `1.204` access openings și `2.269` boundary chains;
`coverage_state` rămâne `PARTIAL_OBSERVED_COMPONENTS`, iar hash-ul de conținut
este `4a2918ad8555687d599d7894fab1998c3a2c52e00df79df89f095137c8569029`.
Registry-ul indică acum v12 numai pentru awareness structural read-only. Nu
există semantic catalog pentru Kalimdor, deci auditul păstrează
`autonomous_ready_map_count=1` (Azeroth), iar runtime-ul și live input-ul
rămân `OBSERVE_ONLY`/absente.

## ME-220 — Lot Expansion01 v10 și stare curentă a acoperirii candidate (offline)

Un lot bounded read-only pe profilul comun WorldPack pentru Expansion01 a rulat
cu workerul allowlisted v35 (`1.000` probe, `jobs=4`, awareness persistent).
Raportul curent
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v4.json`
are `10.000/47.170` seed-uri completate, `196` observații acceptate, `0`
erori de worker, `352` structuri complete și `37.170` seed-uri rămase.

Agregarea strictă
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v10.json`
are `196` observații, `728` access openings și `1.764` boundary chains;
`coverage_state` rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu hash
`9de91e04296bfee8f293d0aa8872e2aa500a8bc7034174a541c823f17d8f9b44`.
Registry-ul indică v10 doar pentru awareness structural read-only; semantic
catalogul lipsește, deci Expansion01 rămâne `OBSERVE_ONLY` și nu poate porni
autonomie sau input.

## ME-221 — Lot Kalimdor v13 și stare curentă a acoperirii candidate (offline)

Un nou lot bounded read-only Kalimdor a rulat cu profilul candidat și workerul
allowlisted v35 (`1.000` probe, `jobs=4`, awareness persistent). Raportul curent
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v4.json`
are `12.639/40.794` seed-uri completate, `290` observații acceptate, `0` erori
de worker, `437` structuri complete și `28.155` seed-uri rămase.

Agregarea strictă
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v13.json`
are `290` observații, `1.285` access openings și `2.466` boundary chains;
`coverage_state` este în continuare `PARTIAL_OBSERVED_COMPONENTS`, cu hash
`cdd9f14a4e5706bd74c92d1baf1ffb9b04da306ac4c385067dbaa85e5b8ced91`.
Registry-ul indică v13 exclusiv pentru awareness structural read-only; lipsa
catalogului semantic ține Kalimdor `OBSERVE_ONLY`, fără autonomie sau input.

## ME-222 — Lot Expansion01 v11 și reconfirmare read-only a addonului (offline)

Un nou lot bounded read-only Expansion01 a rulat cu profilul comun WorldPack și
workerul allowlisted v35 (`1.000` probe, `jobs=4`, awareness persistent). Raportul
curent are `11.000/47.170` seed-uri completate, `217` observații acceptate și
`0` erori de worker; rămân `36.170` seed-uri.

Agregarea strictă `completed-tasks-only`
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v11.json`
are `217` observații, `843` access openings și `1.958` boundary chains; starea
este `PARTIAL_OBSERVED_COMPONENTS`, cu hash
`b32eb73314950bf597a1018140d5adb3af7bc22e94a7fcd654719f46f99973dd`.
Registry-ul indică v11 doar pentru awareness structural read-only; Expansion01
rămâne `OBSERVE_ONLY`, deoarece catalogul semantic lipsește.

RAR-ul Anniversary local a fost retestat read-only: SHA-256
`D8D416AD95F9071FD8578DF218A70235C377EA8B350F81CA2EA6F5417A65D2D3`, RAR5,
`868` fișiere, `83` directoare, `Everything is Ok`. Nu s-a instalat addonul,
nu s-a reîncărcat WoW și nu s-a pornit test live.

## ME-223 — Indexuri structurale pentru Razorfen/Karazhan și validare semantică v54 (offline)

Din proof WorldPack v3 au fost generate indexuri structurale identity-bound pentru
`RazorfenKraulInstance` (`395` structuri: `5` WMO, `390` doodads, `6` tile-uri)
și `Karazahn` (`5.449` structuri: `60` WMO, `5.389` doodads, `9` tile-uri).
Registry-ul le referă acum doar pentru awareness static read-only; access graph-ul
și catalogul semantic lipsesc, deci ambele rămân `OBSERVE_ONLY`.

Validatorul semantic Azeroth v54, rulat cu workerul v34 și WorldPack-ul pinned,
este `PASS`: Crypt→Brill, Deathknell→Brill, Brill→Deathknell și Brill→South
Road Bend ajung; fixture-ul de deal rămâne `RESET_REQUIRED` fail-closed.
Artefactul este
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v54-worker-v34.json`.
Auditul registry și testele dedicate trec; live-ul rămâne neautorizat și neînceput.

## ME-224 — Regresie completă după indexurile multi-map (offline)

Suita completă offline a trecut `1343/1343` în `119.63s`; `compileall` și
`git diff --check` rămân verzi. Rezultatul confirmă că indexurile noi și
actualizarea registry-ului nu au schimbat gate-ul semantic sau autoritatea de
input. Nu s-a pornit test live.

## ME-225 — Access scan interior pentru Karazhan și frontieră Razorfen (offline)

Scanarea completă Karazhan a terminat `1.662/1.662` seed-uri, cu `65` observații
acceptate, `0` erori și `124` cazuri fără poligon navmesh. Graful v2
`data/runtime/navigation-f3b/karazahn-proof-v3-structure-access-partial-v2.json`
are `116` openings și `315` boundary chains, rămâne
`PARTIAL_OBSERVED_COMPONENTS` și este legat în registry numai pentru awareness
read-only.

Scanarea completă Razorfen a terminat `147/147` seed-uri, `0` erori, dar `0`
WMO confirmate (`18` fără poligon). Raportul păstrează explicit starea fără
graph, pentru a nu inventa egress sau a promova o frontieră neacoperită.
Karazhan și Razorfen nu au catalog semantic; ambele rămân `OBSERVE_ONLY`.

## ME-226 — Regresie completă după graph-ul Karazhan v2 (offline)

Suita completă offline a trecut din nou `1343/1343` în `118.94s`. `compileall`
și `git diff --check` sunt curate; legarea graph-ului Karazhan nu a deschis
autonomia sau input authority. Nu s-a pornit live.

## ME-227 — Extindere candidate Kalimdor/Expansion01 și graph-uri read-only (offline)

Un lot bounded suplimentar de câte `1.000` probe, cu workerul allowlisted v35,
a dus Kalimdor la `13.639/40.794` seed-uri (`313` observații acceptate,
`0` erori) și Expansion01 la `12.000/47.170` (`247` observații acceptate,
`0` erori). Agregările strict `completed-tasks-only` sunt
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v14.json`
(`1.373` openings, `2.632` boundary chains) și
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v12.json`
(`994` openings, `2.289` boundary chains); ambele rămân
`PARTIAL_OBSERVED_COMPONENTS`.

Registry-ul indică aceste versiuni numai pentru awareness structural
read-only. Lipsa cataloagelor semantice ține în continuare ambele continente
`OBSERVE_ONLY`, iar auditul rămâne la `1/83` hărți `autonomous_ready`.
Nu s-a reînnoit autorizația, nu există runtime arm și nu s-a pornit live sau
nu s-a atins WoW/Hermes.

## ME-228 — Gate semantic v55 după extinderea multi-map (offline)

Validatorul semantic rulat cu workerul v34 și WorldPack-ul Azeroth pinned a
închis cu `PASS`: Crypt→Brill, Deathknell→Brill, Brill→Deathknell și Brill→South
Road Bend sunt `ARRIVE`; fixture-ul de deal rămâne
`RESET_REQUIRED`/`partial_local_navmesh_corridor`. Artefactul este
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v55-worker-v34.json`.
Nu s-a schimbat semantic gate-ul live, nu există runtime arm și nu s-a pornit
input live.

## ME-229 — Comparație offline pentru mers fără A/D

La cererea operatorului a fost comparată varianta actuală cu o variantă de
simulare care păstrează doar `MOVE_FORWARD` și virarea camerei prin RMB, fără
`STRAFE_LEFT`/`STRAFE_RIGHT`. Pe cele șase forme sintetice folosite pentru
curbe înguste, pod, poartă cu doodad și hairpin, fiecare variantă a trecut
`1.000/1.000` probe pe scenariu, fără coliziuni. Varianta actuală a emis
`1.695` cadre de strafe în total; varianta camera-only a emis `0`.

Aceasta este o comparație kinematică offline, nu dovadă pentru Crypt→Brill în
client. Nu am schimbat profilul de producție și nu am pornit live; rezultatul
arată că merită un singur test bounded ulterior cu profil camera-only, după o
nouă autorizație și runtime arm.

## ME-230 — Test live bounded camera-only oprit în siguranță

Am reînnoit autorizația pentru LAB-ul local și am pornit un singur test scurt.
Predator era în Brill. Controllerul a ținut W și a întors camera; nu a folosit
A/D. Testul s-a oprit singur înainte de prima destinație, deoarece clientul a
văzut obstacolul confirmat `obstacle:60812e3b1d58cfc5`, iar sistemul nu avea un
ocol validat. Nu s-a forțat trecerea și nu s-a folosit server truth.

Rezultatul este `STOPPED_CHILD_ERROR`, în
`data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-v39-camera-only.json`.
Nu avem sosire, nici handoff de combat. Asta este un eșec sigur, nu o moarte și
nu o dovadă că ruta completă merge. ShadowPlay a lăsat o înregistrare locală de
`180` secunde, aproximativ `1,069,027,610` bytes, în folderul Videos al
operatorului; clipul nu este în repo.

După oprire, Predator a rămas în Brill. Nu am oprit WoW sau Hermes. Nu pornesc
alt test live fără o regulă clară pentru acest obstacol.

## ME-231 — Ocolul mic nu mai este respins prea devreme

Verificarea offline a arătat cauza opririi v39: ocolul calculat din geometria
obstacolului avea o curbă puțin mai lungă decât regula veche. Regula acceptă
acum o margine mică, calculată din raza obstacolului și limitată strict. Nu se
acceptă ocoluri mari și nu se adaugă coordonate fixe.

Am folosit aceeași margine pentru ocolurile de structuri, pentru obstacolele
învățate și pentru recuperarea după o coliziune. Testul nou verifică explicit
un arc mai lung, dar încă limitat. Suita completă este `1344/1344`.

## ME-232 — Gate semantic v56 după repararea ocolului (offline)

Validatorul WorldPack/navmesh a trecut `PASS` pentru Crypt→Brill,
Deathknell→Brill, Brill→Deathknell și Brill→South Road Bend. Cazul artificial
de deal rămâne `RESET_REQUIRED`, cum trebuie. Artefactul este
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v56-obstacle-prior.json`.

La poziția observată în joc, ocolul pentru `obstacle:60812e3b1d58cfc5` este acum
`CONFIRMED_CLEARANCE_PRIOR_APPLIED` și trece cele trei verificări navmesh.
Acesta este gate offline; nu este încă dovadă live.

## ME-233 — Live v40 s-a oprit la primul obstacol local din Brill

După gate-ul offline v56 am pornit un singur holdout bounded camera-only,
`Brill -> Deathknell Crypt`, cu `W` + RMB și fără A/D. Rezultatul este
`data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-v40-camera-only.json`.
Predator nu a intrat în criptă: a mers aproximativ 12 yd, apoi a rămas lângă
intersecția din Brill. Copilul navmesh are `STUCK_REPLAN_REQUIRED`, `463`
cadre, `4` recuperări și `0` obiective semantice completate.

Clientul a raportat obstacole vizibile lângă lampă, grajd și fermă; pozițiile
lor se potrivesc cu structurile din WorldPack. Ocolurile locale au fost
încercate, dar fiecare a intrat din nou în aceeași concavitate. Motorul a
oprit fail-closed, fără forțare și fără combat. `execution_authority=false`.

Filmarea locală `C:\\Users\\LabUser\\Videos\\NVIDIA\\Wow.exe\\Wow.exe
2026.09.01 - 14.25.36.89.mp4` arată camera ridicată spre cer după blocare.
Trace-ul are `mouse_delta_y=0` și `mouse_velocity_y=0`; deci nu am trimis
comandă verticală. Ridicarea este o inferență compatibilă cu Smart Pivot-ul
clientului (`cameraPivot=1`) când camera este lipită de geometrie. Vederea a
fost readusă prin slotul salvat al operatorului. Nu s-a pornit un al doilea
live și nu s-au oprit WoW sau Hermes.

Acest rezultat explică oprirea, dar nu rezolvă încă ieșirea din Brill. Următorul
pas trebuie să fie offline: o regulă care alege un coridor structural liber
înainte de prima mișcare și o protecție pentru camera exterioară. Abia după
testele locale se poate cere un alt live bounded.

## ME-234 — Camera de exterior nu mai folosește Smart Pivot

După v40 am separat profilul camerei după tipul scenei. La exterior,
`cameraPivot=0`, ca o lampă, căruță sau clădire să nu poată ridica vizual
camera spre cer când Predator stă lipit de ea. Într-un WMO verificat,
`cameraPivot=1` rămâne permis pentru a ajuta vederea în interior.

Schimbarea este în `send_input_backend.py` și este acoperită de testul pentru
profilul exterior. Testele camerei sunt `36/36`, iar suita offline completă este
`1345/1345`. Nu s-a pornit un nou test live.

## ME-235 — Coridorul de început este reîmprospătat după alegerea podelei

Verificarea offline a arătat de ce primul coridor din Brill putea fi prea scurt:
structura stabilă de lângă ieșire era filtrată când căutarea pornea cu înălțimea
generică `z=100`. După ce WorldPack alege podeaua clientului (`z≈34`), runnerul
reia scanarea statică pentru primele obiective și adaugă doar structurile locale
confirmate din WorldPack. Nu s-au adăugat coordonate fixe sau waypoints.

În proba exactă Brill→Crypt, scanarea a adăugat un singur blocator stabil,
coridorul a crescut la `41` puncte de ghidare și query-ul navmesh a devenit
`complete=true`. Gate-ul semantic v57 este `PASS` pentru cele patru drumuri
reale, iar dealul rămâne `RESET_REQUIRED`. Artefactul este
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v57-layer-refresh.json`.
Suita completă după această schimbare este `1346/1346`.

## ME-236 — Camera home nu mai reactivează Smart Pivot afară

Am găsit o a doua cale care putea ridica privirea: după o recuperare de cameră,
`SetView(3)` seta din nou `cameraPivot=1`. Acum recuperarea exterioară setează
`cameraPivot=0`; interiorul WMO îl poate cere explicit. Captura după recuperare
arată Predator în Brill, viu, cu vederea pe drum:
`data/runtime/operator/20260901T120441210Z-manual-checkpoint.png`.

Testele țintite pentru input, cameră și motor au fost `200/200`, iar suita
completă este `1348/1348`. Nu am pornit o rută live nouă și nu am schimbat poziția lui
Predator.

## ME-237 — Filmarea live confirmă că Smart Pivot ridică și camera din Crypt

Am verificat filmarea locală a holdout-ului v42:
`C:\\Users\\LabUser\\Videos\\NVIDIA\\Wow.exe\\Wow.exe 2026.09.01 - 15.15.20.91.mp4`.
La început vederea este normală. Când Predator atinge pereții din interiorul
Crypt-ului, camera se înclină până privește tavanul/cerul, deși trace-ul nu
trimite mișcare verticală. Asta confirmă în client că `cameraPivot=1` nu este
sigur nici în WMO.

Am schimbat regula: toate profilurile de navigare țin `cameraPivot=0`; numai
vederea salvată a operatorului controlează înălțimea și înclinarea. Opțiunea
explicită rămâne disponibilă doar pentru diagnostic, nu pentru mers autonom.
Testele țintite sunt `200/200`; nu pornesc încă un live doar pentru cameră.

În același holdout, camera reparată nu schimbă cauza principală de mers:
v42 a ajuns în Crypt, apoi s-a oprit fail-closed la ieșirea de pe podeaua
interioară (`STUCK_REPLAN_REQUIRED`), fără combat și fără moarte.

## ME-238 — Pornirea în spațiu îngust aliniază direcția înainte de W (offline)

Trace-ul v42 arată că primul coridor din Crypt era valid în WorldPack, dar
controllerul `continuous_trajectory_v1` a început să țină W imediat. În testul
istoric care a reușit, Predator a rotit camera pe loc înainte să meargă.

Am adăugat o regulă generică: când coridorul începe într-un WMO sau pe un traseu
cu ocol de doodad, iar unghiul către prima tangentă este încă mare, controllerul
ține doar RMB și nu ține W. După ce unghiul intră într-o fereastră mică, W este
permis. Regula folosește doar `start_awareness`/geometria navmesh; nu are nume de
zonă, coordonate sau waypoint hardcodat.

Testul nou reproduce cazul cu ocol de doodad și verifică `PIVOT` înainte de
`FOLLOW`. Testele țintite sunt `169/169`; nu s-a pornit un live nou.
Suita offline completă este `1349/1349`; `compileall` a trecut.

## ME-239 — Live v43 confirmă reluarea greșită a alinierii

După gate-ul offline v57 și protecția camerei, am pornit un singur holdout
bounded `Crypt -> Brill -> Crypt`, cu protecția de combat oprită și cu zero
handoff-uri de combat permise. Predator a ajuns deja la Crypt, apoi pasul
Crypt→Brill s-a oprit fail-closed după `624` cadre, la aproximativ
`[1672.7381, 1691.1194]`. Nu a murit și nu s-a folosit server truth.

Trace-ul arată că prima aliniere a intrat corect în `PIVOT` fără W, dar
controllerul a reactivat aceeași regulă după câteva cadre cu mișcare mică.
Astfel a rămas în pivot și a consumat recuperările locale. Rezultatul live
este `data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-v43-precision-start.json`;
copilul este `data/runtime/navigation-f3b/results/navmesh-roaming-945cd6e3-e7cb-4efb-b14a-39dc7b417b7a.json`.

Am reparat offline starea controllerului: după ce prima aliniere intră în
fereastra mică, ea este marcată completă pentru acel coridor și nu pornește
din nou la zgomotul minimap-ului. Testul sintetic verifică și un cadru ulterior
cu zgomot; suita completă este `1349/1349`, iar `compileall` trece.

Clipul ShadowPlay pornit pentru v43 are `0` bytes și nu este dovadă video.
Nu pornesc încă un live; următorul pas este doar revizuirea offline a
trace-ului și a regulii de recenter.

## ME-240 — Gate offline după repararea alinierii

Am rulat `1.000` de probe pentru fiecare dintre cele șase forme de drum
(spațiu îngust, curbă în S, hairpin, pod și ocol de doodad). Toate au trecut
fără coliziuni, fără eșecuri și fără probe de calitate respinse. Raportul este
`data/runtime/navigation-f3b/steering-monte-carlo-20260901-v44-precision-gate.json`.

Validatorul WorldPack/navmesh v58 a trecut `PASS`: Crypt spawn→Brill,
Deathknell→Brill, Brill→Deathknell și Brill→South Road Bend sunt `ARRIVE`,
iar dealul rămâne corect `RESET_REQUIRED`. Artefactul este
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v58-precision-gate.json`.

Acestea sunt dovezi offline. Ele nu certifică încă mersul în client după
patch-ul de aliniere; următorul live trebuie să rămână unul singur, bounded,
cu combat handoff oprit până când bucla Crypt→Brill→Crypt ajunge fără blocaj.

Auditul registrului de hărți a găsit `83/83` identități din clientul TBC
2.4.3.8606 și le expune în Control Center. Doar Azeroth are acum toate
artefactele pentru `autonomous_ready`; celelalte hărți rămân read-only sau
`OBSERVE_ONLY` până când există WorldPack/navmesh și catalog semantic verificate.
Artefactul este `data/runtime/navigation-f3b/world-map-registry-audit-20260901-v44.json`.
Nu inventăm poziții pentru hărțile care nu au dovezi locale.

## ME-242 — Camera este refăcută după oprirea mersului

În live v45 filmarea a rămas normală în timpul mersului, dar captura făcută
după oprirea fail-closed privea podeaua/tavanul. Trace-ul nu are mișcare
verticală de mouse. Cauza probabilă este coliziunea camerei din client, iar
profilul WMO de la final nu chema vederea salvată.

Runnerul eliberează acum toate tastele și apoi reapelează `SetView(3)` cu
`cameraPivot=0`, dacă oprirea nu a fost o preluare manuală. Evenimentul este
`TERMINAL_CAMERA_HOME_RESTORED`; dacă această reparare nu reușește, mersul
rămâne fail-closed. Testul țintit este `201/201` după patch. Nu pornesc încă un
live nou până când verificarea offline rămâne verde.

Am executat doar recuperarea separată a camerei, nu o rută: rezultatul a fost
`OPERATOR_CAMERA_VIEW_RESTORED`, iar captura confirmă vederea normală în
`data/runtime/operator/20260901T135103904Z-manual-checkpoint.png`. Predator a
rămas în Crypt și nu a primit W, A/D sau combat.

## ME-243 — Minimap fallback nu mai poate întoarce direcția după primul cadru

Trace-ul v45 arată o problemă separată de cameră: în lipsa unui facing exact
din client, markerul mic din minimapă a sărit la cealaltă parte a aceleiași axe.
Fuziunea veche a ales acel capăt după predicția mouse-ului și a lăsat W să
pornească în sensul opus coridorului Crypt-ului.

Runnerul păstrează acum heading-ul integrat de mouse după prima citire a
minimapei. O deplasare reală poate corecta heading-ul doar când markerul și
vectorul de deplasare sunt de acord în limita `0.75` radiani; un vector care nu
se potrivește rămâne doar dovadă de alunecare/diagnostic. Facing-ul exact din
HUD rămâne prioritar când există.

Schimbarea nu are coordonate sau waypoints hardcodate și nu dă autoritate nouă
de input. Testele țintite acoperă saltul de 180°, corecția confirmată și
vectorul contradictoriu. Suita completă după patch este `1352/1352`,
`compileall` trece, simularea are `1000/1000` pentru fiecare din cele șase
forme de drum, iar validatorul semantic v58 rămâne `PASS`. Auditul registrului
confirmă `83/83` hărți cunoscute și o singură hartă `autonomous_ready`.
Artefactul Monte Carlo este
`data/runtime/navigation-f3b/steering-monte-carlo-20260901-v45-heading-fallback.json`.
Nu pornesc încă un live; trace-ul v45 este doar reanalizat offline cu regula
nouă.

## ME-244 — Camera veche este refăcută înainte de primul W

Filmarea holdout-ului v47 începe cu vederea deja înclinată spre tavan. Trace-ul
nu are mișcare verticală, iar camera revine la normal mai târziu; asta arată că
un test nou putea porni cu starea stricată lăsată de testul anterior. Oprirea
Smart Pivot nu schimbă pitch-ul deja memorat de client.

Runnerul reface acum `SetView(3)` cu `cameraPivot=0` imediat după `/stand` și
înainte de orice W. Evenimentul este `START_CAMERA_HOME_RESTORED`. Astfel prima
observație de traseu pornește cu vederea operatorului verificată, fără pitch
inventat și fără input vertical. Restaurarea de la final rămâne activă.

Schimbarea este verificată offline prin testul de ordine al pornirii; nu am
pornit un live nou după această schimbare.

## ME-245 — v47 a rulat fără access graph

În trace-ul v47, `structure_access_graph_id` este `null`, deși Control Center
are graful complet Azeroth. Comanda manuală a testului nu a transmis opțiunea
`--structure-access-graph`, așa că runnerul a avut doar scanarea locală și nu a
putut transforma poarta Crypt-ului într-un subobiect de ieșire. Verificarea
offline a grafului confirmă poarta observată `access:7bb73baa2ccf348bb33511f2`
și traseul ei valid către exterior.

Acesta este un test configurat incomplet, nu o dovadă că poarta nu funcționează.
Următorul live bounded va folosi graful sigilat din catalog, va păstra camera
refăcută la pornire, `maximum-combat-handoffs=0` și limita veche de cadre.

## ME-246 — Camera rămâne dreaptă când o poză întârzie

Live-ul v48 a pornit cu camera normală și a scris `START_CAMERA_HOME_RESTORED`.
Predator a rămas viu, fără combat și fără A/D. Graful porții a fost folosit și
a scris `STRUCTURE_EGRESS_PLANNED`, dar pasul Crypt→Brill s-a oprit după `900`
de cadre la `CONTROL_FRAME_BUDGET_EXHAUSTED`; deci ruta nu este încă validată.

Trace-ul a găsit o întârziere de aproximativ `6` secunde între două poze ale
clientului. Codul folosea din greșeală acea întreagă perioadă ca și cum RMB ar
fi rămas activ. Acum direcția mouse-ului poate fi calculată cel mult pentru
fereastra de siguranță de `450 ms`, iar evenimentul
`MOUSE_HEADING_INTEGRATION_CLAMPED` păstrează dovada întârzierii. Un vector de
deplasare nu mai schimbă direcția integrată decât dacă se potrivește și cu
direcția veche, și cu markerul minimapei.

Testele țintite sunt `268/268`, iar suita offline completă este `1354/1354`.
Nu activăm combatul și nu declarăm mersul Crypt→Brill reușit până când un nou
live bounded trece aceeași rută fără buget consumat.

## ME-247 — v49 găsește direcția inițială greșită după reset

Al doilea live după frâna de captură a folosit graful corect și a început cu
`START_CAMERA_HOME_RESTORED`. Vederea nu a mai urcat la cer și trace-ul nu are
mouse vertical. Totuși, după resetul la spawn, primul vector vizibil a mers
spre est, iar poarta validată către exterior cerea vest. Runnerul a observat
coliziuni, a încercat patru recuperări și a oprit fail-closed la `474` cadre,
cu `STUCK_REPLAN_REQUIRED`; combatul a rămas la `0` handoff-uri.

Frâna nouă nu a fost declanșată în acest trace, deci cauza este separată:
markerul minimapei nu dovedește că vederea salvată și direcția reală a lui
Predator sunt aliniate după un reset. Următorul pas este offline: un mic test
de calibrare care compară primul vector de deplasare cu tangenta coridorului,
înainte de a lăsa mersul să continue. Nu folosim coordonate de server și nu
facem încă un live pentru această idee.

## ME-248 — Verificare manuală a camerei după v49

Poza live de la `2026-09-01 18:13` nu arată cerul. Camera este însă lipită de
un zid, iar modelul lui Predator este aproape transparent. Asta este o
coliziune vizuală rămasă din poziția unde v49 s-a oprit, nu o comandă de mouse
verticală.

Am trimis o singură recuperare bounded: `/stand` și `SetView(3)` cu
`cameraPivot=0`. Nu am trimis W, A/D sau combat și nu am pornit o rută nouă.
Captura este
`data/runtime/operator/20260901T151420289Z-manual-checkpoint.png`. Camera nu
mai privește cerul; pentru o vedere completă trebuie mai întâi să scoatem
Predator din contactul cu zidul într-un pas separat, după gate-ul offline de
calibrare.

## ME-249 — Calibrare offline a direcției după reset

Pentru problema v49 am adăugat o probă generică la începutul fiecărui coridor.
După primul chord real de mers, runnerul compară vectorul observat cu tangenta
coridorului. Un chord opus, dar încă aproape de coridor, schimbă doar estimarea
de heading și lasă următorul tick să facă pivotul normal fără W. Un chord care
arată ca alunecare pe zid este păstrat `UNSAFE` și nu schimbă direcția.

Proba se rearmează la fiecare coridor nou sau handoff semantic. Facing-ul exact
din HUD rămâne prioritar. Nu sunt folosite coordonate de Cryptă, server truth,
waypoints noi sau combat.

Verificarea offline a trecut `1358/1358` teste, `compileall` și `git diff
--check`. Simularea mare a trecut `6000/6000` probe pentru cele șase forme de
drum, fără coliziuni și cu calitate `100%`. Validatorul WorldPack/navmesh a
trecut din nou Crypt spawn→Brill, Deathknell→Brill, Brill→Deathknell și Brill→
South Road Bend; dealul artificial rămâne corect `RESET_REQUIRED`.
Artefactele sunt
`data/runtime/navigation-f3b/steering-monte-carlo-20260901-initial-direction-
calibration.json` și
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-
initial-direction-calibration.json`.

Nu am pornit încă live-ul următor. Mai întâi trebuie păstrat acest gate; apoi
se poate face un singur test bounded Crypt→Brill→Crypt, cu combat oprit.

## ME-250 — v50 și v51 au arătat următoarea problemă

v50 a folosit încă măsurarea veche: proba vedea doar pasul mic dintre două
poze. De aceea nu a putut porni corect calibrarea direcției. Rularea nu este
dovadă de succes.

După corecția măsurării, v51 a pornit calibrarea și a scris mai multe
`INITIAL_FORWARD_DIRECTION_REALIGNED`. Predator a mers mai departe decât în
v49, dar s-a oprit sigur după `652` cadre și `4` recuperări, cu combatul la
`0`. Trace-ul arată că direcția greșită a fost găsită, însă W rămânea încă
apăsat în primul tick de după corecție. Asta putea împinge camera și actorul
în geometria Crypt-ului. Artefactul este
`data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-v51-initial-direction-calibration-v2.json`.

## ME-251 — După o corecție de direcție, Predator se întoarce pe loc

Controllerul are acum o cerere bounded `request_stationary_pivot()`. Când
primul chord spune că direcția salvată este greșită, runnerul cere explicit
un pivot staționar: eliberează W, întoarce camera și pornește din nou numai
când eroarea este mică. Regula este generică pentru orice coridor și nu
adaugă coordonate, waypoints, server truth sau combat.

Testul nou pentru această frână trece împreună cu suita țintită: `275/275`.
Suita offline completă trece `1362/1362`, iar `compileall` trece. Simularea
are `6000/6000` probe de calitate, fără coliziuni. Validatorul WorldPack/navmesh
este `PASS`: cele patru drumuri Azeroth ajung la destinație, iar dealul de
test rămâne corect `RESET_REQUIRED`.

Artefactele noi sunt
`data/runtime/navigation-f3b/steering-monte-carlo-20260901-stationary-realign.json`
și
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-stationary-realign.json`.
Nu pornesc încă un live după acest patch până când verificăm împreună că
autorizația este încă valabilă și păstrăm aceeași limită: Crypt→Brill→Crypt,
un singur test, fără combat handoff.

## ME-252 — v52 a confirmat frâna, dar chordul a fost prea lung

În v52, evenimentul de corecție a avut `stationary_pivot_requested=true`, iar
următorul cadru a avut W eliberat. Deci frâna funcționează. Totuși, calibrarea
a așteptat `1.25` unități și Predator a apucat să se abată prea mult în Crypt;
v52 s-a oprit după `502` cadre și `4` recuperări. Combatul a rămas la `0`.

Pragul generic al primei probe este acum `0.75` unități. Astfel vedem mai
repede dacă direcția este greșită, dar păstrăm limita minimă de zgomot și
regula `UNSAFE` pentru alunecarea pe zid. Testele țintite după această schimbare
sunt `189/189`; live-ul următor nu pornește până când suita offline completă
este din nou verde.

## ME-253 — Proba scurtă a intrat pe podeaua potrivită, dar v53 încă a ales exteriorul

v53 a declanșat proba de direcție foarte devreme și frâna staționară a
funcționat. Totuși, alegerea inițială de Z a preferat încă podeaua exterioară
completă (`138.729`) în locul suprafeței WMO locale (`121.797`). Rularea s-a
oprit după `755` cadre, cu `4` recuperări și `0` combat handoff-uri. Nu este
succes live.

## ME-254 — Suprafața WMO locală are prioritate, apoi v54 s-a oprit fail-closed

Regula de selecție a nivelului pune acum suprafața locală văzută de client
înaintea completitudinii coridorului. v54 a ales corect `Z=121.797` în Crypt,
dar coridorul local era parțial și runnerul s-a oprit înainte de primul cadru
(`RESET_REQUIRED`, `0` cadre). Nu s-au inventat puncte noi.

## ME-255 — Piedică veche la locul actorului și verificarea camerei

Trace-ul v54/v55 a arătat o piedică învățată chiar peste poziția de start.
Memoria rămâne păstrată, dar piedica nu mai este aplicată dacă discul ei
conține poziția proaspătă a actorului pe același nivel. Testul live v56 a
confirmat filtrarea, însă s-a oprit încă la `RESET_REQUIRED` înainte de
control deoarece piedica era adusă și din rezultatul de reluare. Filtrarea a
fost mutată după alegerea nivelului local.

v57 a plecat din Crypt și a mers `526` cadre, cu `4` recuperări, dar s-a oprit
la `x=1678.25, y=1677.12`. v58 a mers mai departe, până la
`x=1668.10, y=1674.57`, apoi s-a oprit după `578` cadre și `4` recuperări.
Ambele au rămas cu `0` combat handoff-uri și nu sunt succes de rută.

Pentru cameră, capturile directe arată zidul foarte aproape, nu cerul:
`data/runtime/operator/20260901T164900Z-camera-check.png` și
`data/runtime/operator/20260901T165300Z-camera-restored-check.png`. Am rulat
recuperarea bounded `SetView(3)` cu `cameraPivot=0`, fără W, A/D sau combat.
Problema rămasă este contactul camerei cu zidul; nu există input vertical în
trace.

După filtrarea nivelului și limita de direcție mai strictă, suita offline este
`1364/1364`, iar `compileall` trece. Următorul pas este offline: separarea
coridorului de egress al Crypt-ului de reluările locale care îl recentrează în
interior. Combatul rămâne oprit.

## ME-256 — Filmarea a confirmat pitch-ul vechi din slotul camerei

În filmarea NVIDIA `Wow.exe 2026.09.01 - 16.40.09.94.mp4`, cadrele de la
început privesc tavanul. Trace-ul v58 are `mouse_delta_y=0` și
`mouse_velocity_y=0`, deci Predator nu a trimis o comandă verticală. După
aproximativ cinci minute camera revine singură la o compoziție normală. Asta
arată că `SetView(3)` a reprodus o vedere veche deja înclinată, iar coliziunea
interioară a făcut-o și mai vizibilă; nu este dovadă de input vertical.

Imaginea live verificată la `2026-09-01T20:06` era normală. Am salvat acea
compoziție în `SaveView(3)` și am verificat imediat recuperarea bounded
`SetView(3)` cu `cameraPivot=0`; nu s-au trimis W, A/D sau combat. Captura este
`data/runtime/operator/20260901T-camera-after-slot-save.png`. Nu pornesc o
nouă rută pentru această verificare. Înainte de următorul live trebuie păstrat
același gate offline și limita de combat `0`.

## ME-257 — Egress-ul verificat nu mai este aruncat după trei încercări

În v58, la a treia și a patra ciocnire, runnerul dezactiva chiar ruta completă
găsită cu discul de coliziune și pornea un backtrack. Astfel, Predator rămânea
în aceeași concavitate, deși navmesh-ul avea ocolire completă până la ieșirea
din Crypt.

Regula generică `_allow_bounded_blocker_exclusion` păstrează o astfel de
ocolire numai când egress-ul este deja verificat de graful structural și
`_blocker_route_quality` o ține în limita de lungime. Pentru drumurile normale,
limita veche de trei încercări rămâne neschimbată. S-au adăugat teste pentru
ambele cazuri.

După schimbare: suita completă este `1365/1365`, `compileall` trece, validatorul
semantic este `5/5 PASS`, iar simularea este `6 x 1000/1000`, fără coliziuni și
cu `quality_pass_rate=1.0`. Următorul pas permis este un singur live bounded
Crypt→Brill→Crypt, cu combat `0`.

## ME-258 — Live v60: ocolirea a fost aleasă, dar controllerul a rămas local

Proba `data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-v60-verified-egress-live.json`
nu a ajuns la Brill. Primul leg a fost `ARRIVED` în Crypt, iar al doilea s-a
oprit la `[1656.0978,1681.3972]` după `446` cadre și `4` recuperări. La
încercările 3 și 4, ruta cu excludere a fost acceptată, dar volanul creat pentru
ocolirea mică a rămas activ și a dus din nou Predator în concavitate.

## ME-259 — Live v62: egress-ul reia volanul, dar limita locală încă pornea prea devreme

În `data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-v62-verified-egress-steering-live.json`,
Predator a mers mai departe, până la `[1659.4075,1689.5335]`, apoi s-a oprit
`STUCK_REPLAN_REQUIRED` după `776` cadre și `4` recuperări. Resetarea volanului
pentru egress a fost corectă, însă la primele două ciocniri ruta directă avea
prea puține poligoane excluse sau depășea cu puțin limita locală; runnerul a
repetat două ocoliri mici și apoi a ajuns pe backtrack.

Regula offline următoare acceptă, numai pentru un egress deja verificat, o rută
completă care a exclus poligoane și este cu cel mult `2.0` yarzi peste limita
locală. O rută fără poligoane excluse sau mai lungă rămâne respinsă. După această
schimbare suita completă este `1366/1366`, `compileall` trece, validatorul
semantic rămâne `PASS`, iar simularea anterioară rămâne `6 x 1000/1000`.

Următorul live trebuie să fie unul singur, cu `combat=0`, folosind această
regulă. Nu se folosește teleport sau reset ca să ascundă eșecul. Integrarea
Zygor rămâne separată: ghidul poate furniza obiective și ordinea lor, dar nu
înlocuiește testul de mișcare și nu se copiază conținut licențiat în repository.

## ME-260 — Live v63: stare de intrare stricată, oprire corectă

Proba `data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-v63-verified-egress-route-live.json`
nu este succes de rută. A pornit din poziția rămasă de v62, nu dintr-un
checkpoint curat. Primul leg a fost considerat `ARRIVED` în Crypt; al doilea a
ajuns la `[1661.9817,1694.4980]` și s-a oprit `RESET_REQUIRED` după `293` cadre
și `3` recuperări, deoarece nici coridorul candidat și nici backtrack-ul nu mai
erau complete. Combatul a rămas `0`, iar arm-ul a fost șters imediat.

Concluzie: nu mai evaluăm egress-ul dintr-o poziție deja degradată de o probă
anterioară. Pentru următoarea validare este necesar un checkpoint LAB curat și
un singur test. Zygor poate fi conectat după aceea ca sursă de obiective
semantică, în afara mișcării și a conținutului licențiat.

## ME-261 — Parserul Zygor păstrează zonele cu apostrof

Verificarea read-only a `D:\Downloads\Zygor.zip` a găsit nume ca `Un'Goro
Crater`. Regex-ul vechi tăia numele la `Un`, iar importul se oprea pentru că
nu mai găsea binding-ul WorldPack. Parserul citește acum ghilimeaua de început
și caută aceeași ghilimea la final. Testul nou trece, iar proba pe ghidul Horde
din ZIP produce `3307` pași, `2922` candidați de coordonate și rămâne cu
`execution_authority=false`. Testele Zygor țintite sunt `15/15`, suita completă
este `1367/1367`, iar `compileall` trece. Conținutul ghidului nu este salvat în
repository.

## ME-262 — Memorie separată pentru ocoliri care au eșuat repetat

Trace-urile v60/v62 au arătat că Predator putea încerca din nou aceeași
ocolire locală după un eșec. Memoria nouă
`recovery-strategy-memory-tbc243.json` păstrează doar celula client-observată,
strategia și numărul de eșecuri. După două eșecuri în aceeași celulă,
`local_clearance` este sărit la următoarea planificare; nu sunt adăugate
waypoint-uri și nu se acordă autoritate de execuție. O ocolire locală care
reușește șterge eșecul pentru celula respectivă, iar un singur eșec expiră după
7 zile. Contractul este `contracts/recovery-strategy-memory.schema.json`, iar
testele dedicate acoperă confirmarea, expirarea, rezolvarea și mismatch-ul de
client build.

După implementare, suita completă este `1374/1374`, validatorul semantic
`semantic-road-journey-validation-20260901-recovery-memory.json` este `PASS`
(cele patru drumuri ajung, iar dealul rămâne `RESET_REQUIRED`), iar simularea
`steering-monte-carlo-20260901-recovery-memory.json` trece `6 x 1000/1000`, fără
coliziuni și cu `quality_pass_rate=1.0`. Acestea sunt verificări offline; nu
dovedesc încă drumul live.

## ME-263 — Gate-ul de mișcare continuă trebuie închis înainte de următorul live

Verificarea runnerului continuu a găsit o diferență importantă: acesta construiește
`WindowsContinuousMotionSession` direct din autorizația fixed-UI și nu încarcă un
`movement_runtime_arm`. Autorizația fixed-UI are doar captură/HUD/UI și
`permitted_modes=[]`; ea nu poate acorda singură dreptul de a apăsa W/A/D sau RMB.

Profilul separat `config/execution-targets/tbc_243_lab_movement_f3a.json` este încă
`pending_evidence`, iar încercarea de revalidare a fost refuzată deoarece nu are
aprobare. În acest moment clientul este în viață, dar `runtime_arm_present=false`
și Predator rămâne `OBSERVE_ONLY`. Nu se pornește un nou drum live până când
runnerul continuu folosește poarta/arm-ul de mișcare potrivit și există o aprobare
bounded valabilă; nu se inventează câmpul `approval` și nu se folosește autorizația
de UI ca înlocuitor.

## ME-264 — Cursor advisory pentru pașii Zygor

RouteTeacher are acum `next_advisory_route_steps()`. El alege următorii pași după
ordinea din ghid, nivel, `map_id` exact și o listă de pași deja finalizați. Include
și pași fără coordonate, pentru că aceștia pot fi questuri, traineri sau acțiuni
care trebuie observate în client. Rezultatul rămâne `KnowledgeEntry` advisory:
nu are autoritate, nu apasă taste și nu înlocuiește verificarea navmesh/client.

Testul nou acoperă ordinea, finalizarea și separarea între hărți. Testele
Knowledge Broker sunt acum `13/13`.

## ME-265 — Regresie offline după cursorul Zygor

După cursorul advisory, suita completă era `1376/1376`, iar `compileall` trece.
Validatorul semantic rămâne `PASS`: Crypt spawn→Brill, Deathknell→Brill,
Brill→Deathknell și Brill→south road ajung; dealul de test rămâne corect
`RESET_REQUIRED`. Simularea de steering rămâne `6 x 1000/1000`, fără coliziuni,
cu `quality_pass_rate=1.0`. Aceste rezultate sunt offline și nu schimbă gate-ul
live.

## ME-267 — Gate F4a pentru mișcare continuă

Runnerul de navmesh nu mai construiește direct sesiunea continuă din
autorizația fixed-UI. `ContinuousMotionExecutionGateway` cere un arm separat,
cu profilul `execution:tbc243-lab:movement-f4a-continuous-navmesh`, binding pe
procesul WoW, hash-ul autorizației aprobate și hash-ul receipt-ului exact.
Arm-ul permite doar cele patru controale de mers și lease-uri scurte; F3a
single-pulse și autorizația de UI sunt respinse.

Issuerul F4a există acum ca pași separați, fără input: `issue_continuous_motion_authorization.py`
creează autorizația doar după ack-ul separat, iar
`issue_continuous_motion_runtime_arm.py` leagă arm-ul de receipt și de o
revalidare de realm proaspătă. Profilul F4a și arm-ul nu există încă în stare
`approved_bounded` pentru clientul curent. De aceea orice pornire normală a
runnerului fără cele trei fișiere se oprește înainte de input. Nu s-a pornit un
test live nou. Testele dedicate ale gateway-ului și runnerului trec `5/5`, iar
suita completă anterioară este `1390/1390`. Următorul pas este emiterea
controlată a acestor fișiere, nu ocolirea gate-ului.

## ME-268 — Clearance lateral pentru poduri și coridoare înguste

`NavPortal` oferă acum măsura generică `PortalLateralClearance`: lățimea
portalului, spațiul centrului actorului până la ambele margini și spațiul liber
după raza actorului plus marja de siguranță. Măsura este obținută numai din
geometria locală client-side și nu devine waypoint sau autoritate de execuție.

`TargetTetherIntent` păstrează această dovadă pentru combat. Dacă actorul este
prea aproape de marginea unui pod/coridor, `HumanlikeCombatMotionController`
ține strafe-ul oprit (`LANE_GUARD`) și păstrează observarea țintei. Când nu
există portal apropiat, valoarea este necunoscută, nu este presupusă liberă.

Testele țintite pentru navmesh, tether și combat trec `35/35`; suita completă
după schimbare trece `1396/1396`, iar `compileall` și `git diff --check` trec.
Nu s-a pornit live și nu s-a acordat arm de mișcare.

## ME-269 — Video live și memorie de obstacol pe alt etaj

Sesiunea live din 1 septembrie a fost înregistrată și fișierul NVIDIA este
valid (`537.247244` secunde, `3202363822` bytes). Cadrele din partea în care
trebuia să înceapă drumul arată Predator nemișcat în `Shadow Grave`.

Prima încercare (`v64`) s-a oprit înainte de input din cauza unui worker care nu
se potrivea cu graful de structură. A doua (`v65`), cu workerul corect, s-a
oprit tot înainte de input: memoria `obstacle:c7d030808bec03c9` avea centrul
la înălțimea `138.07`, iar stratul local selectat al spawnului era `121.80`.
Filtrul vechi compara doar X/Y și trata obiectul de sus ca zid pe podeaua
curentă.

Corecția mută aplicarea priors după alegerea stratului local și ignoră doar
obstacolele confirmate din orizontul apropiat care sunt pe altă înălțime. Nu se
adaugă coordonate sau waypoint-uri. Testul nou acoperă acest caz; suita completă
trece `1397/1397`, iar `compileall` și `git diff --check` trec. Următoarea probă
live poate fi o singură ieșire Crypt→Brill, cu combat oprit; Silverpine rămâne
după ce avem catalog și acces local validate pentru zona aceea.

## ME-270 — V74: probă live înregistrată și realiniere de heading

Am păstrat `LAB_COMBAT_PROTECTION_ON:PLAYER=Predator` și combatul a rămas
dezactivat. Primele două porniri v74 s-au oprit înainte de input: una folosea
un argument CLI inexistent (`--result-file`), iar următoarele au consumat
armarea F4a de 30 de secunde în scanarea locală a clădirii. Runnerul scrie
rezultatul singur în `data/runtime/navigation-f3b/results`.

Pentru o felie diagnostică explicită am adăugat `--skip-structure-awareness`.
Aceasta nu ocolește navmesh-ul și nu acordă autoritate nouă; sare doar încărcarea
și scanarea mare de structuri, ca să putem testa mersul direct înainte ca armarea
scurtă să expire. Folosirea ei nu este dovadă pentru ieșirea Crypt→Brill.

Proba live v74-direct2 a fost înregistrată în
`C:\Users\LabUser\Videos\NVIDIA\Wow.exe\Wow.exe 2026.09.02 - 01.20.32.106.mp4`
(`28.967711` secunde, `168291280` bytes). Rezultatul este
`data/runtime/navigation-f3b/results/navmesh-roaming-877c418e-5aee-455d-b902-78dcf58c529f.json`:
`RUNTIME_ARM_EXPIRED`, `68` cadre de control, `23` apăsări W, fără combat,
poziția finală `[1662.8550417730626, 1694.773835149142]`, iar distanța la
ținta scurtă a crescut la `5.049295950876706`. Video-ul arată Predator în
Shadow Grave, cu puțină mișcare spre stânga, apoi camera se lipește de model
și perete; nu a ajuns la țintă. După probă, camera a fost readusă prin comanda
de recovery, dar checkpoint-ul manual încă arată camera foarte aproape de model
și perete; Predator este în continuare în Shadow Grave.

Patch-ul de heading rămâne bounded: realinierea live este limitată la două
încercări și cere abatere mare, deplasare observată și coridor scurt. Testele
țintite pentru runner trec `186/186`, suita completă după schimbare trece
`1402/1402`, `compileall` trece, iar `git diff --check` trece. Următorul pas
este repararea camerei și a sensului W în această poziție, apoi o singură
ieșire Crypt→Brill cu scanarea completă; nu declarăm încă autonomia.

## ME-271 — V75: alunecarea pe perete nu mai schimbă heading-ul

Am adăugat o verificare geometrică bounded pentru realinierea din primul chord:
deplasarea observată trebuie să aibă cel puțin `0.25` proiecție pe tangenta
coridorului. Un chord care merge în lateral sau înapoi rămâne doar dovadă de
coliziune și este scris ca `INITIAL_FORWARD_DIRECTION_REALIGNMENT_SKIPPED`.
Regula se aplică și realinierii live scurte; nu adaugă waypoint-uri și nu
schimbă autoritatea de execuție. Testul nou acoperă și logarea acestui caz.

Primele două porniri v75 nu au trimis input: arm-ul F4a a expirat în timp ce
porneam/opream filmarea. Fișierele video au fost totuși păstrate ca evidență a
preflight-ului. A treia pornire a fost proba live v75, cu godmode LAB activ și
combat `0`. Rezultatul este
`data/runtime/navigation-f3b/results/navmesh-roaming-79f53d4b-40c4-48ab-944d-3d3161072851.json`:
`ARRIVED`, `78` cadre, `59` apăsări W, `0` recuperări. Predator a mers de la
poziția curentă din `Shadow Grave` până la ținta locală de cinci yarzi și a
rămas la `1.9513` yarzi de ea, în raza de sosire de `2.0`.

În trace, primul chord util a avut proiecție `0.8196` și a fost acceptat; al
doilea a avut proiecție `-0.7675` și a fost ignorat cu motivul de alunecare pe
perete. Asta este exact problema observată în v74-direct2. Filmarea NVIDIA
este `C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 01.45.10.109.mp4`
(`60.767367` secunde, `360438607` bytes). Cadrele de la început trec prin
peretele apropiat, apoi camera revine la o vedere normală din spatele
personajului; Predator nu moare și nu intră în combat.

După probă am oprit filmarea, am reassertat godmode-ul și am salvat checkpoint-ul
`data/runtime/operator/20260901T224714521Z-manual-checkpoint.png`. Checkpoint-ul
arată Predator în picioare în Shadow Grave, cu camera joasă dar fără privirea
în tavan. După patch, suita completă este `1403/1403`, testele țintite de
runner și heading sunt `194/194`, `compileall` trece și `git diff --check`
trece. Aceasta este o confirmare a mersului pe felia locală; ieșirea completă
Crypt→Brill cu scanarea structurală rămâne netestată în această probă.

## ME-272 — Armarea F4a se leagă după preflight-ul read-only

Problema din v74/v75 era temporală: runtime arm-ul F4a este scurt, iar runnerul
încărca arm-ul înainte de scanarea WorldPack, alegerea etajului și planificarea
coridorului. La o scanare structurală lentă, arm-ul expira înainte de prima
apăsare W. Nu am mărit durata și nu am creat o reînnoire automată.

Runnerul folosește acum un placeholder release-only în preflight. El poate
elibera în siguranță orice input, dar nu poate aplica un cadru de mers. După ce
planul local și ultima observație vizibilă sunt gata, runnerul tipărește
`PREFLIGHT_READY` (dacă este cerută așteptarea), validează arm-ul F4a și abia
apoi construiește `ContinuousMotionExecutionGateway`. Opțiunea bounded
`--runtime-arm-wait-seconds` (0–300, implicit 0) doar așteaptă ca operatorul să
înlocuiască un arm expirat; nu emite, nu reînnoiește și nu lărgește autorizația.

Testele runnerului, gateway-ului și client-navigation sunt `280/280`, suita
offline completă este `1405/1405`, `compileall` trece și `git diff --check`
trece. Nu s-a pornit un nou test live după această schimbare; următoarea probă
poate folosi preflight-ul complet și o armare F4a proaspătă, cu godmode și
combat `0`.

## ME-273 — Ocolirea folosește și obstacolul observat; două probe live ajung la țintă

Am găsit un defect în recuperarea după coliziune: cele trei picioare ale
ocolirii erau cerute de navmesh-ul curat, fără discul obstacolului observat.
Astfel, planul putea fi „valid” pe hartă, dar putea trece din nou prin locul în
care clientul tocmai raportase contact. `side_corridor`, `pass_corridor` și
`mission_probe` folosesc acum aceeași interogare `candidate_query`, care include
obstacolul observat. Testul structural verifică toate cele trei apeluri.

Suita completă după corecție este `1408/1408`; testele țintite movement și
client-navigation sunt `279/279`, iar `compileall` și `git diff --check` trec.

Am făcut două probe live înregistrate, cu `LAB_COMBAT_PROTECTION_ON` pentru
Predator și combat `0`:

* `navmesh-roaming-a63471cd-78a8-4f92-b2a3-d08b61487074.json` a mers 140 cadre,
  fără coliziune sau recuperare, până la `2.506` yarzi de țintă. Filmarea este
  `C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 02.47.58.113.mp4`
  (`90.023711` secunde, `534154487` bytes). Cadrele verificate arată camera
  stabilă și mersul în sala Crypt; bugetul de cadre s-a terminat înainte de
  raza de sosire.
* Continuarea `navmesh-roaming-792f6474-9435-47e3-947c-441b9d343814.json` a
  ajuns `ARRIVED` în 16 cadre, cu 5 cadre W, 0 recuperări și `1.9739` yarzi
  rămași (raza de sosire este `2.0`). Filmarea este
  `C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 02.50.44.114.mp4`
  (`73.609656` secunde, `436206275` bytes). Cadrele verificate nu arată
  privirea în tavan și nu arată contact cu peretele.

Aceasta confirmă doar felia locală din Crypt. Nu este încă testul complet
Crypt→Brill și nu pornesc combatul până când ruta de ieșire nu trece separat.

## ME-274 — Așteptare bounded pentru armul F4a

Supervisorul transmite acum `--runtime-arm-wait-seconds` către runnerul de
navmesh. Dacă armul expiră înainte de input, rezultatul rămâne
`STOPPED_FAIL_CLOSED`; nu se reînnoiește automat și nu se mărește fereastra de
execuție. Testele supervisorului sunt `16/16`, iar verificările runnerului și
`compileall` trec.

## ME-275 — Probă live completă fără graful de egress

Proba înregistrată a pornit cu primul leg local din Crypt, apoi s-a oprit
`RUNTIME_ARM_EXPIRED` după `449` cadre. Predator a rămas viu, fără combat și
fără moarte; nu a existat dovadă de ieșire în Brill. Filmarea este
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 03.01.35.115.mp4`
(`651.128344` secunde, `3880638525` bytes). Imaginile de la final arată
camera coborâtă spre perete/podea, deci clipul este diagnostic, nu succes de
rută.

## ME-276 — Diagnostic direct fără obstacole învățate vechi

Cu memoria locală goală, rezultatul
`data/runtime/navigation-f3b/results/navmesh-roaming-f8304c64-1907-4f2f-8c75-602eb4c444b9.json`
este `RUNTIME_ARM_EXPIRED`, `261` cadre, `179` apăsări W și `3` recuperări.
Poziția finală este `[1662.6711705703833,1687.0512443758435]`; Predator nu a
murit și nu a intrat în combat. Filmarea
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 03.16.56.116.mp4`
are `113.556956` secunde și `673325198` bytes. Clipul arată mai întâi
personajul în picioare, apoi camera lipită de zid.

## ME-277 — Graful de structură alege egress-ul verificat

Proba cu graful explicit a selectat
`graph_id=wow.tbc.2.4.3.8606.azeroth-full-worldpack-v3:Azeroth:structure-access-v1`,
`structure_id=0:wmo:85944` și
`opening_id=access:7bb73baa2ccf348bb33511f2`. Anchorul de ieșire este
`[1666.710938,1661.981445,141.939575]`, iar deschiderea este
`[1666.369385,1662.64917,141.875641]`. Rezultatul
`navmesh-roaming-6ebf4bc5-8669-4103-9534-b98df3556172.json` s-a oprit
`RUNTIME_ARM_EXPIRED` după `193` cadre și `143` W; nu este sosire în Brill.
Filmarea `C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 03.26.14.117.mp4`
are `568.829589` secunde și `3387656327` bytes. Predator a rămas viu, fără
combat; după coliziune camera a ajuns din nou spre podea/perete.

## ME-278 — Realinierea inițială nu mai inventează un zid

Proba geometrică următoare, `navmesh-roaming-60615dea-57c3-43be-a9da-43130ac19285.json`,
este `RUNTIME_ARM_EXPIRED`, `130` cadre, `82` W și `2` recuperări. Primul
chord a mers în sens opus tangentei egress-ului, iar logul a păstrat dovada
de deplasare fără să o transforme în obstacol fals. Filmarea
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 03.41.29.118.mp4`
are `326.996511` secunde și `1953530232` bytes; cadrele verificate arată
Predator viu și fără combat, dar camera se lipește de perete după aproximativ
`110` secunde.

## ME-279 — Replan bounded după primul chord curat

După un chord inițial care nu se potrivește cu tangenta, runnerul poate cere o
singură reconstruire de coridor din poziția clientului proaspăt observată.
Evenimentele sunt `INITIAL_DIRECTION_CORRIDOR_REPLAN_REQUESTED` și
`CORRIDOR_RECENTER_REPLAN`; nu se inventează coliziune și nu se adaugă
waypoint. Testele movement sunt `194/194`, supervisorul `16/16`, iar
`compileall` și `git diff --check` trec.

Proba grafică rezultată
`navmesh-roaming-f5bc2dd7-de80-4500-9916-cbe59b708e65.json` a rulat cu
`geometric_predictive_v1`: `CONTROL_FRAME_BUDGET_EXHAUSTED`, `220` cadre,
`125` W, `1` recuperare, un waypoint semantic și poziția finală
`[1658.30422950675,1691.60205679582]`. Distanța rămasă la Brill era
`1524.6045230876` yarzi. Filmarea
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 03.58.51.119.mp4`
are `381.479100` secunde și `2273472859` bytes. Verificarea cadrelor arată
camera normală după început, Predator viu și zero combat; nu este sosire.

## ME-280 — Controllerul de traiectorie continuă rămâne în Crypt

Am comparat `continuous_trajectory_v1` pe același egress verificat. Rezultatul
`navmesh-roaming-185f463a-0feb-4eaa-98d8-d857d15ac22b.json` este
`CONTROL_FRAME_BUDGET_EXHAUSTED`, `180` cadre, `138` W și `1` recuperare.
Au apărut replanul inițial și backtrack-ul verificat, dar Predator a rămas în
Crypt la `[1656.6953564833111,1692.2226221258202]`; ținta locală de recovery
era `[1658.671971912112,1691.73996020249]`, iar Brill era încă la
`1525.8095077269331` yarzi. Filmarea
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 04.06.58.120.mp4`
are `623.718722` secunde și `3718410149` bytes. Cadrele verificate arată
camera stabilă și Predator în picioare, fără moarte și fără combat.

## ME-281 — Raza de backtrack toleră jitterul HUD-ului

Trace-ul ME-280 s-a oprit la aproximativ `2.03` yarzi de ancora de backtrack,
deși aceasta era o urmă sigură deja traversată. Am introdus
`BREADCRUMB_BACKTRACK_ARRIVAL_RADIUS_WORLD=2.25`, folosit numai pentru acest
backtrack verificat; ocolirile laterale păstrează raza `0.5`. Testul nou duce
movement la `195/195`, suita offline completă la `1412/1412`, iar `compileall`
și `git diff --check` trec.

Pornirea live de verificare a fost refuzată înainte de input deoarece armul
F4a a expirat în fereastra de preflight. Filmarea de preflight
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 04.23.57.121.mp4`
are `567.029211` secunde și `3376487624` bytes; cadrele arată Predator viu,
în picioare, fără combat, dar nu testează raza nouă. Godmode-ul LAB a fost
reassertat după fiecare probă (`LAB_COMBAT_PROTECTION_ON:PLAYER=Predator`), iar
combatul a rămas `0` în toate probele de mai sus. Nu există încă dovadă live
pentru Crypt→Brill; următorul pas sigur este o singură rulare cu snapshot-uri
aliniate și armare F4a proaspătă, apoi verificare video și status `ARRIVED`.

## ME-282 — Rulare live înregistrată după armare F4a proaspătă

Armarea a fost reînnoită în fereastra de preflight, iar rularea cu
`continuous_trajectory_v1` și workerul compatibil `pa_nav_probe-v34` a primit
`260` cadre de control. Rezultatul
`navmesh-roaming-dfb3209a-8482-4d26-a82d-8f5bba2e5f74.json` este
`CONTROL_FRAME_BUDGET_EXHAUSTED`, cu `199` comenzi W, `1` recuperare și fără
moarte sau combat. Predator a rămas în Crypt, la
`[1656.1897106759434,1686.085920529181]`; distanța până la Brill a rămas
`1520.3740201239202` yarzi. Graful de egress și world pack-ul au fost încărcate,
dar poziția fizică de pornire a rămas lipită de geometria interioară, cu un
blocker observat local; nu declarăm sosire și nu folosim teleport sau server
truth.

Înregistrarea este
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 04.48.11.122.mp4`
(`257.356722` secunde, `1531363831` bytes). Cadrele la aproximativ 0, 30, 60,
90, 120, 180 și 240 secunde arată Predator în picioare, cu viață completă,
camera în Crypt și zero combat; clipul este dovadă de diagnostic, nu de
Crypt→Brill reușit. Godmode-ul LAB a fost reassertat la final, iar statusul
operatorului arată clientul WoW viu, `runtime_arm_present=false` și
`predator_execution_mode=OBSERVE_ONLY`.

## ME-283 — Detectorul de mini-hartă a fost adaptat la scalarea Windows

Pe capturile actuale, fereastra clientului are `3621x2037` pixeli fizici,
deci cercul mini-hărții este mai mare decât limita veche a profilului. Două
încercări cu profilul vechi s-au oprit fail-closed la
`initial visible heading unavailable`, fără să trimită mișcare. Profilul
`config/pose/minimap-tbc243-8606.json` acceptă acum raza normalizată
`0.055..0.10`, iar testul de regresie pentru cadrul scalat trece.

Rularea live cu profilul nou a citit direcția din minimapă
(`MOUSE_INTEGRATED_MINIMAP_FALLBACK`) și a executat `201` comenzi W în `205`
cadre, cu `3` recuperări. Armul F4a a expirat și a oprit inputul; rezultatul
este `RUNTIME_ARM_EXPIRED`, la
`[1657.6606802973765,1691.1193948724917]`, cu `1524.4148026336317` yarzi până
la Brill. Nu este încă egress din Crypt și nu este sosire. Clipul verificat este
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 05.02.12.124.mp4`
(`476.588256` secunde); cadrele arată Predator în picioare și cu viață
completă, fără combat. Godmode-ul LAB a fost reassertat (`PLAYER=Predator`),
iar la final statusul a revenit la `runtime_arm_present=false` și
`OBSERVE_ONLY`.

După această ajustare, suita offline completă este `1413/1413`, iar
`compileall` și `git diff --check` trec. Următoarea problemă izolată rămâne
geometria pornirii din colțul interior al Crypt-ului și alegerea primului
coridor fizic; nu trecem la combat până când Crypt→Brill nu are sosire live
verificată.

## ME-284 — Atingerea laterală WMO a fost testată live, dar egress-ul încă nu iese

Am adăugat în controller o atingere laterală scurtă și limitată la un coridor
WMO drept, când clearance-ul local din navmesh confirmă partea liberă. Testele
offline pentru controller și movement sunt `283/283`; suita completă după
această schimbare este `1414/1414`. Rularea live
`navmesh-roaming-c3c19cb4-9228-4e0b-9919-ad3c7a03c7a3.json` a încărcat graful
corect de structură
`wow.tbc.2.4.3.8606.azeroth-full-worldpack-v3:Azeroth:structure-access-v1`
și a planificat opening-ul verificat
`[1666.369385, 1662.64917, 141.875641]`. Au apărut atingeri
`STRAFE_LEFT/RIGHT` în cadrele continue, dar Predator a rămas în aceeași
concavitate: `RESET_REQUIRED`, `140` cadre, `94` comenzi W și `1` recuperare,
cu poziția finală `[1659.2235855201493, 1694.9117385558081]` și aproximativ
`1527.2854` yarzi până la Brill. Nu este sosire și nu este o soluție încă.

ShadowPlay-ul verificat este
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 05.12.51.125.mp4`
(`1409.253100` secunde, `6731641022` bytes). În cadrele din probă, bara de
viață este plină și nu apare combat, însă camera este din nou ridicată spre
tavan; după probă, captura manuală
`data/runtime/operator/20260902T024608703Z-manual-checkpoint.png` arată
unghiul bun. Godmode-ul LAB a fost reassertat pentru Predator. Următorul pas
este recuperarea controlată din această concavitate și o nouă probă filmată;
nu se folosește teleport, server truth sau combat până când ieșirea nu este
verificată.

## ME-285 — Recuperarea scurtă live a reușit, dar nu este încă ieșirea spre Brill

După armare F4a proaspătă, rularea
`navmesh-roaming-1d984cf7-fa9a-4ce2-86f0-277ccb19b61d.json` a ajuns la ținta
semantică din centrul Crypt-ului: `ARRIVED`, `71` cadre, `49` comenzi W și
`0` recuperări. Poziția finală a fost
`[1661.062297546941, 1693.1189942691494]`, la `21.891350522521467` yarzi de
ținta `[1676.35, 1677.45]`. Nu a existat moarte sau combat. Aceasta este doar
o recuperare locală; nu dovedește Crypt→Brill.

Salvarea ShadowPlay prin `SaveShadowReplay` a fost înregistrată, dar nu a
creat un fișier MP4 nou. Captura de după comandă a arătat camera lipită de
zid. O corecție de pitch limitată (`-120`) a readus vederea third-person,
confirmată în `data/runtime/operator/20260902T032748579Z-manual-checkpoint.png`
și apoi salvată în slotul nativ 3. Godmode-ul LAB a fost reassertat.

## ME-286 — Felie live filmată cu controlerul geometric

Rularea repetată de la poziția sigură, cu `geometric_predictive_v1`, este
`navmesh-roaming-3cb7bb0b-9e0d-40cc-8094-e9d1aa9a0fba.json`: `CONTROL_FRAME_BUDGET_EXHAUSTED`,
`220` cadre, `184` comenzi W, `0` recuperări, poziția finală
`[1657.56874469604, 1686.08592052918]`, `1519.82754991884` yarzi până la
Brill și `1/73` waypoint semantic. Combatul a rămas `0`.

Proba a fost filmată în
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 06.35.27.127.mp4`
(`232.548133` secunde, `1383900011` bytes). Cadrele verificate la 0, 30, 60,
120, 180 și 230 secunde arată podeaua și Predator la început, apoi camera
urcând spre tavan/zid și revenind ulterior; bara de viață rămâne plină. Nu
este ieșire din Crypt și nu este sosire la Brill.

## ME-287 — Diagnostic direct navmesh fără scanarea de egress

Pentru comparație, am rulat o felie explicită cu `--skip-structure-awareness`
și `continuous_trajectory_v1`. Rezultatul
`navmesh-roaming-5323347b-6fec-4ee8-a217-ebbd35b4247c.json` s-a oprit fail-closed
la expirarea armului: `RUNTIME_ARM_EXPIRED`, `158` cadre, `109` comenzi W,
`2` recuperări, poziția `[1659.775199128187, 1690.7056846524936]`,
`1523.2012440611086` yarzi până la Brill și `0/73` waypoint-uri. Combatul a
rămas `0`; graful de structură nu a fost folosit în această comparație.

Clipul verificat este
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 06.43.45.128.mp4`
(`207.382789` secunde, `1232584422` bytes). Cadrele arată mișcare locală în
Crypt, dar camera ajunge din nou la tavan. Diagnostic: scoaterea scanării de
egress nu rezolvă blocajul fizic.

## ME-288 — MPPI a încercat mai multe direcții, fără progres de egress

Proba cu `pa_mppi_v1` a fost înregistrată separat. Rezultatul
`navmesh-roaming-0aafe4ee-e21d-47d6-bdc0-81d09a4928aa.json` este
`CONTROL_FRAME_BUDGET_EXHAUSTED`, `180` cadre, `130` comenzi W,
`2` recuperări, poziția `[1659.40745672283, 1692.15367042249]`,
`1524.67712154014` yarzi până la Brill și `1/73` waypoint semantic. Combatul
a rămas `0`.

Clipul verificat este
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 06.51.23.129.mp4`
(`352.506167` secunde, `2101585521` bytes). Cadrele la 0, 30, 60, 120, 180,
240 și 280 secunde confirmă aceeași concavitate și aceeași alternanță a
camerei; MPPI nu a produs ieșire. După test, armul operator a fost retras,
iar godmode-ul LAB a fost reassertat pentru Predator.

## ME-289 — Repetarea cu `adaptive_trajectory_v1` a rămas în aceeași concavitate

Am pornit din nou ruta semantică Crypt→Brill cu controlerul care avusese
dovada bună în rularea veche, după preflight read-only și armare F4a proaspătă.
Rezultatul
`navmesh-roaming-a2f8e6e1-4375-4ccb-8835-653236183135.json` este
`RUNTIME_ARM_EXPIRED`: `343` cadre, `232` comenzi W și `3` recuperări.
Predator a rămas în Crypt la
`[1656.37358187862,1690.70568465249]`, cu `1524.5431999638` yarzi până la
Brill; a completat doar `1` waypoint semantic și nu a trecut de egress.
Nu a existat moarte sau combat. Jurnalul arată blocarea repetată lângă
`[1656.8689497524474,1689.6479351143614]`, urmată de expirarea armului cu
inputul eliberat.

Clipul ShadowPlay valid este
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 07.22.16.130.mp4`
(`705.469600` secunde, `4206475023` bytes). Am verificat cadrele din partea
testului: Predator este viu și cu viața plină; la început se vede în Crypt,
apoi camera se ridică spre tavan și zid și rămâne acolo. Filmarea confirmă
diagnosticul, nu o sosire la Brill. Godmode-ul LAB a fost reassertat după
probă (`LAB_COMBAT_PROTECTION_ON:PLAYER=Predator`), iar statusul final este
client WoW viu, `runtime_arm_present=false` și
`predator_execution_mode=OBSERVE_ONLY`.

Concluzie: `adaptive_trajectory_v1` nu rezolvă încă pornirea din concavitatea
interioară. Nu trecem la combat și nu declarăm Crypt→Brill până când o probă
filmată nu arată ieșirea reală.

## ME-290 — Reprobă filmată și protecție pentru ținte non-semantice

Am reparat un caz de siguranță în `run_navmesh_roaming.py`: ramura de frontieră
nu mai indexează `semantic_goals` când ținta vine din coordonate normalizate
și coada semantică este goală. Testul de regresie a fost adăugat în
`tests/test_movement_engine.py`; suita completă a motorului de mișcare este
`196/196`.

Am repetat live, cu `adaptive_trajectory_v1`, pornind către centrul Crypt-ului
din coordonate normalizate. Rezultatul
`navmesh-roaming-6d0d0bf4-311a-49e0-94a9-45982842e9eb.json` este
`PARTIAL_CORRIDOR_FRONTIER_STUCK`: nu a trimis cadre de control după gardul
de siguranță, poziția observată a rămas
`[1661.7977823576575,1694.980690259141]`, iar distanța până la ținta locală a
rămas `22.7835936426185` yarzi. Nu a fost moarte și nu a fost combat. Patch-ul
a prevenit excepția `IndexError` din încercarea anterioară și a permis oprirea
fail-closed.

Toate probele acestei sesiuni sunt înregistrate în clipul ShadowPlay
`C:/Users/LabUser/Videos/NVIDIA/Wow.exe/Wow.exe 2026.09.02 - 07.42.22.131.mp4`
(`776.677700` secunde, `4632547351` bytes). Am extras și verificat cadre din
momentele probelor: Predator rămâne în Shadow Grave, în picioare, cu bara de
viață plină; camera se lipește uneori de perete/tavan. Clipul este dovadă de
diagnostic și nu dovedește încă Crypt→Brill.

Godmode-ul LAB a fost reassertat după probă
(`LAB_COMBAT_PROTECTION_ON:PLAYER=Predator`). Statusul final confirmă clientul
WoW viu (`PID 53092`), `runtime_arm_present=false` și
`predator_execution_mode=OBSERVE_ONLY`. Nu trecem la combat până când ieșirea
Crypt→Brill nu este văzută clar în video și raportată `ARRIVED`.

## ME-291 — Barierele memorate din interiorul WMO nu mai închid ieșirea

Reproducerea offline a blocajului ME-290 a arătat că două discuri memorate în
interiorul Crypt (`[1658.8195778691615,1681.0162859328252]` și
`[1664.4280149045119,1690.1899729575648]`) făceau cererea către ieșire să
pară blocată. Am adăugat `ClientNavmeshQuery.for_structure_egress()` și
implementarea în adaptorul client: pentru picioarele de egress se scot doar
discurile al căror centru este în limitele 3D ale aceluiași WMO; discurile de
afară rămân active.

Cu aceleași bariere și aceeași poziție de start din rularea live, verificarea
offline a ales waypoint-ul semantic `1` și portalul
`access:7bb73baa2ccf348bb33511f2`, cu anchor revalidat la
`[1666.710938,1661.981445,141.939575]`. Aceasta este o dovadă de contract și
navmesh offline, nu o dovadă de mișcare live.

Testele țintite pentru motor și adaptor sunt `286 passed`. Nu am pornit încă
un test live după patch; armul runtime rămâne absent, iar Predator rămâne în
godmode LAB și în `OBSERVE_ONLY`. Următorul pas permis este o singură probă
live scurtă și filmată, după verificarea finală a suitei offline.

## ME-292 — Trei probe live după filtrarea barierelor WMO

Am făcut trei probe live scurte pe ruta semantică Crypt→Brill, cu Predator în
godmode LAB și cu armare nouă pentru fiecare probă. Nu am folosit teleport,
server truth sau combat. Toate probele au rămas în limita de siguranță și au
oprit inputul singure când armul a expirat sau când a fost cerut resetul.

Prima probă, `navmesh-roaming-3023d213-af8d-4488-85a8-89ace51272ae.json`, s-a
oprit cu `RUNTIME_ARM_EXPIRED` după `168` cadre și `93` comenzi W. A ajuns la
evenimentul `STRUCTURE_EGRESS_REACHED` pentru portalul
`access:7bb73baa2ccf348bb33511f2`, apoi a planificat a doua ieșire
`access:752513947a920bf1de1b9c15`. Aceasta este prima dovadă live că noul
egress scos din filtrarea barierelor memorate a fost ales și parcurs de
planner. Poziția fizică finală a rămas în Crypt, la
`[1658.5800363107724,1692.7742357524844]`, cu `0/71` waypoint-uri Brill.

A doua probă, `navmesh-roaming-04220853-ad05-4ee0-ab68-21f08a932a84.json`,
s-a oprit cu `RUNTIME_ARM_EXPIRED` după `179` cadre, `100` comenzi W și o
recuperare. A detectat coliziunea și a replanificat, dar nu a raportat egress
atins. Poziția finală a fost
`[1661.6598789556483,1694.704883445809]`, cu `0/71` waypoint-uri.

A treia probă, `navmesh-roaming-90501676-680b-4cb2-8077-50f4ab10e2f0.json`,
s-a oprit corect cu `RESET_REQUIRED` după `44` cadre și `44` comenzi W,
după `OBSERVED_COLLISION_REPLAN`. Poziția finală a fost
`[1660.005038131536,1694.9117385558081]`, cu `0/71` waypoint-uri. Nu a fost
moarte și nu a fost combat în niciuna dintre cele trei probe; bara de viață a
rămas plină.

Am înregistrat proba cu captură locală, deoarece `SaveShadowReplay` nu a creat
un MP4 NVIDIA nou:
`data/runtime/operator/live-video/crypt-egress-20260902-0904.mp4`
(`80.000000` secunde, `7024666` bytes). Am verificat cadrele extrase și foaia
de contact din `data/runtime/operator/live-video/inspect-0904/`. La început
camera vede peretele/tavanul, apoi Predator și Crypt se văd; nu apare moarte
sau luptă. Clipul este dovadă de diagnostic și nu dovedește încă ieșirea reală
Crypt→Brill.

După teste am retras armul runtime și am reassertat godmode-ul
(`LAB_COMBAT_PROTECTION_ON:PLAYER=Predator`). Statusul final confirmă clientul
WoW viu (`PID 53092`), `runtime_arm_present=false` și
`predator_execution_mode=OBSERVE_ONLY`.

Concluzie: patch-ul a trecut testele offline și prima probă live a făcut
progres real în planificarea ieșirii, dar problema fizică rămasă este pornirea
din concavitatea Crypt și camera care sare spre perete/tavan. Nu declarăm încă
sosire la Brill și nu pornim combat. Următorul pas este să reparăm camera și
alinierea de la pornire, apoi să repetăm o probă live filmată.

## ME-293 — Anchor-ul de egress este folosit de runner; proba live rămâne blocată în Crypt

Am reparat `integrations/windows-input/run_navmesh_roaming.py`: cele patru
ramuri care pornesc sau replanifică egress-ul folosesc acum
`StructureEgressPlan.movement_target`, adică anchor-ul verificat de client când
există, nu doar mijlocul grafic al opening-ului. Am adăugat și regresia
`test_structure_egress_runner_targets_revalidated_exit_anchor` în
`tests/test_movement_engine.py`.

Verificările offline după patch:

- `356 passed` pentru testele țintite ale movement/client/steering/combat;
- `1418 passed` pentru suita completă;
- `compileall` fără erori;
- toate cele cinci cazuri din validarea semantică au trecut, inclusiv
  Crypt→Brill (`destination_reached=true`, `131` etape);
- Monte Carlo: toate cele șase scenarii `100/100`, inclusiv hairpin, fără
  coliziuni sau eșecuri de calitate.

Am făcut apoi singura probă live permisă după aceste verificări, cu captură
locală la
`data/runtime/operator/live-video/crypt-egress-anchor-fix-20260902.mp4`
(`100.000000` secunde, `6234336` bytes). Jurnalul este
`data/runtime/navigation-f3b/results/navmesh-roaming-3868b071-f1ac-45a5-a0e3-3bfe346f9007.json`.
Rezultatul este `RUNTIME_ARM_EXPIRED`: `310` cadre, `259` comenzi W și `2`
recuperări. A raportat două `OBSERVED_COLLISION_REPLAN` și un
`CORRIDOR_RECENTER_REPLAN`, dar nu a completat niciun waypoint semantic
(`0/71`); poziția finală a rămas în Crypt, la
`[1660.9703619456013,1691.946815312488]`, cu aproximativ `1523.87` yarzi până
la Brill. Nu a fost moarte și nu a fost combat; bara de viață a rămas plină.

Am verificat foaia de contact
`data/runtime/operator/live-video/crypt-egress-anchor-fix-20260902-contact-3x2.png`.
Primele cadre arată Predator în interior, iar ultimele arată camera ridicată
spre perete/tavan; nu există ieșire vizibilă. După probă, armul a fost retras,
clientul WoW a rămas viu (`PID 53092`), modul este `OBSERVE_ONLY`, iar
godmode-ul pentru Predator a fost reassertat:
`LAB_COMBAT_PROTECTION_ON:PLAYER=Predator`.

Concluzie: codul a fost corectat să urmărească anchor-ul real de ieșire, dar
proba live încă se lovește de problema fizică de aliniere/coliziune din
concavitatea Crypt și de cameră. Nu declarăm Crypt→Brill rezolvat și nu
trecem la combat. Următorul pas este doar diagnosticarea controlată a
frontierei și a camerei, fără teleport, server truth sau input permanent.

## ME-294 — Scopul WMO rămâne activ la fiecare replanificare

Am urmărit exact cazul din video în care prima ciocnire era urmată de încă o
replanificare. Runner-ul construia un `ClientAssetNavmeshQuery` nou din lista
globală de obstacole și pierdea filtrarea scurtă pentru WMO-ul Crypt. Astfel,
discuri vechi din interior puteau închide din nou aceeași ieșire chiar după ce
egress-ul fusese verificat.

Adaptorul păstrează acum scopul WMO când lista de obstacole se schimbă, iar
runner-ul îl aplică la toate ramurile de egress și îl scoate doar după ce
anchor-ul este atins. Obstacolele din afara WMO-ului rămân active. Am adăugat
și o singură excepție strictă pentru direcție: la întoarcerea pe breadcrumb,
primul chord W poate recalibra camera/avatarul după o coliziune; limita este
un singur chord, cu abatere mică, apoi regula veche revine.

Dovezi offline după schimbare:

- `1422 passed` pentru suita completă și `291 passed` pentru testele țintite;
- `compileall` fără erori;
- cu cele șase obstacole observate în ultima probă, scopul Crypt reduce lista
  la două obstacole din afară, iar query-ul către anchor-ul
  `[1666.710938,1661.981445,141.939575]` este `complete=true`, cu `39` puncte,
  `4` detururi de doodad și `4` inseturi de clearance;
- validarea semantică rămâne `PASS` pentru toate cele cinci cazuri;
- Monte Carlo rămâne `6 x 100/100`, fără coliziuni sau eșecuri de calitate,
  inclusiv hairpin-ul.

## ME-295 — Proba live după scopul WMO: progres fizic, dar încă fără ieșire

La cererea explicită a operatorului am făcut o probă live nouă, scurtă și
înregistrată, numai pe clientul LAB local. Aprobarea de sesiune și aprobarea
F4a au fost reînnoite; godmode-ul a fost confirmat înainte și după probă cu
`LAB_COMBAT_PROTECTION_ON:PLAYER=Predator`. Nu a fost folosit teleport, memorie
de proces, server truth pentru decizie sau combat.

Jurnalul este
`data/runtime/navigation-f3b/results/navmesh-roaming-a553d477-894c-4fbe-9255-7285cbbee452.json`.
Runner-ul a trimis `256` comenzi W în `300` cadre și s-a oprit cu
`CONTROL_FRAME_BUDGET_EXHAUSTED`. A pornit din Shadow Grave, a planificat
același anchor de egress Crypt și a trecut prin două recuperări. Poziția finală
a fost `[1664.923592803203,1686.1548722325142]`, mai aproape de coridorul de
ieșire decât în proba ME-293, dar încă în Crypt; `semantic_waypoints_completed`
rămâne `0/71`, iar Brill nu a fost atins.

Față de proba anterioară, jurnalul arată două realinieri de direcție acceptate
după coliziuni (`INITIAL_FORWARD_DIRECTION_REALIGNED`) și nu mai arată
întoarcerea imediată în aceeași concavitate. Totuși, ieșirea nu este încă
stabilă: a apărut din nou o coliziune la interior, iar camera a pornit lipită
de perete/tavan înainte să revină la o vedere utilă.

Video local și foaie de contact:

- `data/runtime/operator/live-video/crypt-egress-scope-me294-20260902-run.mp4`
  (`32.000000` secunde, `2279684` bytes);
- `data/runtime/operator/live-video/crypt-egress-scope-me294-20260902-run-contact/contact-2s.png`.

După probă, armul runtime este retras, clientul WoW rămâne viu, modul este
`OBSERVE_ONLY`, iar godmode-ul este reassertat. Rezultatul este o dovadă live
de progres și diagnostic, nu o dovadă că Predator ajunge încă la Brill.

## ME-296 — Replanarea de coliziune păstrează scările egress-ului

Am urmărit traseul din ME-295 până la prima coliziune. Corridor-ul inițial era
floor-aware și avea `requested_stop.z` la nivelul ieșirii, dar replanarea de
coliziune apela `engine.plan()` numai cu X/Y. Worker-ul putea astfel să aleagă
din nou podeaua interioară a Crypt, chiar dacă anchor-ul de egress era valid.

Runner-ul folosește acum `_corridor_requested_stop_z()` pentru replanările de
coliziune și recenterizare. Picioarele temporare de clearance trimit și ele
`stop_z` pentru ancorele lor. Pentru drumurile fără `requested_stop`, valoarea
rămâne `None`, deci compatibilitatea 2D nu se schimbă.

Dovezi offline după patch:

- `293 passed` pentru testele țintite movement/client;
- `1424 passed` pentru suita completă;
- `compileall` fără erori;
- query local cu blocker-ul observat la `[1662.3941313789246,
  1687.4204528288756, 120.71875, 1.5]` și anchor-ul de egress a produs
  `complete=true`, `20` puncte, Z inițial `121.358002`, Z final
  `141.939575`, cu traseul de scară păstrat;
- nu s-a folosit teleport, server truth sau combat.

Următoarea probă permisă este una live, bounded și filmată, după validarea
semantică și Monte Carlo. Dacă video-ul arată încă doar podeaua interioară,
următorul diagnostic este camera/alinierea fizică, nu o nouă presupunere de
hartă.

## ME-297 — Proba live filmată după replanarea floor-aware

Am reînnoit sesiunea LAB, am intrat cu Predator în lume și am confirmat
protecția de damage înainte de control. Am pornit captura locală înainte de
proba bounded; nu am folosit teleport, memorie de proces, server truth pentru
decizie sau combat.

Jurnalul probei este
`data/runtime/navigation-f3b/results/navmesh-roaming-dd71e8ec-a054-48ae-839c-b563d19aa1d5.json`.
Runner-ul a executat `250` cadre și `176` comenzi W, cu `2` recuperări. A
completat `1/71` waypoint-uri, apoi armul runtime a expirat în mod fail-closed
(`RUNTIME_ARM_EXPIRED`). Poziția finală a fost
`[1671.2671492956338,1688.2234233325048]`, cu `1516.43` yarzi rămași până la
Brill. Nu a fost moarte și nu a fost combat; godmode-ul a fost reassertat după
probă cu `LAB_COMBAT_PROTECTION_ON:PLAYER=Predator`.

Video-ul este
`data/runtime/operator/live-video/crypt-egress-floor-aware-replan-20260902-run.mp4`,
iar foaia de contact este
`data/runtime/operator/live-video/crypt-egress-floor-aware-replan-20260902-contact/contact-2s.png`.
Video-ul arată Predator în aceeași cameră din Crypt pe toată durata utilă;
camera rămâne orientată spre peretele interior, iar spre final apare meniul de
siguranță. Nu se vede ieșirea și nu declarăm Crypt→Brill rezolvat.

Jurnalul confirmă două `OBSERVED_COLLISION_REPLAN`, un
`CORRIDOR_RECENTER_REPLAN` și păstrarea planului pe stratul Z verificat, dar
alinierea fizică nu a reușit să ducă personajul pe scări. După probă,
`runtime_arm_present=false`, clientul WoW a rămas viu (`PID 53092`), iar
modul a revenit la `OBSERVE_ONLY`. Următorul pas este diagnosticarea strictă a
camerei și a primei alinieri la trepte, nu o altă hartă inventată sau teleport.

## ME-298 — Prefixul partial este păstrat pentru staging-ul egress-ului

Am găsit un caz în care primul corridor către un marcaj semantic era `partial`,
dar frontiera lui avea un punct de staging complet pe aceeași podea. Runner-ul
nu mai abandonează acel prefix. Cere un corridor de lungime zero la frontieră,
alege în continuare un egress verificat și unește prefixul cu approach-ul
egress-ului. Nu sunt coordonate scrise manual.

## ME-299 — Prima probă cu prefix compus: armul a expirat

Proba live a fost filmată local după reînnoirea bounded a sesiunii și cu
`LAB_COMBAT_PROTECTION_ON:PLAYER=Predator`. Jurnalul este
`data/runtime/navigation-f3b/results/navmesh-roaming-dc36bd63-7165-4fd3-9c67-593e8a60b0dd.json`.
Au fost `288` cadre, `246` comenzi W și `4` recuperări; statusul a fost
`RUNTIME_ARM_EXPIRED`, cu `0` waypoint-uri semantice și poziția finală
`[1667.5437574413809,1692.7052840491513]`, încă în Crypt. Prima captură
`crypt-egress-partial-staging-me299-20260902-run.mp4` nu are atom MP4 final
(procesul a fost oprit forțat), deci nu este dovadă video.

## ME-300 — Ținerea heading-ului după primul chord

Am adăugat o ținere bounded a heading-ului derivat din displacement după o
realiniere acceptată. Jurnalul este
`data/runtime/navigation-f3b/results/navmesh-roaming-c69087c8-0ef5-46d3-8022-1c7c2e29bc3d.json`:
`446` cadre, `402` comenzi W, `3` recuperări, `0` waypoint-uri semantice,
`RUNTIME_ARM_EXPIRED`, poziție finală
`[1664.5558503978446,1677.8806678325514]`. Video valid de `240` secunde:
`data/runtime/operator/live-video/crypt-egress-heading-hold-me300-20260902-run.mp4`.
Cadrele arată Predator în Crypt, iar după aproximativ un minut camera ajunge
din nou la perete/tavan; nu se vede moarte sau combat.

## ME-301 — Repetare cu meniu închis înainte de start

Am închis meniul vizual, am restaurat camera și am reassertat godmode înainte
de test. Jurnalul este
`data/runtime/navigation-f3b/results/navmesh-roaming-9a691f96-2b08-4d1c-9b56-43ed9430785f.json`:
`367` cadre, `300` comenzi W, `3` recuperări, `1/71` waypoint semantic,
`RUNTIME_ARM_EXPIRED`, poziție finală
`[1671.2671492956338,1680.5008325592062]`. Video valid de `180` secunde:
`data/runtime/operator/live-video/crypt-egress-repeat-me301-20260902-run.mp4`.
Meniul a reapărut în captură deoarece runner-ul încă primea flag-ul vechi de
dismiss la start; captura rămâne diagnostică, nu dovadă de ieșire.

## ME-302 — Test curat, fără dismiss-ui la start

Am închis meniul separat, am restaurat camera home, am ținut protecția
Predator ON și am pornit runner-ul fără `--dismiss-ui-at-start`. Jurnalul este
`data/runtime/navigation-f3b/results/navmesh-roaming-6126621c-8dc2-4c10-b093-88350bf44898.json`:
`375` cadre, `254` comenzi W, `4` recuperări, `1/71` waypoint, status
`RUNTIME_ARM_EXPIRED`, poziție finală
`[1670.5316644849172,1683.258900692527]`. Video valid de `180` secunde:
`data/runtime/operator/live-video/crypt-egress-clean-ui-me302-20260902-run.mp4`.
Cadrele verificate arată Predator vizibil la început, apoi camera se ridică
spre tavan, iar personajul rămâne în aceeași cameră. Nu declarăm încă
Crypt→Brill rezolvat și nu pornim combat.

## ME-303 — Verificări offline după ultimele schimbări

`compileall` a trecut. Suita completă a avut `1424 passed`; cele două teste
PowerShell care au părut roșii în terminal au trecut la rerulare fără terminal
interactiv (`2 passed`), fiind doar împachetarea mesajului pe linie. Validarea
semantică este `PASS` în
`data/runtime/navigation-f3b/semantic-road-journey-validation-me303.json`.
Monte Carlo este în
`data/runtime/navigation-f3b/steering-monte-carlo-20260902-me303-egress-calibration.json`:
șase scenarii, fiecare `100/100`, fără coliziuni și fără eșecuri de calitate.

După ME-302 am retras armul de mișcare și am reassertat
`LAB_COMBAT_PROTECTION_ON:PLAYER=Predator`. Clientul WoW a rămas viu (`PID
53092`); nu am pornit sau oprit jocul ori procesele Hermes. Pentru următoarea
probă live este necesară o aprobare bounded nouă; până atunci nu se trimite
input.

## ME-304 — Runnerul a așteptat armul cu amprenta veche

O probă intermediară a rămas în așteptare deoarece autorizația continuă a fost
înlocuită după ce runnerul își citise amprenta. Am oprit doar procesele
runnerului și worker-ele lui, nu jocul și nu Hermes. Rezultatul ulterior
`navmesh-roaming-f7d57d7f-de17-4a15-b2bd-8a4cd712df51.json` a executat `421`
cadre, `336` comenzi W, `2` recuperări și `1/67` waypoint semantic, apoi a
expirat bounded (`RUNTIME_ARM_EXPIRED`) la
`[1663.4985909824395,1690.5677812458275]`. Godmode a fost pornit și nu a fost
moarte sau combat. Nu folosim captura acelei încercări ca video pereche.

## ME-305 — Proba live filmată după corectarea amprentei

Am lăsat aceeași autorizație continuă să fie citită înainte de preflight, apoi
am reînnoit doar revalidarea scurtă și armul. Jurnalul este
`data/runtime/navigation-f3b/results/navmesh-roaming-4bee78c7-218f-4b06-b588-05f107a4ed62.json`:
`383` cadre, `231` comenzi W, `2` recuperări, `1/67` waypoint semantic și
`RUNTIME_ARM_EXPIRED`, la poziția finală
`[1664.6937537998542,1692.291573829153]`. Bara de viață a rămas plină; nu a
fost moarte și nu a fost combat. Protecția a fost reassertată după probă.

Video valid de `180` secunde:
`data/runtime/operator/live-video/crypt-egress-recorded-me305-20260902-run.mp4`.
Am verificat cadrele la `0`, `60`, `120`, `150` și `170` secunde. La început și
în mijloc Predator este vizibil în Crypt, iar apoi camera se ridică din nou la
perete/tavan. Asta arată că blocajul rămas este controlul camerei/alinierea
fizică, nu lipsa unei deschideri în WorldPack. După test,
`runtime_arm_present=false`, clientul WoW a rămas viu (`PID 53092`), iar modul
a revenit la `OBSERVE_ONLY`.

## ME-306 — Validator offline PASS, dar calibrarea fizică din Crypt încă eșuează

Am adăugat o regulă generică pentru cazul în care axa minimapului are două
capete posibile: înainte de primul W, o orientare fallback este întoarsă numai
dacă este clar opusă primei tangente locale din navmesh. Nu se adaugă poziții
de Cryptă și nu se folosește server truth. Testele țintite au trecut `3/3`,
suita completă `1429 passed`, iar `compileall` a trecut.

Validatorul semantic este `PASS` în
`data/runtime/navigation-f3b/semantic-road-journey-validation-me306-minimap-axis.json`:
Crypt spawn→Brill, Deathknell→Brill și Brill→Deathknell ajung; cazul de deal
este respins corect cu `RESET_REQUIRED`. Simularea este în
`data/runtime/navigation-f3b/steering-monte-carlo-20260902-me306-minimap-axis.json`:
șase scenarii, fiecare `100/100`, fără coliziuni și cu `quality_pass_rate=1.0`.

Singurul test live bounded a fost filmat cu godmode ON. Jurnalul este
`data/runtime/navigation-f3b/results/navmesh-roaming-fe3e7d29-1669-4260-8f2a-5ab7e2d64387.json`:
`419` cadre, `325` comenzi W, `3` recuperări, `1/71` waypoint-uri semantice și
status `RUNTIME_ARM_EXPIRED`; Predator a rămas viu și nu a intrat în combat.
Poziția finală a fost `[1663.72842998579,1684.43107964919]`, încă în Cryptă.

Video valid de `180` secunde:
`data/runtime/operator/live-video/crypt-egress-after-axis-flip-me306-20260902-run.mp4`.
Cadrele verificate la `0`, `30`, `60`, `90`, `120`, `150` și `170` secunde arată
personajul în Cryptă la început, apoi camera lipită de tavan/perete. Jurnalul
arată că orientarea de control a rămas
`MOUSE_INTEGRATED_MINIMAP_FALLBACK`, iar evenimentul
`INITIAL_MINIMAP_AXIS_ORIENTED_TO_CORRIDOR` nu a apărut. Așadar navmesh-ul știe
ieșirea, dar legătura dintre poziția locală, fața corpului și camera WoW încă
nu este stabilă. Nu declarăm Crypt→Brill rezolvat și nu trecem la combat.

După probă, armul runtime a fost retras, protecția `LAB_COMBAT_PROTECTION_ON:PLAYER=Predator`
a fost reassertată, clientul WoW a rămas viu (`PID 53092`), iar modul este
`OBSERVE_ONLY`. Următorul pas este o calibrare fail-closed a feței corpului la
egress (sau oprire când HUD-ul exact lipsește), nu o hartă nouă și nu teleport.

## ME-307 — Separarea poziției exacte de orientarea estimată (offline)

Am comparat cuvânt-cu-cuvânt handoff-ul anterior și artefactele video locale.
Video-ul vechi `data/runtime/operator/live-video/reference-old-crypta-deathknell-mobile.mp4`
arată camera stabilă și Predator ieșind din Cryptă; pagina YouTube legată în
discuție este acum indisponibilă, iar pagina Gofile nu redă video în browser.

Diferența tehnică este clară: în run-ul vechi, jurnalul a folosit
`VISIBLE_CLIENT_HEADING_FUSED` în `3447/3447` cadre; în ME-306 a folosit
`MOUSE_INTEGRATED_MINIMAP_FALLBACK` în `369` cadre. X/Y nu a dispărut: ME-306
are poziții fresh și `PRECONTROL_POSE_REFRESHED`. A lipsit dovada unui yaw exact.

Am verificat și SavedVariables-ul curent: există `map_position_snapshot` cu
`available=true`, dar nu există niciun `facing_rad`. Addonul instalat este
byte-identic cu copia din repo și încearcă opțional `GetPlayerFacing()`, însă
API-ul nu este disponibil în mod normal pe TBC 2.4.3. De aceea fuziunea veche
nu trebuie numită „poziție și orientare exacte”.

Offline, addonul declară acum `api_capabilities.player_facing_api`, iar schema
permite această capabilitate. Runner-ul are poarta explicită
`--require-exact-body-heading`; ea oprește fail-closed dacă heading-ul vine din
minimap, mouse sau displacement. Testele noi pentru poartă trec împreună cu
regresia offline. Nu s-a reîncărcat WoW, nu s-a schimbat procesul live și nu s-a
pornit alt test.

## ME-308 — Restaurarea fuziunii vizuale verificate (offline)

Am comparat trace-ul vechi bun cu ME-306 printr-un replay read-only al
markerului vizibil și al temporizării comenzilor mouse. Run-ul vechi are
`VISIBLE_CLIENT_HEADING_FUSED` în `3447/3447` cadre. ME-306 are marker vizibil
în `419/419` cadre, dar branch-ul runtime îl ocolea și înregistra doar fallback
mouse/displacement. După schimbarea offline, replay-ul aplică fuziunea bounded
în `419/419` cadre: `195` cadre `VISIBLE_CLIENT_HEADING_FUSED` și `223` cadre
`VISIBLE_CLIENT_HEADING_AXIAL_FLIP_FUSED`; corecția maximă este `0.25` rad.

Schimbarea este în
`integrations/windows-input/run_navmesh_roaming.py`: când sursa este
`MINIMAP_VISION_FALLBACK`, `VisibleHeadingObserver` este din nou autoritatea
pentru headingul estimat. Displacement-ul rămâne diagnostic/calibrare și nu
poate suprascrie headingul prin wall-slide. Replay-ul este în
`data/runtime/navigation-f3b/heading-replay/me308-fused-heading-replay.json`.

În plus, înainte de primul W, `_orient_initial_fallback_heading_to_corridor`
poate orienta și rezultatele `VISIBLE_CLIENT_HEADING_INITIAL/FUSED` către
tangenta locală când axa minimapului este clar inversată. Nu schimbă unghiuri
normale de viraj și nu inventează coordonate.

Regresia are teste dedicate în `tests/test_heading_fusion_replay.py` și
`tests/test_movement_engine.py`. Verificarea țintită a trecut `213` teste, iar
suita completă a trecut `1433 passed`; `compileall` și `git diff --check` au
trecut. Nu s-a reîncărcat addonul, nu s-a modificat clientul live și nu s-a
pornit test live. Următorul pas este verificarea camerei și replay-ul
Cryptă-egress, apoi numai după PASS offline se poate cere testul live bounded.

## ME-309 — Detector offline pentru pierderea actorului și blocarea driftului camerei

Am verificat că HUD-ul CRC nu spune dacă Predator mai apare în imagine: în
filmarea ME-306 coordonatele rămân vizibile după ce camera ajunge la tavan.
Am adăugat `player_actor_detector.py`, un adaptor read-only foarte conservator
care caută două componente neutru-luminoase în zona centrală (capul și
sprijinul corpului). Profilul este
`config/pose/player-actor-anchor-tbc243-predator-v1.json` și are starea
`retained_video_candidate`, nu „live verificat”.

Pe cadrele păstrate, detectorul a raportat `VISIBLE` la `0s` și `30s`, apoi
`LOST` la `60s`, `90s`, `120s`, `150s` și `170s`, exact când filmarea arată
tavanul/peretele fără Predator. Testele de contract și detector sunt în
`tests/test_player_actor_detector.py` și `tests/test_camera_integrity.py`.

Runner-ul publică dovada în `camera_integrity`, armează poarta numai după
restaurarea camerei home și eliberează mișcarea când actorul dispare. Am adăugat
și o regulă explicită: cadrele de navigație nu pot avea mișcare verticală a
mouse-ului; pitch-ul rămâne doar o recuperare de prezentare bounded. Nu s-a
reîncărcat addonul și nu s-a pornit test live.

## ME-310 — Verificare offline după poarta de integritate

Am rerulat suita completă după detector și poartă: `1445 passed`. Testele
țintite pentru cameră, detector, runner și Movement Engine au trecut `312/312`;
`compileall` și `git diff --check` au trecut.

Validatorul de drum semantic a trecut în
`data/runtime/navigation-f3b/semantic-road-journey-validation-me309-camera-gate.json`:
Crypt spawn→Brill, Deathknell→Brill și Brill→Deathknell ajung, iar cazul de
deal este respins corect cu `RESET_REQUIRED`. Aceasta este dovadă WorldPack și
replay offline; nu este dovadă că inputul ajunge în client.

Replay-ul de steering pe un coridor WorldPack are `100/100` execuții de
calitate, `0` coliziuni și `96,7%` observații MPPI în
`data/runtime/navigation-f3b/crypt-egress-offline-replay-me310.json`.
Cele șase scenarii de steering au fiecare `100/100`, fără coliziuni, în
`data/runtime/navigation-f3b/steering-monte-carlo-20260902-me310-camera-gate.json`.

Poarta rămâne nepromovată live: profilul actorului este încă
`retained_video_candidate`, iar controlul se oprește dacă Predatorul dispare
din cadru sau detectorul devine necunoscut. Nu s-a reîncărcat addonul, nu s-a
trimis input nou și nu s-a pornit test live.

## ME-311 — Auditul WorldPack după regresia de cameră

Am verificat offline profilurile WorldPack pentru Azeroth, Tirisfal–Silverpine,
Kalimdor și World Continents. Toate patru se deschid și au hash-ul intern
corect, fără client, server sau input. Replay-ul de drum rămâne separat de
aceste verificări.

Auditul complet al registrului este în
`data/runtime/navigation-f3b/world-map-registry-audit-me310.json`: sunt
inventariate `83` hărți, `35` apar în coada de bake, `4` au bake complet, dar
doar `1` este `autonomous_ready` (Azeroth), deoarece celelalte încă nu au
catalog semantic complet și/sau graf de structuri promovat. Asta este starea
reală; nu declarăm toate continentele gata.

## ME-312 — Poarta respinge și geometria actorului invalidă

Am întărit regula camerei: `VISIBLE` nu este suficient doar cu un obiect
nevid. Anchor-ul trebuie să aibă toate cele șase margini/centre normalizate,
cu lățime și înălțime pozitive; altfel controlul este respins fail-closed.
Aceasta repară cazul în care un detector defect ar fi raportat actor vizibil
fără formă reală.

Regresia finală a trecut `1446` teste, inclusiv `109` teste țintite pentru
camera, detector și runner. Nu s-a reîncărcat addonul și nu s-a pornit test
live.

## ME-313 — Portabilitate WorldPack pe continente (offline)

Am rulat validatorul de portabilitate pe trei pachete independente:
Azeroth v3, Kalimdor v1 candidate și World Continents v1. Rezultatul este
`PASS` pentru `5` mapări (Azeroth, Kalimdor și Expansion01); toate coridoarele
de probă sunt complete, iar politica de evitare dinamică a rămas bounded
(`AVOID` sau `YIELD`). Raportul este
`data/runtime/navigation-f3b/standalone-movement-portability-me313.json`.

Acesta confirmă că adapterul poate citi topologia din pachete diferite fără
client sau server. Nu confirmă încă o rută live pe Kalimdor/Expansion01 și nu
promovează automat aceste hărți în Control Center.

## ME-314 — Starea topografică nu mai este confundată cu starea autonomă

Registrul expune acum `topographic_ready` separat de `autonomous_ready`.
Primul cere doar WorldPack-ul, indexul de structuri și graful de acces pentru
aceeași hartă; al doilea cere în plus catalog semantic. Auditul curent are
`5` profile topografice gata și `1` profil autonom gata. Control Center afișează
`TOPOGRAFIC • catalog semantic lipsă` și păstrează startul autonom blocat.

Schimbarea este documentată în ADR-0091 și în contractul de audit (câmpuri
opționale pentru compatibilitate cu rapoartele vechi). Testele de registry și
UI trec `38/38`, iar verificarea de portabilitate pentru cele trei WorldPack-uri
rămâne `PASS`. Nu s-a pornit live.

## ME-315 — Portabilitatea egress cu artefacte și worker potrivite (offline)

Validatorul de egress a fost rulat cu perechi care au aceeași identitate de
WorldPack, index, graph și `pa_nav_probe-v34`. Azeroth v3 și Shadowfang v2 au
trecut împreună `PASS`; artefactul este
`data/runtime/navigation-f3b/structure-egress-portability-me315.json`.
Încercarea cu indexul Shadowfang v1 vechi a fost respinsă corect deoarece îi
lipsesc câmpuri obligatorii noi, iar graph-urile Tirisfal v5 și Shadowfang v1
au fost respinse când worker-ul nu corespundea. Niciuna dintre aceste verificări
nu a atins clientul sau serverul.

## ME-316 — Bake queue legat de rădăcina reală (offline)

Am regenerat queue-ul fără să schimb queue-ul vechi: `bake-queue-full-v1.json`
folosește rădăcina existentă cu BVH, navmesh și semantică pentru Azeroth,
Kalimdor, Expansion01 și Shadowfang. Rezultatul este `4/35` hărți complete,
`3.610` ADT-uri eligibile și `4.511` artefacte BVH. Auditul nou este
`data/runtime/navigation-f3b/world-map-registry-audit-me316.json`; el arată
clar că doar o hartă este încă `autonomous_ready`.

## ME-317 — Deadmines v2: WorldPack și geometrie structurală (offline)

Deadmines a fost făcut într-o rădăcină nouă cu MapBuilder pinned v5. Bake-ul a
trecut `36/36` ADT-uri, iar auditul structural Detour a trecut `36/36` fără
eșecuri. Prima încercare v1 a rămas păstrată separat și a avut cinci tile-uri
degenerate; nu a fost promovată. v2 a fost sigilat și verificat la
`E:\\WoWserver\\PerfectAssassin-Runtime\\worldpacks\\tbc243-deadmines-v2`
cu `runtime_ready=true` și hash
`6ca07a617241bd0c42f7cfd679c990a830412f46da1510f7ce731db7cff27aa9`.

Indexul topografic are `36` tile-uri, `12` WMO și `267` doodad-uri. Scanarea
read-only a făcut `336/336` probe, cu zero erori de worker; graph-ul are patru
deschideri confirmate, dar rămâne `PARTIAL_OBSERVED_COMPONENTS` deoarece unele
structuri nu au fost confirmate complet. Artefactele sunt în
`data/runtime/client-catalog/tbc243-8606/deadmines-v2-*`. Deadmines nu este
declarat autonom și nu s-a pornit live.

## ME-318 — Portabilitate offline cu Deadmines inclus

Validatorul de portabilitate a rulat pe trei WorldPack-uri independente:
Azeroth v3, Shadowfang v2 și Deadmines v2. Rezultatul este `PASS` pentru
`3/3` mapări, fără client, server sau input. Pentru Shadowfang și Deadmines,
unele coridoare de probă sunt încă parțiale; aceasta rămâne vizibilă în raport
și nu acordă autonomie. Artefactul este
`data/runtime/navigation-f3b/standalone-movement-portability-me318.json`.

## ME-319 — Audit de registry cu queue-uri din rădăcini separate

Coada continentală și coada Deadmines folosesc rădăcini WorldPack diferite.
Auditul registry acceptă acum mai multe queue-uri, păstrează referințele lor și
alege starea cea mai completă pentru același `map_id`; conflictele la aceeași
stare sunt respinse. Auditul combinat
`data/runtime/navigation-f3b/world-map-registry-audit-me319.json` arată
`5` hărți cu bake complet, `6` topografice și doar `1` autonomă. Deadmines este
corect `COMPLETE` în queue, dar rămâne `autonomous_ready=false` deoarece nu are
catalog semantic. Testele țintite după schimbare trec `39/39`, iar suita
offline completă trece `1448/1448`; `compileall` și `git diff --check` sunt
curate. Nu s-a pornit testul live.

## ME-320 — RazorfenKraul v2: bake, geometrie și WorldPack (offline)

Am construit RazorfenKraul pe o rădăcină nouă, folosind doar asset-urile pinned
ale clientului TBC 2.4.3. Bake-ul este `COMPLETE`: `6/6` ADT-uri au navmesh,
BVH și semantică de drum, iar auditul geometric a trecut `6/6` tile-uri cu
`0` eșecuri. Recast a raportat diagnostice (`243` erori de contur și `526`
avertismente), dar niciun tile nu a eșuat; acestea rămân scrise în raport și
nu sunt ascunse.

WorldPack-ul sigilat și verificat este
`E:\\WoWserver\\PerfectAssassin-Runtime\\worldpacks\\tbc243-razorfen-v2`,
cu `runtime_ready=true`, `466` artefacte și hash
`8014951207d52e21dc186af6b05326f6d03b70703bf71c4185e4266983743fbd`.
Profilul are `execution_authority=false`; nu cere client, server sau emulator.

## ME-321 — RazorfenKraul: structuri și acces observat (offline)

Indexul topografic conține `395` structuri (`5` WMO și `390` doodad-uri) pe
`6` tile-uri. Scanarea read-only a rulat `147/147` probe, cu `0` erori de
worker; a acceptat `1` observație și a găsit `4` deschideri. Graful rămâne
`PARTIAL_OBSERVED_COMPONENTS`, deoarece nu toate componentele au fost
confirmate. În registry, Razorfen este `topographic_ready=true`, dar
`autonomous_ready=false` și nu primește input.

## ME-322 — Portabilitate și steering Razorfen (offline)

Validatorul de portabilitate a trecut `4/4` WorldPack-uri independente:
Azeroth, Shadowfang, Deadmines și Razorfen. Pentru Razorfen, singurul coridor
rezolvat a trecut `100/100` simulări, cu `0` coliziuni; MPPI a fost activ în
aproximativ `96,7%` din observații. O a doua cerere a rămas corect în raport ca
`ENDPOINT_UNAVAILABLE` după refuzul awareness serverului de test; nu am
inventat un punct de sosire și nu am promovat harta autonom.

## ME-323 — Regresie offline după Razorfen

Suita completă rămâne `1448/1448 OK` (`111,1` secunde). `compileall` și
`git diff --check` sunt curate. Auditul combinat al registry-ului are acum
`6` hărți cu bake complet, `7` topografice și doar `1` autonomă. Nu s-a
reîncărcat addonul, nu s-a trimis input și nu s-a pornit test live.

## ME-324 — Catalog RouteTeacher complet, cu ID-uri stabile (offline)

Importul catalogului Zygor se oprea înainte de scriere: ID-urile mai lungi de
128 de caractere erau tăiate și mai multe etape deveneau identice. Scurtarea
folosește acum un prefix lizibil și hash-ul ID-ului complet. Limita contractului
`knowledge_broker_catalog` a fost ridicată la `16.384` intrări, suficient pentru
ghidurile TBC selectate.

Catalogul Horde a fost construit cu `5.838` pași, iar cel Alliance cu `5.821`.
Intrările sunt `worldpack` advisory, au `confidence=0,75`, provenance RouteTeacher
și coordonate 2D marcate `STATIC_SOURCE_CANDIDATE`. Fișierele originale nu sunt
copiate în repo; ieșirile sunt doar artefacte locale în
`data/runtime/navigation-f3b/zygor-leveling-*-tbc243-catalog.json`.

## ME-325 — Catalog static NPCData pentru traineri și NPC-uri (offline)

Am adăugat un builder separat pentru exportul user-owned `NPCData.lua`. Catalogul
local are `3.255` intrări: `286` traineri de clasă, `287` traineri de profesie
și `2.682` NPC-uri statice. Toate folosesc `map_scope=zone_area`, confidence
`0,70`, provenance explicit și coordonate 2D statice; nu sunt confundate cu
poziții live și nu pot acorda input. Builder-ul cere binding explicit pentru
fiecare map-area și oprește importul când lipsește.

Artefactul local este
`data/runtime/navigation-f3b/zygor-npcdata-tbc243-catalog.json`; testul de
reproducere verifică și că ieșirea este identică la aceeași sursă. ADR-0094
descrie limita și separarea de WorldPack.

## ME-326 — Regresie după catalogele RouteTeacher și NPCData (offline)

Suita completă a trecut `1451/1451 OK` în `110,7` secunde. `compileall` și
`git diff --check` sunt curate. Catalogele noi rămân locale și advisory;
registry-ul WorldPack nu a fost promovat, nu s-a acordat autonomie, nu s-a
reîncărcat addonul și nu s-a pornit test live.

## ME-327 — Separarea pauzei live de logica offline și reluare bounded (offline)

Ultima urmă live a arătat două lucruri importante: planificarea offline era
validă, dar între cadrele 27 și 28 exista o pauză de `9,341 s`, urmată de un
șir lung de pivotări. Pauza venea din recalcularea sincronă a coridorului după
o abatere mică a primei corzi, nu dintr-o lipsă dovedită în WorldPack. Codul
nu mai face această recalculare pentru o abatere sub `2,0` yarzi: păstrează
coridorul verificat și lasă pivotul bounded să corecteze orientarea. Pentru o
abatere mai mare, replanificarea rămâne activă și bounded.

Fiecare `CONTINUOUS_FRAME` scrie acum `observation_gap_s`,
`observation_latency_ms` și `capture_latency_ms`. Sursa live eliberează
controalele dacă numai capturarea sau întreaga decodare trece de lease-ul de
`450 ms`; callback-ul este release-only și nu prelungește niciun arm.

Supervisorul poate relua o felie după `RUNTIME_ARM_EXPIRED` numai dacă este
pornit explicit cu `--resume-on-runtime-arm-expiry` și un wait pozitiv. El
trimite o singură dată checkpoint-ul către copilul următor, care așteaptă un
arm nou emis de operator; nu există rearmare automată sau prelungire ascunsă.
Control Center folosește wait-ul bounded de `120 s`.

Replay-ul offline al secvenței reale Crypt→Brill→Crypt a trecut în testul
`test_offline_crypt_brill_crypt_sequence_replays_in_canonical_order`, iar
coridoarele WorldPack au trecut separat pentru Crypt→Brill și Brill→Crypt în
`data/runtime/navigation-f3b/semantic-road-journey-validation-me327.json` și
`data/runtime/navigation-f3b/semantic-road-journey-validation-me327-brill-to-crypt.json`.
Ambele rapoarte sunt `PASS`, fără client, server sau input.

Regresia completă după schimbare este `1459/1459 OK`; testele țintite pentru
supervisor, runner, UI și replay sunt verzi, iar `compileall` și
`git diff --check` sunt curate. Nu s-a reîncărcat addonul și nu s-a pornit
testul live; următorul test live rămâne o singură felie filmată și necesită
confirmare explicită.

Auditul pe toate cele 12 cerințe, cu stările `PASS`, `PARTIAL` și `PENDING`,
este păstrat în
`docs/MOVEMENT_ENGINE_REQUIREMENT_AUDIT_2026-09-02.md`.

## ME-328 — Diagnostic live și protecție post-plan (offline)

Urma live curentă
`data/runtime/navigation-f3b/results/navmesh-roaming-fe3e7d29-1669-4260-8f2a-5ab7e2d64387.json`
arată că problema apare în puntea de heading, nu în prima verificare a
WorldPack-ului: după `HEADING_READY_BEFORE_CONTROL` cu facing exact,
refresh-ul de după plan a devenit `MOUSE_INTEGRATED_MINIMAP_FALLBACK`. Au fost
`369/419` cadre cu această sursă, `36/58` comparații cu divergență peste un
radian (maxim `3,13` radiani), abatere de până la `4,97` yarzi și patru
replanificări de recenter înainte de `RUNTIME_ARM_EXPIRED`.

Runner-ul păstrează acum headingul exact anterior pentru acel singur refresh
post-plan, cu sursa explicită `COORDINATE_HUD_EXACT_PRESERVED`; nu îl tratează
ca facing HUD proaspăt și nu îl extinde în bucla de mișcare. ADR-0097 descrie
decizia, iar testele offline o reproduc fără client sau input.

Replay-ul read-only al aceleiași urme arată că valorile `player_facing_rad`
existau în toate cele `419` cadre: fuziunea bounded ar fi produs `419/419`
cadre `VISIBLE_CLIENT_HEADING_*`, cu corecție maximă `0,25` radiani. Asta
separă clar datele vizibile de ramura runtime care le-a înregistrat ca fallback;
nu este un test live nou și nu acordă autoritate de input. Raportul este
`data/runtime/navigation-f3b/heading-replay/me328-live-trace-recheck.json`.

Regresia completă după schimbare este `1462/1462 OK`; `compileall` și
`git diff --check` sunt curate. Nu s-a pornit un test live nou.

## ME-329 — Separarea headingului calculat de facing-ul brut (offline)

Pentru următoarea probă, fiecare `HEADING_READY_BEFORE_CONTROL` și fiecare
`CONTINUOUS_FRAME` păstrează separat `heading_source` și
`client_facing_source`. Astfel vedem dacă jocul a dat un facing exact sau dacă
runner-ul a căzut pe minimapă, fără să confundăm cele două lucruri. Replay-ul
numără acum și sursele brute; o urmă veche care nu are câmpul rămâne validă,
dar apare ca neînregistrată, nu ca facing exact.

Replay-ul urmei ME-328, care a fost scrisă înaintea câmpului nou, marchează
explicit `419` cadre fără sursă brută (`client_facing_source_complete=false`).
Testele țintite au trecut `6/6`, iar regresia completă a rămas `1462/1462 OK`.
Schimbarea este doar de telemetrie și replay offline; nu pornește clientul, nu
trimite input și nu schimbă ruta live.

## ME-330 — Fuziunea vizibilă rămâne prioritară în calibrarea bounded (offline)

Am găsit o regresie în ordinea surselor: după o realiniere inițială, fereastra
de `12` cadre putea înlocui un heading vizual proaspăt cu
`DISPLACEMENT_INITIAL_DIRECTION_CALIBRATION`. Codul păstrează acum orice
`VISIBLE_CLIENT_HEADING_*` și consumă normal cadrul de calibrare; displacement-ul
mai este folosit doar când vederea nu oferă heading. `COORDINATE_HUD_EXACT`
închide în continuare fereastra imediat. Decizia este în ADR-0098.

Testul nou și testele țintite au trecut, iar regresia completă este
`1463/1463 OK`. Nu s-a pornit clientul live și nu s-a trimis input.

## ME-331 — Poarta de completitudine a sursei brute (offline)

Evaluatorul de urmă raportează acum separat cadrele care au o
`client_facing_source` utilizabilă. Câmpul lipsă sau valoarea `UNAVAILABLE`
înseamnă dovadă incompletă. Modul diagnostic păstrează compatibilitatea cu
urmele istorice, iar `--require-client-facing-source` activează poarta strictă
pentru o probă live viitoare.

Aplicat pe urma ME-328: `0/419` cadre cu sursă brută, deci
`frames_missing_client_facing_source=419` și eșec explicit
`missing_client_facing_source`, pe lângă faptul că ruta nu a ajuns la
destinație. Testele țintite au trecut `10/10`. Nu s-a pornit clientul live și
nu s-a trimis input. Decizia este în ADR-0099.

## ME-332 — Separarea body yaw / camera yaw în urme (offline)

Runner-ul scrie acum pe fiecare cadru de control observația brută a yaw-ului
corpului, sursa ei, estimarea yaw-ului camerei integrată din mouse și diferența
bounded dintre canale. Estimarea camerei este etichetată explicit ca estimare;
nu este citire directă și nu este server truth. Evaluatorul strict poate cere
prezența tuturor celor trei valori prin `--require-body-camera-separation`.

Pe urma ME-328, separarea este incompletă în toate cele `419` cadre, deoarece
urma a fost creată înaintea telemetriei noi. Testele țintite au trecut, iar
regresia completă curentă este `1469/1469 OK`. Nu s-a pornit clientul live și nu
s-a trimis input. Raportul strict este
`data/runtime/navigation-f3b/heading-replay/me332-live-trace-quality-strict.json`.
Decizia este în ADR-0100.

## ME-333 — Poarta strictă pentru integritatea camerei (offline)

Evaluatorul de trace are acum și câmpurile `camera_integrity_frames`,
`frames_missing_camera_integrity` și `camera_integrity_complete`. Opțiunea
`--require-camera-integrity` cere ca fiecare cadru continuu să aibă
`camera_integrity_state=VISIBLE` și confidence de cel puțin `0,55`, aceeași
limită folosită de poarta runtime pentru ancora vizuală a Predatorului.
Urmele istorice rămân citibile în modul diagnostic, dar nu pot fi declarate
complete când actorul nu este demonstrat pe ecran.

Aplicată urmei ME-328 împreună cu porțile de sursă facing și separare
body/cameră, verificarea strictă raportează `0/419` cadre complete și
`missing_camera_integrity`, pe lângă lipsa celorlalte două grupuri de câmpuri.
Raportul este
`data/runtime/navigation-f3b/heading-replay/me333-live-trace-quality-strict.json`.
Testele dedicate trec `2/2` pentru noua poartă; nu s-a pornit live, nu s-a
reîncărcat WoW și nu s-a trimis input. Regresia completă curentă este
`1471/1471 OK`, iar `compileall` și `git diff --check` sunt curate (avertismentul
LF→CRLF pentru `.gitignore` este preexistent și non-fatal). Decizia este în
ADR-0101.

## ME-334 — Audit WorldPack reîmprospătat din queue-uri separate (offline)

Auditul read-only combină queue-ul continental cu queue-urile Deadmines v2 și
Razorfen v2, alegând doar starea completă mai bună pentru același `map_id` și
respingând conflictele la aceeași stare. Rezultatul este
`data/runtime/navigation-f3b/world-map-registry-audit-me334.json`:
`83/83` identități de hartă, `35` mapări în queue, `6` bake-uri complete,
`7` hărți topografice și `1` hartă autonomă (`Azeroth`). Kalimdor, Expansion01,
Shadowfang, Deadmines și Razorfen au artefacte topografice, dar fără catalog
semantic complet rămân `OBSERVE_ONLY`. Nu s-a pornit map bake, WoW reload,
input live sau combat. Dovada nu schimbă registry-ul runtime.

## ME-335 — Integritatea conținutului din trace (offline)

Poarta strictă nu acceptă doar o etichetă text. `client_facing_source` trebuie
să fie una dintre sursele emise de runtime (`COORDINATE_HUD_EXACT` sau
`MINIMAP_VISION_FALLBACK`) și să aibă yaw brut finit. Pentru separarea
body/cameră, delta înregistrată trebuie să fie egală cu diferența unghiulară
înfășurată, cu toleranță de `0,001` radian; confidence-ul camerei este limitat
la `[0,55, 1,0]`.

Astfel, o urmă nu poate trece doar pentru că are câmpurile completate manual.
Testele dedicate pentru verificarea sursei și a delta-ului trec `3/3`, iar
raportul strict al urmei vechi rămâne `0/419` cadre complete. Raportul reprodus
după întărire este
`data/runtime/navigation-f3b/heading-replay/me335-live-trace-quality-strict.json`.
Schimbarea este strict offline; nu s-a pornit live, nu s-a reîncărcat WoW și nu
s-a trimis input.
Regresia completă după această întărire este `1474/1474 OK`.

## ME-336 — Replay-ul folosește aceeași poartă de sursă (offline)

`scripts/replay_heading_fusion.py` folosește acum aceeași allowlist de surse
(`COORDINATE_HUD_EXACT`, `MINIMAP_VISION_FALLBACK`) și cere yaw brut finit.
Etichetele necunoscute sunt numărate separat în
`invalid_client_facing_source_frames` și nu pot face urma completă. Testul
dedicat trece `1/1`; toate operațiile rămân read-only și `input_emitted=false`.

## ME-337 — Poartă bounded pentru heading live proaspăt (offline)

Urma live veche și filmarea ShadowPlay au confirmat aceeași problemă: camera
poate ajunge în perete sau tavan, iar bucla rămâne pe
`MOUSE_INTEGRATED_MINIMAP_FALLBACK`. Am adăugat politica pură
`src/perfect_assassin/movement/heading_integrity.py`.

Înainte de fiecare cadru de control, un heading curent este acceptat numai
dacă are sursă brută cunoscută (`COORDINATE_HUD_EXACT` sau
`MINIMAP_VISION_FALLBACK`) și rezultat vizibil/fuzionat. Dacă facing-ul lipsește,
ultimul heading vizual poate fi ținut cel mult `0,30 s`; apoi runner-ul
eliberează inputul, scrie `HEADING_EVIDENCE_LOST` și încheie felia bounded.
Au fost adăugate câmpurile `heading_integrity_state`,
`heading_integrity_evidence_age_s` și `heading_integrity_reason` în trace.

Testele dedicate pentru politica nouă și poarta runner-ului trec `8/8`.
Schimbarea este strict offline: nu s-a pornit WoW, nu s-a reîncărcat addonul și
nu s-a trimis input. Testul live final rămâne `PENDING` și necesită confirmare
explicită.

## ME-338 — Replay live-shaped și potrivirea sursei headingului (offline)

Am adăugat `scripts/replay_heading_integrity.py`. El aplică aceeași poartă
bounded pe o urmă veche și se oprește la primul cadru care nu are dovadă
vizuală. Pe urma ME-328, rezultatul este
`data/runtime/navigation-f3b/heading-replay/me337-live-shaped-heading-integrity.json`:
`1` cadru evaluat, `MISSING`, `0` cadre cu sursă brută completă. Asta este o
reconstrucție a deciziei offline, nu o nouă rulare live; urma veche a fost
scrisă înainte de câmpurile noi și nu poate dovedi ce a făcut clientul atunci.

Poarta verifică acum și perechea de proveniență: `COORDINATE_HUD_EXACT` poate
produce doar heading exact, iar `MINIMAP_VISION_FALLBACK` doar heading vizibil
inițial/fuzionat sau axa orientată spre coridor. O etichetă pusă manual pe
canalul greșit nu poate reîmprospăta dovada. Testele dedicate heading-integrity
și replay trec `10/10`, iar
regresia Movement Engine trece `224/224`; nu s-a pornit WoW, nu s-a reîncărcat
addonul și nu s-a trimis input. Următorul pas rămâne o singură probă live
filmată, fără combat, numai după confirmare explicită.

## ME-339 — Profil v2 pentru ancora vizibilă (offline)

În cadrele ShadowPlay păstrate, Predatorul putea fi văzut puțin la stânga
centrului. Profilul v1 cerea capul în intervalul `0,50..0,56` și raporta
`LOST` chiar când silueta era pe ecran. Am păstrat v1 pentru rollback și am
adăugat profilul v2 cu `head_center_x=0,44..0,60`; restul cerințelor de cap,
suport, luminanță și confidence nu s-au relaxat. Runner-ul folosește v2 ca
`retained_video_candidate`, fără promovare la live verificat.

Auditul este în
`data/runtime/operator/live-video/player-actor-profile-v2-audit-me339.json`.
Pe `38` cadre selectate din filmarea păstrată, v2 a găsit `17` cadre vizibile,
față de `5` cu v1; cadrele în care camera era în tavan au rămas pierdute în
verificarea offline. Comparația a folosit deadline `100 ms` doar pentru
diagnostic; runtime-ul rămâne la `8 ms`. Aceasta este calibrare pe imagini
păstrate, nu test nou în WoW; rollback-ul rămâne fișierul v1.

După schimbare, testele țintite pentru detector, cameră, heading și runner au
trecut `237/237`, iar suita completă a trecut `1486/1486 OK`. `compileall` și
`git diff --check` rămân curate (avertismentul LF→CRLF pentru `.gitignore` este
preexistent). Nu s-a pornit WoW și nu s-a trimis input.

## ME-341 — Deadline bounded pentru detectorul ancorei (offline)

În auditul pe cadrele ShadowPlay, deadline-ul de `8 ms` a produs un
`PlayerActorAnchorError` pe `sample_0026.jpg`, deși Predatorul este vizibil în
cadru. Am păstrat profilul v1 neschimbat pentru rollback și am ridicat numai
deadline-ul profilului v2 la `12 ms`; pragurile de vizibilitate, confidence și
poarta fail-closed nu au fost relaxate.

Matricea este în
`data/runtime/operator/live-video/player-actor-profile-runtime-deadline-audit-me341.json`.
La `10 ms` și `12 ms`, rezultatul a fost `17 VISIBLE`, `21 LOST`, fără erori,
în câte trei treceri offline. La `8 ms` a rămas timeout-ul cunoscut. Cele `21`
de cadre `LOST` sunt cadre în care camera arată peretele/tavanul; un deadline
mai mare nu le transformă în dovadă validă. Profilul rămâne
`retained_video_candidate`, nu este verificat live.

Testele pentru detector și auditul offline trec, iar suita completă curentă este
`1488/1488 OK`. Nu s-a pornit WoW, nu s-a reîncărcat addonul și nu s-a trimis
input live.

## ME-342 — Preflight explicit pentru dependențele live (offline)

Am adăugat politica pură
`src/perfect_assassin/movement/live_preflight.py` și contractul
`contracts/live-observation-preflight.schema.json`. Înainte de legarea arm-ului
F4a, runner-ul verifică și publică separat poziția HUD, ancora vizibilă,
headingul, latențele și focusul exact al ferestrei. Un rezultat `REJECTED`
lasă arm-ul nelegat și nu emite input; un rezultat `READY` nu este dovadă de
sosire și nu promovează nimic la autonomie live.

De asemenea, canalul de body yaw din preflight este populat numai pentru
`COORDINATE_HUD_EXACT`; headingul din minimapă rămâne estimare de cameră și nu
mai este etichetat ca facing brut al corpului. Preflight-ul este validat cu
schema și toate operațiile din această schimbare au rămas offline. Testele
țintite au trecut `137/137` pentru runner, sink și preflight, iar suita
completă curentă este `1495/1495 OK`. Nu s-a pornit WoW și nu s-a trimis input
live.

## ME-343 — Separarea efectivă a body yaw de facing-ul minimapei (offline)

Runner-ul păstrează acum `player_facing_rad` pentru valoarea brută a canalului
client-facing, ca replay-ul headingului să poată folosi în continuare și
minimapa. Câmpurile `body_yaw_observation_rad` și
`body_camera_yaw_delta_rad` sunt completate numai când sursa este
`COORDINATE_HUD_EXACT`; pentru `MINIMAP_VISION_FALLBACK` ele rămân `null`, cu
sursa body `UNAVAILABLE`. Astfel nu mai spunem că un marker de minimapă este
orientarea exactă a corpului.

Evaluatorul și replay-ul strict acceptă `player_facing_rad` pentru canalul
client-facing, dar resping un trace minimapă care încearcă să treacă doar cu
`body_yaw_observation_rad`. Decizia este în ADR-0107. Testele țintite pentru
runner, replay și evaluator trec `331/331`, iar suita completă este
`1498/1498 OK`; compileall este curat. Schimbarea este offline, fără client,
reload sau input live.

## ME-344 — Checkpointul de continuitate respectă poarta de preflight (offline)

Dacă preflight-ul observației live este respins, bucla de control nu pornește.
Runner-ul publică acum și checkpointul de continuitate ca
`LIVE_PREFLIGHT_REJECTED`, nu ca `RUNNING`. Astfel supervisorul și operatorul
nu mai văd un job „în mers” când nu există voie să fie apăsată nicio tastă.
Pentru reset sau search-vantage respins se păstrează statusul lor terminal.

Schimbarea este doar de stare și audit, fără extinderea autorității. Testul
offline verifică ordinea și ramura fail-closed; suita completă este
`1499/1499 OK`; nu s-a pornit clientul și nu s-a trimis input live.

## ME-345 — Revalidare Cryptă–Brill pe WorldPack Tirisfal v2 (offline)

Am verificat profilul standalone
`worldpack-runtime:tbc243:tirisfal-silverpine:v2` și am rulat validatorul
semantic cu workerul local pin-uit. Toate cele patru direcții au trecut:
Crypt spawn→Brill, Brill→Crypt, Deathknell→Brill și Brill→Deathknell.
Primele două au `131/131` etape validate; direcțiile Deathknell au `117/118`
etape raportate cu sosire semantică și toate coridoarele complete.

Rezultatul este în
`data/runtime/navigation-f3b/semantic-road-journey-validation-me345-tirisfal-four-routes.json`;
WorldPack-ul are hash `4ceee9a4…34bdb2` și `execution_authority=false`.
Aceasta confirmă încă o dată geometria și frontiera navmesh offline, nu
comportamentul camerei sau al inputului în WoW. Nu s-a pornit clientul și nu
s-a trimis input live.

## ME-448 — Prioritate open world și poarta de heading la pornire

Prioritatea operatorului este roamingul în open world (99%); dungeons rămân
doar 1% și nu se extind în această etapă. Pack-urile de dungeon existente nu
se șterg și rămân doar pentru rollback/awareness read-only.

La `2026-09-03` s-a făcut o singură încercare live, filmată, fără combat, cu
Predator în Cryptă și cu protecția LAB activă. Poziția exactă și actorul au
fost vizibili în proba read-only imediat înainte de runner. Runnerul a oprit
înainte de prima apăsare de mers deoarece, după camera-home, a primit pentru
scurt timp heading din minimapă în loc de heading exact din HUD; poarta strictă
a refuzat corect mișcarea. Nu există dovadă că Predator s-a deplasat în această
încercare.

Runnerul cere acum explicit `COORDINATE_HUD_EXACT` la pornire și reîncearcă
doar observații fără input până la limita existentă; heading-ul minimapă nu mai
este confundat cu dovadă exactă. Regresia locală pentru movement/heading,
client-navigation și live-preflight este `330 passed`. Următorul pas este o
nouă verificare live doar după confirmarea operatorului; nu se rulează automat.

## ME-346 — Audit curent al WorldPack-urilor și al limitelor de promovare (offline)

Am regenerat auditul registry-ului folosind queue-ul continental și queue-urile
Deadmines v2 și Razorfen v2. Registry-ul are `83/83` identități de hartă,
`35` hărți cunoscute în queue și `6` queue-uri complete. Doar `7` hărți sunt
topografice-ready, iar numai Azeroth are catalog semantic complet și rămâne
`autonomous_ready=1`; Kalimdor, Shadowfang, Deadmines, Razorfen, Karazhan și
Expansion01 rămân topografice/observe-only fără catalog semantic complet.

Rezultatul verificabil este
`data/runtime/navigation-f3b/world-map-registry-audit-me346.json`, cu
`client_build=2.4.3.8606` și `execution_authority=false`. Auditul confirmă
limita reală: existența unei geometrii topografice nu acordă singură autonomie
și nu repară problema de observație a clientului live. Nu s-a pornit clientul,
nu s-a reîncărcat addonul și nu s-a trimis input.

## ME-347 — Offline verde, frontiera live rămâne cauza probabilă

Suita neinteractivă a fost rerulată după ME-346 și a trecut `1499/1499 OK`.
Cele două alarme văzute într-o rulare cu terminal interactiv îngust au fost
doar înfășurarea textului PowerShell; testele respective și suita completă au
trecut fără PTY.

Dovezile existente separă clar cele două lumi: validatorul semantic
Cryptă↔Brill trece offline, iar auditul strict al urmei live vechi are `0/419`
cadre cu sursă brută de facing, separare body/cameră sau integritate vizibilă a
camerei. Urma are și o pauză de `9,341 s`, iar filmarea păstrată arată cadre în
care camera privește peretele/tavanul. Prin urmare, rezultatul nu spune că
Predatorul a uitat harta; spune că în clientul live observația și/sau legătura
de input nu sunt încă demonstrate.

Preflight-ul rămâne fail-closed: fără fereastră exactă, poziție proaspătă,
ancoră vizibilă și heading compatibil nu se leagă arm-ul F4a. Acest checkpoint
nu pornește WoW, nu reîncarcă addonul și nu trimite input. Următorul pas rămâne
o singură probă live, scurtă și filmată, fără combat, numai după confirmare
explicită.

## ME-348 — Auditul urmei vechi nu validează codul nou (offline)

Am rulat din nou evaluatorul strict pe urma păstrată
`data/runtime/navigation-f3b/results/navmesh-roaming-fe3e7d29-1669-4260-8f2a-5ab7e2d64387.json`,
fără client, reload sau input. Raportul nou este
`data/runtime/navigation-f3b/heading-replay/me348-latest-live-boundary-audit.json`.

Rezultatul este `passed=false`: `419` cadre, `0` cadre cu sursă raw de facing,
`0` cu separare body/cameră și `0` cu integritate de cameră. Urma are și
`7` goluri peste `300 ms`, dintre care `4` neexplicate de mișcare. Ea este un
artefact cu schema `0.1`, scris înainte ca runner-ul curent să publice aceste
câmpuri și preflight-ul explicit; prin urmare dovedește problema live istorică,
dar nu poate spune dacă reparațiile offline curente au trecut în client.

Acest checkpoint întărește următoarea decizie: nu schimbăm WorldPack-ul pe baza
acestei urme și nu declarăm fixul live. Rămâne necesară o singură probă bounded,
filmată, fără combat, după confirmare explicită.

## ME-349 — Revalidare read-only a arhivei Zygor Anniversary (offline)

Am testat din nou arhiva locală `D:\\Downloads\\Zygor Release 8.1.37070.rar`
cu 7-Zip (`Everything is Ok`, `868` fișiere) și am extras temporar numai cele
șase ghiduri selectate și `NPCData.lua`. Cele trei audituri cu `--check` au
trecut pe conținutul proaspăt extras: ghidurile au `14.748` pași și `11.687`
candidaturi de coordonate, iar `NPCData.lua` are `3.255` rânduri în `66`
map-area IDs; toate păstrează `execution_authority=false`. Hash-ul arhivei
rămâne `d8d416ad95f9071fd8578df218a70235c377ea8b350f81ca2ea6f5417a65d2d3`.

Aceasta elimină ipoteza că problema live vine dintr-o arhivă TBC greșită sau
dintr-un catalog Zygor vechi. Datele rămân însă RouteTeacher static, 2D și
advisory: ele nu pot furniza singure poziția/headingul curent al Predatorului
și nu acordă autoritate de input. Verificarea a fost strict offline; nu s-a
pornit WoW, nu s-a reîncărcat addonul și nu s-a trimis input.

## ME-350 — Karazhan: navmesh parțial, cu tile-uri problematice (offline)

Am reluat doar offline bake-ul pentru mapa Karazhan (`map_id=532`) folosind
clientul local TBC 2.4.3.8606, MapBuilder-ul pin-uit și cele nouă ADT-uri deja
extrase. Semantica `.road` este completă pentru `9/9` ADT-uri. Cinci tile-uri
au produs navmesh nenul (`34_51`, `34_52`, `34_53`, `35_53`, `36_53`), iar
`35_51`, `35_52`, `36_51` și `36_52` au fost oprite după limita de trei minute
fără artefact navmesh; MapBuilder a raportat contururi Recast cu „Multiple
outlines for region”. Nu am pus tile-uri goale în locul lor.

Queue-ul candidat este
`data/runtime/client-catalog/tbc243-8606/bake-queue-full-v1-karazahn-partial-20260902.json`;
starea calculată este `NAVMESH_PARTIAL`, iar auditul navmesh este
`data/runtime/client-catalog/tbc243-8606/karazahn-navmesh-quality-partial-20260902.json`
(`5/9` ADT-uri, `execution_authority=false`). Auditul registry este în
`data/runtime/navigation-f3b/world-map-registry-audit-me350-karazahn-partial-20260902.json`
și a trecut verificarea `--check`.

Acesta este progres de hartă, nu dovadă că Predatorul poate intra sau ieși din
Karazhan în client. Nu s-a pornit WoW, nu s-a reîncărcat addonul și nu s-a
trimis input live; tile-urile problematice rămân de reparat separat înainte de
orice promovare.

## ME-351 — WorldPack v3 păstrează Karazhan complet (offline)

Verificarea de mai sus a găsit un artefact mai vechi, dar sigilat și local:
`E:\WoWserver\PerfectAssassin-Runtime\worldpacks\tbc243-8606-proof-worldpack-v3`.
Verificarea manifestului a trecut (`826` artefacte, `execution_authority=false`,
`runtime_ready=true`, `nav_profile_id=tbc243-proof-v2`). Pentru Karazhan,
manifestul conține toate cele `9/9` tile-uri navmesh, mapa `.map` și toate cele
`9/9` semantici `.road`; pack-ul mai conține și Razorfen Kraul (`6/6`). Hash-ul
de conținut al pack-ului este
`33bbbba1ef9f698cd1e843c7ca463a069e78dd27339a28f57715669a00b03363`.

Am generat fără mutare queue-ul de control
`data/runtime/client-catalog/tbc243-8606/bake-queue-proof-worldpack-v3-20260903.json`;
Karazhan și Razorfen apar `COMPLETE`. Auditul combinat cu queue-ul continental
și Deadmines este
`data/runtime/navigation-f3b/world-map-registry-audit-me351-proof-v3-20260903.json`;
`--check` a trecut, cu `7` hărți complete, `7` topografice și `1` autonomă.

Concluzia este simplă: tile-urile lipsă din copia nouă nu înseamnă că am pierdut
Karazhan. Avem deja o copie locală completă, verificată. Ea rămâne doar
topografică/observe-only până când catalogul semantic și observația clientului
live sunt demonstrate. Nu s-a pornit WoW, nu s-a reîncărcat addonul și nu s-a
trimis input live.

## ME-352 — Registry-ul runtime selectează WorldPack v3 (offline)

Am rezolvat și verificat profilul runtime
`config/navigation/world-pack-runtime-tbc243-proof-v3.json` prin loaderul real,
cu store-ul local `E:\WoWserver\PerfectAssassin-Runtime\worldpacks`. Rezultatul
este `VERIFIED`: `pack_id=wow.tbc.2.4.3.8606.proof-worldpack-v3`, hash
`33bbbba1ef9f698cd1e843c7ca463a069e78dd27339a28f57715669a00b03363`,
`nav_profile_id=tbc243-proof-v2` și hărțile `[47, 532]`. Toate dependențele
runtime declarate sunt false și `execution_authority=false`.

Aceasta confirmă că binding-ul folosit de registry este copia sigilată completă,
nu directory-ul experimental `navigation\tbc243-full-v1` cu `NAVMESH_PARTIAL`.
Verificarea a fost locală și read-only pentru pack; nu s-a pornit WoW, nu s-a
reîncărcat addonul și nu s-a trimis input live.

## ME-353 — Urma live veche pierde headingul exact după planificare (offline)

Am inspectat câmpurile din cele `419` acțiuni `CONTINUOUS_FRAME` ale urmei
`data/runtime/navigation-f3b/results/navmesh-roaming-fe3e7d29-1669-4260-8f2a-5ab7e2d64387.json`.
Prima citire înainte de control a raportat `VISIBLE_CLIENT_HEADING_INITIAL`,
dar reîmprospătarea de după plan a raportat
`MOUSE_INTEGRATED_MINIMAP_FALLBACK`. În cadrele efective, `369` au fost
`MOUSE_INTEGRATED_MINIMAP_FALLBACK`, `39`
`DISPLACEMENT_INITIAL_DIRECTION_CALIBRATION` și `11`
`DISPLACEMENT_HEADING_CONFIRMED_MINIMAP_FALLBACK`; niciun cadru nu are
`client_facing_source`, `heading_integrity` sau `camera_integrity_state`.

Aceasta este o explicație tehnică puternică pentru abaterea live: headingul exact
nu a fost păstrat când planificarea s-a terminat, iar controlul a continuat pe
un fallback de minimapă. Totuși urma are schema `0.1`, nu conține preflight-ul
și este anterioară runnerului curent; de aceea nu declară că ME-342/343 au
trecut live. Verificarea a fost read-only, fără client, reload sau input.

## ME-354 — Replay strict: fuziunea headingului trece, dovada live nu (offline)

Evaluatorul strict rerulat este
`data/runtime/navigation-f3b/heading-replay/me354-latest-boundary-audit-20260903.json`.
El respinge urma veche cu `0/419` cadre pentru sursă client-facing, separare
body/cameră și integritate cameră; rămân și `7` goluri de observație peste
`300 ms`, dintre care `4` neexplicate. Acesta este un eșec corect al porții
live, nu un eșec al planificatorului offline.

Replay-ul bounded asociat,
`data/runtime/navigation-f3b/heading-replay/me354-heading-replay-20260903.json`,
reconstruiește `419/419` cadre cu heading vizibil (`replayed_fused_fraction=1.0`),
fără input emis și fără server truth. Corecția maximă rămâne `0,25 rad`, iar
lease-ul activ de mouse este `0,45 s`. Rezultatul arată că fuziunea poate
funcționa când primește observații; urma live nu le-a înregistrat. Nu s-a
reîncărcat addonul și nu s-a trimis input live.

## ME-355 — Protecție de regresie pentru headingul exact post-plan (offline)

Am adăugat testul
`test_post_plan_refresh_does_not_replace_exact_heading_with_minimap_fallback`
în `tests/test_movement_engine.py`. El reproduce cazul din ME-353: observația
nouă are marker de minimapă și facing estimat, dar runnerul păstrează pentru o
singură reîmprospătare bounded headingul exact obținut înainte de planificare.
Testele țintite au trecut `217/217`, iar suita completă curentă a trecut
`1500/1500 OK`. Mesajul `--jobs must be between 1 and 4` din suită este cazul
negativ verificat de un test și nu este eșec de suită.

Schimbarea nu lărgește autoritatea: fallback-ul rămâne doar observație vizuală,
poarta exact-body poate respinge în continuare cadrul, iar toate verificările
au fost offline; nu s-a pornit WoW, nu s-a reîncărcat addonul și nu s-a trimis
input live.

## ME-356 — Facing-first: nici mouse-ul, nici headingul păstrat nu pornesc mersul (offline)

Am adăugat două regresii în `tests/test_live_preflight.py`. Ele verifică faptul
că un heading `MOUSE_INTEGRATED_MINIMAP_FALLBACK` nu trece preflight-ul chiar
dacă există un yaw de minimapă, iar `COORDINATE_HUD_EXACT_PRESERVED` nu este
tratat drept facing proaspăt. Ambele trebuie să oprească sesiunea înainte de
armarea mișcării. Astfel, „facing primul” este o regulă verificabilă: numai un
heading vizibil curent (`COORDINATE_HUD_EXACT` sau `VISIBLE_CLIENT_HEADING_*`
cu sursa minimapă potrivită) poate ajunge la control.

Aceasta nu promite o valoare matematic „perfectă” din captură; promite că, dacă
valoarea nu este demonstrată și proaspătă, Predatorul nu merge. Verificarea
rămâne offline, fără client, reload sau input live.

## ME-357 — Revalidare proaspătă a transformărilor Zygor (offline)

Prima rulare a auditului a găsit o coordonată Black Temple dintr-un rând comentat
(`//step`). Parserul o număra din greșeală ca rută. Am reparat parserul bounded să
ignore liniile de comentariu `//` și `--`, apoi am rerulat testele și auditul pe
cele șase fișiere din arhiva Anniversary `D:\Downloads\Zygor Release 8.1.37070.rar`.

Auditul este acum verificabil cu `--check` și complet pentru coordonatele active:
`11.686/11.686` transformate, `0` nerezolvate și `0` erori; `execution_authority=false`.
Cele trei hărți continentale rămân complete: Azeroth `3.434/3.434`, Kalimdor
`3.918/3.918`, Expansion01 `4.334/4.334`. Coordonata comentată de Black Temple
nu mai intră în RouteTeacher și nu este folosită la decizie.

Auditul proaspăt de route coverage are `14.748` pași și `11.686` candidaturi.
Datele Zygor rămân RouteTeacher static și advisory. Acest audit nu schimbă
facingul și nu pornește WoW; facing-first rămâne poarta înainte de orice input:
dacă sursa vizibilă nu este curentă și compatibilă, preflight-ul respinge sesiunea.

Regresia pentru comentarii și auditurile Zygor au trecut testele țintite `20/20`,
iar suita completă după schimbare a trecut `1503/1503 OK`; mesajul despre
`--jobs` rămâne cazul negativ verificat de suită.

## ME-358 — Razorfen Downs: candidate navmesh complet, verificat structural (offline)

Am construit separat, din MPQ-urile locale TBC `2.4.3.8606`, candidate-ul
`RazorfenDowns` în
`E:\WoWserver\PerfectAssassin-Runtime\assets\tbc243-next-v1` și
`E:\WoWserver\PerfectAssassin-Runtime\navigation\tbc243-next-v1`. Extracția,
semantica `.road` și navmesh-ul au ajuns `COMPLETE` pentru toate `24/24` ADT-uri,
fără să atingă pachetul runtime existent.

Auditul structural
`data/runtime/client-catalog/tbc243-8606/razorfen-downs-candidate-v1-navmesh-geometry.json`
a trecut `24/24` tile-uri, `6.144` tile-uri Detour și `0` tile-uri goale.
Auditul de bake este `COMPLETE_WITH_RECAST_DIAGNOSTICS` (nu eșec): are contururi
Recast raportate în log, deci candidate-ul nu este promovat în registry până la
revizuirea acelor diagnostice. Queue-ul și catalogul candidat sunt păstrate
pentru rollback/reluare; `execution_authority=false`.

Am sigilat candidate-ul ca
`E:\WoWserver\PerfectAssassin-Runtime\worldpacks\tbc243-razorfen-downs-candidate-v1`.
Verificarea manifestului a trecut: `428` artefacte, `runtime_ready=true`,
`packed_map_count=1`, hash de conținut
`1f7304951212b44858c3a86be1baadb21a7ee30544b084b54427c19f54be1e35`.
Pachetul rămâne nelegat în registry și nu poate porni input.

Aceasta este dovadă offline de asset, navmesh și integritate structurală, nu
dovadă de mers live în dungeon și nu pornește WoW.

## ME-359 — Razorfen Downs: corpus steering pe toate tile-urile (offline)

Am verificat candidate-ul sigilat prin profilul separat
`config/navigation/world-pack-runtime-tbc243-razorfen-downs-candidate-v1.json`.
Corpusul geometric bounded a acoperit toate `24/24` tile-uri: `24/24` coridoare
complete, `24/24` simulate, `2.400/2.400` trial-uri de steering, `0` eșecuri de
query și `0` coridoare cu quality failure. Raportul este
`data/runtime/navigation-f3b/razorfen-downs-steering-full-v1.json`.

Acesta verifică doar coridoarele reale ale navmesh-ului candidate și controllerul
offline; nu demonstrează poziția unui player în client, combat, facing live sau
intrare/ieșire reală din dungeon. Pachetul rămâne candidate nelegat în registry,
cu `execution_authority=false`.

## ME-360 — Razorfen Downs: index structural și scanare de acces (offline)

WorldPack-ul candidate are acum și index structural local:
`data/runtime/client-catalog/tbc243-8606/razorfen-downs-candidate-v1-world-structure-index.json`.
El identifică `1` WMO (`129:wmo:336884`), `24` tile-uri de teren și `24` tile-uri
navmesh; cunoașterea entităților dinamice este explicit `NONE`.

Planul de scanare a produs `39` seed-uri bounded. Toate au fost clasificate
`REJECTED_EXPECTED_STRUCTURE_NOT_CONFIRMED`; unele au fost `OPEN_GROUND`, iar
cele apropiate de WMO au rămas `WMO_TRANSITION_OR_UNRESOLVED`. Agregarea nu a
creat un graph fals, deoarece nu există nicio observație WMO confirmată. Fragmentele
și planul sunt păstrate în
`data/runtime/navigation-f3b/razorfen-downs-candidate-v1-structure-scan` și
`.../razorfen-downs-candidate-v1-structure-access-scan-plan.json` pentru reluare.

Acesta este un rezultat fail-closed: navmesh-ul este bun, dar accesul structural
nu este încă demonstrat. Nu se promovează candidate-ul și nu se pornește WoW.

## ME-361 — Replay-ul nu mai poate înlocui facingul cu yaw-ul camerei (offline)

Am întărit `scripts/replay_heading_integrity.py`: dacă un cadru declară o sursă
client-facing cunoscută (`COORDINATE_HUD_EXACT` sau
`MINIMAP_VISION_FALLBACK`), evaluatorul cere și martorul brut din același cadru.
Un `camera_yaw_estimate_rad` numeric nu mai este suficient când
`player_facing_rad` lipsește; pentru urmele exacte vechi este acceptat doar
fallback-ul explicit `body_yaw_observation_rad`.

Regresia nouă verifică exact cazul „minimapă lipsă, cameră încă numerică” și
oprește replay-ul cu `INVALID`, fără să numere cadrul ca vizual. Testele dedicate
heading/preflight/replay au trecut `23/23`, iar suita completă curentă a trecut
`1504/1504`. Schimbarea este offline-only; nu s-a pornit WoW, nu s-a reîncărcat
addonul și nu s-a trimis input live.

## ME-362 — MonasteryInstances: WorldPack candidat și steering complet (offline)

Am construit separat mapa client `MonasteryInstances` (map `189`) din clientul
local TBC `2.4.3.8606`. Bake-ul are `36/36` tile-uri ADT, iar auditul geometric
are `36/36` tile-uri trecute și `0` tile-uri goale. Auditul de bake rămâne
`COMPLETE_WITH_RECAST_DIAGNOSTICS` (diagnostice Recast păstrate, fără promovare
automată). Candidate-ul este sigilat în
`E:\\WoWserver\\PerfectAssassin-Runtime\\worldpacks\\tbc243-monastery-candidate-v1`,
cu `498` artefacte, `runtime_ready=true` și hash de conținut
`621055111208d0887cacba01db9419d7ac5b30402006e44fb27df2a6e677d2f7`.
Profilul este verificat separat, cu `map_id=189` și `execution_authority=false`;
nu este legat în registry și nu poate porni input.

Prima încercare a corpusului a fost respinsă înainte de query deoarece am cerut
un timeout de `15 s`, peste limita adaptorului nativ de `10 s`. Am adăugat
validare CLI ca această eroare să fie vizibilă imediat. După corecție, smoke-ul
tile-ului `28_27` a trecut `1/1` coridor și `100/100` trial-uri, iar corpusul
complet a trecut `36/36` coridoare și `3.600/3.600` trial-uri, cu `0` eșecuri
de query și `0` quality failures. Raportul este
`data/runtime/navigation-f3b/monastery-steering-full-v2.json`.

Acesta este progres offline de geometrie și controller, nu dovadă de intrare,
combat sau facing live în dungeon. Facing-first rămâne neschimbat: controlul
este permis numai cu heading vizual curent și compatibil; pentru o afirmație
strictă de body yaw se folosește opțiunea exactă HUD, iar minimapa/camera rămân
estimări bounded. Nu s-a pornit WoW, nu s-a reîncărcat addonul și nu s-a trimis
input live.

## ME-363 — Audit combinat cu queue-ul Monastery (offline)

Am inclus queue-ul candidat Monastery în auditul combinat, fără să modific
registry-ul runtime. Prima generare a fost oprită corect de schema veche
(`queue_reference` depășea `320` caractere); după ADR-0112, auditul verificat
este `data/runtime/navigation-f3b/world-map-registry-audit-me362-proof-v4-20260903.json`.
El păstrează `83/83` hărți în registry, `35` mapări în queue și `8` mapări cu
starea `COMPLETE`; `MonasteryInstances` (`map_id=189`) apare `COMPLETE`, dar
`topographic_ready_map_count` rămâne `7`, deoarece candidate-ul nu este legat
în registry și nu are încă dovadă structurală de egress.

Suita de regresie pentru schema și audit a trecut împreună cu suita completă
`1506/1506`. Totul este offline și read-only pentru runtime: nu s-a pornit WoW,
nu s-a reîncărcat addonul și nu s-a trimis input live.

## ME-364 — Monastery: index structural și graph de acces parțial (offline)

Pentru candidate-ul Monastery am creat și verificat indexul structural
`data/runtime/client-catalog/tbc243-8606/monastery-candidate-v1-world-structure-index.json`:
`36` tile-uri teren, `36` tile-uri navmesh și `4` WMO. Planul bounded are `126`
seed-uri pentru cele `4` structuri eligibile.

Scanarea read-only a terminat toate `126/126` seed-uri, cu `0` erori de worker.
Au fost confirmate `15` observații WMO (`111` respinse fiindcă structura nu a
fost confirmată în seed), iar agregarea strictă a produs graph-ul candidat
`data/runtime/navigation-f3b/monastery-candidate-v1-structure-access-partial-v1.json`
cu `43` opening-uri și `88` boundary chains. Starea este
`PARTIAL_OBSERVED_COMPONENTS`; physical door semantics și dynamic state rămân
`UNKNOWN`, deci graph-ul nu este promovat și nu acordă autonomie.

Un query de verificare lângă un opening a trecut prin loaderul world-pack-bound,
cu `execution_authority=false`. Nu s-a pornit WoW, nu s-a reîncărcat addonul și
nu s-a trimis input live.

## ME-365 — Revalidare fresh a rutei Cryptă–Brill–Cryptă (offline)

Am rerulat validatorul `scripts/validate_semantic_road_journey.py` pe profilul
WorldPack Azeroth actual, fără `--write-offline-gate` și fără autoritate live.
Rezultatul este
`data/runtime/navigation-f3b/semantic-road-journey-validation-me365.json` cu
starea `PASS`: cele patru direcții Cryptă/Deathknell↔Brill și holdout-ul spre
drumul de sud au ajuns la destinație, iar fixture-ul de deal a fost respins
corect cu `RESET_REQUIRED` și `partial_local_navmesh_corridor`.

Detalii utile: Cryptă→Brill și Brill→Cryptă au câte `131` etape validate;
Deathknell→Brill și Brill→Deathknell au câte `117`; nu există eșec de worker.
Aceasta este dovadă de planificare și navmesh offline, nu dovadă de facing,
combat sau mers live. Gate-ul live nu a fost scris sau deschis.

## ME-366 — Stratholme: bake complet, dar steering-ul nu trece poarta (offline)

Am construit separat candidate-ul client `Stratholme` (`map_id=329`) din TBC
`2.4.3.8606`. Bake-ul și verificarea geometrică au trecut `20/20` tile-uri;
WorldPack-ul sigilat este
`E:\\WoWserver\\PerfectAssassin-Runtime\\worldpacks\\tbc243-stratholme-candidate-v1`,
cu `513` artefacte, hash
`3e441648de567d3b16e9b9d6b000135b70a5ceef944d93dd1c815bc98e666f50`,
`runtime_ready=true` și `execution_authority=false`. Auditul de bake rămâne
`COMPLETE_WITH_RECAST_DIAGNOSTICS`: nu are tile-uri eșuate, dar păstrează
diagnostice Recast (`214` contururi multiple, `595` warnings și `436` avertismente
de triangulare).

Corpusul bounded de steering
`data/runtime/navigation-f3b/stratholme-steering-full-v1.json` a încercat toate
`20/20` tile-uri: `19` coridoare complete, `26` query/eligibility failures,
`9` coridoare cu quality failure și `1.900` trial-uri. Eșecurile sunt în zone cu
hairpin, portal foarte îngust, pantă și clearance/doodad; candidate-ul nu este
promovat și nu este legat în registry.

Un smoke MPPI izolat pe tile-ul `38_25` a rezolvat query-ul, dar a avut doar
`14/100` trial-uri quality (`max cross-track 3,53 yd`). Asta nu justifică o
promovare și nu dovedește că schimbarea controllerului rezolvă geometria.

Auditul combinat cu cinci queue-uri este
`data/runtime/navigation-f3b/world-map-registry-audit-me366-proof-v5-20260903.json`:
`35` mapări queue, `9` complete, `7` topographic-ready și `1` autonomous-ready.
Totul rămâne offline; nu s-a pornit WoW, nu s-a reîncărcat addonul și nu s-a
trimis input live.

## ME-367 — Facing strict: martorul HUD trebuie să coincidă cu headingul folosit

Poarta `--require-exact-body-heading` verifica deja existența unui `facing_rad`
din Coordinate HUD. Am întărit-o ca să compare și headingul dat controllerului
cu martorul brut din același cadru. O abatere peste `0,02 rad` este tratată ca
amestec de cadre sau heading vechi și respinge preflight-ul înainte de input.
Aceeași regulă este acum în `build_live_preflight_record`, nu doar în runner;
regresia acoperă și apropierea de limita `0/2π`, fără falsă respingere.

Testele țintite facing/preflight/replay au trecut `120/120`. Modul strict este
opțional deoarece clientul TBC legacy poate să nu publice facing HUD la fiecare
cadru; în acel caz minimapa rămâne doar fallback vizual bounded, niciodată body
yaw exact. Aceasta este verificare offline; proba live rămâne blocată până la
confirmare explicită și arm nou.

## ME-368 — Replay facing: valoarea fără sursă nu mai este numărată ca brută

Replay-ul heading-integrity tratează acum `player_facing_rad` ca martor numai
când cadrul are și `client_facing_source` cunoscut (`COORDINATE_HUD_EXACT` sau
`MINIMAP_VISION_FALLBACK`). O valoare numerică rămasă într-o urmă veche cu sursa
`UNAVAILABLE` nu mai apare drept facing brut disponibil.

Auditul păstrat în
`data/runtime/navigation-f3b/heading-replay/me368-retained-facing-audit-20260903.json`
arată trei urme istorice: fiecare se oprește la primul cadru cu `MISSING`, are
`0` cadre cu sursă brută completă și `input_emitted=false`, inclusiv urma veche
care ajunsese atunci `ARRIVED`. Aceasta separă clar rezultatul istoric al rutei
de dovada de facing.

Regresia suplimentară a trecut în suita completă `1510/1510`. Nu s-a pornit WoW,
nu s-a reîncărcat addonul și nu s-a trimis input live.

## ME-369 — Shadowfang: corpus complet, candidate nepromovat (offline)

Am rulat corpusul bounded pe candidate-ul Shadowfang v3, nu pe WorldPack-ul
Stable. Verificarea a selectat `25/25` tile-uri și a încercat `250` cereri.
Doar `15` coridoare au fost rezolvate complet; `121` cereri au fost respinse
(`108` `ENDPOINT_UNAVAILABLE`, `13` `PARTIAL_CORRIDOR`), iar `5` coridoare
rezolvate au avut quality failure. Numărul total de trial-uri simulate a fost
`1.500`.

Eșecurile se concentrează în zona cu scări și curbe înguste: `SHARP_TURN`,
`ACTOR_SCALE_PORTAL`, `STEEP_GEOMETRY`, `DOODAD_DETOUR` și
`CLEARANCE_INSET`; scenariul `28_30` a trecut doar `3/100` trial-uri, cu
cross-track maxim de aproximativ `3,06 yd`. Smoke-ul vechi de patru tile-uri
nu era suficient pentru promovare.

Raportul este
`data/runtime/navigation-f3b/shadowfang-v3-steering-full-v1.json`.
Candidate-ul rămâne sigilat, nelegat în registry și cu
`execution_authority=false`. Rezultatul este dovadă offline despre limita
actuală a steering-ului, nu dovadă de intrare live în dungeon.

## ME-370 — Facing strict înaintea fiecărui cadru de mers (offline)

Am întărit poarta de facing în `integrations/windows-input/run_navmesh_roaming.py`.
În modul `--require-exact-body-heading`, runnerul nu mai verifică body yaw doar
la pornire: înainte de fiecare nou cadru cu input verifică din nou facing-ul HUD
exact și îl compară cu headingul folosit, cu abatere maximă `0,02 rad`. Dacă
facing-ul lipsește sau nu mai coincide, inputul este eliberat și urma primește
starea `EXACT_BODY_HEADING_LOST`.

Supervisorul normal și ruta reviewed trimit acum automat această opțiune strictă.
Minimapa, camera și deplasarea nu pot înlocui facing-ul exact în calea normală.
Am adăugat regresii pentru poarta per-cadru și pentru cele două lansatoare; suita
completă a trecut `1512/1512`. Schimbarea este offline-only și fail-closed: nu
pornește WoW, nu reîncarcă addonul și nu trimite input live.

## ME-371 — Comparație geometrică cu PA-MPPI pe coridoare Shadowfang (offline)

Am repetat cele cinci coridoare cu `pa_mppi_v1` (`batch=256`, `56` pași,
replan la `3` ticks), fiecare cu `100` încercări. Raportul agregat este
`data/runtime/navigation-f3b/shadowfang-mppi-comparison-20260903.json`, iar
replay-urile individuale sunt păstrate lângă el.

MPPI a ridicat `28_30:p0` de la `3%` la `100%`, `28_31:p0` de la `3%` la `100%`
și `28_32:p0` de la `26%` la `98%`. Pe `27_30:p2` a scăzut de la `47%` la
`40%`, iar `27_33:p1` a ajuns la `85%`, dar numai `85/100` încercări au fost
complete și abaterea maximă a rămas aproximativ `12 yd`. Concluzia este
`CANDIDATE_CONTROLLER_NOT_PROMOTED`: păstrăm MPPI izolat, fără schimbare în
Stable sau registry.

Aceasta este comparație de steering offline, nu dovadă de facing, combat sau
mers în client. Nu s-a pornit WoW, nu s-a reîncărcat addonul și nu s-a trimis
input live.

## ME-372 — Facing strict păstrat și la reluarea continuității (offline)

Am închis și calea de reluare din `run_navigation_continuity.py`. Când o felie
este reluată după oprire, moarte sau recuperarea corpse-ului, comanda copil cere
acum `--require-exact-body-heading`, la fel ca supervisorul și ruta reviewed.
Astfel, reluarea nu poate coborî accidental la heading de cameră sau minimapă.
Regresia pentru comanda de continuitate și suita completă au trecut `1512/1512`.
Schimbarea este offline-only, fail-closed și nu modifică Stable, registry-ul sau
autoritatea live.

## ME-373 — Facing strict pe toate lansatoarele de navigație (offline)

Am verificat și calea de hunting, care pornește direct felii de navmesh pentru
intrare și patrulare. Am adăugat `--require-exact-body-heading` la ambele
comenzi, astfel încât nici hunting-ul nu poate porni din heading de cameră sau
minimapă. Împreună cu supervisorul, ruta reviewed și continuitatea, toate
lansatoarele normale cer acum facing HUD exact.

Regresia nouă și suita completă au trecut `1513/1513`. Nu s-a pornit WoW, nu
s-a reîncărcat addonul și nu s-a trimis input live.

## ME-374 — Revalidare fresh Cryptă–Brill–Cryptă după poarta facing (offline)

Am rulat din nou validatorul semantic pe WorldPack-ul Azeroth actual și workerul
pinned, după întărirea porții de facing. Raportul este
`data/runtime/navigation-f3b/semantic-road-journey-validation-me374.json` și
este `PASS`: Cryptă→Brill și Brill→Cryptă au câte `131/131` etape, cele două
direcții Deathknell↔Brill au câte `117/117`, iar holdout-ul spre drumul de sud
trece. Fixture-ul de deal este respins corect cu `RESET_REQUIRED`.

Aceasta confirmă din nou planificarea și navmesh-ul offline; nu confirmă facing
în client, combat sau mers live. Nu s-a pornit WoW, nu s-a reîncărcat addonul și
nu s-a trimis input.

## ME-375 — Lot Kalimdor pentru graful topografic (offline)

Am continuat scanarea resumabilă a candidate-ului Kalimdor cu workerul v35,
singurul care se potrivește hash-ului din plan. Lotul bounded a procesat încă
`1.000` probe: `789` prin awareness persistent și `211` prin fallback one-shot
clasificat, cu `0` erori de probe. Progresul verificat este acum
`14.639/40.794` seed-uri, `334` observații acceptate și `508` structuri complete.

Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v5.json`.
Graful parțial nou este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v15.json`;
el conține `334` observații, `1.494` deschideri și `2.776` legături de frontieră.
Candidate-ul rămâne separat de Stable, cu `execution_authority=false`.
Scanarea este offline și nu pornește WoW, nu reîncarcă addonul și nu trimite
input live.

## ME-376 — Lot Expansion01 pentru graful topografic (offline)

Am continuat separat scanarea candidate-ului Expansion01 folosind profilul
`world-continents-v1` care se potrivește indexului și workerul v35. Lotul
bounded a procesat încă `1.000` probe: `958` prin awareness persistent și `42`
prin fallback one-shot clasificat, cu `0` erori. Progresul verificat este acum
`13.000/47.170` seed-uri, `253` observații acceptate și `456` structuri complete.

Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v5.json`.
Graful parțial nou este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v13.json`;
el conține `253` observații, `1.031` deschideri și `2.346` legături de frontieră.
Candidate-ul rămâne separat de Stable, cu `execution_authority=false`.
Scanarea este offline și nu pornește WoW, nu reîncarcă addonul și nu trimite
input live.

## ME-377 — Regresie completă după scanările de hartă (offline)

După loturile Kalimdor și Expansion01, suita completă a trecut din nou cu
`1513 passed in 122,27 s`. Scanările și grafurile candidate nu au schimbat
codul de execuție sau autoritatea live. Nu s-a pornit WoW, nu s-a reîncărcat
addonul și nu s-a trimis input.

## ME-378 — Replay strict pe ultima urmă păstrată (offline)

Am rulat poarta strictă pe ultima urmă `navmesh_roaming_result` păstrată.
Urma are `419` cadre, dar toate au `client_facing_source=UNAVAILABLE` și
folosesc fallback de minimapă sau calibrare prin deplasare. Replay-ul nou s-a
oprit fail-closed chiar la cadrul `1`, cu starea `MISSING` și motivul
`no_prior_visible_heading_to_hold`; nu a numărat niciun cadru ca facing vizual.

Raportul este
`data/runtime/navigation-f3b/heading-replay/me378-latest-retained-trace-strict.json`.
Rezultatul are `input_emitted=false`, `execution_authority=false` și
`server_truth_used=false`. Aceasta este dovadă că gate-ul reparat refuză urma
veche fără facing client; nu este dovadă de mers live.

## ME-379 — Singura probă live confirmată, bounded, fără combat (LAB)

După confirmarea explicită a operatorului, am verificat ținta exactă: un singur
`Wow.exe` TBC 2.4.3.8606, PID `53092`, realm MaNGOS pe emulator local
`127.0.0.1`; godmode-ul LAB pentru Predator a fost confirmat `ON`. A fost
reînnoită identitatea sesiunii, revalidarea realm-ului și armul F4a, toate cu
limite bounded.

Prima pornire a fost respinsă înainte de navigație deoarece am folosit din
greșeală ID-ul intern de validator `canonical_crypt_spawn_to_brill`, care nu
este destinație unică în catalogul clientului; nu a fost emis input de mers.
Am corectat la `settlement:brill` și am rulat felia aprobată, cu maximum `800`
cadre și `0` handoff-uri de combat. Rezultatul copilului este
`data/runtime/navigation-f3b/results/navmesh-roaming-4ea4a903-1c04-4afd-96f3-95f08dcc7f8b.json`:
stare `CAMERA_ACTOR_LOST`, `0` cadre continue și poziție finală aproape de
spawn (`1676.691, 1678.225`). Detectorul a primit o captură `1×1`, confidence
`0,0`, deci controlul s-a eliberat înainte de primul cadru de mers. ME-380 a
clarificat ulterior că `1×1` era doar fallback-ul jurnalului după timeout-ul
detectorului; checkpoint-ul real avea `3643×2093` pixeli.

Jurnalul supervisorului este
`data/runtime/navigation-f3b/results/navmesh-roaming-live-20260903-crypt-brill-corrected.json`.
Filmarea NVIDIA asociată are `51,06 s`:
`C:\Users\LabUser\Videos\NVIDIA\Wow.exe\Wow.exe 2026.09.03 - 03.33.28.133.mp4`;
cadrele extrase din ea sunt negre, deci clipul nu este dovadă vizuală validă
pentru navigație. Armul fix a fost retras, Predator a rămas fără combat, iar
testul nu se repetă automat. Cauza următoare de reparat este captura/ancora
actorului, nu WorldPack-ul sau facingul; o nouă probă live necesită o nouă
confirmare explicită.

## ME-380 — Diagnostic offline al probei live și eșantionare 4K bounded

Am verificat checkpoint-urile reale ale acelei probe. Fiecare avea
`3643x2093` pixeli; deci valoarea `1x1` din jurnalul ME-379 nu era dimensiunea
capturii. Ea venea din fallback-ul `failure_record`, care folosea `1x1` când
detectorul ancorei arunca `PlayerActorAnchorError`. Rădăcina este clară în
reproducerea offline: profilul v2 cu `sample_stride=3` depășea deadline-ul de
`12 ms` pe aceste cadre, cu mesajul `player actor detector operation budget
exceeded`; la `50 ms` găsea actorul în toate cele trei checkpoint-uri.

Am păstrat fail-closed, fără să relaxez ROI-ul, pragurile sau confidence:
profilul v2 folosește acum `sample_stride=4`, iar `failure_record` scrie
dimensiunea eșantionată adevărată și eroarea bounded. Auditul offline nou este
`data/runtime/navigation-f3b/actor-frame-audit-live-check-me380-stride4.json`:
`3/3 VISIBLE`, `0` erori, fără input, fără autoritate și fără server truth.
Decizia este în ADR-0118. Aceasta repară diagnosticul și costul detectorului
pentru captura 4K, dar nu este dovadă de mers live; următoarea probă filmată
rămâne blocată până la confirmare explicită nouă.

## ME-381 — Loturi suplimentare de WorldPack candidate (offline)

Am închis două loturi bounded, numai offline. Kalimdor este la
`15.639/40.794` probe, `351` observații acceptate și `0` erori; raportul v6 este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v6.json`,
iar graful v16 are `1.593` deschideri și `3.009` frontiere. Expansion01 este la
`14.000/47.170` probe, `267` observații acceptate și `0` erori; raportul v7 este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v7.json`,
iar graful v14 are `1.093` deschideri și `2.410` frontiere.

Ambele rămân `PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`,
separate de WorldPack-ul Stable și de calea live. Nu s-a pornit WoW, nu s-a
reîncărcat addonul și nu s-a trimis input.

## ME-382 — Lot Kalimdor continuat (offline)

Am procesat încă `1.000` probe bounded pentru Kalimdor, fără client și fără
input. Progresul verificat este `16.639/40.794` seed-uri, `360` observații
acceptate, `578` structuri complete și `0` erori. Raportul v7 este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v7.json`,
iar graful v17 are `1.658` deschideri și `3.099` frontiere, cu acoperire
`PARTIAL_OBSERVED_COMPONENTS` și `execution_authority=false`.

## ME-383 — Regresie după detectorul 4K și loturile candidate (offline)

După schimbarea detectorului de ancoră și generarea rapoartelor de scanare,
suita completă a trecut `1514/1514`. `compileall` a trecut, iar `git diff
--check` nu a găsit erori noi (rămâne doar avertismentul preexistent LF→CRLF
pentru `.gitignore`). Nu s-a pornit WoW, nu s-a reîncărcat addonul și nu s-a
trimis input live.

## ME-384 — Lot Expansion01 continuat (offline)

Am procesat încă `1.000` probe bounded pentru Expansion01. Progresul verificat
este `15.000/47.170` seed-uri, `282` observații acceptate, `526` structuri
complete și `0` erori. Raportul v8 este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v8.json`,
iar graful v15 are `1.144` deschideri și `2.565` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-385 — Lot Kalimdor continuat (offline)

Am procesat încă `1.000` probe bounded pentru Kalimdor. Progresul verificat
este `17.639/40.794` seed-uri, `368` observații acceptate, `611` structuri
complete și `0` erori. Raportul v8 este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v8.json`,
iar graful v18 are `1.740` deschideri și `3.199` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-386 — Audit unificat pentru cataloagele Zygor (offline)

Am adăugat un contract și un audit read-only pentru cele trei cataloage Zygor
folosite de LAB. Raportul este
`data/runtime/navigation-f3b/zygor-knowledge-catalog-audit-20260903.json`:
`3` cataloage și `14.914` intrări validate. NPCData are `3.255/3.255`
poziții; ghidul Horde are `5.207` poziții și `631` pași fără poziție; ghidul
Alliance are `5.228` poziții și `593` pași fără poziție. Toate intrările au
provenance, confidence și `execution_authority=false`; pozițiile sunt
`STATIC_SOURCE_CANDIDATE`, iar politica este
`CLIENT_OBSERVED_CONFIRMATION_REQUIRED`. Nu s-a pornit WoW și nu s-a trimis
input.

## ME-387 — Regresie după auditul Zygor (offline)

Suita completă a trecut `1516/1516`. `compileall` și verificarea de whitespace
au rămas curate; auditul Zygor este doar citire și nu schimbă autoritatea live.

## ME-388 — Lot Expansion01 continuat (offline)

Am procesat încă `1.000` probe bounded pentru Expansion01. Progresul verificat
este `16.000/47.170` seed-uri, `316` observații acceptate, `562` structuri
complete și `0` erori. Raportul v9 este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v9.json`,
iar graful v16 are `1.294` deschideri și `2.850` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-389 — Lot Expansion01 continuat (offline)

Am procesat încă `1.000` probe bounded pentru Expansion01. Progresul verificat
este `17.000/47.170` seed-uri, `336` observații acceptate, `594` structuri
complete și `0` erori. Raportul v10 este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v10.json`,
iar graful v17 are `1.387` deschideri și `3.057` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-390 — Lot Expansion01 continuat (offline)

Am procesat încă `1.000` probe bounded pentru Expansion01. Progresul verificat
este `18.000/47.170` seed-uri, `351` observații acceptate, `630` structuri
complete și `0` erori. Raportul v11 este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v11.json`,
iar graful v18 are `1.450` deschideri și `3.173` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-391 — Poarta actor/cameră verificată și lot Expansion01 continuat (offline)

Am verificat codul runnerului: fabrica live folosește obligatoriu profilul de
ancoră Predator v2, armează poarta după restaurarea camerei și cere un actor
`VISIBLE` înainte de orice cadru de mișcare. Dacă detectorul eșuează sau actorul
dispare, toate controalele sunt eliberate și rezultatul rămâne fail-closed.
Nu am schimbat această regulă și nu am pornit WoW.

Am procesat încă `1.000` probe bounded pentru candidate-ul Expansion01. Progresul
verificat este `19.000/47.170` seed-uri, `366` observații acceptate, `651`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v12.json`,
iar graful agregat este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v19.json`:
`1.502` deschideri și `3.280` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-392 — Lot Kalimdor continuat (offline)

Am procesat încă `1.000` probe bounded pentru candidate-ul Kalimdor. Progresul
verificat este `18.639/40.794` seed-uri, `383` observații acceptate, `645`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v9.json`,
iar graful agregat este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v19.json`:
`1.839` deschideri și `3.388` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-393 — Lot Expansion01 continuat (offline)

Am procesat încă `1.000` probe bounded pentru candidate-ul Expansion01. Progresul
verificat este `20.000/47.170` seed-uri, `381` observații acceptate, `700`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v13.json`,
iar graful agregat este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v20.json`:
`1.597` deschideri și `3.458` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-394 — Lot Kalimdor continuat (offline)

Am procesat încă `1.000` probe bounded pentru candidate-ul Kalimdor. Progresul
verificat este `19.639/40.794` seed-uri, `402` observații acceptate, `681`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v10.json`,
iar graful agregat este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v20.json`:
`1.900` deschideri și `3.477` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-395 — Lot Expansion01 continuat (offline)

Am procesat încă `1.000` probe bounded pentru candidate-ul Expansion01. Progresul
verificat este `21.000/47.170` seed-uri, `409` observații acceptate, `735`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v14.json`,
iar graful agregat este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v21.json`:
`1.743` deschideri și `3.707` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-396 — Lot Kalimdor continuat (offline)

Am procesat încă `1.000` probe bounded pentru candidate-ul Kalimdor. Progresul
verificat este `20.639/40.794` seed-uri, `460` observații acceptate, `716`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v11.json`,
iar graful agregat este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v21.json`:
`2.104` deschideri și `3.961` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-397 — Lot Expansion01 continuat (offline)

Am procesat încă `1.000` probe bounded pentru candidate-ul Expansion01. Progresul
verificat este `22.000/47.170` seed-uri, `420` observații acceptate, `770`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v15.json`,
iar graful agregat este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v22.json`:
`1.803` deschideri și `3.822` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-398 — Lot Kalimdor continuat (offline)

Am procesat încă `1.000` probe bounded pentru candidate-ul Kalimdor. Progresul
verificat este `21.639/40.794` seed-uri, `511` observații acceptate, `752`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v12.json`,
iar graful agregat este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v22.json`:
`2.268` deschideri și `4.291` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-399 — Lot Expansion01 continuat (offline)

Am procesat încă `1.000` probe bounded pentru candidate-ul Expansion01. Progresul
verificat este `23.000/47.170` seed-uri, `429` observații acceptate, `805`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v16.json`,
iar graful agregat este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v23.json`:
`1.836` deschideri și `3.881` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-400 — Lot Expansion01 continuat (offline)

Am procesat încă `1.000` probe bounded pentru candidate-ul Expansion01. Progresul
verificat este `24.000/47.170` seed-uri, `440` observații acceptate, `841`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v17.json`,
iar graful agregat este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v24.json`:
`1.886` deschideri și `3.990` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-401 — Lot Kalimdor continuat (offline)

Am procesat încă `1.000` probe bounded pentru candidate-ul Kalimdor. Progresul
verificat este `22.639/40.794` seed-uri, `544` observații acceptate, `788`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v13.json`,
iar graful agregat este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v23.json`:
`2.374` deschideri și `4.536` frontiere. Candidate-ul rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`; nu s-a pornit
WoW și nu s-a trimis input.

## ME-402 — Lot extins Expansion01 (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Expansion01. Raportul de
progres verifică `26.000/47.170` seed-uri, `493` observații acceptate, `909`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v26.json`.
Agregarea strictă a taskurilor complete este păstrată în
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v26.json`:
`489` observații în grafic, `2.137` deschideri și `4.466` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-403 — Audit complet al registrului WorldPack (offline)

Am rulat auditul reproductibil al registrului pentru clientul TBC
`2.4.3.8606`. Rezultatul confirmă `83/83` identități de hartă, `35` hărți în
queue, `4` queue-uri declarate `COMPLETE`, `7` hărți `topographic_ready` și o
singură hartă `autonomous_ready` (Azeroth). Candidate-urile Kalimdor și
Expansion01 rămân topografice, nu autonome; raportul este
`data/runtime/navigation-f3b/world-map-registry-audit-me403.json`, iar
`--check` a confirmat reproducibilitatea. Nu s-a pornit WoW și nu s-a trimis
input.

## ME-404 — Lot extins Kalimdor (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Kalimdor. Raportul de
progres verifică `24.639/40.794` seed-uri, `600` observații acceptate, `858`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v15.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v25.json`:
`599` observații în grafic, `2.534` deschideri și `5.161` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-405 — Lot extins Expansion01 (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Expansion01. Raportul de
progres verifică `28.000/47.170` seed-uri, `541` observații acceptate, `982`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v28.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v28.json`:
`541` observații în grafic, `2.263` deschideri și `4.891` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-406 — Lot extins Kalimdor (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Kalimdor. Raportul de
progres verifică `26.639/40.794` seed-uri, `677` observații acceptate, `930`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v17.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v27.json`:
`677` observații în grafic, `2.588` deschideri și `5.520` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-407 — Lot extins Expansion01 (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Expansion01. Raportul de
progres verifică `30.000/47.170` seed-uri, `582` observații acceptate, `1.052`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v30.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v30.json`:
`582` observații în grafic, `2.336` deschideri și `5.150` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-408 — Lot extins Expansion01 (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Expansion01. Raportul de
progres verifică `32.000/47.170` seed-uri, `622` observații acceptate, `1.121`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v32.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v32.json`:
`622` observații în grafic, `2.412` deschideri și `5.424` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-409 — Lot extins Expansion01 (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Expansion01. Raportul de
progres verifică `34.000/47.170` seed-uri, `648` observații acceptate, `1.193`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v34.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v34.json`:
`648` observații în grafic, `2.497` deschideri și `5.602` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-410 — Lot extins Kalimdor (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Kalimdor. Raportul de
progres verifică `28.639/40.794` seed-uri, `721` observații acceptate, `998`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v19.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v29.json`:
`721` observații în grafic, `2.770` deschideri și `5.920` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-411 — Lot extins Expansion01 (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Expansion01. Raportul de
progres verifică `36.000/47.170` seed-uri, `686` observații acceptate, `1.264`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v36.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v36.json`:
`686` observații în grafic, `2.591` deschideri și `5.875` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-412 — Lot extins Kalimdor (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Kalimdor. Raportul de
progres verifică `30.639/40.794` seed-uri, `750` observații acceptate, `1.069`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v21.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v31.json`:
`749` observații în grafic, `2.967` deschideri și `6.268` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-413 — Lot extins Expansion01 (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Expansion01. Raportul de
progres verifică `38.000/47.170` seed-uri, `692` observații acceptate, `1.334`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v38.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v38.json`:
`692` observații în grafic, `2.625` deschideri și `5.963` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-414 — Lot extins Kalimdor (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Kalimdor. Raportul de
progres verifică `32.639/40.794` seed-uri, `766` observații acceptate, `1.140`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v23.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v33.json`:
`766` observații în grafic, `3.008` deschideri și `6.381` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-415 — Lot extins Expansion01 (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Expansion01. Raportul de
progres verifică `40.000/47.170` seed-uri, `724` observații acceptate, `1.406`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v40.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v40.json`:
`724` observații în grafic, `2.685` deschideri și `6.143` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-416 — Lot extins Kalimdor (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Kalimdor. Raportul de
progres verifică `34.639/40.794` seed-uri, `882` observații acceptate, `1.211`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v25.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v35.json`:
`880` observații în grafic, `3.160` deschideri și `6.702` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-417 — Lot extins Expansion01 (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Expansion01. Raportul de
progres verifică `42.000/47.170` seed-uri, `756` observații acceptate, `1.476`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v42.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v42.json`:
`756` observații în grafic, `2.772` deschideri și `6.352` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-418 — Lot extins Kalimdor (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Kalimdor. Raportul de
progres verifică `36.639/40.794` seed-uri, `927` observații acceptate, `1.282`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v27.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v37.json`:
`927` observații în grafic, `3.262` deschideri și `6.952` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-419 — Lot extins Expansion01 (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Expansion01. Raportul de
progres verifică `44.000/47.170` seed-uri, `811` observații acceptate, `1.547`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v44.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v44.json`:
`811` observații în grafic, `2.926` deschideri și `6.696` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-420 — Scanare completă Expansion01 (offline)

Am terminat toate `47.170/47.170` probe pentru candidate-ul Expansion01:
`878` observații acceptate, `1.659` structuri complete și `0` erori. Raportul
este `data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v48.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v48.json`:
`878` observații, `3.098` deschideri și `7.109` frontiere.
Graful rămâne `PARTIAL_OBSERVED_COMPONENTS` deoarece include doar structurile
cu observații confirmate; `execution_authority=false`, fără pornire WoW și fără
input.

## ME-421 — Lot extins Kalimdor (offline)

Am procesat `2.000` probe bounded pentru candidate-ul Kalimdor. Raportul de
progres verifică `38.639/40.794` seed-uri, `958` observații acceptate, `1.353`
structuri complete și `0` erori. Raportul este
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v29.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v39.json`:
`958` observații în grafic, `3.444` deschideri și `7.264` frontiere.
Candidate-ul rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu
`execution_authority=false`; nu s-a pornit WoW și nu s-a trimis input.

## ME-422 — Scanare completă Kalimdor (offline)

Am terminat toate `40.794/40.794` probe pentru candidate-ul Kalimdor:
`1.003` observații acceptate, `1.426` structuri complete și `0` erori. Raportul
este `data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v33.json`.
Agregarea strictă a taskurilor complete este în
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v43.json`:
`1.003` observații, `3.780` deschideri și `7.749` frontiere.
Graful rămâne `PARTIAL_OBSERVED_COMPONENTS` deoarece include doar structurile
cu observații confirmate; `execution_authority=false`, fără pornire WoW și fără
input.

## ME-423 — Audit registru după scanările continentelor (offline)

Auditul reproductibil al registrului confirmă `83/83` identități, `35` hărți în
queue, `4` queue-uri `COMPLETE`, `7` hărți `topographic_ready` și `1` hartă
`autonomous_ready` (Azeroth). Kalimdor și Expansion01 sunt declarate
`topographic_ready`, dar nu `autonomous_ready`, iar verificarea `--check` a
trecut în `data/runtime/navigation-f3b/world-map-registry-audit-me422.json`.
Nu s-a pornit WoW și nu s-a trimis input.

## ME-424 — Dry-run Razorfen Kraul pe copia verificată (offline)

Am verificat pipeline-ul de bake pentru `47:RazorfenKraulInstance` folosind
inventarul pin-uit `world-continents-v1`, extractorul v3 și MapBuilder-ul
pin-uit v5. Dry-run-ul a raportat `initial_state=COMPLETE`, `bvh_ready=true`,
`server_dependency=false`, `emulator_dependency=false` și
`execution_authority=false`. Dovada este
`data/runtime/navigation-f3b/razorfen-kraul-map-bake-dry-run-me424.json`, iar
queue-ul reproductibil este
`data/runtime/navigation-f3b/razorfen-kraul-map-bake-dry-run-me424-queue.json`.

Nu am rulat extractorul, MapBuilder-ul sau WoW și nu am trimis input. Copia
existentă `tbc243-razorfen-v2` nu a fost modificată; aceasta confirmă că nu
trebuie refăcută sau înlocuită harta Razorfen Kraul.

## ME-425 — Karazhan: dry-run separă copia parțială de WorldPack-ul sigilat (offline)

Dry-run-ul aceleiași pipeline pentru `532:Karazahn` pe directory-ul experimental
`navigation\\tbc243-full-v1` raportează `initial_state=NAVMESH_PARTIAL` și
`bvh_ready=true`. Dovada este
`data/runtime/navigation-f3b/karazahn-map-bake-dry-run-me425.json`, iar queue-ul
este `data/runtime/navigation-f3b/karazahn-map-bake-dry-run-me425-queue.json`.

Această stare nu înseamnă că am pierdut harta: WorldPack-ul sigilat v3 rămâne
copia verificată cu `9/9` tile-uri Karazhan. Nu am rulat MapBuilder-ul și nu am
modificat nici copia experimentală, nici WorldPack-ul Stable; nu s-a pornit WoW
și nu s-a trimis input.

## ME-426 — Dry-run pentru Razorfen Downs și Shadowfang (offline)

Am verificat încă două copii locale existente cu pipeline-ul pin-uit: atât
`129:RazorfenDowns`, cât și `33:Shadowfang` raportează `initial_state=COMPLETE`
și `bvh_ready=true`. Dovezile sunt
`data/runtime/navigation-f3b/razorfen-downs-map-bake-dry-run-me426.json` și
`data/runtime/navigation-f3b/shadowfang-map-bake-dry-run-me427.json`, cu queue-
urile lor versionate în același director.

Acestea sunt verificări de stare, nu rebuild-uri: nu am rulat extractorul sau
MapBuilder-ul, nu am schimbat WorldPack-ul și nu s-a pornit WoW ori input live.

## ME-427 — Scanare Razorfen Downs fără WMO confirmat (offline)

Am rulat toate cele `39/39` probe planificate pentru singurul WMO din
Razorfen Downs, cu workerul v34 cerut de plan. Progresul este în
`data/runtime/navigation-f3b/razorfen-downs-candidate-v1-structure-access-scan-progress-v1.json`:
`0` observații acceptate, `39` seed-uri în afara structurii, `0` probe fără
poligon, `0` erori și structură `COMPLETE_NO_CONFIRMED_WMO`.

Nu am fabricat un graf gol și nu am promovat această hartă. Agregarea strictă
nu are ce observații să includă; candidata rămâne fără dovadă de access opening,
cu `execution_authority=false`. Scanarea a fost offline, fără WoW și fără input.

## ME-428 — Grafic candidat MonasteryInstances (offline)

Am verificat planul și am închis scanarea read-only pentru cele `126/126` probe
din `MonasteryInstances` (`4` WMO-uri): `15` observații acceptate, `0` erori,
`0` seed-uri lipsă și `4` structuri complete. Agregarea strictă a taskurilor
cu observații a produs `15` observații, `43` deschideri și `88` frontiere în
`data/runtime/navigation-f3b/monastery-candidate-v1-structure-access-partial-v2.json`.
Progresul complet este în
`data/runtime/navigation-f3b/monastery-candidate-v1-structure-access-scan-progress-v1.json`.

Graful este `PARTIAL_OBSERVED_COMPONENTS`, acoperă doar cele două structuri cu
observații și rămâne separat de Stable, cu `execution_authority=false`. Nu s-a
pornit WoW și nu s-a trimis input.

## ME-429 — Grafic candidat Stratholme (offline)

Am indexat și am verificat cele `8` WMO-uri din `Stratholme`, apoi am rulat
toate cele `252/252` probe cu workerul v34. Progresul este în
`data/runtime/navigation-f3b/stratholme-candidate-v1-structure-access-scan-progress-v1.json`:
`17` observații acceptate, `20` probe fără poligon, `0` erori și `8` structuri
complete. Agregarea strictă a taskurilor cu observații a produs `15` deschideri
și `51` frontiere în
`data/runtime/navigation-f3b/stratholme-candidate-v1-structure-access-partial-v1.json`.

Graful rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`,
fără promovare în Stable și fără pornire WoW sau input.

## ME-430 — Registry include awareness candidat pentru două instanțe (offline)

Am legat în registry doar referințele read-only pentru `189:MonasteryInstances`
și `329:Stratholme`, apoi am rulat auditul reproductibil. Rezultatul
`data/runtime/navigation-f3b/world-map-registry-audit-me430.json` trece
`--check` și raportează `83/83` identități, `35` hărți în queue, `9` hărți
`topographic_ready` și `1` hartă `autonomous_ready` (Azeroth). Cele două hărți
noi rămân `autonomous_ready=false` deoarece nu au semantic catalog.

Schimbarea este documentată în ADR-0119. Nu s-a pornit WoW și nu s-a trimis
input; rollback-ul este eliminarea celor două referințe candidate din registry.

## ME-431 — Regresie completă după legarea candidatelor (offline)

Suita completă a trecut cu `1517 passed in 132,54 s` după adăugarea
MonasteryInstances și Stratholme în registry-ul read-only. Nu s-au schimbat
limitele de execuție, nu s-a pornit WoW și nu s-a trimis input live.

## ME-432 — Razorfen Downs: separare între WMO și proba scurtă de tavan (offline)

Am găsit de ce prima scanare Razorfen Downs raporta toate punctele ca fiind
în afara structurii: punctele erau pe suprafață `wmo` și în limitele 3D ale
WMO-ului, dar camera de probă la doar `12` yarzi în sus era liberă. Acea probă
nu măsoară înălțimea întregii încăperi. Am separat cele două fapte în
`build_local_environment_awareness`: containment-ul WMO rămâne valid, iar
`overhead_clear` rămâne semnal separat pentru tavan și cameră. Regula este în
ADR-0120 și are test dedicat.

Am refăcut scanarea într-un director nou, fără să ating rezultatul vechi:
`39/39` probe, `8` observații WMO acceptate, `31` puncte open-ground și `0`
erori. Graficul candidat este
`data/runtime/navigation-f3b/razorfen-downs-candidate-v1-structure-access-partial-v2.json`:
`81` frontiere, `0` access openings și `coverage_state=PARTIAL_OBSERVED_COMPONENTS`.
Nu este rută autonomă și are `execution_authority=false`.

Am legat map-ul `129:RazorfenDowns` în registry doar ca awareness read-only.
Auditul verificat este
`data/runtime/navigation-f3b/world-map-registry-audit-me432.json`: `83/83`
identități, `10` hărți `topographic_ready` și `1` hartă
`autonomous_ready` (Azeroth). Nu s-a pornit WoW și nu s-a trimis input.

## ME-433 — Regresie țintită după corecția WMO (offline)

Testele pentru awareness local, scan runner, grafic și registry au trecut:
`28 passed`. Nicio armare live nu a fost creată și testul filmat rămâne
închis până la o confirmare explicită nouă.

## ME-434 — Candidat Deadmines construit și verificat structural (offline)

Am extras `36/36` dale ADT pentru `36:DeadminesInstance` din clientul pin-uit
TBC `2.4.3.8606`, am generat semantica locală și am construit navmesh-ul într-un
director candidat separat (`tbc243-full-v3-candidate`). Catalogul candidat este
`data/runtime/navigation-f3b/deadmines-candidate-v3-world-catalog-me434.json`,
iar coada și rezultatul bake-ului sunt
`data/runtime/navigation-f3b/deadmines-instance-bake-queue-me434.json` și
`data/runtime/navigation-f3b/deadmines-instance-bake-me434-final.json`.

Auditul navmesh verifică `36/36` dale, `0` dale lipsă și `0` dale eșuate, dar
raportează diagnostice Recast (`68` erori de contur și `178` avertismente), deci
rezultatul este `COMPLETE_WITH_RECAST_DIAGNOSTICS`, nu o aprobare geometrică
implicită. Validatorul geometric independent a trecut `36/36` dale cu `0`
eșecuri în
`data/runtime/navigation-f3b/deadmines-candidate-v3-geometry-me434.json`.

Am sigilat candidatul ca WorldPack separat, fără să ating Stable:
`tbc243-deadmines-candidate-v3`, `279` structuri (`12` WMO, `267` doodad),
`runtime_dependencies` toate false și `execution_authority=false`. Profilul
este `config/navigation/world-pack-runtime-tbc243-deadmines-candidate-v3.json`,
iar indexul structurilor este
`data/runtime/navigation-f3b/deadmines-candidate-v3-world-structure-index-me434.json`.
Nu l-am legat în registry ca hartă autonomă: nu are semantic catalog de
destinații și nu are scanare de access openings. Nu s-a pornit WoW și nu s-a
trimis input live.

## ME-435 — Receipt aggregate MapBuilder și WorldPack Deadmines v3b (offline)

Auditorul de bake înțelege acum rezumatul pin-uit MapBuilder v5 (`N tiles`) doar
când totalul este exact `256 × ADT`; testul nou trece și nu schimbă pragurile
de eșec. Raportul Deadmines indică acum explicit `36/36` ADT terminate,
`36/36` nav ADT, `0` lipsă și `0` eșuate, cu diagnosticele Recast păstrate.

Pentru trasabilitate am păstrat candidatul v3 și am sigilat o versiune nouă
`tbc243-deadmines-candidate-v3b`, cu hash de conținut
`470b324c425bff9ed638ff43cd44d87271ab8d30b2f32493a0b379f0e976a69a`. Profilul
este `config/navigation/world-pack-runtime-tbc243-deadmines-candidate-v3b.json`,
iar indexul WMO/doodad este
`data/runtime/navigation-f3b/deadmines-candidate-v3b-world-structure-index-me434.json`.
Pack-ul a fost verificat ca runtime-portabil (`279` structuri, `12` WMO,
`267` doodad); rămâne candidat read-only, fără semantic catalog și fără
autoritate de execuție. Nu s-a pornit WoW și nu s-a trimis input live.

## ME-436 — Candidat dungeons: Scholomance + Deadmines (offline)

Am extras și construit `289:SchoolofNecromancy` în același director candidat:
`16/16` dale ADT, semantici generate și navmesh complet. Catalogul cu cele două
instanțe este
`data/runtime/navigation-f3b/dungeons-candidate-v1-world-catalog-me436.json`.
Auditul bake pentru Scholomance are `16/16` ADT terminate și `0` dale eșuate,
cu diagnosticele Recast păstrate; validatorul geometric trece `16/16`.

Scanarea read-only a celor `6` WMO-uri a procesat `174/174` probe, cu `37`
observații acceptate, `5` fără poligon și `0` erori. Graful este
`data/runtime/navigation-f3b/schoolofnecromancy-structure-access-partial-me436.json`:
`58` access openings și `331` boundary chains, starea
`PARTIAL_OBSERVED_COMPONENTS`.

WorldPack-ul comun `tbc243-dungeons-candidate-v1` este sigilat și verificat,
cu `2` hărți, `688` artefacte și `execution_authority=false`. Nu l-am promovat
în registry ca rută autonomă: nu are semantic catalog pentru destinații și nu
are autoritate de execuție. Nu s-a pornit WoW și nu s-a trimis input live.

## ME-437 — Scholomance legată read-only în registry (offline)

Am legat `289:SchoolofNecromancy` în registry doar ca hartă topografică
read-only, folosind indexul WMO și graful de access scan din candidatul verificat.
Auditul reproductibil `--check` este
`data/runtime/navigation-f3b/world-map-registry-audit-me436.json` și confirmă
`83/83` identități, `11` hărți `topographic_ready` și `1`
`autonomous_ready`. Scholomance rămâne `autonomous_ready=false` deoarece nu
există semantic catalog de destinații; decizia este în ADR-0123.

Suita completă după schimbare este `1519 passed`. Nu s-a pornit WoW și nu s-a
trimis input live.

## ME-438 — Hellfire Rampart construit și scanat offline

Am extras `72/72` dale ADT pentru `543:HellfireRampart` din clientul pin-uit
TBC `2.4.3.8606`, am generat semantica locală și am construit navmesh-ul în
directorul candidat separat `tbc243-full-v3-candidate`. Auditul de bake este
`COMPLETE_WITH_RECAST_DIAGNOSTICS`, cu `72/72` dale terminate, `72/72` dale nav,
`0` lipsă și `0` eșuate; validatorul geometric independent trece `72/72`.

WorldPack-ul comun `tbc243-dungeons-candidate-v2` rămâne separat de Stable și
conține acum `3` hărți (`36`, `289`, `543`), cu hash
`552fec12d4f10b579eb3368e23770c087e5da69c5a76066e3dd1ccb2a3a75df4` și fără
dependențe runtime sau autoritate de execuție. Indexul Hellfire are `1.747`
structuri (`43` WMO, `1.704` doodad).

Scanarea locală read-only a planului Hellfire a terminat `1.221/1.221` probe:
`177` observații WMO acceptate, `991` structuri neconfirmate, `53` fără poligon
și `0` erori. Agregarea strictă a produs `122` access openings și `1.352`
boundary chains în
`data/runtime/navigation-f3b/hellfire-rampart-structure-access-partial-me438.json`;
starea rămâne `PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`.
Nu s-a pornit WoW și nu s-a trimis input live.

## ME-439 — Hellfire Rampart legat read-only în registry (offline)

Am legat `543:HellfireRampart` în registry numai pentru awareness topografic,
folosind profilul candidat v2, indexul și graful de mai sus; nu există semantic
catalog, deci `autonomous_ready=false`. Auditul reproductibil este
`data/runtime/navigation-f3b/world-map-registry-audit-me438.json` și trece
`--check`: `83/83` identități, `12` hărți `topographic_ready` și `1` hartă
`autonomous_ready`. WorldPack-urile vechi și rollback-ul rămân neschimbate.
Suita completă offline după legare rămâne verde: `1519 passed`.

## ME-440 — TanarisInstance construit și scanat offline

Am extras și construit `21/21` dale ADT pentru `209:TanarisInstance` din
clientul pin-uit TBC `2.4.3.8606`, în candidatul separat
`tbc243-full-v3-candidate`. Auditul bake este
`COMPLETE_WITH_RECAST_DIAGNOSTICS`, cu `21/21` dale terminate, `21/21` dale nav,
`0` lipsă și `0` eșuate; validatorul geometric independent trece `21/21`.

WorldPack-ul nou `tbc243-dungeons-candidate-v3` conține patru hărți (`36`,
`209`, `289`, `543`), este sigilat și verificat cu hash
`f6adc3e3a41686fc8e4710bacac073c2d905fc3bc0803514e15e34f21a13bfe9`. Are
`1.268` artefacte, toate dependențele runtime false și
`execution_authority=false`; pack-urile v1/v2 rămân neschimbate.

Indexul Tanaris are `2.146` structuri (`78` WMO, `2.068` doodad). Scanarea
locală read-only a închis `2.178/2.178` probe: `418` observații WMO acceptate,
`1.760` respinse și `0` erori. Graful strict este
`data/runtime/navigation-f3b/tanaris-instance-structure-access-partial-me440.json`:
`259` access openings, `1.410` boundary chains și starea
`PARTIAL_OBSERVED_COMPONENTS`. Nu s-a pornit WoW și nu s-a trimis input live.

## ME-441 — TanarisInstance legat read-only în registry (offline)

Am legat `209:TanarisInstance` numai pentru awareness topografic, folosind
profilul v3, indexul și graful candidat. Nu există semantic catalog, deci
`autonomous_ready=false`. Auditul
`data/runtime/navigation-f3b/world-map-registry-audit-me440.json` trece
`--check`: `83/83` identități, `13` hărți `topographic_ready` și `1` hartă
`autonomous_ready`. Suita completă offline rămâne `1519 passed`; nu s-a pornit
WoW și nu s-a trimis input live.

## ME-442 — Sunwell5ManFix construit offline cu alpha-map comprimat

Am găsit cauza exactă pentru care bake-ul `585:Sunwell5ManFix` se oprea:
anumite ADT-uri MCAL folosesc alpha-map comprimat. Parserul are acum un
decoder RLE bounded, cu ieșire obligatorie de `4096` octeți și respingere pentru
blocuri invalide; regula și testul sunt în ADR-0126.

Bake-ul din asset-urile clientului pin-uit TBC `2.4.3.8606` a trecut `64/64`
ADT și `64/64` nav tiles. Auditul este
`data/runtime/navigation-f3b/sunwell5manfix-navmesh-quality-me442-v4.json`:
`COMPLETE_WITH_RECAST_DIAGNOSTICS`, fără dale lipsă sau eșuate. Validatorul
geometric independent trece `64/64` în
`data/runtime/navigation-f3b/sunwell5manfix-geometry-me442.json`. Diagnosticele
Recast rămân vizibile; nu sunt tratate ca rută autonomă.

## ME-443 — Sunwell5ManFix legat read-only în registry (offline)

WorldPack-ul candidat v4, `tbc243-dungeons-candidate-v4`, conține cinci hărți
(`36`, `209`, `289`, `543`, `585`) și este verificat cu hash
`8c7bafb2a18456eadf0ff3475355918c5dec94cc840b3e099f74dbd36bc07aa`. Are
`1632` artefacte, runtime dependencies false și `execution_authority=false`;
pack-urile v1–v3 rămân neschimbate. Profilul este
`config/navigation/world-pack-runtime-tbc243-dungeons-candidate-v4.json`.

Indexul Sunwell are `1711` structuri (`11` WMO, `1700` doodad). Scanarea
read-only a terminat `339/339` probe: `43` observații WMO acceptate, `226`
neconfirmate, `26` cu awareness static incomplet, `44` fără poligon și `0`
erori. Graful
`data/runtime/navigation-f3b/sunwell5manfix-structure-access-partial-me442.json`
are `50` access openings, `449` boundary chains și
`coverage_state=PARTIAL_OBSERVED_COMPONENTS`.

Map-ul `585` este legat în registry numai pentru awareness topografic
read-only. Auditul `data/runtime/navigation-f3b/world-map-registry-audit-me442.json`
trece `--check` cu `83/83` identități, `14` hărți `topographic_ready` și `1`
`autonomous_ready`; Sunwell rămâne `autonomous_ready=false` fără semantic
catalog. Regresia completă offline după schimbare este `1521 passed`. Nu s-a
pornit WoW și nu s-a trimis input live.

## ME-444 — SunwellPlateau construit și scanat offline

Am extras și construit `30/30` dale ADT pentru `580:SunwellPlateau` din
clientul pin-uit TBC `2.4.3.8606`. Bake-ul este PASS, cu `30/30` nav tiles; auditul
de calitate păstrează diagnosticele Recast fără dale lipsă sau eșuate, iar
validatorul geometric independent trece `30/30`.

WorldPack-ul candidat v5, `tbc243-dungeons-candidate-v5`, este sigilat și
verificat cu hash
`67f15af4b319b0d014420cb49691bb2a5661ee24c3f36e3994e9e67fba7d4bd3`. Are șase
hărți (`36`, `209`, `289`, `543`, `580`, `585`), `1700` artefacte și toate
dependențele runtime false. Pack-ul v4 și pack-urile mai vechi rămân pentru
rollback.

Indexul Sunwell Plateau are `1565` structuri (`14` WMO, `1551` doodad).
Scanarea bounded read-only a închis `453/453` probe: `47` observații WMO
acceptate, `252` neconfirmate, `33` cu awareness static incomplet, `121` fără
poligon și `0` erori. Graful are `32` access openings și `418` boundary chains,
cu `coverage_state=PARTIAL_OBSERVED_COMPONENTS`.

## ME-445 — SunwellPlateau legat read-only în registry (offline)

Map-ul `580` este legat numai pentru awareness topografic, folosind profilul v5,
indexul și graful candidat; nu există semantic catalog, deci
`autonomous_ready=false`. Auditul registry
`data/runtime/navigation-f3b/world-map-registry-audit-me444.json` confirmă
`83/83` identități și `15` hărți `topographic_ready`; nu s-a pornit WoW și nu
s-a trimis input live.

## ME-446 — ZulAman construit și scanat offline

Am extras și construit `25/25` dale ADT pentru `568:ZulAman` din clientul
pin-uit TBC `2.4.3.8606`. Bake-ul este PASS, cu `25/25` nav tiles; auditul de
calitate păstrează diagnosticele Recast fără dale lipsă sau eșuate, iar
validatorul geometric independent trece `25/25`.

WorldPack-ul candidat v6, `tbc243-dungeons-candidate-v6`, este sigilat și
verificat cu hash
`6e2e4d3eddbaec9df86e8656e63f7f36106f61d65e9e89f90d2df7af642549f2`. Are șapte
hărți (`36`, `209`, `289`, `543`, `568`, `580`, `585`), `1873` artefacte și
toate dependențele runtime false. Pack-urile v1–v5 rămân pentru rollback.

Indexul ZulAman are `1323` structuri (`35` WMO, `1288` doodad). Scanarea
bounded read-only a închis `993/993` probe: `229` observații WMO acceptate,
`666` neconfirmate, `56` cu awareness static incomplet, `42` fără poligon și
`0` erori. Graful are `53` access openings și `1362` boundary chains, cu
`coverage_state=PARTIAL_OBSERVED_COMPONENTS`.

## ME-447 — ZulAman legat read-only în registry (offline)

Map-ul `568` este legat numai pentru awareness topografic, folosind profilul v6,
indexul și graful candidat; nu există semantic catalog, deci
`autonomous_ready=false`. Auditul registry
`data/runtime/navigation-f3b/world-map-registry-audit-me448.json` confirmă
`83/83` identități și `16` hărți `topographic_ready`; nu s-a pornit WoW și nu
s-a trimis input live.

## ME-449 — Ultima probă live: camera a fost cauza opririi înainte de mers

La cererea operatorului am făcut o singură probă live bounded, fără combat, pe
clientul LAB TBC `2.4.3.8606`, cu godmode-ul Predator activ. Rezultatul este
`data/runtime/navigation-f3b/results/navmesh-roaming-15664ad7-a6c1-4566-95af-e84c5c19d65e.json`:
`CAMERA_ACTOR_LOST`, `0` cadre de control și `0` comenzi W; poziția HUD a rămas
`[1676.6913497746687, 1678.2254263492164]`. Nu s-a mișcat, nu a murit și nu a
existat combat.

Filmarea NVIDIA locală este
`C:\Users\LabUser\Videos\NVIDIA\Wow.exe\Wow.exe 2026.09.03 - 11.42.49.135.mp4`
(`285.914700` secunde). Primele cadre utile au arătat doar partea de sus a
personajului, iar după ce camera s-a așezat corpul a devenit vizibil. Un
checkpoint real de după oprire a trecut auditul actorului `VISIBLE`; deci
detectorul și corpul nu au dispărut, ci camera a fost încă în tranziție când
poarta a cerut dovada.

Aceasta este o oprire corectă fail-closed, nu pierderea WorldPack-ului sau a
anchor-ului Crypt. Armul a fost retras după probă, iar clientul a rămas viu.

## ME-450 — Așteptare bounded pentru camera de pornire (offline, fără rerulare live)

Runner-ul a primit `wait_for_camera_integrity`: după `SetView(3)` așteaptă cel
mult `40` cadre la `0,10` secunde și cere `3` cadre consecutive cu actorul
vizibil. Poarta rămâne nearmată în această așteptare; dacă actorul nu apare,
runner-ul se oprește la fel ca înainte. Nu se acceptă HUD singur, minimapă sau
heading estimat.

Regresia țintită a trecut `5` teste, iar `py_compile` nu a raportat erori.
Nu am pornit încă o nouă probă live după patch; ea rămâne următorul test unic,
filmat și fără combat, după confirmare explicită.

## ME-452 — Topologia completă a Crypt-ului restaurată și verificată live

Regresia nu provenea din WorldPack-ul construit în sesiunea Luna. Navmesh-ul
fără memoria dinamică produce un coridor complet de `50` poligoane și `69`
puncte de ghidare din spawn. Un obstacol învățat greșit, confirmat anterior ca
excludere Detour chiar lângă spawn, reducea aceeași interogare la un singur
poligon și două puncte. O demonstrație `COMPLETE` poate acum contrazice numai
anvelopa acelui obstacol; nu furnizează și nu înlocuiește ruta autonomă.

Heading-ul clientului folosește deplasarea numai ca corecție bounded în timpul
unui W continuu și neobstrucționat. Cele două etichete rezultate sunt acceptate
de poarta de integritate ca dovezi vizuale curente. Detectorul de siluetă rămâne
diagnostic în navigarea normală și devine blocant doar cu
`--require-player-anchor`, inclusiv în preflight.

Dovezi live filmate, fără combat și cu godmode activ:

- `navmesh-roaming-109fb333-5a13-47cd-a804-0db50831db88.json`: Predator a
  parcurs `83.96 yd`, a urcat Crypt-ul și a ieșit afară; oprirea a fost numai
  expirarea armării temporale după `354` cadre.
- `navmesh-roaming-7fb027c0-34c5-47b5-813b-cff6c0dcc784.json`: continuarea
  autonomă a parcurs `153.86 yd` pe potecă, cu `0` recuperări și fără abatere
  prin pădure; limita a fost `500` cadre.
- `navmesh-roaming-0a0f7d27-d3e9-484a-afbb-fb8514d3d98b.json`: status final
  `ARRIVED` în raza semantică Deathknell după încă `18` cadre și `3.41 yd`.

Clipurile scurte sunt în
`data/runtime/operator/live-video/me452b-inspect/crypt-egress-fixed-me452b.mp4`
și
`data/runtime/operator/live-video/me452d-inspect/post-crypt-to-deathknell-me452d.mp4`.
Suita completă după reparație este `1531 passed`.
