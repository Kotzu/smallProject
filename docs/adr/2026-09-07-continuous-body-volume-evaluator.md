# Volumul continuu al corpului — evaluator offline, nu controller

## Decizie

Adăugăm distanța geometrică dintre o capsulă verticală translatată liniar
și triunghiurile furnizate. Axa capsulei mătură un paralelogram; distanța
minimă la această suprafață minus raza măsoară apropierea/întrepătrunderea.
Nu folosim câteva raze pentru a pretinde verificarea întregului volum.
Valoarea negativă înseamnă suprapunere cu o suprafață, nu adâncime fizică
de penetrare. Calculul este numeric, cu toleranțe și bugete finite.

Implementare: `movement/swept_volume.py`, adaptor `adapter/wmo_swept_volume.py`.
Geometria modelului este transformată în world înaintea calculului, pentru
a păstra raza în yards inclusiv sub transformări cu scalare neuniformă.
Sunt păstrate identitatea structurii/grupului/triunghiului și hash-urile.
Sunt separate fețele cu |normal_z| >= 0.7 de cele abrupte și degenerările.
Acestea sunt clase de orientare, NU etichete podea/perete/traversabil.
Contactul cu suprafețele joase nu este eliminat și nu produce un verdict blocat.

Funcțiile nu au input, nu sunt importate în controller sau CC și nu schimbă
v34. Nicio coordonată a criptei nu există în regula geometrică/adaptor.
Scriptul de audit folosește explicit proba istorică delimitată, nu un traseu
executabil. Anti-AFK, Stop robust, indexarea memoriei și camera rămân neschimbate.

## Dovezi

153 teste relevante PASS: noua geometrie/adaptor, WMO bundle, suprafețe,
grupuri/BVH, asociere, sonar și prezentare. Cazuri: obstacol între capete libere,
intersecție prin interiorul feței, podea/plafon, nivel superior, rampă,
degenerări, winding, translație/scalare/rotire, date lipsă și transformare invalidă.

Audit offline pe run ebd340cd-ba97-4a5b-a726-40246ce9d0eb, 32 segmente consecutive
64→65 până la 95→96. Fiecare punct combină XY din `decision_observation`
cu Z din `projected_z_world`, etichetat deja `decision_corridor_projection_not_observed_z`.
NU este XYZ observat independent. Raza 0.389 yd și înălțimea 2 yd sunt ipoteze
explicite, nu dimensiuni nou calibrate ale personajului.

Geometrie: 1947 triunghiuri reținute, toate cele cinci grupuri ale modelului
criptă din bundle-ul verificat față de WorldPack/BVH. Structura 0:wmo:85944;
605 fețe joase, 1342 abrupte, fără fețe degenerate în acest model.

| Evaluare la segmentul cel mai apropiat, 85→86 | Separare față de fețe abrupte |
|---|---:|
| Z proiectat, raza 0.389, înălțime 2 | +0.181355 yd |
| Același segment, Z minus 0.25 yd | −0.042956 yd |
| Același segment, Z plus 0.25 yd | +0.405667 yd |
| Z proiectat, raza 0.489, înălțime 2.2 | +0.171080 yd |

Sensibilitățile sunt ilustrative, NU limite calibrate ale erorii. Suprafața
cea mai apropiată în evaluarea de bază: grup 3/id 1489, triunghi 347,
normal_z ~0.000160. Din orientare singură nu deducem dacă este zid sau treaptă.
Pentru fețele joase, minimul pe secvență este −0.197003 yd; aceasta nu dovedește
un blocaj: trebuie separat sprijinul, scara și eroarea de Z.

Concluzie: abaterea față de centrul traseului NU măsoară singură riscul de
contact. După viraj există un segment sensibil la Z. Nu afirmăm că Predator
a lovit fizic suprafața sau că ar fi fost sigur cu o altă reglare.

Cost măsurat al primei evaluări complete: încărcare verificată ~15.8 s,
mediană ~156 ms/segment. Acest evaluator Python rămâne offline; nu îl punem
în bucla de mers sau în firul UI. Optimizarea/indexarea geometrică poate urma
doar păstrând aceleași rezultate și fără a omite fețe relevante.

## Reproducere și proveniență

`scripts/audit_recorded_crypt_volume.py`, prin Python-ul proiectului.
Necesită pachetul/bundle-ul și raportul local existente. Nu conectează clientul.
Scrie numai rezultate derivate în `data/runtime/operator/crypt-summary-index-repeat/`:
`swept-volume-evidence.json`, `swept-volume-sensitivity.json`.
Datele brute, geometria licențiată și filmele rămân în runtime ignorat, nu Git.

- Raport run SHA256: 9855cc0ca9d5fe98ee14702687222b4ceecc84f574b8c858f1211165603f213f
- Bundle SHA256: a92d925975dcfeb86cd1cd73baa831a8f136eb957bbadd9b86efc70623f61bbd
- WorldPack SHA256: a9feb578fea082f073effd84415977fa8a760ed2e5b2f8b07a1609215fe56b78

## Limite și următoarea intervenție

Acoperire numai modele WMO încărcate din vecinătatea segmentului; terenul,
doodad-urile și actorii mobili nu sunt verificate. Lipsa fețelor rămâne
necunoscută, nu liber. Traiectoria dintre două observații este liniară; nu
pretindem că aceasta este traiectoria exactă a clientului între cadre.
Nu certificăm volumul solid sau starea inițială din interiorul unui solid.

C03 rămâne parțial, C01/C05/C07 neacceptate. Urmează identificarea sprijinului
și a suprafeței din segmentul 83–87, comparând Z-ul proiectat cu alternativele
geometrice și filmul existent. Abia apoi alegem o singură corecție generală
de traseu/urmărire, cu probă filmată și revenire dacă nu aduce beneficiu.
Integrarea CC trebuie să păstreze ipotezele/acoperirea/prospețimea și să fie
asincronă; această schimbare NU este prezentată ca sonar live complet.
