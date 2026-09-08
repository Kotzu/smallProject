# 12 — M0/M1 Observer slice

## Scope

Acest milestone implementează numai observare și reconstrucție. Intrarea reală de addon/client rămâne un port neconectat; testele folosesc fixtures sintetice, explicit ne-Champion.

## Boundary-uri executabile

- `adapter`: traduce raw keys către semantic IDs și declară target profile/version.
- `observer`: aplică capability profile și provenance firewall înainte să creeze un `ObservationEnvelope`.
- `brain`: produce numai explicații/candidate read-only; nu produce input.
- `telemetry`: append-only JSONL, cu duplicate event IDs respinse.
- `replay`: validează fiecare record și calculează un hash determinist.
- `lab`: asamblează `EncounterRecord` fără a scrie Champion identity.
- `journal`: generează o proiecție Markdown read-only.

## Capability policy

`available` este permis. `restricted` cere `restriction_evidence` explicit și sursa corectă. `unavailable`, `unknown` și capabilitățile absente sunt respinse. `server_ground_truth` este respins înainte de normalizare și nu apare în contractul de provenance permis.

## Evidență acceptată

Rezultatul acestui slice poate fi etichetat numai `contract_tested` și `replay_tested`. Nu este `lab_integrated` cu un addon real și nu este `controlled_live_verified`.

## Definition of done

Fixture-ul `level_1_first_kill` parcurge adapter → firewall → observer → decision stub → telemetry → encounter → replay → Journal. Testele negative resping server-only facts, capabilități deny-by-default, duplicate telemetry IDs și `lab_derived` în `champion_identity`. Toate deciziile rămân `OBSERVE_ONLY`.
