# Sonar condițional: sesiune, timp și integrare CC

Status: implementat și verificat offline pe WorldPack real, apoi afișare CC
verificată vizual staționar în LAB. Aceasta nu este verificare de navigație.

## Contract și flux

Bridge-ul existent poate primi `--spatial-sonar-profile`. CC îi transmite
profilul hărții selectate; nicio verificare de asset-uri sau query nu rulează
pe firul Tk. `SpatialSonarObserver` folosește un singur job în fundal și un
worker geometric persistent, cu hash verificat, separat de v34. Profilul și
WorldPack-ul sunt verificate prin încărcătorul existent, nu doar citite ca JSON.

Identitatea include PID/timp de creare client, tag sesiune addon și map ID;
raportul păstrează hash WorldPack. Tagul CRC nu este autentificare. Poziția și
numele trebuie să fie proaspete înaintea interogării; rezultatul vechi din
altă sesiune/hartă nu este publicat. Timpul poziției, cererii și rezultatului
rămân separate. Refolosirea rezultatului nu îi schimbă timestamp-ul.
Vârsta maximă a poziției la interogare: 2 s; aplicabilitate afișare: 3 s și
maximum 0,5 yd deplasare XY. Acestea sunt filtre de afișare, nu garanții metrice.

Date: XY de referință, Z sugerat și rezolvat separat, alternative verticale,
maximum 8 limite apropiate și 8 deschideri. Distanța la segment este recalculată
de la originea geometrică rezolvată, nu copiată drept distanță a actorului.
Rămâne explicit condițională de suprafața aleasă. Deschiderile au lățime și
referință geometrică, dar nu tip ușă/scară, înălțime sau destinație inventate.
Raze sparse și lipsa limitelor nu certifică spațiul liber. Entitățile mobile
nu sunt observate de acest canal. Incertitudinea metrică rămâne necunoscută.

Seed-ul generic inițial Z=100 este declarat prior geometric, nu măsurătoare
și nu regulă pentru criptă. La suprafețe suprapuse rezultatul rămâne ambiguu;
încă nu există dovada independentă care alege etajul fizic al actorului.

CC citește datele prin cititorul asincron existent, fără alt capture loop.
Eticheta arată **altitudine estimată**, numărul de candidate și **etaj
neconfirmat**. Erorile workerului sunt în diagnosticul bridge-ului.
Lipsa datelor nu oprește poziția/harta. Protocolul workerului sonar are limită
de așteptare de 5 s; timeout-ul închide workerul, retry după 10 s. Vechea cale
de awareness păstrează timeout-ul implicit neschimbat.

## Clarificare cerută de operator: open world

Altitudinea Z nu este număr de etaj și poate fi mare sau negativă. Înălțimea
plafonului este altă mărime. Dacă sonda verticală nu lovește nimic, raportăm
`NO_HIT_IN_TESTED_SEGMENT`, nici infinit, nici plafon la capătul razei. Cu hit
raportăm doar segment blocat, nu distanță exactă până la plafon. În ambele
cazuri distanța la plafon rămâne null și open-world nu este confirmat numai
de această sondă. Codul nativ verificat testează de la Z+1,20 la Z+12,0 yd;
nu testează întregul cer. Etajul poate deveni neaplicabil numai cu dovadă
separată, nu pe baza altitudinii sau a lipsei unui hit.

## Dovezi și limite

Integrarea offline cu profilul real și workerul pin-uit: 11,313 s la prima
deschidere/verificare, XY din cripta înregistrată, Z rezolvat 121,797379,
candidate 121,670326 / 138,451950, 8 limite și 8 deschideri în raport,
execution_authority=false. Identitatea de client a probei este fixture offline,
nu o nouă localizare live. Nu consumăm date server-side.

Teste: respingere sesiune/hartă diferită, timp vechi/viitor, deplasare XY,
poziție veche cu nume noi, rezultat asincron întârziat, timeout de pipe, distanță
de segment, altitudine mare/negativă și lipsa plafonului fără valori infinite.
Suita relevantă finală: **345 PASS în 11,91 s** (spatial_sonar,
vertical_candidates, location_hud, movement_engine, world_pack_viewer,
movement_map_responsive, stay_online_guard). Ruff pentru fișierele noi și
diff-check trec; aceasta nu este suita completă a proiectului.

CC a fost închis normal și relansat cu motor oprit. La XY 1809,58 / 1592,79,
Tirisfal Glades / Deathknell, a afișat altitudine estimată 98,88 yd și etaj
neconfirmat. Workerul separat a fost observat ca proces copil al bridge-ului.
În 12 mostre la interval de 1 s: status LIVE, nicio eroare sonar, vârstă nume
API 0,038–1,039 s, vârstă poziție sonar 1,238–2,240 s; ceasul clientului a
avansat. Sonarul avea o suprafață candidată, 16 sonde radiale, zero limite/
deschideri în raport; aceste zerouri NU certifică lipsa obstacolelor.
Sonda de plafon: NO_HIT_IN_TESTED_SEGMENT, fără înălțime infinită.
Verificarea vizuală a identificat formularea ambiguă „1 niveluri candidate”;
afișarea folosește acum suprafață/suprafețe candidate și rezultatul separat
al sondei de plafon. Suita relevantă rerulată: **346 PASS în 12,43 s**.
După a doua relansare normală, textul nou a fost observat în CC live:
„1 suprafață candidată”, „Etaj neconfirmat” și „Plafon: nedetectat în segmentul
testat”. Poziția a rămas aceeași, motorul oprit, diagnosticul fără erori.
Distanțele/deschiderile sunt încă metadate, nu panou grafic complet.
Nu s-a schimbat plannerul/controllerul sau addonul; nu s-a rulat mers/combat.
Rollback: revert al commitului dedicat și restart CC; v34 nu este înlocuit.
