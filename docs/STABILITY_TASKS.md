# Predator — lista delimitată de stabilizare

> Lista consolidată actuală este `PREDATOR_BACKLOG.md` (2026-09-07).
> Cele de mai jos sunt istoricul stabilizării; unele stări, inclusiv transportul
> API și afișarea sonarului, au fost depășite. Nu se folosesc ca status curent.

Actualizat: 2026-09-06. Ordinea nu se extinde implicit la hunting/combat.

Plan spațial detaliat, păstrat la cererea operatorului:
`SPATIAL_AWARENESS_PLAN.md`. Nume API și prezentare istorică implementate;
125 teste relevante PASS, integrare verificată pe export real.
Transportul live către CC și legarea Z/etajului rămân deschise.

Rezultat curent: candidatul `7015e3f` a fost testat live o singură dată și
respins (ARRIVED, calitate FAIL). CC a revenit la v34, gate și obstacole
restaurate. Captura NVIDIA a eșuat după pornire; proba nu are clip salvat.
Raport: `LIVE_CORNER_CANDIDATE_REJECTION_2026-09-06.md`. Stabilizarea nu este
încheiată; continuarea corecțiilor/probelor necesită o etapă delimitată nouă.

- [x] Control Center: rapoarte invalide și prospețimea stării motorului.
- [x] Cerere separată AFK: un Space per episod confirmat în client, opt-in
  la pornirea CC; 423 teste relevante PASS și o tranziție controlată live.
  Nu este test de anduranță; limite în `adr/2026-09-06-observed-afk-single-space.md`.
- [x] Control Center: hartă centrată/adaptivă, verificată vizual.
- [x] Analiza filmării existente: restrângerea zonei suspecte la colțurile scării;
  separarea indiciilor de dovada efectivă a unei coliziuni.
- [x] Diagnostic: poziția deciziei separată de observația după comandă;
  păstrarea geometriei locale la actualizare, cu timestamp și truncare explicite.
- [x] O singură probă LAB filmată Shadow Grave → Deathknell, aceleași setări
  de control, cu jurnalul îmbunătățit. Înainte: profil/client, început canonic,
  godmode + stay-online confirmate, filmare și autorizare runtime valide.
  Verificăm datele noi, colțurile scării, lipsa regresiilor și timpul de captură.
- [ ] Corelarea probei cu geometria și comenzile. Abia apoi alegem o corecție
  de ghidaj sau control, dacă este demonstrată cauza; o schimbare → teste →
  probă filmată → acceptare/revenire. Nu se confundă ARRIVED cu humanlike.
  Progres: primele 140 cadre reproduse geometric exact; contribuții distincte
  din abatere și apropierea traseului de obstacol. Candidat de corecție a razei
  la colț comun orizontal: 18 cazuri C++ și 417 teste Python PASS, numai offline.
  Candidat `7015e3f`: și toate cele 6 cazuri semantice PASS (529 etape), pe
  executabilul final cu protecție pentru pante; nu sunt deplasări live.
  Ulterior: proba live FAIL, candidat scos din runtime; v34 restaurat.
  Mostra 108 rămâne nerezolvată; nu se declară întreaga scară reparată.
  Detalii: `adr/2026-09-06-shared-corner-inset-candidate.md`.
  Diagnostic după respingere: 80/80 cadre reproduse exact în fiecare probă,
  controlul din sursa pre-candidat reproduce traseul v34. Schimbarea afectează
  și apropierea de scară: `adr/2026-09-06-first-stall-replay.md`.
  Lanț cauzal offline izolat: punct inset 7 mutat cu 0,391215 yd → sonda joasă
  acceptă altă scurtătură din start → apropiere schimbată. JSON-urile workerilor
  instrumentați coincid integral cu originalele. Detalii:
  `adr/2026-09-06-inset-shortcut-causal-trace.md`.
  Audit generic al followerului adăugat: 600 sosiri, 403 depășiri de marjă;
  verdict separat FAIL. 297 teste relevante PASS, fără corecție runtime.
  Integrarea cu traseul netezit/inset–simplificare rămâne de verificat:
  `adr/2026-09-06-generic-tracking-clearance-audit.md`.
- [ ] Reproducerea separată a mesei/sub scara ME503 și repetabilitate.
- [x] Nucleu offline pentru context spațial cu vârstă, incertitudine și origine
  explicită a distanțelor; fără memory reading sau autoritate de execuție.
- [ ] Legarea contextului spațial de dovezi reale în replay, apoi afișare CC
  read-only; nu inventăm etaj/Z/eroare metrică. Detalii:
  `adr/2026-09-06-observed-spatial-context.md`.
  Progres: adaptorul formatului existent verificat pe 626 decizii reale,
  620 asocieri geometrice. Poziția completă și afișarea CC rămân neîncheiate.
  97 teste relevante PASS: `adr/2026-09-06-spatial-trace-adapter.md`.
- [ ] Profilarea pornirii lente și reînnoirii autorizării, fiecare separat.

Jurnalul este validat live: 626/626 decizii și 166/166 actualizări geometrice.
ARRIVED în 33,571 s nu certifică distanța de zid sau humanlike. Urmează replay-ul
ferestrelor +6,3–7,8 s; raport: `LIVE_CRYPT_DIAGNOSTIC_2026-09-06.md`.
Replay geometric realizat; detalii: `adr/2026-09-06-egress-geometry-replay.md`.
Control Center rămâne în fluxul operatorului. Nu schimbăm camera jocului,
navmesh-ul, pragurile sau modul de combat pentru a obține un rezultat verde.
Detalii: `adr/2026-09-06-movement-decision-evidence.md`.
