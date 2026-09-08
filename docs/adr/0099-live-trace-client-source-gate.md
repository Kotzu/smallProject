# ADR-0099 — Sursă brută obligatorie pentru dovada live

## Context

Testele offline pot reproduce fuziunea headingului cu valori deja curate. O
urmă live poate însă să aibă poziție și `player_facing_rad`, dar să nu spună
din ce observație a venit facing-ul. În acest caz nu putem deosebi un facing
vizibil al clientului de o estimare internă sau de o urmă veche incompletă.

## Decizie

`evaluate_live_steering_trace` raportează pentru fiecare urmă câte cadre au o
`client_facing_source` utilizabilă și câte sunt incomplete. Câmpul lipsă și
valoarea explicită `UNAVAILABLE` sunt tratate la fel. Modul diagnostic rămâne
compatibil cu urmele istorice; opțiunea strictă
`require_client_facing_source=True`, expusă de script prin
`--require-client-facing-source`, respinge o dovadă live incompletă.

## Consecințe

Un rezultat offline poate rămâne util pentru depanare, dar nu mai poate fi
confundat cu dovadă live completă. Urmele noi trebuie să păstreze sursa brută
pe fiecare cadru. Regula nu pornește clientul, nu trimite input și nu folosește
server truth.
