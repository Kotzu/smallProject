# PA-024C — Contractele pipeline-ului de navigație

- Status: contract-only implementat și verificat
- Date: 2026-08-23
- Execution authority: `false`

## Outcome

Boundary-ul dintre asseturile clientului, Recast și vizualizarea NAV DEBUG este
versionat înainte de primul bake real:

- `pgeom v1` descrie geometria neutră per build/map;
- `pnav v1` descrie manifestul navmesh-ului Recast și referă tile-uri binare
  opace prin byte size și SHA-256;
- `NavigationDebugSnapshot v1` transportă numai date de randare top-down pentru
  `OFF | ROUTE | MESH`.

Manifesturile `pgeom` și `pnav` sunt actor-free și reutilizabile între instanțe.
Identitatea actorului și authorization SHA există numai în snapshotul de debug,
care este `render_only=true`, `decision_input=false` și
`execution_authority=false`.

## Trust boundary

- starea asseturilor locale este `candidate_untrusted` și `unpromoted`;
- niciun artifact curent nu poate declara `champion_eligible`;
- `server_ground_truth`, `server_mmap` și `lab_oracle` sunt interzise în
  `pgeom`/`pnav`;
- un debug snapshot oracle este permis numai ca `lab_evaluation_only`;
- Recast este fixat la commitul
  `9f4ce64458dfae86e1239c525ddc219c4e9e06f1`;
- hash-urile canonice detectează modificarea manifestului, geometriei, datelor
  de debug și payloadului binar referit.
- recordurile raw trec prin semantic decoder bounded înainte de integrity;
- `pgeom -> pnav -> debug` cere aceeași identitate build/map/profile/scope și
  aceeași mulțime de tile-uri;
- referințele binare sunt strict `sha256:<digest>`, nu căi de filesystem;
- v1 este blocat integral la `candidate_untrusted` + `unpromoted`;
- formatul `pa-nav-wire-v1` are vector canonic hex/SHA pentru implementarea C++.
- loaderul validează structurile Detour v7 complete — header, vertices,
  `dtPoly`, links, detail mesh/triangles, BV tree și off-mesh connections —
  înainte de orice `addTile` nativ;
- categoriile numerice sunt normalizate identic între schema, semantic decoder
  și wire hash, iar axis declarations sunt legate de matrice;
- byte/node/string/number-lexeme budgets sunt verificate înainte de alocările
  mari sau de `json.loads`.

## Evidence

- navigation contracts: `32/32 PASS`;
- combined execution + Win32 sink + navigation + motion + movement +
  architecture: `116/116 PASS`;
- review independent: CLEAN, inclusiv coruperi `dtPoly/detail/BV/offmesh` și
  cele patru probe finale reproduse separat;
- Python compile și `git diff --check`: PASS;
- nu există încă parser integrat, tile Deathknell, query Detour sau overlay live;
- nu a existat input ori control al clientului.

Acest gate fixează formatul reproductibil; nu pretinde că un navmesh real a fost
deja generat ori că Predatorul s-a deplasat.
