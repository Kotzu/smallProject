# ADR-0121 — Candidat Deadmines v3 separat de Stable

## Context

`DeadminesInstance` are terenul clientului TBC 2.4.3.8606 disponibil pentru
extracție, dar WorldPack-ul Stable `tbc243-deadmines-v2` trebuie păstrat
neselectat pentru orice rebuild. Un bake nou trebuie să poată fi inspectat fără
să schimbe profilul folosit de Movement Engine.

## Decizie

Extragem și construim harta numai în `tbc243-full-v3-candidate`, apoi o sigilăm
ca `tbc243-deadmines-candidate-v3`. Catalogul, profilul, indexul WMO/doodad și
rapoartele de calitate sunt artefacte versionate separat. Diagnosticele Recast
rămân vizibile; `COMPLETE_WITH_RECAST_DIAGNOSTICS` nu este promovat automat.
Validatorul geometric independent este obligatoriu înainte de orice promovare.

## Dovezi

- `36/36` dale ADT extrase și `36/36` dale navmesh prezente;
- audit geometric: `PASS`, `36/36`, `0` eșecuri;
- audit bake: `0` dale eșuate, cu `68` erori de contur și `178` avertismente
  Recast;
- index candidat: `12` WMO și `267` doodad;
- WorldPack verificat, fără dependențe runtime și cu
  `execution_authority=false`.

## Consecințe

Candidatul poate fi folosit pentru următoarea rundă de awareness/access scan,
dar nu devine hartă autonomă și nu schimbă ruta Cryptă–Brill. Orice test live
necesită separat confirmare explicită și armare bounded.
