# 21 — Navigation Quality Benchmark v0.1

## Scop

Acest benchmark decide dacă navigarea este sigură, robustă, portabilă și naturală. Nu aprobăm movement live fiindcă o rută arată bine într-o singură zonă. Fiecare candidat rulează aceleași replay-uri, seeds, map signatures, perturbări și latency profiles.

## Candidați comparați

1. `fixture_waypoint_follower` — baseline minim, nu candidat de producție;
2. `detour_crowd_baseline` — corridor/crowd baseline;
3. `rvo2_baseline` — dynamic avoidance baseline;
4. `pa_mppi_hybrid` — candidatul de producție.

DetourCrowd/RVO2 versus PA-MPPI compară controlul local. Un backend experimental sub USD 500 poate fi adăugat ulterior prin același port. Nu atribuim controllerului un avantaj produs de un pose oracle diferit.

## Matricea de scenarii

### Static geometry

- traseu lung pe drum și off-road;
- uși, clădiri, garduri și pasaje înguste;
- scări, rampe, poduri, cliffs și water boundaries;
- copaci/obiecte cu collision footprint dificil;
- peșteri, niveluri suprapuse și intrări/ieșiri;
- navmesh tile boundaries, zone transitions și transport links;
- corpse run cu punct de pornire și destinație variabile.

### Dynamic world și event hunt

- quest hub cu 10/25/50 player traces redate determinist;
- player care blochează intermitent o ușă sau un pod;
- trafic în sens opus, grupuri care se opresc și schimbă direcția;
- target cu zig-zag, turn brusc, mount/speed transition;
- line-of-sight break, occlusion și reacquisition;
- combat effects, frame drops și observații întârziate.

### Rogue tactical movement

- intrare în range fără overshoot;
- flank/behind positioning unde mecanica și contextul permit;
- circle/strafe fără oscilație;
- kite/disengage către un safe corridor;
- target switch și party member follow;
- stealth path cu aggro și exposure costs.

### Perception degradation

- coordinate noise și heading noise;
- stale observations la 50/100/200/300 ms;
- dropped capture frames și UI/minimap occlusion;
- camera rotation independentă de body;
- pierderea anchor-ului, `DEGRADED`, `LOST` și relocalizare;
- alt target profile/client build ținut complet ca holdout.

## Metrici obligatorii

### Safety și reliability

- route completion rate;
- unrecovered stuck events/km;
- autonomous recovery rate și p50/p95 time-to-recovery;
- manual interventions/hour;
- navigation-caused fall/death;
- invalid traversal attempts;
- pending-input cancellation latency la takeover;
- movement emitted while pose is `LOST`.

### Efficiency și responsiveness

- travel time/path length versus LAB oracle, numai ca scor evaluator;
- replans/km și corridor reversals/km;
- end-to-end observation-to-intent latency p50/p95/p99;
- frame age, pose drift, heading error și relocalization time;
- controller deadline misses și fallback activations.

### PvP/event hunt

- time-to-contact și target contact uptime;
- preferred-range error;
- line-of-sight retention/reacquisition;
- intercept success pe target maneuvers holdout;
- crowd bottleneck completion și yield/replan quality.

### Naturalness

- curvature, yaw rate, acceleration și jerk distributions;
- key-hold duration și key-tap rate;
- camera/body coupling și stop/turn distributions;
- oscillation/backtracking rate;
- blinded side-by-side rating față de trasee umane consimțite.

Naturalness nu poate compensa un safety failure.

## Hard gates

Aceste reguli nu se negociază:

1. zero input în `LOST`;
2. `MANUAL` anulează toate acțiunile pending în maximum un control cycle;
3. zero server-only facts/waypoints în decision evidence;
4. zero traversal de cliff/water/jump fără capability și link valid;
5. map/build signature mismatch oprește backendul;
6. testul nu modifică Champion identity memory;
7. orice rezultat este etichetat corect: fixture, replay, LAB sau controlled-live.

Pragurile numerice de quality se blochează după human baseline și primul Recast baseline, înainte de optimizare. Nu se ajustează retroactiv pentru a face un candidat să treacă.

## Protocol A/B

```text
freeze scenario + seed + observations + latency profile
                         |
          run every controller/backend candidate
                         |
       collect identical telemetry and video views
                         |
        score safety -> reliability -> quality
                         |
             holdout replay verification
```

- fiecare replay are train/dev/holdout classification;
- tuning-ul nu vede holdout maps, actors sau traces;
- minimum trei rulări pentru orice componentă stochastică;
- failure-ul păstrează clip marker, pose belief, corridor, critic scores și action primitives;
- LAB oracle apare numai în scorer, după închiderea deciziei candidatului;
- build/client/server profiles se raportează separat înainte de un scor agregat.

## Recovery ladder verificată

1. release all + fresh observation;
2. relocalize și camera/body reconciliation;
3. context-valid backstep/strafe;
4. local replan cu obstacle temporar;
5. alternate corridor cu stuck heat cost;
6. global replan;
7. safe stop + manual takeover.

Jump/spin loops și retry infinit sunt failure-uri, nu recovery.

## Commercial component gate

Havok este închis. O componentă eligibilă sub USD 500 primește exact aceeași geometry input, pose stream, local controller și scenario set. Este cumpărată numai dacă trece toate hard gates și rezolvă un blocker confirmat sau produce un improvement material preînregistrat. Un demo propriu al vendorului nu este suficient.

## Ordinea implementării

1. capture/pose contracts și replay recorder;
2. static torture fixtures + Recast corridor baseline;
3. motion calibration și geometric follower fallback;
4. PA-MPPI + deadline telemetry;
5. recovery behavior tree;
6. dynamic player replay și PvP intercept evaluator;
7. human trace baseline și blinded video review;
8. bounded LAB course;
9. numai dacă apare un candidat eligibil: experimental backend adapter.
