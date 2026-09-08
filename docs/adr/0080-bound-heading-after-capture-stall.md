# ADR-0080: Limitarea direcției după o întârziere de captură

## Stare

Acceptată — 2026-09-01

## Decizie

`Rogue Predator` nu presupune că RMB a rămas activ cât timp o captură nouă
întârzie. Integrarea direcției folosește cel mult fereastra lease-ului de
`450 ms`, iar trace-ul scrie `MOUSE_HEADING_INTEGRATION_CLAMPED` când poza
vine mai târziu. Un vector de deplasare din minimapă poate corecta direcția
numai dacă se potrivește simultan cu direcția integrată și cu markerul vizibil.

## Motiv

În v48 o pauză de aproximativ șase secunde a făcut direcția calculată să nu
mai descrie inputul real. W/RMB sunt oricum eliberate de watchdog după lease;
folosirea întregii pauze crea o întoarcere imaginară și putea împinge camera
și Predator în partea greșită a criptei.

## Limite

Aceasta este doar o protecție de steering și de cameră. Nu adaugă coordonate
de server, waypoints, combat sau autoritate nouă de input. Dacă poza nu este
proaspătă, watchdog-ul rămâne autoritatea de oprire.
