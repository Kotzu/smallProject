# ADR 0048: Călătorie multimodală și simulare PvP

## Status

Accepted; se implementează după promovarea WorldPack-ului celor trei continente
și controllerul local predictiv.

## Context

O destinație îndepărtată nu se rezolvă numai printr-un coridor terestru. În
World of Warcraft, ruta potrivită poate combina mersul cu barcă, zeppelin,
portal, taxi/flight path sau hearthstone. Cea mai scurtă linie geometrică poate
fi imposibilă, mai lentă ori mult mai periculoasă decât o asemenea combinație.

În PvP apare aceeași nevoie de anticipare. Predatorul trebuie să compare
deschideri, reacții ale adversarului, poziționări, control, reset și re-engage
înainte ca o întâlnire reală să devină singurul experiment disponibil.

## Decizie

### Graf semantic de călătorie

Peste navmesh-ul local construim un graf autonom de călătorie. Nodurile sunt
regiuni, intrări, docuri, turnuri de zeppelin, portaluri, flight masters,
hearthstone bind points și destinații. Muchiile au un tip explicit:

- `walk_navmesh`;
- `boat`;
- `zeppelin`;
- `portal`;
- `flight_path`;
- `hearthstone`.

Fiecare muchie păstrează condiții și evidence: build/realm, faction, acces
descoperit, cost, cooldown, punct de îmbarcare, punct de ieșire, timp observat,
incertitudine și ultima confirmare. Topologia statică învățată nu este ștearsă.
Observațiile dinamice, precum timpul până la următorul vapor sau prezența
curentă a unui portal, își reduc confidence-ul când se învechesc, dar istoricul
lor rămâne permanent.

Plannerul global compară călătoriile după timp estimat, risc, disponibilitate,
cost și valoarea obiectivului. Nu alege automat nici distanța geometrică minimă,
nici ruta cea mai lungă doar fiindcă este sigură. Nivelul, stealth-ul, memoria
de aggro/death și scopul curent schimbă scorul fără să schimbe geometria.

MovementEngine rezolvă fiecare segment `walk_navmesh` prin WorldPack, iar
tranzițiile sunt mașini de stare observabile: apropiere, confirmarea terminalului,
așteptare, îmbarcare/interacțiune, călătorie, confirmarea noii hărți și replan.
Dacă Predatorul ratează transportul, este împins, intră în combat ori ajunge la
altă ieșire, nu continuă o rută presupusă; observă din nou și recalculează.

WorldPack-ul conține geometria și topologia statică. Disponibilitatea live este
confirmată numai prin informație permisă de client. Serverul și emulatorul pot
fi evaluatori LAB, niciodată surse obligatorii în decizia Championului.

### Simulare continuă a călătoriilor

Offline se generează călătorii între regiuni și combinații de transport, cu
variații de nivel, viteză, cooldown, timp de așteptare, aggro, deces, rută
închisă și transport ratat. Rezultatele alimentează euristici și regresii
reutilizabile pentru orice destinație; nu hardcodează traseul Deathknell–Brill.

Live, plannerul rulează asincron și păstrează mereu o alternativă validă. O
schimbare a mediului invalidează numai partea afectată și declanșează replan,
fără să oprească inutil controllerul local.

### Simulare PvP

PvP folosește trei niveluri de dovadă:

1. simulator rapid pentru mii de rollout-uri cu formule calibrate, clase,
   level/gear bands, cooldown-uri, energie, combo points, LOS și teren;
2. replay-uri de adversari cu stiluri diferite, latență, reacții, strafe,
   kite, fake cast, trinket, defensives, reset și intervenții externe;
3. clone LAB în client pentru confirmarea tacticilor pe development și holdout,
   înainte de promovarea în Champion.

Simulatorul propune și elimină tactici dominate, dar nu poate promova singur o
politică. Rezultatul trebuie confirmat în client deoarece timingul, pathingul,
serverul, animațiile și comportamentul uman real nu sunt reproduse perfect de
model. Championul primește policy-ul agregat și verificat, nu amintiri episodice
fabricate de clone.

În open PvP, căutarea globală folosește hotspot-uri, ore, ultimele întâlniri și
probabilități. Poziția exactă a unui player este folosită numai cât timp este
observabilă legitim de client. După contact, controllerul combină interceptarea,
LOS, facing magnetic, range envelope și terenul din WorldPack.

### Fight Learning Bundle

Fiecare luptă LAB din Gurubashi produce un bundle append-only, sincronizat pe
un timeline monotonic comun. Bundle-ul păstrează:

- manifestul: client/build/realm, brain și policy hashes, spellbook, talents,
  gear, level, arena/terrain signature, seed și profilul adversarului;
- observațiile permise: HP, energy, combo points, buffs/debuffs, target/focus,
  cast observat, combat state, target health și evenimentele raw din combat log;
- percepția/movementul: pose belief, facing error, range band, LOS evidence,
  target bearing, coridor, clearance și obstacle/recovery state;
- fiecare decizie: toți candidații și scorurile lor, acțiunea aleasă și motivul;
- fiecare execuție: input propus, autorizat, trimis și efectul confirmat de un
  frame/eveniment ulterior;
- rezultatul: win/loss/escape/reset, damage, control, resources, TTK, uptime,
  positional advantage, erori de facing/range/LOS și clipul video sincronizat.

Lanțul obligatoriu este
`observation -> candidates -> chosen -> authorized -> input -> observed effect`.
Astfel, raportul nu spune doar că o lovitură a lipsit: poate diferenția o
decizie greșită de un input neexecutat, facing pierdut, informație veche sau
miss/dodge/crit legitim.

După fiecare fight, diagnosticul separă cinci cauze: `decision`, `execution`,
`perception`, `movement/environment` și `game_variance`. Replay-ul rulează apoi
counterfactuale controlate, schimbând câte o singură alegere: opener, momentul
finisherului, interrupt, cooldown, trinket, orbit/behind, disengage ori reset.

Fiecare luptă actualizează statisticile și memoria de adversar, dar nu rescrie
imediat policy-ul Stable. Candidate-ul este promovat numai după adversari/seeds
variați, regresii și holdout in-client. Această regulă împiedică Predatorul să
învețe o superstiție dintr-un singur crit sau dintr-un PlayerBot defect.

PlayerBots pot furniza profiluri reproducibile de adversar și reset rapid.
Starea lor ascunsă/server-side este permisă numai scorerului LAB după luptă;
deciziile Predatorului din timpul luptei primesc exact informația vizibilă
clientului, la fel ca într-un realm fără emulator controlat.

## Criterii de acceptare

- o destinație între continente poate produce o călătorie mixtă, explicabilă;
- pierderea unei tranziții produce reobservare și rută nouă, nu blocare;
- hearthstone nu este ales când bind-ul/cooldown-ul nu este confirmat;
- nicio rută nu depinde de coordonate sau stare ascunsă ale emulatorului;
- simulatorul PvP păstrează train/development/holdout separat;
- fiecare fight are timeline complet și legături verificabile între observație,
  decizie, input și efect;
- diagnosticul separă decision/execution/perception/movement/game variance;
- o tactică nu ajunge în Champion fără confirmare in-client și regresie;
- memoria istorică nu este ștearsă; freshness afectează numai câtă încredere
  acordăm stării dinamice curente.
