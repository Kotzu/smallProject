# Fixtures

Date sintetice, clar etichetate. Nu sunt experiențe trăite de Champion și nu pot fi importate în `champion_identity`.

- `level_1_first_kill.raw.json`: login, target, combat start, cast, damage, kill, loot și level-up.
- `level_1_death.raw.json`: encounter PvE încheiat cu moarte observată.
- `server_only_fact.raw.json`: fixture negativ; pipeline-ul trebuie să îl respingă.
- `tbc243_observer_saved_variables.synthetic.lua`: formă data-only a exportului addon; parserul îl citește fără execuție Lua.

Numele, GUID-urile, itemele și timestamps sunt sintetice. Niciun fișier de aici nu provine din Champion, CMaNGOS DB sau un player real.
