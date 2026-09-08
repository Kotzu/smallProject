# Mersul din Control Center nu pornește automat combatul

Data: 2026-09-05. Stare: implementat, validare offline; fără promovare live.

## Context

Butonul principal din tab-ul Mers pornea supervisorul cu un buget de 24 de
handoff-uri de combat, permitea continuarea prin aggro și dezactiva protecția
LAB. Aceste efecte nu erau clare din denumirea butonului și amestecau proba de
navigație cu alte comportamente. Utilizatorul a cerut continuarea stabilizării
și separarea clară a funcției reale a acestui Start.

## Decizie

- Clarificare explicită a utilizatorului după prima implementare: aggro este
  permis în testele de mers; nu este permisiune pentru atacuri automate.
- Butonul principal se numește `PORNEȘTE MERSUL`; explicația precizează
  continuarea prin aggro în testele LAB cu godmode și lupta pornită separat.
- Folosim supervisorul existent, cu `--maximum-combat-handoffs 0` și
  `--continue-through-routine-aggro`. Nu introducem un alt controler și nu
  eliminăm pragul existent de viață sau verificările de observație.
- Înainte de armarea mersului, `Set-LabCombatProtection.ps1 -State On
  -PlayerName Predator` trebuie să obțină confirmare de la serverul local.
  La eșec, nu se lansează copilul de navigație.
- La fiecare intrare în lume condusă de agent, se confirmă mai întâi că
  Predator este în world și se activează/verifică godmode prin aceeași comandă.
  `Login` și `EnterWorld` nu sunt echivalente. Nu există un monitor nou care
  să garanteze aplicarea instantanee la loginuri manuale din afara fluxului;
  Start revalidează protecția inclusiv după o reconectare manuală.
- Tab-ul de combat rămâne separat; finalizarea lui nu mai dezactivează automat
  godmode, conform cererii utilizatorului pentru testele LAB.
- Nu schimbăm observarea poziției, camera, navmesh-ul, MPPI, memoria sau
  reînnoirea armării. Oprirea și aprobarea explicită rămân obligatorii.
- Numele istoric `--acknowledge-autonomous-journey-combat` este păstrat pentru
  compatibilitatea parserului; nu anulează bugetul explicit zero de combat.

## Verificare

Testul de integrare execută metoda reală de lansare a UI, capturează comanda
în loc să pornească procese și o trece prin parserul/supervisorul real.
Copilul de navigație este simulat: întâi cere continuarea navigației, apoi
handoff explicit de combat (nu simplu aggro). Rezultatul trebuie să fie
`STOPPED_COMBAT_BUDGET`, cu zero
combat și numai două apeluri către copilul de navigație. Sunt verificate și
armarea absentă, anularea și înlocuirea sesiunii, confirmarea obligatorie a
godmode-ului și absența dezactivării automate. Flag-ul pentru aggro trebuie
să ajungă până la copilul de navigație. Nicio comandă nu ajunge la WoW sau la
server în aceste teste.

## Limite și revenire

Aceasta nu demonstrează că Predator evită fizic toate obstacolele. Proba live
ME503 rămâne de făcut cu autorizare explicită și condiții de test documentate.
Aggro obișnuit nu oprește testul dacă observația și pragul de viață rămân valide.
O cerere explicită de handoff de combat rămâne o oprire, fără atac automat.

Prima separare a fost salvată în `fef2cc1`; aceea oprea și la aggro, comportament
corectat după clarificarea utilizatorului. `046312a` este versiunea anterioară
care permitea combat automat. Revenirea nu trebuie făcută în timpul unei probe active. Nicio instanță
Control Center deja deschisă nu a fost relansată în această etapă.
