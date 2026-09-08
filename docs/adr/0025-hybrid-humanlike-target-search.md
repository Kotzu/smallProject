# ADR 0025 — Căutare hibridă și humanlike a țintelor

- Status: accepted
- Date: 2026-08-24

## Context

`Tab` singur găsește doar unități aflate în raza și ordinea internă ale
clientului. O rotație oarbă nu știe în ce zonă apare un mob, dacă patrulează,
dacă obiectivul este un NPC sau un game object și nici când o zonă a fost deja
căutată suficient.

Clientul TBC 2.4.3 oferă `/target` și `/targetexact` prin secure command
handling. Acestea sunt probe locale de prezență, nu coordonate și nu dovadă că
ținta poate fi atacată. Orice rezultat trebuie confirmat prin target snapshot,
tip, reaction, viață și apoi prin detectorul vizual de bearing.

## Decizie

`HybridTargetSearchPolicy` combină, în această ordine:

1. target curent confirmat de client;
2. detecție vizibilă curentă din nameplate, model, target circle, minimap sau
   tooltip;
3. regiuni probabile din quest context, research extern cu provenance și
   memoria proprie a Predatorului;
4. o singură probă `/targetexact Nume` după intrarea într-o regiune plauzibilă;
5. sweep vizual limitat la opt sectoare;
6. traseu de patrulare observat sau publicat, urmat ca ipoteză;
7. negative evidence și replan către următoarea regiune.

O sursă externă precum Wowhead este un `Knowledge Broker`. Dots și rutele de
patrulare devin priors cu map/build/source/version, nu adevăr despre lumea
curentă. O observație reușită întărește regiunea. Sweep-urile fără rezultat îi
scad confidence. Schimbarea realmului sau a buildului separă memoria dinamică.

Quest log-ul ridică prioritatea numelor, NPC-urilor și obiectelor din obiectiv.
Pentru unități se poate folosi target exact. Pentru game objects, herbs și
mining nodes se folosește exclusiv vederea/minimap/tooltip și `interact` după
confirmarea vizuală; `/targetexact` nu este tratat ca detector universal.

## Scanner addon și overlay

Addonul rămâne read-only. Poate exporta unitatea selectată, focus, mouseover,
quest log, tooltip și starea legitim vizibilă prin API. Nu poate pretinde că
enumeră toate unitățile, obiectele sau resursele din jur și nu furnizează
coordonate pentru entități nevăzute.

Există însă un precedent legitim și foarte util, pe care îl păstrăm explicit:

- un detector de tip `Spy` adaugă playeri într-o listă `Nearby` când numele lor
  apare în combat log, target sau mouseover;
- un tracker de tip `NPCScan` combină nameplates, minimap/mouseover și o probă
  `/targetexact` declanșată prin binding;
- un navigator de tip `Carbonite Punks` păstrează ultima zonă în care un player
  a fost detectat și poate orienta un HUD către acel anchor sau către un
  waypoint de quest/spawn.

Aceste mecanisme formează `EncounterRadar`, o listă externă de urme cu
`entity_kind`, nume, sursă, `first_seen`, `last_seen`, confidence, TTL și
semantica poziției. O poziție are obligatoriu unul dintre sensurile:
`live_visible_bearing`, `last_seen_area`, `observer_position_at_detection` sau
`spawn_prior`. Astfel, săgeata nu prezintă un spawn ori o zonă veche drept
poziție live exactă.

Overlay-ul desenează două tipuri diferite de ghidaj:

- săgeată plină pentru bearing vizual confirmat în frame-ul curent;
- săgeată conturată pentru ultima zonă observată, un patrol waypoint sau un
  spawn prior, împreună cu vârsta urmei și confidence.

Click-ul pe o intrare doar selectează obiectivul de căutare. Pentru unități,
gateway-ul poate încerca binding-ul exact și apoi cere confirmare nouă din
target snapshot. Pentru urme expirate, click-ul produce o rută către zona de
căutare, nu pretinde că unitatea se află încă acolo.

Procesul extern detectează nameplates și elemente vizibile și afișează radarul
de debug într-un overlay care nu intră în captura video. Overlay-ul nu execută
input. Plannerul emite numai o decizie fără execution authority; gateway-ul
poate compila doar familia allowlisted `target_exact`, validată împotriva
newline, slash și alte caractere de comandă.

## Comportament humanlike

Predatorul nu încearcă numele din fiecare punct al hărții. Merge întâi într-un
habitat plauzibil, privește scena, încearcă target exact o dată, caută pe traseul
probabil și abandonează temporar regiunea când dovezile devin slabe. Pe măsură
ce acumulează sightings și traversări, priors-urile proprii ajung să domine
research-ul extern, astfel încât pe traseele familiare merge aproape direct.

## Consecințe

- `/targetexact` accelerează confirmarea locală fără a înlocui navigația.
- Vision și target bearing oferă direcția după confirmarea numelui.
- Questurile și `use object` folosesc aceeași hartă de credință, dar actuatori
  diferiți.
- Server DB, mmaps și spawn state rămân oracle exclusiv pentru evaluarea LAB și
  nu pot intra în decizia Championului.
