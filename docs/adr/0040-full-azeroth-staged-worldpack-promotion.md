# ADR 0040: Promovarea etapizată a WorldPack-ului full-Azeroth

## Status

Accepted.

## Context

WorldPack-ul activ TBC 2.4.3.8606 acoperă 24 de tile-uri din
Tirisfal–Silverpine și păstrează regresiile de interior și drum validate. El nu
reprezintă continentul Azeroth. Inventarul pin-uit al clientului enumeră 687
ADT-uri pentru `map_id=0`, iar pipeline-ul generic poate extrage și construi
acest set fără date de server sau emulator.

Înlocuirea directă a profilului stabil cu rezultatul unui bake mare ar putea
ascunde o regresie în criptă, semanticile drumurilor sau structurile statice.
Mărimea pachetului nu este dovadă de corectitudine.

## Decizie

Full-Azeroth este construit într-un root staging separat:

1. extragerea cere exact cele 687 ADT-uri și WDT-ul declarate de inventar;
2. semanticile de drum cer exact 687 artefacte `.road`;
3. navmesh-ul cere exact 687 tile-uri `.nav` și `Azeroth.map`;
4. orice catalog cu terrain coverage `complete` cere inventarul clientului și
   coada de bake recalculată din fișiere; numărul sau existența parțială a
   tile-urilor nu constituie dovadă;
5. catalogul candidat declară terrain și road coverage `complete`, dar păstrează
   interior coverage `partial` până la indexare și scanarea WMO;
6. WorldPack-ul este sigilat într-o destinație nouă și verificat prin hash;
7. toate regresiile WorldPack-ului stabil sunt repetate direct din candidatul
   sigilat înainte ca vreun default runtime să fie schimbat;
8. indexul static, planul generic și scanarea resumabilă sunt regenerate pentru
   noul hash. Graful vechi nu poate fi reutilizat între pachete.

Logul MapBuilder este convertit într-un
`navmesh_bake_quality_report`. Raportul separă progresul, eșecurile terminale,
setul exact de coordonate și diagnosticele Recast care nu opresc serializarea.
Chiar și un build cu return code zero păstrează
`geometric_validation_required=true`; existența celor 687 fișiere nu înlocuiește
regresiile de rută și scanarea structurală. Sigilatorul refuză un catalog cu
terrain coverage `complete` dacă raportul final lipsește ori nu corespunde
hărții și numărului exact de tile-uri. Raportul acceptat este inclus în
WorldPack cu rolul `NAVMESH_BAKE_QUALITY`, astfel încât manifestul și hash-ul
agregat îl păstrează împreună cu geometria validată.

În plus, fiecare artefact `.nav` din catalog este verificat înainte de
promovare prin parserul structural Namigator/Detour v7: fluxul zlib este limitat
și trebuie să fie unic, headerul ADT, coordonatele și grila exactă de 256 tile-uri
sunt validate, iar fiecare tile Detour intern este verificat pentru secțiuni,
poligoane, muchii, detalii și indici. Namigator este pin-uit cu
`DT_POLYREF64`; zona de link-uri neinițializată este obligatoriu zero înainte de
normalizarea strictă pentru verificatorul portabil. Un
`navmesh_geometry_validation_report` cu status `PASS`, hash-ul catalogului și
hash-ul setului de artefacte este obligatoriu pentru fiecare hartă completă.
Raportul este inclus cu rolul
`NAVMESH_GEOMETRY_VALIDATION` și este verificat din nou când WorldPack-ul este
redeschis; un manifest recalculat peste un raport modificat este respins.

Dacă un tile din catalogul final diferă de bytes-ii acelui raport brut, el nu
poate fi promovat printr-o copiere implicită. ADR 0041 cere dovada portabilă a
defectului, WorldPack-ul sursă și regresia FAIL→PASS, incluse în același
manifest final.

Buildul rulează pe `MapBuilder` pin-uit, cu maximum opt fire, în afara clientului
WoW. Artefactele clientului sunt import offline; WorldPack-ul final nu depinde de
client, server sau emulator la runtime.

## Dovezi curente

- inventar client: 83 map ID-uri, 35 hărți cu ADT și 3.610 ADT-uri total;
- Azeroth: 687/687 ADT-uri extrase;
- Azeroth: 687/687 semantici de drum generate;
- navmesh full-Azeroth: 687/687 ADT-uri și 175.872 tile-uri interne construite
  în staging, cu return code 0;
- raportul de bake este `COMPLETE_WITH_RECAST_DIAGNOSTICS`: nu există tile-uri
  eșuate ori coordonate lipsă/extra, iar diagnosticele Recast rămân păstrate ca
  dovadă și nu sunt confundate cu o validare geometrică;
- auditul structural Namigator/Detour complet rămâne poarta obligatorie înainte
  de sigilare;
- profilul candidat este valid contractual și nu acordă execution authority;
- WorldPack-ul activ de 24 tile-uri rămâne neschimbat.

## Consecințe

- Shadowfang și Deathknell–Brill rămân benchmarkuri/regresii, nu specializări.
- Un bake terminat nu promovează automat runtime-ul.
- Aceeași succesiune poate fi aplicată separat pentru Kalimdor, Expansion01 și
  alte hărți sau builduri, cu adaptoare și identități proprii.
- Clientul modern 2.5.5+ nu poate consuma pachetul MPQ/WDBC 2.4.3.8606.
