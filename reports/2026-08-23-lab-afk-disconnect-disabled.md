# LAB AFK disconnect — disabled

Date: `2026-08-23`

Target: `tbc_243_lab`, CMaNGOS TBC + Playerbots

Result: `PASS`

## Outcome

The hardcoded 15-minute AFK disconnect in CMaNGOS is now a reloadable unsigned integer setting expressed in minutes:

```ini
Player.AFK.DisconnectTimeout = 0
```

`0` disables AFK disconnection. The generic core default remains `15`, preserving upstream behavior outside this LAB profile. Network, logout, reconnect and battleground AFK-report behavior are unchanged.

## Source and build evidence

- Upstream base: `adbc7f747a3a5c4741a012d86f6cd8112238b5bc`.
- Local source branch: `perfect-assassin/lab-afk-policy`, commit `6444b78070a09afaf0a491c3527f4aea707db730`.
- Versioned local overlay: `TBC-LAB/integration/patches/0001-configurable-afk-disconnect.patch`.
- Overlay SHA-256: `9BB2012E574095F1BADC5E15745B209AD318080F2D5D12DE43C8ED7E37D6ECCB`.
- Reverse apply check against the patched source: `PASS`.
- `core-playerbots`, x64 Release, target `mangosd`: build `PASS`.
- The timeout comparison uses unsigned 64-bit elapsed seconds, avoiding signed `time_t` overflow on 32-bit builds.
- Deployed `mangosd.exe` SHA-256: `C719891C11D3E94B8ADF84CA466818B3EB6D24138E623B0880526B570F9E82A6`.
- Deployed `mangosd.conf.dist` SHA-256: `06997CB65B6FAF52BD914F422B553B41B1FC674C420CD2D88045532917B90ED1`.
- Active `mangosd.conf` SHA-256: `5AC287EF0C6F1F72757E7BAD88CE17D5D33547AD3236B51511E8802F92647295`.
- Active config contains exactly one `Player.AFK.DisconnectTimeout = 0` entry.

`Write-LabRuntimeConfig.ps1` now sets the LAB value fail-closed: it refuses an old distribution config that does not expose the new setting.

## Runtime verification

- Players online before restart: `0`.
- World server stopped gracefully through RA; MariaDB and `realmd` remained running.
- New world server reached `CMANGOS: World initialized`.
- Loopback listeners healthy: MariaDB `3307`, RA `3443`, auth `3724`, world `8085`.
- `server info`: `PASS`, zero sessions online.
- Exact execution-target listener pins were updated for the new world binary and config.
- `Invoke-LabClientOperator -Action Status`: `PASS`, `OBSERVE_ONLY`, no client, receipt or runtime arm active.
- Final authorization snapshot SHA-256: `ABCA4868065A8F04A0AB5A1592657E4A4B1EFBBE0820D9E5DDF848AA9E4621AA`.
- Full Perfect Assassin test suite after final deploy: `240/240 PASS`; Python compile, PowerShell parse and `git diff --check`: `PASS`.

## Rollback proof

Exact previous runtime snapshot:

```text
E:\WoWserver\TBC-LAB\snapshots\mangosd-pre-afk-config-20260823T001642
```

Previous Stable hashes:

- `mangosd.exe`: `C3A2BCE7685F5222A2A3E298959C0016255C0F677A697A01C678160887C929B7`;
- `mangosd.conf`: `4EF7697615B289C96B37B179E555C804596A9185B775FE1B74A2451E93A901E0`;
- `mangosd.conf.dist`: `93195A90858DC1F30EA72613FA6F02ECEE5DE790954CB04C8A6CF78ECEDFB055`.

The complete rollback was executed, not simulated: the old binary/config were restored by exact hash, the old world server reached ready state and answered `server info`, then the patched binary/config were redeployed and reached ready state again. The snapshot manifest validates every stored artifact.

The portability hardening was also deployed through a second exact rollback cycle. Its immediate predecessor snapshot is:

```text
E:\WoWserver\TBC-LAB\snapshots\mangosd-pre-afk-portability-20260822T213407Z
```

The predecessor binary `78E325DE967C5C0CE79D9EEB5E5FA8FC78C4A0218EAB463C5694BFA783DC55CC` was restored and booted successfully, answered `server info`, then the final overflow-safe binary was redeployed and reached ready state on loopback ports `3443` and `8085`.

## Operational note

The first activation required a binary restart because the previous executable contained the hardcoded timeout. On the patched executable, later changes between `0` and a positive minute value can be applied through `reload config`.
