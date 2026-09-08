# Probă vizuală pentru separarea nivelurilor — numai offline

## Alegerea metodei

Nu există în proiect o calibrare conectată între repere 3D și pixeli.
Observația de facing/camera yaw și ancora siluetei nu înlocuiesc această
calibrare. OpenCV nu este instalat în mediul proiectului; nu am adăugat o
dependență pentru acest experiment.

`visual_vertical_probe` folosește NumPy existent pentru o proiecție pinhole
3×4 estimată prin DLT normalizat: minimum 8 repere 3D necoplanare, plus minimum
4 repere separate pentru verificare. Nu estimează rotația/translația metrică
a camerei și nu redenumește centrul camerei „poziție personaj”.

Principiul proiecției și al verificării reziduurilor este descris în
[documentația OpenCV despre proiecție și PnP](https://docs.opencv.org/4.13.0/d5/d1f/calib3d_solvePnP.html).
Implementarea prezentă nu apelează solvePnP și nu pretinde echivalență cu un
solver complet, robust la repere greșite sau ambiguități de asociere.

## Ce produce

Pentru XY furnizat și fiecare Z candidat, proiectează punctul în imagine și
raportează distanța până la pixelul de contact al piciorului furnizat separat.
Raportează și separarea dintre proiecțiile nivelurilor. Bugetele de eroare
sunt explicite și experimentale, nu o calibrare de precizie a actorului.
Toate alternativele rămân în rezultat. Un singur candidat nu devine dovadă de
discriminare; privirea exact verticală pe axa optică poate suprapune nivelurile.

Refuză repere coplanare/degenere, copii între fit și verificare, puncte în
afara viewportului, proiecții în spatele camerei, coordonate nefinite și
reziduuri prea mari pe reperele independente. Limite: maximum 64 puncte/set,
64 candidate și coordonate absolute cel mult 1e7. Nu există I/O sau input în
modul, iar sursa rezultatului este `OFFLINE_LANDMARK_PROJECTION_DIAGNOSTIC`.

`observed_actor_z=null`, `confirmed_floor_id=null`, `live_calibration_verified=false`,
`execution_authority=false`. Un reziduu mic nu verifică autenticitatea reperelor.
Nu este conectat în CC sau Brain și nu este senzor de Z gata de utilizare.

## Dovezi

18 teste noi pentru: vedere oblică, vedere verticală nediscriminativă,
translație în coordonate world mari, zgomot, verificare independentă eșuată,
repere coplanare/repetate, bugete invalide, puncte ascunse de planul de
proiecție și candidat unic. Împreună cu contextul spațial, candidații verticali
și prezentarea WMO: **68 PASS**. Lint și diff-check PASS.

Nu este calibrare pe joc. Pentru date reale am extras și inspectat două cadre
din video-ul deja arhivat `Wow.exe 2026.09.06 - 01.54.50.02.mp4`, fără a
modifica originalul sau jocul. Dimensiuni originale 2558×1440; cadrele afișate
în chat au fost micșorate, deci coordonatele de adnotare trebuie raportate la
original, nu copiate necorectat din preview.

- Secunda 85: personajul este mare în cadru, iar contactul picioarelor cu
  podeaua este ascuns de bara interfeței; nu este martor de contact valid.
- Secunda 92: corpul este complet vizibil, dar în animație de mers; pixelul
  cel mai de jos al siluetei nu devine automat centrul actorului pe podea.
  Încadrarea camerei diferă de cea de la secunda 85; fiturile nu se amestecă.

Cadre locale ignorate: `data/runtime/visual-vertical-probe/crypt-85.png`
(SHA256 `eca17b5e6e1da157c852e772be9e48cc1c547f345274cab93b0d702640ec6183`)
și `crypt-92.png`
(SHA256 `07eb717425d58e7dc2c93561b8a85db2e0e885bc67a69205baba39bc254934c2`).
Nu există încă perechi reale verificate vertex-WMO/pixel sau ancoră de contact.

## Următorul pas și limite de promovare

1. Identifică aceleași colțuri structurale în mesh-ul WMO verificat și într-un
   singur cadru original. Păstrează grup/vertex/transform/hash, nu XYZ ghicit.
   Separă dinainte reperele de fit de cele de verificare.
2. Înregistrează camera/viewportul/cadrul și legătura temporală la XY observat;
   nu folosi un XYZ proiectat navmesh drept etichetă vizuală de adevăr.
3. Verifică contactul vizibil și offsetul față de originea actorului sau alege
   un alt martor calibrabil. Un picior ridicat, ocuzia și săritura cer respingere
   ori incertitudine măsurată, nu presupunerea că piciorul este pe podea.
4. Evaluează pe cadre nefolosite la calibrare, alte încadrări și niveluri
   suprapuse; abia apoi integrare cu identitate/prospețime și incertitudine.

Nicio modificare live în acest pas; CC, v34, addon și anti-AFK rămân ca înainte.
Goal-ul complet rămâne activ. Acest experiment nu închide localizarea verticală.
