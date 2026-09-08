# Test suites

- `contract`: schemas, provenance, capability allow/deny și memory isolation.
- `replay`: round-trip, deterministic decisions și counterfactual fixtures.
- `integration`: vertical slices bounded; rezultatul nu implică automat verificare live.

Toate testele folosesc fixtures sintetice până când un mediu controlat este aprobat și etichetat separat.

Rulare locală după instalarea mediului:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Suite-ul M0/M1 verifică schemele, deny-by-default, provenance firewall, restricții inspect, semantic portability, append-only IDs, replay determinist, isolation memory și ambele rezultate PvE sintetice.

PA-017 adaugă verificarea statică a addon-ului 2.4.3, parserul SavedVariables neexecutabil, respingerea expresiilor Lua și pipeline-ul offline complet. Rulare: `scripts\Test-PA017.ps1`.
