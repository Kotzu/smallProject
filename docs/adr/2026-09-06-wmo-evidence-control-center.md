# Dovezi WMO în Control Center, fără confirmare artificială de etaj

## Implementare

Tabul Sonar afișează înaintea sondelor maximum 32 de rânduri de asociere:
altitudinea candidatului, instanța, numărul potrivirilor și primele două
identități grup/triunghi. Limita afișării este explicită; nu șterge alternativele
din observație. Acoperirea parțială și instanțele cu modele lipsă sunt explicite.
Nicio instanță WMO în coloană nu înseamnă lipsa tuturor obstacolelor.

Prezentarea verifică legătura cu harta, pack-ul, coloana originală și setul
candidaților sonar. Respinge valori infinite, etaje declarate, potriviri
numeric incompatibile, alternative eliminate și schimbarea suprafeței selectate.
Există un buget de 8192 potriviri procesate/raport pentru prezentare. Un raport
opțional invalid nu ascunde sonarul de bază. Excepțiile brute nu apar în UI.
Filtrul existent de sesiune/poziție/timp precedă această prezentare.

CC și bridge acceptă `--spatial-sonar-wmo-config`. Fără opțiune, integrarea WMO
rămâne dezactivată. Configurația este citită limitat la 16 KiB, numai în workerul
de fundal; căile relative din ea sunt raportate la rădăcina proiectului.
`config/navigation/sonar-wmo-azeroth-v1.json` fixează indexul, bundle-ul și hash-ul
verificat în ADR-ul bundle-ului. Nu există coordonate sau comportament special
pentru criptă în prezentare sau în configurarea observerului.

## Verificare

- 176 teste relevante PASS, inclusiv CC/autonomie, prospețime, sonar și WMO.
- Lint pentru modulele de prezentare/observer și testele modificate PASS;
  diff verificat. Fișierele mari CC/bridge păstrează stilul existent.
- Integrare offline reală: configurație -> pack/index/bundle -> worker ->
  `sonar_details`. Cripta produce două rânduri, 121.670 și 138.452 yd:
  primul corespunde grupului1490/triunghiului4901, al doilea fără potrivire
  WMO rămâne candidat. Nu dovedește poziția actorului în criptă.
- CC anterior închis normal în starea Oprit; redeschis cu opțiunea de mai sus.
  Proces CC 39332 (wrapper5248), sesiunea WoW10756 neschimbată.
- Verificare vizuală staționară LAB: tab Sonar și hartă, inclusiv redimensionare
  de la lățimea 1500 la 1300 pixeli logici. Limitele WMO sunt lizibile, harta
  păstrează poziția actuală și aplicația rămâne în Oprit.
- 12 mostre live la interval de o secundă: 12 LIVE, 12 bundle-uri cu hash-ul
  așteptat, 11 secvențe distincte, fără erori sonar/WMO. Vârsta poziției
  1.114–2.116 s; un singur XY. În această coloană exterioară: zero instanțe WMO,
  plafon nedetectat în segment, fără înălțime infinită, etaj neconfirmat.
- Anti-AFK existent rămâne RUNNING. Nicio pornire de mers, nicio schimbare v34.

## Limite și revenire

Aceasta este validare live staționară, nu probă filmată de navigație sau dovadă
de etaj corect. Nu extinde acoperirea la alte modele; terenul/doodad-urile
rămân în afara acestei asocieri. Orientarea camerei și eroarea metrică nu sunt
rezolvate de potrivirea geometriei statice.

Revenire: pornește CC fără `--spatial-sonar-wmo-config`; sonarul de bază rămâne.
Opțiunea este activă în sesiunea CC verificată, nu implicit în toate lansările.
Reperul anterior acestei integrări: `bc73196`. Nu șterge bundle-ul original.

Urmează dovezi independente pentru diferențierea nivelurilor suprapuse și
asocierea temporală a poziției actorului cu suprafața, înainte de folosirea
acestei geometrii în decizii de mers. Nu este suficientă potrivirea numerică.
