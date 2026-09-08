# ADR 0015 — Rolling static-structure horizon for movement preplanning

- Status: accepted
- Date: 2026-08-31
- Extends: ADR 0012 și ADR 0013

## Context

Clientul TBC 2.4.3 poate avea doodad-uri cu coliziune într-un poligon Detour
altfel traversabil. O scanare făcută doar la începutul unei călătorii nu vede
un prop întâlnit mult mai târziu; o scanare a întregii rute ar transforma
WorldPack-ul într-o hartă executabilă rigidă și ar încărca inutil query-ul.
Preplanarea semantică trebuia de asemenea izolată de ceasul pose/control.

## Decizie

1. La fiecare preplan semantic se interoghează doar segmentul imediat
   `current_goal -> next_goal` din indexul static DOODAD. WMO-urile rămân în
   fluxul dedicat de awareness/egress, nu în lista de discuri.
2. Candidatele sunt discuri de clearance bounded, unite cu blocker-ele
   observate și validate de query-ul local Detour. Structura nu devine
   waypoint, tactică sau autoritate de execuție.
3. Bounds-urile AABB sunt folosite pentru selecție, iar raza transmisă este
   limitată la contractul probe-ului; astfel un canopy foarte alungit nu
   blochează fals o șosea apropiată.
4. Query-ul care conține această dovadă este construit înainte de submit-ul
   preplanului; procesul worker primește snapshot-ul immutable al blockerelor.
5. Preplanarea rulează în procese copil fără handle-uri de actuator, astfel
   încât parsing-ul și smoothing-ul să nu concureze cu bucla de captură.

## Consecințe

- props întâlnite târziu, inclusiv carturi/signpost-uri, pot fi ocolite de
  navmesh fără coordonate hardcodate;
- costul și memoria rămân limitate la următorul segment semantic;
- o coliziune necunoscută încă produce recovery bounded și fail-closed, nu o
  promisiune de omnisciență server-side;
- verificarea rămâne offline/replay mai întâi, iar live-ul trebuie să confirme
  separat calitatea capturii și comportamentul în client.
