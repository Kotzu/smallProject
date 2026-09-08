# ADR 0041: Proveniență obligatorie pentru orice tile navmesh înlocuit

## Status

Accepted.

## Context

Un bake complet poate avea un tile serializat care trece controlul de număr,
dar produce o regresie reală de rută. Cazul de referință este ieșirea din crypta
Deathknell: un `28_28.nav` corectat dintr-un WorldPack stabil reface ruta, în
timp ce bytes-ii bruti ai bake-ului nou nu trebuie ascunși printr-o simplă
copiere peste fișier.

Un hash aggregate al WorldPack-ului final detectează modificări ulterioare, dar
nu explică de ce un tile diferă de raportul brut de bake și nici nu poate arăta
ce regresie a justificat alegerea.

## Decizie

Pentru o hartă declarată cu coverage `complete`, raportul de calitate enumeră
hash-ul și coordonata fiecărui tile brut. Sigilatorul compară acea listă cu
catalogul final, nu doar cu numărul de fișiere:

1. dacă toate hash-urile coincid, hash-ul aggregate al raportului trebuie să
   coincidă cu cel al catalogului;
2. pentru fiecare diferență este obligatoriu un
   `navmesh_tile_repair_evidence` unic;
3. dovada declară tile-ul brut defect, hash-ul replacementului, hash-ul exact
   al raportului brut, WorldPack-ul sursă verificat și calea artefactului;
4. dovada include aceeași regresie înainte cu rezultat `FAIL` și după cu
   rezultat `PASS`;
5. cele două rezultate sunt copiate în WorldPack, iar manifestul le hashuiește
   cu rolul `NAVMESH_TILE_REPAIR_REGRESSION`;
6. o dovadă pentru un tile neschimbat, o dovadă în plus, un hash neconform sau
   un artifact de regresie lipsă oprește sigilarea.

`build_navmesh_tile_repair_evidence.py` nu acceptă declarații manuale: verifică
catalogul final, raportul brut, manifestul și bytes-ii WorldPack-ului sursă,
precum și rezultatele JSON FAIL/PASS înainte de a produce dovada portabilă.
La redeschiderea offline, verificatorul recalculează relația dintre raport,
catalog, tile-ul final și artefactele de regresie; un manifest recalculat peste
o dovadă modificată este respins.

## Consecințe

- O corecție locală a criptei rămâne permisă, dar nu devine hardcoding ascuns.
- Pachetul final poate fi auditat offline fără client, emulator sau server.
- Orice tile corectat după bake devine o schimbare explicită și regresabilă.
- Procesul se aplică identic pentru construcții, intrări, garduri și interioare
  ale oricărei hărți, nu doar pentru Deathknell.
