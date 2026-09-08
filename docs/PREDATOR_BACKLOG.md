# Predator — lista de lucru consolidată
Actualizat: 2026-09-07. Prioritatea activă: Shadow Grave → scară → ieșire.

## Ce reprezintă lista

Consolidează cererile din conversația curentă, analiza inițială recuperată din
„Restructurare proiect AI Wow” și starea verificată în cod/documentele de probe.
Nu declară recitite integral în această etapă jurnalele de mai mulți GB ale
celor doi agenți. Handoff-urile și probele lor rămân surse istorice, nu dovada
că fiecare funcție merge în versiunea curentă.

„Parțial” = există implementare, dar cerința completă nu este acceptată.
„De validat” = există mecanism/probă limitată, lipsește demonstrația cerută.
„De construit” = lipsește livrarea completă cerută; pot exista piese reutilizabile.
„De verificat” = nu avem suficiente dovezi pentru a declara funcția absentă.
C = cerere a operatorului; R = recomandare de implementare/acceptare.
Toate bifele deschise de mai jos reprezintă lucru rămas, nu funcții pretins inexistente.

## Ce NU reconstruim

- WorldPack/navmesh, graful de acces și navigatorul v34 există.
- Controllerul cu feedback, anticiparea curbelor și recuperări există.
- Nume zonă/subzonă din API, transportul addon și fallback-ul vizual există.
- Sonarul asincron, 64 raze la patru înălțimi, niveluri alternative și tabul Sonar există.
- CC are hartă adaptivă, urmărirea poziției și control manual separat.
- Anti-AFK are bifa verificată în CC, un Space per episod confirmat și limită de sesiune.
- Există launcher/operator LAB, cod de combat PvE și module de căutare.
Acestea nu echivalează cu localizare completă, humanlike sau hunting PvP funcțional.

## A. Cripta — prioritate activă; nu trecem la alte medii înainte de acceptare

- [ ] C01 — C, Parțial: ieșire naturală din startul canonic, fără împins în zid,
  oscilații stânga/dreapta, pivotări ori opriri nejustificate.
  Acceptare: film complet și jurnal, nu numai ARRIVED.
- [ ] C02 — C/R, De validat: cronometrare corectă spawn–ieșire completă.
  Separăm click→prima mișcare, parcurgere, ieșire și drumul exterior.
  Referința operatorului este maximum 10 s, nu încă un benchmark sincronizat.
  Comparăm același start, final, viteză și condiții; nu folosim speed cheats.
- [ ] C03 — R, Parțial: verificare integrată traseu netezit → follower → corp în viraj.
  Măsurăm separat traseul prea apropiat de zid și abaterea de urmărire.
  Sonde radiale sau o linie validă nu certifică întregul volum parcurs.
  Nou: evaluator continuu capsulă–triunghiuri și adaptor WMO, offline,
  153 teste relevante PASS; 32 segmente reale înregistrate evaluate.
  Integrarea mers/CC, Z independent și corpul calibrat rămân de făcut.
- [ ] C04 — C/R, Parțial: colțurile și scara fără tăierea colțului, fără salt
  nejustificat între suprafețe. Testul acoperă și apropierea de scară, nu numai
  punctul modificat. Candidatul geometric respins nu se reactivează.
- [ ] C05 — C, De validat: corp, facing și cameră coerente în spațiu îngust;
  perspectivă utilizabilă, fără salturi și fără a confunda pitch cu yaw.
  Nu ajustăm camera ca să ascundem un defect de traseu.
- [ ] C06 — R, Parțial: recuperare bazată pe cauză. Separăm zidul, lipsa
  observației, lipsa controlului și aggro; fără „sari și virează” automat.
  Verificăm în special viteza estimată când poziția nu mai progresează.
- [ ] C07 — C/R, De validat: repetabilitate, apoi porniri/orientări diferite
  în aceeași criptă și cazul masă/sub scară ME503.
  Propunere de acceptare: 5 repetări canonice + 3 porniri diferite, toate filmate;
  numărul este criteriu propus, nu o garanție de succes universal.
- [ ] C08 — C/R, De verificat: pornirea lentă observată istoric (~70 s).
  Profilăm etapele și optimizăm doar costul demonstrat. Nu scurtăm verificările
  de identitate/autorizație și nu confundăm preflight-ul cu timpul mersului.
- [ ] C09 — R, De validat: probă filmată după corecția XYZ a cache-ului de traseu,
  fără alte schimbări în planner/cameră. Verificarea offline este deja trecută;
  schimbarea nu certifică etajul actorului și nu rezolvă singură C01.
  Actualizare: proba 42a590bb este filmată și oprită controlat, 255 cadre,
  zero recuperări. Ieșire vizibilă aproximativ 11–12 s, camera încă neacceptată.
  C09 rămâne deschis pentru evaluare/acceptare, nu pentru lipsa filmului.
  Detalii: LIVE_CRYPT_C09_2026-09-07.md.

Următoarea activitate: C03/C04/C05, sprijinul și suprafața din cadrele 83–87
ale primului palier. Evaluatorul de volum a identificat sensibilitate la Z:
separare estimată 0.181 yd, dar −0.043 yd dacă Z este cu 0.25 yd mai jos.
Nu este dovadă de contact real; Z proiectat și dimensiunile corpului sunt
ipoteze. Nu punem evaluatorul offline (~156 ms/segment) în firul CC/mers.
Detalii: adr/2026-09-07-continuous-body-volume-evaluator.md.
Replay-ul ebd340cd este exact pe 140 cadre. Candidatul de rotire 8aa5af8 a
fost filmat (59fe4963), dar nepromovat: abatere interioară 2.161→1.981 yd,
schimbări de semn 7→9, fără câștig de timp. Controllerul anterior este restaurat.
Nu reintroducem candidații respinși și nu ajustăm succesiv plafoane fără dovadă
de spațiu traversabil. Detalii: adr/2026-09-07-geometric-turn-budget-trial.md.
Cronometrarea a identificat rezumatul memoriei dinamice ca sursă de latență;
indexarea corectată a redus maximul etapei live 307.8 → 10.635 ms.
Zero cicluri peste 200 ms după fix, față de 9 înainte. 344 teste relevante PASS.
Abaterea maximă globală de traseu nu s-a îmbunătățit: 2.807 → 2.995 yd.
Maximul 2.995 apare la handoff; maximul segmentului interior ebd340cd este
2.161 yd. Nu confundăm cele două și nu le tratăm ca dovezi de contact fizic.
Prin urmare latența este optimizată, humanlike și camera rămân neacceptate.
Dacă filmarea ori autorizarea nu funcționează, rezolvăm acel blocaj explicit,
nu îl înlocuim cu alte funcții și nu declarăm o probă nefilmată drept acceptată.

## B. Localizare și sonar — rezolvăm în criptă ce este necesar, apoi generalizăm

- [ ] L01 — C, Parțial: Z/suprafață/etaj susținute de dovezi independente.
  Păstrăm alternativele când XY coincide; numele subzonei și proiecția navmesh
  nu aleg singure etajul. Tranziții scară, interior/exterior, pod/sub pod.
- [ ] L02 — C, Parțial: facing al corpului separat de cameră, cu sursă și eroare.
  API prioritar; clientul TBC testat nu expune UnitPosition/GetPlayerFacing.
  API-ul propriu normalizează dovezile disponibile, nu inventează acces nou.
- [ ] L03 — C/R, Parțial: eroare metrică și încredere calibrate cu date reale;
  conflicte API/viziune, teleport, login/loading și observații expirate.
  Nu alegem valori mici arbitrar pentru ca testele să treacă.
- [ ] L04 — C/R, Parțial: calibrare vizuală robustă, când API-ul nu ajunge.
  Repere independente pentru verificare; seturile deja respinse nu se refolosesc
  cu praguri relaxate. Poziția proiectată nu devine adevăr de calibrare.
- [ ] S01 — C, Parțial: distanțe de la corp la ziduri/obstacole și spațiu sigur
  la mai multe înălțimi. Dimensiunile personajului, marja și timpul de reacție
  intră în verificare; golurile dintre raze nu sunt implicit libere.
- [ ] S02 — C, Parțial: descriere geometrică a spațiului: contur, laturi,
  orientări, suprafață aproximativă și unități explicite. Nu presupunem patru
  pereți în orice încăpere; dimensiunile necunoscute rămân necunoscute.
- [ ] S03 — C, Parțial: intrări/ieșiri cu lățime, înălțime, pantă/trepte,
  conexiune la spațiul următor și volum traversabil. Scară/ușă/poartă/gaură
  se etichetează numai cu dovezi; navmesh conectat nu certifică ușa deschisă.
- [ ] S04 — C, Parțial: verticalitate în exterior. Diferențiem altitudinea,
  nivelul local și plafonul; plafon nedetectat nu înseamnă infinit.
- [ ] S05 — C/R, Parțial: extindere a geometriei/semanticii la alte structuri,
  teren și obstacole statice: copaci, pietre, ziduri, ruine, poduri.
  Acoperirea WMO curentă este parțială; fiecare asset/client trebuie verificat.
- [ ] S06 — C/R, Parțial: sonar → decizie de mișcare, nu doar afișare.
  Numai date din aceeași sesiune/hartă și suficient de proaspete; reacție sigură
  când nivelul, geometria sau trecerea nu sunt determinate.

## C. Control Center și operare — îmbunătățim ce ajută probele, nu cosmetizare paralelă

- [ ] U01 — C, Parțial: vedere clară „unde sunt / ce știu / ce estimez /
  de ce mă opresc”, cu nivel, distanțe, traseu propus versus parcurs și vechime.
- [ ] U02 — C/R, De validat: responsivitate în mers, la redimensionare,
  schimbarea hărții, date lipsă și sesiuni lungi. Testele staționare nu ajung.
- [ ] U03 — C, De construit: alegerea unei zone de roaming și limitele ei,
  cu stare/motiv vizibil și Stop sigur. Selectorul unei destinații nu este
  încă întregul flux „roam în Stranglethorn”.
- [ ] U04 — C/R, De validat: operare fără utilizator acasă: launcher → login →
  personaj → world, reconectare și checkpoint-uri. Refolosim mecanismele locale;
  nu declarăm tot lanțul autonom doar pentru că există un script.
  Credentialele rămân locale, excluse din Git și din rapoarte.
- [ ] U05 — C/R, De validat: Anti-AFK pe durată lungă și arbitraj comun cu
  mers/combat/control manual. Testăm că nu apar comenzi concurente; existența
  verificării de procese nu echivalează cu un mecanism atomic de exclusivitate.
  Godmode rămâne setup explicit pentru LAB, nu percepție sau combat realist.

## D. Generalizare și roaming — după acceptarea criptei

- [ ] W01 — C, De validat: aceeași logică în alt interior/scară, apoi pod,
  pantă, drum și exterior; fără coordonate/viraje hardcodate.
- [ ] W02 — C, Parțial: obiective accesibile generate automat în zona aleasă,
  fără waypoint-uri manuale. Evităm buclele și repetarea excesivă a acelorași locuri.
- [ ] W03 — C/R, Parțial: cost de deplasare, noutate, vizite recente, riscuri
  și zone neexplorate în alegerea următoarei destinații.
- [ ] W04 — C/R, Parțial: destinație inaccesibilă, conexiune parțială, lipsa
  datelor hărții și schimbarea obiectivului în mers; recuperare delimitată.
- [ ] W05 — C, Parțial: obstacole mobile observate prin surse permise:
  poziție/direcție/incertitudine/expirare. Separăm blocajul fizic de riscul de
  aggro și de ținta de urmărit; nu pretindem entități ascunse observate.
- [ ] W06 — R, De validat: coordonarea traseului global cu evitarea locală,
  anularea comenzilor vechi și revenirea la obiectiv după ocolire.

## E. Predator Rogue și evenimentul — ulterior; fără modificări combat în etapa criptei

- [ ] H01 — C, De construit: ciclu complet roam → observă → selectează ținta →
  apropiere stealth → luptă → regrupare, numai din informații permise.
  Module de căutare și combat există; nu le rescriem de la zero.
- [ ] H02 — C, De construit: politică explicită pentru participanții evenimentului
  și ținte player în LAB autorizat. Combatul PvE actual respinge player targets;
  nu eliminăm acea protecție global și nu confundăm PvE cu hunting PvP.
- [ ] H03 — C, Parțial: Rogue cu range/facing/LoS, energie, combo points,
  cooldown-uri, control, defensivă și decizie de retragere, validate per client.
- [ ] H04 — C/R, De construit: pierderea țintei, ultima poziție observată,
  căutarea la ieșiri accesibile și abandon justificat; fără urmărire omniscientă.
- [ ] H05 — C, De construit: ciclul evenimentului: zonă, participanți, înfrângerea
  Predatorului, reset și dovada rezultatului. Recompensa gold rămâne manuală
  de pe main, cum a cerut operatorul; automatizarea plății cere o cerere separată.
- [ ] H06 — C/R, De validat: humanlike comparat cu demonstrații umane:
  traiectorie, rotire, opriri și comportament, nu zgomot aleatoriu.
  Demonstrația este referință, nu traseu executabil memorat.

## F. Portare și protejarea progresului

- [ ] P01 — C, Parțial: matrice de capabilități și adaptor pentru al doilea
  client/expansiune: observații, geometrie, unități, mecanici și control.
  Nucleu comun, nu presupunere că TBC validează orice client.
- [ ] P02 — C/R, De validat: aceleași teste de acceptare pe al doilea mediu.
  Targeturile publice rămân refuzate de profilurile actuale; nu extindem
  utilizarea autonomă la Anniversary doar prin acordul guildului.
- [ ] R01 — R, Parțial: pachet de referință cod + config + hash-uri assets/
  executabile + film + rezultate. v34 rămâne reper de revenire, nu certificat humanlike.
- [ ] R02 — C/R, Parțial: regresii păstrate per defect, inclusiv primul input,
  colțuri, scări, cache XYZ, pierderea observației și procesul exact de control.
- [ ] R03 — C/R, Parțial: un singur backlog actual și handoff scurt cu
  următorul pas; istoricul păstrat separat. Nu copiem stări vechi ca „actuale”.
- [ ] R04 — R, De validat: promovare numai după probe repetate și condiții
  nefolosite la reglaj. Refactorizarea, funcțiile noi și schimbările de control
  rămân separate; păstrăm oprirea și rollback-ul verificabile.

## Upgrade început acum

Optimizare nouă, confirmată în probă filmată: index de acoperire pentru
rezumatul memoriei dinamice. Aceeași interogare pe copia bazei reale:
214.94 → 0.55 ms median, aceleași date; etapa live maximă 307.8 → 10.635 ms.
Nu am șters amintiri, nu am relaxat validările și nu am modificat v34.
Separat, citirea inaccesibilă a comenzii Stop este tratată ca oprire controlată
cu raport; prima probă a expus problema, repetarea s-a încheiat corect.
Cod: 7fe2ea1 + bd3f37e; 344 teste relevante PASS, film ebd340cd cu
298 cadre/294 forward/zero recuperări. Filmul confirmă ieșirea, nu C01/C05/C07.
Detalii: adr/2026-09-07-dynamic-summary-covering-index.md și
adr/2026-09-07-unreadable-operator-control-stop.md.

Corectat cache-ul geometric al controllerului: identitatea traseului include
XYZ, nu doar XY. Reproducere înainte de fix în ambele controllere, apoi teste
pentru planuri suprapuse, rampă intermediară și schimbare dus/întors. 302 teste
relevante PASS; replay v34 al primelor 80 de cadre din criptă are eroare 0.
Asta repară consistența planului, nu observă Z real și nu certifică C01/C09.
Ulterior: proba C09 filmată a ieșit, cu oprire deliberată după 18 s de la
prima publicare proaspătă; C01/C05/C07 rămân neacceptate. Nu atribuim
diferența de timp fixului XYZ fără o comparație controlată.

## Dovezi și reguli de lucru

Surse în repository: CURRENT_MOVEMENT_STATUS.md, SPATIAL_AWARENESS_PLAN.md,
LIVE_CRYPT_DIAGNOSTIC_2026-09-06.md, LIVE_CORNER_CANDIDATE_REJECTION_2026-09-06.md,
ADR-urile legate din ele; codurile predictive_steering.py, brain/combat.py,
brain/hunting.py și modulele CC/sonar. Analiza inițială este recomandare, nu
constatare retrospectivă despre cei doi agenți.

Nu promitem 100% world awareness sau succes în orice condiție. Protejăm
progresul prin dovezi și limite explicite. Fără memory reading/injecție,
server truth în Brain, credențiale în Git ori ocolirea armării.
Nu consumăm usage pe audituri repetate fără o întrebare concretă și nu pornim
subagenți pentru această listă. Actualizăm itemul lucrat cu cod, test, limită
și următoarea probă; nu bifăm o categorie fiindcă există un modul cu acel nume.
