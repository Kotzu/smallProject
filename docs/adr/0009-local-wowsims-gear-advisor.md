# ADR 0009 — WoWSims local ca analist PvE și gear advisor

- Status: accepted
- Date: 2026-08-22

## Context

Predator Journey este predominant PvE până la nivelul 70. Predatorul trebuie să compare quest rewards și să echipeze cel mai bun obiect dintre cele legitim disponibile, păstrând explicația și ipotezele folosite.

WoWSims are un simulator Rogue și poate rula local, dar este orientat în principal spre modele PvE controlate. Rezultatul brut nu reprezintă singur leveling speed, survivability, downtime, PvP utility sau valoare economică.

## Decizie

Integrarea se face printr-un port intern `PveSimulationPort`; Brain-ul nu importă WoWSims și Control Panel nu scrapează UI-ul.

```text
Legitimate Gear Snapshot
        -> Target Compatibility Adapter
        -> Leveling Gear Evaluator
        -> PveSimulationPort
        -> Local WoWSims Adapter
        -> GearAnalysisResult
        -> Journal / Gear Advisor / Decision candidate
```

Folosim proiectul activ `wowsims/tbc-new`, pin-uit la un commit verificat, cu licența și atribuirea păstrate. UI-ul original poate fi expus local pentru operator; consumul Predatorului se face prin contract structurat și versiune de simulator înregistrată.

Profilul implicit pentru Journey este `leveling_balanced`. Profilele inițiale sunt:

- `leveling_balanced`
- `pve_sustained`
- `pve_burst`
- `pvp_opener`
- `pvp_survival`

WoWSims contribuie la scorurile PvE. `Leveling Gear Evaluator` completează nivelurile 1–69 și factorii care nu sunt modelați suficient de simulator.

Un obiect poate fi analizat ca disponibil numai dacă provine din equipment/bags observate, reward-uri afișate legitim sau altă disponibilitate confirmată. Cunoașterea externă despre un obiect nu îl face disponibil.

## Consecințe

- Fiecare rezultat păstrează target profile, simulator build/commit, input hash, iterations/seed, encounter assumptions, metrici și confidence.
- Rezultatele sunt counterfactuale, nu experiențe trăite de Champion.
- 2.4.3 LAB și Anniversary au politici/calibrare separate.
- Înainte de folosire sub nivelul 70 trebuie demonstrat ce niveluri și mecanici modelează corect simulatorul.
- Dacă simulatorul nu este disponibil, combatul și alegerea bounded continuă prin evaluatorul local, cu confidence redus.

