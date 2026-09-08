# ADR 0047: Imaginație de mișcare cu orizont glisant

## Status

Implemented for deterministic LAB/replay; live promotion remains gated by a
filmed holdout journey.

## Context

ADR 0012 a ales deja PA-MPPI ca controller local de producție. Prezenta decizie
fixează modul de execuție asincron, relația dintre simularea offline și cea live
și regula prin care componenta neuronală rămâne sub geometria autoritară.

Un traseu A* complet dovedește conectivitatea, iar controllerul predictiv
existent urmărește fluid coridorul pe un orizont de timp. Niciunul nu compară
însă explicit mai multe viitoare apropiate în timp ce personajul continuă să
alerge: intrare devreme într-o curbă, linie mai largă printr-o poartă, viteză
redusă înaintea unui pod sau detur preventiv în jurul unui actor dinamic.

Rularea a mii de simulări complete înaintea fiecărui control tick ar repeta
aceeași geometrie, ar crește latența și ar putea transforma planificarea într-o
oprire vizibilă. Simulările masive sunt valoroase pentru învățare și regresie,
nu ca barieră sincronă în fața fiecărui pas.

## Decizie

MovementEngine va folosi trei orizonturi legate de același WorldPack:

1. plannerul global A*/semantic alege coridorul mare către destinație;
2. un planner local asincron generează și evaluează un set de traiectorii pe
   următoarele 2–5 secunde, cu distanța adaptată vitezei și confinării;
3. controllerul la 50 ms execută traiectoria publicată, închis în buclă de
   observația reală a poziției și facingului.

Plannerul local primește un snapshot imuabil: coridor, portaluri, pantă,
clearance pentru capsula actorului, obstacole statice, actori dinamici și
incertitudinea observației. Scorul penalizează coliziunea, ieșirea din navmesh,
apropierea de margini, curburile imposibile, inversarea steeringului,
pivoturile, lipsa progresului și riscul semantic. Coliziunea și navmesh-ul sunt
constrângeri ferme, nu simple preferințe.

Workerul simulează continuu și nu are plafon total de traiectorii, timp de
călătorie ori experiențe memorate. Inputul jocului nu așteaptă sincron după o
rundă de calcul: dacă următorul rezultat nu este încă gata, personajul continuă
ultima traiectorie încă validă și workerul își continuă simulările. Publicarea
este atomică, iar planul este invalidat imediat la o schimbare materială a
mediului. Aceasta este protecție anti-lag, nu limită de inteligență.

Rezultatele statice sunt memorate după hash-ul WorldPack/navmesh, intervalul de
coridor, raza capsulei, profilul de viteză și clasa geometrică. Mii sau zeci de
mii de variații rulează offline pentru fiecare situație nouă și alimentează
regresiile. Live se evaluează numai candidații care pot schimba decizia curentă.

Un model neuronal poate ordona candidații, estima mișcarea actorilor sau sugera
costuri semantice. El nu poate declara traversabil un perete, o margine sau un
gol pe care validarea topografică îl respinge. Fallback-ul fără model neuronal
rămâne complet funcțional și determinist.

## Consecințe

- Predatorul anticipează curbe și obstacole fără opriri vizibile.
- Încărcarea live rămâne limitată de timp și poate fi mutată într-un proces
  separat; simularea masivă nu blochează inputul jocului.
- Aceeași tehnologie se aplică tuturor hărților și clienților pentru care există
  un WorldPack valid, fără coordonate sau trasee hardcodate.
- Telemetria va separa numărul de candidați, timpul de planificare, vârsta
  planului activ, motivul invalidării și fallback-ul folosit.

## Implementare verificată

`movement/mppi_steering.py` implementează un optimizer vectorizat NumPy cu
1.000 × 56 eșantioane implicit, model cinematic la 50 ms, warm start,
regularizare path-integrală, constrângeri ferme pentru coridor/clearance și
predicția obstacolelor dinamice. Fațada asincronă are un singur worker, nu
așteaptă în threadul de input, publică atomic și invalidează după hash-ul
coridorului, vârsta planului sau abaterea poziției observate. Fallback-ul
geometric rămâne explicit în telemetrie.

Forma implicită urmează implementarea oficială Nav2 MPPI (batch 1.000, 56 de
pași, `dt=0.05`, o iterație), adaptată la viteză înainte + yaw RMB, nu la un
robot diferențial. Referințe primare:
[Nav2 MPPI Controller](https://github.com/ros-navigation/navigation2/blob/main/nav2_mppi_controller/README.md?plain=1),
[Information Theoretic MPC](https://arxiv.org/abs/1707.02342) și
[MPPI cu covarianță variabilă](https://arxiv.org/abs/1509.01149).

Corpusul real păstrează geometria completă a fiecărui coridor pentru replay și
leagă checkpoint-ul de hash-urile WorldPack-ului, contractului, runnerului și
controllerului. Smoke-ul actual are 300/300 variații trecute, câte 100 pe
Azeroth, Kalimdor și Expansion01. Kalimdor include un hairpin de 114,95°, portal
de 0,595 yd și pantă geometrică maximă de 85,62°; PA-MPPI a avut maximum 1,775
yd cross-track, maximum șase schimbări de sens, zero coliziuni și 86,69% cadre
controlate de MPPI. Acesta este coverage de smoke pe trei coridoare reale, nu
încă acoperirea tuturor celor 2.505 ADT-uri și nici confirmare live.
