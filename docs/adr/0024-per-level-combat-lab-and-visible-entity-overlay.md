# ADR 0024 — Combat lab per nivel și overlay extern bazat pe vedere

- Status: accepted
- Date: 2026-08-24
- Extends: ADR 0013, ADR 0017, ADR 0018, ADR 0020, ADR 0021 și ADR 0023

## Context

Scopul proiectului nu este un bot care doar execută o rotație fixă, ci un
Assassin care descoperă și promovează strategii mai bune pe măsură ce crește.
O singură luptă nu poate separa o decizie bună de noroc, miss, dodge, crit,
regen, latență sau variația damage-ului. În același timp, champion journey nu
trebuie folosit drept cobai și nu trebuie să primească amintirile brute ale
clonelor de laborator.

Primul combat controlat din 2026-08-24 a demonstrat bucla vizibilă completă:
targeting NPC, facing, approach, Attack, Sinister Strike, GCD/energy wait și
damage observat. Un Young Scavenger a ajuns la 8 HP, iar policy-ul a selectat
Eviscerate într-o fereastră conservatoare. O a doua luptă a demonstrat că ținta
poate muri numai din builders și auto-attack, fără ca un finisher să fie
rentabil. Aceste două traiectorii justifică evaluarea empirică per inamic.

## Decizie

### Două bucle separate

Perfect Assassin folosește două bucle care nu își amestecă authority sau
memoria episodică:

1. `champion_journey`: caracterul persistent care explorează, face questuri și
   primește numai policy-uri promovate;
2. `lab_clone`: una sau mai multe instanțe client + caracter clonă, pe același
   realm privat ori pe un realm privat separat, folosite pentru lupte resetabile.

Fiecare instanță are PID/HWND, cont, caracter, porturi, runtime arm, realm
receipt, output root și memory namespace proprii. Niciun lease sau target fact
nu este reutilizat între instanțe. Champion poate continua călătoria în timp ce
clonele evaluează combat, dar execuția rămâne serială în fiecare client.

### Experiment la fiecare nivel

La atingerea fiecărui nivel se emite un `per_level_combat_experiment` pentru
fiecare archetype relevant întâlnit: beast, humanoid, caster, healer, ranged și
elite, apoi pentru identitățile care au produs pierderi sau overkill mare.

Pentru un Young Scavenger sau Duskbat de nivel 1, candidatul minim include:

- finisher imediat la 1 CP;
- finisher la 2 CP;
- finisher la 3 CP;
- `adaptive_lethal_window`, care estimează HP-ul viitor după auto-attack,
  builder, armor band, miss/dodge și regen și termină la cel mai mic CP cu risc
  acceptat;
- policy-ul champion curent, ca baseline.

Fiecare candidat primește 100 de lupte in-client cu aceeași versiune de client,
server, clasă, nivel, talents, gear, weapon skill, consumables și poziție de
start. Seed-urile sau ordinea condițiilor sunt paired între candidați când
serverul permite; altfel ordinea este randomizată și start-state divergence
este înregistrată. Primele 80 de runs formează development set, ultimele 20 un
holdout care nu participă la alegerea candidatului.

Înaintea celor 100 de lupte live, un simulator determinist rulează mii de
rollouts ieftine din formulele client-build și distribuțiile calibrate. El
elimină strategiile evident dominate, dar nu poate promova singur un policy.
Rezultatele live ale clonei calibrează hit/miss/dodge/crit, armor, timing și
regen și sunt sursa empirică obligatorie pentru promovare.

Resetul dintre runs restaurează un snapshot versionat sau recreează exact
caracterul și inamicul. Run-ul este invalid dacă diferă level, HP/energy de
start, gear hash, spellbook hash, target identity/archetype, realm build ori
poziția peste toleranță. Death, evade, add aggro și manual takeover sunt
rezultate explicite, nu runs șterse.

### Protecția clonei în timpul calibrării

În fazele de calibrare a percepției, facing-ului și transportului de input,
clona LAB poate primi `labgod <player> on` prin interfața administrativă locală
a serverului. Această protecție anulează numai damage-ul primit de player;
aggro, threat, atacurile inamicului, proc-urile și acțiunile Predatorului rămân
active și observabile. Nu folosește GM mode și nu este trimisă prin chatul
clientului de joc.

Protecția este destinată testelor de infrastructură, nu măsurării survival,
damage taken sau consumului de recovery. Runs folosite pentru promovarea unui
policy de combat trebuie să o aibă oprită și să înregistreze explicit acest
lucru în manifest. Starea este volatilă și trebuie reactivată după restart sau
reconectarea caracterului. Scriptul `scripts/Set-LabCombatProtection.ps1`
o activează/dezactivează prin RA și acceptă succesul numai dacă world serverul
confirmă exact schimbarea.

Pentru sesiunile lungi de observare, `labstay <player> on` respinge marcarea
automată AFK direct în world server și curăță imediat un flag AFK existent.
Nu fabrică mișcare, nu trimite taste, nu mută camera și nu poate concura cu
preluarea manuală. Configurația generală păstrează în plus
`Player.AFK.DisconnectTimeout = 0`. Ca și protecția de damage, `labstay` este o
stare volatilă a sesiunii LAB și se reactivează după reconnect sau restart prin
`scripts/Set-LabStayOnline.ps1`.

### Metrici și promovare

Fiecare run păstrează numai telemetry structurată și evidence refs necesare:

- win/death/retreat/evade;
- HP și energy rămase;
- time-to-kill și time-in-danger;
- damage dealt/taken și auto-attack uptime;
- CP create, CP consumate și CP pierdute la moartea țintei;
- raw/likely/conservative overkill;
- număr de builders, finishers, miss, dodge, parry și crit observate;
- GCD waste, energy cap time și cooldown waste;
- facing/range failures, approach distance și add pulls;
- recovery time și consumables cost.

Ordinea obiectivelor este lexicografică: survival constraint, apoi win rate,
apoi risk-adjusted TTK, damage taken, resource waste și overkill. Un candidat
poate fi promovat numai dacă:

1. nu scade limita inferioară a win rate-ului sau survival față de baseline;
2. îmbunătățirea trece pragul minim și intervalul de încredere configurat;
3. holdout-ul confirmă direcția rezultatului;
4. replay-ul de decizii și provenance este complet;
5. un canary scurt pe champion nu produce regresie.

Dacă 100 de runs nu separă statistic candidații, nu se inventează un câștigător:
baseline rămâne activ, iar laboratorul poate aloca încă un batch limitat.

Memoria promovată conține modelul agregat și policy versionat, nu cele 100 de
istorii brute. La un nou level, spell, rank, talent, weapon, gear tier sau
server build, policy-ul relevant devine `needs_revalidation`.

### Confirmarea acțiunilor live

După Sinister Strike sau Eviscerate, executorul nu poate trimite alt ability
până când un frame nou confirmă cel puțin damage, energy/CP transition ori GCD.
Pentru Eviscerate, damage-ul sau moartea trebuie observate înaintea următorului
damage action. O schimbare automată de target ori `target=null` după o acțiune
de damage poate fi doar o tranziție provizorie de one-shot; kill-ul devine
confirmat exclusiv dacă recovery reselectează aceeași identitate CRC ca țintă
moartă și observă apoi deschiderea lootului. Fără această dovadă exactă,
execuția se oprește fail-closed.

### Facing magnetic și locomoție target-relative

Facing-ul este un invariant continuu, nu o etapă executată o singură dată la
începutul luptei. Fiecare acțiune de damage, approach sau orbit cere un bearing
proaspăt al aceleiași ținte. Mouse yaw este proporțional cu abaterea vizuală;
după fiecare impuls se capturează un frame nou și nu se presupune că rotația a
reușit.

În melee, ferestrele de GCD și energy regeneration pot fi folosite pentru un
impuls scurt `STRAFE_LEFT`/`STRAFE_RIGHT`. Direcția rămâne stabilă pentru
identitatea luptei, ca mișcarea să formeze o orbită și nu un jitter stânga-dreapta.
Dacă ținta părăsește coridorul central, orbitarea se oprește imediat, corecția
cu mouse-ul revine la prioritate, iar următorul strafe cere din nou bearing
`VISIBLE/CENTER`, auto-attack activ și melee range confirmat. Astfel Predatorul
menține presiune și poate învăța ulterior rear-arc control fără a deveni o
turelă statică.

### Overlay extern, nu ESP ascuns

Entity overlay-ul este o fereastră externă, separată de captură/video, și poate
fi oprit fără să afecteze clientul. El folosește exclusiv pixeli pe care i-ar
putea vedea jucătorul: frame-ul clientului, nameplates, target circle, minimap,
tooltip și HUD-ul addon vizibil. Nu citește process memory, packets, server DB,
hidden object lists, injected code sau poziții ale unităților aflate după
obstacole.

Detectorul poate propune etichete `hostile_mob`, `player`, `friendly_npc`,
`herb`, `mining_node`, `quest_object` și `unknown`. Fiecare detection are box,
bearing, confidence, frame id, timestamp, evidence method și TTL. Track-urile
se sting când nu mai sunt văzute; nu devin cunoaștere perfectă despre obiecte
off-screen. Player detections sunt utile pentru evitare/context, dar gate-ul
PvE continuă să interzică player targets.

Overlay-ul nu decide și nu execută input. El afișează separat:

- detections curente și confidence;
- selected target și focus target când acestea sunt vizibile;
- facing corridor, route, navmesh tiles și path cost;
- fog-of-war al cunoașterii proprii: zone văzute, traversability încercată,
  blocaje, deaths, herbs/mines confirmate și vechimea observației.

Harta internă este o hartă de experiență, nu o hartă omniscientă. Celulele
necunoscute rămân necunoscute; observațiile vechi decad, iar schimbarea realmului
sau buildului le separă în alt namespace. Navmesh-ul din asseturile locale poate
oferi geometria statică, dar NPC/player/resource state rămâne numai vizual.

### Spellbook, target și focus

Cele trei sloturi actuale sunt bootstrap, nu limita arhitecturii. Spellbook-ul
va fi inventariat pe toate taburile și compilat într-un `action_registry`
versionat cu spell id/name/rank, cost, cooldown, range, form/stealth și binding.
Execution gateway-ul primește acțiuni semantice, iar bar paging/bindings sunt
detalii ale adaptorului.

Combat state păstrează separat `main_target` și `focus_target`. Focus este
rezervat pentru healer/caster important și poate primi interrupt fără a pierde
main target, dar numai după ce target identity, cast evidence, range și facing
sunt confirmate. Pentru Rogue level 1 rămân active numai Attack, Sinister
Strike și Eviscerate.

## Consecințe

- Ideea „100 de lupte cu același bat” devine un test reproducibil, nu grind
  necontrolat.
- Champion învață din rezultate agregate fără să-și riște progresul.
- Un policy de 1/2/3 CP poate fi diferit pentru fiecare enemy archetype, gear și
  level, iar `adaptive_lethal_window` poate câștiga când evită overkill.
- Overlay-ul oferă senzația utilă de ESP pentru video/debug, dar nu acordă
  informație pe care clientul nu a afișat-o.
- Multi-instance crește throughput-ul, dar fiecare instanță consumă resurse și
  cere identity/realm isolation completă.

## Rollback

Oprirea workerelor `lab_clone`, dezarmarea runtime arms și ascunderea ferestrei
overlay nu modifică champion journey. Ultimul policy promovat rămâne activ;
rezultatele incomplete rămân `evaluation_only` și nu pot fi promovate.
