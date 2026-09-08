# Validarea segmentelor pentru ocolirea obstacolelor confirmate

## Defect demonstrat offline

Corecția `616c193` verifica distanța colțurilor ocolirii, nu distanța minimă
pe segmente. Fixture-ul cu raza obstacolului de 1 yd accepta ocolirea la
1,75 yd, deși raza plus marja corpului cer 2,25 yd. Testul vechi a fost
păstrat cu aceleași date și transformat într-o cerință de respingere.

## Decizie limitată

- Fiecare segment al ghidajului rezolvat de navmesh trebuie să păstreze raza
  obstacolului plus `DEFAULT_ACTOR_CLEARANCE_WORLD`. Sunt incluse extremitățile
  proiectate, nu numai punctele cerute inițial.
- Candidatul conservator este cel puțin raza obstacolului plus marja corpului;
  altfel, o verificare corectă ar respinge și toate variantele propuse pentru
  obstacole mai mari. Marja corpului nu a fost schimbată.
- Colțurile rămân un filtru preliminar; variantele mai înguste pot fi acceptate
  numai dacă traseul efectiv curbat păstrează distanța pe fiecare segment.
- Aceeași verificare se aplică traseului alternativ global și continuării
  reutilizate din cache. O continuare nesigură nu este memorată. Dacă nu există
  ocolire validă, rezultatul rămâne `CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED`,
  tratat de verificarea existentă înaintea execuției.
- Nu schimbăm camera, controlerul, armarea, datele navmesh sau configurația UI.

## Dovezi și limite

Înainte de corecție, trei teste noi au eșuat pe apropierea segmentului,
curbarea către obstacol și proiecția mică nesigură. După corecție trec.
Sunt verificate și arcul sigur, rotația/translația, limita exactă și respingerea
traseelor nesigure din cache sau din alternativa globală.

Aceasta este o verificare geometrică orizontală față de obstacolul memorat,
nu o simulare completă 3D a corpului, nici o garanție despre trasee recalculate
ulterior sau executarea fizică a mișcării. Poate respinge conservator un pasaj
suprapus vertical; nu adăugăm aici excepții de etaj fără dovezi. Nu dovedește
că întreaga problemă ME503 este rezolvată live. Versiunea nu este promovată Stable.

Referința anterioară este `84da1c9`. Revenirea trebuie făcută separat, fără
probă activă; nicio instanță Control Center nu a fost relansată în acest pas.
