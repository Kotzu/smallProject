# Control Center: prospețimea observațiilor nu se transferă între surse

## Context confirmat

După proba Shadow Grave → Deathknell, procesul motorului ieșise cu ARRIVED,
dar textul secundar afișa încă „Acum: merge”. `_snapshot_with_live_pose`
înlocuia timestamp-ul întregului snapshot cu timestamp-ul poziției noi.
Următorul refresh evalua prospețimea acelei copii, păstrând FOLLOW, camera și
coridorul anterior. Reproducerea offline cu 120 de actualizări / 30 secunde
confirma vechime aparentă zero pentru informația veche de mers.

## Decizie și limite

- Cache separat `raw_movement_snapshot`, alimentat numai de raportul motorului.
  Copia pentru afișare primește poziția live, dar păstrează timpul sursei motor.
  Poziția live are în continuare timestamp separat în `last_live_pose`.
- Prospețimea se verifică pe raportul brut, la fiecare refresh. Raportul
  invalid/lipsă înlocuiește și invalidează raportul precedent, nu îl păstrează.
- Proces ieșit, motor oprit, raport expirat/future-epoch sau anterior noului
  Start: se elimină din afișaj starea/geometry/camera veche și cache-urile de
  awareness asociate. Poziția proaspătă rămâne vizibilă, fără aceste informații.
- Graniță temporală UI la Start pentru a nu adopta un cadru recent din proba
  precedentă. Nu înlocuiește identitatea și autorizarea gateway-ului.
- Textul motorului respectă starea ciclului de execuție și existența procesului,
  nu inferă mișcarea fizică dintr-un FOLLOW istoric. „Motor oprit” nu pretinde
  că utilizatorul nu poate mișca manual personajul.
- Testul staționar reușit este explicit istoric, formulat la trecut, fără a
  pretinde că Predator se află încă în criptă.
- Cache-ul pe mtime și refresh-ul de 250 ms se păstrează. Nu se adaugă polling
  accelerat, proces nou, reconstrucție de navmesh sau relaxare de protecții.

Schimbarea nu modifică controlerul, camera, geometria, contractele de navigație
sau criteriile evaluatorului. Nu rezolvă atingerea zidului/humanlike din criptă.
Nu reprezintă un audit exhaustiv de performanță/stabilitate al aplicației.

## Verificări

343 de teste relevante au trecut împreună în 11,563 secunde: freshness UI,
movement engine, autonomie UI, launch movement-only, stationary pose,
live-trial gate și journey/combat supervisor. Nu s-a rulat întreaga suită
a proiectului și aceste teste offline nu constituie o nouă probă live.

14 teste de regresie noi, executate fără Tk, input sau gateway live: actualizări
repetate, timestamp separat, cadru invalid/lipsă, pierderea observației,
future-epoch, proces ieșit, restart, revenire cu raport valid, cache pe mtime,
stări stopped/starting/paused/stopping și formularea istorică.

Un test vechi pentru godmode OFF apărea de două ori în aceeași clasă; Python
masca prima definiție. Duplicatul contradictoriu a fost eliminat, iar testul
rămas cere ON conform cerinței deja implementate. Comanda godmode nu s-a schimbat.

Verificare UI cu computer-use: închisă instanța veche, relansare prin launcherul
LAB existent; noul Control Center arată „Motor oprit”, poziția live se actualizează,
geometria veche și camera estimată nu mai sunt prezentate ca actuale.
La restart verificarea staționară spune „Nu am verificat încă”. Destinația
Deathknell a fost restabilită; Start nu a fost apăsat. WoW a rămas deschis.

Revenire: revert al commitului acestei corecții, apoi relansarea doar a Control
Center după oprirea oricărei probe. Punct anterior de cod: `71f6ec6`; acesta este
checkpoint, nu versiune Stable certificată. Dovezile live anterioare rămân păstrate.

## Cererea suplimentară: anti-AFK LAB

S-a folosit scriptul existent `scripts/Set-LabStayOnline.ps1 -State On
-PlayerName Predator`. Serverul a confirmat `LAB_STAY_ONLINE_ON:PLAYER=Predator`.
Implementarea LAB existentă blochează activarea AFK și anulează starea AFK
deja activă. Nu trimite taste, nu mișcă personajul și nu modifică inputul Brain.

Protecția aparține sesiunii Player: constructorul o inițializează cu false.
La o nouă intrare în lume trebuie reaplicată, la fel ca verificarea godmode.
Nu s-a introdus un guard de tastatură, serviciu permanent sau auto-login și
nu se pretinde protecție împotriva pierderii rețelei ori opririi serverului.
