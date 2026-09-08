# Asocierea numerică între candidatele native și suprafețele WMO

## Decizie și implementare

`adapter/surface_association.py` asociază candidatele `FindHeights` cu hit-urile
triunghiurilor WMO de pe aceeași coloană XY. Primește un buget numeric explicit
de potrivire, nu îl deduce din precizia actorului. Toate candidatele, inclusiv
duplicatele și cele fără potrivire, rămân în ordinea inițială. Toate identitățile
triunghiurilor compatibile sunt păstrate; nici cea mai apropiată suprafață,
nici un singur grup interior nu devin automat nivelul personajului.

Stări distincte: MATCHED_GEOMETRY, NO_WMO_MATCH, OUTSIDE_TESTED_SEGMENT.
Absența unui hit WMO nu invalidează candidatul: terenul și doodad-urile nu sunt
incluse aici. Z selectat de worker este păstrat neschimbat; observed_actor_z și
confirmed_floor_id rămân null, execution_authority=false. Normala nu este
folosită pentru a declara singură podea/plafon/traversabilitate.

Respinge alt XY, segment invalid, date nonfinite, identități invalide, mai mult
de 64 candidate sau 4096 hit-uri. Toleranța numerică acceptată este explicită,
strict pozitivă și maximum 0,01 yd; proba de mai jos folosește 0,001 yd.
Aceasta este o limită configurată de asociere, nu eroare metrică validată.
Funcția pură nu verifică singură fișierele/harta: această responsabilitate
rămâne orchestration-ului care îi furnizează datele din aceeași interogare.

## Verificare integrată offline

Auditul existent acceptă acum `--profile`, `--candidate-worker`,
`--worker-sha256`, `--candidate-z-hint` și `--matching-tolerance`.
Înaintea interogării native verifică:

1. WorldPack-ul complet prin verificatorul existent și profilul fixat.
2. Indexul instanțelor prin schema existentă și reconstruire din harta fixată.
3. Root ID și multisetul triunghiurilor WMO față de BVH-ul aceleiași clădiri.
4. Hash-ul executabilului worker furnizat explicit.

Doar apoi pornește un worker separat de observație pentru map_name din index;
workerul este închis în finally. Nu comunică cu jocul sau serverul. Asociază
XY returnat de query cu segmentul geometric și păstrează pack hash, worker
hash, instanța, map ID și timpul interogării native în rezultatul de audit.
runtime_session_binding rămâne null: nu poate fi prezentat drept observație
live a personajului. Nu s-a produs încă un artefact sigilat de metadate WMO
pentru consumul CC; câmpul general asset_instance_binding_verified rămâne false.
world_pack_seal_verified=true se referă strict la verificarea pack-ului existent.

## Rezultat real

WorldPack a9feb578fea082f073effd84415977fa8a760ed2e5b2f8b07a1609215fe56b78,
worker a19c6947d7bbbe4ecd1702477cf2c3a6bb431a6712ba98df18ddd678565a1404,
instanța 0:wmo:85944, hartă 0. XY1676,369629 /1677,466919, segment Z160→100,
hint de query Z121,797379. Nicio valoare de referință nu este hardcodată în
algoritmul generic. Indexul și geometria au trecut verificările de mai sus.

- Candidatul Z121,670326: potrivire cu grupul 4 /group ID1490 /triunghi4901,
  suprafața la Z121,67034075043068. Abatere numerică 0,00001475043068 yd.
- Candidatul Z138,45195: NO_WMO_MATCH și păstrat. Nu este reclasificat automat
  ca teren, exterior sau candidat greșit.
- Z selectat rămâne 121,670326. Nicio localizare efectivă a etajului actorului
  nu este declarată; suprafața geometrică și actorul sunt lucruri distincte.

## Teste, continuare și rollback

247 teste relevante PASS în 0,72 s, dintre care 21 pentru asociere: candidate
nepotrivite păstrate, identități multiple pe muchii comune, toleranță fără
fallback la nearest, segmente diferite, lipsă acoperire vs lipsă hit,
immutabilitate, bugete și valori invalide. Nu este suita completă a proiectului.

Urmează artefactul de metadate WMO legat verificabil la pack și index, cu
acoperire explicită și hash-uri, apoi citirea lui asincronă în observer/CC.
Un bundle pentru o clădire nu va fi raportat ca acoperire a întregii hărți.
Potrivirile geometrice vor fi afișate separat de confirmarea etajului și de
observația API; nu conferă autoritate plannerului sau controllerului.

Nicio modificare live în acest pas: v34, anti-AFK, addon și CC neschimbate.
Rollback: revenirea acestui commit; fără reinstalare sau mutări de runtime.
