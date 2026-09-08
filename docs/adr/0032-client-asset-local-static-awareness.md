# ADR 0032 — Awareness static local din geometria clientului

## Status

Acceptat pentru Movement Engine și instrumentarea LAB read-only.

## Context

Coridorul Detour dovedește că o destinație este accesibilă, dar nu descrie
explicit spațiul imediat al actorului. Fără această informație, controllerul nu
poate diferenția robust terenul deschis de un perete apropiat, o trecere WMO sau
un interior îngust. Etichetele legate de Deathknell ori de coordonate ar fi
hardcoding și nu s-ar transfera pe altă hartă sau pe alt server compatibil cu
aceleași asset-uri.

## Decizie

1. Workerul client-asset produce pentru începutul rezolvat al fiecărui coridor
   un `start_awareness` fără execution authority.
2. Snapshotul conține suprafețele fizice ale poligonului (`ground`, `wmo`,
   `doodad`), clearance vertical și 16 probe radiale uniforme pe 360°.
3. Fiecare probă măsoară până la 12 yd. Dacă raza completă este blocată,
   distanța până la coliziune este aproximată bounded prin șapte iterații de
   căutare binară la înălțimea capsulei.
4. Bearingurile folosesc aceeași convenție world-space ca facingul și navmesh-ul:
   zero pe +X, crescând spre +Y. Adaptorul validează ordine strictă, limite
   numerice, număr de probe și schema JSON exactă.
5. Clasificarea `OPEN_GROUND`, `WMO_STRUCTURE_OR_TRANSITION`,
   `CONFINED_STATIC_SPACE` sau `STATIC_TRANSITION` este derivată numai din
   geometria clientului. Nu introduce nume de clădiri sau coordonate speciale.
6. O direcție devine `candidate_opening_bearing` numai dacă raza de coliziune
   este liberă și un raycast Detour confirmă că endpointul de 12 yd rămâne pe
   suprafața navigabilă. Nici această confirmare locală nu transformă direcția
   într-un portal semantic, o ieșire din clădire sau o comandă de mers; acestea
   cer conectivitate/portal și un coridor complet separat.
7. Pentru un start WMO se explorează componenta locală conectată într-o rază
   de 60 yd. Workerul păstrează separat pereții fără vecin Detour și
   `surface_transition_portals`; schimbarea WMO→ground/doodad nu este numită
   automat ieșire, deoarece poate aparține altui etaj sau unui obiect mic.
8. Un `egress_portal` cere simultan: start acoperit, muchie Detour de la un
   poligon acoperit la unul cu clearance vertical liber, continuare navigabilă
   cu plafon liber pentru minimum 4 yd și un coridor Detour complet de la
   poziția actorului. Se raportează atât distanța 2D, cât și distanța reală a
   traseului, iar rezultatele sunt sortate după aceasta din urmă.
9. Inferența este bounded la 2.048 poligoane locale, 512 probe de plafon, 128
   poligoane pentru verificarea continuării și 32 de portaluri raportate.
   `egress_inference_complete` și contoarele de truncare împiedică un rezultat
   parțial să fie prezentat drept hartă completă.
10. Snapshotul descrie numai coliziune statică. Jucătorii, mobii și NPC-urile
   rămân în stratul observat și expirabil al world modelului.

## Consecințe

- Predatorul poate recunoaște generic dacă se află pe teren deschis, într-o
  structură WMO sau într-un spațiu static strâmt.
- Distanțele radiale, pereții și ieșirile verificate pot alimenta costul
  controllerului fără waypoint walking și fără coordonate de clădire scrise
  manual.
- Probe suplimentare sunt bounded la maximum 128 de raze de coliziune pentru o
  interogare și sunt calculate în procesul izolat al workerului.
- Un worker vechi, un câmp absent sau o structură numerică nevalidă este respinsă
  fail-closed de adaptor.

## Verificare

- Testele unitare verifică schema exactă, clasificarea și direcțiile candidate.
- Proba offline pe geometria Deathknell a raportat outdoor `ground`, 16/16 raze
  fără coliziune, 13/16 confirmate și de Detour, plus plafon liber.
- Proba de pe scara criptei a raportat `wmo`, 7/16 raze fără coliziune, 5/16
  confirmate și de Detour, clearance minim aproximativ 0,56 yd și plafon blocat.
- Pe aceeași poziție, 42 tranziții brute de suprafață au fost păstrate ca
  geometrie descriptivă, dar numai 15 muchii acoperit→deschis au trecut proba
  de continuare și coridor complet. Cea mai apropiată ieșire verificată cere
  aproximativ 64,6 yd de traseu și urcă de la Z≈121 la Z≈142; distanța ei 2D
  de aproximativ 15,3 yd nu mai poate fi confundată cu acces direct între etaje.
