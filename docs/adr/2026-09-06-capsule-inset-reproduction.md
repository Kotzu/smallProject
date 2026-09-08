# Raza declarată nu dovedește clearance-ul executabil

Status: defect generic reprodus; nicio corecție live acceptată.

Actualizare: secțiunile de mai jos păstrează reproducerea pe `55c71b3`.
Un candidat ulterior, limitat la colțuri orizontale și încă nedeployat, este
în `2026-09-06-shared-corner-inset-candidate.md`; testul curent nu mai este roșu.

## Cod inspectat

Dependency-ul local Namigator (`PerfectAssassin-Dependencies/navigation/namigator`):
`Common.hpp` declară `WalkableRadius=0.90`, iar `SerializeMeshTile` din
`MapBuilder/MeshBuilder.cpp` trece de la `rcBuildCompactHeightfield` la
`rcBuildDistanceField`, fără apel `rcErodeWalkableArea`. Valoarea radius este
folosită în configurare și scrisă în header-ul Detour; acest lucru nu dovedește
retragerea efectivă a suprafeței traversabile de la obstacole.

Aceasta este o constatare despre sursa locală inspectată, nu o dovadă completă
a provenienței binarului care a produs fiecare tile din WorldPack-ul activ.
Nu deducem retrospectiv proveniența bake-ului numai din configurația actuală.

Worker-ul proiectului compensează prin `inset_funnel_corners`: 0,90 yd pe
portal; probele de tunel folosesc 0,389 yd rază corporală + 0,30 yd abatere =
0,689 yd. Valorile sunt politica existentă din cod, nu măsurători noi ale
modelului vizual. Media direcțiilor de inset poate micșora spațiul rezervat.

## Reproducere generică pe funcția C++ reală

`native/pa_nav_probe/tests/portal_clearance_test.cpp` include funcția de producție
într-un executabil separat; entry point-ul worker-ului este redenumit și nu
este apelat. Nu se citesc asset-uri, nu se lansează clientul și nu există input.

Fixture: un colț convex la origine, două portaluri perpendiculare cu același
capăt, traseu în L. Testul verifică ambele segmente și rezervă raza + abaterea.
Aceeași scenă este rotită cu 0, 0,7 și 1,9 radiani.

Rezultat baseline în toate trei: distanța minimă 0,636396 yd, necesar 0,689 yd,
clearance rezidual **−0,052604 yd**. Testul opt-in este intenționat ROȘU:
reproduce o condiție nesatisfăcută; nu a fost inversat ca să raporteze PASS.
Raza corpului fără abatere ar încăpea aici; problema este garanția combinată,
nu afirmația că orice trecere centrală lovește fizic obstacolul.

Compilare izolată:

```powershell
cmake -S native/pa_nav_probe -B data/runtime/native-build/pa-nav-clearance-test -G "Visual Studio 17 2022" -A x64 -DNAMIGATOR_ROOT=E:/WoWserver/PerfectAssassin-Dependencies/navigation/namigator -DNAMIGATOR_BUILD_ROOT=E:/WoWserver/PerfectAssassin-Dependencies/navigation/namigator/build-pa-pinned-debug -DPA_NAV_BUILD_GEOMETRY_TESTS=ON
cmake --build data/runtime/native-build/pa-nav-clearance-test --config Debug --target pa_portal_clearance_test
ctest --test-dir data/runtime/native-build/pa-nav-clearance-test -C Debug --output-on-failure
```

Build-ul implicit păstrează opțiunea OFF. Nu se modifică worker-ul activ v34.

## Candidat respins înainte de live

Am încercat offline normalizarea bisectoarei rezultate la 0,90 yd, exclusiv
pentru portaluri cu același capăt exact. Fixture-ul trecea. Totuși, interogarea
pe asset-uri a schimbat apropierea de prima scară fără a îmbunătăți mostra
critică 108: sonda minimă pe traseu a rămas 0,5625 yd. Și mostra 133 a rămas
neschimbată la 1,125 yd. Nu avem dovadă de corectare a problemei urmărite.

Modificarea funcției a fost retrasă din sursă. Nu a fost instalată în profil,
nu a fost rulată în joc și nu este corecția acceptată a goal-ului. Testul și
constatările rămân pentru a evita repetarea încercării sau un PASS superficial.

## Urmează

Verificarea provenienței bake-ului activ și un experiment de clearance pe
geometrie generică folosind Recast-ul local, izolat de WorldPack-ul activ.
Nu se reconstruiește implicit întregul continent și nu se schimbă raza doar
pentru a trece testul. O eventuală corecție trebuie verificată și pe pasaje
înguste/scări: erodarea în plus poate elimina drumuri legitime.

Control Center, worker-ul activ, serverul și clientul rămân neschimbate.
Hash worker activ v34 verificat:
`CB3555065C56A40C45C73D929A89BDA6F8237FE5FFA2E018FCE50FAC84821D3D`.
