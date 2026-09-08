# Compoziție geometrică și deplasare pe minimapă — probă offline

## Decizie și sursă tehnică

Compoziția grupurilor folosește pozițiile din MOGI, nu un fit liber per cameră.
Ipoteza de layout a fost verificată pornind de la implementarea primară
[World-of-MapCraft, wmo_build.php](https://github.com/iamcal/World-of-MapCraft/blob/master/build/wmo_build.php),
secțiunile de asamblare și `extract_mogi`: minimul local X/Y, inversarea Y,
grid de 256 pixeli, origine la baza imaginii și densitate 1.993 pixeli/unitate.
Aceasta este o implementare pentru o generație ulterioară a clientului, nu
specificație oficială TBC; densitatea rămâne parametru explicit al probei.
Am comparat și densitatea 2.0, fără a declara vreuna calibrare universală.

`minimap_layout.py` calculează dreptunghiurile, proiecția XY și deplasarea
texturii pentru unghi/scară constante. Respinge transformări înclinate în
care poziția orizontală depinde de Z necunoscut. Nu include selecție de etaj.
Tile-urile lipsă și suprapunerile nu sunt spațiu liber. Ordinea compoziției
este explicit ordinea intrărilor, nu o deducție despre grupul ocupat.

## Dovezi reale

Aceleași patru BLP originale și cadre 85/90/92s ca în ADR-ul anterior.
Root WMO verificat prin SHA256 extern
`058f40d5ca2a4e7fdbb0c2a7883f37a3662c203908b89e35924f68643de3ba92`.
Legătura originală nume logic → nume fizic este documentată în
`2026-09-06-minimap-original-texture-probe.md`; tool-ul de compoziție primește
asocierile explicit și nu pretinde că a reverificat tabelul de traducere.

Compoziția 1.993: 108×129 pixeli, alfa bounds [1,51,85,129], origine [-45,-60].
SHA256 PNG: `e900a6bab9b6be838a91286d058dc6e77fa8faa746f44154e37230f95a07c2f2`.
Outputul tool-ului general coincide byte-for-byte cu experimentul inițial.
Grupul 0 nu are imagine furnizată; absența rămâne explicită.
Potrivire comună în toate trei cadrele: rotație 270°, scară 1.0;
scoruri 0.75375 / 0.71945 / 0.70643. Nu sunt probabilități.

Banda coordonatelor din fiecare cadru a fost decodată cu detectorul existent
și verificarea CRC. Nu am atribuit cadrelor vechi prospețime/sesiune live.
Continent=2, zone_index=25; conversie prin transformarea existentă TBC
WorldMapArea. Facing indisponibil în aceste pachete, păstrat null.
WorldPack, indexul reconstruit și bundle-ul au fost reverificate înaintea
folosirii matricei pentru instanța `0:wmo:85944`. Matricea ei permite inversarea
XY fără să introducem un Z presupus. Datele serverului nu au fost folosite.

| Cadru | XY din banda addonului, convertit în world | Origine textură în ROI |
| --- | --- | --- |
| 85s | 1676.369575, 1677.466958 | 71,98 |
| 90s | 1672.416344, 1676.363730 | 69,90 |
| 92s | 1658.580036, 1677.535909 | 71,62 |

Cu densitate/rotație/scară constante, deplasarea XY prezice mișcarea opusă
a conturului în jurul ancorei minimapei. Nu folosim markerul ca reper de fit.

| Interval | Deplasare prezisă, px | Deplasare măsurată prin fit, px | Rezidual |
| --- | --- | --- | --- |
| 85→90s | -2.12989, -7.89768 | -2, -8 | 0.16536 px |
| 85→92s | +0.44681, -35.45200 | 0, -36 | 0.70707 px |

Este consistență între două canale în acest segment, NU eroare metrică
certificată a poziției. Textura și geometria au aceeași origine în client;
cele trei cadre nu sunt scene independente. Fitul fiecărui cadru explorează
translația, iar selecția setului de texturi nu este exhaustivă.

Detectorul existent de marker găsește centroidul la aproximativ 1.73/4.12/3.16
pixeli de punctul proiectat din XY. Centroidul formei săgeții variază odată
cu orientarea; nu este tratat ca ancoră exactă a actorului. Nu se aplică un
offset corector hardcodat după aceste trei mostre.

## Limita verticală și pasul următor

Această proiecție plană nu conține Z: două suprafețe cu același XY au același
pixel prezis. Nu dovedește că minimapa nu poate ajuta deloc la etaj; schimbarea
grupurilor/texturilor afișate poate aduce dovezi, dar necesită alte probe.
Urmează examinarea tranziției pe scări/interior–exterior din filmare și
compararea grupurilor vizibile cu suprafețele alternative. Niciun candidat
nu se elimină numai fiindcă XY se potrivește cu acest contur.

## Reproducere și teste

```powershell
.\.venv\Scripts\python.exe tools/compose_wmo_minimap.py --root-wmo data/runtime/wmo-semantic-probe-20260906/crypt-root.wmo --root-sha256 058f40d5ca2a4e7fdbb0c2a7883f37a3662c203908b89e35924f68643de3ba92 --pixel-density 1.993 --tile 1:0:0:data/runtime/minimap-wmo-probe/group-1.blp --tile 2:0:0:data/runtime/minimap-wmo-probe/group-2.blp --tile 3:0:0:data/runtime/minimap-wmo-probe/group-3.blp --tile 4:0:0:data/runtime/minimap-wmo-probe/group-4.blp --output data/runtime/minimap-wmo-probe/new-composition
.\.venv\Scripts\python.exe tools/audit_minimap_displacement.py --input data/runtime/minimap-wmo-probe/projection-audit-v1.json --output data/runtime/minimap-wmo-probe/new-displacement-audit.json
```

Compoziția poate fi dată tool-ului anterior `probe_minimap_textures.py` ca
referință. Folosiți căi noi de output. Fișierele originale și telemetria nu
intră în Git. `audit_minimap_displacement.py` verifică aritmetica unui record
offline furnizat, nu reverifică singur proveniența lui.
Teste: grid, margini parțiale, limite, grupuri lipsă, duplicate, Z independent,
inversarea XY sub rotație, respingerea înclinării, semnele celor patru rotații,
schimbarea zoom-ului/unghiului, input invalid și păstrarea necunoscutului.
111 teste relevante PASS (layout, audit deplasare, corelație, sonar și repere WMO).

Fără instalare sau modificare de proces live; CC, v34 și anti-AFK neschimbate.
Rollback: revert-ul acestei probe offline; niciun consumer live nu o importă.
