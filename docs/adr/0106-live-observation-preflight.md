# ADR-0106: Preflight read-only pentru integrarea live

## Context

Testele offline pot trece cu date curate chiar când clientul live nu oferă o
captură utilizabilă. Urma veche nu separa suficient vederea actorului, headingul
și focusul ferestrei, iar un stop live nu spunea care dintre acestea a lipsit.

## Decision

Înainte de legarea arm-ului F4a, runner-ul publică un record
`live_observation_preflight` validat prin
`contracts/live-observation-preflight.schema.json`. Recordul verifică separat:

- poziția HUD proaspătă și vârsta ei;
- ancora Predatorului și confidence-ul camerei;
- perechea `client_facing_source` / `heading_source`, inclusiv diferența
  body-yaw/camera-yaw când body yaw este exact;
- latența capturii și a observației;
- potrivirea ferestrei foreground cu ținta autorizată.

Un rezultat `REJECTED` nu leagă arm-ul și nu trimite input. Recordul este
diagnostic, are `execution_authority=false` și nu folosește server truth.

## Consequences

Un viitor clip live poate fi clasificat înainte de mers: vedere, heading,
observație veche sau focus. Faptul că preflight-ul este `READY` dovedește doar
că dependențele sunt prezente în acel moment; nu este dovadă de sosire la
Brill și nu promovează profilul actorului la verificat live.
