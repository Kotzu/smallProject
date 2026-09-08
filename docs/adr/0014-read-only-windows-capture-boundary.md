# ADR 0014 — Read-only Windows capture boundary

- Status: accepted
- Date: 2026-08-22
- Extends: ADR 0012 și ADR 0013

## Context

PA-024B are nevoie de pixeli și timestampuri pentru minimap/scene vision, fără memory read, injection sau server-only pose. Captura trebuie să rămână în afara Brain-ului și să poată fi înlocuită per client/OS.

Au fost evaluate Desktop Duplication, Windows Graphics Capture și un sidecar Python bazat pe DXcam 0.3.0. Mediul curent are Python 3.14 și Windows SDK, dar nu are un toolchain C++/.NET complet; un sidecar pin-uit permite să validăm contractele și latența înainte să justificăm cod nativ.

## Decizie

1. `CaptureProvider` este un port read-only. Livrează un `CapturePacket`: manifest versionat și un pixel view opțional, caller-owned.
2. Pixelii nu intră în telemetry. Telemetry/replay indexează numai `CaptureFrameManifest` și, când retenția este aprobată explicit, un artifact path + SHA-256.
3. DXcam 0.3.0 rămâne integrare opțională în `integrations/windows-capture`, nu dependency a nucleului.
4. DXGI Desktop Duplication este backend-ul primar v0.1. WinRT monitor capture este fallback/comparator.
5. DXcam WinRT folosit aici capturează monitorul; nu îl prezentăm drept `CreateForWindow`. Window locator + client-region tracker este un provider separat.
6. `CaptureReplayProvider` este primul provider conectat la test harness. El nu încarcă pixeli și permite regression determinist.
7. Orice manifest de captură are `execution_authority=false`.

## Privacy și failure behavior

- default: frame numai în memorie, `persisted=false`, retention `none`;
- persistarea cere path, hash și clasificare `redacted` sau `unredacted_restricted`;
- probe-ul afișează numai metadata și nu salvează screenshot;
- capture loss, minimizare, RDP rejection, source mismatch sau frame stale degradează pose; nu autorizează movement;
- window/source identity va fi verificată înainte ca frame-ul să fie folosit de un pose provider.

## Consecințe

- putem dezvolta minimap localization și optical-flow replay fără WoW pornit;
- backend-ul Windows poate fi înlocuit fără schimbarea Brain/movement contracts;
- nu avem încă dovadă de client-region capture sau pose accuracy;
- un sidecar nativ `CreateForWindow` se evaluează numai dacă region tracking/DXGI nu trece benchmark-ul;
- dependințele binare rămân în `E:\WoWserver\PerfectAssassin-Dependencies`, separat de server și repo.

## Status implementare

PA-024B1 continuous provider este verificat pe clientul LAB: bounded RAM buffer, per-frame source revalidation, authorization-backed executable hash/build identity, legare PID → process image → cale/SHA-256 înainte și după fiecare frame, DXGI/WinRT stable capture, foreground deny și live move/resize. Output migration rămâne fail-closed; hardware-ul curent oferă un singur output pentru proba live.

Pentru identitatea procesului, Windows încearcă mai întâi
`PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE`. Clientul legacy 2.4.3 poate
refuza acel mask cu `ERROR_ACCESS_DENIED`; numai atunci sidecar-ul folosește
fallback-ul metadata-only `PROCESS_QUERY_INFORMATION | SYNCHRONIZE`. Nu sunt
cerute drepturi VM. Approval-ul este întotdeauna finit: dacă `expires_at`
lipsește dintr-un authorization v2 compatibil, expirarea este derivată din
`recorded_at + max_session_minutes`; un `expires_at` explicit nu poate depăși
această limită.

Authorization-ul și launch receipt-ul sunt citite dintr-un singur file handle,
cu un read de cel mult limita plus un byte; hash/parsing folosesc același
snapshot. Parserul refuză duplicate keys și orice număr non-finit, inclusiv
overflow-ul unui exponent JSON finit lexical. Metadata procesului leagă path,
creation UTC/FILETIME, Windows session și liveness înainte/după verificare.
`ProcessIdToSessionId` are fallback WTS read-only numai pentru
`ERROR_ACCESS_DENIED` observat pe clientul legacy.

Până când markerul atomic de identity issuance este consumat în această
boundary, fallback-ul receipt v1 acceptă numai `operator_launch` fără parent
lineage. Receipt-urile adoptate sau renewed sunt fail-closed aici și folosesc
identitatea nativă directă, care este calea verificată pe sesiunea legacy
curentă.

## Migrare contract 0.1 → 2.0

v1.0 a făcut scope-ul contextual și incompatibil cu v0.1. v2.0 adaugă
`actor_binding` structurat și `authorization_sha256`, apoi elimină alegerea
liberă a `decision_context` din CLI. Hash-ul leagă manifestul de bytes exacți
ai autorizației validate, nu doar de un ID reutilizabil. Replay-ul este
obligatoriu `synthetic_fixture`, captura live pentru
`lab_clone` este `lab_evaluation_only`, iar captura Champion cu actor doar
configurat este `unpromoted_evaluation_only`. `expected_character_name` nu este
prezentat ca identitate observată. Fixture-urile vechi trebuie regenerate; un
consumer nu are voie să rescrie scope-ul ori actorul sursei.

## Surse

- Microsoft Desktop Duplication API: <https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/desktop-dup-api>
- Microsoft `CreateForWindow`: <https://learn.microsoft.com/en-us/windows/win32/api/windows.graphics.capture.interop/nf-windows-graphics-capture-interop-igraphicscaptureiteminterop-createforwindow>
- Microsoft ScreenCaptureForHWND sample: <https://github.com/microsoft/Windows.UI.Composition-Win32-Samples/tree/master/cpp/ScreenCaptureforHWND>
- DXcam upstream: <https://github.com/ra1nty/DXcam>
