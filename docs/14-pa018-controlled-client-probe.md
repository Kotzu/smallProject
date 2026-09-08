# 14 — PA-018 controlled client probe

## Outcome

`PASS — controlled_live_verified for the bounded observe-only intake`

## Final state

- client static build: `2.4.3.8606`;
- client process at install: stopped;
- realmlist: `127.0.0.1`;
- addon target: installed and hash-verified;
- LAB database/realm/world/RA: ready, loopback only;
- probe account: `PA_OBSERVER`, expansion 1, GM level 0;
- probe credential: maximum 16 characters, conform limitei legacy CMaNGOS/TBC 2.4.3;
- Playerbots: module initialized, no automatic population and zero players online at readiness check;
- client execution: performed manually by the operator; Codex did not execute the untrusted binary;
- addon load: verified by the resulting real SavedVariables export;
- real export: imported, replayed and reconciled with the operator's visible actions;
- online players after logout: zero.

## Manual execution boundary

`Wow.exe` reports build 8606, but Authenticode is `HashMismatch` and package provenance is not canonical. The operator accepted this risk and launched it manually. This does not authorize Codex or a future Supervisor to execute an untrusted client automatically.

## Bounded probe card

1. Confirm that the four LAB listeners remain on `127.0.0.1`: `3307`, `3443`, `3724`, `8085`.
2. Read the local credential from `E:\WoWserver\TBC-LAB\database\observer-account.local.json`; do not copy it into Git/chat.
3. Launch the client manually only if accepting the executable risk.
4. In AddOns, confirm `Perfect Assassin Observer` is enabled and no Lua error appears.
5. Log in as `PA_OBSERVER`; create a level-1 Rogue with an unmistakable temporary LAB name. It is not Champion.
6. Perform only: enter world → select one nearby NPC → one short combat → optionally open loot → normal logout.
7. Exit the client fully.
8. From the workspace run `scripts\Import-LabObserverCapture.ps1`.
9. Compare the produced Journal timeline with the visible steps above. Do not promote if an event, timestamp ordering or target fact is wrong.

## Pass results

- addon loads without error;
- export matches schema `0.1` and `tbc243-legacy-v1`;
- importer does not execute the file;
- at least one player snapshot, target snapshot and combat state normalize;
- 85 raw combat events were archived; only the verified `PARTY_KILL` event was interpreted;
- every normalized fact is `client_observed` and passes the firewall;
- telemetry/replay/Journal complete in `OBSERVE_ONLY`;
- no Playerbots/server ground truth appears in observations;
- output: 19 observations, 19 read-only decisions and one PvE victory encounter;
- deterministic replay hash: `b9139fbe46c0345b1c6429aef037c9da0ab269aea895f87abe0bd155ebb4f921`.

## Reconciled screen evidence

- the temporary level-1 Undead Rogue appeared in `Tirisfal Glades / Shadow Grave`;
- `Undertaker Mordo` appeared as the selected quest giver;
- a `Duskbat` appeared as combat target and the kill was recorded;
- player XP reached 52;
- no loot event was captured;
- quest acceptance cannot be inferred because v0.1 has no verified quest-state contract.

The real export and generated runtime files remain ignored by Git because they may contain client/player-identifying data.

## Fail/rollback

Stop the client. Preserve the failed export in an ignored runtime/quarantine location for diagnosis. Run `scripts\Remove-Tbc243ObserverAddon.ps1 -WhatIf`, inspect the exact target, then run it without `-WhatIf` only if rollback is desired. Stop LAB gracefully with world → realm → database scripts.
