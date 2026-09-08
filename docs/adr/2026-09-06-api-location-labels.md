# Numele zonei din API, separat de localizare și transport

Status: adaptor și model de prezentare offline implementate; fără instalare
addon, interacțiune cu jocul sau conectare UI în această etapă.

## Confirmat în cod și exportul real

Addonul existent folosește `GetZoneText()` pentru `world_zone` și
`GetSubZoneText()` pentru `world_subzone`. Snapshot-urile sunt cerute inclusiv
la `ZONE_CHANGED`, `ZONE_CHANGED_INDOORS` și `ZONE_CHANGED_NEW_AREA`.
Nu este necesar OCR pentru aceste valori. Nu s-a verificat în această etapă
`GetMinimapZoneText()` și nu se pretinde echivalența exactă, în orice situație,
între alegerea subzonei și textul afișat de frame-ul minimapei.

Importul real din SavedVariables era respins de schema existentă: payload-ul
poziției conținea `player_dead_or_ghost` și `player_ghost`, deja emise de addon,
dar absente din schema de export. Au fost adăugate ca două proprietăți
booleene opționale. Schimbarea este aditivă, păstrează versiunile și
`additionalProperties=false`; nu ignoră toate câmpurile necunoscute.
Nu promovează aceste două stări în fapte noi pentru Brain în acest pas.

După corecție, fișierul real a trecut validatorul și adaptorul: 10 snapshot-uri
de locație. Ultimul: `Tirisfal Glades / Deathknell`, capturat la
2026-09-06 08:34:04 UTC. Este o arhivă veche, NU dovada locației curente.
Nu s-a modificat fișierul clientului, nu s-a cerut reload sau logout.

## Implementare

`client_location_labels.py` modelează zona/subzona, sesiunea, referința
evenimentului și timpii. Sursa SavedVariables oferă `location_labels()` după
validarea existentă a schemei și ordinii evenimentelor. Consumatorii anteriori
ai `events()` rămân neschimbați.

Modelul de prezentare pentru viitorul CC păstrează explicit:

- originea `CLIENT_ADDON_API`, distinctă de transportul arhivă;
- `REPORTED`, `EMPTY` și `UNAVAILABLE` pentru fiecare nume;
- sesiune incompatibilă, date sintetice, viitoare sau vechi;
- `last_recorded_label` separat de `current_label`, acesta din urmă mereu
  indisponibil pentru transportul SavedVariables;
- Z, etaj și identitate geometrică neconfirmate. Numele unei subzone nu
  dovedește suprafața unei încăperi, distanța la zid sau punctul XYZ.

O subzonă goală ori lipsă nu moștenește subzona anterioară. Subzona poate fi
folosită ca etichetă istorică mai specifică, cu fallback la zonă; aceasta
nu este o implementare declarată a textului exact al minimapei.
Importul unui fișier recent nu îl transformă automat într-un flux live.
Etichetele de origine nu autentifică singure un fișier arbitrar modificat.

## Verificare

125 teste relevante PASS în 4,54 s: model nou, import addon, replay/context
spațial, fuziune, dovezi, awareness, limite arhitecturale și guard AFK.
Teste pentru tranziții, text localizat, sesiuni, vechime, lipsuri, stări
booleene și refuzul câmpurilor neaprobate. Verificare statică pe fișierele
noi și diff-check PASS.

O dependență de ordinea suitei a fost găsită în testul AFK pentru pornirea
CC: importa modulul UI doar dacă un alt test adăugase calea. Testul își
declară acum propria cale; codul runtime AFK nu s-a schimbat.

## Următorul pas și rollback

Planul cerut de operator este în `../SPATIAL_AWARENESS_PLAN.md`. Transportul
live trebuie verificat: sursă API nu înseamnă automat că aplicația
externă poate apela API-ul Lua al clientului. Banda de date existentă poate
transporta valori API fără OCR; eliminarea completă a capturii pentru
transport necesită o altă interfață permisă, nu memory reading/injecție.
Nicio astfel de schimbare nu este făcută aici.

Clarificare ulterioară a operatorului: captura nu trebuie eliminată; API
prioritar, OCR ca verificare utilă/fallback, păstrarea oricărui mecanism care
îmbunătățește precizia fluxului client–CC. Pentru cazul prezent, zona este
regiunea Tirisfal Glades, iar subzona este localitatea Deathknell. Câmpurile
trebuie afișate distinct, fără a clasifica toate subzonele drept localități.

Rollback: retragerea noului model și metodei additive. Corecția independentă
a celor două câmpuri de schemă poate fi păstrată pentru compatibilitatea cu
addonul deja instalat. Nu există schimbări de geometrie, mișcare sau UI.
