# Audit generic: marja traseului versus urmărirea lui

Status: instrument offline implementat; certificarea marjei FAIL. Controllerul,
workerii runtime, Control Center și autorizările nu sunt schimbate. Nu este o
a doua corecție comportamentală și nu a avut loc o probă live nouă.

## Ce verificăm

`scripts/audit_tracking_clearance.py` apelează `ContinuousTrajectoryFollower`
prin simulatorul cinematic existent. Coridoarele sunt sintetice: o linie și
un colț de 90°, cu poligoane și portal comun, inclusiv oglindire, rotație și
translație. Nu conțin coordonate, nume de structuri sau asset-uri din criptă.
Pornirile sunt în marja presupusă: abatere inițială cel mult 0,15 yd;
orientare inițială cel mult 0,15 rad. Controalele aliniate au ambele zero.
Viteza este 8,75 yd/s, iar intervalul observațiilor variază între 65–120 ms.

Distanța la întreaga polilinie XY este calculată independent de proiectorul
controllerului, inclusiv la observația terminală. Pentru aceste trasee simple
nu există etaje suprapuse sau ambiguitate topologică. Verificarea compară
abaterea cu 0,30 yd și raportează limita conservatoare `0,389 + abatere`,
față de raza bugetată de 0,689 yd. Un test fixează aceste ipoteze față de
constantele native; schimbarea lor nu poate ascunde silențios un rezultat roșu.

## Rezultat reproductibil

| Scenariu | Ajunși / 100 | Depășiri / 100 | Abatere maximă yd |
| --- | ---: | ---: | ---: |
| Linie, perfect aliniat | 100 | 0 | ~0 |
| Linie, porniri perturbate | 100 | 3 | 0,3132 |
| Colț stânga, perfect aliniat | 100 | 100 | 4,0142 |
| Colț stânga, porniri perturbate | 100 | 100 | 4,5734 |
| Colț dreapta, porniri perturbate | 100 | 100 | 4,7882 |
| Colț rotit și translatat | 100 | 100 | 4,5734 |

600/600 sosiri, 403/600 depășiri. Nicio pornire în afara marjei, pivotare zero
în aceste simulări. Rezultatul global este **FAIL**, iar comanda returnează 1.
Raportul păstrează primul contraexemplu cu seed, poziție, comandă, abatere
independentă, plus hash-urile surselor. Rezultatele nu sunt promovate în CC.

Reproducere din rădăcina repository-ului:

```powershell
.\.venv\Scripts\python.exe scripts/audit_tracking_clearance.py --output data/runtime/operator/tracking-clearance-audit-20260906.json
```

Cele 9 teste ale instrumentului trec, inclusiv rezultatul FAIL și codul de
ieșire 1. Împreună cu testele existente pentru smoothing, simulare, steering
adaptiv, replay geometric și movement engine: **297 PASS**, 20,98 s.
Acest PASS validează instrumentul și protejează comportamente existente;
nu anulează FAIL-ul clearance-ului. Verificarea statică a fișierelor noi trece.

## Limite importante

- Nu este simulat contactul fizic cu zidul. Depășirea marjei invalidează acea
  presupunere conservatoare, nu dovedește automat o coliziune.
- Colțul brusc este un caz de stres, nu dovada că pipeline-ul native ar
  accepta sau produce același traseu. Controllerul este destinat traseelor
  pre-netezite; această precondiție trebuie testată explicit în integrare.
- Auditul nu execută inset-ul, simplificatorul, selectorul adaptiv sau
  supervisorul runtime. Nu reproduce integral regresia live anterioară.
- Observațiile cinematice sunt exacte. Perturbarea pornirii și variația
  intervalului nu înlocuiesc zgomotul senzorilor, latența ori camera reală.
- Bugetul este constant aici; un coridor mai larg poate oferi spațiu suplimentar.
  Nu transformăm 0,30 yd într-un prag universal de pivotare.
- Măsurarea este la observații, nu o dovadă continuă a capsulei între ele.

## Decizie și următorul pas delimitat

Păstrăm auditul drept contraexemplu reproductibil și comparație pentru un
viitor candidat. Nu modificăm controllerul pentru a face numai acest test verde.
Următoarea verificare offline trebuie să lege traseul efectiv netezit de raza
virajului, viteza și timpul de reacție, apoi să includă observații zgomotoase.
Trebuie demonstrat când geometria permite mers continuu și când este necesară
replanificarea/alinierea; nu oprire la fiecare eșantion puțin peste marjă.
Testul integrat inset–simplificare rămâne deschis, separat de acest audit.

v34 rămâne baseline-ul de rollback, nu o versiune certificată humanlike.
Stabilizarea și goal-ul nu sunt declarate complete. Înaintea altei probe live
rămâne necesară și verificarea unei filmări efectiv salvate.
