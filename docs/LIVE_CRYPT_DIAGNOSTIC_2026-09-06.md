# Predator — repetare filmată cu jurnalul de decizie

2026-09-06, Europe/Bucharest. Controlled-live LAB, cod `89e5d56`, worktree
curat înaintea probei. Un singur Start din Control Center; fără modificări
de steering, cameră, navmesh sau praguri. Nu promovează Stable.

## Setup și rezultat

- Client LAB deja în world, verificat vizual; receipt pentru PID 10756,
  build 2.4.3.8606, profil `tbc_243_lab`. Runtime-ul existent păstrează
  verificările de identitate și reînnoire; nu s-au ocolit aceste verificări.
- Reset canonic Shadow Grave prin scriptul LAB; godmode și stay-online ON,
  confirmate de server. Serverul este folosit pentru setup, nu input Brain.
- Verificare staționară CC: 21 mostre / 3,995 s, drift și jitter zero;
  poziție `(1676.37, 1677.47)`, în zona așteptată.
- Deathknell, drum autonom, manual Codex dezactivat, fără combat automat.
  Interfața și înregistrarea au fost operate prin skill-ul computer-use.
- Start apăsat la 01:55:09,297; pregătirea până la primul mers este aproximativ
  70 s din filmare, nu o măsurătoare sincronizată la nivel de cadru.
- Run `run:f3b:8544bb3c-f0f6-41f1-84d5-8e7952458f56`, supervisor
  `journey-combat:ff6c6b8b-3845-4ada-9a12-28702ae61b48`.
- ARRIVED, 626 cadre, 33,571 s de control, 617 forward / 9 pivot;
  zero stall frames, zero recuperări și zero replanificări parțiale.
- Final `(1808.710873, 1592.794266)`, la 34,953 yd de centrul destinației
  cu rază 35 yd. Nu este sosire exactă în centru.
- Opt obstacole memorate încărcate, zero noi persistate. 166 actualizări
  awareness, fără eroare finală raportată.
- Procesele de navigație/supervisor au ieșit. Oprirea a fost observată în joc;
  CC arată „A ajuns” și „Motor oprit”, cu poziția live în continuare proaspătă.

## Verificarea jurnalului și comparația cu prima probă

Evaluatorul existent, fără schimbarea pragurilor, trece cu toate cele trei
cerințe: client-facing source, body/camera separation, camera integrity.
Acest PASS nu certifică distanța corpului de zid sau mișcarea humanlike.

| Măsură | Prima probă `a3ad6b4e` | Diagnostic `8544bb3c` |
|---|---:|---:|
| Durată control | 33,543 s | 33,571 s |
| Cadre | 623 | 626 |
| Inversări rapide detectate | 0 | 4 |
| Cadre pivot | 4 | 9 |
| Intervale observaționale >300 ms | 7 | 8 |
| Cel mai mare interval | 358 ms | 440 ms |
| Captură mediană / P95 | 28,859 / 40,242 ms | 28,671 / 40,013 ms |
| Observație mediană / P95 | 35,336 / 49,238 ms | 35,067 / 48,590 ms |
| Dimensiune rezultat JSON | 1.548.429 bytes | 3.023.951 bytes |

Toate cele opt intervale mari sunt exceptate de evaluator prin dovada
continuității mișcării. Captura maximă crește de la 110,734 la 120,269 ms;
observația maximă de la 116,466 la 128,931 ms. Două probe nu izolează efectul
jurnalizării de variația runtime-ului; nu afirmăm nici cost zero, nici o
regresie cauzată de jurnal. Medianele/P95 sunt apropiate; rezultatul ocupă
aproape dublu pe disc. Dimensiunea rămâne delimitată de numărul actualizărilor.

- 626/626 cadre conțin `decision_observation`; timestamp-ul deciziei este
  anterior sau egal observației ulterioare în toate cadrele.
- Diferență decizie → observație ulterioară: mediană 38,676 ms, P95 108,263 ms,
  maxim 148,433 ms. Aceasta nu este doar latență de captură.
- 166/166 actualizări rețin `boundary_evidence`. În criptă setul de 128
  segmente este marcat trunchiat: nu poate certifica spațiul liber complet.
- Timestamp-ul geometriei poate fi cu câteva ms după timestamp-ul poziției
  la care este aplicată, din cauza lucrului asincron. Diferența lor nu trebuie
  redenumită automat „vechimea geometriei la execuție”.
- Cele patru inversări rapide apar la +13,313 / +16,418 / +26,908 / +33,239 s
  față de primul cadru, ulterior zonei scării. Nu explică singure problema
  colțurilor din criptă.

## Ce arată zona suspectă

Revizuire eșantionată: traseul complet la 1 fps și secvența scării la 6 fps.
Se văd treceri strânse pe lângă zid și schimbări rapide ale compoziției camerei
în spațiul îngust. Nu este o certificare de contact fizic cadru cu cadru.
Camera nu a fost ajustată manual; profilurile existente WMO_NAV și tranziția
amânată OUTDOOR_HUNT au rămas active.

Jurnalul nou restrânge investigația fără a inventa contactul:

| Timp față de primul cadru | Poziția deciziei XY | Cea mai scurtă sondă radială | Eroare față de traseu |
|---|---|---:|---:|
| +6,309 s | 1644,790 / 1667,469 | 0,469 yd | 0,898 yd |
| +6,545 s | 1644,974 / 1665,400 | 0,375 yd | 0,260 yd |
| +7,719 s | 1651,777 / 1665,194 | 0,281 yd | 0,841 yd |

Sondele sunt estimări din geometria clientului, nu măsurarea distanței pielii
personajului de zid. La +6,545 s, eroarea mică față de traseu coexistă cu o
sondă scurtă: nu avem bază să atribuim totul numai urmăririi slabe a traseului.
Trebuie verificată și distanța traseului cerut față de obstacol. La celelalte
două mostre abaterea de urmărire este mai mare. Cauza nu este încă separată.

Reapar două refuzuri de reînnoire a armării și două reînnoiri reușite;
autorizația încă validă este păstrată. Investigația pornirii/reînnoirii rămâne
separată, fără relaxarea mecanismului de protecție.

## Pasul următor delimitat

Replay offline al acestor ferestre: comparație între corp/poziție, segmentul
cerut și geometria aceluiași nivel, folosind ordinea evenimentelor și mostrele
din decizie. Mai întâi separăm traseu prea strâns de abatere de urmărire și de
compoziția camerei. Apoi un test care reproduce cauza, o singură corecție
generală, testele relevante și o probă filmată. Fără excepții pentru criptă,
coordonate fixe sau secvențe de viraje temporizate. ME503 rămâne separat.

## Dovezi locale (ignorate de Git)

Director: `data/runtime/operator/live-evidence/20260906-crypt-diagnostic/`.
Conține rezultat, evaluator, raport staționar, supervisor, log, profil și
memoria obstacolelor înainte/după. Nici filmările, nici telemetria nu se comit.

Rezultat: `navmesh-roaming-8544bb3c-f0f6-41f1-84d5-8e7952458f56.json`.
SHA256 `E2E220E4879F00BAFFDB72A9546084719CF5D408C3B772BDA20CF88877A0A511`.

Video original: `C:\Users\LabUser\Videos\NVIDIA\Wow.exe\Wow.exe 2026.09.06 - 01.54.50.02.mp4`.
149,274 s, 889.628.156 bytes, SHA256
`A82189BB2B756E71A9E2AC52D07F2200270727D1053A6A64506EE42FE0AD06BD`.
Extras de vizionare: secundele 85–130 din original, fără audio, aproximativ
45 s; timpul din clip nu coincide cu timpul relativ al trace-ului.

Progres acceptat: jurnal diagnostic validat live și sosire tehnică repetată.
Neacceptat ca rezolvat: distanța confortabilă de zid, humanlike, repetabilitate
generală. Registrul aprobării vizuale nu a fost modificat.
