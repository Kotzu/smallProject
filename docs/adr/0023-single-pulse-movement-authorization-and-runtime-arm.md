# ADR 0023 — Authorization și runtime arm pentru primul puls de mișcare

- Status: accepted
- Date: 2026-08-23
- Extends: ADR 0007, ADR 0013, ADR 0021 și ADR 0022

## Context

PA-024F1 și PA-024F2 au separat policy gateway-ul de adaptorul Windows, dar un
obiect `ExecutionLease` construit de caller nu trebuie să poată crea authority.
Primul gate de mișcare trebuie să fie suficient de mic pentru a demonstra
binding-ul complet fără combat, questing, economie, path loop sau runner
autonom.

## Decizie

PA-024F3a autorizează un singur puls `MOVE_FORWARD` în LAB-ul emulator local:

- maximum `100 ms` hold și `150 ms` start-through-release envelope;
- `max_queue_depth=1` și `max_primitives=1`;
- pose `POSITION_2D` în exact `normalized_current_zone_map`;
- confidence minim `0.9`, radius maxim `2/65535`, yaw absent;
- combat și economy sunt false;
- takeover manual și `release_all` sunt obligatorii.

Profilul versionat din repo este inert: `pending_evidence`, fără modes,
capabilities, movement policy ori approval. Snapshotul aprobat poate fi emis
numai din bytes exact hash-pinned ai template-ului și după acknowledgment-ul
explicit al pulsului unic. Chiar și acel snapshot este insuficient singur.

`MovementRuntimeArm` cere simultan:

1. authorization F3a aprobat, activ și exact hash-pinned;
2. authorization fixed-UI încă activ pentru sesiunea care a produs receipt-ul;
3. `lab_client_launch_receipt` v1.0 non-authority, legat de authorization hash și
   semantic hash;
4. exact PID, HWND, native process FILETIME, Windows session, executable path și
   hash;
5. routing localhost și realm revalidation receipt proaspăt;
6. actor LAB și aceeași identity chain;
7. cauzalitate `authorization/receipt <= revalidation <= arm <= now` și ferestre
   UTC/monotonic consistente;
8. aceeași `ExecutionLeasePolicy` immutable v1.0 în authorization, runtime arm
   și lease.

Gateway-ul acceptă numai un lease egal ori mai strict decât ambele politici.
Compilerul F3a cere egalitate exactă, inclusiv controls, primitive budget,
hold/envelope/queue, confidence, componente, coordinate space, radius, yaw și
issued-at în interiorul armului. Niciun obiect caller-authored nu poate lărgi
authority.

F3a nu promovează profilul HUD la world-navigation. Pentru această singură
probă, coordonatorul acceptă numai profilul HUD v0.2.0 exact hash-pinned, deja
decodat în controlled-live LAB, ca măsurare relativă pre/post în aceeași zonă.
`synthetic_verified` rămâne starea profilului pentru world-map și cross-zone;
schimbarea profilului/hashului, hărții sau zonei refuză pulsul ori rezultatul.

## Identity issuance commit

Receipt-ul v1.0 are un commit separat `lab_client_identity_issuance` pentru
`Launch`, `AdoptSession` și `RenewSessionIdentity`. Markerul immutable este
scris durabil înaintea proiecției receipt-ului și păstrează parent/new receipt
și authorization hashes, PID/HWND/native FILETIME și receipt bytes în base64.
Este recovery/audit evidence, nu authority (`execution_authority=false`).

## Consecințe

- Un lease lărgit este refuzat cu `LEASE_POLICY_DENIED` înainte de sink.
- O politică runtime-arm schimbată ori prea îngustă produce
  `RUNTIME_ARM_POLICY_MISMATCH` înainte de sink.
- Revocarea armului, takeover și release semantics din ADR 0021 rămân
  obligatorii.
- Slice-ul este contract/policy/fake-sink only. Nu include runner, input live,
  client control, combat ori economie.

## Rollback

Profilul repo rămâne inert. Rollback înseamnă neemiterea snapshotului aprobat și
necrearea armului temporar; F1/F2 pot rămâne testate fără a primi authority.
