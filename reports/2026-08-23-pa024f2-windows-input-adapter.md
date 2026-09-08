# PA-024F2 — Windows scan-code input adapter

- Status: implemented, fake-only verified
- Date: 2026-08-23
- Live input: absent

## Outcome

Adaptorul user-mode Windows este implementat în spatele portului F1. Core-ul
nu importă API-uri native; boundary-ul `ctypes` este izolat în `integrations/`.
Nu există runner, authorization live ori apel asupra clientului.

## Garanții verificate

- target exact: PID, HWND, process creation time, path/hash, title/class,
  foreground, visibility și liveness;
- receipt cold-path separat de verificările hot-path fără hashing;
- allowlist v1 exact W/S/Q/E/A/D/Space și refuz pre-mapping pentru extended keys;
- succes `SendInput` numai pentru `int(1)`, în ambele direcții;
- ownership pentru fiecare key-down și key-up de urgență la focus loss,
  cancellation ori clock failure;
- revocare linearizată înaintea validării lente, înainte de key-down și la tail;
- hold măsurat separat de envelope, fără rezervă ascunsă;
- bugetul consumat de hot checks este reverificat imediat pre-down și produce
  zero evenimente dacă nu mai încape hold-ul plus slack-ul.
- clientul legacy încearcă întâi
  `PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE`; fallback-ul
  `PROCESS_QUERY_INFORMATION | SYNCHRONIZE` este permis numai după
  `ERROR_ACCESS_DENIED`, fără niciun drept VM.

## Evidence

- F2: `25/25 PASS`;
- F1 + F2 + architecture: `75/75 PASS`;
- review independent: CLEAN pentru late-budget și extended-key probes;
- review independent legacy: CLEAN; verificarea read-only pe clientul deschis a
  confirmat PID/HWND/path/SHA-256/creation time/class/title/liveness exacte,
  fallback-ul strict după eroarea `5`, `100` cicluri fără handle leak și zero
  apeluri `SendInput`;
- compile și `git diff --check`: PASS;
- input live/client control: zero.

Acest gate dovedește transportul și cleanup-ul, nu displacement ori navigație.
