# Repere vizuale: coordonate din vertexuri verificate, nu XYZ introduse manual

## Implementare și scop

`resolve_landmarks` rezolvă selecții explicite grup/vertex din bundle-ul WMO
verificat și aplică transformarea instanței în world. Rezultatul păstrează
hash-urile pack/bundle/grup/transform, harta, instanța, grupul și indexul
vertexului, coordonatele locale/world și apartenența la geometria reținută.
Maximum 64 referințe/apel; duplicatele, vertexurile fără triunghiuri și
modelele neacoperite sunt refuzate.

Aceasta verifică originea punctului 3D, nu asocierea lui cu un pixel.
`pixel_correspondence_verified=false`, `confirmed_floor_id=null`,
`execution_authority=false`. Camera și XYZ-ul presupus al actorului nu sunt
folosite în transformarea model–world.

`tools/export_wmo_landmark_view.py` verifică pack/index/bundle, exportă muchiile
ascuțite sau de frontieră ale triunghiurilor reținute și două proiecții
ortogonale pentru examinare. Sudarea coordonatelor identice se face numai la
afișare; se păstrează indexul original ales. Nu este o imagine a camerei din joc.
Muchiile interne coplanare sunt eliminate din desen, nu din datele sursă.
Secțiunea opțională de Z exclude muchiile care o depășesc; nu taie/reconstruiește
triunghiuri. Limite: 2000 puncte, 20000 muchii desenate, destinație nouă fără
suprascriere. Nu presupune că textura și coliziunea au aceleași detalii.

## Verificare pe date reale

Comanda reproductibilă, numai citire de asset-uri și export local:

```powershell
.\.venv\Scripts\python.exe tools/export_wmo_landmark_view.py --profile config/navigation/world-pack-runtime-tbc243-azeroth-full-v3.json --store-root E:/WoWserver/PerfectAssassin-Runtime/worldpacks --bundle-config config/navigation/sonar-wmo-azeroth-v1.json --structure-id 0:wmo:85944 --group 4 --maximum-z 126 --output data/runtime/visual-vertical-probe/landmarks-floor-v1
```

Pentru repetare folosește alt director de ieșire. Rezultat real: **164 puncte,
269 muchii**, grup index4/ID1490. Desenul a fost inspectat vizual; planul arată
conturul încăperii și dreptunghiul central. Proiecția laterală suprapune puncte
și unele etichete sunt dense: nu se folosesc coordonatele desenului drept
adnotări pentru cadrul video.

Exemple din export:

- vertex3148 → world `(1669.649545604, 1688.456435854, 121.024504912)`;
- vertex2854 → world `(1659.081379436, 1688.364214185, 121.024504912)`;
- vertex3518 → world `(1668.617833704, 1687.406561967, 120.530106825)`.

Acestea sunt referințe de verificare, nu coordonate introduse în algoritmul
de navigație. Același export funcționează pentru orice instanță/model acoperit.
Datele derivate și PNG-ul rămân în directorul runtime ignorat, nu în Git.

78 teste relevante PASS: repere, bundle, transformări/grupuri, triunghiuri și
proiecția vizuală. Include transformare rotită/translatată cu verificare inversă,
proveniență, limite și referințe inexistente. Lint și diff-check PASS.

## Starea asocierii cu imaginea

Am extras suplimentar cadrul 90s din filmarea deja identificată în ADR-ul
proiecției. Cadrul arată personajul în animație de mers și o încadrare diferită;
nu este o ancoră staționară nouă. Nu am declarat perechi vertex/pixel confirmate.
Contururile mari sunt candidați de asociere; liniile decorative din textură și
colțurile ascunse nu furnizează automat puncte 3D independente.

Urmează adnotarea verificabilă într-un singur cadru original, cu seturi separate
pentru fit/verificare și martor de contact justificat. Dacă nu sunt suficiente
repere neambigue, proba trebuie să raporteze date insuficiente, nu să completeze
cu XYZ presupus sau cu proiecția navmesh a actorului.

Nicio modificare în procese, camera live, CC, navigatorul v34, addon sau anti-AFK.
Nu este încă localizare vizuală, calibrare reală sau confirmare de etaj.
