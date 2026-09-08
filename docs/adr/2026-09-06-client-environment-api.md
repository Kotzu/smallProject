# Mediu interior/exterior observat prin API, separat de etaj

## Decizie

Addon 0.5.10 extinde numai pachetul de localizare la wire v2. Cei doi bytes
anterior rezervați transportă tipul exact returnat de IsIndoors/IsOutdoors
și disponibilitatea ca funcție Lua a UnitPosition/GetPlayerFacing. Dimensiunea
144 bytes, cele 96 celule RGB, CRC, etichetele și ritmul existent sunt păstrate.
Coordonatele, combatul și canalul AFK nu sunt modificate. Decoderul acceptă
atât v1, cât și v2; câmpurile rezervate nepermise sunt respinse.

API absent, nil, false, true, 0, 1, eroare și valoare neacceptată sunt stări
distincte. Apelurile interior/exterior sunt protejate cu pcall. Celelalte două
funcții sunt numai verificate ca disponibilitate, nu apelate pentru coordonate.
Observația moștenește legarea la client/sesiune și prospețimea pachetului de
localizare. Nu confirmă etajul, nu selectează o suprafață navmesh și nu dă input.

API-ul de mediu nu este un senzor de plafon. Un rezultat exterior nu înseamnă
spațiu vertical infinit; un segment fără coliziune rămâne doar segmentul testat.
Altitudinea estimată, suprafețele candidate, etajul și plafonul rămân separate.
CC afișează valorile API brute în harta principală și în tabul Sonar, numai
după filtrele existente de identitate/prospețime.

## Dovezi

477 teste Python relevante PASS înaintea instalării: transport v1/v2, toate
cele 64 combinații ale tipurilor returnate, CRC/RGB la scări diferite,
expirare, schimbare de sesiune, compatibilitate și protecțiile installerului,
coordonate, AFK, movement engine, sonar details și height scan. Nu este întreaga
suită și nu este probă de navigație.

Installerul a verificat și înlocuit cele trei fișiere ale addonului, păstrând
backup exact 0.5.9 în data/runtime/addon-backups/
PerfectAssassinObserver-20260906T212037809. CC relansat o singură dată.
În clientul LAB deja autentificat s-a executat numai /console reloadui.
Clientul a rămas inworld, fără dialog de eroare observat. Recepția reală v2
confirmă execuția noii căi Lua, nu doar existența unor nume în executabil.

Proba staționară exterior Deathknell a returnat IsIndoors=NIL, IsOutdoors=ONE,
UnitPosition_available=false și GetPlayerFacing_available=false. Acestea sunt
fapte despre sesiunea/clientul testat, nu despre orice versiune WoW. XY a rămas
1809,584262 /1592,794266. Sonarul a revenit fără eroare cu 64 raze, etaj null,
altitudine estimată 98,875381 yd și NO_HIT_IN_TESTED_SEGMENT pentru plafon,
cu infinite_clearance=false. Noile etichete au fost verificate vizual în
ambele taburi CC; motorul era Oprit. Guardul AFK existent raporta RUNNING;
nu a fost forțat un episod AFK nou pentru această probă.

## Limite, continuare și rollback

Nu avem încă tranziție live interior/exterior sau dovadă independentă a
suprafeței pe care stă actorul. Nil nu este redenumit eroare sau API absent.
Următorul pas: verificarea posibilității de a asocia semantica geometriei
clientului cu această observație; dacă nu diferențiază nivelurile, păstrăm
alternativele și căutăm o observație vizuală calibrată. Fără scoruri inventate.

v34 și plannerul/controllerul sunt neschimbate. În caz de regresie a addonului,
installerul curent cu -RestoreLatestVerifiedPrevious restaurează exact 0.5.9
din backup verificat; pentru client deschis cere și -AcknowledgeLiveHotReload.
Restaurarea fișierelor necesită apoi reload UI, în aceeași limită LAB autorizată.
CC curent acceptă deja v1, deci rollback addon nu cere simultan rollback CC.
Pentru revenirea întregii extensii: restaurează addonul înainte de revenirea
codului la fcfd45f și repornește CC. Nu comite backupuri sau telemetrie brută.
