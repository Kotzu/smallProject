# Predator — prima probă controlată după stabilizare

Data locală: 2026-09-06, Europe/Bucharest. Tip de dovadă: controlled-live LAB.
Cod testat: `bd353f1b7cec313e7991e80359751b4c5d6f8203`, worktree curat înaintea
probei; include corecția geometrică `ce71543`. Acest raport nu acordă autoritate
de execuție și nu promovează Stable.

## Configurație și intervenții

- Clientul LAB a fost lansat prin operatorul existent, cu identitate verificată.
  Autentificarea a fost făcută de utilizator. Intrarea efectivă în lume a fost
  verificată vizual, apoi godmode a fost confirmat ON pentru Predator.
- Reset canonic de setup prin `Reset-LabPlayerToSpawn.ps1`, confirmare
  `LAB_SPAWN_RESET:PLAYER=Predator:SOURCE=CANONICAL_PLAYERINFO`.
  Ground truth-ul serverului a fost folosit pentru setup, nu drept input Brain.
- Poziție observată la pornire aproximativ `(1676.37, 1677.47)`, Shadow Grave.
  Verificarea staționară: 21 mostre / 4,009 s, drift și jitter detectate zero.
- Control Center: Deathknell, drum ales autonom, permisiunea de mers activă,
  controlul manual Codex oprit. Start a confirmat din nou godmode.
- `adaptive_trajectory_v1`, `maximum_combat_handoffs=0`, continuare aggro activă.
  Fără waypoint-uri manuale, comenzi manuale de mers sau modificări de cod
  între pornire și sosire. Interfața a fost operată cu skill-ul computer-use.
- Filmare NVIDIA pornită înainte de Start; creșterea fișierului a fost verificată.
  Filmarea a fost oprită după ARRIVED. Procesele de navigație/supervisor au ieșit.

## Rezultat confirmat

Run: `run:f3b:a3ad6b4e-b1f4-4460-9e4b-5375f7a19732`.
Supervisor: `journey-combat:57291925-d9c9-4443-ac13-e8201b948d81`.

- ARRIVED, un ciclu, 623 cadre, 33,543 s de control (nu include pregătirea).
- 619 cadre/acțiuni forward; 4 cadre pivot; zero întoarceri discrete.
- Zero forward-stall frames, zero recuperări locale/globale, zero replanificări
  parțiale. Cel mai lung interval forward fără progres: 0,232 s.
- Poziție finală `(1809.170551, 1593.001121)`, la 34,513 yd de centrul
  destinației; raza semantică este 35 yd. Nu este sosire exactă în centru.
- Evaluatorul existent trece inclusiv cerințele explicite client-facing source,
  body/camera separation și camera integrity: 623/623 pentru fiecare.
- Zero inversări rapide de steering. Șapte intervale observaționale peste
  300 ms, maxim 0,358 s; toate sunt exceptate de evaluatorul existent prin
  dovada continuității mișcării. Nu s-au schimbat pragurile evaluatorului.
- Cadrele live și eșantionarea video la 2 secunde arată ieșirea pe scări, apoi
  deplasarea pe drumul exterior și oprirea la poarta Deathknell. Această
  inspecție eșantionată nu este o aprobare vizuală integrală a utilizatorului.

## Observații și limite

1. Pregătirea înainte de primul pas a fost vizibil lungă; timpul de 33,543 s
   nu o include. Merită măsurată separat înainte de optimizare.
2. Două `CONTINUOUS_MOTION_ARM_RENEWAL_REJECTED` au raportat
   `runtime arm does not bind realm revalidation`. Autorizarea încă validă a
   fost păstrată, iar două reînnoiri live au reușit. O posibilă citire între
   actualizările fișierelor este o ipoteză de investigat, nu un diagnostic
   confirmat. Nu se elimină verificarea identității pentru a ascunde mesajul.
3. Camera nu a fost ajustată manual. Comportamentul existent a înregistrat
   WMO_NAV și tranziția amânată OUTDOOR_HUNT aplicată la final; deci camera
   nu trebuie descrisă ca fizic neschimbată pe tot traseul.
4. Opt obstacole memorate încărcate, zero obstacole noi persistate. Proba nu
   reproduce contactul cu masa de sub scară din ME503 și nu demonstrează
   separat repararea lui. Nu validează combatul sau robustețea prin aggro.
5. O probă reușită nu certifică repetabilitatea, roaming general sau alte
   clienți/servere. Registrul de aprobare vizuală rămâne neschimbat, 0/10.
6. La verificarea finală, Control Center avea Start disponibil, dar textul
   secundar încă spunea „Acum: merge”, iar verificarea staționară afișa proba
   anterioară din criptă. Acestea nu sunt dovezi că personajul încă se mișcă:
   supervisorul a raportat ARRIVED, procesele de mers au ieșit și oprirea a fost
   observată în joc. Prospețimea și etichetarea acestor texte UI necesită
   verificare separată; nu s-au schimbat în această probă.

## Artefacte locale — nu se comit filmarea sau telemetria

În repository:

- `data/runtime/navigation-f3b/results/navmesh-roaming-a3ad6b4e-b1f4-4460-9e4b-5375f7a19732.json`
  SHA256 `90B255EFEEE411F1BC27F69E5EEFB37FC800B95A4FF4E691C66D494C1BE7F149`.
- `data/runtime/navigation-f3b/live-trace-quality-20260906-crypt-first.json`.
- Copii ale dovezilor volatile în `data/runtime/operator/live-evidence/20260906-crypt-first/`.

Video original: `C:\Users\LabUser\Videos\NVIDIA\Wow.exe\Wow.exe 2026.09.06 - 00.49.01.01.mp4`,
161,432 s / 939.245.257 bytes,
SHA256 `1C3D98BB06C96F132F642516C1DC2B343AA8CA3AEEFABBBD8A35B78D8CDF7A42`.

Clip de revizie de 40 s, extras din original la secunda 95, fără modificarea
originalului: `outputs/Predator-Shadow-Grave-Deathknell-20260906.mp4` în task-ul
Codex din `C:\Users\LabUser\Documents\Codex\2026-09-05\referenced-chatgpt-conversation-this-is-an`.

## Continuare delimitată

Păstrăm această probă drept referință a codului curent. Urmează repetabilitatea
aceleiași ieșiri și reproducerea exactă a mesei ME503. Investigăm separat
latența de pregătire și reînnoirea autorizării, fără rescrierea controlerului,
relaxarea protecțiilor sau un nou bake global.
