# PA-024B4 — Client-asset world-map calibration v0.1

## Outcome

`PASS — strict-profile calibration verified + raw-fact promotion denied + LAB-oracle-validated`

Coordonata proprie normalizată poate fi calibrată în world-map 2D fără server-only knowledge. Implementarea citește un `WorldMapArea.dbc` extern numai prin profilul strict, exact-build și SHA-256-pinned pentru o calibrare eligibilă Champion; fact-ul rezultat rămâne la scope-ul cel mai restrictiv al observației și assetului. Baza emulatorului a fost folosită numai pentru măsurarea erorii.

## Implementat

- parser WDBC strict, data-only, cu layout `<IIIIffffi>`; `map_id` este `uint32`, iar `virtual_map_id` signed;
- profil TBC `2.4.3.8606` validat prin schema versionată, apoi comparat cu pin-urile exacte din adapter;
- rezolvare sigură a `dbc/WorldMapArea.dbc` sub asset root, fără cale absolută, `..` sau symlink/junction care evadează root-ul;
- asset name, SHA-256, client build și build signature verificate exact;
- fingerprint canonic al celor 68 de recorduri și binding-ul HUD `2/25 -> Tirisfal / map 0 / area 85` pin-uite în profilul `0.2.0`;
- loaderul strict de profil produce `client_asset_calibration` / `champion_eligible`;
- încărcarea directă din fișier produce numai `client_asset_calibration` / `lab_evaluation_only`;
- încărcarea directă din bytes produce numai `synthetic_fixture` / `fixture_only`, inclusiv când apelantul își calculează singur hash-ul;
- transformarea cere un `coordinate_hud_observation` v2.0 contract-valid, fresh,
  actor/build/target-bound și legat de `authorization_sha256`; două float-uri
  brute sunt respinse;
- outputul păstrează separat sursa poziției și sursa calibrării, inclusiv session/time/confidence/profile/evidence;
- scope composition nu promovează raw Champion HUD peste `unpromoted_evaluation_only`, LAB peste `lab_evaluation_only` sau replay peste `fixture_only`;
- resolver exact pentru internal map name/map/area IDs, ales numai prin contextul HUD și binding-ul versionat; callerul nu poate substitui zona;
- payloadul HUD este re-decodificat și verificat semantic față de CRC/flags/sequence/poziție/timing;
- transformarea TBC cu axele inversate documentat;
- rezultat 2D fără `z` inventat;
- cuantizare fixă `1/65535`; source uncertainty rămâne `uncharacterized` și nu poate fi declarată de caller;
- tabel, provenance și bindings imutabile după încărcare;
- cazuri negative pentru profil falsificat, asset sintetic, path escape, provenance forgery, hash, header, lungime, string offsets, duplicate IDs, bounds, selector și coordonate invalide.

Verificarea focalizată curentă a trecut `20/20` teste. Include fixture-uri
deterministe, diferența `uint32 map_id` / signed `virtual_map_id`, separarea
trust-ului asset/fact, scope composition, respingerea float-urilor brute,
payload/timing binding, map-context substitution, actor/authorization binding
izolat între clone, imutabilitate și proba opțională cu assetul local exact. Acest număr
descrie numai suita PA-024B4 și nu este prezentat drept rezultat al întregii
suite repository-wide.

## Calibrare Tirisfal

Asset extern:

```text
WorldMapArea.dbc SHA-256 = 918BF402A83BAA78B0D35F0978BC760683291EE8CF48D7CE8C90E3814AA1BC7B
record = Tirisfal / id 20 / map 0 / area 85
loc_left   = 3033.333251953125
loc_right  = -1485.4166259765625
loc_top    = 3837.499755859375
loc_bottom = 824.9999389648438
```

Valorile decodate în proba live inițială HUD `(0.2945601587, 0.6467078660)` au fost reproduse ulterior într-un fixture contract-valid și au produs world `(1889.2924279, 1702.2895708)`. Această regresie numerică nu este prezentată ca o nouă probă live. Martorul LAB read-only a fost `(1889.2700195, 1702.3100586)`: `|dx|=0.0224084`, `|dy|=0.0204880`, iar distanța 2D este `0.03036`. Erorile pe axe sunt sub razele de cuantizare corespunzătoare, aproximativ `0.0229839` pe x și `0.0344759` pe y.

După logout normal, SavedVariables `(0.2946131527, 0.6465227604)` a produs `(1889.8500586, 1702.0501040)`, iar poziția persistată LAB a fost `(1889.8499756, 1702.0500488)`, `online=0`. Diferența a fost `0.0000996` world units.

## Boundary de încredere

- poziția normalizată din HUD rămâne observație proprie client-visible și versionată; nu devine automat pose sau rută;
- numai componenta de calibrare DBC încărcată prin profilul strict este `client_asset_calibration` / `champion_eligible`;
- rezultatul compus al raw HUD Champion + calibrare eligibilă este încă `unpromoted_evaluation_only`;
- orice DBC încărcat direct din fișier este `lab_evaluation_only`, indiferent de hash-ul declarat de apelant;
- orice bytes încărcați direct sunt `synthetic_fixture` / `fixture_only`;
- DB `x/y/z/orientation/online`: `lab_evaluation_only`, niciodată input de decizie;
- `z`: indisponibil din această transformare;
- `execution_authority=false`.
- `WorldMapCoordinate2D` rămâne rezultat local al adapterului; nu este încă un contract de domeniu și nu poate fi consumat de Brain/Movement înainte de pose composition.

## Următorul gate

1. zone transition pe un LAB clone dedicat, fără teleportarea Championului Journey;
2. compunere într-un `PoseObservation` versionat, cu map signature și output contract;
3. proiecție height/navmesh cu uncertainty;
4. integrare în pose fusion, încă read-only.
