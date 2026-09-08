# AFK observat în client → un singur Space

Stare: implementat; o tranziție controlată verificată în LAB la 2026-09-06.

## Problema confirmată

Guard-ul anterior măsura inactivitatea Windows, nu AFK-ul personajului.
Secvența lui conținea două salturi plus înainte/înapoi. Starea runtime veche
era oprită fail-closed. Interpretul global nu avea dependențele actuale.

## Decizie și limite

- Addonul 0.5.8 observă `UnitIsAFK("player")`; nu trimite input. Un rând
  separat cu 48 biți, versiune și CRC16 transmite starea, secvența, identitatea
  Predator în world, focusul unei casete de text și combat/dead.
- Protocoalele coordonatelor și combatului rămân neschimbate. Observarea AFK
  este opt-in în sursa de captură; navigația nu o activează implicit.
- Două observații proaspete eligibile confirmă AFK. Gateway-ul existent
  trimite numai JUMP/Space, 45 ms. Încercarea este salvată înainte de input;
  un rezultat incert nu provoacă retry. Două observații non-AFK reînarmează.
- Nu există timer de salt periodic sau mișcare înainte/înapoi. `IdleSeconds`
  rămâne acceptat doar pentru compatibilitate, fără efect asupra declanșării.
- Chat/edit focus, meniuri/popup, combat/dead, alt actor, captură nevalidă sau
  un proces cunoscut de navigație/combat blochează saltul. Verificarea
  proceselor nu reprezintă un mutex atomic pentru toate sursele de input.
- Ținta rămâne exact clientul emulatorului local și conexiunea loopback 8085.
  Captura validează identitatea și expirarea fiecărui cadru. Nu există memory
  reading, injecție sau informații server-side folosite drept percepție.
- Reînnoirile de dovezi făcute de CC sunt acceptate numai pentru același
  proces, aceeași fereastră și același actor; validatorul existent verifică
  noua autorizație. Guard-ul nu emite și nu prelungește singur autorizații.
- Opt-in local ignorat de Git: `data/runtime/stay-online/enabled.json`.
  La pornirea CC este lansat guard-ul, cu interpretul proiectului și fără
  fereastră auxiliară. Eșecul pornirii nu împiedică deschiderea CC.
- Sesiunea guard-ului rămâne delimitată la 12 ore implicit (maxim 24 prin
  opțiunea explicită existentă), apoi trebuie relansată. Nu este serviciu
  permanent Windows, nu se conectează automat și nu adoptă un alt client.
  Fără o sesiune de captură validă nu poate interveni, chiar dacă procesul
  guard-ului încă există. CC trebuie păstrat deschis pentru reînnoirile sale.

## Dovezi

423 teste relevante PASS în 18,71 s: codec/politică AFK, captură, addon,
mișcare, lansare movement-only, hartă responsive, prospețime și worker roles.
Un fixture de lansare nu furniza graful cerut de selectorul existent; testul
izolează acum selectorul, testat separat. Nicio protecție runtime slăbită.

Verificare controlată live prin computer-use: după intrarea în world,
strip valid/non-AFK, zero comenzi; chat deschis → input_blocked true.
Comanda `/afk` a afișat mesajul AFK. Guard-ul a înregistrat pulse_count=1,
apoi AFK=false, fără apăsare Space manuală și fără repetare în următoarele
minute. Confirmare prin capturi și stare runtime, nu filmare. Nu este probă
de AFK natural după așteptarea timeout-ului și nici test de anduranță 12 ore.
Reînnoirea aceleiași identități și izolarea pornirii CC au teste offline;
nu este demonstrată încă o sesiune live de mai multe ore.

## Revenire

Oprire cooperativă: `scripts/Stop-LabStayOnlineGuard.ps1`. Pentru a dezactiva
pornirea automată se retrage opt-in-ul local. Addonul precedent real 0.5.7
a fost verificat și copiat înainte de instalare în
`data/runtime/addon-backups/PerfectAssassinObserver-20260906T140553754`.
Hash-urile installerului reflectă exact predecesorul instalat, nu doar HEAD.
La rollback se restaurează acel director și se reîncarcă UI-ul clientului.
Motorul v34 și traseele nu au fost schimbate.
