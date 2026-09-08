# ADR 0033 — Catalog versionat pentru lumi, builduri și expansiuni

## Status

Acceptat și implementat pentru profilul TBC 2.4.3/build 8606. Extensibilitatea
este implementată; acoperirea completă a altor builduri nu este încă declarată.

## Context

Viewerul 3D și Movement Engine trebuie să folosească aceeași identitate de
hartă și aceleași asseturi. Un nume precum `Azeroth` nu dovedește singur că
terrainul, WMO-urile, interioarele și tile-urile Detour provin din clientul
activ. Formatele se schimbă între expansiuni: clienții vechi folosesc MPQ și
WDBC, iar familiile moderne folosesc CASC și generații DB2/WDC.

## Decizie

Introducem contractul `client_world_catalog` v1. O intrare leagă:

- product, expansion, client version și build;
- familia containerului de asseturi și profilul parserului;
- hash-ul catalogului de hărți extras din client;
- map ID-ul și numele intern citite din acel catalog;
- profilul nav, fișierul `.map`, fiecare tile `.nav` și hash-urile lor;
- câte o mască semantică `.road` cu exact aceleași coordonate ca fiecare tile,
  plus hash-ul fiecărui fișier și al setului ordonat;
- starea reală de acoperire open-world, pentru interioare și pentru drumuri.

Runtime-ul verifică identitatea din launch receipt înainte de orice input,
parsează `Map.dbc` cu adaptorul declarat, cere egalitate exactă între hărțile și
tile-urile și semanticile catalogate și cele de pe disc, apoi verifică toate
hash-urile. Orice map ID necunoscut, build diferit, tile/semantică
lipsă/suplimentară, coordonate ADT nealiniate sau artefact modificat oprește
Movement Engine fail-closed.

Viewerul poate descoperi hărțile disponibile din același profil, dar o hartă
devine utilizabilă de engine numai după verificarea catalogului. Rendererul și
contractul world-space sunt comune tuturor expansiunilor; extractoarele și
parsers sunt adaptoare versionate, nu ramuri hardcodate în planner.

## Profil confirmat

`wow.tbc.2.4.3.8606.client-world-v1` verifică în prezent:

- `DBFilesClient/Map.dbc` din clientul enGB 2.4.3.8606;
- Map ID `0`, nume intern `Azeroth`;
- profilul nav `tbc243-human-road-corridor-v6`;
- 8 tile-uri ADT (`28_27` până la `31_28` pe cele două coloane construite);
- 8 măști de drum aliniate 1:1 cu tile-urile;
- acoperire `partial`, interioare `partial`, drumuri `partial`.

Aceasta nu este o declarație de suport complet pentru tot TBC. Catalogul spune
explicit ce există, astfel încât extinderea la fiecare continent, instanță și
interior să fie măsurabilă și să nu fie confundată cu o promisiune deja livrată.

Profilul candidat `tbc243-tirisfal-silverpine-v1` extinde aceeași hartă la
dreptunghiul ADT `x=28..31`, `y=27..32`: 24 tile-uri `.nav` și 24 semantici
`.road`. Catalogul său este verificat separat și rămâne `partial` deoarece nu
acoperă întregul Azeroth, iar bake-ul raportează contururi și triangulări Recast
care trebuie păstrate în audit, nu ascunse de un exit code reușit. Profilul
stabil `tbc243-human-road-corridor-v6` nu este înlocuit automat.

Gate-ul global al candidatului validează Deathknell→Brill direct și
Deathknell→Shadowfang prin A* semantic plus coridoare Detour locale. O cerere
Detour unică spre Shadowfang se oprește într-un frontier local; validatorul
adaptiv o rezolvă fără waypoint de localitate hardcodat: folosește orizonturi
de 60 yd și rafinează monoton numai pe celulele A* curente când un orizont este
parțial. Proba a ajuns la destinație în 86 de etape validate, cu o singură
rafinare.

## Extindere pe expansiuni

Pentru un build nou se adaugă un adaptor de asset/container și unul pentru
familia tabelei de hărți, apoi se generează un catalog nou. Gate-ul minim cere:

1. inventar determinist al map ID-urilor din client;
2. extragere/bake terrain, WMO, M2/doodads, liquids și holes;
3. navmesh și collision pentru exterior și interior;
4. hash-uri reproductibile și coverage manifest;
5. probe de coordonate, relief, etaje, uși și ieșiri;
6. validare vizuală în viewerul 3D și teste de path topology.

MPQ/WDBC și CASC/DB2-WDC pot coexista în catalog, dar niciun adaptor nu se
consideră compatibil implicit cu altă familie de builduri.

Registry-ul implementat leagă momentan numai perechea exactă
`mpq + wow-wdbc-map-v1` de adaptorul `wow-mpq-wdbc-v1`. Un profil CASC/DB2-WDC
este refuzat înainte de pornirea oricărui extractor până când adaptorul său este
implementat și validat. Fiecare adaptor declară explicit că runtime-ul rezultat
nu cere client, server sau emulator; aceste procese nu fac parte din interfața
WorldPack.

### Inventarul fizic al clientului

Pentru familia MPQ/WDBC, `pa_client_asset_extract --inventory-world` deschide
arhivele clientului o singură dată, citește map ID-urile direct din `Map.dbc` și
verifică toate coordonatele ADT `0..63` fără a extrage fișiere. Builderul Python
leagă rezultatul de hash-ul aceluiași `Map.dbc`, cere egalitate exactă între
map ID-uri/nume, ordine deterministă, count și bounds, apoi validează contractul
`client_world_asset_inventory`.

Inventarul confirmat pentru TBC 2.4.3.8606 conține 83 de hărți, 74 WDT-uri, 35
hărți cu ADT și 3.610 tile-uri ADT. Exemple: `Azeroth=687`, `Kalimdor=1018`,
`Expansion01=800`, `Shadowfang=25`. Valorile sunt coverage de asseturi, nu o
declarație că navmesh-ul a fost deja construit sau validat.

Extracția bulk acceptă numai un nume intern prezent în `Map.dbc`, cere o
destinație nouă și extrage exact WDT-ul și coordonatele inventariate. Pentru
ADT-urile valide fără texture layers (întâlnite în instanțe), semantica de drum
este explicit neutră; WMO-ul și terenul rămân în geometria navmesh, dar nu sunt
etichetate fals ca drum. BVH și navmesh se construiesc în faze separate, iar un
profil devine selectabil numai după catalog și gate-uri topologice.

## Consecințe

- Movement Engine nu mai presupune numele hărții în calea principală live.
- Putem adăuga Classic, WotLK, retail sau servere custom fără a schimba nucleul
  plannerului, dacă asseturile clientului respectiv au adaptor validat.
- Coverage-ul incomplet rămâne vizibil și blochează afirmațiile universale.
- Catalogul și viewerul nu oferă execution authority.
