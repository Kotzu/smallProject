# Movement Engine completion audit — 2026-08-31

This audit records current evidence without promoting partial evidence to
completion. It covers the persistent Movement Engine objective after the
handoff and the ME-111 LAB awareness-scoring change.

| Requirement | Current state | Evidence / reason |
| --- | --- | --- |
| Crypt hairpins, narrow curves and navmesh frontier | **Improved offline; live gate still open** | Monte Carlo v6 passes `1,200/1,200` offline steering trials; the outbound-tangent projection correction passes `100/100` on Shadowfang `28_30` and `100/100` on `28_31` (zero collisions/pivots; maxima `1.988531 yd` and `1.986825 yd`). The current profile-bound validator v46 retains bounded Crypt→Brill→Crypt semantic evidence and the hill frontier as an explicit reset. A fresh live revalidation is not authorized. |
| Autonomous semantic routing, no executable hardcoded waypoints | **Verified** | Semantic sequence stores IDs only; route is generated from client WorldPack/navmesh/topology evidence and `route_is_operator_hardcoded=false` in runtime snapshots. |
| Offline tests and simulations | **Verified** | Full regression after the hash-bound worker fix is `1343/1343`; the current focused registry/Movement/UI/audit set is `195/195`; compileall, diff check and the semantic validator remain green offline. |
| One bounded live Crypt→Brill→Crypt test | **Verified as movement evidence** | `data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260831-v38.json` validates against the supervisor schema; both cycles are `ARRIVED`, zero combat handoffs, `execution_authority=false`. Offline reevaluation of both traces also passes the quality gate with zero unexplained gaps. ME-117 now prevents projected progress from masking a physical pause in future runs. |
| All client map identities visible to Control Center | **Verified** | World-map loader resolves 83 inventory-bound map profiles. |
| Autonomous routing on every map | **Not verified / fail-closed by design** | Azeroth remains the only profile with complete runtime, semantic, structure and access binding. Shadowfang plus the new proof v3 profile for Razorfen Kraul/Karazhan are runtime-loadable, but their semantic/access promotion evidence is incomplete and readiness remains `OBSERVE_ONLY`; all other maps are inventory-only. |
| Kalimdor structure/access groundwork | **Verified partial; not promoted** | Local WorldPack indexing covers 1,018 tiles, 1,426 WMO and 103,898 doodads. The current bounded progress is `12,639/40,794` seeds with 290 accepted observations, 437 completed structures, 0 worker errors and 28,155 seeds remaining. |
| Kalimdor targeted WMO graph | **Verified partial; not promoted** | The latest strict aggregate `partial-v13` contains 290 observations, 1,285 openings and 2,466 boundary chains. The graph remains `PARTIAL_OBSERVED_COMPONENTS`; it is not a map-wide access graph. |
| Kalimdor extended structure scan | **Verified partial; not promoted** | `kalimdor-candidate-structure-access-scan-progress-v4.json` is the current checkpoint (`12,639/40,794`); v13 is linked only for read-only structure awareness and cannot open registry autonomy. |
| Expansion01 structure/access groundwork | **Verified partial; not promoted** | Current bounded progress is `10,000/47,170` seeds with 196 accepted observations, 352 completed structures and 0 worker errors; the strict aggregate `partial-v10` has 728 openings and 1,764 boundary chains. |
| Client map-area transforms | **Verified read-only** | `world-map-zone-transforms-tbc243-8606.json` covers 68 unique audited `(map_id, area_id)` transforms with pinned asset hash and provenance; it supplies no height or execution authority. |
| Multi-destination and patrol loops | **Verified offline** | `semantic-sequence-deathknell-brill-loop.json` contains two semantic IDs and bounded loop count; supervisor and Control Center tests pass. |
| Exact awareness of every mob/NPC in world coordinates | **Not available through current public client path** | Observer provides target/focus/mouseover identity/state and visible nameplate screen-space. No exact generic NPC position is inferred. ME-111 provides LAB recall/precision scoring without leaking server ground truth into Champion. |
| Static trainer/quest/profession/leveling knowledge | **Contract foundation verified** | `knowledge_broker_catalog` loader, RouteTeacher and bounded NPCData parser tests 8/8; entries bind to exact TBC/map identity and static source candidates require later client confirmation. The real Anniversary NPCData table parses offline to 3,255 entries, with `zone_area` scope kept separate from WorldPack IDs. |
| Profile-aware semantic journey validator | **Verified offline** | v46 profile-bound report is `PASS` for 5/5 expected outcomes; incomplete hill fixture remains `RESET_REQUIRED`/`safe=false`. |
| Zygor Anniversary package audit/import | **Verified offline; direct install denied** | RAR TOC is `Interface:20506`; bounded parsers count 14,748 guide steps, 11,687 coordinate candidates and 3,255 static NPC rows without executing Lua or copying licensed payload. |
| Zygor NPCData map-area discovery | **Verified offline; partial client reconciliation** | Content-minimal discovery found 66 numeric `m####` IDs and 3,255 rows. The explicit LibRover→WorldMapArea compatibility layer now resolves `62/66` (`0` ambiguous); Black Temple and three synthetic instances remain unresolved because the client audit has no matching `WorldMapArea` rows. IDs remain `zone_area` and are not used as live positions or executable movement. |
| Combat after successful movement | **Pending explicit fresh authorization** | Historical combat snapshots are expired; no runtime arm exists. Read-only observation config has `permitted_modes=[]`; no combat input was started. |
| Parallel single-player/Hermes processes untouched | **Verified for this audit** | No commands targeted those processes; WoW LAB PID remained read-only checked and responding. |

## ME-119/120 interior-corpus follow-up

The v3 Razorfen Kraul tile `27_27` was queried with the original generated
course pattern and a bounded second candidate. The first candidate is a real
interior/frontier sample with no walkable polygon at the requested endpoint;
the worker resolves local floor height but correctly rejects the endpoint. The
second candidate yields a complete corridor (`29` polygons, `28` portals) and
`100/100` collision-free arrivals. This confirms that the failure is sparse
endpoint coverage, not a fabricated Z seed or an endpoint teleport.

The geometric production controller scores `44/100` on that complete corridor.
The offline PA-MPPI evaluation improves it to `93/100` with the reviewed
baseline. A risk-specific experimental smoothness setting (`yaw_smoothness_weight`
`8.0`, then `10.0`) reaches `999/1000` on the 1,000-run holdout, with zero
collisions, but each has one quality failure. These artifacts remain evaluation
only; no production constants, live controller, or live input were changed:

- `data/runtime/navigation-f3b/proof-v3-corpus-razorfen-smoke-v3.json`
- `data/runtime/navigation-f3b/proof-v3-corpus-razorfen-smoke-mppi.json`
- `data/runtime/navigation-f3b/proof-v3-corpus-razorfen-smoke-mppi-smooth8-risk-1000.json`
- `data/runtime/navigation-f3b/proof-v3-corpus-razorfen-smoke-mppi-smooth10-risk-1000.json`

ME-121 binds the successful tuning only to the adaptive, geometry-aware risk
path: narrow (`<=3.5 yd`) portals plus client-recorded clearance inset or
steep polygon evidence. It does not alter the direct MPPI baseline. The
selector and runtime wiring are covered by tests; the complete offline suite
after this change is `1260/1260`, and the six-scenario adaptive benchmark is
`600/600`. The Control Center now launches the adaptive profile with `256 x 56`
to match the validated holdout shape. This remains offline evidence; no fresh
live input is implied.

The current registry read-only inventory contains `83` client map identities,
`6` runtime WorldPack profiles, `1` semantic catalog and `2` structure-access
graphs. The Control Center picker exposes all `83` identities; profiles without
the complete artefact set remain visibly `OBSERVE_ONLY` and cannot start an
autonomous route.

## ME-122 — Client terrain versus complete navigation bake

A deterministic read-only bake-queue audit over client build `2.4.3.8606`
found `35` terrain-eligible maps containing `3,610` ADT files. The persisted
record is
`data/runtime/navigation-f3b/client-world-bake-queue-audit-20260831.json`.
The canonical target root
`E:\\WoWserver\\PerfectAssassin-Runtime\\navigation\\tbc243-full-v1`
currently reports `complete_map_count=0`, `bvh_ready=false` and
`bvh_artifact_count=0`. Existing navigation directories are named proof/work
snapshots with partial coverage and are not silently merged or promoted.
This confirms that local terrain source exists, but map-by-map navmesh/BVH plus
semantic/access sealing is still missing for all-map autonomy. The command only
generated the queue; it did not invoke `MoveMapGen`, grant execution authority,
reload WoW, or start live input.

## ME-123 — Azeroth v4 offline bake and sealed candidate

The correct pinned `MapBuilder` v5 was used against the local MPQ directory
`E:\\Games\\WoW TBC 2.4.3\\Data`; the TBC-LAB `MoveMapGen.exe` was not used for
Champion navigation because it produces CMaNGOS `.mmap/.mmtile` oracle output.
Azeroth produced `687/687` road sidecars, `2,178` BVH artifacts and `687/687`
`.nav` tiles. The queue now reports Azeroth `COMPLETE` while the other 34
eligible maps remain unbaked.

Quality evidence reports zero failed tiles and
`COMPLETE_WITH_RECAST_DIAGNOSTICS`; the structural Detour audit passes
`687/687` with `failure_count=0`. Recast diagnostics are retained explicitly
(`7,894` errors and `21,433` warnings) and do not become a silent PASS.
The candidate catalog and WorldPack are separate from Stable: v4 is sealed and
verified at
`E:\\WoWserver\\PerfectAssassin-Runtime\\worldpacks\\tbc243-azeroth-full-v4-candidate`
with `3,558` artifacts, `runtime_ready=true` and content hash
`99feeb1ca0969f0a0cbc1575f5fb4adb37eb2ee464fc53a54d04782f157f6dbf`.
It is not bound in the registry yet. Current catalog coverage is therefore
`1/83` complete maps, not all-map autonomy; no live input or combat was started.

## ME-124 — v4 steering corpus and awareness-worker correction

The first candidate smoke invocation used `MapBuilder.exe` as the persistent
awareness worker. That binary has a different CLI and failed the JSON handshake;
the invocation was corrected to the compiled
`data/runtime/native-build/pa_nav_probe-v35/Debug/pa_nav_probe.exe` with the
contractual ten-second query bound. This was a harness error, not a navmesh or
live-runtime failure.

The corrected geometric corpus over four selected ADTs resolved two complete
corridors and simulated `200/200` quality-pass trials with zero collisions and
zero quality failures; the two remaining requests were retained as
`PARTIAL_CORRIDOR` fail-closed results. The production MPPI profile (`256 x 56`,
replan `3`) resolved two of two selected corridors and passed `200/200` trials,
with zero collisions and zero quality failures. MPPI was active for roughly
`96.7%–97.0%` of observations. Evidence is persisted at
`data/runtime/navigation-f3b/azeroth-v4-steering-smoke-4tiles-20260831.json`
and
`data/runtime/navigation-f3b/azeroth-v4-steering-smoke-mppi-2tiles-20260831.json`.

This remains bounded offline evidence on a small ADT sample; it does not prove
all-map autonomy, Crypt→Brill→Crypt humanlike live behavior, generic 3D entity
awareness, or combat. No live input, WoW reload, Hermes change, or combat was
started.

## ME-203 — Map-identity-bound profile readiness (offline)

The Control Center registry readiness check no longer treats file existence as
capability evidence. `inspect_world_map_profile` now validates record type,
schema, `execution_authority=false`, and the exact `map_id`/`internal_name`
identity in the WorldPack runtime profile, semantic catalog, structure index,
and structure-access graph. A shared runtime profile is accepted only when it
explicitly lists the selected map; stale cross-map files fail closed.

The registry/audit/Movement Engine regression passes `156/156`; the regenerated
registry audit passes `--check` with all `83` inventory identities present,
`4` bake-complete maps, and `1` autonomous-ready profile. This is offline
evidence only; no new live run was started.

## ME-125 — Kalimdor bake and isolated candidate pack

Kalimdor was resumed offline from `READY_FOR_SEMANTICS` with the pinned v5
MapBuilder and the local MPQ data root. The runner produced `1018/1018` road
sidecars and `1018/1018` nav tiles; the queue now reports `COMPLETE` for
Kalimdor and the global BVH count is `3261`. The contractual result is
`data/runtime/navigation-f3b/kalimdor-bake-20260831.json` (`PASS`,
`execution_authority=false`).

The quality report remains explicit
`COMPLETE_WITH_RECAST_DIAGNOSTICS` with no missing/failed tiles, `12,237`
Recast errors and `30,081` warnings. A serial structural audit passes
`1018/1018` with zero failures. A separate WorldPack candidate is sealed and
verify-only checked at
`E:\WoWserver\PerfectAssassin-Runtime\worldpacks\tbc243-kalimdor-v1-candidate`
with `5,303` artifacts, `runtime_ready=true` and content hash
`609a20256ec154c98bd630091753a6229f610488536ec61b7ef0a5ca19c3db5f`.

The candidate is not bound in the registry. Offline bake coverage is now two
of thirty-five terrain-eligible maps, but semantic/access promotion,
all-map autonomy, generic 3D entity awareness, live Crypt→Brill→Crypt quality
and combat remain unverified. No live input, WoW reload, Hermes change, or
combat was started.

## ME-126 — Kalimdor MPPI corpus on real baked geometry

The offline corpus
`data/runtime/navigation-f3b/kalimdor-v1-steering-smoke-mppi-4tiles-20260831.json`
resolved `4/4` selected Kalimdor corridors and passed `400/400` MPPI trials
using the Control Center profile (`256 x 56`, replan `3`), with zero collisions
and zero quality failures. The selected risk set includes steep geometry,
doodad detours, clearance insets, a sharp turn, and a narrow portal. These are
navmesh/BVH-derived observations, not executable operator waypoints.

This remains four-ADT offline evidence; it does not promote the candidate in
the registry or prove all-map autonomy, generic 3D entity awareness,
Crypt→Brill→Crypt humanlike live behavior, or combat. No live input, WoW
reload, Hermes change, or combat was started.

## ME-127/128 — Shadowfang hairpin candidate and adjacent corridor

The controller candidate changes only time-horizon and yaw-actuator
parameters: nominal MPPI preview `1.80 s` and maximum yaw acceleration
`12 rad/s²`. These are bounded controller constants over observed corridor
geometry; no executable waypoint, map-specific coordinate or route shortcut
was added. The new switchback unit test is included in the full regression.

With the Control Center profile (`256 x 56`, replan `3`),
`shadowfang-v3-steering-replay-preview18-accel12-28-30-100-20260831.json`
records `100/100` arrivals, `99/100` quality-pass, zero collisions, zero
pivots, maximum cross-track `2.030789 yd`, p95 `1.930345 yd`, and MPPI active
for `98.21%` of observations. Only `trial_index=86` misses the strict `2.0 yd`
cross-track gate (`2.030789 yd`); this is not promoted as a complete PASS.

The adjacent
`shadowfang-v3-steering-replay-preview18-accel12-28-31-100-20260831.json`
records `100/100` quality-pass, zero collisions, zero pivots, maximum
cross-track `1.986825 yd`, and maximum four steering-sign changes. The full
offline suite after the candidate change is `1262/1262`. No live input, WoW
reload, combat or Hermes process was started.

The one 28_30 outlier was audited without changing the gate. At observation
`182`, the monotonic projection reports progress `124.208726 yd` and
cross-track `2.030789 yd`, while the nearest unconstrained local path point is
approximately `1.9426 yd` away at progress `124.801 yd`. The difference comes
from the `0.40 s` projection-advance cap retained to prevent branch stealing
at self-near hairpins. Alternative windows `0.35`, `0.45`, `0.50` and `0.55 s`
were tested on a 20-seed shard and remained at `16/20`; no production or
evaluator relaxation was justified. The live gate therefore remains pending.

## ME-130 — Outbound-tangent projection correction

The controller now uses the remaining bounded four-yard projection window when
all of the following are true: the corridor has valid local geometry/portal
evidence, the next sharp corner is already within the existing window, the
observed actor is within four yards of that corner, and its heading is within
`0.85 rad` of the outbound tangent. The nearest-segment projection and
monotonic progress rules remain authoritative; no waypoint or route-specific
exception is introduced. Guidance is cached per corridor so the added check
does not duplicate the expensive path cleanup on every frame; corner detection
keeps its existing discretization.

The official `256 x 56`, replan-3 replay now records `100/100` quality-pass on
`Shadowfang:28_30:p0` (maximum cross-track `1.988531 yd`, zero collisions and
zero pivots) and `100/100` on `Shadowfang:28_31:p0` (maximum `1.986825 yd`, zero
collisions and zero pivots). The final 28_30 artefact is
`data/runtime/navigation-f3b/shadowfang-v3-steering-replay-projection-corner-final-28-30-100-20260831.json`.
The six-scenario geometric Monte Carlo report
`data/runtime/navigation-f3b/steering-monte-carlo-20260831-v5-projection-corner-open-ground.json`
passes `600/600`, with no collisions or quality failures.
Full offline regression is `1263/1263`; no live
input, WoW reload, combat or Hermes process was started.

## ME-131 — Generic registry-bound profile gate

Control Center nu mai tratează `map_id=0` ca o condiție de cod pentru
readiness. Orice profil selectat este evaluat după propriile artefacte
WorldPack, semantic catalog, structure index, access graph și semantic gate;
un profil incomplet rămâne `OBSERVE_ONLY`. Testul sintetic non-zero (`map_id=33`)
ajunge la verificarea awareness, iar `tests.test_movement_engine` trece
`139/139`; un test separat confirmă legarea gate-ului de WorldPack-ul profilului
selectat. Suita completă trece acum `1270/1270`.
Această schimbare elimină o limită de hartă fără să promoveze
profiluri care nu au încă dovezi complete.

## ME-133 — WorldMapArea static client coverage

Auditul separat al `WorldMapArea.dbc` (scope `lab_evaluation_only`) confirmă
`68` rânduri și `7` contexte de hartă, cu bounds 2D pinned pentru clientul
TBC `2.4.3.8606`. Artefactul este
`data/runtime/navigation-f3b/client-world-map-area-audit-20260831.json`;
schema/parser și `--check` trec `1/1`. Această dovadă nu este feed live, nu
conține poziții exacte de entități și nu ridică `OBSERVE_ONLY` pentru instanțe
fără transformare/coridor.

## ME-132 — Audit determinist pentru toate identitățile de hartă

Raportul `data/runtime/navigation-f3b/world-map-registry-audit-20260831.json`
este generat și verificat cu schema dedicată. El confirmă `83` identități în
registry/inventar, `35` hărți în bake queue, `3` `COMPLETE` și doar `1`
`autonomous_ready`; starea fiecărei hărți rămâne fail-closed și nu primește
artefacte din alt profil. Testele auditului trec `3/3`, iar `--check` este
verde. Acesta este audit offline, nu acoperire autonomă pentru toate hărțile.

## Non-negotiable boundary

The audit is not a claim that every objective row is complete. The remaining
items are the deliberately fail-closed all-map runtime expansion, the public
client's missing generic 3D entity-position capability, and a fresh bounded
combat authorization/runtime arm. No new live input is implied by this file.

## ME-134 — Control Center nu reutilizează catalogul altei hărți

Destinațiile semantice sunt încărcate din profilul WorldPack selectat și sunt
validate după identitatea declarată a hărții. La schimbarea către un profil
fără catalog valid, UI-ul golește destinațiile și secvența, păstrând startul
autonom în stare fail-closed. Plannerul semantic folosește același binding de
profil pentru WorldPack.

Regresia completă după această schimbare este `1270/1270`. Acest lucru
pregătește promovarea viitoare a unor hărți noi, dar nu pretinde că Shadowfang
sau celelalte profile au deja transformare, catalog și coridor complet pentru
autonomie live.

## ME-145 follow-up — Expansion01 bake evidence

The previously extracted `Expansion01` terrain was advanced offline from
`READY_FOR_SEMANTICS` to `COMPLETE` with the pinned client-only `MapBuilder`.
The result is `800/800` road sidecars and `800/800` nav tiles in
`data/runtime/navigation-f3b/expansion01-bake-20260831.json`.

The separate candidate catalog
`data/runtime/navigation-f3b/client-world-catalog-world-continents-v2-candidate.json`
contains exactly `Azeroth`, `Kalimdor`, and `Expansion01`, all with complete
terrain/road coverage. The Outland structural audit
`data/runtime/navigation-f3b/expansion01-navmesh-geometry-20260831.json`
passes `800/800` tiles and `204,800/204,800` embedded tiles with zero failures.
The quality report is explicitly
`COMPLETE_WITH_RECAST_DIAGNOSTICS` (zero failed/missing tiles; Recast warnings
and errors retained). This candidate is not promoted to the registry because
semantic destinations and structure/access evidence are still incomplete.

The full offline regression after the validator fix is `1285/1285`. A large
parallel Python 3.14 audit still exhibits the interpreter's internal
`Executing a cache` crash, so the complete Outland evidence was produced by
the serial validator; the dedicated parallel Namigator regression passes.
No WoW reload, live input, combat, single-player change, or Hermes change was
performed.

## ME-146 follow-up — Anniversary package and map reconciliation

The supplied `D:/Downloads/Zygor Release 8.1.37070.rar` passed a local 7-Zip
integrity test (RAR5, 18,260,702 bytes, SHA-256
`d8d416ad95f9071fd8578df218a70235c377ea8b350f81ca2ea6f5417a65d2d3`). Its
TOC identifies `ZygorGuidesViewerClassicTBCAnniv`, `Interface: 20506`,
`Version: 8.1`, and the TBC-specific `Guides-TBC`, `Data-TBC`, and `Code-TBC`
trees. The older `Zygor.zip` is a separate 2008-era addon.

Bounded parsing of the non-Trial leveling/profession files reconfirmed the
previous offline counts: 11,205 leveling steps / 10,007 coordinate
candidates / 730 class-trainer references / 2,373 combat steps, plus 3,543
profession steps / 1,680 coordinate candidates / 524 profession trainers /
16 profession quests. Lua was not evaluated and licensed payloads were not
copied into the repository.

The new content-minimal reconciliation artifact
`data/runtime/navigation-f3b/zygor-world-map-reconciliation-20260831.json`
matches the source hashes and reports 22 exact plus 23 normalized matches,
zero ambiguous IDs, and 21 unresolved IDs out of 66. It carries no execution
authority; unresolved IDs remain excluded from semantic/access promotion.
The full offline regression after this addition is `1287/1287`.
No live test, combat, reload, or input was started.

## ME-147 follow-up — Explicit closed-loop destination sequences

`DestinationSequence` now accepts an optional `close_loop` flag. When enabled,
the bounded orchestration expands `A → B → C` to `A → B → C → A`; legacy
sequence files remain valid with the default `false`. The Control Center
exposes the option and persists it in the identifier-only sequence contract.
The targeted supervisor/UI regression is `31/31`; route legs remain
WorldPack-gated and replanned from observed position. No live input was
started.

## ME-148 follow-up — Offline regression and map readiness audit

The post-loop full offline regression passes `1289/1289`; `compileall` and
`git diff --check` also pass. The negative fixture message for `--jobs=5` is
expected. The three content-minimal Zygor `--check` audits pass against the
temporarily extracted Anniversary files without evaluating Lua or copying
licensed payloads.

The current registry/UI audit exposes `83` map identities, with `35` queue
entries and `4` complete bakes, but only `1` profile has all runtime,
semantic, structure-index, and access-graph artefacts required for
`autonomous_ready`. Other profiles remain inspectable but fail-closed. No
live test, combat, reload, or input was started.

## ME-149 follow-up — Content-minimal guide coverage in Control Center

The new `scripts/audit_zygor_guide_coverage.py` processes six selected
non-Trial Anniversary files and persists only file/archive hashes, sizes, and
bounded counts. The artifact
`data/runtime/navigation-f3b/zygor-guide-coverage-20260901.json` reports
14,748 steps, 11,687 coordinate candidates, 730 class trainers, 663
profession trainers, and 855 classified quests. It is explicitly
`SELECTED_NON_TRIAL_FILES` with `execution_authority=false`.

Control Center now renders this as a read-only RouteTeacher coverage line.
Malformed audits and any record claiming execution authority are ignored; the
line does not feed the planner, create waypoints, or alter the WorldPack gate.
The dedicated audit/UI regression is `21/21`. No addon payload was copied into
the repository, Lua was not evaluated, and no live input was started.
The full offline regression after this integration is `1293/1293`; `compileall`,
the audit `--check`, and whitespace checks pass.

## ME-150 follow-up — Validated MPPI profile on retained Shadowfang replay

The retained Shadowfang corridor replay was rerun offline with the explicit
validated profile `batch_size=256`, `time_steps=56`, and
`replan_interval_ticks=3`. It achieved `100/100` quality passes, zero
collisions, maximum cross-track `1.9885`, and `98.2%` MPPI-active observations.
The artifact is
`data/runtime/navigation-f3b/shadowfang-v3-steering-replay-adaptive-20260901-v2.json`.
The previous `128/56/4` defaults produced only `79/100`, so the replay
defaults are now aligned and covered by a dedicated `14/14` steering test.

Malformed replay input is rejected before simulation. This remains offline
evidence only; no WoW reload, live input, or combat was started. The full
offline regression after this correction passes `1295/1295`; `compileall`, the
guide audit `--check`, and whitespace checks pass.

## ME-151 follow-up — Multi-map RouteTeacher coverage

The bounded RouteTeacher audit now requires explicit bindings for all 66 zone
names encountered in the six selected Anniversary files. Its content-minimal
artifact `data/runtime/navigation-f3b/zygor-route-coverage-20260901.json`
reports 4,625 Azeroth steps, 5,148 Kalimdor steps, 4,974 Expansion01 steps,
and one BlackTemple step, with 11,687 coordinate candidates overall. No guide
payload or coordinates are retained in the audit.

Modern guide steps without a `goto` retain the last explicit zone within the
same guide, so map counts are not silently reset to Azeroth. The binding file,
audit, and Control Center indicator remain read-only; dedicated tests pass
`13/13`, and no live input was started. The full offline regression passes
`1300/1300`; audit `--check`, `compileall`, and whitespace checks are green.

## ME-152 follow-up — Bounded Kalimdor structure scan progress

An additional offline batch of 1,000 probes used the plan-pinned `v35`
worker. Progress is now 2,139 of 40,794 seeds, with 57 confirmed WMO
observations, 74 completed structures, and zero worker errors. The updated
progress report is
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v1.json`.

Completed observed structures were aggregated into
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v2.json`
with 57 observations, 254 access openings, and 488 boundary chains. It remains
`PARTIAL_OBSERVED_COMPONENTS` and is not linked to registry autonomy. The first
run with an incompatible worker was rejected before probing; no live input was
started.

## ME-153 follow-up — Continued bounded Kalimdor structure scan

A second offline batch of 1,000 probes resumed from the existing fragments with
the same plan-pinned `v35` worker. Progress is now 3,139 of 40,794 seeds, with
73 confirmed WMO observations, 106 completed structures, and zero worker
errors; 37,655 seeds remain. The strict progress artifact is
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v1.json`.

Completed structures were re-aggregated into
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v3.json`
with 73 observations, 350 openings, and 692 boundary chains. Coverage remains
`PARTIAL_OBSERVED_COMPONENTS`, unlinked from registry autonomy. No WoW reload or
live input was started.

## ME-154 follow-up — First bounded Expansion01 access scan

Expansion01 already has complete local bake evidence (`800/800` nav tiles). A
new immutable structure index records 1,659 WMO and 94,506 doodads; its
deterministic access plan contains 47,170 eligible seeds and zero deferred
structures. The first offline batch of 1,000 probes with the plan-pinned `v35`
worker confirmed 17 WMO observations, completed 35 structures, and produced
zero worker errors; 46,170 seeds remain.

The strict progress and candidate graph artifacts are
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v1.json`
and
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v1.json`.
The graph has 17 observations, 29 openings, and 88 boundary chains; coverage
remains `PARTIAL_OBSERVED_COMPONENTS` and is unlinked from registry autonomy.
No WoW reload or live input was started.

## ME-155 follow-up — Static NPCData coverage in Control Center

The explicit LibRover binding for all 66 `map-area` IDs in
`Data-TBC/NPCData.lua` is complete and unambiguous. The content-minimal audit
`data/runtime/navigation-f3b/zygor-npcdata-audit-20260901.json` records only
source hash/size and counts: 3,255 entries across 66 zones, including 286 class
trainers, 287 profession trainers, and 2,682 static NPC entries. Control Center
renders this as read-only advisory coverage; it does not claim exact live 3D
positions or execution authority.

The binding and audit use `execution_authority=false`; UI tests reject an audit
that attempts to grant authority. Lua was not evaluated, WoW was not reloaded,
and no live input was started.

## ME-156 follow-up — Offline Crypt/Brill holdout comparison

The retained journey-supervisor holdouts `v17` through `v38` were compared
without rerunning WoW. Five records are `ARRIVED`; the remainder are explicit
fail-closed, child-error, navigation-budget, or combat-budget stops. The
latest `v38` is `ARRIVED`, but the mixed historical series is not a
determinism claim. Every record keeps `execution_authority=false`.

The profile-aware semantic road artifact
`data/runtime/navigation-f3b/semantic-road-journey-validation-v41-profile-aware.json`
passes all five offline cases, including Crypt spawn/Deathknell↔Brill and the
Brill south-road holdout. The hill fixture remains a deliberate
`partial_local_navmesh_corridor` reset case. This confirms the static
WorldPack/RouteTeacher base while leaving journey frontier variation as the
next offline investigation; no live input was started.

## ME-157 follow-up — Continued Kalimdor structure scan

The first attempt was rejected before probing because the Kalimdor structure
index is bound to `world-pack-runtime-tbc243-kalimdor-v1-candidate.json`, not
the aggregate `world-continents` profile. With the exact candidate binding, a
bounded batch of 1,000 seeds completed successfully: 4,139 of 40,794 seeds
processed, 121 accepted WMO observations, 140 completed structures, and zero
worker errors; 36,655 seeds remain.

The strict aggregate
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v4.json`
contains 121 observations, 608 openings, and 1,126 boundary chains. Coverage
remains `PARTIAL_OBSERVED_COMPONENTS`, unlinked from registry autonomy, and
execution authority remains false. No WoW reload or live input was started.

## ME-158 follow-up — Strict Tirisfal semantic-anchor filtering

The Azeroth catalog now adds only `landmark:deathknell-south-gate`, derived
from the reviewed route and confirmed by a local 3D corridor query with a
complete result and no unresolved blocker. Other candidate descent/midpoint/
approach anchors were tested offline and removed when the client query
reported a partial frontier, height error, or timeout. This keeps the picker
from presenting road-semantic points as executable destinations without local
geometry proof; no live input was started.

## ME-159 follow-up — First bounded Expansion01 scan after WMO indexing

Using the exact WorldPack profile bound to the Expansion01 index, another
bounded batch processed 1,000 seeds. Progress is now 2,000 of 47,170 seeds,
with 37 accepted WMO observations, 70 completed structures, and zero worker
errors; 45,170 seeds remain. The strict aggregate
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v2.json`
contains 37 observations, 98 openings, and 254 boundary chains.

Coverage remains `PARTIAL_OBSERVED_COMPONENTS`, unlinked from registry
autonomy, with execution authority false. No WoW reload or live input was
started.

## ME-189 follow-up — Bounded live loop and temporal-gap remediation

The fresh bounded LAB holdout
`data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-live.json`
reported `ARRIVED` for Brill and the return Crypt leg, with zero combat
handoffs and `execution_authority=false`. The client was visually confirmed in
world at Crypt after disarm; this is movement evidence only, not a combat or
survivability claim.

The strict trace evaluator passed the return leg, while outbound remains false
because two measured gaps are unexplained: `2.1296 s` at the static frontier and
`1.2960 s` at corridor recenter. The gate was not loosened. Offline remediation
now preplans both the bounded route-cell bypass and early geometric recenter in
isolated workers, applying results only with valid query/goal/start evidence.
Semantic validator v47 passes all five expected outcomes (`4x ARRIVE`, hill
fixture `RESET_REQUIRED`). Focused tests (`145/145`), runtime/supervisor tests
(`98/98`) and the full offline suite (`1325/1325`) pass. A second live run remains intentionally
deferred until the outbound temporal gate is revalidated offline.

## ME-190 follow-up — Live v2 and frontier-worker priority

The second bounded holdout
`data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-live-v2.json`
again reached Brill and Crypt with zero combat handoffs and
`execution_authority=false`; the session was disarmed after completion.
Return quality passed with 6,699 frames and no unexplained gaps. Outbound
improved to one unexplained `2.10225 s` frontier gap; the `1.3329 s` recenter
interval has measured continuous movement and is therefore explicitly
exempted by the existing gate.

The subsequent offline change gives the frontier bypass worker priority over
the next-goal preplan while the active corridor is partial. The full regression
after this change is `1326/1326` (focused movement/runtime checks `244/244`).
This last priority change has not been live-verified; humanlike movement is
still not certified.

## ME-187 follow-up — Static candidate query and current offline gate

The shared Zygor–WorldMapArea compatibility layer now reconciles `62/66`
static NPCData map-area identities (`0` ambiguous; four unresolved client
areas). `KnowledgeBrokerCatalog.nearby_static_candidates(...)` provides a
deterministic, exact-map/scope query for normalized 2D source candidates and
keeps `execution_authority=false`; it does not claim live NPC coordinates or
create movement destinations. The dedicated regression and the full offline
suite pass (`1323/1323`).

The current semantic artifact
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v46.json`
is `PASS` for 5/5 expected outcomes, with the hill frontier intentionally
`RESET_REQUIRED`/`partial_local_navmesh_corridor`. The operator gate remains
`live_authority_enabled=false`; no LAB authorization/runtime arm, WoW reload,
or live input was created.

## ME-191 follow-up — Dedicated frontier worker

The bounded atlas-forward frontier query now runs in its own one-worker
`ProcessPoolExecutor`, isolated from WMO baseline and ordinary semantic
preplans. The worker has no actuator access, and teardown explicitly closes the
pool. Compileall plus focused Movement Engine/runtime/supervisor tests pass
`245/245`; no live test was started after this offline amendment.

## ME-192 follow-up — Bounded concurrent frontier probes

The dedicated frontier worker now fans out at most four native read-only probes
for its bounded candidate horizon. Selection remains deterministic in semantic
route order, so faster completion cannot select a later candidate as a shortcut.
The Movement Engine tests pass `147/147`; no live test was started after this
offline change.

## ME-193 follow-up — Continued bounded continental scans

The latest read-only Kalimdor batch processed 1,000 additional seeds, reaching
`9,139/40,794` with 211 accepted WMO observations, 314 completed structures,
and zero worker errors. The strict aggregate
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v9.json`
contains 967 openings and 1,842 boundary chains.

Expansion01 processed its corresponding 1,000-seed batch, reaching
`7,000/47,170` with 149 accepted observations, 249 completed structures, and
zero worker errors. Its strict aggregate
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v7.json`
contains 429 openings and 1,070 boundary chains. Both graphs remain
`PARTIAL_OBSERVED_COMPONENTS`, unlinked from registry autonomy; no live input
was started.

## ME-188 follow-up — Cross-pack frontier diagnosis

The hill frontier was re-queried offline with worker v34/v35 and the v3,
v4-candidate, and repair-source packs. All variants stop at the same client
navmesh point with identical steep/doodad metrics; the repaired `29_28` tile is
already loaded but does not connect the hill component to the road. This is
stronger evidence for a real local topology boundary, not a worker-version
fluke. The case remains fail-closed and no shortcut/teleport/waypoint or live
input was introduced.

## ME-166 follow-up — Continued bounded Kalimdor scan

An additional offline batch of 1,000 probes resumed from the existing
checkpoint with the plan-pinned v35 worker. Progress is now 7,139 of 40,794
seeds, with 188 accepted seeds, 246 completed structures, 33,655 seeds
remaining, and zero worker errors. The strict completed-task aggregate
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v7.json`
contains 186 accepted observations, 837 access openings, and 1,682 boundary
chains. Coverage remains `PARTIAL_OBSERVED_COMPONENTS`, unlinked from registry
autonomy, with `execution_authority=false`; no WoW reload or live input was
started.

## ME-167 follow-up — Continued bounded Expansion01 scan

An additional offline batch of 1,000 probes resumed from the existing
checkpoint with the World Continents profile and plan-pinned v35 worker.
Progress is now 5,000 of 47,170 seeds, with 123 accepted seeds, 177 completed
structures, 42,170 seeds remaining, and zero worker errors. The strict
completed-task aggregate
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v5.json`
contains 123 accepted observations, 303 access openings, and 848 boundary
chains. Coverage remains `PARTIAL_OBSERVED_COMPONENTS`, unlinked from registry
autonomy, with `execution_authority=false`; no WoW reload or live input was
started.

## ME-164 follow-up — RouteTeacher 2D transform coverage

Auditul content-minimal
`data/runtime/navigation-f3b/zygor-route-transform-coverage-20260901.json`
transformă `11,686/11,687` coordonate Zygor prin catalogul client: Azeroth
`3,434/3,434`, Kalimdor `3,918/3,918`, Expansion01 `4,334/4,334`. Singurul
candidat nerezolvat este Black Temple (`map_id=564`), fără rând WorldMapArea în
assetul auditat. Artefactul păstrează numai hash-uri/count-uri, nu creează
waypoints, iar starea rămâne `PARTIAL_CLIENT_2D_TRANSFORM` cu
`execution_authority=false`. Testele dedicate auditului sunt `2/2`, testele UI
`2/2`; full regression după integrare este `1313/1313`. Nicio operațiune live nu
a fost pornită.

## ME-165 follow-up — Continued bounded continental scans

The latest offline Kalimdor batch processed 1,000 additional probes, bringing
progress to `6,139/40,794` seeds, with 177 accepted WMO observations, 209
completed structures and zero worker errors. Strict `partial-v6` contains 812
openings and 1,622 boundary chains. Expansion01 processed the corresponding
1,000-probe batch on the corrected path, reaching `4,000/47,170` seeds, with
114 accepted observations, 141 completed structures and zero worker errors;
strict `partial-v4` contains 226 openings and 776 boundary chains. Both graphs
remain `PARTIAL_OBSERVED_COMPONENTS`, unlinked from registry autonomy and with
`execution_authority=false`; no live input was started.

## ME-163 follow-up — Client-derived all-map-area transform catalog

The audited WorldMapArea rows are now available through the read-only
`config/pose/world-map-zone-transforms-tbc243-8606.json` catalog: 68 unique
`(map_id, area_id)` transforms with asset hash, record fingerprint, source and
retrieval time. The adapter rejects duplicate/degenerate bounds and any
execution authority. Control Center renders the count without using it as a
route or live height oracle. Targeted tests pass 29/29 and the full offline
regression passes 1309/1309; no WoW reload or live input was started.

## ME-162 follow-up — Offline v38 trace-quality recheck

The official evaluator was rerun on both existing v38 navigation result files,
without starting WoW. Both traces report `arrived=true`, `passed=true`, and
zero unexplained observation gaps over 300 ms. The outbound trace contains four
raw gaps and the return trace one; each is explicitly recorded as a measured
motion-continuity exemption with compatible forward input. No threshold was
loosened and no new live run was started.

## ME-160 follow-up — Bounded Kalimdor scan after partial-v4

The next offline batch of 1,000 probes used the exact Kalimdor candidate
profile/index pair and the pinned v35 worker. Progress is now 5,139 of 40,794
seeds, with 146 accepted WMO observations, 175 completed structures, and zero
worker errors; 35,655 seeds remain. The strict artifacts are
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v1.json`
and
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v5.json`,
which contains 146 observations, 753 openings, and 1,439 boundary chains.

Coverage remains `PARTIAL_OBSERVED_COMPONENTS`, unlinked from registry
autonomy, with execution authority false. No WoW reload or live input was
started.

## ME-161 follow-up — Continued bounded Expansion01 scan

With the aggregate WorldPack profile correctly paired to the Expansion01
index, a further offline batch of 1,000 probes reached 3,000 of 47,170 seeds:
83 accepted WMO observations, 105 completed structures, and zero worker
errors; 44,170 seeds remain. The strict aggregate is
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v3.json`
with 83 observations, 186 openings, and 586 boundary chains; progress is
recorded in
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v1.json`.

Coverage remains `PARTIAL_OBSERVED_COMPONENTS`, unlinked from registry
autonomy, with execution authority false. No WoW reload or live input was
started.

## ME-194 — Live holdout after dedicated frontier pool and bounded fan-out

The local archive `D:\Downloads\Zygor Release 8.1.37070.rar` was audited
read-only (SHA-256 `D8D416AD95F9071FD8578DF218A70235C377EA8B350F81CA2EA6F5417A65D2D3`,
root `ZygorGuidesViewerClassicTBCAnniv`, Interface `20506`, Version `8.1`,
868 files and 83 directories); it was not extracted or copied into the repo.

The `live-v3` preflight stopped fail-closed at `CHARACTER_SELECT` before any
movement input. After a controlled `EnterWorld` checkpoint, the one effective
bounded `Crypt -> Brill -> Crypt` holdout reached both destinations in
`data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-live-v4.json`,
with zero combat handoffs and `execution_authority=false`; the session was
disarmed immediately.

Strict trace quality still fails the temporal gate. Outbound has 6 raw gaps,
3 motion-continuity exemptions and 3 unexplained gaps (maximum `2.554495 s`);
return has 2 raw gaps, 1 exemption and 1 unexplained gap (maximum `0.366721 s`).
Both legs are `ARRIVED`, but `passed=false` due to `control_observation_gap`.
The dedicated pool and bounded fan-out therefore remain unproven as a fix for
the frontier pause; no second live run is started. Next work is offline gap
analysis around `SEMANTIC_FRONTIER_REPLAN_REQUIRED`.

## ME-195 — Frontier worker bound aligned with inclusive candidate window

Offline analysis of the v4 trace confirmed that the frontier helper emitted 9
candidates at `1883.035767, 1583.333374`: the eight-cell extension is inclusive
of the next coalesced semantic goal. The worker rejected every batch above 8,
so its future failed and the caller issued a synchronous query in the control
loop.

The worker now accepts a bounded batch of at most 32 candidates while retaining
the ten-query native fan-out and deterministic route-order selection. Batches
above 32 remain explicitly rejected; no coordinates, teleport or execution
authority were added. Movement Engine tests pass `149/149`; the full offline
regression was `1328/1328` before this correction and is now `1329/1329` before
any live gate. No new live run is started in this cycle.

## ME-196 — Frontier fan-out calibrated offline on the real batch

The real local worker validated the same Crypt→Brill frontier with 10 semantic
candidates reconstructed from the route and returned a complete corridor at
`route_index=18`. The batch took about `3.3 s` with fan-out 4 and about `1.5 s`
with fan-out 10 on the pinned client WorldPack. No WoW input or process access
was used. Movement Engine tests remain `150/150` and full regression remains
`1330/1330`; this benchmark is offline evidence only, not a new live gate.

## ME-197 — Live holdout v5 after the inclusive-window correction

After a fresh LAB authorization, controlled `EnterWorld`, and an inspected
`InWorld` checkpoint, one bounded live `Crypt -> Brill -> Crypt` sequence
reached both destinations in
`data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-live-v5.json`.
The navmesh runs are `bdb4916c-b97d-4779-a91d-8cbcc3a2b62f` and
`4f0eb7b0-e029-488d-a3ba-c2de7e67997f`; both are `ARRIVED` with `5987` and
`6110` frames, zero combat handoffs, and `execution_authority=false`.

The strict temporal gate still fails: outbound has 15 raw gaps, 13 motion
continuity exemptions, and 2 unexplained gaps (maximum `2.104445 s`); return
has 12 raw gaps, 11 exemptions, and 1 unexplained gap (maximum `0.384832 s`).
Both quality artifacts report `passed=false` only for
`control_observation_gap`. ShadowPlay was toggled only for this holdout and
the LAB runtime was disarmed immediately after the final checkpoint. This is
functional route progress, not humanlike-motion certification; offline gap
analysis remains the next step and no second live holdout is started.

## ME-198 — Preserve the frontier future across partial replans (offline)

The v5 trace showed that the bypass future started at frontier
`1883.035767, 1583.333374` was cancelled at the start of the repeated partial
replan branch, before the handoff block could inspect and reuse it. This forced
the synchronous `SEMANTIC_STATIC_FRONTIER_BYPASS` path despite the calibrated
worker.

The runner now preserves a future from the same frontier until the handoff
validation; stale or incomplete futures remain fail-closed and synchronous
fallback is retained only as the last valid option. The focused regression is
`151/151`, the full offline suite is `1331/1331`, and `py_compile` plus
`git diff --check` pass. This amendment has not been run live.

## ME-199 — Invalidate the future when a replan changes frontier (offline)

If a partial replan moves the corridor stop to a different frontier, the
future prepared for the old context is now explicitly cancelled. A future is
retained only for the same frontier/query and bounded handoff proximity, so a
topologically unrelated corridor cannot consume stale work. Movement Engine
and full regression remain `151/151` and `1331/1331`; no second live run was
started.

## ME-200 — Offline hairpin benchmark after frontier corrections

`data/runtime/movement-lab/adaptive-steering-benchmark-20260901-me199-1000.json`
completed 1,000 runs for each of six curve scenarios, including
`narrow_outdoor_hairpin`: 6,000/6,000 quality passes, zero collisions, and zero
incomplete runs. The hairpin recorded 0.484 MPPI-active fraction, maximum
cross-track 1.448 yards, and maximum pivot fraction 0.278. This is offline
steering evidence and does not replace the live temporal gate.

## ME-201 — Read-only confirmation of the supplied TBC Anniversary archive

The local `D:\Downloads\Zygor Release 8.1.37070.rar` was re-audited in a
temporary directory only. It reproduces the `ZygorGuidesViewerClassicTBCAnniv`
root, TOC Interface `20506`, Version `8.1`, `868` files and `83` directories,
with SHA-256
`D8D416AD95F9071FD8578DF218A70235C377EA8B350F81CA2EA6F5417A65D2D3`.
Nothing was installed or copied into the repository.

The six selected non-Trial leveling/profession files validate to `14,748`
steps and `11,687` coordinate candidates. `Data-TBC/NPCData.lua` validates to
35 sections and 3,255 rows, including 286 class trainers and 287 profession
trainers. The client 2D transform catalog covers `11,686/11,687` coordinates;
the only unresolved case remains map ID `564` (`BlackTemple`) with no matching
catalog row.

All three existing content-minimal artifacts pass `--check` against this
archive. They remain local advisory data with `execution_authority=false`; no
new live test was started.

## ME-202 — Offline regression for stale frontier-future invalidation

The Movement Engine regression now explicitly checks the changed-frontier
branch: a future prepared from the old topology is cancelled and cannot be
consumed by a later handoff or fallback. Movement Engine tests pass `152/152`
and the full suite passes `1332/1332`; `py_compile` and `git diff --check`
remain green. The v5 live trace is unchanged and no additional live test was
started.

## ME-204 — Advisory Expansion01 structure scan (offline)

The verified scan report is
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v2.json`:
8,000/47,170 seeds completed, 160 accepted observations, 7,040 expected-WMO
rejections, 647 no-nav-polygon results, 153 incomplete static-awareness results,
zero probe errors, and 39,170 seeds remaining. The v35 local probe worker was
hash-verified against the scan plan; the 500-probe batch was bounded and
offline.

The completed-tasks-only aggregate
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v8.json`
contains 92 distinct observed structures, 160 observations, 1,267 boundary
chains, and 501 access openings. Coverage remains
`PARTIAL_OBSERVED_COMPONENTS`, dynamic entity knowledge is `NONE`, and
`execution_authority=false`. This advisory graph is not promoted to registry
readiness and no live test was started.

## ME-205 — Lower priority for read-only native workers (offline)

`ClientAssetNavmeshQuery` and the persistent navmesh-awareness service now
launch their native worker with `CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS`
on Windows, detected without adding a platform dependency. The worker remains
isolated, bounded, read-only and without actuator access; the change only keeps
cold tile loads below the DXGI capture/control clock. Hosts without the flag
fall back deterministically to zero creation flags.

Focused runtime tests pass `239/239`, the full suite passes `1,336/1,336`, and
offline semantic validation v49 passes the four expected arrival cases while
retaining the hill fixture as `RESET_REQUIRED`. The temporal evaluator was not
relaxed, and no live test was started.

## ME-206 — Live preflight remains fail-closed

The semantic gate for v49 is `PASS` but explicitly has
`live_authority_enabled=false`. A read-only preflight found the LAB WoW client
PID `53092` and the expected loopback listeners, while the session
authorization/identity receipt were expired and `runtime_arm_present=false`.
No authorization was regenerated, no runtime arm was issued, and no input was
sent; an open client is not treated as an authorized live session.

## ME-207 — Controlled renewal, visual disconnect, and disarm

For the explicit bounded-live request, the fixed-UI LAB authorization,
identity receipt, and runtime arm were renewed for the existing WoW PID `53092`.
Before movement, the read-only pose probe failed closed with
`ClientVisibleStateError: DISCONNECTED_DIALOG` at confidence `0.532`; the
client was not proven to be in-world at Crypt. No movement pulse, combat
handoff, or route execution was sent. The runtime arm was immediately removed
and the final status reports `runtime_arm_present=false`. The WoW and Hermes
processes were left running and untouched, and the bounded
`Crypt->Brill->Crypt` holdout remains unexecuted.

## ME-208 — Frontier bypass first-candidate fast path (offline)

The v5 trace showed that the first valid semantic road candidate was launched
with speculative siblings, then the executor context waited for the remaining
read-only probes before returning. The worker now probes that first ordered
candidate alone and returns immediately on success; only a first-candidate
failure enters the bounded fan-out, still selecting by route order and waiting
for explicit teardown.

Focused tests pass `245/245`, the full suite passes `1337/1337`, and semantic
offline validation v50 passes the four arrival cases while retaining the hill
fixture as `RESET_REQUIRED`. The temporal quality gate was not relaxed. This
fix has not yet been revalidated live; the previous live holdout remains the
only route evidence.

## ME-209 — Bounded worker-pool warmup (offline)

The v6b trace still contained two unexplained outbound gaps around the first
semantic preplan/frontier transition. `ProcessPoolExecutor` workers were
created lazily by the first submitted job while the capture/control loop held
its lease. The runner now submits and awaits a picklable no-op for all five
read-only workers (two primary preplan, two advisory, one frontier) before
`pose_source.open()`. Warmup is bounded and fail-closed; it has no client or
actuator access.

Focused tests pass `247/247`, the full suite passes `1339/1339`, compileall is
clean, and semantic offline validation v51 passes the four arrival cases while
retaining the hill fixture as `RESET_REQUIRED`. No live input was started after
this change.

## ME-210 — Bounded live v6b arrival with temporal-quality failure

One bounded identifier-only `Crypt -> Brill -> Crypt` session completed both
semantic legs in
`data/runtime/navigation-f3b/journey-combat-supervisor-live-priority-v6b-20260901.json`.
Both child runs reported `ARRIVED`, combat handoffs were zero, and
`execution_authority=false`; the runtime arm was removed immediately.

The outbound trace has 6,591 frames and five raw gaps: three are exempted by
measured motion continuity, but two remain unexplained (maximum gap
`1.551341 s`), so its strict quality result is false for
`control_observation_gap`. The return has 6,285 frames and one
motion-continuity-exempted `0.300153 s` interval and passes. Arrival is
functional evidence only; humanlike movement is not certified and combat stays
behind the gate. The optional structure graph was omitted because its bound
worker hash was v34 while the runtime worker is v35.

## ME-211 — Bounded live v7: outbound arrival, return fail-closed at Brill

The only bounded live revalidation in this cycle ran the identifier-only
`Crypt -> Brill -> Crypt` sequence without combat and without the optional
structure graph. Outbound reached Brill (`ARRIVED`) with zero combat handoffs.
At the return handoff, the first fresh poses did not expose a visible facing;
the controller therefore entered `CALIBRATE_HEADING`, emitted its legacy
natural-forward stride, and departed in the wrong direction. The corridor
recenter budget was exhausted and the supervisor stopped fail-closed with
`CORRIDOR_RECENTER_REPLAN_BUDGET_EXHAUSTED`. Outbound quality remained false
for one unexplained gap (maximum `1.266432 s`); return quality failed because
the destination was not reached, pivot was excessive, and an observation gap
remained. The runtime arm was removed immediately.

## ME-212 — Initial visible-heading reacquisition (offline)

The runner now requires a bounded sequence of fresh, read-only observations
before the first input and after route planning. It accepts only exact HUD
facing or the provenance-tagged minimap fallback; persistent unavailability
fails closed with `refusing natural calibration stride` instead of sending a
calibration `MOVE_FORWARD`. Focused tests pass `249/249`, the full suite passes
`1341/1341`, compileall and diff checks are clean, and no live input was sent
after this change.

## ME-213 — Frontier result materialization moved ahead of handoff (offline)

The v7 outbound trace localized its remaining unexplained gap to a completed
frontier worker result being consumed in the same iteration as the semantic
handoff. The runner now materializes a ready result once during the preplan
phase, while the current corridor is still authoritative; the later handoff
reuses that Future without changing candidate order, geometry provenance, or
execution authority. Worker failure remains fail-closed.

Focused tests pass `250/250`, the full suite passes `1342/1342`, and semantic
offline validation v52 passes the four arrival cases while retaining the hill
fixture as `RESET_REQUIRED`. No live input was sent after this change.

## ME-214 — Anniversary package and Control Center capability re-audit

The local `D:\Downloads\Zygor Release 8.1.37070.rar` archive is confirmed as
the TBC Classic Anniversary package (`ZygorGuidesViewerClassicTBCAnniv`, TOC
`Interface: 20506`, version `8.1`, SHA-256
`D8D416AD95F9071FD8578DF218A70235C377EA8B350F81CA2EA6F5417A65D2D3`).
Read-only `--check` reruns reproduce the existing content-minimal counts:
14,748 guide steps, 11,687 coordinate candidates, and 11,686/11,687 client
2D transforms, with map 564 (BlackTemple) unresolved.

The Control Center/supervisor path is confirmed to support identifier-only
bounded sequences (2–16 IDs, 1–32 repetitions) and an explicit closed-loop
return. Each leg is replanned from fresh observed position. The registry exposes
83 client map identities, but only Azeroth currently has a complete semantic,
WorldPack, structure-index and access-graph binding; all other profiles remain
`OBSERVE_ONLY`. NPCData remains static read-only knowledge (3,255 rows), while
dynamic awareness remains client-visible screen-space evidence and does not
claim exact 3D positions. No addon install, WoW reload or live input occurred;
the runtime remains `OBSERVE_ONLY`.

## ME-215 — Offline worker/graph identity closure

The semantic road validator was rerun against Azeroth WorldPack v3 with
`pa_nav_probe-v34`, matching the worker hash bound by the existing structure
access graph. The fresh artifact
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v53-worker-v34.json`
is `PASS`: four Crypt/Deathknell/Brill arrival cases pass and the hill fixture
retains the expected `RESET_REQUIRED` / `partial_local_navmesh_corridor`
verdict. The offline semantic gate remains explicitly inert
(`live_authority_enabled=false`, `execution_authority=false`).

The read-only structure-awareness service also reached `READY` with 96,024
structures (1,509 WMO, 94,515 doodad) and 4,754 access openings. Full
regression is 1,342/1,342; compileall and diff checks are clean. This closes
the offline worker/graph mismatch only. No LAB authorization was renewed, no
runtime arm exists, and no WoW/Hermes reload or live input was performed.

## ME-216 — Continued continental candidate scans

Two bounded, read-only batches of 1,000 probes each extended the candidate
coverage without touching execution. Kalimdor now has 10,639/40,794 completed
seeds with 229 accepted observations; Expansion01 has 9,000/47,170 with 176
accepted observations. Both batches completed with zero worker errors.

The strict `completed-tasks-only` aggregates are
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v11.json`
and
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v9.json`.
They remain `PARTIAL_OBSERVED_COMPONENTS` candidate graphs and are not attached
to any semantic catalog or live gate. The map registry references them only as
read-only evidence for structure awareness; they cannot make a profile
`autonomous_ready`. No WoW/Hermes reload, runtime arm, or live input was
performed.

## ME-217 — Registry-bound continental structure awareness

The map registry now references the Kalimdor and Expansion01 candidate
structure indexes and partial access graphs as read-only evidence. This lets
the Control Center load nearby WMO/BVH awareness for those maps while the
semantic catalogs remain absent. The readiness audit still reports only 1/83
maps as `autonomous_ready`; both continental profiles remain `OBSERVE_ONLY`
and fail closed for autonomous routing. Registry/UI/scan regression is 46/46,
and ADR-0074 records the rollback. No live input or runtime arm was used.

## ME-218 — Hash-bound worker selection for read-only awareness

The Control Center now selects the structure-awareness worker from a fixed
local v34/v35 allowlist whose binary hash must equal the graph's recorded
`probe_worker_sha256`. Unknown or forged graph hashes fail closed and cannot
inject an arbitrary executable path. The full regression after this change is
1,343/1,343 and compileall is clean. This affects read-only awareness only;
the semantic gate remains inert and no runtime arm or live input was used.

## ME-219 — Kalimdor candidate scan v12 (offline)

A second bounded read-only Kalimdor batch used the dedicated WorldPack profile
and allowlisted v35 worker (`1,000` probes, four jobs, persistent awareness).
The current progress artifact
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v3.json`
records 11,639/40,794 completed seeds, 250 accepted observations, zero worker
errors, 401 complete structures, and 29,155 remaining seeds.

The completed-tasks-only aggregate
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v12.json`
contains 250 observations, 1,204 access openings, and 2,269 boundary chains;
its state remains `PARTIAL_OBSERVED_COMPONENTS` and its content hash is
`4a2918ad8555687d599d7894fab1998c3a2c52e00df79df89f095137c8569029`.
The map registry points to v12 for read-only structure awareness only. No
semantic catalog exists for Kalimdor, so the audit remains at 1/83
`autonomous_ready` maps; runtime arm and live input remain absent.

## ME-220 — Expansion01 candidate scan v10 (offline)

A bounded read-only Expansion01 batch used the shared WorldPack profile and
allowlisted v35 worker (`1,000` probes, four jobs, persistent awareness). The
current progress artifact
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v4.json`
records 10,000/47,170 completed seeds, 196 accepted observations, zero worker
errors, 352 complete structures, and 37,170 remaining seeds.

The completed-tasks-only aggregate
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v10.json`
contains 196 observations, 728 access openings, and 1,764 boundary chains;
its state remains `PARTIAL_OBSERVED_COMPONENTS` and its content hash is
`9de91e04296bfee8f293d0aa8872e2aa500a8bc7034174a541c823f17d8f9b44`.
The registry references v10 for read-only structure awareness only. Expansion01
still has no semantic catalog, so it remains `OBSERVE_ONLY` and cannot open
autonomous movement or input authority.

## ME-221 — Kalimdor candidate scan v13 (offline)

A further bounded read-only Kalimdor batch used the candidate WorldPack profile
and allowlisted v35 worker (`1,000` probes, four jobs, persistent awareness).
The current progress artifact
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v4.json`
records 12,639/40,794 completed seeds, 290 accepted observations, zero worker
errors, 437 complete structures, and 28,155 remaining seeds.

The completed-tasks-only aggregate
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v13.json`
contains 290 observations, 1,285 access openings, and 2,466 boundary chains;
its state remains `PARTIAL_OBSERVED_COMPONENTS` and its content hash is
`cdd9f14a4e5706bd74c92d1baf1ffb9b04da306ac4c385067dbaa85e5b8ced91`.
The registry references v13 for read-only structure awareness only. Kalimdor
still has no semantic catalog, so it remains `OBSERVE_ONLY` and cannot open
autonomous movement or input authority.

## ME-222 — Expansion01 candidate scan v11 (offline)

A further bounded read-only Expansion01 batch used the shared WorldPack profile
and allowlisted v35 worker (`1,000` probes, four jobs, persistent awareness).
The current progress artifact
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v4.json`
records 11,000/47,170 completed seeds, 217
accepted observations, zero worker errors, 298 incomplete-awareness results,
and 36,170 remaining seeds.

The completed-tasks-only aggregate
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v11.json`
contains 217 observations, 843 access openings, and 1,958 boundary chains;
its state remains `PARTIAL_OBSERVED_COMPONENTS` and its content hash is
`b32eb73314950bf597a1018140d5adb3af7bc22e94a7fcd654719f46f99973dd`.
The registry references v11 for read-only structure awareness only. Expansion01
still has no semantic catalog and remains `OBSERVE_ONLY`.

The local TBC Anniversary RAR was retested read-only: SHA-256
`D8D416AD95F9071FD8578DF218A70235C377EA8B350F81CA2EA6F5417A65D2D3`, RAR5,
868 files, 83 directories, `Everything is Ok`. No addon installation or live
WoW input was performed.

## ME-223 — Structural indexes and semantic validation v54 (offline)

Proof WorldPack v3 now has identity-bound structural indexes for
`RazorfenKraulInstance` (395 structures across 6 tiles) and `Karazahn` (5,449
structures across 9 tiles). The registry references these artifacts for static
awareness only; neither map has a semantic catalog or access graph, so both stay
`OBSERVE_ONLY`.

The pinned Azeroth semantic journey validator v54 passed Crypt→Brill,
Deathknell→Brill, Brill→Deathknell, and Brill→South Road Bend. The hill fixture
remained `RESET_REQUIRED` as designed. No live authorization or input was used.

## ME-224 — Full regression after multi-map indexes (offline)

The complete offline suite passed `1343/1343` in `119.63s`; `compileall` and
`git diff --check` are clean. The new Razorfen/Karazhan indexes and registry
links did not alter the semantic gate or input authority. No live test was run.

## ME-225 — Interior access scan for Karazhan and Razorfen frontier (offline)

Karazhan completed all 1,662/1,662 derived seeds with 65 accepted observations,
zero worker errors, and 124 no-nav-polygon results. Its v2 partial graph has
116 access openings and 315 boundary chains and is bound only to read-only
awareness.

Razorfen completed 147/147 seeds with zero errors but no confirmed WMO (18 seeds
had no nav polygon), so no access graph was created. Both maps lack semantic
catalogs and remain `OBSERVE_ONLY`; no live input was used.

## ME-226 — Full regression after Karazhan graph v2 (offline)

The complete offline suite passed again at 1343/1343 in 118.94s; `compileall`
and `git diff --check` are clean. Binding the Karazhan graph did not open
autonomy or input authority, and no live test was run.

## ME-227 — Continued Kalimdor/Expansion01 candidate structure evidence (offline)

One additional bounded batch of 1,000 probes per continent used the allowlisted
v35 worker. Kalimdor is now at 13,639/40,794 completed seeds with 313 accepted
observations and zero worker errors; Expansion01 is at 12,000/47,170 with 247
accepted observations and zero worker errors.

The strict completed-tasks-only aggregates are
`data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v14.json`
(1,373 openings, 2,632 boundary chains) and
`data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v12.json`
(994 openings, 2,289 boundary chains). Both remain
`PARTIAL_OBSERVED_COMPONENTS` read-only evidence. The registry points to the
new versions without adding semantic catalogs; the audit remains 1/83
`autonomous_ready`. No authorization renewal, runtime arm, WoW input or
Hermes modification occurred.

## ME-228 — Semantic gate v55 after multi-map evidence extension (offline)

The pinned Azeroth semantic validator using worker v34 completed with `PASS`:
Crypt→Brill, Deathknell→Brill, Brill→Deathknell, and Brill→South Road Bend all
reached `ARRIVE`. The hill fixture remains `RESET_REQUIRED` with
`partial_local_navmesh_corridor`, preserving the fail-closed frontier verdict.
The artifact is
`data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v55-worker-v34.json`.
The live gate and input authority were not changed; no runtime arm or live
input was used.
