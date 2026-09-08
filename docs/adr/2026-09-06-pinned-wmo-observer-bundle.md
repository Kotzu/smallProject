# Bundle WMO verificat, cu acoperire parțială explicită

## Decizie

Metadatele originale ale grupurilor intră în observer numai printr-un bundle
cu manifest SHA256 fixat extern, legat de WorldPack, hartă și indexul de
instanțe reconstruit. Fiecare model inclus trebuie să conțină toate grupurile;
triunghiurile reținute și root ID trebuie să coincidă exact cu BVH verificat.
Un manifest rehashuit nu poate schimba proveniența, harta sau acoperirea.

Acoperirea este `LISTED_MODELS_ONLY`, nu întreaga lume. Instanțele fără model
încărcat sunt enumerate separat. Terenul și doodad-urile nu sunt verificate de
această asociere. Lipsa unei intersecții nu elimină alternativa verticală.
Bounds aleg instanțele de interogat, nu etajul ori interiorul actorului.
Segmentele verticale au capete finite din bounds-ul instanței; nu există
scanare până la infinit. Altitudinea, etajul și plafonul rămân lucruri distincte.

Limite: 256 MiB de asset-uri/bundle, 64 modele, 512 grupuri/model,
un milion de triunghiuri reținute/model, 16 instanțe și 4096 hit-uri/instanță
pentru o coloană. Depășirile produc eroare, nu spațiu liber certificat.
Builderul creează numai o destinație nouă, fără suprascriere. Artifactele
bundle nu pot ieși din director; fișierele sunt verificate prin hash.

## Observer

`SpatialSonarObserver(..., wmo_bundle_spec=...)` este opțional; implicit
comportamentul existent nu se schimbă. Încărcarea și interogarea se fac numai
în workerul de fundal existent. O încărcare eșuată nu este repetată la fiecare
cadru și nu suprimă sonarul de bază. Asocierea folosește XY-ul coloanei
interogate de worker, nu XY-ul mutat prin proiecția navmesh.

Rezultatul moștenește limita de sesiune/hartă/poziție/timp a observației sonar.
Încărcarea inițială poate expira prima observație: aceasta este respinsă normal,
nu primește timestamp nou pentru a părea proaspătă. Următoarea interogare
folosește bundle-ul deja încărcat. Nicio autoritate de execuție.

## Dovezi la 2026-09-06

- 168 teste relevante PASS; verificarea de stil pentru fișierele schimbate PASS.
- Bundle real construit și reîncărcat: un model, cinci grupuri; acoperă
  instanțele acelui model din indexul verificat al hărții 0.
- Director local ignorat: `data/runtime/wmo-bundles/azeroth-wmo-observer-v1`.
- Manifest SHA256:
  `a92d925975dcfeb86cd1cd73baa831a8f136eb957bbadd9b86efc70623f61bbd`.
- WorldPack SHA256:
  `a9feb578fea082f073effd84415977fa8a760ed2e5b2f8b07a1609215fe56b78`.
- Integrare offline prin observer, worker și pack reale: la XY
  1676.369629/1677.466919, 121.670326 corespunde grupului 1490/triunghiului
  4901 cu diferență numerică ~0,000015 yd; 138.45195 rămâne fără potrivire WMO.
  Nu reprezintă precizia poziției actorului. Ambele alternative sunt păstrate.
- Prima interogare 16,633 s, aceeași coloană după încărcare 0,055 s.
  Sunt măsurători punctuale, nu garanții de latență.
- Referință exterioară XY 1809.584261511/1592.794265920: 0,261 s,
  nicio instanță WMO în coloană, plafon nedetectat în segmentul testat,
  `ceiling_height_yards=null`, `infinite_clearance=false`, etaj neconfirmat.

## Limite, continuare și revenire

Noua opțiune NU este activată în CC de producție; nicio verificare live a
acestui bundle și nicio mișcare nouă. Urmează configurație explicită cu hash,
afișarea acoperirii/potrivirilor/erorilor în CC și probă staționară delimitată.
Nu închide identificarea etajului, percepția volumetrică sau traversabilitatea.
v34 și anti-AFK sunt neschimbate. Omiterea `wmo_bundle_spec` păstrează observerul
anterior; nu se promovează workerul de observație în navigator.
