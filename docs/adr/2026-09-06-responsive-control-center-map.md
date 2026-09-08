# Control Center — hartă centrată și adaptivă

## Defect confirmat

Scara era fixă în pixeli (zoom întreg 1–8), independentă de suprafața ferestrei.
Urmărirea lui Predator muta atlasul inclusiv când încăpea complet, expunând
zone goale asimetrice și tăind restul hărții. „Toată harta” nu dezactiva
urmărirea, deci refresh-ul putea anula imediat resetarea.

## Corecție UI

- Zoom 1 înseamnă încadrare proporțională completă la dimensiunea curentă.
  Marginile necesare păstrării proporțiilor sunt simetrice, nu se deformează harta.
- La zoom, urmărirea centrează personajul când geometria permite; aproape
  de margine se oprește la limita atlasului, fără spațiu gol artificial.
- Pan-ul este în pixeli ai atlasului, nu în coordonate world. Drag-ul este
  limitat inclusiv în starea memorată, pentru răspuns imediat la inversare.
- Zoom-ul manual și „Toată harta” dezactivează urmărirea; aceasta se reactivează
  explicit prin „Urmărește Predatorul”. Modul nu este schimbat de poziția nouă.
- Redimensionările sunt grupate într-un singur callback la 40 ms. Actualizarea
  existentă de 250 ms rămâne; nu se adaugă proces/polling/gateway de gameplay.
- Harta, overlay-ul transparent și marcajele folosesc aceeași transformare.
  Rasterizarea este limitată la suprafața vizibilă, nu creează atlase complete 8x.
  Cache-ul păstrează o singură imagine pe strat și reutilizează vederea nemodificată.
- Bara hărții are rânduri separate pentru stare, comenzi și cursor, evitând
  înghesuirea lor pe un singur rând.

Dependență UI: Pillow 12.3.0, fixată în extra-ul `control-center` și
`requirements.lock`, instalată în `.venv` local. Pentru alt checkout:
`.venv/Scripts/python.exe -m pip install -e ".[control-center]"`.
Brain și motorul de deplasare nu depind de acest renderer.

## Verificare și limite

362 teste relevante trecute în 11,375 s, inclusiv 13 noi pentru încadrare,
margini, resize, urmărire, zoom/cursor, transformarea inversă, transparență,
alinierea markerului, coalescing și limita cache-ului. Testul de etichetă UI
existent a fost actualizat pentru „Urmărește Predatorul”. Nu este întreaga suită.

Verificare vizuală cu skill-ul computer-use, în Control Center relansat:
fereastră normală, maximizare ultrawide, revenire la normal, zoom 2x,
reactivarea urmăririi și „Toată harta”. Harta rămâne proporțională/centrată,
iar poziția live rămâne aliniată. Motorul a rămas oprit; nu s-a apăsat Start.
Aceste verificări nu certifică un framerate minim sau toate configurațiile DPI.

Nu s-au modificat mișcarea, camera jocului, navmesh-ul, autorizarea sau serverul.
Punct anterior: `8016e89`, checkpoint testat, nu versiune Stable certificată.
Rollback: revert al commitului acestei corecții și relansarea doar a Control
Center când nu rulează nicio probă. Pillow poate rămâne instalat fără a fi folosit.
