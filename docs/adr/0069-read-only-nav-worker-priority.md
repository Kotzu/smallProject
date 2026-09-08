# ADR-0069 — Prioritate redusă pentru worker-ele navmesh read-only

## Context

Preplanarea semantică și awareness-ul local pornesc procese native pentru
query-uri bounded pe WorldPack. Unele query-uri fac cold tile loads și pot
consuma CPU/IO în același timp cu capture-ul DXGI și controlul la 20 Hz. Trace-ul
live v5 a păstrat două goluri inexplicate; quality gate-ul nu trebuie relaxat ca
acestea să dispară.

## Decizie

Pe Windows, adapterul `ClientAssetNavmeshQuery` și serviciul persistent de
awareness folosesc `CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS` pentru
worker-ele native. Flag-urile sunt detectate prin `getattr`; pe host-uri fără
constante rezultatul este `0`. Nu se schimbă protocolul workerului, limitele de
timeout, izolarea procesului sau autoritatea de execuție.

## Consecințe

- Capture/control primește prioritate relativă față de încărcările read-only.
- Preplanarea poate dura mai mult, dar este deja off-loop și rezultatul rămâne
  aplicabil numai după verificarea `Future.done()` și a contextului curent.
- Nu există acces la memoria clientului, injectare sau input suplimentar.
- Dovada actuală este offline: `239/239` teste focalizate, `1336/1336` full
  suite și semantic validation v49 `PASS`; revalidarea live rămâne o poartă
  separată.
