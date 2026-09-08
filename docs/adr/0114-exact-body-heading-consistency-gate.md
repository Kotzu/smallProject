# ADR-0114: Poarta strictă verifică și consistența body heading

## Context

HUD-ul poate furniza un `facing_rad` exact pentru cadrul clientului. Un apelant
poate însă combina accidental acel martor cu un heading păstrat sau integrat de
mouse din alt moment. Faptul că ambele valori există nu dovedește că descriu
aceeași orientare.

## Decizie

În modul `--require-exact-body-heading`, poarta compară headingul folosit de
controller cu `position.facing_rad` din același cadru. O diferență de peste
`0,02 rad` respinge preflight-ul și oprirea strictă înainte de input. Minimapă,
camera și deplasarea rămân estimări bounded și nu sunt promovate ca body yaw
exact.

## Consecințe

Facingul strict este verificabil offline și fail-closed. Modul implicit poate
folosi minimapa ca fallback vizual bounded pentru compatibilitate cu clientul
TBC legacy; asta nu este prezentat drept precizie matematică de body yaw.
