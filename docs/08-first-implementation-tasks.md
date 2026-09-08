# 08 — Primele taskuri de implementare

## Sprint 0A — Foundation (în ordine)

1. `PA-001` — alege runtime-ul și inițializează package/build/test tooling.
2. `PA-002` — implementează validatorul pentru `contracts/core.schema.json`.
3. `PA-003` — definește capability profile pentru `tbc_243_lab` și un profil Anniversary `unknown/restricted` până la verificare.
4. `PA-004` — creează semantic registry pentru primele state/action IDs de Rogue nivel 1.
5. `PA-005` — implementează information firewall și test cu server-only fact respins.
6. `PA-006` — creează fixtures: login, target acquired, combat start, cast, damage, kill, loot, death, level-up.
7. `PA-007` — scrie append-only telemetry writer cu session/event IDs.
8. `PA-008` — scrie replay reader determinist și test round-trip.
9. `PA-009` — implementează separarea memory namespaces și interdicția LAB -> identity.
10. `PA-010` — generează un raport M0 cu statusurile de evidență.

## Sprint 0B — Observer slice

11. `PA-011` — adapter interface + fixture adapter.
12. `PA-012` — normalizer către ObservationEnvelope.
13. `PA-013` — decision stub read-only care produce candidates/reason, fără execution.
14. `PA-014` — encounter assembler.
15. `PA-015` — Journal CLI/debug view pentru un replay fixture.
16. `PA-016` — capability parity report 2.4.3 vs Anniversary, bazat pe verificare, nu presupuneri.

## Definition of done pentru primul vertical slice

Un fixture `level_1_first_kill` trece adapter -> observer -> decision stub -> telemetry -> encounter -> replay -> Journal; fiecare fact are provenance; execution rămâne `OBSERVE_ONLY`; testele negative resping omnisciența și contaminarea Champion memory.

## Status 2026-08-22

- `PA-001`–`PA-017`: implementate; foundation, observer slice și intake-ul offline sunt verificate.
- `PA-018`: probe controlat finalizat manual pe clientul LAB `2.4.3.8606`; exportul real a fost reconciliat cu ecranul.
- `PA-019`: implementat; numai `PARTY_KILL` are mapare semantică verificată, cu active-target GUID guard. Capability parity a fost actualizat din captura reală.
- Evidence curent: `contract_tested`, `replay_tested`, `lab_integrated` și `controlled_live_verified`, strict pentru suprafața observe-only documentată.
- Suita curentă: se recalculează la fiecare gate; telemetry/exporturile reale rămân ignorate de Git.
- `PA-020`: contract și addon implementate pentru quest NPC/detail/log și spellbook. Prima probă live a verificat detail/log/spellbook, dar gate-ul complet rămâne deschis pentru greeting, loot și zone recapture.
- `PA-020a`: external LAB client operator implementat cu faze finite, audit și checkpoint-uri. Nu este Predator execution.
- `PA-020b`: următoarea probă controlată trebuie să verifice `quest_npc_snapshot`, `loot_snapshot` și zone state cu addon `0.2.1`.
- După închiderea PA-020b: `PA-021` — QuestPlanner read-only + route-drift reconciler + QuestNarrator fără autoritate de execution.
- `PA-022A` — target fingerprint + capability negotiation pentru onboarding standalone.
- `PA-022B` — GearSnapshot/Analysis contracts și availability firewall.
- `PA-022C` — Leveling Gear Evaluator pentru reward/equip, cu profile PvE/PvP/leveling.
- `PA-022D` — WoWSims `tbc-new` pin/build local, simulator adapter și golden Rogue fixtures.
- `PA-022E` — Gear Advisor în Predator Control Panel și Journal.
- `PA-023A` — VoiceOver legacy 2.4.3, module audio și probă client controlată.
- `PA-023B` — NarrativeCue, Predator reflections și ShadowPlay/replay timing.
- `PA-024A` — MovementGoal/PathProposal contracts + deterministic tactical grid A*.
- `PA-024B1` — complete v0.1: pose/capture contracts, replay intake, exact foreground locator și bounded continuous provider. DXGI/WinRT stable, foreground deny și live move/resize au trecut pe clientul LAB.
- `PA-024B2a` — implementat/testat: boundary determinist pentru minimap anchor, separare camera/body și uncertainty-aware pose fusion; fără input și fără server truth.
- `PA-024B2b1` — implementat/testat sintetic: profil versionat minimap ROI + detector geometric pentru circle/player marker; contractul interzice absolute pose.
- `PA-024B2b2` — pending: calibrare pe replay-uri reale redactate și probă controlată live pentru UI scale/resolution/minimap modes.
- `PA-024B3a` — implementat/testat sintetic: self-coordinate API contract, Observer HUD v1 vizibil, CRC-16 codec și detector cu fiducials.
- `PA-024B3b` — complete exact-version: addonul `0.3.5` a trecut matricea controlled-live, relaunch/relog și un al treilea current-source resmoke după hardening. Raster/freshness, două UI scales și două dimensiuni, map open/close fail-closed, parity SavedVariables și autorizația fixed-UI cu `permitted_modes=[]` sunt dovedite.
- `PA-024B3c` — pending: zone transition pe LAB clone dedicat; nu teleportăm Championul Journey pentru calibrare.
- `PA-024B4` — implementat/testat: WorldMapArea client-asset hash-pinned transformă self map position în world-map 2D, fără `z` și fără server truth.
- `PA-024B2c` — pending: provider scene/camera și fusion live cu minimap/dead-reckoning.
- `PA-024B5` — implementat/testat: trace sincronizat pose/action + motion
  calibration determinist per client/target; modelul curent rămâne evaluation-only
  și nu consumă server truth.
- `PA-024F1` — implementat și review independent CLEAN: Execution Gateway
  deny-by-default, hold/envelope separat, lease/pose/deadline binding,
  runtime-arm revocation, takeover și release-all.
- `PA-024F2` — implementat și review independent CLEAN, fake-only:
  Win32 user-mode scan-code adapter exact target-bound, key ownership,
  hot identity checks și cleanup; nu există runner ori input live.
- `PA-024F3a` — controlled-live PASS: un singur forward hold de `100 ms` într-un
  envelope total de `150 ms`, fresh pose înainte/după, displacement peste
  incertitudinea combinată, stop și disarm imediat. Urmează turn/2-point course.
- `PA-024C` — contract-only implementat/testat: `pgeom v1`, `pnav v1` și
  snapshotul NAV DEBUG fixează manifestul asseturilor, coordinate space,
  Recast pin, tile refs size/SHA și provenance; parserul și primul tile real
  Deathknell rămân următorul gate.
- `PA-024C2` — Navigation Debug Visualizer `OFF | ROUTE | MESH`: inset
  Direct2D/DirectComposition peste client ca suprafață primară, Control Panel
  opțional ulterior, apoi world-aligned după camera calibration; addonul oferă
  numai toggle-ul vizibil, nu randarea mesh-ului.
- `PA-024D0` — Experience Map per actor/build: static geometry verification,
  traversals, familiarity, stuck/fall/death/aggro/stealth heat și TTL pentru
  observațiile dinamice; nicio contaminare LAB -> Champion.
- `PA-024D1` — tactical costs și dynamic actor/obstacle memory peste Experience Map.
- `PA-024E0` — geometric curvature-limited spline follower baseline + 2-point/hairpin course; rămâne deadline fallback pentru MPPI.
- `PA-024E1` — common replay benchmark pentru geometric follower, DetourCrowd, RVO2 și PA-MPPI.
- `PA-024E2` — PA-MPPI local trajectory controller, motion primitives și deadline fallback.
- `PA-024E3` — behavior-tree recovery, relocalization și stuck heatmap.
- `PA-024F0` — Target Profile Registry v2 + onboarding local/LAN/remote + Instance/Actor binding și lease per Executor Worker.
- `PA-024F3b` — bounded Recast/spline/MPPI LAB movement course și takeover instant; fără combat inițial.
- `PA-024F4` — multi-worker orchestrator + Control Panel remote/takeover + adapter de stream care păstrează desktopul local-console.
- `PA-024F5` — probă cu două instanțe pe desktopuri izolate: Champion Journey + LAB clone, fără focus sau memory cross-talk.
- `PA-024G` — corpse-run, event-hunt și PvP pursuit benchmark pe holdouts.
- `PA-024H1` — graf semantic de călătorie pentru mers, barcă, zeppelin,
  portal, flight path și hearthstone, derivat din WorldPack și evidence
  client-visible.
- `PA-024H2` — executor observabil al tranzițiilor de transport, cu replan după
  transport ratat, combat, hartă/ieșire neașteptată și cooldown indisponibil.
- `PA-025A` — simulator rapid PvP cu opponent policies, LOS/teren și build-uri
  calibrate; produce candidați, nu autoritate de promovare.
- `PA-025B` — replay + clone LAB PvP development/holdout și promotion gate către
  Champion memory.
- `ADR 0019`: cercetarea prior-art a validat stackul PA și a interzis copierea din repo-uri fără licență; ordinea accelerată livrează primul movement măsurat înaintea stackului complet, fără downgrade de producție.

## Status Gear/VoiceOver foundation 2026-08-22

- `PA-022A`: contractul target fingerprint/capability negotiation este implementat; runtime discovery rămâne de construit.
- `PA-022B`: GearAnalysis contract și availability firewall sunt implementate/testate.
- `PA-022C`: pending; nu există încă evaluatorul numeric level 1–69.
- `PA-022D`: source/release WoWSims pin-uite și UI/CLI smoke-tested local; golden simulations și calibrarea sunt pending.
- `PA-023A`: cele patru componente VoiceOver sunt deployate pentru 2.4.3; addon discovery și main-player load sunt verificate live, iar redarea audio NPC/quest rămâne gate-ul deschis.
- `PA-024A`: implementat și testat fără input; Recast este staged, nu integrat runtime.
- `ADR 0012`: Recast/Detour + PA-MPPI + uncertainty-aware pose fusion este stackul ales.
- `ADR 0013`: Havok este închis; bugetul comercial este sub USD 500/componentă; fără memory read/kernel HID; actuatorul viitor este Win32 user-mode și target-allowlisted.
- `PA-024B1 contract`: implementat/testat read-only; player/body și camera sunt separate, iar `LOST` și provenance firewall sunt fail-closed.
- `PA-024B1 capture`: complete v0.1; exact TBC 2.4.3 PID/HWND/foreground/client-region, DXGI + WinRT continuous și live move/resize verificate fără pixel persistence. Multi-output transition rămâne fail-closed și testat determinist deoarece hardware-ul curent expune un singur output.
- `PA-024B2a`: complete v0.1; anchor measurements devin pose observations contract-valid, fusion-ul este determinist/covariance-weighted, camera rămâne independentă, iar stale/expired/build-map mismatch/server truth sunt fail-closed. Detectorul vizual live nu este încă implementat.
- `PA-024B2b1`: complete `synthetic_only`; NumPy sidecar localizează geometria
  minimap și markerul central, publică explicit `absolute_pose_available=false`
  și propagă actor binding fără LAB/Champion/replay provenance laundering.
  Noise/loading/missing marker/profile mismatch/buffer mismatch sunt testate
  fail-closed. Calibrarea reală rămâne PA-024B2b2.
- `PA-024B3a`: complete `synthetic_verified`; addon API + HUD vizibil este sursa primară de self map coordinates.
- `PA-024B3b`: controlled-live exact-version `0.3.5` trecut pentru raster, sequence freshness, occlusion, layout matrix, relog, offline parity și current-source hardening resmoke. Acest gate nu promovează profilul; PA-024B3c zone transition rămâne obligatoriu.
- `PA-024B4`: client-asset calibration validată în Tirisfal; SavedVariables transformate diferă de martorul LAB post-logout cu numai `0.00010` world units. Martorul DB rămâne `lab_evaluation_only`.
- `ExecutionTargetAuthorization`: implementat/testat; localhost-only eliminat, emulator allowlist general, PTR pending evidence, public live denied.
