# ADR 0045 — Handoff între journey și combat cu autorități separate

## Status

Acceptat și verificat offline; validarea live rămâne necesară.

## Context

O călătorie autonomă nu poate presupune că lumea rămâne fără combat. Totuși,
Movement Engine și Combat Engine au politici, deadline-uri și autorizări diferite.
Un singur runner care păstrează tastele de mers în timp ce începe să atace ar
încălca separarea dintre propunere și Execution Gateway și ar putea continua un
input vechi după schimbarea stării clientului.

După combat, destinația trebuie continuată fără coordonate speciale pentru zona
în care s-a produs întâlnirea. Pentru modul autonom, reluarea corectă este un
replan al aceleiași destinații semantice din poziția live proaspăt observată.
Pentru o rută authored de operator, `OperatorAuthoredPath` alege cel mai apropiat
punct logic și avansează peste un punct deja atins.

## Decizie

1. `run_navmesh_roaming.py` observă combat HUD la fiecare frame cu coordonate
   valide. Dacă `in_combat=true`, eliberează movementul, tastatura și mouse-look,
   publică `COMBAT_HANDOFF_REQUIRED` și se închide fără autoritate reziduală.
2. Prima observație de la startup are loc înaintea comenzilor idempotente de
   postură sau cameră. Un client deja aflat în combat nu primește mai întâi input
   de navigație.
3. `run_journey_combat_supervisor.py` nu importă și nu deține niciun backend de
   input. El pornește secvențial runnerul de navigație și runnerul de combat,
   fiecare cu acknowledgement-ul și runtime gate-ul propriu.
4. Rezultatele contractate `TARGET_DEFEATED` și `ESCAPED_RISKY_AGGRO` permit
   reluarea automată. Al doilea este valid numai când Combat Engine a urmat
   invers o urmă proaspătă de poziții traversate real, a emis zero acțiuni de
   damage și un frame HUD proaspăt confirmă `in_combat=false`. Timeoutul,
   epuizarea urmei, outputul necontractat, stopul operatorului sau depășirea
   bugetelor opresc fail-closed.
5. După o victorie, supervisorul pornește un runner nou pentru aceeași destinație.
   Acesta citește poziția curentă din client și recalculează ruta; nu primește
   waypoint-uri construite din locul întâlnirii.
6. Starea supervisorului este atomică, validată Draft 2020-12 și păstrează pașii
   NAVIGATION/COMBAT/NAVIGATION ca dovadă read-only, cu
   `execution_authority=false`.
7. Ferestrele copil sunt pornite fără consolă vizibilă pe Windows. Controlul
   Pause/Stop este același fișier operator pentru etapa activă, deci takeover-ul
   nu depinde de ce engine deține temporar execuția.

## Consecințe

- Modul autonom din Control Center folosește supervisorul; butonul manual de
  combat rămâne separat și este refuzat cât timp journey-ul rulează.
- Combatul nu poate „moșteni” taste ținute de Movement Engine.
- Reluarea este generică pentru orice hartă suportată de WorldPack și orice
  destinație semantică; benchmark-ul criptă–Brill nu apare în algoritm.
- Această dovadă este offline. Nu afirmăm încă faptul că tranziția HUD,
  achiziția țintei și reluarea după victorie au fost validate împreună live.
- Regresia completă după integrarea retragerii are 1.068 de teste trecute în
  79,869 s.
