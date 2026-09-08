# ADR 0050 — Nucleu determinist de mișcare și agent AI opțional

- **Status:** acceptat
- **Data:** 2026-08-29
- **Scop curent:** `MovementEngine` autonom și standalone, fără injection,
  memory read/write, packet hooks sau logică de tip pixel-click în nucleu

## Context

Predator trebuie să poată planifica și executa deplasări lungi, fluide și
reproductibile pe mai multe versiuni de client și server. Problemele live
curente — balans, opriri, fallback-uri dese și pierderea continuității între
procese — sunt probleme de geometrie, control și feedback temporal. Un model
lingvistic chemat la fiecare cadru nu le rezolvă și ar adăuga latență și
nondeterminism.

Clarificarea operatorului din 2026-08-29 permite captură read-only și un HUD
optic validat. „Fără pixel bot” înseamnă că imaginea este numai un adaptor de
observație; Predator nu navighează prin reguli de forma „pixelul are culoarea X,
apasă tasta Y”. Harta, traseul, clearance-ul și controlul provin din WorldPack,
navmesh și world model.

Auditul a confirmat și o limită informațională: un proces extern nu poate
corecta în buclă închisă poziția și facingul dacă nu primește niciun feedback
live. Dacă adaptorul optic este dezactivat împreună cu memory read, injection,
packet access și server telemetry, rămâne doar dead reckoning. Acesta nu poate
oferi autonomie robustă după coliziuni, lag, loading screen sau input pierdut.

## Research

Au fost comparate următoarele direcții publice:

- [mod-llm-playerbots](https://github.com/bigr00/mod-llm-playerbots) păstrează
  mișcarea și lupta de frecvență mare în motorul determinist Playerbots;
  LLM-ul este folosit rar pentru agendă, social și narațiune. Este dependent de
  AzerothCore și nu este standalone.
- [DaemonCraft](https://github.com/nicoechaniz/DaemonCraft) folosește Gemma
  peste o reprezentare compactă a lumii și unelte structurate, dar motorul
  Mineflayer execută deplasarea. Arhitectura susține folosirea AI-ului deasupra
  controlerului, nu în locul lui.
- [WowClassicGrindBot](https://github.com/Xian55/WowClassicGrindBot) are
  Recast/Detour, costuri pentru drumuri, spline following, lookahead adaptiv,
  hysteresis și simulator. Este reperul public direct pentru fluiditate, dar
  folosește screen capture și telemetrie Lua prin pixeli, pune accent pe rute
  înregistrate și nu oferă portabilitatea WorldPack dorită aici. Codul său nu
  va fi copiat.
- [Recast Navigation](https://github.com/recastnavigation/recastnavigation)
  validează baza Recast + Detour și necesitatea unui agent radius nenul pentru
  margini retrase față de obstacole.
- [Nav2 Regulated Pure Pursuit](https://docs.nav2.org/configuration/packages/configuring-regulated-pp.html)
  oferă un fallback stabil cu lookahead și viteză reglate după curbură și
  proximitate; [Nav2 MPPI](https://docs.nav2.org/configuration/packages/configuring-mppic.html)
  este modelul potrivit pentru mii de traiectorii candidate pe un orizont
  scurt.
- [Voyager](https://github.com/MineDojo/Voyager) arată unde este util un LLM:
  curriculum, skill library și feedback iterativ, nu servo motor.
- [DAgger](https://proceedings.mlr.press/v15/ross11a.html) este potrivit pentru
  demonstrațiile manuale: modelul poate învăța un reziduu de stil peste un
  controler sigur, nu să înlocuiască geometria și regulile de siguranță.

SIMA 2 și proiectele vision-only sunt relevante ca cercetare generală, însă nu
sunt alese drept fundație: depind complet de imagine și nu oferă geometria,
determinismul și precizia WorldPack/navmesh cerute aici.

## Decizie

Pipeline-ul țintă este:

`MissionPlanner optional` → `WorldRouteGraph` → `Detour corridor` →
`clearance/semantic smoother` → `MPPI local controller` →
`Regulated Pure Pursuit fallback` → `continuous W + RMB input shaper`.

1. `MovementEngine`, WorldPack-ul, navmesh-ul, simulatorul și memoria de
   experiență rămân independente de client, emulator și Windows.
2. Observația intră numai prin `MovementObservationPort`. Adaptoarele sunt
   externe și interschimbabile: replay determinist, API client-visible exportat
   prin HUD optic validat sau o sursă autorizată a unui mediu privat. Captura nu
   ia decizii și nu devine motor de pathing.
3. Gemma/local AI este opțional și asincron. Poate alege obiective, clasifica
   eșecuri, propune curriculum și selecta skill-uri. Nu comandă W/A/D/RMB la
   20–120 Hz și nu este o dependență pentru mișcare.
4. Controlerul local trebuie să ruleze într-un singur proces persistent.
   Replanificarea nu eliberează inutil W/RMB și nu pierde warm-start-ul,
   estimatorul de heading sau memoria locală.
5. MPPI trebuie să primească geometria topologică corectă, obstacolele și
   timpul real al actuatorului. Dacă planul predictiv nu este valid, fallback-ul
   reglat continuă fluid, fără pivot staționar implicit.
6. Experiențele brute nu expiră și nu sunt șterse. Doar relevanța contextuală
   și confidence-ul se recalculează.

## Poziția față de proiectele publice

Predator are deja o fundație mai generală prin WorldPack standalone, geometrie
3D extrasă din client, semantică de drum și simulare offline. Nu este însă
încă demonstrat mai fluid live decât follower-ul spline public. Superioritatea
va fi revendicată numai după holdout-uri filmate și metrici mai bune, nu după
`ARRIVED` sau teste sintetice izolate.

Metricile de acceptare sunt: rata de sosire, secunde în coliziune/1.000 yd,
RMS/P95 cross-track, inversări mouse/minut, jerk-ul camerei, duty cycle W,
opriri inutile, clearance minim, abatere de la drum și recovery/1.000 yd.

## Ordine de implementare

1. Port de observație și replay adapter.
2. Runtime persistent și sincronizare model–observație–actuator.
3. Geometrie MPPI topologică și obstacole integrate în rollout.
4. Graph global pentru drumuri, hearthstone, portal, barcă și zeppelin.
5. Corpus de simulări + holdout-uri live neschimbate.
6. DAgger/residual style model, apoi Gemma opțional pentru planificare rară.

Rădăcinile mari nu mai sunt legate de litera de disc a stației LAB.
`PERFECT_ASSASSIN_RUNTIME_ROOT` și `PERFECT_ASSASSIN_DEPENDENCIES_ROOT` pot
reloca runtime-ul și dependențele; în lipsa lor se folosesc directoarele sibling
`PerfectAssassin-Runtime` și `PerfectAssassin-Dependencies`.

## Consecință operațională

În LAB, adaptorul optic read-only rămâne permis și este tratat ca senzor
interschimbabil, nu ca „pixel bot”. Dacă el lipsește, trebuie configurată o altă
sursă explicit autorizată; altfel runtime-ul poate rula simulări și replay-uri,
dar va refuza fail-closed să pretindă control live robust.

Nu se implementează anti-detection, bypass Warden sau ascunderea automatizării.
Execuția autonomă rămâne limitată de `ExecutionTargetAuthorization`: realm
privat/LAB ori un mediu de test autorizat, nu public live.

Pentru clientul 2.5.6 se va genera un catalog și un WorldPack separat, identificat
prin build și hash. Texturile sau rendererul modern pot îmbunătăți observația
vizuală, dar nu presupunem că ADT/WMO/collision sunt mai corecte; geometria și
regresiile trebuie comparate înainte de promovare.
