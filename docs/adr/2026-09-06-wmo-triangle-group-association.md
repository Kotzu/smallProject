# Asocierea suprafețelor cu grupurile WMO, verificată offline

## Implementare

`adapter/wmo_surfaces.py` citește fișierele de grup WMO v17: antet MOGP de
68 bytes și subchunk-urile MOPY/MOVI/MOVT. Păstrează indexul grupului din root,
group ID din MOGP, flags brute, indexul original al triunghiului și hash-ul.
Bounds și biții interior/exterior sunt comparați cu root; alte flags MOGP
pot diferi legitim. Date lipsă/incoerente sunt erori, nu geometrie liberă.
Referință de layout: [MaNGOS WMO](https://www.getmangos.eu/wiki/referenceinfo/clientfiles/wmo-file-r20030/).

Parserul este delimitat la 32 MiB/grup, 65536 vertices, 200000 triunghiuri.
Mask-ul `NAMIGATOR_MOPY_RETAINED` reproduce filtrul efectiv din dependența
locală parser/Wmo/Wmo.cpp: exclude bitul 4 dacă materialul nu este 255.
Nu pretinde că această interpretare reproduce integral fizica clientului.
Array-urile decodate au buffer read-only; fără schimbări ale asseturilor.

Intersecția folosește un segment finit transformat în model, păstrează toate
hit-urile din ambele sensuri și normala geometrică în world. Nu clasifică
automat normală pozitivă=podea sau negativă=plafon și nu certifică mersul.
Triunghiurile de pe o muchie comună rămân două identități; nu se confundă cu
două etaje. Segmentele coplanare și triunghiurile degenerate nu sunt rezolvate.
Niciun hit nu înseamnă doar lipsa intersecției în acest subset/segment.
Doodad-urile și terenul ADT nu sunt incluse în acest instrument.

`tools/audit_wmo_surfaces.py` încarcă toate grupurile root-ului primit, maximum
un milion de triunghiuri păstrate, și produce raport fără input client/server.
Parametrii sunt generici: root, prefix grup, instanță, segment world. Nu conține
coordonate sau rute pentru criptă în algoritm.

## Legarea la geometria existentă

`adapter/wmo_bvh_audit.py` citește prefixul geometric BVH1 și root ID, după
layoutul local AABBTree::Serialize, și compară multiseturile exacte ale
triunghiurilor float32. Păstrează multiplicitatea și ordinea vârfurilor;
reordonarea triunghiurilor de către BVH nu contează. Calea modelului provine
din bvh.idx, trebuie să fie un nume de fișier local și să fie unică.

Este verificare geometrică, nu verificare a arborelui de accelerație, a întregului
WorldPack sau a legăturii dintre mediul API și actor. Raportul păstrează
world_pack_seal_verified=false și asset_instance_binding_verified=false.
Înainte de integrarea runtime trebuie folosit verificatorul existent de pack
și sigilate metadatele noi; un hash calculat nu este singur autorizare.

## Dovezi reale, staționare/offline

Cele cinci grupuri ale md_cryptonerm au fost extrase din fișierele clientului
cu extractorul existent, în directorul runtime al auditului anterior. Nu s-a
schimbat clientul, addonul, CC, procesul de navigație sau serverul.

| Grup | Group ID | Triunghiuri originale | Păstrate |
| --- | --- | --- | --- |
| 0 | 1484 | 1097 | 1073 |
| 1 | 1485 | 733 | 146 |
| 2 | 1488 | 883 | 50 |
| 3 | 1489 | 448 | 74 |
| 4 | 1490 | 4941 | 604 |

Total 1947 triunghiuri păstrate: toate coincid exact, cu multiplicitate, cu
modelul clădirii din WorldPack-ul existent. Root ID 712 coincide. Niciun
triunghi lipsă sau suplimentar. Digest comun al multisetului:
`57b6f0cbffad49fc397e90eb1f51219c4080d56558b7648f2e070a1f50964a0a`.
SHA256 BVH: `3b8200b9548675fcca156e24de7eecea25c67736c2b1396ac4beb512c01a2b57`.
SHA256 index BVH: `fa47c3ffb337b975053bbab2d9d6a6ab9b93e5aa1f8094be7a2b87fb3473fddc`.

La XY de referință 1676,369629 /1677,466919, segmentul Z160→100 intersectează
două triunghiuri ale grupului 4 (flags MOGP 10757):

- triunghi 1232: Z128,085877765, componenta Z a normalei −0,965925884;
- triunghi 4901: Z121,670340750, componenta Z a normalei +1.

Acestea sunt suprafețe geometrice distincte în aceeași cutie, nu două niveluri
confirmate ale actorului. Diferența verticală este circa 6,416 yd; nu este
clearance-ul corpului. Nu atribuim etichete fizice certe după winding singur.

Interogarea separată prin workerul sonar existent, nemodificat, returnează la
același XY candidatele native 121,670326 și 138,45195. Valoarea inferioară
coincide cu suprafața WMO la aproximativ 0,000015 yd în această probă; nu este
precizia localizării actorului. Valoarea superioară nu este un hit al grupurilor
WMO pe acest segment. Nu afirmăm din acest rezultat singur că este teren.
Z121,797379 și Z138,729095 din probele de traseu sunt alte valori: hint/poziție
rezolvată, nu trebuie redenumite înălțimi ale triunghiurilor.

## Teste și continuare

226 teste relevante PASS în 0,68 s (include 31 noi pentru suprafețe și audit
BVH). Testele verifică triunghi vs AABB, transformări cu rotație/înclinare/scală,
suprafețe suprapuse, winding invers, muchie comună, limite segment, degenerare,
date trunchiate, root/grup incompatibile, multiplicitate și path traversal.
Ruff trece. Acestea nu sunt teste de mers sau validare live a etajului.

Urmează asocierea generică a candidatelor native cu suprafețele WMO, cu grup,
proveniență și distanță de potrivire; candidații fără hit rămân neasociați.
Aceasta nu trebuie să elimine candidatul superior doar pentru că instrumentul
WMO nu include terenul. Apoi integrare read-only CC prin artefact sigilat și
verificare API/poziție, înaintea oricărei folosiri de planner/controller.
Rollback: revenirea acestui commit. v34 și artefactele active sunt intacte.
