# Perfect Assassin v0.1

## Copie publică pentru consultare tehnică

Snapshot al codului privat la commitul `addb19a`, publicat pentru review.
Include sursele Predator, Control Center, addon-ul propriu, uneltele native,
contractele, configurațiile de exemplu, testele și documentația urmărite în Git.
Istoricul Git privat nu este inclus; handoff-urile tehnice sunt păstrate.

**Începe aici:** [starea actuală](docs/CURRENT_MOVEMENT_STATUS.md),
[lista de lucru](docs/PREDATOR_BACKLOG.md),
[planul spațial](docs/SPATIAL_AWARENESS_PLAN.md),
[arhitectura](docs/02-architecture.md).

Nu sunt incluse parole, fișiere locale de autentificare, baze de date,
clientul/serverul WoW, WorldPack/navmesh generat, asset-uri licențiate,
addon-uri terțe, jurnale brute, înregistrări video sau mediul Python instalat.
Exemplele de căi locale rămân orientative; numele personal din căile de profil
a fost înlocuit cu `LabUser`. Fixture-urile sintetice din `data/fixtures` sunt incluse.
Identificatorii `perfect-assassin.local` din scheme sunt namespace-uri, nu servicii publice.

Aceasta este o copie pentru analiză, **nu un pachet gata de rulat live**.
Unele teste și unelte de audit necesită datele locale excluse. Rezultatele live
descrise în documentație sunt istorice, nu validate prin publicarea acestei copii.
Navigatorul de referință v34 este un executabil local exclus; sursa nativă
curentă nu trebuie confundată cu acel artefact validat.
Rularea necesită configurarea propriului LAB autorizat; protecțiile de execuție
rămân active. Publicarea nu adaugă o licență nouă și nu acordă drepturi asupra WoW
sau dependențelor terțe.

Bootstrap de proiect pentru **Predator**, un AI player Rogue care învață PvE, PvP, movement și lumea TBC în drumul legitim de la nivelul 1 la 70.

> Terminologie obligatorie: `AI player`, `Rogue Predator`, `Champion`, `LAB clone`. Proiectul descrie un player adaptiv, nu o automatizare repetitivă de farm.

## Ordinea de citire

1. [Project charter](docs/00-project-charter.md)
2. [Guardrails și surse legitime](docs/01-guardrails.md)
3. [Arhitectură și module](docs/02-architecture.md)
4. [Contracte de date](docs/03-data-contracts.md)
5. [Champion, LAB și learning](docs/04-champion-lab-learning.md)
6. [Journal/HUD și replay](docs/05-journal-hud-replay.md)
7. [Milestones M0–M7](docs/06-milestones.md)
8. [Testing, promotion și rollback](docs/07-testing-rollback.md)
9. [Primele taskuri](docs/08-first-implementation-tasks.md)
10. [Decizii blocate și întrebări deschise](docs/09-decisions-and-open-questions.md)
11. [Repository conventions](docs/10-repository-conventions.md)
12. [Architecture decisions](docs/adr/)
13. [TBC LAB bootstrap](docs/11-tbc-lab-bootstrap.md)
14. [Latest LAB bootstrap report](reports/2026-08-22-tbc-lab-bootstrap.md)
15. [M0/M1 Observer slice](docs/12-m0-m1-observer-slice.md)
16. [M0/M1 evidence report](reports/2026-08-22-m0-m1-observer.md)
17. [Capability parity v0.1](reports/2026-08-22-capability-parity-v0.1.md)
18. [TBC 2.4.3 offline addon intake](docs/13-tbc243-addon-offline-intake.md)
19. [PA-017 evidence report](reports/2026-08-22-pa017-tbc243-offline-intake.md)
20. [PA-018 controlled client probe](docs/14-pa018-controlled-client-probe.md)
21. [PA-018 readiness report](reports/2026-08-22-pa018-readiness.md)
22. [PA-019 first live observer capture](reports/2026-08-22-pa019-first-live-observer-capture.md)
23. [PA-020 portable quest observer](docs/15-pa020-portable-quest-observer.md)
24. [PA-020 readiness report](reports/2026-08-22-pa020-readiness.md)
25. [PA-020 first live quest capture](docs/16-pa020-first-live-quest-capture.md)
26. [External LAB client operator ADR](docs/adr/0007-external-lab-client-operator.md)
27. [Away-from-home LAB runbook](docs/17-away-from-home-lab-runbook.md)
28. [Standalone portability](docs/18-standalone-portability.md)
29. [Gear Intelligence și Journey VoiceOver](docs/19-gear-intelligence-and-journey-voiceover.md)
30. [Gear/VoiceOver foundation report](reports/2026-08-22-gear-voiceover-foundation.md)
31. [Movement și pathfinding portabil](docs/20-movement-pathfinding.md)
32. [Movement foundation report](reports/2026-08-22-movement-foundation.md)
33. [Navigation Quality Benchmark](docs/21-navigation-quality-benchmark.md)
34. [Production navigation stack ADR](docs/adr/0012-production-navigation-stack-and-buy-gate.md)
35. [Navigation technology decision report](reports/2026-08-22-navigation-technology-decision.md)
36. [Client integrity/input execution ADR](docs/adr/0013-client-integrity-and-input-execution-boundary.md)
37. [Input execution safety](docs/22-input-execution-safety.md)
38. [Client integrity/input decision report](reports/2026-08-22-client-integrity-input-decision.md)
39. [PA-024B1 pose contract report](reports/2026-08-22-pa024b1-pose-contracts.md)
40. [Execution target authorization](docs/23-execution-target-authorization.md)
41. [Execution target scope report](reports/2026-08-22-execution-target-scope.md)
42. [PTR education dossier](docs/24-ptr-education-dossier.md)
43. [Windows capture și pose-provider intake](docs/25-windows-capture-and-pose-intake.md)
44. [Read-only Windows capture ADR](docs/adr/0014-read-only-windows-capture-boundary.md)
45. [PA-024B1 capture foundation report](reports/2026-08-22-pa024b1-capture-foundation.md)
46. [PA-024B1 exact window-region report](reports/2026-08-22-pa024b1-window-region-probe.md)
47. [PA-024B1 continuous capture report](reports/2026-08-22-pa024b1-continuous-capture.md)
48. [Visible self-coordinate HUD ADR](docs/adr/0015-visible-self-coordinate-hud.md)
49. [PA-024B3 coordinate HUD report](reports/2026-08-22-pa024b3-visible-coordinate-hud.md)
50. [Client-asset world-map calibration ADR](docs/adr/0016-client-asset-world-map-calibration.md)
51. [PA-024B4 world-map calibration report](reports/2026-08-22-pa024b4-client-asset-world-map.md)
52. [Standalone multi-target și multi-instance ADR](docs/adr/0017-standalone-multi-target-and-multi-instance-operation.md)
53. [Predator Pack Hunt party ADR](docs/adr/0018-predator-pack-hunt-party.md)
54. [HUD `0.3.6` layout and live evidence](reports/2026-08-23-pa024b3-hud-layout-036.md)
55. [LAB AFK disconnect disabled](reports/2026-08-23-lab-afk-disconnect-disabled.md)
56. [Existing WoW AI player landscape](reports/2026-08-23-existing-wow-ai-player-landscape.md)
57. [Clean-room prior art and first movement gate ADR](docs/adr/0019-clean-room-prior-art-and-first-movement-gate.md)
58. [Client-asset Recast pipeline and NAV DEBUG ADR](docs/adr/0020-client-asset-navigation-pipeline-and-debug-overlay.md)
59. [PA-024B5 motion calibration report](reports/2026-08-23-pa024b5-motion-calibration.md)
60. [Bounded Execution Gateway ADR](docs/adr/0021-bounded-execution-gateway.md)
61. [PA-024F1 Execution Gateway report](reports/2026-08-23-pa024f1-execution-gateway.md)
62. [Windows scan-code input adapter ADR](docs/adr/0022-windows-scan-code-input-adapter.md)
63. [PA-024F2 Windows input adapter report](reports/2026-08-23-pa024f2-windows-input-adapter.md)
64. [PA-024C navigation contracts report](reports/2026-08-23-pa024c-navigation-contracts.md)
65. [Single-pulse movement authority ADR](docs/adr/0023-single-pulse-movement-authorization-and-runtime-arm.md)
66. [PA-024F3a movement authority report](reports/2026-08-23-pa024f3a-movement-authority-foundation.md)
67. [PA-024F3a first controlled-live proven displacement](reports/2026-08-24-pa024f3a-first-proven-displacement.md)

## Repo tree

```text
perfect-assassin/
├── README.md
├── docs/                 # sursa de adevăr pentru produs și operare
├── contracts/            # JSON Schema versionate
├── config/               # exemple; fără secrete
├── integrations/         # addon/client-facing collectors, fără Brain/execution
├── src/
│   ├── adapter/          # TBC 2.4.3 LAB / Anniversary / viitor target
│   ├── observer/         # client/addon events -> observations
│   ├── capture/          # read-only frame port + deterministic manifest replay
│   ├── brain/            # intent, PvE/PvP, action scoring
│   ├── movement/         # navigation/facing/camera/takeover
│   ├── memory/           # identity, skill, opponent, world, mistakes
│   ├── knowledge/        # Zygor, Wowhead, Armory/inspect gates
│   ├── analysis/         # leveling gear evaluator + local simulation ports
│   ├── narrative/        # VoiceOver cues și Journey reflections
│   ├── journal/          # HUD, diary și decision explanations
│   ├── supervisor/       # diagnose -> candidate patch -> promotion
│   ├── replay/           # deterministic reconstruction/ghost fights
│   └── lab/              # clones, opponents, reset harness
├── tests/                # contract, replay, integration
└── data/fixtures/        # synthetic, never Champion identity history
```

## Primul outcome verificabil

Observer v0.1 trebuie să reconstruiască: „ce informații legitime avea Predatorul la momentul `t`, ce alternative a evaluat și de ce a ales acțiunea”. Nu controlează caracterul în M1.

## Verificare M0/M1

```powershell
.\scripts\Test-M1Observer.ps1
```

Runtime-ul este izolat în `.venv`, iar telemetry/Journals generate local rămân în directoarele `data/*` ignorate de Git.

Pentru intake-ul offline TBC 2.4.3 verificat static și prin fixture:

```powershell
.\scripts\Test-PA017.ps1
```

PA-019 și PA-020, inclusiv quest/spellbook boundaries:

```powershell
.\scripts\Test-PA020.ps1
```

Pentru fazele operaționale finite ale clientului LAB, inclusiv când operatorul uman este plecat:

```powershell
.\scripts\Invoke-LabClientOperator.ps1 -Action Status
```

Acest helper este extern Predatorului, produce checkpoint-uri vizuale și nu oferă movement/combat execution.
