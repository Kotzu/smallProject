# TBC LAB bootstrap report — 2026-08-22

## Outcome

Status: **LAB-baseline-001 ready; Predator integration has not started.**

The isolated CMaNGOS TBC host, Playerbots opponents, MariaDB databases, extracted client data, local realm, world boot, operator channel and rollback snapshot are verified. No Playerbots opponent is configured to log in automatically, and none is part of Predator's decision system.

## Pinned source

| Repository | Commit |
|---|---|
| `cmangos/mangos-tbc` | `adbc7f747a3a5c4741a012d86f6cd8112238b5bc` |
| `cmangos/playerbots` | `076045efa835da9aab7caa943bca752aebe1baad` |
| `cmangos/tbc-db` | `b878ba13e8af90b9ce597278f9858109f15bff91` |

Machine-readable source, toolchain and client records are stored in `E:\WoWserver\TBC-LAB`.

## Evidence

| Check | Result |
|---|---|
| Release x64 build with extractors and Playerbots | PASS |
| Dedicated MariaDB 12.3.2 | PASS on `127.0.0.1:3307` |
| Full TBC world/characters/realm/logs import | PASS |
| DBC/maps extraction | PASS: 185 / 3,586 files |
| VMaps/MMMaps generation | PASS: 8,607 / 2,838 files |
| `realmd` | PASS on `127.0.0.1:3724` |
| `mangosd` | PASS on `127.0.0.1:8085` |
| Local remote administration | PASS on `127.0.0.1:3443` |
| Full world initialization | PASS; startup completed with VMaps and MMaps enabled |
| Dedicated operator | PASS: `PA_OPERATOR`, gmlevel 3, expansion 1 |
| Public stock administrator password | Rotated after operator login verification |
| Playerbots cohort | 5 accounts, 45 level-1 characters available; max 20 active; autologin off |
| Graceful world shutdown | PASS through localhost RA |
| Snapshot | PASS: `LAB-baseline-001` |
| Snapshot DB archive | 81,067,404 bytes; 4 SQL dumps; SHA-256 `3735FFEAE2AA20A23260D110D2296B8EE81879E48632D7A2C31E2A6521424927` |

## Client decision

The current enGB client reports build `2.4.3.8606` and its archives are compatible with the pinned CMaNGOS extractors. However, it is a user-provided repack with unverified provenance, and `Wow.exe` has SHA-256 `406DA0C1C22D6E9121FD3BC17740A0D013660A03748CFE2A235768B8C574D3E6` plus Authenticode status `HashMismatch`.

Decision: the package is accepted only as a **candidate extraction source**. `Wow.exe` is not authorized to run. A canonical trusted client can replace it later without changing Predator Core; only the TBC adapter/LAB data need revalidation.

Moonwell-specific addons, fonts, links and readme were moved to recoverable quarantine at `E:\WoWserver\TBC-LAB\quarantine\client-moonwell-2026-08-22`. `realmlist.wtf` now targets `127.0.0.1`.

## Safety and boundaries

- LAB, project workspace and game client are separate roots.
- All services bind only to loopback.
- DB and operator secrets stay outside Git with restricted ACLs.
- Playerbots are opponents/quest helpers, never Predator and never a source of privileged knowledge.
- Predator has not received server-only state or control hooks.
- AHBot is disabled; Playerbots startup/autologin is disabled.
- The first world boot created caches and the controlled opponent pool; no players were online.
- The baseline was captured with world and realm stopped.

## Snapshot and rollback

`E:\WoWserver\TBC-LAB\snapshots\LAB-baseline-001` contains a manifest and compressed logical dumps of `tbcrealmd`, `tbccharacters`, `tbcmangos` and `tbclogs`. The ZIP was reopened and all four entries were enumerated after creation. Restore must occur into an isolated LAB instance and pass DB, realm and world smoke tests before promotion.

One incomplete dump attempt, caused by an unnecessary `SHOW EVENTS` privilege, was moved intact to `E:\WoWserver\TBC-LAB\quarantine\failed-LAB-baseline-001-events-20260822`; it is not a valid snapshot.

## Next gate

M1 begins with the read-only TBC 2.4.3 Observer adapter and telemetry contract. It may consume only client/addon-observable information. No movement or action execution is allowed until deterministic observation/replay tests pass.
