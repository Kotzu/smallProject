# ADR-0068 — Preplanare asincronă pentru frontieră și recenter

## Context

Holdout-ul Crypt→Brill→Crypt a ajuns la ambele destinații, însă trace-ul
outbound a măsurat două goluri inexplicate: o query sincronă pentru bypass-ul
unei frontiere statice și o replanare de recenter. Relaxarea evaluatorului ar
ascunde o oprire reală și nu este acceptabilă.

## Decizie

Runner-ul poate pregăti în `ProcessPoolExecutor`:

1. celule strict ordonate din ruta semantică, pornind de la frontiera Detour
   deja dovedită;
2. o replanare geometrică timpurie, pornind de la un pose observat înainte de
   pragul `REPLAN`.

Worker-ul creează un query client-navmesh izolat, nu are acces la actuator și
returnează doar coridoare validate. Aplicarea este permisă numai dacă query-ul,
ținta și apropierea față de startul preplanificat sunt încă valide. Rezultatul
expirat, incomplet sau cu context schimbat este anulat, iar calea existentă
rămâne fail-closed.

## Consecințe

- Procesarea JSON/Detour nu mai trebuie să blocheze controlul la frontiera
  cunoscută sau la deviația geometrică timpurie.
- Când coridorul activ este parțial, worker-ul de bypass are prioritate față
  de preplanarea următorului obiectiv; astfel resursele bounded nu se concurează
  exact în fereastra de frontieră.
- Nu se introduc coordonate laterale hardcodate, teleport, shortcut sau
  autoritate live; candidații provin din ruta semantică și navmesh-ul clientului.
- Testul live nu este implicit reluat. Poarta temporală outbound trebuie să
  treacă într-o viitoare sesiune LAB bounded după validare offline.

## Dovezi

- Validator semantic v47: `5/5` rezultate așteptate.
- Regresie completă după implementare: `1325/1325`.
- Holdout live: `ARRIVED` pe ambele leg-uri, zero handoff combat,
  `execution_authority=false`; returul trece quality gate, outbound rămâne
  explicit respins pentru un gol măsurat la frontieră (2.10225 s în v2).

## Amendament — pool dedicat pentru frontieră

După analiza trace-ului v2, worker-ul de bypass pentru frontieră folosește un
`ProcessPoolExecutor` separat, cu un singur worker bounded. Astfel, verificările
WMO și preplanurile obișnuite nu pot pune query-ul de frontieră în coadă. Pool-ul
dedicat este închis explicit în teardown; rezultatul rămâne fail-closed și nu
schimbă autoritatea de execuție.

În interiorul acestui worker, cel mult zece query-uri native read-only sunt
validate concurent pentru un lot bounded de cel mult 32 de candidaturi. Limita
este separată de extensia de opt celule a helper-ului: fereastra inclusivă poate
conține nouă sau mai multe probe când traversează următorul obiectiv coalescat.
Rezultatul este selectat în ordinea candidaturilor, nu în ordinea terminării,
pentru a păstra fallback-ul semantic determinist. Un lot peste 32 este respins
explicit, iar caller-ul păstrează calea existentă fail-closed.

În benchmark-ul offline pe batch-ul frontieră v4 (10 candidaturi), fan-out-ul
4 a durat aproximativ `3.2 s`, iar fan-out-ul 10 aproximativ `1.5 s` pe același
WorldPack pinned. Valoarea rămâne bounded și nu acordă autoritate de execuție.

Dovadă offline: testele Movement Engine/runtime/supervisor `245/245` trec după
amendament. Test live nou nu a fost pornit.

## Amendament — Reutilizare după replan parțial

Trace-ul live v5 a arătat că future-ul pornit de la aceeași frontieră era
anulat la începutul ramurii de replan parțial, înainte de verificarea de
handoff. Runner-ul îl păstrează acum până la acea verificare; numai contextul
stale/incomplet sau schimbarea query-ului îl invalidează, iar fallback-ul
sincron rămâne ultima opțiune fail-closed. Astfel worker-ul nu este anulat
prematur după ce a fost deja planificat în afara buclei de control.

Dovadă: holdout-ul v5 a ajuns la ambele destinații, dar quality gate a rămas
explicit respins pentru trei goluri temporale; după amendament testele dedicate
trec `151/151`, iar regresia completă `1331/1331`. Nu s-a pornit o nouă sesiune
live după această schimbare.

Replanul care ajunge la o frontieră diferită invalidează explicit future-ul
pregătit pentru contextul vechi. Numai aceeași frontieră, același query și
apropierea bounded pot păstra rezultatul pentru handoff; nu există reutilizare
între contexte topologice diferite.
