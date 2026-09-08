# Replay offline: regresia începe înaintea colțului vizat

Status: diagnostic, fără modificare de comportament și fără input de navigație.
Candidatul rămâne respins; runtime v34 nu se schimbă.

## Probe și metodă

Se folosesc cele două jurnale identificate în
`../LIVE_CORNER_CANDIDATE_REJECTION_2026-09-06.md`. Aceeași poziție/heading de
start, același WorldPack și aceeași deschidere structurală. Se reconstruiește
primul coridor folosind fiecare worker, apoi follower-ul de producție consumă
în ordine primele 80 de observații de decizie ale fiecărei probe.
Rezultatele lookahead și cross-track coincid numeric exact cu jurnalul în
80/80 cadre pentru v34 și 80/80 pentru candidat. Testul verifică geometria
deciziei; NU simulează fizica clientului și nu reproduce toate comenzile finale.
Replay-ul încrucișat păstrează pozițiile înregistrate fixe; nu este o predicție
a pozițiilor pe care le-ar fi executat celălalt controller.

## Constatare confirmată

Traseul candidat este diferit deja pe segmentul de apropiere, nu exclusiv în
zona colțului urmărit. La prima decizie lookahead diferă cu 0,342740 yd.
La poziția candidatului din cadrul 68, cross-track este 1,487998 yd față de
traseul candidat, dar 2,717038 yd față de traseul v34. Diferența 1,229040 yd
arată schimbarea referinței geometrice la aceeași poziție, nu mișcarea corpului.
Lookahead-ul calculat din aceeași secvență de poziții diferă cu 1,596662 yd.
Poziția este aproximativ 1655,546 / 1675,192; primul no-progress >0,5 s apare
acolo la +4,540 s. Nu se compară cadrele celor două probe ca momente identice:
cadrele au durate diferite, iar pozițiile la cadrul 68 sunt diferite.

La cadrul 68 candidat, jurnalul arată FOLLOW, mouse delta cerut 0, abatere de
direcție circa 0,04 rad și abatere transversală circa 1,49 yd. Controllerul
folosește curbura spre lookahead, apoi rotunjește comanda în pixeli; abaterea
transversală singură nu obligă la o virare. Nu este corectă ipoteza că viteza
observată zero explică aici comanda zero: viteza folosită de decizie este
aproximativ 8,75 yd/s, chiar în cadrul fără progres. Proveniența/persistența
acestei estimări rămâne de investigat separat, nu se corectează prin presupunere.

## Control pentru diferențe de build

Sursa `main.cpp` și CMake din părintele commitului `7015e3f` au fost extrase
în directorul de lucru al taskului și compilate într-un build separat, folosind
aceleași căi de dependențe ca ambele build-uri inspectate. Niciun executabil
runtime și nicio sursă de dependență nu au fost suprascrise.
Cele 63 puncte ale primului coridor reconstruite astfel coincid exact cu v34,
nu cu cele 61 ale candidatului. Pentru ACEASTĂ interogare, schimbarea sursei
candidatului explică diferența geometrică; nu se pretinde identitate binară
sau echivalență globală a executabilului istoric cu sursa recompilată.

## Implicații pentru stabilizare

Corecția locală a razei nu a fost neutră pentru restul traseului. Testele
locale și reachability-ul celor 529 de etape nu protejau suficient apropierea
executată. Respingerea și restaurarea v34 sunt justificate; nu mărim global
raza și nu schimbăm camera pentru a masca rezultatul.
Următorul diagnostic delimitat: legătura dintre colțul mutat, simplificarea
traseului și segmentul lung de apropiere; separat, estimarea vitezei în lipsa
progresului. Viitoarea corecție trebuie testată pentru întregul coridor și
comportamentul executat, nu doar pentru distanța unui punct la un colț.
Nu există încă o corecție nouă autorizată/testată sau validare humanlike.

## Captură: progres separat, încă nerezolvat automat

Clipul manual `Wow.exe 2026.09.06 - 11.55.22.11.mp4` este valid: 3,742911 s,
H.264 2560x720; un cadru decodat arată WoW și desktopul. Nu dovedește că
metoda automatizată funcționează. Testul ulterior fără screenshot intermediar
(`get_window_state` doar text) produce din nou notificare Protected Content,
la 12:01:07.185, urmată de oprire. Ipoteza screenshot-ului imediat ca explicație
unică nu este susținută. Nu se declară că browserele sunt cauza confirmată;
nu se opresc alte aplicații la întâmplare și nu se ocolesc protecțiile.
Înaintea unei probe live viitoare, filmarea trebuie confirmată persistent și
verificat fișierul rezultat. Filmul manual scurt nu repară retroactiv lipsa
filmării candidatului.

## Artefacte

În arhiva locală ignorată `data/runtime/operator/live-evidence/20260906-corner-candidate/`:
`first-stall-comparison.json` și `compare_corner_first_stall.py` conțin replay-ul
și procedura; scriptul original folosește directorul de lucru al taskului.
Build-ul de control rămâne în `work/probe-pre-candidate-build` al taskului,
niciodată ca worker activ. Nicio telemetrie brută sau filmare nu intră în Git.
