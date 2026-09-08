# ADR-0044 — Serviciu standalone pentru structure awareness

## Stare

Acceptat și implementat.

## Context

Full-Azeroth conține 96.024 instanțe structurale. Validarea contractului,
reconstrucția exactă din artefactul `.map`, spatial index-ul și graful de acces
sunt obligatorii înainte ca movement-ul autonom să poată porni. Executarea lor
în procesul Tk făcea Control Center indisponibil zeci de secunde; un thread nu
izola suficient munca CPU-bound.

## Decizie

- `run_structure_awareness_service.py` este un proces headless, read-only și
  fără autoritate de input.
- Procesul verifică exact profilul și conținutul WorldPack, indexul structural,
  Access Graph-ul și hash-ul workerului nativ.
- JSON Schema Draft 2020-12 este evaluat de `jsonschema-rs==0.50.1`; validatorul
  Python păstrează meta-schema, iar verificarea proprie respinge numerele
  non-finite înainte de backend.
- După validare, serviciul emite un receipt mic `READY`, inclusiv identitatea
  semantic gate. Control Center verifică receipt-ul și fișierele mici curente;
  nu devine sursă de adevăr pentru geometrie.
- Query-urile NDJSON `NEARBY` acceptă poziție, Z opțional, rază `0..1000 yd` și
  opțional lista completă de hits. UI cere sumarul de 100 yd; viitorul brain
  standalone poate cere hits fără a încărca toate structurile în GUI.
- Runnerul autonom continuă să-și verifice singur artefactele înainte de input.
  Receipt-ul UI nu poate arma movement-ul și fiecare răspuns declară
  `execution_authority=false`.

## Consecințe

- UI rămâne responsiv din prima secundă, indiferent de mărimea WorldPack-ului.
- Awareness devine reutilizabil de Control Center, overlay, viewer 3D și brain
  fără duplicarea a sute de MB în fiecare proces.
- Crash-ul sau răspunsul invalid al serviciului invalidează readiness-ul și
  menține Start dezactivat.
- Procesul consumă memorie separată cât timp indexul este activ; aceasta este o
  alegere deliberată pentru izolare și poate evolua spre un singur serviciu
  partajat între toate suprafețele externe.

## Dovezi

- Pornire + validare + query + shutdown full-Azeroth: 16,319 s, exit 0.
- Receipt: 96.024 structuri, 1.509 WMO, 4.754 deschideri.
- Control Center: 20/20 mostre `Responding=True`, CPU UI aproximativ 0,5 s.
- Regresie completă: 1.045 teste trecute.
