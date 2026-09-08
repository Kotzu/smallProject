# 19 — Gear Intelligence și VoiceOver pentru Predator Journey

## Gear Intelligence

Predatorul trebuie să aleagă reward-ul potrivit și să echipeze cel mai bun obiect dintre cele pe care le are, fără omnisciență. Pipeline-ul are două analize complementare:

1. `Leveling Gear Evaluator`: rapid și disponibil permanent; nivel, slot, requirements, weapon DPS/speed, stats, survivability, downtime, PvP utility și valoare.
2. `WoWSims Adapter`: analiză PvE locală mai profundă pentru candidați relevanți și build-uri suportate.

### Availability firewall

Stările unui obiect sunt distincte:

- `observed_equipped`
- `observed_bag`
- `observed_reward_option`
- `researched_only`
- `unknown`

Numai primele trei pot deveni alegere imediată. `researched_only` este knowledge, nu posesie sau reward disponibil.

### Profile de optimizare

Journey folosește implicit `leveling_balanced`, cu scor compus pentru kill speed, survivability, downtime, PvP readiness și valoare economică. WoWSims furnizează metrici PvE, nu scorul final universal.

### Înregistrare în Journal

O analiză păstrează:

- observation/evidence refs;
- target și mechanic profile;
- obiectele candidate și availability;
- gear/talents/level snapshot hash;
- simulator adapter/version/commit;
- encounter assumptions, seed și iterations;
- metrici, confidence și warnings;
- ranking, alegere și motivul respingerii alternativelor.

Rezultatul este `counterfactual_analysis`, nu `champion_lived`.

## VoiceOver și povestea Journey

VoiceOver rulează în client ca strat opțional de prezentare. Pentru `2.4.3` există un player dedicat; sunetele sunt module separate.

Componente planificate:

- `AI_VoiceOver` — player legacy 2.4.3;
- `AI_VoiceOverData_Vanilla` — corpusul Vanilla de bază;
- `AI_VoiceOverData_VanillaExtra` — coverage suplimentar;
- `AI_VoiceOverData_TBC` — quest/gossip din Outland.

### Separarea canalelor

```text
Quest/gossip text -> Observer -> QuestPlanner + Journal + Narrative context
                              \
VoiceOver audio --------------> Stream/clip presentation
```

Predatorul „înțelege” din textul legitim observat, nu din faptul că un MP3 există. Audio-ul face Journey cinematic și poate da timing pentru clip/replay. Dacă textul emulatorului nu corespunde corpusului, questing-ul continuă normal și coverage gap-ul este logat.

### Reacții narative

QuestNarrator poate produce reflecții de tipul „Trebuie să curăț zona de lilieci pentru NPC”, folosind numai textul și contextul legitim observate. Reflecția este marcată `predator_reflection`; nu modifică obiectivul, nu pretinde că este dialog oficial și nu intră în combat loop.

## Ordinea de implementare

1. Închidem gate-ul live `PA-020b` pentru quest/loot/zone observation.
2. Construim `PA-021` QuestPlanner/Route Drift/QuestNarrator read-only.
3. `PA-022A` target fingerprint + adapter negotiation contract.
4. `PA-022B` GearSnapshot/Analysis contracts și availability firewall.
5. `PA-022C` Leveling Gear Evaluator cu fixtures level 1–69.
6. `PA-022D` pin/build local WoWSims și golden Rogue simulations.
7. `PA-022E` Gear Advisor view în Predator Control Panel/Journal.
8. `PA-023A` instalare VoiceOver 2.4.3 într-o probă controlată.
9. `PA-023B` NarrativeCue + clip timing + coverage report.

