# ADR 0089 — Fuziunea vizuală verificată ca heading principal în TBC 2.4.3

## Decizie

Pentru mișcare în clientul TBC 2.4.3 păstrăm `VISIBLE_CLIENT_HEADING_FUSED`
ca sursa principală de heading atunci când HUD-ul de coordonate nu oferă un
`facing_rad` explicit. Fuziunea folosește predicția continuă a mouse-ului și
markerul vizibil din minimap, cu corecție mică și limitată. Vectorul de
deplasare poate confirma calibrarea inițială o singură dată, dar nu înlocuiește
headingul după ce personajul poate aluneca pe un perete.

La începutul unei ieșiri dintr-o structură se face o probă scurtă pe tangenta
locală a navmesh-ului. Camera rămâne cu pitch stabil; orice drift spre tavan,
dispariție a actorului sau neconcordanță mare oprește controlul și cere
recalibrare bounded. Nu folosim A/D, server truth, citire de memorie sau un
bot extern.

`COORDINATE_HUD_EXACT` rămâne prioritar când există. Opțiunea
`--require-exact-body-heading` rămâne disponibilă pentru cazurile care cer
dovadă exactă, în special combatul.

## Motiv

Run-ul verificat de acum două zile a ajuns la Brill cu
`VISIBLE_CLIENT_HEADING_FUSED` și fără încercări de recuperare. ME-306 a
schimbat calea efectivă spre `MOUSE_INTEGRATED_MINIMAP_FALLBACK`; poziția X/Y a
rămas prezentă, dar headingul vizual nu a mai închis deriva, iar camera a
urcat spre tavan. Refolosim deci mecanismul care a funcționat, adăugând limite
pentru zgomotul minimapului și alunecarea pe obstacole.

## Consecințe

- Clientul țintă rămâne TBC 2.4.3; Anniversary este doar laborator de
  comparație, nu dependență.
- WorldPack, navmesh-ul, egress-ul din Cryptă și ruta veche rămân intacte.
- Toate sursele de heading sunt etichetate cu provenance și confidence.
- Validarea următoare este offline replay și teste; un test live bounded se
  face numai după PASS.
