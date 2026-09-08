# ADR 0016 — Transformarea map-space prin assetul exact al clientului

- Status: accepted
- Date: 2026-08-22
- Scope: PA-024B4, localizare 2D și adaptoare portabile

## Context

HUD-ul Observer furnizează poziția proprie normalizată în harta zonei curente. Recast/Detour și evaluarea rutelor au nevoie de coordonate 2D în sistemul hărții lumii. Baza emulatorului cunoaște poziția exactă, dar această informație este `lab_evaluation_only` și nu poate intra în deciziile Championului.

## Decizie

Transformarea folosește `WorldMapArea.dbc` extras din asseturile exact aceluiași client. Fișierul rămâne extern repository-ului. Eligibilitatea pentru Champion există numai prin loaderul strict de profil: profilul trece `contracts/world-map-area-profile.schema.json`, coincide integral cu pin-urile din adapter, calea relativă se rezolvă sub un asset root explicit, iar asset name, SHA-256, fingerprintul canonic al recordurilor, client build și build signature coincid exact.

Celelalte intrări sunt intenționat mai restrictive:

- bytes furnizați direct, chiar împreună cu propriul lor hash corect, sunt `synthetic_fixture` / `fixture_only`;
- un fișier furnizat direct, chiar hash-pinned de apelant, este `client_asset_calibration` / `lab_evaluation_only`;
- numai assetul încărcat prin profilul strict poate fi `client_asset_calibration` / `champion_eligible`.

`champion_eligible` descrie numai eligibilitatea calibrării din asset. Nu promovează coordonata care urmează să fie transformată și nu este, singură, provenance pentru un fact de poziție.

Adapterul:

- parsează strict containerul WDBC și forma TBC `<IIIIffffi>`, cu 9 câmpuri/36 bytes per record; `map_id` este `uint32`, iar numai `virtual_map_id` este signed;
- leagă prin profil contextul HUD `(continent_index=2, zone_index=25)` de exact `Tirisfal / map 0 / area 85`; transformarea nu primește selectori de hartă de la caller;
- respinge selectorii inexistenți sau ambigui;
- aplică convenția de axe a clientului TBC/CMaNGOS:

```text
world_x = loc_top  + normalized_y * (loc_bottom - loc_top)
world_y = loc_left + normalized_x * (loc_right  - loc_left)
```

Transformarea nu acceptă două float-uri fără identitate. Inputul trebuie să fie
un `coordinate_hud_observation` v2.0 validat prin contract și să poarte
`actor_binding`, `authorization_sha256`, coordinate space, x/y,
observation/frame/session IDs, timp și
freshness, confidence, target/build, scope, profilul sursei și evidence refs.
Adapterul re-decodează `packet_hex`, verifică CRC-ul și egalitatea exactă dintre
payload, flags, sequence, x/y și contextul de hartă publicat. Relațiile monotonic
capture/observation/expiry sunt verificate semantic, nu doar ca formă JSON.
Build signature, client build și target profile trebuie să fie compatibile cu
profilul calibrării.

Cuantizarea este fixată de protocol la `1/65535`; callerul nu poate declara o precizie mai bună. Source uncertainty rămâne `uncharacterized` până când există un profil versionat și dovezi separate. Tabelul, provenance-ul și binding-urile sunt imutabile după construcție.

Rezultatul păstrează separat `calibration` provenance și `position` provenance,
inclusiv hash-ul exact al autorizației sursei, apoi derivă scope-ul cel mai
restrictiv. În contractul curent:

- raw HUD pentru context Champion rămâne `unpromoted_evaluation_only` chiar peste un asset `champion_eligible`;
- observația LAB rămâne `lab_evaluation_only`;
- replay/fixture sau o calibrare fixture devine `fixture_only`.

Nicio ramură curentă nu produce un fact world-map `champion_eligible`. Promovarea aparține unui gate ulterior de pose composition, cu propriul contract și propriile dovezi. Adapterul nu inventează `z`; înălțimea va veni ulterior din proiecția controlată pe navmesh/terrain, cu propria uncertainty.

`WorldMapCoordinate2D` este momentan un rezultat local al adapterului, nu un contract de domeniu consumabil de Brain sau Movement. El nu traversează boundary-ul până când PA-024B2c îl compune într-un `PoseObservation` versionat și validat.

## Separarea LAB

Poziția din baza emulatorului poate compara rezultatul în teste controlate, sub `lab_evaluation_only`. Ea nu este input pentru adapter, pose fusion, movement, memory sau Brain și nu poate completa câmpurile lipsă ale Championului.

## Portabilitate

Fiecare ClientAdapter va avea propriul profil strict, versionat și hash-pinned. Nu includem DBC-uri licențiate în Git și nu presupunem că două build-uri au aceleași bounds, IDs ori nume interne. Un DBC extern arbitrar nu devine eligibil pentru Champion prin simpla furnizare a hash-ului său; un target fără profil acceptat și asset exact rămâne fără această capabilitate.

## Consecințe

- coordonata HUD poate fi transformată determinist local în `wow_world_map_2d`;
- cuantizarea `uint16` este propagată în unități world, nu ascunsă;
- sursa de calibration uncertainty rămâne `uncharacterized` până la măsurare;
- contextul hărții vine exclusiv din binding-ul versionat al profilului;
- fixture-urile și verificările LAB nu pot escalada provenance prin API-urile de încărcare directă;
- float-urile hardcodate nu pot deveni facts de poziție, iar o calibrare eligibilă nu poate ridica scope-ul observației;
- legarea la pose fusion și proiecția pe navmesh sunt gate-uri ulterioare, nu sunt implicite în acest ADR.
