# Continuitate verticală: serviciu persistent numai pentru observație

## Decizie

Un proces separat păstrează navmesh-ul încărcat și răspunde la perechi de
suprafețe candidate. Modul explicit este `--vertical-continuity-server`;
nu generează input, nu selectează etajul și nu înlocuiește navigatorul v34.
Integrarea în observer și Control Center NU este încă făcută.

Protocolul păstrează capetele cerute și proiectate, poligoanele, rezultatul
complet/parțial și lungimea poliliniei funnel. Interogările sunt limitate la
64 yd orizontal și 512 poligoane/puncte. Clientul verifică hash-ul extern al
executabilului, secvența, coordonatele și câmpurile permise; închide procesul
la eroare de protocol. Apelantul trebuie să lege rezultatele de sesiune,
hartă, WorldPack și prospețimea ambelor observații. Nu folosi serviciul
sincron în firul interfeței.

## Dovezi offline

Build separat reușit, testul nativ existent `spatial_height_scan` PASS.
Opt perechi din arhiva tranziției 98/99→100s, același proces: prima cerere
244.535 ms, următoarele 0.202–0.317 ms. Procesul s-a închis cu codul 0.
Acesta este un benchmark local restrâns, nu o garanție globală de latență.

La 99→100s, alternativa superioară are funnel 7.200 yd, cea inferioară
68.430 yd; acoperișul produce rezultat incomplet. Candidații superiori
apropiați se proiectează pe același poligon în aceeași sesiune a workerului.
Referințele poligoanelor nu sunt identități portabile între builduri/hărți.

Filtrul Detour are costuri neutre. Lungimile inferioare diferă de auditul
v34 (89.124 yd), care folosește preferințe și rafinări de mișcare. Nu sunt
ieșiri echivalente și nu demonstrează o regresie v34. Funnel-ul nu certifică
volumul traversabil, traseul fizic parcurs sau absența unei alternative mai
scurte. Nu impunem prag de viteză și nu promovăm o proiecție la Z observat.

78 teste Python relevante PASS: parser, păstrarea proiecțiilor, limite,
autoritate nulă, hash înainte de lansare, reutilizarea procesului,
respingerea răspunsurilor incorecte și închiderea fluxului desincronizat. Testele cu
proces simulat nu înlocuiesc benchmark-ul nativ real.

## Identitate și rollback

Executabil exclusiv observație:
`data/runtime/native-build/pa-nav-continuity-observer/Debug/pa_nav_probe.exe`
SHA256 `2b6448ce97c7be4f69784ec6663740d2d7d54fbd0cc063408e7552f2fb31ca64`.
WorldPack SHA256 `a9feb578fea082f073effd84415977fa8a760ed2e5b2f8b07a1609215fe56b78`.
Dovada locală ignorată de Git:
`data/runtime/minimap-wmo-probe/persistent-continuity-v1.json`.

ATENȚIE: sursa generală a probei conține și candidatul de mișcare respins.
Acest executabil nu se instalează ca worker de mișcare. v34 rămâne nemodificat,
cu hash `cb3555065c56a40c45c73d929a89bda6f8237fe5ffa2e018fce50fac84821d3d`.
Nimic nu a fost activat în CC/live; rollback-ul acestei etape înseamnă să nu
pornești serviciul opțional. Anti-AFK, addonul și credențialele sunt neatinse.

## Următorul pas

Loturi asincrone limitate între toate alternativele a două observații,
cu identificarea explicită a perechilor neinterogate, invalidare la schimbarea
sesiunii/hărții/pack-ului și la expirare. Afișare read-only în CC, fără
eliminarea candidaților pe baza lungimii minime. Închidere la schimbarea
hărții și la oprirea observerului; activare opțională, implicit dezactivată.
