# ADR-0103: Potrivirea sursei brute cu headingul calculat

## Context

Un câmp text separat pentru sursa brută nu este suficient dacă un trace poate
declara `COORDINATE_HUD_EXACT` împreună cu un heading calculat din minimapă.
Într-un astfel de caz, numele ar arăta mai bună dovadă decât există cu adevărat.

## Decision

Poarta `heading_integrity` acceptă doar perechi compatibile:

- `COORDINATE_HUD_EXACT` → `COORDINATE_HUD_EXACT`;
- `MINIMAP_VISION_FALLBACK` → heading vizibil inițial/fuzionat sau
  `MINIMAP_AXIS_FLIP_ORIENTED_TO_CORRIDOR`.

Orice altă combinație devine lipsă de dovadă și nu poate ține inputul. Regula
este pură și lucrează numai cu contractul adapterului, timpul observației și
etichetele de proveniență.

## Consequences

Un trace nu poate trece prin completarea manuală a unui singur câmp. Falsurile
pozitive scad, iar următoarea probă live va spune separat dacă a lipsit
headingul, ancora Predatorului sau captura proaspătă. Nu se citește memoria
clientului și nu se acordă autoritate de execuție.
