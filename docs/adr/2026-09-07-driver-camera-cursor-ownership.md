# Driver manual: poziționarea cursorului înainte de RMB

## Defect și limitele dovezii

Proba precedentă a raportat `WoW lost focus during the drive step`.
Codul aducea HWND-ul WoW în prim-plan, dar apăsa RMB la poziția globală
existentă a cursorului, fără pregătire sau verificarea ferestrei de sub el.
Captura CC arăta cursorul lângă bifa de control; fereastra WoW nu acoperea
acel punct. Aceasta este o cauză plauzibilă a erorii observate, nu o urmă
instrumentată care identifică sigur fereastra ce a primit apăsarea.

## Corecție punctuală

Numai driverul manual reutilizează `prepare_world_drag_cursor` din backendul
existent. Acesta pregătește punctul interior din profilul vizual existent
și verifică poziționarea exactă; nu se introduce o nouă metodă de input.
Înainte de apăsare se reverifică armarea, ținta și faptul că fereastra
din prim-plan și cea de sub cursor sunt exact HWND-ul WoW autorizat.
O fereastră suprapusă sau o schimbare de autorizare refuză inputul.

Cursorul este restaurat după eliberarea RMB, inclusiv când proba eșuează.
Pierderea focusului în timpul probei rămâne motiv de oprire; nu se dezactivează
protecția și nu există retry automat. Punctul din profil nu dovedește că
orice configurație de addon/UI este liberă de controale; inspecția vizuală
înainte de test rămâne necesară. Mișcarea v34, CC, sonarul și anti-AFK nu
au fost modificate.

## Verificare

32 teste PASS: driver manual, mouse-turn sink și continuous motion.
Testele noi execută comportamentul cu backend fals: ordine place/check/RMB,
refuz pentru cursor acoperit, eșec de plasare, schimbare de autorizare,
eliberare/restaurare la pierderea focusului și la eroare de eliberare,
fără repoziționare pentru pas numai cu tastatură. Nu sunt probe live.

Proba live din 2026-09-07 nu a început: captura exactă a clientului arată
`Disconnected from server`; raportul CC arată `PAUSED_VISIBLE_STATE`.
Armarea a rămas dezactivată. Nicio comandă de cameră/deplasare trimisă în
această etapă. Nu se revendică remediere live sau calibrare/Z confirmate.

## Continuare și rollback

După revenirea Predator în lume: încarcă versiunea nouă a driverului
(conectorul deja pornit poate păstra modulul vechi), armează din CC,
maximum 60 secunde, două ajustări verticale mici în sensuri opuse,
fără taste de deplasare; verifică imaginile și XY, eliberează și dezarmează.
Nu este nevoie de repornirea WoW sau CC pentru încărcarea driverului nou.
Geometria și corespondențele pixel/vertex necesită în continuare validare.

Rollback: restaurează numai schimbarea driverului din acest ADR la versiunea
anterioară din Git, păstrând v34 și celelalte module. Versiunea anterioară
are defectul de cursor descris; nu relua RMB cu cursorul în afara WoW.

## Revenire în lume și probă controlată, 2026-09-07

Operatorul a reconectat Predator. CC a reluat datele pentru sesiunea nouă.
Driverul din workspace a fost încărcat într-un proces proaspăt; conectorul
MCP persistent nu a fost repornit și poate păstra codul vechi.

Prima probă, driver SHA256 `187f90a7b95076275d7799ac4c90a5782e27ff40dc14695c2a3910d7fe0dfc91`:
două comenzi fără taste, dy +60/-60, câte 150 ms. Ambele EXECUTED, fără
pierderea focusului, dar rotirea vizuală a fost excesivă, cu schimbarea
orientării estimate pe minimapă. **Respinsă pentru calibrare**. XY a rămas
identic în instantaneele înainte/după. Armare temporară aproximativ 43 s.

Cauza suspectată a fost izolată prin comparare cu transportul existent:
`windows_mouse_turn.py` documentează deja că restaurarea imediată a cursorului
după RMB-up poate fi consumată drept ultimul drag mare. Driverul manual
omise această așteptare. Reutilizăm acum constantele existente: 20 ms după
RMB-down, 50 ms după RMB-up. Dacă RMB-up eșuează, cursorul nu este restaurat
cât timp butonul poate fi încă apăsat. Nu modificăm transportul v34.

33 teste PASS, inclusiv ordinea exactă a pauzelor și refuzul restaurării la
eroare de eliberare. Nou SHA256 driver:
`51dd72ac6d50ad5d97f935a731644db0ccc18c0fa25f3771f13736c64e65ce40`.

A doua probă a trimis dy +8/+16, apoi +240 pentru a readuce vederea dinspre
cer spre teren. Fiecare comandă: 150 ms, fără taste, EXECUTED. Cadrele mici
arată ajustări mici fără saltul anterior; orientarea estimată afișată în CC
a rămas 187.8 grade, XY identic în toate cele 16 instantanee ale celor două
probe. Aceasta nu este măsurare exactă a orientării corpului sau calibrare
metrică a pitch-ului. Ultima vedere este spre sol, mai apropiată de actor;
încadrarea/orientarea inițială nu au fost restaurate exact.

Toate comenzile celei de-a doua probe au fost în primele aproximativ 47 s.
Dezarmarea UI a fost confirmată la aproximativ 61.6 s de la armare: depășire
de aproximativ 1.6 s a ferestrei planificate, fără comenzi suplimentare.
Pentru următoarea probă rezervăm minimum 15 s pentru eliberare/dezarmare.
Controlul final este dezactivat, motorul de mers nu a fost pornit.

Dovezi ignorate în Git: `data/runtime/camera-focus-live-20260907-v1/`.
Două MP4 de 40 s, capturi PNG și rezultate JSON cu hash-ul driverului și
instantanee de poziție. Filmul al doilea acoperă pașii +8/+16, nu ultima
corecție +240; pentru aceasta există captura și rezultatul comenzii.
Nu numim proba întreagă filmată integral. Foi de cadre inspectate pentru
filmul al doilea, capturi inspectate după fiecare comandă.

Acceptare limitată: pregătirea cursorului și așteptarea după eliberare au
o probă live fără saltul anterior la pașii mici. Repetabilitatea, izolarea
camerei de corp și calibrarea geometrică/Z rămân nevalidate. Sonarul,
plannerul, controllerul v34 și anti-AFK au rămas neatinse.
