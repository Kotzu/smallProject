# Perfect Assassin Observer — TBC 2.4.3

0.5.10: pachet de localizare v2, aceeași dimensiune și aceiași senzori.
Publică rezultatele brute IsIndoors/IsOutdoors (absent, nil, false/true, 0/1,
eroare sau tip neacceptat) și disponibilitatea UnitPosition/GetPlayerFacing.
Nu presupune semnificația lui nil și nu confirmă etajul din aceste valori.
Consumatorul acceptă în continuare pachetul v1, fără aceste informații.

0.5.9: regiune/subzonă din GetZoneText/GetSubZoneText, într-un pachet separat
cu CRC și timp client. Maximum 64 octeți UTF-8 per nume; depășirea este
indisponibilă, nu nume trunchiat. Două rânduri RGB nu mută senzorii existenți.
CRC-ul este integritate de transport, nu autentificare sau precizie XYZ.

0.5.8: bandă AFK separată, CRC, fără schimbarea protocoalelor poziție/combat.
Publică starea AFK, personajul Predator și blocarea inputului în chat/dialog/combat.
Nu apasă taste. Guard-ul extern LAB poate emite un singur Space per episod AFK.

Addon observer pentru `Interface 20400`. Observația rămâne read-only și scrie exclusiv în `PerfectAssassinObserverDB`, prin mecanismul normal `SavedVariables` al clientului. Singura mutație opțională este profilul local de UI/bindings declanșat explicit de operator prin `/paobars apply`; acesta are backup și rollback prin `/paobars restore`.

## Boundary

- nu apasă taste și nu apelează acțiuni protejate;
- nu trimite chat sau addon messages;
- nu citește memoria procesului și nu folosește DLL-uri;
- nu interoghează serverul, baza CMaNGOS ori playerbots;
- păstrează maximum 5.000 de evenimente;
- arhivează combat log-ul legacy brut; acesta nu devine automat knowledge pentru Brain.

PA-020 adaugă observații read-only pentru dialogul/questurile NPC-ului, textul și obiectivul questului, quest log și spellbook. Apariția unui quest în log este dovada disponibilă clientului; addon-ul nu pretinde un quest ID pe care API-ul legacy nu îl expune și nu acceptă questuri.

PA-024B3 adaugă exclusiv coordonata normalizată și facing-ul propriului caracter, dacă API-urile publice legacy le expun. Senzorul vizibil include un payload de 112 biți cu CRC-16/CCITT-FALSE, pentru captură de ecran robustă. Facing-ul elimină estimarea sacadată din deplasare și rămâne o observație a propriului caracter, nu memory reading. Nu exportă pozițiile altor jucători, coordonate server-side sau informații ascunse. Dacă harta este deschisă, contextul lipsește ori CRC-ul nu validează, consumatorul trebuie să declare poziția `LOST` și să oprească navigarea.

În `0.3.6`, HUD-ul pornește sub frame-urile standard de player/target. Ține `Ctrl`
și trage cu butonul stâng de bara de titlu pentru a-l muta. Fără `Ctrl`, panoul
rămâne click-through. Poziția este păstrată de mecanismul nativ `layout-cache`
al clientului și este limitată la zona în care detectorul vizual o poate citi.
Comanda locală `/paohud reset` restaurează poziția implicită.

În `0.3.7`, textul de diagnostic este mutat în afara clientului, iar senzorul
din joc este redus la o bandă compactă `170x76`. Grila de poziție rămâne
byte-identică; o a doua grilă cu CRC publică numai starea legitim vizibilă a
propriului Rogue, țintei curente și sloturilor exacte `Attack`, `Sinister
Strike` și `Eviscerate`. Addonul nu selectează ținte și nu execută abilități.
Consumatorul extern poate desena o consolă lizibilă și poate produce ulterior
un clean feed pentru video, fără ca acea consolă să intre în client.

În `0.4.0`, protocolul compact de combat publică și HP-ul absolut al țintei,
precum și attack power-ul Rogue-ului, pentru estimarea client-side a TTK și a
overkill-ului. Snapshot-ul spellbook continuă să parcurgă toate taburile, iar
registrul de action bars descrie toate cele 72 de sloturi ale celor șase pagini.
Snapshot-ul `focus` este separat de `target`, inclusiv pentru castul observabil,
astfel încât un healer ținut în focus să nu înlocuiască adversarul principal.

Protocolul compact de combat `v6` păstrează identitatea stabilă CRC-16 a țintei,
nivelul, reacția, tipul player/NPC, HP-ul absolut, bearing-ul vizual discret și
secvența monotonă a ferestrei de loot. Codul de bearing `7` înseamnă că ținta
este probabil în spate sau camera este prea joasă, nu o direcție inventată.
Pentru o țintă moartă, addonul poate păstra temporar punctul de interacțiune al
nameplate-ului asociat aceluiași CRC. Consumatorul extern trebuie să confirme
CRC-ul, starea `dead` și incrementarea secvenței de loot; niciun pixel sau click
singur nu constituie dovadă de loot.

În `0.5.0`, cei trei octeți care erau neutilizați când nu există target publică
numărul nameplate-urilor atacabile vizibile și coordonata 2D a candidatului ales.
Această awareness este limitată strict la entitățile pe care clientul le-a primit
și le afișează deja; nu pretinde ESP dincolo de visibility range. După selectare,
geometria continuă să fie acceptată numai împreună cu identitatea CRC a țintei.
Toolul extern poate astfel desena legătura Predator–mob și cere un coridor local
navmesh înainte de a autoriza apropierea, fără să adauge elemente pe clean feed.

`0.5.1` identifică health bar-ul nameplate-ului după tipul semantic `StatusBar`,
nu după poziția fragilă în lista de children. Astfel, layouturile legacy care
inserează alte frame-uri înaintea barei nu mai fac mobii vizibili să dispară
din awareness.

`0.5.2` leagă bearing-ul și selecția mouse-ului de centrul barei de viață
vizibile, nu de centrul ramei invizibile a nameplate-ului. Astfel, selecția
pre-combat apasă exact elementul afișat, iar motorul extern poate aștepta
confirmarea targetului fără clickuri repetate.

`0.5.3` convertește coordonatele nameplate-ului din scala efectivă a
`WorldFrame` în scala rădăcinii UI înainte de normalizare. Conversia elimină
eroarea produsă de UI Scale în clientul windowed și păstrează punctul extern de
click pe aceeași bară vizibilă indiferent de rezoluție sau profilul UI.

`0.5.4` urmărește nameplate-urile printr-un registru semantic persistent,
compatibil cu replacement addons legacy, și identifică unitatea selectată după
alpha ramei native părinte. În TBC bara `StatusBar` rămâne de regulă opacă și la
non-target; folosirea ei putea lega săgeata de alt mob cu același nume. Registrul
reduce și scanarea repetată a tuturor copiilor `WorldFrame` la fiecare cadru.

`0.5.5` include în același pachet protejat de CRC coordonatele X/Y cuantizate
ale frame-ului semantic selectat. Procesul extern folosește direct această
geometrie pentru servo-ul de facing; contururile colorate rămân doar martor
secundar și nu mai pot muta bearing-ul pe un alt nameplate sau obiect.

`0.5.6` unifică pragul `LEFT/CENTER/RIGHT` al addonului cu toleranța canonică
de `0.12` a Combat Engine. Direcția discretă și coordonata exactă din același
pachet CRC nu se mai pot contrazice în apropierea centrului ecranului.

`0.5.7` adaugă snapshot-uri read-only pentru unitatea `mouseover`: GUID/name,
tip player/NPC, HP și reacție, cu proveniență `client_observed`. Acesta este un
martor de identitate și stare pentru un singur obiect indicat de cursor, nu o
poziție 3D; câmpurile de coordonată și distanță rămân intenționat absente.

Comanda `/paobars apply`, folosită numai în afara luptei, face A/D strafe,
activează cele patru bare suplimentare, păstrează `Tab`/`Shift-Tab` pentru
ciclarea inamicilor, leagă `F`/`Shift-F` la focus/target-focus și oferă 24 de
sloturi directe pe `1..=` și `Shift-1..Shift-=`. Configurația existentă este
salvată înaintea primei aplicări și poate fi restaurată exact cu
`/paobars restore`. `/paobars snapshot` doar înregistrează configurația curentă.
Nicio comandă nu selectează ori atacă automat o unitate și nicio schimbare de
binding nu este acceptată în combat.

`0.4.5` aplică separat starea salvată pentru următoarea încărcare și variabilele
FrameXML care controlează barele în sesiunea curentă; succesul este raportat
numai după ce toate cele patru frame-uri sunt realmente vizibile.
Profilul recunoaște numai aranjamentul exact Eviscerate/Sinister Strike din
sloturile 2/3 sau layout-ul inițial gol/Sinister Strike din 2/3. În al doilea
caz, mută Sinister Strike și așază Eviscerate din spellbook, apoi reține layoutul
pentru restaurare.
Orice alt conținut al sloturilor este refuzat.
Profilul păstrează `Y` pe bindingul TBC `TURNORACTION` pentru compatibilitatea
layoutului și îl include în restaurarea exactă. Executorul extern de facing nu
apasă însă `Y`: aplică un drag RMB direct, scurt și limitat, cu punct de pornire
sigur în world view, apoi cere un frame nou de bearing înaintea oricărui strafe
sau atac.

`0.4.6` mărește rata senzorului compact de la 5 Hz la 20 Hz pentru Movement
Engine. Schimbarea nu adaugă informații noi și nu execută input; oferă doar
observații vizuale mai dese controlerului extern. Facing-ul magnetic folosește
corecții RMB mici și reobservă ținta după fiecare tick. Movement Lab poate
desena extern cercul și săgețile de facing/target/waypoint, iar overlay-ul poate
fi oprit complet pentru capturile video curate.

`0.4.7` calibrează separat geometria verticală a targetului: un mob mic aflat
în framing normal de melee rămâne LEFT/CENTER/RIGHT, iar starea BELOW este
rezervată geometriei puternice de underfoot/behind-camera. Astfel, servo-ul de
facing nu abandonează inutil axa orizontală în combat apropiat.

`0.4.9` ridică HUD-ul de coordonate la protocolul `v3` și adaugă două flaguri
CRC-bound pentru starea propriului personaj: dead-or-ghost și ghost. Datele vin
exclusiv din API-urile publice TBC `UnitIsDeadOrGhost("player")` și
`UnitIsGhost("player")`. Addonul nu eliberează spiritul, nu recuperează corpul,
nu execută input și nu primește informații de la emulator; controllerul extern
poate astfel separa portabil moartea de corpse-run fără integrare MaNGOS.
