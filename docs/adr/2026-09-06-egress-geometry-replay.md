# Replay geometric înaintea schimbării virajelor

Status: instrument read-only verificat offline; controlul live rămâne neschimbat.

## Constatări confirmate

Pe înregistrarea `8544bb3c`, primele **140 cadre** au fost reproduse geometric:
zero diferență pentru lookahead XYZ, abatere transversală și Z proiectat.
Nu am reprodus comenzile actuatorului sau evoluția fizică după comenzi modificate.
Replay-ul consumă pozițiile de decizie înregistrate, nu pozițiile de după comandă.

În timpul ieșirii din structuri, runner-ul selectează
`ContinuousTrajectoryFollower`, separat de controlerul adaptiv al misiunii.
Traseul de apropiere păstrat de `MovementEngine` duce la deschiderea clădirii;
ținta exterioară și continuarea sunt alte elemente ale planului. O interogare
directă până la ținta exterioară NU reproduce același traseu: prima încercare
de reconstrucție a diferit cu până la 0,938 yd în lookahead. Folosirea deschiderii
înregistrate a eliminat toate diferențele pe prefixul verificat. Aceasta este
o corecție a metodei de analiză, nu un bug de movement declarat rezolvat.

Interogări offline pe același WorldPack, după confirmarea identității din
manifest și a reproducerii geometrice:

| Cadru | Abatere de la traseu | Sondă minimă la poziția Predatorului | Sondă minimă pe traseu |
|---|---:|---:|---:|
| 103 (+6,309 s) | 0,898 yd | 0,469 yd | 1,406 yd |
| 108 (+6,545 s) | 0,260 yd | 0,375 yd | 0,563 yd |
| 133 (+7,719 s) | 0,841 yd | 0,281 yd | 1,125 yd |

Interpretare limitată: în 103/133, abaterea de urmărire contribuie la apropierea
de obstacol; în 108, chiar traseul are o sondă scurtă. Numerele sunt sonde
radiale din asset, NU distanța pielii/capsulei de zid și NU contact fizic dovedit.
În 133, reinterogarea proiectează înălțimea cu circa +1,2 yd pentru ambele
puncte; interpolarea Z a traseului nu se confundă cu o înălțime observată.
Nu deducem siguranța capsulei doar din aceste sonde finite sau din navmesh.

Ipoteza „frânarea virajului provoacă singură apropierea” nu este demonstrată:
în cadrul 103, orientarea observată are deja componentă spre traseu, nu
departe de el. Eliminarea acelei frânări fără test ar fi un reglaj pe presupuneri.

## Decizie și protecție împotriva regresiilor

Adăugăm `scripts/replay_structure_egress_geometry.py`, independent de numele
zonei și fără coordonate de navigație hardcodate. Primește înregistrarea,
worker-ul, WorldPack-ul și prefixul de analizat. Refuză să interpreteze sondele
de pe traseul reconstruit când metricile geometrice nu coincid cu înregistrarea.
Nu apelează clientul, serverul, Control Center sau gateway-ul de input.
Nu schimbă fișierele runtime în afara raportului cerut explicit.

Cinci teste sintetice verifică potrivirea, refuzul unui lookahead diferit,
refuzul unui nivel diferit, lipsa mostrei de decizie și prefixul gol. Testele
validează instrumentul; dovada geometrică pentru LAB este rularea pe cele
140 cadre, păstrată separat în directorul de dovezi ignorat de Git.

Reproducere din rădăcina repository-ului:

```powershell
.venv/Scripts/python.exe scripts/replay_structure_egress_geometry.py data/runtime/navigation-f3b/results/navmesh-roaming-8544bb3c-f0f6-41f1-84d5-8e7952458f56.json --nav-root E:/WoWserver/PerfectAssassin-Runtime/worldpacks/tbc243-azeroth-full-v3 --worker data/runtime/native-build/pa_nav_probe-v34/Debug/pa_nav_probe.exe --through-frame 140 --sample-frames 103 108 133 --output data/runtime/operator/live-evidence/20260906-crypt-diagnostic/geometry-replay.json
```

## Următorul pas, fără extindere de scop

Test offline al spațiului necesar corpului pe un colț generic, înainte de a
schimba planner-ul sau controlerul: separă raza capsulei, marja de confort și
abaterea admisă. Verifică dacă inset-ul navmesh existent include deja raza,
pentru a nu o adăuga de două ori. Apoi confruntă regula cu segmentul reprodus.
Doar o cauză demonstrată justifică o corecție generală și o nouă probă filmată.
Nu se modifică traseul manual al criptei, camera, combatul sau Control Center.

Rollback: se pot elimina exclusiv instrumentul, testele și această documentare;
controlerul/profilurile live nu au fost schimbate în acest pas.
