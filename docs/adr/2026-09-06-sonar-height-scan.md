# Sonar la patru înălțimi, numai observație

## Motiv și delimitare

Sonda istorică la Z+1,20 yd nu acoperă obiecte joase ori suspendate. Extensia
verifică 16 direcții la Z+0,25 /0,60 /1,20 /1,80 yd, față de originea estimată
Detour. Nu sunt măsurători ale înălțimii corpului și nu certifică volumul
continuu dintre raze/niveluri. Nici suprafața/etajul actorului nu devin confirmate.
Pe pantă, o rază orizontală nu urmează solul; nu certifică traversabilitatea.

## Implementare și izolare

`--spatial-awareness-server` este opt-in. Calea `--awareness-server` păstrează
comportamentul vechi și nu execută scanarea suplimentară. Sonarul CC folosește
un executabil nou, separat de workerul vechi și de v34:
`data/runtime/native-build/pa-nav-height-observer/Debug/pa_nav_probe.exe`.
SHA256: `A19C6947D7BBBE4ECD1702477CF2C3A6BB431A6712BA98DF18DDD678565A1404`.
Hash-ul și WorldPack-ul sunt verificate de observer înaintea folosirii.
Bibliotecile NAMIGATOR rămân cele din build-ul anterior; fără modificări în ele.

Antetul C++ `height_scan.hpp` separă scanarea de sursa razelor pentru teste.
Raza maximă este 12 yd, șapte iterații de căutare binară: cel mult 512
interogări LOS suplimentare per mostră, numai în workerul de fundal. Erorile
sursei se propagă; nu sunt transformate în coliziuni. Nicio buclă nelimitată.
Protocolul păstrează prefixul testat liber și capătul testat blocat. Lățimea
intervalului geometric este cel mult 12/128 =0,09375 yd (plus rotunjirea wire).
Aceasta NU este eroarea totală a localizării sau precizia față de personaj.
Fără hit: capăt blocat null, rază testată 12 yd; nu infinit.

Adaptorul verifică versiunea, sursa, originea egală cu query-ul rezolvat,
ordinea și exact cele 64 raze, valori finite și intervale coerente. Răspuns
vechi fără scanare → necunoscut. Dacă scanarea a fost cerută explicit și
workerul nu o trimite, este eroare, nu fallback tăcut. Raportul sonar păstrează
execution_authority=false și etajul necunoscut. Tabelul CC arată separat
înălțimea fiecărei raze și intervalul, prin aceleași filtre de prospețime.

## Dovezi offline

Build separat VS17/x64 Debug și test CTest PASS: cer liber, piedestal jos,
obstacol suspendat, origine blocată, limita de apeluri și propagarea erorilor.
395 teste Python relevante PASS în 12,02 s, plus 5 local_environment_awareness
PASS în 0,25 s. Nu este întreaga suită a proiectului.

`tools/audit_spatial_height_scan.py` compară workerul anterior și extensia pe
asset-urile clientului, fără comenzi de joc. În cele trei cereri, toate
câmpurile legacy coincid exact; razele de la 1,20 yd coincid cu cele vechi.
Nu este echivalență globală a workerilor și nu este promovare a mersului.

| Interogare de referință | Blocaje la 0,25 /0,60 /1,20 /1,80 yd |
| --- | --- |
| Exterior XY 1809,584 /1592,794, hint Z100 | 2 /1 /0 /0 |
| Criptă XY 1676,370 /1677,467, hint Z121,797 | 12 /12 /12 /12 |
| Același XY, hint Z138,729 | 1 /0 /1 /1 |

În exterior, cel mai apropiat prefix liber de la 0,25 yd este 7,875 yd;
la 0,60 yd este 11,71875 yd. Identitatea obiectelor nu este stabilită; nu
afirmăm că sunt gardurile din screenshot. Primele query-uri ale candidatului
au durat 0,260 /0,313 /0,011 s în această probă, nu un benchmark general.

Integrarea prin observer cu profil/WorldPack verificat: 64 raze noi, 80 rânduri
în modelul CC exterior, raport de 11223 bytes, sub limita cititorului 32768.
WorldPack SHA256: `a9feb578fea082f073effd84415977fa8a760ed2e5b2f8b07a1609215fe56b78`.

## Live și rollback

CC relansat normal și tabul Sonar verificat vizual staționar: razele Z+0,25
afișează blocaje între 7,88–7,97 yd și 11,44–11,53 yd; Z+0,60 afișează
11,72–11,81 yd. Acestea sunt intervale rotunjite de afișare, nu precizie
absolută a actorului. Headerul păstrează etajul neconfirmat; motorul este oprit.
În opt mostre live: toate rapoartele LIVE, 64 raze noi, fără erori, vârsta
poziției sonar 1,219–2,220 s; durata query-ului încălzit 6,29–7,90 ms.
Verificarea computer-use confirmă integrarea vizuală, nu certifică evitarea
obstacolelor în mers. Nu s-a trimis input jocului și nu s-au modificat addonul
sau anti-AFK.
Rollback: revert al acestui commit și restart CC. Executabilul anterior
`pa-nav-spatial-observer` rămâne intact; v34 nu este înlocuit.

Urmează dovada independentă a nivelului vertical, incertitudinea metrică și
verificarea volumului corpului. Patru straturi de raze nu închid aceste cerințe.
