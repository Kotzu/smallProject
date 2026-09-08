# ADR-0116: Facing exact înaintea navigației lansate de supervisor

## Status

Accepted — 2026-09-03

## Context

Un heading calculat din cameră, minimapă sau deplasare poate fi util ca
diagnostic, dar nu dovedește unde arată corpul Predatorului. Dacă este folosit
pentru mers, o eroare de orientare poate produce abatere sau wall-slide înainte
ca problema să fie observată.

## Decision

Modul normal lansat de `run_journey_combat_supervisor.py` și
`run_reviewed_journey_route.py` cere `--require-exact-body-heading`. Runnerul
reverifică body yaw-ul HUD și headingul controllerului înaintea fiecărui nou
cadru de mișcare; o lipsă sau o abatere peste `0,02 rad` eliberează inputul și
închide felia cu `EXACT_BODY_HEADING_LOST`. Fallback-urile rămân disponibile
doar pentru diagnostic/rollback explicit, nu pentru calea normală.

## Consequences

- Facingul este poarta întâi pentru mers și pentru orice extindere viitoare de
  combat.
- O captură legacy fără facing exact se oprește în siguranță, nu ghicește.
- Dovada este offline și fail-closed; nu acordă autoritate live și nu folosește
  server truth.
