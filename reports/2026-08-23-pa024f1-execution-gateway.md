# PA-024F1 — Execution Gateway

- Status: implemented, fake-only verified
- Date: 2026-08-23
- Native input: absent

## Outcome

Perfect Assassin are un singur boundary revocabil între propunerile de mișcare
și un viitor adaptor de input. Contractul breaking v1.0 include `ExecutionLease`,
`MovementPrimitive`, `ExecutionPoseState` și `ExecutionResult`. O primitivă
separă timpul în care tasta trebuie ținută (`hold_duration_ms`) de fereastra
totală care include apăsarea și eliberarea (`max_execution_envelope_ms`). Primul
gate folosește implicit `100 ms / 150 ms`.

Gateway-ul verifică identity/target/authorization/runtime-arm, pose freshness și
uncertainty, sequence/replay, queue/duration și toate expiry-urile. Întreaga
primitivă trebuie să încapă în fereastra temporală rămasă. Rezultatul
`EXECUTED` poate fi publicat numai după `release_all` și revalidarea stării.

Lease-ul declară acum componentele de pose necesare și spațiul poziției, iar
pose-ul declară numai componentele pe care le are efectiv. Gateway-ul verifică
subsetul, egalitatea spațiului de coordonate și doar pragurile componentelor
cerute. F3a este reprezentat fără yaw inventat: `POSITION_2D` în
`normalized_current_zone_map`, `YAW` absent și câmpul său de uncertainty `null`.
Producătorul F3a trebuie să derive uncertainty din cuantizarea pachetului HUD
`uint16`; F1 doar o consumă și nu pretinde adevăr world-map. Navigația cere
separat `POSITION_2D+YAW`.

Authorization, runtime arm și lease sunt acum legate prin același
`ExecutionLeasePolicy` immutable v1.0. Politica acoperă toate controalele și
bugetele, confidence, componentele pose, coordinate space și uncertainty.
Gateway-ul refuză înainte de sink atât un lease lărgit față de authorization,
cât și un runtime arm care nu mai acoperă lease-ul curent.

## Failure and takeover evidence

- manual takeover înainte, în timpul ori imediat înainte de commit câștigă;
- takeover-ul dintre înregistrarea invocation-ului și pornirea workerului nu
  mai poate ajunge la sink;
- revocarea runtime armului întrerupe cooperativ execuția in-flight;
- deadline-ul depășit înainte de worker produce zero apeluri către sink;
- timpul este citit din nou după `release_all`, astfel o eliberare lentă nu
  poate deveni `EXECUTED`;
- un watchdog gateway-owned anulează și execută `release_all` chiar dacă sink-ul
  ignoră deadline-ul;
- dacă un sink defect revine după timeout, workerul urmărit execută încă o
  eliberare finală; contractul interzice input work detașat și nu pretinde
  hard-kill de thread;
- numai o singură primitivă poate fi in-flight, iar `execute(p)` nu poate
  consuma o altă primitivă deja aflată în coadă;
- `OSError` și excepțiile custom de apply/release sunt conținute și normalizate;
- un sink fără cancellation/deadline contract este refuzat;
- recordurile raw contradictorii sunt refuzate de schema și validatorul semantic.
- un lease construit manual cu control, primitive, hold, envelope, queue,
  confidence, componente, coordinate space ori uncertainty lărgite este refuzat
  înainte de `FakeInputSink`;
- politica revocabilă a runtime armului este recitită la fiecare session gate.

## Evidence

- Execution Gateway: `54/54 PASS`;
- F1 + F2 + F3a movement arm + authorization policy: `110/110 PASS`;
- probe concurente/race/watchdog: `600/600 PASS` în 100 de repetări ale celor
  șase cazuri deterministe;
- review independent: CLEAN pentru cele trei ferestre temporale reproduse;
- Python compile și `git diff --check`: PASS;
- toate testele folosesc `FakeInputSink`;
- nu a existat input live, import server ori control al clientului.

Acest gate dovedește policy/authority/revocation, nu mișcare reală.
Contractul respinge explicit recordurile legacy `0.1`; cross-map/world și orice
delta între contexte continent/zone/map diferite rămân în afara autorității F1.
