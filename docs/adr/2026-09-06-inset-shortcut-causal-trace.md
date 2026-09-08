# Cauza schimbării apropierii: inset → alegerea altei scurtături

Status: diagnostic offline confirmat pentru prima interogare a celor două
probe. Nicio corecție nouă și nicio probă de navigație live. Runtime v34 păstrat.

## Izolare

Au fost construite două executabile de diagnostic în directorul `work/` al
taskului, din `7015e3f^` și `7015e3f`. Instrumentarea scrie pe stderr etapele
și motivele refuzului, fără schimbarea rezultatului stdout. Pentru fiecare
variantă, întregul JSON rezultat este comparat cu executabilul original și
trebuie să fie identic. Ambele comparații trec, inclusiv după separarea
diagnostică a celor două teste de raze, cu ordinea short-circuit păstrată.
Nu au fost modificate executabilele runtime, WorldPack-ul, dependențele,
camera, Control Center sau controllerul.

## Lanțul confirmat

1. Cele 7 puncte ale traseului Detour inițial coincid între variante.
2. Cele 12 puncte după ocolirile locale, înainte de inset, coincid.
3. După inset, diferă un singur punct, index 7: deplasare XY 0,391215 yd,
   Z neschimbat. Numărul punctelor rămâne 12 în ambele variante.
4. Simplificatorul încearcă de la fiecare punct cea mai îndepărtată țintă
   care trece verificările. Din punctul 0, v34 respinge ținta 7 și alege 6;
   candidatul acceptă ținta 7. Astfel schimbarea locală a unui colț modifică
   direct segmentul de apropiere încă de la start.
5. Respingerea v34 pentru 0→7 apare la mostra 22, în
   `doodad_capsule_clear_at_height` cu `kPreferredLowObstacleProbeHeight=0.35`.
   Motivul instrumentat este `preferred_low_ray`, nu buget epuizat și nici
   refuz de pantă/înălțime. Testul de capsulă anterior acestei sonde trece
   pentru mostra respectivă; nu generalizăm acest fapt la restul traseului.
6. Rezultatul final este 63 de puncte pentru v34, 61 pentru candidat.
   Acestea sunt traseele care au fost reproduse exact în primele 80 de
   observații din fiecare probă în diagnosticul anterior.

| Variantă | Scurtături alese, indici pre-simplificare | Primul segment |
| --- | --- | --- |
| v34 | 0→6, 6→8, 8→10, 10→11 | start către punctul 6 |
| Candidat | 0→7, 7→9, 9→10, 10→11 | start către punctul 7 mutat |

Indicii sunt locali interogării înregistrate, nu waypoint-uri manuale,
reguli pentru Shadow Grave sau identificatori care trebuie introduși în Brain.

## Ce dovedește și ce nu dovedește

Este demonstrat mecanismul prin care modificarea inset-ului schimbă segmentul
de apropiere. Nu este demonstrat că sonda joasă este greșită sau că trebuie
eliminată. Nu este demonstrată coliziunea fizică exactă a capsulei vizibile
doar din raycast-ul diagnostic; filmul probei candidatului lipsește.
Un refuz la o mostră discretă și un succes pe o altă linie nu reprezintă o
garanție asupra mișcării reale, care poate părăsi acea linie.

Codul native rezervă raza 0,389 + abaterea 0,30 = 0,689 yd pentru tunel.
La primul blocaj observat, cross-track-ul candidatului este 1,487998 yd,
deci în afara marjei de tracking presupuse de acea verificare. Aceasta arată
nepotrivirea dintre ipoteza planificatorului și execuția înregistrată, nu
certifică faptul că fiecare abatere >0,30 yd produce o coliziune. Și baseline-ul
poate depăși 0,30 yd; nu trebuie prezentat drept fundație de clearance certificată.

## Direcția următoarei etape

Nu reparăm situația prin eliminarea sondei joase, creșterea globală a razei,
waypoint-uri manuale sau modificări ale camerei. Înaintea unei a doua corecții:

- un test generic trebuie să acopere interacțiunea inset–simplificare, nu
  numai distanța unui singur colț;
- execuția trebuie evaluată față de marja geometrică realmente verificată,
  inclusiv pornirea și abaterea acumulată înainte de lipsa progresului;
- încălcarea marjei nu justifică automat pivotare sau oprire la orice cadru:
  mecanismul de reacție necesită testare cu observații zgomotoase și pasaje înguste;
- următoarea schimbare trebuie aleasă separat, după acel test, cu baseline
  păstrat și fără amestecarea reparării filmării cu controllerul.

Goal-ul de stabilizare nu este declarat complet. Candidatul deja respins nu
este reactivat. Limita etapei actuale rămâne diagnostic și păstrarea dovezilor.

## Reproducere și dovezi locale

Arhivă ignorată de Git:
`data/runtime/operator/live-evidence/20260906-corner-candidate/pipeline-causal-trace/`.
Include `corner-pipeline-trace.json`, scriptul `trace_corner_pipeline.py` și
sursele instrumentate baseline/candidate; JSON-ul păstrează hash-urile lor.
Executabilele de diagnostic rămân în `work/stages-*-build` al taskului.
Scriptul original rulează din directorul taskului și folosește asset-urile
locale; nu trimite input clientului și nu accesează serverul.
Legătură cu execuția: `2026-09-06-first-stall-replay.md` și
`../LIVE_CORNER_CANDIDATE_REJECTION_2026-09-06.md`.
