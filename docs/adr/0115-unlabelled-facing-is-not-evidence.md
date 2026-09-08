# ADR-0115: Unlabelled facing nu este martor client

## Context

Urmele vechi pot conține `player_facing_rad` fără să păstreze sursa care a
produs valoarea. Câmpul poate fi atunci un heading de cameră sau o valoare
moștenită, nu facing brut al clientului.

## Decizie

Replay-ul acceptă un facing brut numai dacă `client_facing_source` este o sursă
cunoscută și valoarea este prezentă în același cadru. Valorile numerice fără
etichetă sunt ignorate ca dovadă, iar poarta se oprește fail-closed.

## Consecințe

Auditurile istorice nu mai supraestimează calitatea facingului. O urmă veche
poate rămâne utilă pentru diagnostic, dar nu poate dovedi facing live complet.
