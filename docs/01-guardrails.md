# 01 — Guardrails și surse legitime

## Regula de portabilitate

Predator Brain poate decide numai din `ObservationEnvelope` provenit din capabilități pe care targetul declarat le oferă legitim clientului/addonului. LAB poate păstra ground truth separat pentru scoring, dar nu îl introduce în observațiile Brainului.

## Clasificarea informației

| Clasă | Exemple | Poate intra în Brain? |
|---|---|---|
| `client_observed` | combat log, target, cast, buff/debuff, poziție disponibilă, spellbook | Da |
| `legitimate_inspect` | gear/talents numai când API-ul, faction/range și targetul permit | Da |
| `external_cached` | Wowhead consultat între fight-uri | Da, cu sursă și vechime |
| `route_guidance` | pas/waypoint Zygor | Da; Movement decide execuția |
| `predator_memory` | întâlniri și observații reale ale Championului | Da |
| `lab_skill` | policy verificată în clone/replay | Da după promotion; fără amintiri false |
| `server_ground_truth` | spawn intern, patrol path DB, cooldown secret, poziții globale | Nu |

Fiecare fapt are `source`, `observed_at`, `confidence` și opțional `expires_at`. Informația expirată se degradează, nu devine adevăr permanent.

## Knowledge Broker

- **Zygor** este route teacher: furnizează obiective/waypoints; nu este Movement Brain.
- **Wowhead** este consultant pentru quests, rewards, items, spells, talents, consumables și professions. Lookup-ul nu intră în fast combat loop; rezultatul se cache-uiește.
- **Armory/inspect** se folosesc numai când informația este legitim disponibilă targetului curent. LAB Armory poate servi analiză și ground truth, nu omnisciență.

## Brain versus execution

Brain produce `ActionProposal`; un `ExecutionPolicy` separat decide dacă targetul curent permite `observe_only`, `recommend_only`, `movement_only`, `combat_only` sau control complet. Politicile și regulile platformei se reverifică înaintea oricărui target live.

## Client integrity și platform policy

- fără memory read/write, DLL/process hooks, packet injection sau server GPS;
- fără kernel/virtual-HID și fără mecanisme de mascare a inputului;
- actuatorul user-mode este permis pe emulator allowlisted sau PTR autorizat specific, prin capability + bounded approval + runtime arm;
- orice `public_live` oficial, Classic/legacy sau retail, rămâne exclus; numai un PTR separat și autorizat explicit poate fi eligibil;
- o informație sau acțiune disponibilă tehnic nu devine legitimă automat.
