# 07 — Testing, promotion și rollback

## Pipeline obligatoriu

`proposal -> static/contract checks -> unit tests -> replay regression -> bounded LAB cohort -> safety gates -> approve -> versioned deploy -> smoke test -> monitor`

Champion nu primește niciodată un edit direct. Nici hot parameters nu sar peste teste; hot reload înseamnă reload rapid al unui artifact deja promovat. Schimbările structurale se activează în afara combatului.

## Test gates

1. Provenance: fiecare fact este permis de capability profile.
2. Information firewall: server ground truth nu ajunge în ObservationEnvelope.
3. Determinism: același replay + seed + version produce aceeași decizie.
4. Memory isolation: LAB nu scrie în Champion identity.
5. Portability: Brain rulează cu semantic IDs pe minimum două adapter fixtures.
6. Takeover: `MANUAL` oprește pending actions.
7. Regression: matchup, PvE și movement suites relevante nu scad peste bugetul aprobat.
8. Failure mode: Knowledge/Supervisor indisponibile nu blochează combat loop-ul.
9. Client integrity: memory/kernel/injection capabilities rămân indisponibile pe toate profilele.
10. Deployment policy: emulator/PTR cer realm + client fingerprint, evidence, bounded approval și runtime arm; pending/public-live resping inputul.
11. Pose safety: `LOST`, stale pose sau map/build mismatch nu pot produce movement authorization.
12. Capture privacy: raw pixels nu intră în telemetry; persistence cere hash, classification și retention explicit.
13. Capture portability: replay provider trece fără DXcam/NumPy, iar fiecare backend live este capability-probed separat.
14. Continuous capture: fiecare frame revalidează source înainte/după acquisition; foreground loss, mid-frame geometry change, missing-new-frame, deadline și output mismatch sunt fail-closed.

## Rollback

Fiecare deploy păstrează artifact hash, config, schema, migration, previous Stable și command/procedure de revenire. Auto-rollback la crash loop, schema mismatch, invalid action rate sau safety violation. Performance regression cere review, nu rollback orb.

### Addon TBC 2.4.3: release curent `0.3.6`, previous Stable `0.3.5`

Rollback-ul de versiune al `PerfectAssassinObserver` este explicit și se execută numai cu `Wow.exe` oprit:

```powershell
.\scripts\Install-Tbc243ObserverAddon.ps1 -RestoreLatestVerifiedPrevious
```

Installerul nu acceptă o cale de backup dată de operator. Caută numai în
`data\runtime\addon-backups`, refuză reparse points, directoare imbricate și
fișiere suplimentare, apoi alege cel mai recent backup ale cărui hash-uri sunt
exact previous Stable `0.3.5`:

- `PerfectAssassinObserver.lua`: `F091298093DE17549FF14E184FCD317EA98D40633B8916E81223345297F3D7D6`;
- `PerfectAssassinObserver.toc`: `160BABA2DDC417E0B9C12396C057721AC8D74B753DAEAF0DC78E5A896F613EF8`;
- `README.md`: `426519B0404F3A54CDA112E8925B47F5424ED23CAD3278CD90EFC5B164345759`.

`-UpgradeVerifiedPrevious` acceptă exclusiv acest immediate previous Stable
`0.3.5`; snapshoturi mai vechi sau orice alt set de hash-uri sunt refuzate chiar
dacă au fost la un moment dat versiuni valide. Astfel backup-ul creat este mereu
predecesorul exact al deploymentului `0.3.6` pe care îl înlocuiește.

Înainte să înlocuiască addon-ul, păstrează și verifică exact versiunea curentă
`0.3.6` într-un nou director `PerfectAssassinObserver-current-before-restore-*`.
Copierea este flat și limitată la cele trei artifacts cunoscute; hash-urile
restaurate sunt reverificate după instalare. Dacă schimbarea eșuează după
eliminarea targetului, installerul recuperează `0.3.6` din backup-ul tocmai
verificat și raportează eroarea inițială.

Revenirea controlată la versiunea curentă după testul de rollback folosește:

```powershell
.\scripts\Install-Tbc243ObserverAddon.ps1 -UpgradeVerifiedPrevious
```

`Remove-Tbc243ObserverAddon.ps1` rămâne procedura de dezinstalare completă, nu
înlocuiește rollback-ul versionat.

Artifactul curent `0.3.6` este acceptat numai cu următoarele hash-uri:

- `PerfectAssassinObserver.lua`: `316FC42EC6F9F4EC47F854255865B0BE4C958797ECE81D8213F5817324CCBF2F`;
- `PerfectAssassinObserver.toc`: `761D23A5895210EC713E560A13A3ED7EEA0C44C1901E2C5608E43ABACC924BC9`;
- `README.md`: `552F2D295309B69EFFC0E91B327D7CE7402526C4DBEDB7C5B39AFDC35D9FF40D`.

Secvența curentă de rollback/revenire este strict
`0.3.6 → 0.3.5 → 0.3.6`.

La 2026-08-23, procedura curentă a fost verificată într-un client temporar
izolat prin secvența `0.3.5 → 0.3.6 → 0.3.5 → 0.3.6`. Cele trei artifacts au
fost reverificate prin hash la fiecare frontieră, backup-urile au rămas bounded,
iar sandbox-ul nu a lăsat reziduuri. Dovada live/layout separată pentru release
este în [raportul HUD `0.3.6`](../reports/2026-08-23-pa024b3-hud-layout-036.md).

### Evidence istoric păstrat: release `0.3.5`

La 2026-08-22, procedura a fost verificată end-to-end într-un client temporar
izolat, fără a atinge instalarea reală: un backup cu fișier suplimentar a fost
respins fără mutarea targetului, cel mai recent backup exact `0.3.4` a fost
restaurat, backup-ul pre-restore `0.3.5` a fost reverificat, apoi `0.3.5` a fost
reinstalat cu toate cele trei hash-uri corecte. Sandbox-ul probei a fost șters
după verificare. Instalarea reală nu a participat la mutație, iar verificarea
read-only de după probă a confirmat că a rămas exact `0.3.5` pe toate cele trei
hash-uri.

Un test separat cu failure injectat în timpul copierii backupului a confirmat că
directorul incomplet este curățat înainte de ieșire și targetul instalat rămâne
nemodificat. Cleanup-ul acceptă numai un director flat parțial format din
artifactele cunoscute; o intrare neașteptată ori unsafe blochează operația
non-destructiv, nu este ștearsă automat.

## Evidence

Nu confundăm fixture pass cu joc live. Raportăm separat: `contract_tested`, `replay_tested`, `lab_integrated`, `controlled_live_verified`.
