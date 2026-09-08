# ADR-0108: Checkpoint terminal când preflight-ul respinge controlul

## Context

Runner-ul publică un checkpoint de continuitate înainte de bucla de mișcare.
Când observația live nu are actor vizibil, heading curent, latență validă sau
focus verificat, bucla este sărită. Un checkpoint `RUNNING` în acel moment ar
induce în eroare supervisorul și operatorul.

## Decizie

După preflight:

- `RUNNING` se publică numai dacă preflight-ul este `READY` și nu există o
  respingere de reset/search-vantage;
- `LIVE_PREFLIGHT_REJECTED` se publică atunci când preflight-ul este respins;
- `RESET_REQUIRED` și `SEARCH_VANTAGE_REJECTED` își păstrează prioritatea.

Acest checkpoint descrie starea de observare, nu acordă autoritate. Arm-ul
F4a rămâne nelegat când preflight-ul este respins.

## Consecințe

Operatorul vede imediat că jobul nu poate apăsa taste, iar supervisorul nu mai
interpretează o stare aparent activă ca progres de mișcare. Schimbarea este
offline și nu schimbă ruta sau limitele de input.
