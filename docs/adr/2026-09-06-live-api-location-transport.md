# Nume API live către Control Center — 2026-09-06

## Decizie și limite

`GetZoneText` și `GetSubZoneText` sunt sursele numelor. Addonul publică un
payload separat de coordonate/combat/AFK în spațiul liber al HUD-ului existent.
Nu este OCR și nu utilizează memorie de proces, injecție, server ori bază de
date. OCR-ul existent nu este eliminat. Numele nu sunt hardcodate în emitent.
Acest canal read-only nu acordă input și nu dovedește Z, etaj sau camera fizică.

Coordonatele v3, combat v6 și AFK v1 rămân neschimbate. Decoderul este opțional
în sursa comună; guard-ul AFK nu îl activează. Navigatorul și bridge-ul CC îl
activează în captura lor deja existentă: nu apare o a doua buclă de captură
pentru nume. Plannerul, followerul, camera și regulile combat nu sunt schimbate.

## Contract transport v1

144 octeți, 96 celule RGB de 2×2 puncte UI, pas 3, două rânduri de 48.
Fiecare canal encodează un nibble la nivelul `8 + 16*n`; decoderul acceptă
abatere de cel mult 5 niveluri și verifică CRC16-CCITT-FALSE.

| Offset zero-based | Conținut |
| --- | --- |
| 0–3 | magic D7, versiune 1, secvență coordonate, flags |
| 4–5 | CRC16 al identificatorului sesiunii addon |
| 6–7 | lungimile celor două nume în octeți UTF-8 |
| 8–11 | timpul clientului în ms modulo 2^32, big-endian |
| 12–13 | rezervat, zero |
| 14–77 / 78–141 | regiune / subzonă, maximum 64 octeți fiecare, padding zero |
| 142–143 | CRC16 al primilor 142 octeți |

Flags: bit0 regiune disponibilă, bit1 subzonă disponibilă, bit2 Predator în
world cu context de hartă pregătit, bit3/4 overflow regiune/subzonă. Numele
prea lungi sunt indisponibile, nu tăiate. Stringul gol este distinct de lipsă.
Biții rezervați, paddingul, UTF-8 și caracterele de control sunt validate.
Secvența trebuie să coincidă cu pachetul de coordonate din același cadru.

CRC-ul și tagul de sesiune detectează corupție/schimbări; nu sunt autentificare
și nu exclud coliziunile. Identitatea capturii este legată separat de PID și
timpul de creare al clientului verificat. CC verifică și PID-ul proprietarului
bridge-ului. Două mostre cu timp client în avans sunt necesare pentru publicare.
Duplicatele nu primesc timestamp nou; logoutul, pachetul invalid, schimbarea
tagului și ceasul înapoi invalidează fluxul. Wrap-ul uint32 este acceptat.

## Integrare CC

Bridge-ul publică la circa 1 Hz în diagnosticul existent; în timpul mersului
preia canalul din snapshotul navigatorului, fără captură proprie suplimentară.
CC citește fișiere limitate ca dimensiune, în fundal, maximum o citire simultană
și cel mult una la 0,5 s. Firul UI recalculează vechimea; după 2 s arată date
expirate, chiar dacă cititorul de fișiere s-ar bloca.

Etichetele sunt lângă hartă. Prima amplasare în coloana de comenzi împingea
butoanele în afara suprafeței vizibile; a fost respinsă la verificarea vizuală
și mutată. Nu este un redesign al întregii aplicații.

## Dovezi

- Suita relevantă finală: **423 PASS în 16,12 s**, din `test_location_hud`,
  `test_coordinate_hud`, `test_movement_engine`, `test_stay_online_guard`,
  `test_tbc243_saved_variables`, `test_world_pack_viewer`,
  `test_movement_observation_port`, `test_movement_engine_ui_autonomy`,
  `test_movement_ui_freshness`, `test_movement_map_responsive`. Ruff pentru
  cele patru fișiere noi și verificarea diff-ului trec. Nu este suita integrală.
- Offline: codec cu diacritice, lipsuri, overflow, corupție, structură invalidă,
  schimbări de nume/sesiune, ceas înghețat/înapoi/wrap, identitate CC/client,
  etichete JSON malformate, RGB sintetic la scale 0,8 / 1 / 1,25 / 2.
- LAB live, staționar: addon 0.5.9 instalat cu backup verificat și încărcat prin
  `/console reloadui` (comanda `/reload` nu este acceptată de acest client).
  CC relansat normal; decoderul primește Tirisfal Glades / Deathknell, cu CRC
  valid și ceas client avansând. Confirmat și vizual în CC, nu doar din fișier.
- Eșantionare de 10 s a diagnosticului: 20/20 mostre LIVE, 10 valori distincte
  ale ceasului client, vechime maximă a numelor 1,136 s. Aceasta este vechimea
  observată în fișier, nu un benchmark complet al latenței client–UI.
- Poziția a rămas 1809,58 / 1592,79; motor oprit. Guard-ul AFK continuă RUNNING,
  cu observație validă și fără eroare. Nu s-a declanșat un nou episod AFK.
- Nu s-au efectuat mers, combat, schimbare live de subzonă, probe de alte
  scalări/gamma sau un test de rezistență îndelungat. Aceste limite rămân.

## Instalare și revenire

Installerul păstrează verificarea exactă a celor trei fișiere. Backup local
0.5.8 verificat: `data/runtime/addon-backups/PerfectAssassinObserver-20260906T181449133`.
Testele installerului acoperă upgrade-ul/restaurarea și refuzul fișierelor
modificate; restaurarea nu a fost executată asupra addonului live validat.

Revenire addon: `Install-Tbc243ObserverAddon.ps1 -RestoreLatestVerifiedPrevious
-AcknowledgeLiveHotReload`, numai după verificarea țintei și cu reîncărcare UI
delimitată. Restaurarea codului CC/adaptorului se face prin revert-ul dedicat
al commitului acestei extensii, nu prin resetarea întregului workspace.
Protocolul absent produce nume indisponibile, fără a invalida coordonatele.

Telemetria brută și backupul rămân locale, în afara Git. Navigația rămâne v34;
goal-ul pentru corecția de clearance nu este declarat realizat.
Următorul pas din plan: dovada Z/etaj și incertitudinea, întâi offline.
