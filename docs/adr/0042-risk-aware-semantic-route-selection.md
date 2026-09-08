# ADR 0042: Alegerea rutei după timpul estimat și risc observat

## Status

Accepted.

## Context

Un A* pur geometric găsește cel mai mic cost din harta cyan, nu neapărat
drumul potrivit pentru un Rogue level 1. Între Deathknell și Brill, o tăiere
prin teren poate fi mai scurtă în yards, dar poate trece printr-o zonă cu mobi
ostili; o alegere care preferă întotdeauna drumul ar fi la fel de artificială.

Informația live despre entități dinamice este limitată la ce a fost observat
în setul de vizibilitate şi are o valabilitate scurtă. După aceea, poziția
exactă nu mai este folosită ca adevăr curent. Observația rămâne permanent în
jurnalul de experiență şi contribuie doar ca zonă regională de risc. Niciun
traseu nu poate pretinde poziții actuale ale mobilor sau jucătorilor
neobservați la distanță.

## Decizie

`ClientRoadSemanticPlanner` generează din aceleași semantici de drum extrase
din client trei variante generice: `road_backbone`, `balanced` și `shortcut`.
Ele sunt priorități globale, nu comenzi de mișcare și nu conțin nume de zone
sau waypoint-uri desenate pentru o rută anume.

`RiskAwareRoutePolicy` alege varianta cu cel mai mic timp estimat de sosire
într-un buget de risc adaptat la:

1. nivel, HP curent, Stealth disponibil și abilitate de escape;
2. dificultatea statică a terenului și abaterea de la drum;
3. amenințările live observate, fiecare cu rază, severitate, timp de
   observație și expirare, plus experiența permanentă agregată în zone de
   risc; aceasta din urmă nu este un marker live de entitate.

O rută mai lungă este aleasă numai când reduce timpul pierdut estimat prin
amenințările observate. Dacă scurtătura intră în bugetul adaptat și are timp
estimat mai mic, ea este aleasă. După alegerea globală, fiecare segment este
validat de coridorul Detour 3D local înainte de orice propunere de input.

## Consecințe

- Predator nu rămâne blocat într-o regulă „drumul este mereu sigur”.
- Coordonata live expirată nu poate devia permanent o rută ca şi cum ar fi
  actuală; experiența observată nu este ștearsă şi poate influența prudent
  alegerea unei zone.
- Decizia poate fi afișată extern cu alternativele, bugetul și motivul exact.
- Pentru rularea live, capabilitățile și amenințările trebuie să vină din
  observerul autorizat; valori inventate nu activează politica.
