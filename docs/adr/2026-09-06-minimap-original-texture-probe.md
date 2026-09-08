# Probă offline: texturile originale ale minimapei

## Decizie

Investigăm minimapa ca observație vizuală suplimentară, fără perspectiva
camerei principale. Nu legăm încă rezultatul la CC, Z, grup ocupat sau etaj.
Corelația unei texturi vizibile nu dovedește că actorul ocupă acel grup.
Nu schimbăm navigatorul v34, addonul, anti-AFK ori procesele live.

## Date originale și reproducere

Extractorul existent `pa_client_asset_extract-v3` a citit numai fișiere MPQ
din clientul local TBC 2.4.3. Nu s-a citit memoria procesului sau serverul.
În `Textures\Minimap\md5translate.trs` (909647 bytes, SHA256
`ec82e4f0406c076adb564b9c138f0357e026af64e6d5b20114780373a28b77cd`),
liniile 7854–7857 asociază `WMO\Dungeon\MD_CryptOneRm` astfel:

| Grup | Nume fizic BLP în Textures/Minimap | Dimensiuni |
| --- | --- | --- |
| 1 | 34e0bd96fd445c29ce41a4c6fba70e2c.blp | 64×32 |
| 2 | 0f4df98d8130c5f071f55b3fde1ef04d.blp | 32×32 |
| 3 | 50e3daa6c3c4de22379da904fe508647.blp | 32×32 |
| 4 | 3a5d3e1b85cafd0d41302e92ffe6c430.blp | 64×128 |

Numele fizic este un identificator din tabel, nu o verificare SHA256.
Nu există rând pentru grupul 0 al acestui model în tabel; nu deducem că
grupul lipsește din geometrie. Modelul are cinci grupuri conform auditului WMO.
Referința negativă: `GoldshireInn_000_00_00.blp`, linia 3670,
`8a95b4ffb083ab7886d82e636e04102e.blp`, 32×32.

Fișierele extrase, SHA256 individuale în rezultate, imaginile decodate și
rezultatele rămân ignorate în `data/runtime/minimap-wmo-probe/`.
Cadrele originale 2558×1440 la 85/90/92s provin din filmarea deja păstrată;
hash-ul fiecărui cadru este în JSON. Nu se distribuie imaginile clientului în Git.

Exemplu comandă (din repository, mediu Python existent):

```powershell
.\.venv\Scripts\python.exe tools/probe_minimap_textures.py --frame data/runtime/visual-vertical-probe/crypt-85.png --roi 2300 50 2515 260 --reference data/runtime/minimap-wmo-probe/group-4.blp --reference data/runtime/minimap-wmo-probe/goldshire-0.blp --output data/runtime/minimap-wmo-probe/new-comparison.json
```

ROI manual numai pentru filmarea aceasta; nu este profil live. Un cerc
interior, raza 0.43×latura mică, exclude rama/butoanele. Nu mascăm încă automat
markerul sau alte iconuri. Pentru reproducere folosiți un output nou.

## Algoritm și limite

`minimap_texture_probe.masked_texture_match` compară intensități normalizate
prin corelație cu medie eliminată, pe suportul alfa al texturii. Suportul
întreg trebuie să fie în regiunea validă; padding-ul transparent și fundalul
negru nu sunt dovezi. Minimum 64 pixeli și variație minimă elimină referințe
goale/constante, dar NU garantează identificabilitatea unei texturi mici.
FFT bounded, imagini de maximum 512×512, fără biblioteci noi.

Tool-ul explorează independent rotații din 15° în 15°, scale
0.75/1/1.25/1.5, apoi rafinează în jurul maximului. Aceste limite sunt ale
experimentului, nu limite demonstrate pentru toate zoom-urile/clientele.
Nu constrânge încă transformarea după instanța WMO sau compoziția grupurilor.
Scorurile nu sunt probabilități și nu sunt comparabile ca încredere între
suporturi foarte diferite. `CANDIDATE_ONLY` nu are prag de acceptare.

## Rezultate reale, nu fixture

| Cadru | Grup 1 / pixeli | Grup 4 / pixeli | Referință greșită / pixeli |
| --- | --- | --- | --- |
| 85s | 0.8675 / 674 | 0.7349 / 2906 | 0.8001 / 70 |
| 90s | 0.8730 / 674 | 0.6962 / 2906 | 0.7879 / 70 |
| 92s | 0.8772 / 674 | 0.6594 / 2906 | 0.7492 / 70 |

Grupul 4: aceeași rotație de probă 270°, scala 1.0, offseturi ROI
(71,99), (69,91), (71,63). Acestea sunt deplasări ale unei texturi în imagini,
NU coordonate world sau observații Z. Grupul 3 mic obține 0.9462–0.9588.
Suprapunerea vizuală de diagnostic la 85s a fost inspectată: încăperea mare
și porțiuni distincte ale culoarului se aliniază simultan pe minimapă.

Consecință demonstrată: alegerea celui mai mare scor între aceste referințe
ar favoriza un fragment mic, inclusiv unul greșit, în detrimentul camerei mari.
Minimapa nu este un indicator simplu „un grup afișat = grupul ocupat”.
Setul negativ este mic; nu există rată generală măsurată de fals pozitiv.
Cele trei cadre sunt din aceeași filmare, nu trei scene independente.

## Teste și pas următor

Teste unitare: potrivire exactă/translație, intensitate/contrast, alfa,
mască invalidă, no-hit/constant/negru, limite și NaN/inf, referință greșită,
duplicare ambiguă, verificare numerică FFT față de corelația directă.
74 teste relevante PASS: proba nouă, sonar, prezentare și repere WMO.
Rezultatele reale sunt în `match-85-v1.json`, `match-85-negative.json`,
`match-90-v1.json`, `match-92-v1.json` din directorul runtime.

Următorul experiment trebuie să constrângă compoziția prin geometria
instanței și să verifice relația markerului cu suprafețele candidate. Trebuie
testate și minimape parțiale, rotite, alte zoom-uri, exteriorul și clădiri
suprapuse. Până atunci: fără observare actor Z, fără floor_id, fără eliminarea
alternativelor și fără input live. Calea proiectivă 3D–pixeli rămâne alternativă.

Rollback: eliminați exclusiv tool-ul/modulul offline și testele lor sau
revert-ul commitului acestei probe. Runtime-ul și v34 nu depind de ele.
