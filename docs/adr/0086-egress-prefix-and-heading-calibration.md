# ADR 0086: Prefix verificat și calibrare bounded pentru egress

## Context

În Crypt, prima cerere către un marcaj semantic poate fi `partial` pe podeaua
inferioară, deși frontiera are o continuare validă către scări. Clientul TBC
poate raporta temporar un heading vizual vechi după primul chord W.

## Decizie

Runner-ul păstrează prefixul navmesh deja verificat și îl unește cu un plan
complet de staging/egress. Nu inventează puncte: prefixul și continuarea vin
din WorldPack și din navmesh-ul client.

După o realiniere acceptată din displacement, heading-ul integrat rămâne
autoritar pentru un număr mic și fix de cadre. Un heading exact din HUD îl
poate înlocui imediat; fallback-ul minimap nu poate întrerupe calibrarea.

## Dovezi

- Testele runner verifică păstrarea prefixului partial și realinierea bounded.
- Validarea semantică ME-303 este `PASS` pentru Crypt→Brill și
  Deathknell→Brill.
- Monte Carlo ME-303: șase scenarii `100/100`, fără coliziuni sau eșecuri de
  calitate.

## Consecințe

Planul offline nu mai aruncă o frontieră bună doar pentru că primul tile este
incomplet. Verificarea offline nu dovedește controlul fizic live; acesta
rămâne bounded și cere o aprobare runtime proaspătă.
