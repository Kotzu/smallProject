# Audit Movement Engine — 2026-09-02

Acest document separă dovada offline de comportamentul care încă trebuie
verificat în clientul live TBC 2.4.3. `PASS` înseamnă că există o verificare
directă; `PARTIAL` înseamnă că există doar o parte din dovadă; `PENDING`
înseamnă că nu am pornit încă testul cerut.

| Cerință | Stare | Dovadă curentă |
|---|---|---|
| 1. Heading fused offline | PASS | `VISIBLE_CLIENT_HEADING_FUSED` rămâne prioritar și în calibrarea bounded; ME-354 reconstruiește offline `419/419` cadre cu `replayed_fused_fraction=1.0` și corecție maximă `0,25 rad`; ME-355 protejează prin test păstrarea post-plan `COORDINATE_HUD_EXACT_PRESERVED`; ME-356 verifică suplimentar că mouse-only și headingul păstrat nu trec preflight-ul; ME-361 cere și martorul brut client-facing în replay, chiar dacă yaw-ul camerei este numeric; ME-367 respinge și combinația exact HUD + heading controller divergent; ME-368 ignoră valorile numerice fără sursă cunoscută; ME-370 cere reverificarea facingului exact înaintea fiecărui cadru de mers; ME-353 arată că urma veche a folosit fallback după plan, motiv pentru care nu este dovadă pentru runnerul nou |
| 2. Body yaw separat de camera yaw | PASS offline | ME-343 păstrează `player_facing_rad` ca facing brut al canalului client, dar completează `body_yaw_observation_rad`/`body_camera_yaw_delta_rad` numai pentru `COORDINATE_HUD_EXACT`; minimapa singură nu poate trece poarta strictă ME-335; ME-367 cere ca body yaw exact și headingul folosit să coincidă în același cadru; ME-370 repetă această verificare înaintea fiecărui nou input |
| 3. Calibrare scurtă, bounded | PASS | calibrarea primei corzi și limitele din runner; fuziunea vizibilă nu mai este suprascrisă în fereastră |
| 4. Oprire când Predator dispare / camera urcă | PASS offline, profil v2 candidat | `PlayerActorDetector` v2 cu rollback v1, deadline bounded `12 ms`, eșantionare 4K `sample_stride=4` și fallback de eroare cu dimensiuni reale (ME-380), preflight explicit pentru actor/cameră, poarta fail-closed și teste; v2 încă nu este verificat live |
| 5. Fără wall-slide, A/D sau server truth ca heading | PASS | firewall, contracte și teste de regresie |
| 6. Cryptă, egress și curbe | PARTIAL | ME-345 revalidează offline pe WorldPack Tirisfal v2 toate cele patru direcții Crypt/Deathknell↔Brill; ME-365 revalidează fresh aceleași rute cu profilul Azeroth actual (`PASS`, 131/131 și 117/117 etape) și păstrează holdout-ul de reset; ME-369 arată pe Shadowfang complet că smoke-ul de 4 tile-uri nu era suficient (`15/25` coridoare rezolvate, `5` quality failures); ME-370 face facingul exact o poartă per-cadru în calea normală; stabilitatea live încă nu este demonstrată; ME-353 confirmă în urma veche pierderea headingului exact după plan și fallback-ul minimapă; ME-337 oprește acum controlul când headingul vizual devine prea vechi |
| 7. WorldPack topografic pentru toate zonele | PARTIAL | auditul curent ME-346 confirmă `83/83` identități, `35` în queue, `6` queue-uri complete, `7` topografice și `1` autonomă; profilul Tirisfal v2 este verificat și folosit în ME-345; ME-350 arată copia nouă Karazhan `5/9` tile-uri, dar ME-351 și ME-352 verifică WorldPack v3 existent cu Karazhan `9/9` și binding runtime corect; auditul combinat ME-363 are `8` queue-uri complete, dar `7` topographic-ready deoarece Monastery este candidat nelegat; ME-358 adaugă candidate Razorfen Downs `24/24` cu geometrie `PASS` și WorldPack sigilat separat, ME-359 trece steering-ul pe toate tile-urile, iar ME-360 adaugă indexul structural și scanarea fail-closed fără WMO confirmat; ME-362 adaugă candidate MonasteryInstances `36/36` și steering `3.600/3.600`; ME-364 adaugă indexul Monastery cu `4` WMO și graph de acces `PARTIAL_OBSERVED_COMPONENTS` (`15` observații, `43` opening-uri), fără promovare; ME-366 adaugă Stratholme `20/20` geometric, dar steering-ul are `9` quality failures și MPPI `14/100`, deci rămâne nepromovat; ME-381 continuă loturile candidate, ME-382 duce Kalimdor la `16.639/40.794` și `360` observații, ME-384 duce Expansion01 la `15.000/47.170` și `282` observații, iar ME-385 duce Kalimdor la `17.639/40.794` și `368` observații, toate cu `0` erori, dar încă parțiale; candidate-urile au diagnostice Recast și încă nu sunt promovate; restul rămân în coada de extracție/semantici |
| 8. Traineri, quest-uri, NPC-uri și mobi cu provenance | PARTIAL | catalog RouteTeacher Alliance/Horde și `3.255` intrări NPCData; ME-349 reconfirmă arhiva Anniversary și hash-urile; ME-357 reconfirmă `11.686/11.686` candidaturi Zygor transformate, după ignorarea coordonatei comentate Black Temple; ME-386 validează unificat `14.914` intrări, toate cu provenance/confidence, și marchează explicit `STATIC_SOURCE_CANDIDATE`; pozițiile dinamice cer observație client |
| 9. Destinații multiple și loop-uri | PASS offline | replay-ul Crypt→Brill→Crypt și testele de secvență |
| 10. Replay-uri și teste offline | PASS | suita completă după ME-387 `1516/1516 OK` și testele heading-integrity; ME-359 adaugă corpus Razorfen Downs `24/24` coridoare și `2.400/2.400` trial-uri fără quality failure; ME-362 adaugă MonasteryInstances `36/36` coridoare și `3.600/3.600` trial-uri; ME-364 adaugă scanarea structurală Monastery `126/126` seed-uri, `0` erori și graph parțial cu `15` observații; ME-365 revalidează ruta Cryptă–Brill–Cryptă și holdout-ul de reset (`PASS`); ME-366 păstrează Stratholme nepromovat după steering; ME-368 rulează replay pe trei urme păstrate și confirmă `0` cadre cu sursă brută completă; ME-369 rulează Shadowfang complet pe `25/25` tile-uri și păstrează candidate-ul nepromovat după `121` query failures și `5` quality failures; replay heading ME-354 reconstruiește `419/419` cadre, iar evaluatorul live strict se oprește la lipsa dovezii client; ME-361 respinge explicit camera-yaw fără martor facing brut; ME-367 verifică și neconcordanța exact HUD/controller; ME-370 verifică poarta exactă per-cadru și lansatoarele strict; ME-380 verifică captura 4K `3643x2093` cu `3/3 VISIBLE` la eșantionare bounded `stride=4` și elimină diagnosticul fals `1x1`; ME-386 validează unificat `14.914` intrări Zygor și politica de confirmare client; allowlist-ul de surse și potrivirea perechii sunt aliniate cu evaluatorul; matricea deadline-ului actorului nu are erori la `10/12/16 ms`; preflight-ul este validat prin contract; raportul strict ME-335 (`me335-live-trace-quality-strict.json`) identifică `419/419` cadre fără sursă brută, separare body/cameră și integritate cameră în urma veche; WorldPack Tirisfal v2 și cele patru rute Crypt/Deathknell↔Brill `PASS` în ME-345; auditul registry/queue ME-346, ME-363 și verificările WorldPack v3 ME-351/ME-352 rămân consistente și `execution_authority=false` |
| 11. Stop după PASS offline, fără live automat | PASS | nu s-a reîncărcat addonul și nu s-a trimis input |
| 12. O singură probă live filmată, fără combat | FAIL-CLOSED, fără combat | ME-379: confirmarea explicită a fost folosită pe emulatorul local; destinația corectată `settlement:brill` s-a oprit `CAMERA_ACTOR_LOST` înainte de primul cadru continuu (`0` cadre), fără combat și fără sosire demonstrată. Clipul asociat este negru; ME-380 arată că `1x1` era fallback de jurnal după timeout, nu dimensiunea capturii. Nu se repetă fără confirmare nouă |

Actualizare ME-388: lotul Expansion01 este acum la `16.000/47.170` probe,
`316` observații, `562` structuri complete și `0` erori; graful v16 are
`1.294` deschideri și `2.850` frontiere. Starea rămâne partială și
`execution_authority=false`.

Actualizare ME-389: lotul Expansion01 este acum la `17.000/47.170` probe,
`336` observații, `594` structuri complete și `0` erori; graful v17 are
`1.387` deschideri și `3.057` frontiere. Starea rămâne partială și
`execution_authority=false`.

Actualizare ME-390: lotul Expansion01 este acum la `18.000/47.170` probe,
`351` observații, `630` structuri complete și `0` erori; graful v18 are
`1.450` deschideri și `3.173` frontiere. Starea rămâne partială și
`execution_authority=false`.

Observația live cea mai importantă este pauza de `9,341 s` dintre cadrele 27 și
28. Ea a apărut în recalcularea sincronă după o abatere mică, nu în verificarea
offline a WorldPack-ului. Runner-ul evită acum acea recalculare sub `2,0`
yarzi și scrie separat timpul de captură, timpul total de observație și sursa
brută a facing-ului. Urma veche ME-328 nu are acest ultim câmp, deci rămâne
incompletă pentru verificarea sursei live.

Evaluatorul are acum și o poartă strictă pentru această lipsă: câmpul
`client_facing_source` trebuie să fie o sursă emisă de runtime și să aibă yaw
brut finit pe fiecare cadru. Modul diagnostic poate citi urme vechi, dar nu le
numește complete.

În ME-333, evaluatorul strict cere și `camera_integrity_state=VISIBLE` cu
confidence de cel puțin `0,55` pe fiecare cadru. Aplicat urmei vechi, rezultatul
este `0/419` cadre complete și eșec explicit `missing_camera_integrity`.
Aceasta verifică aceeași regulă pe care runtime-ul o folosește deja pentru a
elibera controlul când ancora vizuală a Predatorului dispare. Nu este o
pretinsă dovadă despre pitch-ul intern al camerei și nu pornește live-ul.

ME-335 verifică suplimentar că delta body/cameră este calculată corect și că
confidence-ul camerei rămâne în `[0,55, 1,0]`. ME-338 verifică și că sursa
brută se potrivește cu headingul calculat; replay-ul vechi se oprește la primul
cadru fără dovadă, fără să pretindă că a observat clientul live. Auditul nu
acordă autonomie live și nu schimbă limitele de input.

ME-343 a făcut separarea efectivă în runner și în evaluator: un marker de
minimapă rămâne `player_facing_rad` pentru fuziunea vizibilă, dar nu este
înregistrat drept body yaw exact. Această dovadă este offline; proba live
rămâne `PENDING`.

ME-357 reconfirmă auditul Zygor pe sursa locală proaspăt extrasă. Parserul ignoră
acum rândurile de comentariu, astfel încât cele `11.686` coordonate active sunt
transformate complet și nu mai apare o falsă lipsă pentru Black Temple. Datele
rămân statice, cu provenance, fără autoritate de input; pozițiile dinamice cer
observație client.

ME-371 a comparat offline PA-MPPI cu geometria pe cinci coridoare Shadowfang:
`28_30` și `28_31` au trecut `100%`, `28_32` `98%`, un coridor a regresat la
`40%`, iar unul a avut doar `85/100` încercări complete. Candidate-ul MPPI nu
este promovat și nu schimbă Stable sau registry.

ME-372 verifică faptul că și reluarea de continuitate cere facing HUD exact
înainte de mers; nu există downgrade la heading de cameră după un stop sau o
recuperare de corpse. Suportul rămâne offline și fail-closed.

ME-373 verifică aceeași regulă în hunting: atât intrarea în regiune, cât și
fiecare punct de patrulare cer facing exact înainte de mers. Suportul este
offline și fail-closed.

ME-374 revalidează fresh Cryptă–Brill–Cryptă după această întărire: cele patru
direcții și drumul de sud trec, iar fixture-ul de deal cere reset. Rezultatul
rămâne dovadă offline de navmesh, nu dovadă live.

ME-375 continuă graful topografic Kalimdor cu un lot bounded de `1.000` probe.
Progresul verificat este `14.639/40.794` seed-uri, cu `0` erori de probe,
`334` observații acceptate și `508` structuri complete; raportul și graful
parțial sunt păstrate versionat. Candidate-ul rămâne separat de Stable și cu
`execution_authority=false`; aceasta este dovadă de acoperire structurală
offline, nu dovadă de mers live.

ME-376 continuă graful topografic Expansion01 cu un lot bounded de `1.000`
probe. Progresul verificat este `13.000/47.170` seed-uri, cu `0` erori,
`253` observații acceptate și `456` structuri complete; raportul și graful
parțial sunt păstrate versionat. Candidate-ul rămâne separat de Stable și cu
`execution_authority=false`; aceasta este dovadă offline, nu dovadă de mers
live.

ME-377 reconfirmă după aceste scanări că suita completă are `1513 passed`;
nu s-a schimbat codul de execuție și nu s-a pornit testul live.

ME-378 replay-uiește strict ultima urmă păstrată: cele `419` cadre nu au
martor de facing client, iar poarta se oprește la cadrul `1` cu `MISSING`, fără
input. Raportul păstrează `input_emitted=false`, `execution_authority=false`
și `server_truth_used=false`; aceasta confirmă fail-closed offline, nu mers
live.

ME-379 este singura probă live confirmată din această rundă, pe emulatorul LAB
local TBC 2.4.3. Prima pornire a fost respinsă pentru ID de destinație greșit,
iar felia corectată s-a oprit fail-closed cu `CAMERA_ACTOR_LOST` înainte de
orice cadru continuu (`0` cadre), după ce detectorul a primit o captură `1×1`.
Nu a existat combat și nu există dovadă de sosire la Brill; clipul NVIDIA
asociat este negru și rămâne doar artefact diagnostic. Armul a fost retras,
iar următoarea probă live rămâne blocată până la o nouă confirmare.

ME-391 reconfirmă offline că fabrica runnerului live leagă profilul de ancoră
Predator v2 și armează poarta actor/cameră înainte de primul cadru de mișcare;
dispariția sau eroarea detectorului eliberează controalele. Tot ME-391 continuă
candidate-ul Expansion01 la `19.000/47.170` probe, `366` observații acceptate,
`651` structuri complete și grafic parțial `1.502/3.280`, fără input și fără
promovare în Stable.

ME-392 continuă offline candidate-ul Kalimdor la `18.639/40.794` probe,
`383` observații acceptate, `645` structuri complete și grafic parțial
`1.839/3.388`, fără input și fără promovare în Stable.

ME-393 continuă offline candidate-ul Expansion01 la `20.000/47.170` probe,
`381` observații acceptate, `700` structuri complete și grafic parțial
`1.597/3.458`, fără input și fără promovare în Stable.

ME-394 continuă offline candidate-ul Kalimdor la `19.639/40.794` probe,
`402` observații acceptate, `681` structuri complete și grafic parțial
`1.900/3.477`, fără input și fără promovare în Stable.

ME-395 continuă offline candidate-ul Expansion01 la `21.000/47.170` probe,
`409` observații acceptate, `735` structuri complete și grafic parțial
`1.743/3.707`, fără input și fără promovare în Stable.

ME-396 continuă offline candidate-ul Kalimdor la `20.639/40.794` probe,
`460` observații acceptate, `716` structuri complete și grafic parțial
`2.104/3.961`, fără input și fără promovare în Stable.

ME-397 continuă offline candidate-ul Expansion01 la `22.000/47.170` probe,
`420` observații acceptate, `770` structuri complete și grafic parțial
`1.803/3.822`, fără input și fără promovare în Stable.

ME-398 continuă offline candidate-ul Kalimdor la `21.639/40.794` probe,
`511` observații acceptate, `752` structuri complete și grafic parțial
`2.268/4.291`, fără input și fără promovare în Stable.

ME-399 continuă offline candidate-ul Expansion01 la `23.000/47.170` probe,
`429` observații acceptate, `805` structuri complete și grafic parțial
`1.836/3.881`, fără input și fără promovare în Stable.

ME-400 continuă offline candidate-ul Expansion01 la `24.000/47.170` probe,
`440` observații acceptate, `841` structuri complete și grafic parțial
`1.886/3.990`, fără input și fără promovare în Stable.

ME-401 continuă offline candidate-ul Kalimdor la `22.639/40.794` probe,
`544` observații acceptate, `788` structuri complete și grafic parțial
`2.374/4.536`, fără input și fără promovare în Stable.

ME-402 procesează offline încă `2.000` probe Expansion01. Raportul verifică
`26.000/47.170` seed-uri, `493` observații acceptate, `909` structuri complete
și `0` erori; graficul strict are `489` observații, `2.137` deschideri și
`4.466` frontiere, fără input și fără promovare în Stable.

ME-403 rulează auditul complet al registrului WorldPack: `83/83` identități,
`35` hărți în queue, `4` queue-uri `COMPLETE`, `7` hărți `topographic_ready`
și `1` hartă `autonomous_ready` (Azeroth). Verificarea `--check` este
reproductibilă; nu s-a pornit WoW și nu s-a trimis input.

ME-404 procesează offline încă `2.000` probe Kalimdor. Raportul verifică
`24.639/40.794` seed-uri, `600` observații acceptate, `858` structuri complete
și `0` erori; graficul strict are `599` observații, `2.534` deschideri și
`5.161` frontiere, fără input și fără promovare în Stable.

ME-405 procesează offline încă `2.000` probe Expansion01. Raportul verifică
`28.000/47.170` seed-uri, `541` observații acceptate, `982` structuri complete
și `0` erori; graficul strict are `541` observații, `2.263` deschideri și
`4.891` frontiere, fără input și fără promovare în Stable.

ME-406 procesează offline încă `2.000` probe Kalimdor. Raportul verifică
`26.639/40.794` seed-uri, `677` observații acceptate, `930` structuri complete
și `0` erori; graficul strict are `677` observații, `2.588` deschideri și
`5.520` frontiere, fără input și fără promovare în Stable.

ME-407 procesează offline încă `2.000` probe Expansion01. Raportul verifică
`30.000/47.170` seed-uri, `582` observații acceptate, `1.052` structuri
complete și `0` erori; graficul strict are `582` observații, `2.336` deschideri
și `5.150` frontiere, fără input și fără promovare în Stable.

ME-408 procesează offline încă `2.000` probe Expansion01. Raportul verifică
`32.000/47.170` seed-uri, `622` observații acceptate, `1.121` structuri
complete și `0` erori; graficul strict are `622` observații, `2.412` deschideri
și `5.424` frontiere, fără input și fără promovare în Stable.

ME-409 procesează offline încă `2.000` probe Expansion01. Raportul verifică
`34.000/47.170` seed-uri, `648` observații acceptate, `1.193` structuri
complete și `0` erori; graficul strict are `648` observații, `2.497` deschideri
și `5.602` frontiere, fără input și fără promovare în Stable.

ME-410 procesează offline încă `2.000` probe Kalimdor. Raportul verifică
`28.639/40.794` seed-uri, `721` observații acceptate, `998` structuri complete
și `0` erori; graficul strict are `721` observații, `2.770` deschideri și
`5.920` frontiere, fără input și fără promovare în Stable.

ME-411 procesează offline încă `2.000` probe Expansion01. Raportul verifică
`36.000/47.170` seed-uri, `686` observații acceptate, `1.264` structuri complete
și `0` erori; graficul strict are `686` observații, `2.591` deschideri și
`5.875` frontiere, fără input și fără promovare în Stable.

ME-412 procesează offline încă `2.000` probe Kalimdor. Raportul verifică
`30.639/40.794` seed-uri, `750` observații acceptate, `1.069` structuri complete
și `0` erori; graficul strict are `749` observații, `2.967` deschideri și
`6.268` frontiere, fără input și fără promovare în Stable.

ME-413 procesează offline încă `2.000` probe Expansion01. Raportul verifică
`38.000/47.170` seed-uri, `692` observații acceptate, `1.334` structuri complete
și `0` erori; graficul strict are `692` observații, `2.625` deschideri și
`5.963` frontiere, fără input și fără promovare în Stable.

ME-414 procesează offline încă `2.000` probe Kalimdor. Raportul verifică
`32.639/40.794` seed-uri, `766` observații acceptate, `1.140` structuri complete
și `0` erori; graficul strict are `766` observații, `3.008` deschideri și
`6.381` frontiere, fără input și fără promovare în Stable.

ME-415 procesează offline încă `2.000` probe Expansion01. Raportul verifică
`40.000/47.170` seed-uri, `724` observații acceptate, `1.406` structuri complete
și `0` erori; graficul strict are `724` observații, `2.685` deschideri și
`6.143` frontiere, fără input și fără promovare în Stable.

ME-416 procesează offline încă `2.000` probe Kalimdor. Raportul verifică
`34.639/40.794` seed-uri, `882` observații acceptate, `1.211` structuri complete
și `0` erori; graficul strict are `880` observații, `3.160` deschideri și
`6.702` frontiere, fără input și fără promovare în Stable.

ME-417 procesează offline încă `2.000` probe Expansion01. Raportul verifică
`42.000/47.170` seed-uri, `756` observații acceptate, `1.476` structuri complete
și `0` erori; graficul strict are `756` observații, `2.772` deschideri și
`6.352` frontiere, fără input și fără promovare în Stable.

ME-418 procesează offline încă `2.000` probe Kalimdor. Raportul verifică
`36.639/40.794` seed-uri, `927` observații acceptate, `1.282` structuri complete
și `0` erori; graficul strict are `927` observații, `3.262` deschideri și
`6.952` frontiere, fără input și fără promovare în Stable.

ME-419 procesează offline încă `2.000` probe Expansion01. Raportul verifică
`44.000/47.170` seed-uri, `811` observații acceptate, `1.547` structuri complete
și `0` erori; graficul strict are `811` observații, `2.926` deschideri și
`6.696` frontiere, fără input și fără promovare în Stable.

ME-420 termină offline toate `47.170/47.170` probe Expansion01: `878` observații
acceptate, `1.659` structuri complete și `0` erori; graficul strict are `878`
observații, `3.098` deschideri și `7.109` frontiere. Graful rămâne
`PARTIAL_OBSERVED_COMPONENTS`, cu `execution_authority=false`, fără input și
fără promovare în Stable.

ME-421 procesează offline încă `2.000` probe Kalimdor. Raportul verifică
`38.639/40.794` seed-uri, `958` observații acceptate, `1.353` structuri complete
și `0` erori; graficul strict are `958` observații, `3.444` deschideri și
`7.264` frontiere, fără input și fără promovare în Stable.

ME-422 termină offline toate `40.794/40.794` probe Kalimdor: `1.003` observații
acceptate, `1.426` structuri complete și `0` erori; graficul strict are `1.003`
observații, `3.780` deschideri și `7.749` frontiere. Graful rămâne
`PARTIAL_OBSERVED_COMPONENTS`, fără input și fără promovare în Stable.

ME-423 reface auditul registrului după scanările continentelor: `83/83`
identități, `35` hărți în queue, `4` queue-uri `COMPLETE`, `7` hărți
`topographic_ready` și `1` hartă `autonomous_ready` (Azeroth). Kalimdor și
Expansion01 sunt topografice, nu autonome; verificarea `--check` trece, cu
`execution_authority=false`.

ME-424 verifică offline pipeline-ul pentru `47:RazorfenKraulInstance` cu
inventarul pin-uit și MapBuilder-ul v5: `initial_state=COMPLETE`, `bvh_ready=true`
și toate dependențele de server/emulator/input false. Dovada este
`data/runtime/navigation-f3b/razorfen-kraul-map-bake-dry-run-me424.json`, iar
queue-ul este `data/runtime/navigation-f3b/razorfen-kraul-map-bake-dry-run-me424-queue.json`.
Nu s-a executat bake-ul și nu s-a modificat copia verificată.

ME-425 verifică offline Karazhan pe directory-ul experimental și găsește
`initial_state=NAVMESH_PARTIAL`, cu `bvh_ready=true`. Dovada este
`data/runtime/navigation-f3b/karazahn-map-bake-dry-run-me425.json`; WorldPack-ul
sigilat v3 cu `9/9` tile-uri rămâne neatins și nu s-a trimis input.

ME-426 verifică offline `129:RazorfenDowns` și `33:Shadowfang`: ambele au
`initial_state=COMPLETE`, `bvh_ready=true` și autoritate de execuție falsă.
Dovezile sunt `data/runtime/navigation-f3b/razorfen-downs-map-bake-dry-run-me426.json`
și `data/runtime/navigation-f3b/shadowfang-map-bake-dry-run-me427.json`; nu s-a
executat rebuild și nu s-a pornit WoW.

ME-427 închide scanarea offline a Razorfen Downs la `39/39` probe, cu `0`
erori și `0` observații acceptate (`COMPLETE_NO_CONFIRMED_WMO`, toate cele `39`
în afara structurii). Progresul este
`data/runtime/navigation-f3b/razorfen-downs-candidate-v1-structure-access-scan-progress-v1.json`.
Nu s-a creat sau promovat un graf fără observații și nu s-a trimis input.

ME-428 verifică `MonasteryInstances` la `126/126` probe, `15` observații
acceptate, `0` erori și `4` structuri complete. Graful candidat are `43`
deschideri și `88` frontiere în
`data/runtime/navigation-f3b/monastery-candidate-v1-structure-access-partial-v2.json`,
cu `execution_authority=false`; nu este promovat și nu s-a pornit WoW.

ME-429 indexează și scanează `Stratholme`: `252/252` probe, `17` observații
acceptate, `20` fără poligon, `0` erori și `8` structuri complete. Graful
candidat are `15` deschideri și `51` frontiere în
`data/runtime/navigation-f3b/stratholme-candidate-v1-structure-access-partial-v1.json`,
cu `execution_authority=false`; nu este promovat și nu s-a pornit WoW.

ME-430 leagă în registry grafurile candidate MonasteryInstances și Stratholme
doar pentru awareness read-only. Auditul `data/runtime/navigation-f3b/world-map-registry-audit-me430.json`
trece `--check` și are `83/83` identități, `9` hărți `topographic_ready` și o
singură hartă `autonomous_ready` (Azeroth). Nu s-a trimis input.

ME-431 rulează regresia completă după schimbarea registry-ului: `1517 passed`
în `132,54 s`. Nu s-a pornit WoW și nu s-a trimis input.

ME-432 corectează clasificarea WMO pentru încăperi mai înalte decât proba
verticală bounded de `12` yarzi. Containment-ul 3D plus suprafața navmesh
`wmo` rămân dovadă de structură; `overhead_clear` rămâne doar semnal separat
pentru tavan/cameră. Scanarea offline Razorfen Downs refăcută în director nou
verifică `39/39` probe: `8` acceptate, `31` open-ground și `0` erori. Graficul
candidat are `81` frontiere, `0` access openings și
`execution_authority=false`; scanarea veche rămâne păstrată.

ME-433 verifică regresia țintită după corecție: `28 passed`. Auditul registry
`data/runtime/navigation-f3b/world-map-registry-audit-me432.json` trece
`--check`, cu `10` hărți `topographic_ready` și `1` `autonomous_ready`.
Nu s-a pornit WoW și nu s-a trimis input live.

ME-434 construiește offline un candidat separat pentru `36:DeadminesInstance`:
`36/36` dale ADT extrase, semantici generate, navmesh exact și catalog legat de
clientul TBC `2.4.3.8606`. Auditul de bake este
`COMPLETE_WITH_RECAST_DIAGNOSTICS` (`0` dale eșuate, dar diagnostice Recast
raportate), iar validatorul geometric independent trece `36/36` dale cu `0`
eșecuri. WorldPack-ul candidat este sigilat și verificat separat, cu `279`
structuri și fără dependențe de client/server/emulator; rămâne nepromovat și
nu primește autoritate de execuție. Nu s-a pornit WoW și nu s-a trimis input.

ME-435 actualizează auditorul pentru rezumatul aggregate MapBuilder v5: acceptă
`N tiles` numai la total exact `256 × ADT`, iar raportul Deadmines are acum
`36/36` ADT terminate și `36/36` nav ADT. Diagnosticele Recast rămân vizibile;
geometria independentă trece `36/36`. WorldPack-ul `tbc243-deadmines-candidate-v3b`
este sigilat și verificat separat, cu `execution_authority=false`; nu este
legat ca hartă autonomă și nu s-a trimis input live.

ME-436 construiește offline `SchoolofNecromancy` în același candidat cu
Deadmines: `16/16` dale și geometrie `PASS`. Scanarea celor `6` WMO-uri a
procesat `174/174` probe, cu `37` observații, `58` access openings, `331`
frontiere și `0` erori; graful rămâne `PARTIAL_OBSERVED_COMPONENTS`.
WorldPack-ul comun are `2` hărți, este verificat, nepromovat și are
`execution_authority=false`; live-ul nu a fost pornit.

ME-437 leagă `289:SchoolofNecromancy` doar ca awareness topografic read-only în
registry. Auditul `--check` confirmă `83/83` identități, `11` hărți
`topographic_ready` și `1` `autonomous_ready`; Scholomance rămâne fără
semantic catalog și fără autoritate de execuție. Regresia completă după legare:
`1519 passed`. Live-ul nu a fost pornit.

ME-438 construiește offline `543:HellfireRampart`: `72/72` dale ADT și
geometrie `PASS`, cu bake `COMPLETE_WITH_RECAST_DIAGNOSTICS`. Scanarea read-only
procesează `1.221/1.221` probe, cu `177` observații acceptate, `122` access
openings, `1.352` boundary chains și `0` erori; graful este
`PARTIAL_OBSERVED_COMPONENTS`, fără input și fără promovare în Stable.

ME-439 leagă Hellfire Rampart în registry numai ca hartă topografică read-only.
Auditul `data/runtime/navigation-f3b/world-map-registry-audit-me438.json`
trece `--check` și confirmă `83/83` identități, `12` hărți
`topographic_ready` și `1` `autonomous_ready`. Nu există semantic catalog pentru
Hellfire, deci nu este rută autonomă; live-ul nu a fost pornit.
Suita completă offline după legare: `1519 passed`.

ME-440 construiește offline `209:TanarisInstance`: `21/21` dale ADT și
geometrie `PASS`, cu bake `COMPLETE_WITH_RECAST_DIAGNOSTICS`. Scanarea read-only
procesează `2.178/2.178` probe, cu `418` observații acceptate, `259` access
openings, `1.410` boundary chains și `0` erori; graful rămâne
`PARTIAL_OBSERVED_COMPONENTS`, fără input și fără promovare în Stable.

ME-441 leagă TanarisInstance în registry numai ca hartă topografică read-only.
Auditul `data/runtime/navigation-f3b/world-map-registry-audit-me440.json`
trece `--check` și confirmă `83/83` identități, `13` hărți
`topographic_ready` și `1` `autonomous_ready`. Nu există semantic catalog pentru
TanarisInstance, deci nu este rută autonomă; suita offline rămâne `1519 passed`
și live-ul nu a fost pornit.

ME-442 verifică suportul bounded pentru alpha-map MCAL comprimat din
`585:Sunwell5ManFix`. Testul parserului trece; bake-ul offline are `64/64` ADT,
`64/64` nav tiles și `0` dale eșuate. Validatorul geometric independent trece
`64/64`; raportul păstrează diagnosticele Recast.

ME-443 sigilează și verifică `tbc243-dungeons-candidate-v4` cu cinci hărți și
hash `8c7bafb2a18456eadf0ff3475355918c5dec94cc840b3e099f74dbd36bc07aa`.
Scanarea Sunwell închide `339/339` probe, cu `43` observații WMO acceptate,
`50` access openings, `449` boundary chains și `0` erori; graful rămâne
`PARTIAL_OBSERVED_COMPONENTS`. Legarea în registry este read-only, iar auditul
confirmă `83/83` identități, `14` hărți `topographic_ready` și `1`
`autonomous_ready`. Regresia completă offline: `1521 passed`; live-ul nu a fost
pornit.

ME-444 construiește offline `580:SunwellPlateau`: `30/30` dale ADT și nav
tiles, cu `0` dale eșuate; validatorul geometric independent trece `30/30`.
Scanarea read-only închide `453/453` probe, cu `47` observații WMO acceptate,
`32` access openings, `418` boundary chains și `0` erori; graful rămâne
`PARTIAL_OBSERVED_COMPONENTS`.

ME-445 leagă Sunwell Plateau numai pentru awareness topografic read-only într-un
WorldPack v5 verificat (`6` hărți, hash
`67f15af4b319b0d014420cb49691bb2a5661ee24c3f36e3994e9e67fba7d4bd3`). Auditul
confirmă `83/83` identități, `15` hărți `topographic_ready` și `1`
`autonomous_ready`; live-ul nu a fost pornit.

ME-446 construiește offline `568:ZulAman`: `25/25` dale ADT și nav tiles, cu
`0` dale eșuate; validatorul geometric independent trece `25/25`. Scanarea
read-only închide `993/993` probe, cu `229` observații WMO acceptate,
`53` access openings, `1362` boundary chains și `0` erori; graful rămâne
`PARTIAL_OBSERVED_COMPONENTS`.

ME-447 leagă ZulAman numai pentru awareness topografic read-only într-un
WorldPack v6 verificat (`7` hărți, hash
`6e2e4d3eddbaec9df86e8656e63f7f36106f61d65e9e89f90d2df7af642549f2`). Auditul
confirmă `83/83` identități, `16` hărți `topographic_ready` și `1`
`autonomous_ready`; live-ul nu a fost pornit.
