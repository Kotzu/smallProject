# ADR 0084: Bariere memorate limitate la ieșirea dintr-o structură

## Context

Predator poate păstra discuri de obstacol observate în sesiuni anterioare.
Într-un WMO, un astfel de disc poate fi vechi sau poate descrie chiar locul
din care actorul încearcă să iasă. Dacă este trimis neschimbat la fiecare
cerere Detour, discurile pot închide singure drumul către un portal valid.

## Decizie

Adaptorul `ClientAssetNavmeshQuery` oferă `for_structure_egress()`. Pentru
cele două picioare ale unei propuneri de ieșire, el elimină numai discurile al
căror centru se află în limitele 3D ale aceluiași WMO. Obstacolele din afara
structurii rămân în cerere. Limitele vin din indexul WorldPack, iar portalul
și toate picioarele sunt validate din nou de navmesh-ul clientului.

Navigator-ele de test sau adaptoarele vechi fără această capacitate păstrează
comportamentul anterior; nu se inventează coordonate și nu se acordă
autoritate de execuție.

## Dovezi

- `tests/test_client_navigation_runtime.py`: filtrarea păstrează discurile
  din afara WMO.
- `tests/test_movement_engine.py`: motorul folosește capacitatea opțională
  numai pentru o propunere de egress.
- Reproducerea offline a blocajului de la Crypt cu barierele memorate a ales
  waypoint-ul semantic 1 și portalul `access:7bb73baa2ccf348bb33511f2`, cu
  anchor navmesh la `[1666.710938, 1661.981445, 141.939575]`.
- S-au executat `286` teste țintite, toate verzi. Nu s-a făcut încă o probă
  live după această schimbare.
