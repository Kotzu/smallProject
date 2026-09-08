# ADR 0087 — Calibrarea orientării înainte de primul pas în navmesh

## Decizie

Înainte de primul `MOVE_FORWARD`, Movement Engine compară orientarea observată
cu tangenta locală a corridor-ului navmesh. Dacă orientarea vine numai dintr-un
fallback ambiguu al minimapului, motorul poate schimba capătul axei doar când
diferența arată clar ca o întoarcere de 180°. Orientarea exactă din HUD nu este
înlocuită.

Aceasta este o regulă generică de aliniere locală. Nu adaugă coordonate de
Cryptă, waypoint-uri scrise manual sau server truth.

## Motiv

WorldPack-ul știe scările, podelele și deschiderea, dar jocul poate raporta o
orientare ambiguă când Predator stă pe loc. O orientare numerică greșită este
tot o orientare greșită: primul W poate împinge personajul în perete.

## Limită

Regula nu dovedește singură că orientarea fizică a camerei și a corpului este
corectă. Dacă HUD-ul exact lipsește și prima coardă de deplasare nu confirmă
tangenta, motorul trebuie să realinieze bounded sau să se oprească fail-closed.

## Dovezi

- testele unitare acoperă flip-ul clar, virajul normal și sursa HUD exactă;
- validatorul semantic și simularea offline nu folosesc input;
- ME-306 a arătat că în client sursa a rămas `MOUSE_INTEGRATED_MINIMAP_FALLBACK`
  și regula de flip nu s-a activat, deci calibrarea fizică rămâne deschisă.
