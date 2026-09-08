# ADR-0097 — Păstrarea bounded a headingului exact după planificare

## Context

Urma live `navmesh-roaming-fe3e7d29-1669-4260-8f2a-5ab7e2d64387` a avut un
heading exact înainte de planificare, apoi refresh-ul imediat de după plan a
trecut la `MOUSE_INTEGRATED_MINIMAP_FALLBACK`. În aceeași felie, abaterea a
crescut, iar runner-ul a ajuns la recalculări repetate și la expirarea armului.
Planificarea nu trimite input, deci corpul nu își schimbă yaw-ul în această
fereastră.

## Decizie

La refresh-ul unic de după planificare, dacă ultima observație a dovedit
`COORDINATE_HUD_EXACT`, runner-ul păstrează valoarea pentru acel refresh atunci
când noua observație nu mai dovedește facing-ul exact. Sursa este etichetată
`COORDINATE_HUD_EXACT_PRESERVED`; nu este prezentată ca dovadă HUD proaspătă și
este respinsă de poarta `--require-exact-body-heading`. Nu se face rearmare și
nu se prelungește această păstrare în bucla de mișcare.

## Consecințe

- Un marker minimap sau un yaw integrat instabil nu mai poate înlocui în tăcere
  headingul exact chiar înainte de primul input.
- Dacă operatorul cere dovadă exactă proaspătă, runner-ul rămâne fail-closed.
- Cazul este verificat offline prin teste unitare; comportamentul live rămâne
  neconfirmat până la o probă bounded, filmată și autorizată explicit.
