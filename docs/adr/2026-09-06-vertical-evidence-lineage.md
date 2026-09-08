# Z și etaj — proveniență și ambiguitate, nu înălțime inventată

Status: audit de cod și replay offline. Nicio schimbare în motor, addon,
camera clientului, CC sau procesele active. Etapa 5 nu este închisă.

## Constatări confirmate în codul actual

1. `PAO_MapPositionPayload` preia numai `x, y` din `GetPlayerMapPosition`.
   Transportul actual nu observă Z. Numele din GetZoneText/GetSubZoneText
   identifică regiunea/subzona, nu nivelul fizic.
2. Runnerul inițializează `current_z_hint` din opțiunea de pornire sau din
   istoricul de reluare, apoi alege un strat cu `_select_initial_vertical_layer`.
   Ulterior îl actualizează din `local_sample.resolved.z` și din proiecția
   controllerului pe coridor. Acestea sunt estimări geometrice.
3. Serviciul nativ de awareness interoghează `pathfind_find_heights`, alege
   înălțimea apropiată de hint și apoi poligonul apropiat. Răspunsul publică
   punctul rezolvat, nu toate înălțimile candidate. O singură valoare în acel
   răspuns nu înseamnă că exista o singură suprafață posibilă.
4. `_movement_floor_hint` din bridge-ul CC reutilizează `player_world.z`
   dacă XY este la cel mult 3 yd. În acest helper nu verifică timestamp-ul,
   sesiunea sau WorldPack-ul. Este un prior util numai condițional; nu este
   dovadă de etaj actual. Riscul la relogare sau etaje suprapuse este dedus din
   cod, nu reprodus live. Nu schimbăm încă acest comportament din mers.
5. Constructorul `MinimapAnchorObservationBuilder` cere `normalized_z` și
   varianța verticală de la apelant; nu le măsoară. Fuziunea combină ce primește.
   Căutarea în `src` și `integrations` nu găsește un apel runtime la aceste
   clase în afara definițiilor/exporturilor. Existența lor nu dovedește un
   senzor vertical conectat. Calibrarea incertitudinii rămâne etapa 6.

Nu afirmăm aici că niciun API al oricărei versiuni WoW nu poate oferi Z;
constatarea privește implementarea și transportul existente în acest proiect.

## Dovada reală și schimbarea implementată

Replay-ul existent păstrează acum evenimentele `INITIAL_VERTICAL_LAYER_SELECTED`,
cu hash/index exact, seed, alegere, alternative, diferența până la alternativa
cea mai apropiată și politica înregistrată. Referința apare numai în cadre
ulterioare evenimentului. Este explicit o ipoteză inițială istorică, nu etajul
actual al tuturor cadrelor. Nu este transferată în `SpatialPoseEvidence`.

În proba `8544bb3c-f0f6-41f1-84d5-8e7952458f56`, evenimentul actions/10:

- seed Z = 100,0;
- alegere = 121,797379;
- alternativă = 138,729095, diferență 16,931716 yd;
- ambele candidate aveau traseu complet;
- 626 cadre rămân fără Z observat și fără etaj confirmat.

Acest rezultat nu dovedește că alegerea a fost greșită. Dovedește că succesul
planificării singur nu diferenția cele două niveluri. Nu presupunem că lista
de candidate înregistrată este exhaustivă.

Raport local exclus din Git:
`data/runtime/operator/live-evidence/20260906-spatial-context/replay-8544bb3c-vertical-selection.json`.
Hash-ul înregistrării rămâne
`e2e220e4879f00baffdb72a9546084719cf5d408c3b772bda20cf88877a0a511`.

Verificare: **99 PASS în 1,63 s**, replay spațial, evaluator spațial, fuziune,
contracte pose și transportul numelor. Include alternative cu trasee complete,
candidat unic fără promovare în certitudine, ordine temporală, date invalide
și păstrarea intrării. Nicio probă live nouă.

## Continuare concretă

1. În adaptorul de observație, separăm explicit XY observat, Z estimat și etaj
   necunoscut, fiecare cu identitate/timp/proveniență; nu convertim proiecția
   navmesh în poziție client măsurată și nu refolosim un prior străin.
2. Pentru selecție reală de nivel, păstrăm alternativele la interogarea nativă
   și cerem dovezi care le diferențiază: continuitate de traversare verificată,
   observație vizuală calibrată sau capabilitate API verificată. Numele zonei
   ori simpla proximitate XY nu sunt suficiente. Întâi teste suprapuse offline.
3. CC afișează starea parțială și vechimea asincron; priorul vechi nu primește
   timestamp nou doar fiindcă este recitit. Înainte de schimbarea helperului
   activ sunt necesare teste pentru relogare, identitate de hartă și staționare.
4. Ulterior calibrare de eroare și verificarea volumului parcurs în viraje;
   nu schimbăm praguri pentru a forța un rezultat verde.

Rollback al pasului prezent: revert al commitului dedicat adaptorului/replay-ului.
Nu există consumator live nou. v34 și addon 0.5.9 rămân active ca înainte.

## Goal

Operatorul a cerut continuare persistentă. Goal-ul existent pentru clearance
este încă `blocked`, nu realizat. Încercarea de creare a unui goal pentru
planul spațial complet a fost refuzată: există un goal neterminat. Instrumentele
agentului nu oferă reactivare/modificare a obiectivului; este necesară acțiunea
operatorului în aplicație. Acest lucru nu blochează lucrul normal în turnuri.
