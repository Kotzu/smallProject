# PA-024B5 — Motion calibration

- Status: implemented, contract/replay verified
- Date: 2026-08-23
- Commit: `3d11e19`
- Execution authority: `false`

## Outcome

PA poate transforma trace-uri sincronizate pose/action într-un model determinist
pentru:

- forward speed în world units/s;
- turn rate în grade/s;
- intervalul input-to-motion pentru forward și turn;
- uncertainty 95% și numărul de intervale/tranziții observabile.

Trace-ul și modelul sunt legate de actor expectation, authorization SHA, target,
client build, build/map signature, coordinate space și același monotonic clock.
Primul format este 2D cu `z` opțional, deoarece observația client-visible curentă
produce WorldMap 2D.

## Trust boundary

- un trace manual LAB rămâne `lab_evaluation_only`;
- un Champion cu actor binding `configured_expected_only` rămâne
  `unpromoted_evaluation_only`;
- `lab_oracle`/`server_ground_truth` pot fi înregistrate numai pentru evaluare și
  sunt refuzate de fitterul folosit la control;
- identități, authorization hashes, clocks ori provenance scopes diferite nu pot
  fi amestecate;
- NaN/Infinity, overflow, clock regression și sync skew subdeclarat sunt refuzate.

## Evidence

- motion calibration: `9/9 PASS`;
- movement planner + architecture + calibration: `16/16 PASS`;
- Python compile și `git diff --check`: PASS;
- nu a existat input live, import server ori control al clientului.

Acesta este modelul/calibration boundary necesar primului displacement gate; nu
este încă dovada că Predatorul s-a deplasat autonom.
