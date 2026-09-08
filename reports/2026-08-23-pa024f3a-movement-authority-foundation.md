# PA-024F3a — Single-pulse movement authority foundation

- Status: implemented; contract/policy/fake-sink verified; controlled-live gate PASS on 2026-08-24
- Date: 2026-08-23

## Coordinator fake-first

`SingleForwardPulseCoordinator` compune acum poarta completă fără input nativ:

- validează schema și semantica HUD v2 înainte de orice execuție;
- cere exact actorul, instanța, profilul și hash-ul autorizației din arm;
- compilează exact un `MOVE_FORWARD`, 100 ms hold / 150 ms envelope;
- cere un frame și o secvență HUD distincte, capturate după terminarea execuției;
- refuză schimbarea de sesiune, actor, autorizație, continent sau zonă;
- declară `PROVEN_DISPLACEMENT` numai dacă distanța depășește suma razelor de cuantizare 95%;
- dezarmează și închide gateway-ul în toate ieșirile.

Contractul [single-forward-pulse-result.schema.json](../contracts/single-forward-pulse-result.schema.json)
este non-authority și are validator semantic separat pentru relațiile care nu pot fi
exprimate complet prin JSON Schema.

Runner-ul Windows este compus și a trecut primul gate live pe 2026-08-24: autorizație temporară,
revalidare exactă de realm fără input, arm de maximum 30 s, captură HUD pre/post,
adaptor scan-code și `Pause` prin `RegisterHotKey` (fără hook) pentru preluare
manuală. Arm-ul este eliminat în `finally`.

Verificarea integrată pre-live: **425/425 PASS**. Dovada live exactă este
separată în [raportul first proven displacement](2026-08-24-pa024f3a-first-proven-displacement.md).
- Live input: exact un puls `MOVE_FORWARD` 100/150 ms, `PROVEN_DISPLACEMENT`;
- cleanup: arm disarmed, gateway closed, release clean, character kept in-world.

## Outcome

F3a poate reprezenta fail-closed authority pentru exact un puls
`MOVE_FORWARD`, fără a acorda combat, economy sau un loop autonom. Profilul
versionat rămâne `pending_evidence`; issuerul pur cere template-ul repo
hash-pinned și acknowledgment explicit, iar authorization singură nu poate
porni input.

Runtime armul este legat de authorization, receipt v1.0, identity chain,
PID/HWND/native process FILETIME, executable, actor LAB, routing localhost și
realm revalidation. Causalitatea UTC și monotonică, elapsed/remaining și
expiry-urile sunt validate fail-closed.

## Policy binding

`ExecutionLeasePolicy` v1.0 este purtat separat de authorization și runtime arm,
iar lease-ul își proiectează complet politica. Gateway-ul verifică subsetul față
de authorization la inițializare/session și recitește politica runtime armului
înainte de fiecare sink call. F3a cere exact:

- control `MOVE_FORWARD`;
- `max_primitives=1`, `max_queue_depth=1`;
- hold/envelope `100/150 ms`;
- confidence `0.9`;
- `POSITION_2D` în `normalized_current_zone_map`;
- radius `2/65535`, fără yaw.

Probe adversariale modifică individual controls, primitive count,
hold/envelope/queue, confidence, componentele pose, coordinate space, radius,
yaw și issued-at. Compilerul le respinge; bypass-ul direct prin gateway este
respins de authorization sau runtime arm înainte de `FakeInputSink`.

## Evidence

- Execution Gateway: `54/54 PASS`;
- Windows input adapter fake/native-ABI fixtures: `25/25 PASS`;
- Movement authorization/runtime arm: `16/16 PASS`;
- Execution policy profiles: `15/15 PASS`;
- combined focused suite: `110/110 PASS`;
- Python compile, JSON parse și `git diff --check`: PASS;
- zero client launch/control, zero native input și zero server DB access.

## Boundary și pasul următor

Acest rezultat dovedește contractele, authority chain și gateway binding. Nu
dovedește displacement real. Un viitor runner controlat trebuie să emită
receipt/revalidation/arm proaspete, să obțină pose înainte și după, să păstreze
takeover instant și să ruleze separat sub un gate explicit; nu este inclus aici.
