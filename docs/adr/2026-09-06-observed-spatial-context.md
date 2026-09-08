# Context spațial observat, fără citirea memoriei clientului

Status: nucleu de diagnostic offline implementat și testat; neconectat la
runtime sau Control Center. Nicio schimbare a comenzilor, camerei, workerilor,
autorizărilor ori navmesh-ului. Nu este corecția controllerului și nu închide
FAIL-ul auditului anterior de clearance.

## Ce există deja, verificat în cod

- `pose/fusion.py` combină observații cu incertitudine și prospețime, separă
  corpul de cameră și respinge sursele LAB/server neeligibile pentru Champion.
- `local_environment_awareness.py` combină indexul static cu geometria locală,
  păstrând limitele navmesh distincte de zidurile fizice confirmate.
- `native/pa_nav_probe/main.cpp::measure_local_awareness` folosește 16 sonde
  statice pe direcții, până la 12 yd, la o înălțime de test. Nu măsoară un volum
  complet; spațiul dintre sonde nu este certificat. Un rezultat la raza maximă
  este limita sondei, nu dovada că există un zid exact acolo.
- Publicarea actuală are timestamp-uri și verificări de deplasare față de
  originea interogării. Nu confundăm existența acestora cu o marjă metrică
  garantată a poziției sau cu un certificat de siguranță a mișcării.

## Pasul implementat

`movement/spatial_context.py` adaugă un evaluator pur, fără I/O și fără import
de server, proces sau input. Primește dovezi tipizate, nu caută el poziția.
Sursele declarate acceptate sunt observații HUD, minimapă calibrată, fuziune
de observații client și geometrie din asset-uri. Etichetele de proveniență
nu autentifică singure datele: viitorul adaptor trebuie să valideze intrările.

Fiecare evaluare leagă sesiunea, harta, WorldPack-ul, sistemul de coordonate
și etajul. Etajul necunoscut nu este ales automat după cea mai apropiată
suprafață XY. Înregistrările vechi, viitoare, incompatibile, prea îndepărtate
de originea interogării sau cu incertitudine metrică necunoscută nu primesc
distanțe prezentate drept actuale. Pragurile sunt ale diagnosticului, nu
praguri noi de oprire sau pivotare în joc.

Evaluatorul:

1. Recalculează distanța XY până la cel mai apropiat punct al fiecărui segment
   raportat; nu reutilizează distanța veche și nu măsoară doar până la mijloc.
2. Păstrează originea originală a sondelor radiale. Nu mută razele după actor
   și nu interpolează spațiile dintre ele ca fiind libere.
3. Calculează bugetul condițional `raza corpului + eroare poziție + viteza
   maximă presupusă × (vechimea poziției + întârzierea reacției)`.
4. Publică referințele dovezilor, timpii, ipotezele, motivele refuzului și un
   text în română pregătit pentru o viitoare afișare în Control Center.

Un confidence mare nu inventează o eroare metrică mică. O limită statistică
de 95% nu trebuie transformată de adaptor într-o garanție absolută. Înălțimea
proiectată din navmesh nu trebuie etichetată drept înălțime observată în HUD.
Intrarea cere poziție XYZ; dacă observația oferă numai XY, adaptorul trebuie
să obțină o estimare justificată prin contractele existente sau să păstreze
funcția indisponibilă, nu să completeze un Z fictiv pentru a trece testul.

## Limite deliberate

Ieșirea are permanent `execution_authority=false` și
`free_space_certified=false`. Cea mai apropiată limită din setul raportat nu
este neapărat cel mai apropiat obstacol fizic. Chiar un set netrunchiat poate
fi incomplet semantic; un spațiu fără segmente raportate nu devine liber.
Obstacolele mobile sunt explicit `NOT_EVALUATED` în această etapă.
Nu este un model de frânare, viraj, coliziune sau senzor nou. Nu verifică
incertitudinea verticală și nu certifică un volum 3D; layer-ul trebuie legat
corect de adaptor. Raza de expunere este condiționată de limitele furnizate.

Exemplu exclusiv sintetic: corp 0,389 yd, eroare 0,10 yd, poziție veche de
0,10 s, reacție de 0,10 s și viteză 7 yd/s → rază de expunere 1,889 yd.
Acesta explică de ce distanța geometrică singură nu ajunge. Nu reprezintă o
măsurătoare a clientului actual și nu determină automat oprirea.

## Continuare delimitată

1. Adaptor read-only peste dovezile existente: sursă, moment, identitate,
   incertitudine metrică și etaj. Lipsurile reale rămân vizibile; nu se
   completează valori optimiste. Mai întâi replay, fără execuție.
2. Control Center: poziție/etaj rezolvat sau necunoscut, vârsta observației,
   eroarea poziției, limite cunoscute și zone necunoscute. Valorile expirate
   se estompează; nicio suprafață verde „sigură” derivată din doar 16 raze.
   Actualizarea rămâne asincronă și nu blochează harta ori bucla de control.
3. Legătura cu problema activă: verificarea traseului efectiv netezit și a
   volumului parcurs până la următoarea reacție, folosind raza virajului și
   viteza, nu doar endpoint-uri. Sondele servesc la alegerea interogărilor
   suplimentare, nu înlocuiesc validarea unui coridor.
4. Numai după acestea: alegerea unei corecții generale, apoi o probă LAB
   delimitată cu film salvat și criterii de acceptare/rollback. Nu hunting.

## Verificare

19 teste noi: distanță recalculată, capete/poziție pe limită, rotația corpului,
translație, timp, etaj, proveniență, incertitudine, valori invalide, trunchiere,
raze neinterpolate și lipsa autorității. Testele existente relevante se rulează
împreună cu ele: **87 PASS** (19 noi + 68 existente), 2,13 s. Sunt incluse
limitele arhitecturale, fuziunea poziției, awareness-ul, replay-ul și auditul
de clearance. Verificarea statică trece. Nu sunt teste live.
