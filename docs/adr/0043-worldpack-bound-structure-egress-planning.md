# ADR 0043: Planificarea ieșirilor structurale din cunoaștere standalone verificată

## Status

Accepted.

## Context

Indexul static poate demonstra că actorul se află într-un WMO, iar scanarea
offline poate păstra deschiderile observate în acel WMO. Până acum, Movement
Engine expunea această informație numai în telemetrie. Un coridor Detour parțial
nu o folosea pentru a găsi ieșirea, astfel încât cunoașterea structurii nu
schimba planificarea autonomă.

O deschidere salvată nu trebuie însă tratată drept comandă. WorldPack-ul poate
fi schimbat, actorul poate fi pe alt etaj, iar un frontier vechi poate să nu mai
fie accesibil din poziția curentă. O soluție legată de coordonatele unei cripte
sau ale unui oraș ar ascunde problema numai în locul unde a fost observată.

## Decizie

`Structure Access Graph` rămâne un sidecar read-only, legat criptografic de:

- WorldPack și hash-ul integral al conținutului;
- indexul structural derivat din același artefact de hartă;
- profilul de client și workerul navmesh care a produs observațiile.

Graficul furnizează cunoaștere durabilă, dar nu `execution_authority`. Când un
traseu direct este complet, el rămâne neschimbat. Numai pentru un traseu
parțial, motorul poate propune un sub-obiectiv structural, iar candidatul este
acceptat numai dacă:

1. awareness-ul curent confirmă exact un WMO care conține actorul;
2. deschiderea aparține acelui `structure_id`, etajul este apropiat și lățimea
   conectată depășește limita corpului;
3. deschiderea provine dintr-o tranziție covered-to-open verificată, nu dintr-o
   culoare, rază liberă sau presupunere despre ușă;
4. navmesh-ul activ găsește acum un coridor complet până la deschidere;
5. o a doua interogare, pornită de la deschidere, ajunge la destinația originală
   sau mută frontierul cu o îmbunătățire măsurabilă;
6. alegerea este făcută după completitudinea continuării, distanța rămasă și
   lungimea totală, fără nume de hartă ori coordonate speciale.

Pentru un context local marcat `topology_complete=false`, un egress complet nu
este respins automat dacă incompletitudinea descrie numai acoperirea locală.
Excepția rămâne fail-closed și cere simultan indexul structural imuabil din
WorldPack, graficul de acces legat de aceeași versiune și două coridoare Detour
complete, validate independent: actor-la-ieșire și ieșire-la-continuare. Lipsa
oricărei legături sau un picior parțial păstrează refuzul.

La ieșirea dintr-o structură, runnerul poate verifica cel mult opt obiective
semantice viitoare și alege primul pentru care ambele picioare sunt complete.
Această fereastră bounded este derivată exclusiv din ruta semantică generată și
nu transformă recording-uri ori coordonate operator în traseu executabil.

Runnerul folosește sub-obiectivul cu o rază mică de sosire, apoi reia destinația
originală. Ieșirile încercate sunt reținute pe durata aceleiași destinații
pentru a evita buclele. O recuperare locală după coliziune poate întrerupe acest
sub-obiectiv, dar după terminare revine la el, nu pierde destinația principală.

## Scanare la scară de continent

Planul full-Azeroth conține 42.594 probe. Pornirea unui proces și încărcarea
întregii hărți pentru fiecare seed nu este o proprietate a algoritmului de
awareness și ar transforma acoperirea globală într-un job de mai multe ore.
Scannerul folosește acum maximum patru servicii native persistente, fiecare cu
harta încărcată o singură dată, și ține cel mult `jobs * 2` futures în zbor.

O eroare opacă a serviciului persistent este verificată exact o dată prin
adaptorul strict one-shot, astfel încât `NO_NAV_POLYGON`, awareness incomplet și
eroarea reală de worker să rămână categorii distincte. Checkpointurile sunt
scrise atomic, iar agregarea refuză un scope incomplet sau orice
`PROBE_ERROR`.

Contururile conectate din observații multiple pot fi mai lungi decât limita
unei polilinii locale. Constructorul le împarte lossless în bucăți de maximum
128 segmente, suprapunând endpointul dintre bucăți. Limita contractului nu este
mărită, iar geometria nu este simplificată ori tăiată după coordonate.

La reluarea după întrerupere, fiecare checkpoint este reverificat, însă
validatorii JSON Schema sunt construiți o singură dată pentru întregul job și
reutilizați de scanare, raportare și agregare. Aceasta elimină recompilarea per
seed fără să elimine validarea, binding-ul sau hash-ul vreunui artefact.

## Dovezi de portabilitate

- Azeroth full-v3: 42.594/42.594 probe, zero `PROBE_ERROR`, 1.676 observații,
  10.187 contururi și 4.754 deschideri; graph hash
  `c2cf088fbc21a6ed24fb388d9911fa836dbb4e6cfa0f8320c9b4e56cda857be2`.
- Shadowfang v2: 825/825 probe, zero `PROBE_ERROR`, 73 observații, 274
  contururi și 65 deschideri; graph hash
  `82f1c279338c0d446339da520c657f9adcdb9baf48a4a8267eb98d5f707365b3`.
- `standalone-structure-egress-portability-azeroth-shadowfang-v1.json` este
  `PASS` pentru două WorldPack-uri independente, fără rută/coordonață salvată,
  fără client, server sau emulator la runtime și fără autoritate de input.
- Suita completă a proiectului: 1.045 teste trecute.

## Consecințe

- Nicio clădire, poartă, criptă, hartă sau destinație nu intră în politica de
  selecție.
- Același cod poate consuma grafuri produse pentru continente, dungeon-uri și
  alte builduri de client, dacă binding-ul lor exact trece verificarea.
- Un graf lipsă, vechi, ambiguu sau nevalidabil păstrează comportamentul
  fail-closed; motorul nu inventează o ieșire.
- `topology_complete=false` nu este o autorizație generală: relaxarea se aplică
  numai structurii și versiunii dovedite de cele trei surse legate de mai sus.
- O probă offline pe două WorldPack-uri distincte este obligatorie înainte ca
  această clasă de problemă să fie declarată portabilă. Proba live rămâne o
  etapă separată și nu este dedusă din scanare.
