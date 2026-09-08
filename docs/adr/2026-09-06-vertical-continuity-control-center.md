# Continuitatea candidaților în observerul asincron și Control Center

## Implementat

Opțiunea `--spatial-sonar-continuity` trece din Control Center în bridge și
activează un observator opțional în firul de lucru al sonarului. Implicit
este dezactivată. Nu înlocuiește workerul de mișcare v34 și nu emite input.
Executabilul observațional păstrează hash-ul din ADR-ul serviciului persistent.

Comparația folosește toate alternativele din două observații consecutive,
nu doar nivelul proiectat selectat. Leagă fiecare lot de capture binding,
sesiune, hartă, WorldPack, XY și momentele ambelor poziții. Intervalul trebuie
să fie pozitiv, cel mult 3s; ambele poziții au cel mult 3s vechime, iar
deplasarea orizontală a capetelor este limitată la 64 yd. Nu este filtru de
viteză sau dovadă că actorul a parcurs ruta calculată.

Maximum 16 perechi într-un lot, în ordinea candidaților furnizați, fără
ordonare după presupusa plauzibilitate. Bugetul soft de 0.5s se verifică
între cereri: o cerere deja pornită are timeout propriu 1s, iar închiderea
procesului poate dura suplimentar. Nu pretindem deadline hard de 0.5s.
Restul perechilor este raportat ca neverificat, nu imposibil; listele complete
de candidați sunt păstrate. Enumerarea suprafețelor rămâne neexhaustivă.

Procesul este reutilizat numai în aceeași identitate; se închide la schimbare
și la oprirea observerului. Curățarea opțională este pusă după cererea activă
în același executor, fără acces concurent al UI la pipe-ul de continuitate.
Erorile opționale nu suprimă sonarul de bază; reîncercările au pauză 10s.
Interogarea poate întârzia actualizarea geometrică, dar nu se face pe firul
Tk/captură. Datele expirate nu sunt prezentate ca actuale.

CC prezintă perechile, altitudinile candidate, lungimea funnel, caracterul
complet/incomplet și deplasările proiecțiilor. Revalidează legătura cu raportul
curent și vârsta poziției precedente. O pereche invalidă suprimă numai
prezentarea continuității, nu celelalte detalii ale sonarului. Nu se confirmă
Z/etaj, mers real sau clearance volumetric.

## Dovezi

- 94 teste Python relevante PASS: protocol/parser, integrarea opțională,
  toate perechile, limitele de lot/timp, rebind, date expirate, răspunsuri
  incompatibile, izolarea erorilor și transmiterea opțiunii CC.
- Replay offline cu datele arhivate și geometria clientului real, folosind
  `_query_inner` în executorul sonarului, workerul nativ persistent și
  `sonar_details`: 98s așteaptă precedenta; 99s produce 16 rânduri pentru
  cele 4×4 alternative; 100s produce 4 rânduri pentru cele 4×1 alternative.
  Z observat și etaj rămân null. Ambii workeri s-au închis cu codul 0.
- Dovadă locală ignorată de Git:
  `data/runtime/minimap-wmo-probe/cc-continuity-replay-v1.json`.
  Sursa este explicit `OFFLINE_ARCHIVE_REPLAY_NOT_LIVE`; ceasul arhivei a
  fost folosit doar în replay, niciun fișier de stare live nu a fost scris.

Nu este încă probă vizuală/live a acestei opțiuni în CC. Procesele existente
nu au fost repornite în această etapă; v34, addonul, anti-AFK și credențialele
nu au fost modificate. Testele offline nu închid localizarea verticală.

## Continuare și rollback

Urmează verificarea read-only, delimitată, a opțiunii în CC real, inclusiv
responsivitate și expirare. Apoi legarea continuității de dovezi independente
despre actor, fără alegerea automată a traseului minim sau seed-ului.
Pentru rollback, lansează CC fără `--spatial-sonar-continuity`; nu schimba
executabilul de mișcare. Restul goal-ului (volum, treceri, entități mobile,
navigație filmată) rămâne deschis.
