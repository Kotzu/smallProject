# PA-019 — first live TBC 2.4.3 observer capture

## Outcome

`PASS — lab_integrated + controlled_live_verified for the bounded observe-only intake`

This is not evidence for movement, execution, autonomous play, PvP or Anniversary compatibility.

## Probe

- target: local CMaNGOS TBC LAB, loopback only;
- client: candidate `2.4.3.8606`, launched manually by the operator;
- character: temporary level-1 Undead Rogue LAB clone, not Champion;
- collector: `PerfectAssassinObserver` addon;
- transport: offline client-owned SavedVariables after normal logout;
- decision mode: `OBSERVE_ONLY`.

## Screen-to-export reconciliation

| Operator-visible action | Captured evidence | Result |
|---|---|---|
| entered the Undead starting area | self snapshots; `Tirisfal Glades / Shadow Grave` | PASS |
| selected a quest giver | target `Undertaker Mordo`, 100% health | PASS |
| did not take the quest | no supported quest-state contract exists | NO CLAIM |
| fought a nearby bat | target `Duskbat`; combat state and target-health snapshots | PASS |
| killed the bat | raw `PARTY_KILL` and `UNIT_DIED`; guarded `target.dead=true` mapping | PASS |
| gained progress | player level 1, XP 52 | PASS |
| loot | no `LOOT_OPENED` event captured | NOT VERIFIED |

## Deterministic output

- 19 normalized observations;
- 19 read-only decisions;
- 1 assembled PvE encounter, outcome `victory`;
- 85 raw combat-log events retained;
- 1 raw combat-log event interpreted;
- 0 addon-buffer events dropped;
- replay hash: `b9139fbe46c0345b1c6429aef037c9da0ab269aea895f87abe0bd155ebb4f921`.

The death reducer removes the previously observed 19% health from effective state after `target.dead=true`; it does not fabricate health 0.

## Provenance and privacy

Every normalized fact is `client_observed` and passed the existing provenance firewall. No database, GM, Playerbots, packet or server-ground-truth field entered the decision stream. The real SavedVariables export, telemetry and Journal are ignored runtime artifacts and are not committed.

## Explicitly unverified

- quest offer/accept/complete state;
- real loot-window contents;
- self spellbook and usable abilities;
- damage, cast, miss and `UNIT_DIED` semantic decoding;
- movement, camera, input or execution;
- PvP learning and opponent memory;
- Champion identity binding;
- TBC Anniversary adapter behavior.

## Next gate

PA-020 remains Observer work: add a legitimate quest-state contract, capture a real loot window and capture self spellbook capability. No action leaves `OBSERVE_ONLY` until those observations and their replay behavior are tested.
