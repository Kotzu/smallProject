# Separarea observației de decizie de observația după comandă

## Analiza probei existente

Referință: `run:f3b:a3ad6b4e-b1f4-4460-9e4b-5375f7a19732`, copia păstrată
în `data/runtime/operator/live-evidence/20260906-crypt-first/`.
Filmarea de revizie începe la secunda 95 din originalul NVIDIA; zona vizual
suspectă este aproximativ 8,5–10 s din clip, în virajele scării superioare.
Această eșantionare la 0,5 s nu demonstrează cadrul exact al contactului.
Video și timpul monotonic al motorului nu au un reper comun păstrat suficient
pentru a pretinde o sincronizare exactă la nivel de cadru.

Jurnalul vechi: 623 cadre, ARRIVED, zero collision_slide și zero blocaje.
Evaluatorul existent verifică inversări rapide/pivot/stall/captură, nu clearance
continuu al corpului. PASS nu contrazice observația utilizatorului despre zid.

Patru interogări offline, numai în asset-urile clientului, au fost făcute la
poziții istorice. Minimele razelor statice au fost:

| Timp relativ în trace | X, Y istorice | Distanță radială minimă, yd |
| --- | --- | --- |
| 4,511 s | 1646,812; 1677,743 | 2,2500 |
| 5,496 s | 1642,353; 1674,502 | 2,0625 |
| 6,483 s | 1643,916; 1668,158 | 1,40625 |
| 7,015 s | 1645,066; 1665,056 | 0,5625 |

Acestea sunt indicii de proximitate, nu contact fizic demonstrat: Z este
proiecția coridorului, razele nu reprezintă capsula personajului, geometria
a fost reinterogată ulterior. Manifestul WorldPack coincide cu ID/hash-ul
din probă; nu s-a făcut o nouă verificare hash a întregului pack. Worker-ul
curent are SHA256 `cb3555065c56a40c45c73d929a89bda6f8237fe5ffa2e018fce50fac84821d3d`;
nu se pretinde verificarea identității binare față de worker-ul istoric.
Setul inițial de 128 limite navmesh era trunchiat; nu certifică spațiul liber
în toate colțurile de la alt nivel. Nicio interogare nu a accesat clientul
sau serverul live și nicio geometrie/runtime memory nu a fost modificată.

## Lacună confirmată în cod și înregistrare

Motorul calculează intent/cross-track/lookahead din observația N, aplică
comanda, apoi citește observația N+1. În CONTINUOUS_FRAME poziția/timestamp-ul
sunt N+1, în timp ce cross-track/progress/lookahead și Z proiectat descriu
decizia N. Nu exista o identificare explicită a poziției N în același cadru.
La replanificare sau refresh înainte de comandă, nici simpla folosire a
cadrului precedent nu reconstruiește sigur acea observație.

LIVE_LOCAL_AWARENESS_APPLIED păstra pozițiile source/resolved și numărul de
limite, dar nu geometria actualizată. Lista de limite din începutul/finalul
probei nu înlocuiește setul exact disponibil în timpul virajului.

## Corecție limitată la diagnostic

- `decision_observation` copiază observația folosită la fiecare dintre cele
  trei apeluri reale de decizie: normal, retry după progres, refresh stale.
- Poziția terminală rămâne neschimbată și este marcată `post_command_observation`.
  `decision_metrics_reference` leagă metricele de observația deciziei;
  `projected_z_source` spune explicit că Z nu este observat direct din client.
- Actualizările awareness păstrează separat timpul sursei și observația
  căreia i se aplică, limitele navmesh și probele radiale deja disponibile.
  Limitele existente de 128 segmente și 64 raze nu cresc. Truncarea rămâne
  explicită și `physical_contact_proven=false` nu înseamnă contact absent.
- Nu apar interogări suplimentare în bucla live, nu se modifică inputul,
  controlerul, camera, navmesh-ul, sursele Brain sau pragurile evaluatorului.
  Câmpurile sunt aditive; cititorii și jurnalele vechi rămân compatibile.
  Nu se rescrie jurnalul istoric pentru a-i inventa dovezile lipsă.

## Verificare și continuare

9 teste noi: separare N/N+1, imutabilitatea copiei, heading necunoscut, lipsa
unui Z inventat, timestamp/truncare geometry, limită de volum, lipsa unei false
certificări, execuția izolată a celor trei blocuri reale de decizie și păstrarea
rezultatului evaluatorului existent. 391 teste relevante trecute în 11,471 s;
compilarea Python și diff-check trec. Nu s-a rulat întreaga suită.

Nu s-a făcut o nouă probă live, nu este reparare declarată a colțului, nici
promovare Stable. Costul suplimentar de jurnalizare trebuie verificat în
următoarea probă; limitele structurale nu certifică latența live.
Urmează exact lista din `../STABILITY_TASKS.md`.
Rollback: revert al commitului de diagnostic când motorul este oprit;
următorul proces de mers va încărca codul anterior. Checkpoint anterior:
`a4d0a85`, testat offline/UI, nu versiune Stable certificată.
