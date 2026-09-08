# Cripta: segment de acceptare, nu durata întregii călătorii

Operatorul cere revenire exclusivă la ieșirea humanlike din Shadow Grave și
raportează maximum 10 s pentru propria ieșire. Referința nu este încă filmată
și sincronizată la același punct de start/final; nu fabricăm o comparație.

## Corecția confirmată

În proba 8544bb3c, 33.570654 s este intervalul dintre prima și ultima observație
post-comandă, până la raza Deathknell. De la observația primei decizii sunt
33.709245 s. STRUCTURE_EGRESS_FLYBY este între cadrele 167–168, la
9.625311–9.667073 s de la observația primei decizii, încă la 2.926001 yd de
reperul geometric. Codul face handoff anticipat pentru continuitatea mersului;
evenimentul nu dovedește ieșirea fizică a corpului.

Scriptul offline `report_structure_egress_timing.py` separă aceste măsuri,
păstrează necunoscut timpul ieșirii complete și nu certifică humanlike sau
comparabilitatea cu referința operatorului. Cinci teste protejează această
distincție, absența evenimentelor și integritatea timpului. Rulat pe jurnalul
real cu hash confirmat; raport ignorat în data/runtime/operator/crypt-egress-timing-20260907.json.

## Acțiune LAB și următoarea probă

Nu erau active procesele de navigație verificate. Resetul canonic și godmode
ON au fost confirmate prin utilitarele LAB; clientul arată Shadow Grave și
personajul în încăperea de start. Serverul este doar setup de test, nu sursă
de percepție. Anti-AFK, camera și v34 nu au fost modificate.

Următoarea probă delimitează filmat: click Start, prima deplasare, apropierea
de scară, virajele și trecerea completă în exterior. Stop după acest segment,
nu călătorie până la Brill. Se păstrează aceeași viteză și același start pentru
comparații; fără speed cheats, viraje temporizate sau waypoint-uri manuale.
Humanlike cere și evitarea împingerii în zid, lipsa oscilațiilor/pivotărilor
nejustificate și compoziție vizuală utilizabilă, nu doar un timp mic.

O singură corecție generală → teste relevante → aceeași probă filmată →
acceptare/respingere. Nu extindem la lume/hunting/alte funcții înaintea acestui
reper. Problemele Z/etaj rămân vizibile, fără valori inventate pentru a trece.

## Rollback și limite

Nicio modificare a motorului de mișcare în acest pas. Instrumentul de raportare
poate fi retras independent; v34 rămâne intact. Resetul de LAB nu dovedește
progres humanlike. Nu există încă o nouă probă filmată sau o corecție acceptată.
