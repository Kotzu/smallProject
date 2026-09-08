# ADR 0022 — Adaptor Windows scan-code izolat

- Status: accepted
- Date: 2026-08-23
- Extends: ADR 0013 și ADR 0021

## Context

Execution Gateway are nevoie de un sink user-mode care transformă numai
primitive autorizate în taste, fără să primească obiective, tactică sau acces la
memoria clientului. O implementare sigură trebuie să păstreze identitatea exactă
a ferestrei și să garanteze key-up inclusiv la focus loss, revocare ori eroare.

## Decizie

`WindowsSendInputSink` este core-ul pur injectabil. Singurul boundary care
importă `ctypes` este `integrations/windows-input/send_input_backend.py`.
Transportul v1 folosește `SendInput` cu `KEYEVENTF_SCANCODE` și numai allowlist-ul
exact W/S/Q/E/A/D/Space. Tastele extended și mapările configurabile sunt refuzate
până când E0/E1 devin parte explicită a contractului.

Cold path-ul verifică PID, HWND, creation time, path, SHA-256, class, title,
foreground, visibility și liveness, apoi păstrează un receipt imuabil. Hot
path-ul verifică numai HWND/PID/creation time/foreground/visibility/liveness;
nu recitește fișierul și nu ține state lock pe hashing.

Fiecare generație de input este înregistrată înaintea validărilor care pot
bloca. Chiar înainte de key-down se verifică din nou că mai rămâne cel puțin
`hold_duration_ms + MIN_EXECUTION_SLACK_MS` în envelope. Key-down-ul acceptat
devine owned, iar key-up-ul este încercat inclusiv când ceasul sau verificarea
de focus eșuează. `release_all` este concurent, idempotent și revocă generația.

## Boundary de proces

Backend-ul încearcă mai întâi un handle metadata/liveness cu
`PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE`. Numai dacă Windows răspunde
exact cu `ERROR_ACCESS_DENIED`, necesarul de compatibilitate pentru clientul
legacy 2.4.3 permite fallback la
`PROCESS_QUERY_INFORMATION | SYNCHRONIZE`. Nu cere drepturi VM, nu citește
memoria procesului, refuză fallback-ul pentru orice altă eroare și închide
handle-ul când receipt-ul este eliberat.

## Limite curente

PA-024F2 nu are runner și nu a trimis input live. Nu acordă authorization,
runtime arm sau focus. PA-024F3a va compune separat target authorization,
runtime arm, fresh pose și takeover înaintea unui singur hold de `100 ms`.

## Consecințe

- F2 rămâne un adapter extern; Brain și Movement nu importă `ctypes`;
- fixed-UI operator și movement authorization rămân capabilități separate;
- mouse/camera, multiple keys și extended keys cer gates și contracte ulterioare;
- un rezultat `SendInput` este succes numai dacă are tipul exact `int` și
  valoarea `1`; `bool` sau `float` sunt refuzate.
