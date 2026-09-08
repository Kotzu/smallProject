# Cache de traseu: XY identic nu identifică același nivel

## Defect reprodus și corecție

PredictiveSteeringController._reset_for_corridor identifica traseul doar prin
XY. După un plan nou cu aceleași XY și Z diferite, cache-ul guidance_points și
proiecția moștenită păstrau înălțimile vechi. ContinuousTrajectoryFollower își
actualiza propria semnătură XYZ, dar folosea în continuare acest cache din bază.

Testele adăugate înainte de modificare au eșuat pentru ambele controllere:
planul de la Z=25 producea proiecție/lookahead Z=10. A eșuat și schimbarea unui
punct interior într-o rampă, fără mutarea capetelor, precum și schimbarea dus/întors.
Identitatea include acum XYZ pentru fiecare punct de ghidaj. Nu se schimbă
pragurile, viteza, camera, plannerul nativ, protocoalele sau armarea. Istoricul
actuatorului rămâne păstrat de logica existentă la înlocuirea coridorului.

## Dovezi și limite

- Cinci teste noi: straturi suprapuse în ambele controllere, rampă, dus/întors,
  geometrie egală și comparația cu un controller nou. Reproducere roșie înainte
  de fix, verde după fix.
- 255 teste movement_engine și 17 steering* (incluzând cele cinci noi) PASS.
- Încă 30 teste adaptive steering, MPPI, timing și replay egress PASS; total 302.
- Reinterogare reală cu v34, replay al primelor 80 de cadre din proba 8544bb3c:
  eroare geometrică maximă 0. Raport local ignorat:
  data/runtime/operator/crypt-xyz-cache-replay-20260907.json.
- SHA256 v34 neschimbat:
  cb3555065c56a40c45c73d929a89bda6f8237fe5ffa2e018fce50fac84821d3d.

Acesta este un defect demonstrat al consistenței planului. Nu este demonstrat
că a cauzat contactul cu zidul în filmarea criptei. Nu confirmă Z-ul actorului,
nu rezolvă selecția etajului și nu certifică humanlike. Replay-ul verifică
geometria pe observații arhivate, nu toate comenzile și nu fizica jocului.
Nu s-a pornit o probă de navigație live în această etapă.

## Următorul pas și rollback

PREDATOR_BACKLOG.md C09 cere proba filmată delimitată în criptă, fără o a doua
modificare simultană. Executabilele și datele native nu se înlocuiesc. Schimbarea
Python rămâne candidată pentru acceptarea live; revenirea înseamnă retragerea
doar a celor două modificări ale semnăturii din predictive_steering.py față de
baza e5a20b4. Testul de regresie se păstrează ca defect cunoscut, nu se relaxează.
