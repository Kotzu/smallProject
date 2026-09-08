# Capability parity v0.1 — 2026-08-22

## Evidence boundary

Această matrice separă `fixture_verified`, `controlled_live_verified` și `unverified`. Verificarea live este limitată la LAB-ul local 2.4.3 și nu autorizează execution pe Blizzard.

| Capability | TBC 2.4.3 LAB adapter | TBC Anniversary | Brain fallback |
|---|---|---|---|
| combat log | `controlled_live_verified / restricted`: only `PARTY_KILL` semantic mapping; all other events raw | `unverified / unknown` | omit unverified facts |
| target state | `controlled_live_verified / available` while client-visible | `unverified / unknown` | omit facts |
| self state | `controlled_live_verified / available` for level, XP and dead/alive | `unverified / unknown` | omit facts |
| self spellbook | profile declared; no fixture event yet | `unverified / unknown` | omit facts |
| loot observation | `fixture_verified`; API reported available, but no real loot event captured | `unverified / unknown` | omit facts |
| level progress | `controlled_live_verified / available` for XP and level snapshots | `unverified / unknown` | omit facts |
| world location | `controlled_live_verified / available` for client-visible zone/subzone | `unverified / unknown` | omit facts |
| quest state/text | `fixture_verified / available`; PA-020 live probe pending | `unverified / unknown` | omit facts |
| enemy inspect | policy tested as `restricted` | `unverified / restricted` | require evidence or omit |
| global player positions | `unavailable` by policy | `unavailable` by policy | forbidden |
| server patrol/spawn state | negative test rejects | `unavailable` by policy | forbidden |
| Wowhead in combat loop | `unavailable` | `unavailable` | cached knowledge only, later milestone |
| Zygor route guidance | `restricted`; not integrated | `restricted`; not integrated | no route fact |

## Verified now

- Deny-by-default profile validation.
- Restricted facts require a legitimate source and explicit restriction evidence.
- Raw keys terminate in the adapter and become semantic IDs.
- `server_ground_truth` is rejected before telemetry is created.
- Real `2.4.3.8606` export traverses addon → restricted parser → adapter → firewall → telemetry → replay → Journal.
- Verified `PARTY_KILL` mapping requires destination GUID equality with the last active client-observed target.
- A death observation invalidates stale `target.health_pct`; telemetry is preserved and health `0` is not fabricated.

## Required next

1. Add a client-legitimate quest-state contract before making quest acceptance claims.
2. Capture and reconcile a real `LOOT_OPENED` event.
3. Capture self spellbook data before enabling ability reasoning.
4. Verify each additional legacy combat sub-event independently before semantic mapping.
5. Inventory and test Anniversary through its own adapter; keep unavailable/unknown capabilities omitted, never guessed.
