# Calibrare de cameră separată de contactul actorului; prima asociere respinsă

## Modificare

`fit_landmark_projection` separă calculul și verificarea proiecției camerei
de `visual_vertical_probe`. Folosește același DLT normalizat și aceleași
limite: minimum 8 puncte necoplanare pentru fit și 4 repere separate pentru
verificare. Returnează matricea proiectivă și reziduurile numai când verificarea
numerică trece. Nu cere și nu inventează XY/Z sau contact de picior.
27 teste pentru proiecție și identitatea reperelor PASS, inclusiv calibrare
fără contact al actorului și respingerea verificării independente greșite.

Estimarea verticală experimentală existentă reutilizează funcția, apoi cere
separat contactul actorului. Comportamentul de păstrare a tuturor candidaților
și refuzul etajului confirmat rămân. Niciunul dintre aceste module nu este
integrat live; o matrice numerică nu confirmă autenticitatea asocierilor.

## Verificare pe arhiva reală

Au fost inspectate cadrele 85, 90, 94 și 98. Pentru cadrul 98, exporterul
existent a încărcat WorldPack/index/bundle verificate și a extras 331 vârfuri
și 584 muchii din grupul superior, cu secțiune Z≤147 yd. Instanța este
aceeași din auditurile precedente; algoritmul nu conține coordonate de criptă.
Export local: `data/runtime/visual-vertical-probe/landmarks-upper-v1`.

Prima ipoteză manuală a asociat 8 colțuri ale stâlpului stâng pentru fit și
4 ale celui drept pentru verificare. Asocierile au fost etichetate explicit
`TENTATIVE_MANUAL_HYPOTHESIS`, nu vertex/pixel confirmat. Coordonatele din
preview 2048×1153 au fost transformate în cadrul original 2558×1440; hash-urile
cadrului și exportului sunt păstrate în audit. Niciun Z de actor nu a fost
folosit pentru alegerea punctelor sau verificare.

Cu buget experimental 12 px, rezultatul este **REJECTED**:
eroare maximă fit 16.492 px, verificare 345.914 px. Aceasta respinge setul
curent, nu dovedește că proiecția vizuală este imposibilă. Nu distinge singură
între asociere greșită, adnotare imprecisă și extrapolare instabilă dintr-un
singur stâlp. Nu se mărește bugetul pentru a face ipoteza să treacă.

Dovadă locală ignorată: `data/runtime/visual-vertical-probe/camera-correspondence-audit-v1.json`.
Nu sunt generate coordonate Z/etaj pentru Predator din această probă.
CC live, v34, addonul și anti-AFK rămân neatinse în această etapă.

## Continuare

Sunt necesare asocieri vizuale mai sigure, distribuite în scenă și la adâncimi
diferite, înainte de un nou fit. Nu repeta optimizări pe aceleași aproximări
și nu folosi cea mai scurtă conexiune navmesh ca etichetă de adevăr. Contactul
vizibil/offsetul actorului rămâne o verificare distinctă după calibrarea camerei.
Etajul rămâne deschis în goal; sonarul condițional verificat în CC nu depinde
de reușita acestei probe.
