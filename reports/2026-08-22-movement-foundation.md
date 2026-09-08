# Movement foundation report

Data: 2026-08-22

## Outcome

- ADR 0011 fixează navigația ierarhică standalone și interdicția server GPS pentru Champion.
- `movement.schema.json` contractează MovementGoal și PathProposal fără execution authority.
- Schema respinge un `lab_oracle` path în `decision_context=champion`.
- A* grid planner pur/determinist oferă primul slice verificabil înainte de Recast/Detour.
- Tactical traversal costs pot prefera o rută geometric mai lungă, dar mai sigură.
- Recast Navigation este pin-uit extern la commit `9f4ce64458dfae86e1239c525ddc219c4e9e06f1`, sub licență zlib.

## Evidence boundary

- `contract_tested`: movement goal/path restrictions.
- `planner_unit_tested`: obstacle avoidance, tactical costs, determinism și no-path fail closed.
- Suita completă: 45 tests, toate trecute.
- `dependency_staged`: Recast source/archive/hash.
- Nu există încă navmesh WoW construit, pose provider sau movement live.
- Predator execution rămâne `OBSERVE_ONLY`.

## Next gate

`PA-024B` definește pose observation/capability probes. Apoi un Recast tile fixture intră prin `NavigationMeshPort`; abia după replay/stuck/takeover tests poate exista bounded LAB movement.
