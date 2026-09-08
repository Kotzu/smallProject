# 16 — PA-020 first live quest capture

## Outcome

`PARTIAL PASS — quest detail, quest log and spellbook are controlled-live verified; full PA-020 promotion remains blocked by NPC greeting and loot evidence`

## Session

- client: TBC `2.4.3.8606`;
- realm: local CMaNGOS LAB, loopback only;
- character: `Predator`, level 1 Undead Rogue, LAB clone context;
- addon export schema: `0.2`;
- Predator execution: `OBSERVE_ONLY`;
- UI actor: external LAB operator harness, explicitly outside Predator Brain.

The user explicitly authorized the remote controlled probe while away from the computer. This authorization covered the external operator actions in this session; it did not enable an autonomous Predator execution capability.

## Verified live observations

The client showed and the offline replay reconstructed:

- quest giver: `Undertaker Mordo`;
- quest: `Rude Awakening`;
- full client-visible narrative description;
- objective: `Speak with Shadow Priest Sarvis.`;
- the same quest present in Quest Log after acceptance;
- `Quests: 1/25` and the visible chat confirmation `Quest accepted: Rude Awakening`;
- level 1 and 52 XP;
- nine spellbook entries: Attack, five Undead racial/passive entries, Throw, Eviscerate Rank 1 and Sinister Strike Rank 1;
- target transitions ending on `Young Scavenger`.

Import result:

- 15 observations;
- 15 read-only decisions (`observe.continue`);
- 0 assembled encounters;
- 256 raw combat-log records archived;
- 0 raw combat records semantically interpreted;
- replay SHA-256: `d741fee9ba21de7943e2e29291c7180ccdcbf7e579be505567be5d28a4f71896`.

Runtime telemetry, screenshots, audit and Journal remain ignored by Git.

Post-capture verification: 34 automated tests pass, including operator-boundary, no-secret, addon no-execution and zone-event checks. The deployed client addon hashes match the repository's pinned `0.2.1` artifacts.

## Gaps found instead of hidden

1. A single available quest opened directly as `QUEST_DETAIL`; the client did not emit a separately observed `QUEST_GREETING`, so this session has NPC identity inside `quest_detail` but no `quest_npc_snapshot`.
2. No real loot window was opened, therefore there is no `loot_snapshot`.
3. No kill was completed during this session; target acquisition and attempted external movement do not qualify as a Predator encounter.
4. Initial `GetZoneText`/`GetSubZoneText` values were empty. Addon `0.2.1` now recaptures the legitimate client location on `ZONE_CHANGED`, `ZONE_CHANGED_INDOORS` and `ZONE_CHANGED_NEW_AREA`; this fix still needs the next live probe.
5. Selecting a unit by name can retain a target hidden by terrain. Combat/movement must therefore require visual/state feedback and may not be built from fixed timing or target-name selection alone.

## Promotion decision

Promote only these PA-020 capabilities to `controlled_live_verified`:

- `quest_detail`;
- `quest_log_snapshot`;
- `spellbook_snapshot`.

Keep the complete PA-020 gate open until a follow-up captures:

- a genuine `quest_npc_snapshot` from greeting or gossip;
- a genuine `loot_snapshot`;
- non-empty zone state after addon `0.2.1`;
- a normal logout/import reconciliation.

No observations from this LAB session become Champion identity memory.

## Repeatable away-from-home operation

The bounded helper is `scripts/Invoke-LabClientOperator.ps1`. It validates loopback listeners, reads the local credential without printing it, records checkpoints/audit and supports only launch/login/enter/capture/logout/close/import phases. Login, enter-world and logout refuse to run without an explicit confirmed visual-state label after a separate checkpoint has been inspected. It has no general movement or combat command.
