# ADR 0018 — Predator Pack / Hunt Party după M7

- Status: accepted-future
- Date: 2026-08-22
- Scope: capabilitate post-M7; fără schimbare în scope-ul v0.1 sau M0–M7

## Context

După ce un Champion termină Predator Journey level 1–70 și execuția individuală
este stabilă, proiectul poate evolua într-o echipă cinematică de cinci AI
players. Formația inițială dorită este:

- patru Rogue Predators;
- un Druid healer capabil de stealth.

Scopul este hunting coordonat, PvP/PvE emergent și o serie video în care fiecare
membru rămâne autonom și explicabil. Această direcție nu justifică scurtarea
drumului actual: Predator Pack este post-M7 și nu adaugă cerințe de execution în
v0.1.

## Decizie

Construim Predator Pack ca orchestrare de squad peste cinci actori autonomi, nu
ca un Brain central care apasă tastele tuturor. Fiecare actor păstrează propriul
Observer, Brain, Movement, memory, Journal și Execution Gateway. `Pack
Coordinator` emite obiective și assignments semantice; actorul local le
evaluează, le poate refuza pentru siguranță și produce propriile action
proposals.

```text
                   Pack Coordinator
                  / shared blackboard \
       squad intent / assignments / coordination
             /       /       |       \       \
        Rogue 1  Rogue 2  Rogue 3  Rogue 4  Druid healer
          |         |        |        |          |
       isolated actor memory + local Brain + local Executor Worker
```

Rosterul inițial este un `SquadProfile` versionat, nu logică hardcodată în
Brain. Ulterior pot exista alte compoziții, dar orice rol nou cere propriile
capabilities, teste și promotion gates.

## Identitate și izolare per actor

Fiecare membru are identitate persistentă și separată:

- un `pack_id` comun formației, plus `actor_id`, `actor_role` și
  `memory_namespace` proprii;
- character/credential alias și target binding propriu;
- progression, opponent memory, Journey și Journal proprii;
- runtime session, arm, client root, PID/HWND, checkpoints și audit proprii;
- Executor Worker, takeover și `release_all` proprii.

Nici coordinatorul și nici alt membru nu scriu direct în memoria actorului.
Blackboard-ul este stare efemeră de coordonare, nu o memorie colectivă care
rescrie biografiile. Lecțiile de squad devin skill artifacts Candidate și ajung
în Stable numai după replay regression, scenarii holdout și promotion explicit.

Un membru poate fi Championul canonic sau o identitate Pack separată, conform
profilului de deployment. Rolul nu se deduce din numele personajului, clasă ori
realm; vine din actor binding-ul autorizat.

## Blackboard fără omnisciență

Blackboard-ul acceptă numai facts care provin dintr-o observație legitimă a
unui client sau din comunicare vizibilă în joc. Fiecare intrare poartă:

- actorul observator și observation/evidence reference;
- provenance, confidence, observed time și expiry/TTL;
- target/build/realm și coordinate space, când este relevant;
- statutul `private_to_actor`, `party_visible` sau `communicated_in_game`;
- dovada comunicării atunci când un fact privat devine cunoscut squad-ului.

Party frames, target markers, combat log, emotes și chat/pings permise sunt
surse numai în măsura în care clientul/addonul le poate vedea legitim. Un fact
văzut doar de Rogue 2 nu apare instantaneu în decizia lui Rogue 4: trebuie să
fie deja party-visible sau să existe un eveniment de comunicare în joc.

Sunt interzise în deciziile Pack-ului:

- server DB coordinates, spawn tables și hidden unit state;
- poziții sau cooldown-uri reconstruite din server-only telemetry;
- unirea instantanee a tuturor viewport-urilor ca și cum fiecare actor ar vedea
  totul;
- păstrarea unui fact expirat ca certitudine curentă.

Ground truth-ul emulatorului poate evalua ulterior coordonarea în LAB, dar nu
intră în blackboard, Coordinator, actor Brain sau Movement.

## Protocolul de coordonare

### Leader election

Squad-ul are un singur leader per `leadership_epoch`. Profilul definește
prioritatea inițială; heartbeat-ul, readiness și capability health pot declanșa
o alegere deterministă. O comandă este acceptată numai dacă poartă epoch-ul
curent. La leader loss, membrii opresc commit-urile noi, păstrează apărarea
locală și aleg un successor; un conflict de epoch produce regroup/safe pause,
nu două planuri concurente.

Leaderul coordonează obiectivul și timing-ul, dar nu poate obliga un actor să
ignore pericolul local, invalidarea targetului sau takeover-ul uman.

### Stealth synchronization

Un engage stealth are faze explicite:

```text
rendezvous -> ready check -> stealth confirmed -> approach windows
           -> commit countdown -> synchronized open sau abort/regroup
```

Ready state include poziție estimată, route confidence, stealth observat,
energy/mana, cooldown readiness, LOS și freshness. Dacă un membru este detectat,
întârziat ori pierde targetul, Coordinatorul recalculează sau abandonează
engage-ul. Nu presupune că toate stealth states sunt identice doar fiindcă a
expirat un timer.

### Formations și rendezvous

Formation intents sunt semantice: spread, trail, pincer, screen healer,
collapse sau disengage. Fiecare actor își calculează traseul și avoidance-ul
local; nu urmează mecanic o coordonată server-side sau un offset rigid.
Rendezvous-urile au zonă de toleranță, deadline, route confidence și fallback,
astfel încât grupul să poată traversa world geometry fără lockstep sau blocaje.

### Target, CC și interrupt assignment

Coordinatorul publică kill target, secondary targets, CC owner, interrupt order
și reassign conditions folosind semantic IDs. Assignment-ul include deadline,
confidence și abort conditions. Actorii confirmă `ready`, `unavailable` sau
`failed`; lipsa confirmării nu este succes presupus. DR, immunities, trinket și
cooldown knowledge provin numai din observații legitime și se degradează în
timp.

### Healer protection

Druidul healer are propriul positioning și survival Brain. Ceilalți membri pot
primi screen/peel/CC/interrupt/escape assignments pe baza facts publicate despre
HP, mana, pressure, LOS și pursuers. Pack-ul păstrează o rută de retragere și un
rendezvous de recovery; healerul nu este tratat ca un punct fix și poate cere
disengage sau stealth reset.

## Recovery și takeover

Coordinatorul are stări explicite pentru member lost, death/corpse run,
disconnect, stale observation, route failure, healer unavailable și split
party. Recovery poate însemna hold, defensive local, regroup, substitute,
corpse rendezvous sau safe stop.

Takeover-ul funcționează per actor și global:

- takeover pe un membru face `release_all` numai workerului său și marchează
  actorul `MANUAL`;
- Coordinatorul nu îi mai atribuie acțiuni până la un hand-back confirmat;
- global takeover/disarm oprește commit-urile squad-ului și eliberează toate
  inputurile;
- pierderea Control Panel-ului/stream-ului urmează politica bounded configurată,
  fără auto-arm sau extinderea capabilităților.

## Replay, Journal și seria video

Fiecare encounter produce un squad replay manifest cu timeline comun și refs
către cele cinci replay-uri individuale. Sunt păstrate leader epochs, orders,
acknowledgements, blackboard diffs, formation transitions, CC/interrupt results,
recovery și takeover events.

ShadowPlay hooks rămân adaptere separate per worker. Coordinatorul poate crea un
marker comun și clip refs per actor pentru synchronized open, kill/death,
healer save, failed ambush, escape, leader change sau cinematic discovery. Un
editor/Control Panel poate compune perspectivele într-un episod fără ca
materialul video să devină input de decizie ori să altereze memoria actorilor.

## Concurență reală

Win32 `SendInput` acționează asupra ferestrei foreground a desktopului
interactiv. Cinci clienți care se luptă simultan nu pot împărți un singur
desktop și păstra gameplay fluid. Deployment-ul Pack cere cinci Executor
Workers pe desktopuri interactive izolate — sesiuni, VM-uri sau hosturi
separate — coordonate de același orchestrator.

Time-slicing-ul ferestrelor pe un desktop rămâne numai pentru teste LAB bounded.
Remote viewing/control folosește Control Panel și stream-uri care păstrează
sesiunile interactive; nu folosește RDP pentru clienții legacy. Tehnologia
concretă de transport va fi aleasă și verificată ca adapter separat.

## Gates înainte de implementare

Predator Pack poate începe numai după:

1. M7 terminat sau demonstrat pe criteriile sale de exit;
2. movement/combat individual stabil și takeover verificat;
3. Execution Gateway multi-instance și cinci workeri izolați validați;
4. contracte versionate pentru squad intent, blackboard și acknowledgements;
5. replay simulator pentru leadership, stale facts, split party și recovery;
6. LAB scenario pack cu evaluare fără server truth în decision path;
7. promotion și rollback independente de Brain-ul individual Stable.

## Consecințe

- v0.1 și milestone-urile M0–M7 rămân neschimbate;
- pack coordination nu diluează autonomia sau identitatea fiecărui Predator;
- seria video poate avea perspective sincronizate și decizii explicabile;
- acțiunile coordonate nu primesc cunoaștere omniscientă;
- costul real include desktopuri interactive izolate și observabilitate per
  worker, nu doar încă patru procese de client;
- eșecul unui actor sau al leaderului are recovery și takeover determinist.

## Legături

- [Milestones M0–M7 și roadmap post-M7](../06-milestones.md)
- [Champion, LAB și learning](../04-champion-lab-learning.md)
- [Predator Journal, HUD și replay](../05-journal-hud-replay.md)
- [ADR 0017 — operare standalone și multi-instance](0017-standalone-multi-target-and-multi-instance-operation.md)
- [ADR 0013 — client integrity și input execution](0013-client-integrity-and-input-execution-boundary.md)
