# 18 — Perfect Assassin standalone și portabilitate între targeturi

## Outcome

Același Champion Core poate rula în open world, questing, PvP și ulterior dungeons pe targeturi diferite. Se schimbă adapterul, capability profile și scenario pack; identitatea, contractele semantice și regulile de learning rămân stabile.

Produsul nu este limitat la `localhost`: emulatorul poate fi local, LAN sau
remote controlat, iar un PTR autorizat specific are propriul profil. Realm-ul
este o selecție de date/profile, nu un fork de cod. Poate rula simultan un
Champion Journey și mai multe LAB clones, cu identități, memorii și artifacts
runtime izolate. Decizia completă este în
[ADR 0017](adr/0017-standalone-multi-target-and-multi-instance-operation.md).

## Boot handshake

```text
Discover target
  -> build TargetFingerprint
  -> run read-only capability probes
  -> select exact/compatible adapter
  -> load semantic registry + mechanic profile
  -> enforce deployment policy
  -> OBSERVE_ONLY smoke replay
  -> allow only explicitly approved modes
```

Un adapter nu este selectat doar după numele serverului. Verificăm build/API/event semantics, locale și probe replay. Dacă ceva este necunoscut, capabilitatea este deny.

## Ce rămâne universal

- intent, planning și action scoring;
- memory namespaces și Champion identity;
- tactical world model și opponent memory;
- Journal, replay, ShadowPlay hooks și Supervisor pipeline;
- skill representation semantică;
- profile de obiectiv PvE/PvP/leveling;
- takeover și execution safety.

Environment identity (target/realm/build) rămâne separată de actor identity
(Champion/LAB clone/journey). Un target nou nu transformă o clonă în Champion,
iar un realm nou nu cere schimbarea Brain-ului.

Pentru gameplay fluid simultan, fiecare client cu input are propriul Executor
Worker și propriul desktop interactiv/session/VM/host. `SendInput` este global
pe desktop; time-slicing-ul a două ferestre pe același desktop este numai LAB,
nu arhitectură Champion-quality.

## Ce aparține targetului

- numeric spell/item/NPC/quest IDs;
- API/event names și SavedVariables format;
- patch mechanics și coefficients;
- movement/input transport disponibil;
- inspect/Armory/addon restrictions;
- emulator quirks și quest drift;
- reguli de deployment ale platformei.

## Onboarding pentru un server/version nou

1. Inventar read-only și target fingerprint.
2. Capability profile deny-by-default.
3. Adapter skeleton fără tactică.
4. Fixtures și golden replays pentru observation parity.
5. Mechanic calibration pentru combat și gear.
6. Scenario smoke tests în `OBSERVE_ONLY`.
7. Controlled LAB probe.
8. Promotion separată pentru fiecare execution mode permis.

Un target nu moștenește execution modes din LAB. Emulatorul local/LAN/remote
cere realm allowlist, exact client hash, bounded approval și runtime arm.
Profilele LAN/remote curente au numai assurance `configured_endpoint_only` și
rămân `OBSERVE_ONLY`, cu `permitted_modes=[]`; inputul remote cere un viitor
adapter de assurance mai puternic și o autorizare separată. PTR are profil
separat și rămâne `pending_evidence` până când autorizarea specifică redactată și
fingerprint-ul exact sunt înregistrate. Orice `public_live` oficial este denied,
inclusiv realm-uri Classic/legacy și retail; numai un PTR separat și autorizat
explicit poate deveni eligibil.

## Context packs

- `open_world_roaming`: explorare, threat, resurse, escape și oportunități.
- `questing`: route teacher, quest interpretation, drift reconciliation și reward choice.
- `pvp`: opponent memory, uncertainty, adaptation și encounter review.
- `dungeon`: rol, party coordination, route/boss strategy și wipe recovery.

Dungeon knowledge va combina strategii versionate cu observație și adaptare. Un script de boss nu poate ocoli Brain-ul, capability gates sau party-state uncertainty.
