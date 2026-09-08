# Continuitate în CC real: publicare mai rapidă, praguri de prospețime păstrate

## Problemă confirmată

Opțiunea a fost activată în Control Center real, prin repornirea numai a CC,
cu WMO păstrat. Predator a rămas staționar în Deathknell; mersul oprit,
controlul manual Codex dezactivat. Nu s-a trimis input către WoW.

Verificarea vizuală a găsit comparația alternativ afișată și expirată.
În bridge, apelul `sonar_observer.poll` era în blocul de diagnostic publicat
o dată pe secundă. Colectarea rezultatului gata și publicarea lui puteau
întârzia cu încă un ciclu. În proba de 15s/30 mostre, 19 prezentau comparația,
11 o respingeau corect pentru vechimea poziției precedente peste 3s.
Raportul bridge avea vechime maximă 1.163s; 13 poziții de interogare distincte
temporal. Nu erau erori ale workerului și XY era neschimbat.

## Modificare și verificare

Numai cu `--spatial-sonar-continuity`, publicarea/poll-ul diagnosticului LIVE
are prag 0.2s în loc de 1s. Restul modurilor rămân la 1s. Acesta este pragul
de programare, nu garanție hard de 5Hz. Sonarul păstrează separat limita de
o interogare geometrică pe secundă și un singur job activ. Nu mărim pragul
de vechime și nu reciclăm observații vechi drept noi.

După aceeași repornire delimitată a CC, proba repetată de 15s/30 mostre:

- 30/30 mostre cu comparație validă, zero erori sonar;
- 14 poziții de interogare distincte temporal, nu 30 interogări native;
- vechime maximă a raportului bridge 0.324s;
- XY neschimbat, Z observat și etaj null;
- candidat 98.47 yd proiectat cu aproximativ 0.40 yd la origine 98.88 yd,
  afișat explicit; lungime zero pentru poziția staționară, nu etaj confirmat.

Dovezi locale ignorate de Git: `data/runtime/minimap-wmo-probe/cc-continuity-live-v1.json`
și `cc-continuity-live-v2.json`. Sunt mostre live citite fără input, distincte
de replay-ul anterior. Verificare vizuală prin Computer Use: filele Mers și
Sonar, trecerea între ele, redimensionare/maximizare și starea expirată.
După ultima repornire, fila Sonar afișează comparația proaspătă; motor oprit.
Nu este un benchmark general al UI sau o probă cu niveluri suprapuse live.

Testele verifică păstrarea ritmului geometric independent de publicare.
67 teste relevante pentru tranziții/sonar/prezentare PASS înainte de instalare.
Încă 16 teste existente `live_viewer` PASS. Hash-ul v34 reverificat:
`cb3555065c56a40c45c73d929a89bda6f8237fe5ffa2e018fce50fac84821d3d`.

## Stare runtime și rollback

La verificare: CC PID 41208 (wrapper 41756), WoW 10756, anti-AFK 28956,
același client și aceeași poziție. PID-urile sunt repere istorice, nu identități
de reutilizat fără verificare. Addonul și credențialele nu au fost modificate.
Navigatorul v34 rămâne același executabil; nu s-a folosit noul worker ca
navigator. Pentru rollback, pornește CC fără `--spatial-sonar-continuity`.

## Următorul pas

Integrarea de continuitate este verificată staționar, inclusiv expirarea.
Localizarea verticală reală rămâne deschisă: trebuie dovezi independente
despre actor la suprafețe suprapuse, nu alegerea traseului cel mai scurt.
Continuă cu această legătură, apoi cu volumul traversabil/trecerile și
obstacolele mobile din plan; nu repeta alte audituri de latență fără un defect.
