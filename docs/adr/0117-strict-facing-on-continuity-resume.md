# ADR-0117: Facing strict la reluarea navigației

## Status

Accepted — 2026-09-03

## Context

O felie nouă de navigație poate porni după un stop, o moarte sau recuperarea
corpse-ului. Dacă acea cale folosește doar flagurile generale de continuitate,
există riscul să uite verificarea body yaw-ului exact și să reia mersul dintr-un
heading estimat.

## Decision

`run_navigation_continuity.py` adaugă `--require-exact-body-heading` la fiecare
comandă către runner. Reluarea păstrează aceeași poartă ca prima felie:
facing-ul HUD exact trebuie să existe și să coincidă cu headingul controllerului
înainte de orice nou input.

## Consequences

- O reluare fără facing exact se oprește în siguranță.
- Nu se reutilizează un heading vechi doar pentru a continua drumul.
- Dovada și testele rămân offline; autoritatea live nu este lărgită.
