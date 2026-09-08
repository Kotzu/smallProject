# Enumerarea nivelurilor: defect condițional, nu cauză live demonstrată

## Motiv

Înainte de alegerea nivelului verificăm dacă lista de alternative ascunde
suprafețe. Nici două valori native, nici succesul traseului nu dovedesc că
personajul se află pe una anume. API-urile UnitPosition/GetPlayerFacing sunt
indisponibile în sesiunea TBC deja verificată; flagurile de mediu nu dau Z.

## Constatare de sursă și reproducere compilată

Dependența NAMIGATOR, revizia `54eae6957753c3ca47b73402df9f8d1d52a2721e`,
`pathfind/Map.cpp`, metoda `Map::FindHeights`, compară Z după pasul de coborâre
cu `getMaximum().Z` în ramura `next == current`. Comentariul spune că trebuie
evitată coborârea sub limita tile-ului; limita folosită este însă cea de sus.

Auditul C++ izolat păstrează corpul metodei identic cu sursa locală, dar
folosește un furnizor determinist de intersecții. La limite 0–20, suprafețe
12 și 4, teren 18:

- fără repetarea intersecției: `[12, 4, 18]`;
- dacă intersecția repetă exact Z curent: `[12, 18]`, suprafața 4 omisă.

Este o demonstrație a ramurii condiționale, NU o reproducere de coliziune
reală sau de mers. `utility/Ray.cpp` respinge distanțe `d < 1e-5`; de aceea
nu presupunem că furnizorul real repetă întotdeauna intersecția. Transformările
și rotunjirea float trebuie investigate separat dacă apare o omisiune reală.

`tools/audit_height_enumeration.py` verifică egalitatea corpului copiat cu
sursa instalată înainte de rularea executabilului și raportează hash-uri.
Map.cpp SHA256:
`93f9658ab301e06ece56e1c6384a30dec6c1f119da6022c4e54b843156fe3904`.
Executabil audit SHA256:
`44a67eb7fd8c7d9683c38e27193249e3d0e85030f9d28c5508241bd29f02f06a`.

## Comparație pe geometria reală

Observer separat, fără CC/input: pack/index/bundle reale reverificate prin
încărcătoarele existente, workerul sonar curent, aceeași coloană float publicată
de worker. Grilă 7×7: XY 1676.369629/1677.466919 ±6 yd, pas 2 yd.

Toate cele 49 de interogări au reușit. Triunghiurile WMO cu normală verticală
world >0.5 au fost comparate cu candidații nativi, toleranță numerică 0.001 yd.
**Zero coloane cu astfel de suprafețe fără corespondent în lista nativă.**
Nu certifică mersul pe triunghiuri, întregul model, alte WMO-uri, obiectele
mici, exhaustivitatea sau nivelul actorului. Nu demonstrează că defectul
condițional este imposibil în alte scene.

## Decizie și continuare

Nu modificăm dependența, workerul sau selecția etajului pe baza unei cauze
nedemonstrate în scena actuală. Lista rămâne explicit neexhaustivă. Păstrăm
reproducerea ca test diagnostic înaintea unei eventuale corecții izolate.
Nicio modificare în CC activ, v34, addon, camera clientului sau anti-AFK.

Următorul pas al localizării este evaluarea unei observații vizuale calibrate
sau a continuității de traversare cu ancoră verticală justificată. Nu pornim
continuitatea dintr-un Z ales arbitrar și nu o numim confirmare independentă.
Flagurile API interior/exterior se pot compara ca dovezi parțiale; nu aleg
singure un nivel atunci când geometria/semantica nu diferențiază alternativele.

Verificări: 1 test C++ PASS; paritate cu sursa locală PASS; 37 teste Python
PASS (audit, candidați verticali, asociere), lint și diff-check PASS.
Nu este probă live și nu închide etapa de localizare verticală.
