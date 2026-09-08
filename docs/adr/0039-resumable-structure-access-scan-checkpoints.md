# ADR 0039: Checkpointuri resumabile pentru scanarea accesului în structuri

## Status

Accepted.

## Context

Planul generic al WorldPack-ului extins conține 3.324 seed-uri inițiale. O
execuție monolitică ar dura mult, ar repeta munca după orice întrerupere și ar
face dificilă separarea dintre un punct fără navmesh, un punct rezolvat în afara
WMO-ului și o eroare reală a workerului.

Un seed AABB este numai o ipoteză. El nu devine observație de interior doar
pentru că se află matematic în bounds-ul unei clădiri.

## Decizie

`run_structure_access_scan.py` consumă planul în loturi bounded și scrie câte un
checkpoint hash-uit pentru fiecare seed. La reluare verifică toate binding-urile
și sare peste checkpointurile deja valide. Fiecare rezultat este unul dintre:

- `ACCEPTED_CONTAINED_WMO`: Detour a rezolvat punctul, suprafața este WMO și
  indexul confirmă structura așteptată;
- `REJECTED_EXPECTED_STRUCTURE_NOT_CONFIRMED`: există observație, dar nu aparține
  WMO-ului planificat;
- `REJECTED_NO_NAV_POLYGON`: seed-ul nu are poligon navigabil;
- `REJECTED_INCOMPLETE_STATIC_AWARENESS`: Detour a rezolvat seed-ul, dar
  etichetele fizice sau tranzițiile locale sunt incomplete și nu pot fundamenta
  învățarea structurii;
- `PROBE_ERROR`: eroare de worker/runtime care trebuie auditata sau reluată.

Observația locală este un artefact separat validat prin contract și SHA-256.
Checkpointul păstrează numai legătura către el plus probele radiale de coliziune
necesare pentru corroborarea BVH. Niciun rezultat nu acordă execution authority.

Scannerul poate executa explicit între una și patru interogări read-only în
paralel. Limita nu este auto-mărită, iar fiecare future scrie imediat propriul
checkpoint atomic când se încheie; o probă lentă nu ține în memorie rezultatele
deja terminate și o întrerupere păstrează progresul confirmat. Agregarea rămâne
independentă de ordinea în care s-au terminat probele. Execuțiile unattended
folosesc `--fail-on-probe-error`, care păstrează checkpointul de diagnostic și
iese non-zero înainte ca următorul lot să pornească.

`aggregate_structure_access_scan.py` refuză un scope incomplet sau cu
`PROBE_ERROR`. Numai observațiile acceptate intră în `Structure Access Graph`.
Deschiderile sunt grupate după Z-ul geometriei portalului, nu după înălțimea
seed-ului; boundary chains se conectează în 3D pentru a nu fragmenta artificial
ziduri înclinate sau scări.

## Dovezi controlate

Primul scope complet este WMO-ul criptei Deathknell `0:wmo:85944`:

- 27 seed-uri planificate și 27 checkpointuri validate;
- 5 observații `ACCEPTED_CONTAINED_WMO`;
- 19 rezolvări în afara structurii așteptate;
- 3 puncte fără poligon nav;
- 0 erori de worker rămase;
- agregatul final: 13 boundary chains și 4 deschideri geometrice unice;
- coverage `PARTIAL_OBSERVED_COMPONENTS`, nu „clădire complet cartografiată”.

Un defect detectat în timpul probei producea aceeași ieșire de patru ori, câte
una pentru Z-ul fiecărui seed. Testul nou cere gruparea după Z-ul portalului și
agregatul corect a revenit la patru deschideri distincte.

Snapshotul runtime nu este un nume de versiune ales manual. Fișierul
`tirisfal-silverpine-v2-structure-access-graph-current.json` se înlocuiește
atomic numai după ce vechiul graf trece din nou verificarea exactă de WorldPack,
index și worker. Scanarea finală a închis 3.324/3.324 seed-uri și 121/121
structuri eligibile, cu zero erori de worker: 171 observații WMO acceptate, 46
rezultate cu semantică statică incompletă și 148 puncte fără poligon nav. Dintre
structurile complete, 66 au observații confirmate și intră în snapshotul curent:
171 observații, 896 boundary chains și 240 deschideri. Celelalte 55 rămân
explicit complete fără WMO confirmat; nu sunt inventate în graf. Coverage-ul
grafului rămâne `PARTIAL_OBSERVED_COMPONENTS`, fiindcă observația punctuală nu
înseamnă cartografiere exhaustivă a volumului fiecărei clădiri.

## Consecințe

- Scanarea poate continua în loturi mici fără să blocheze UI-ul sau clientul.
- UI-ul consumă un singur snapshot `current`, extins atomic pe măsură ce se
  închid taskuri complete; nu trebuie modificat codul pentru fiecare lot.
- Lipsa navmesh-ului devine coverage evidence, nu eroare ascunsă.
- O întrerupere nu pierde și nu repetă observațiile deja hash-validate.
- Celelalte 120 taskuri eligibile rămân neexecutate și vizibile ca muncă
  restantă; un singur WMO complet nu justifică un claim de coverage global.
