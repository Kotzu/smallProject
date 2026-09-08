# Eliminarea unei interogări lente din bucla de mers

## Dovadă și cauză

Proba filmată instrumentată 5d3d9fca-aff5-4fd2-b1f2-8dbc0190f6c5,
pe 875ada5/v34: 249 cadre, 243 comenzi forward, zero recuperări, oprire
delimitată după 18 s de la prima publicare proaspătă. Actorul a ieșit;
humanlike nu este acceptat doar din acest rezultat.

Etapa dynamic_observation_and_memory a durat 228–308 ms în cadrele lente;
la cadrul 136: 307.80 ms din 548.95 ms post→post. Overlay 0.0175 ms,
steering 0.1386 ms în același cadru. Etapele sunt timp real, nu CPU exclusiv.
Motivul vechi PRECONTROL_POSE_REFRESHED care numește overlay-ul nu dovedește
cauza întârzierii.

Verificare separată read-only pe baza reală: 5.757 întâlniri, 28.758.016 bytes,
summary 219.18 ms. Planul folosește dynamic_encounters_world_time și un
TEMP B-TREE pentru GROUP BY; reaction cere acces la paginile mari cu record_json.
17 întâlniri au fost memorate în această probă. Nu confundăm indicii vizuali
cu entități identificate sau poziții reale în world.

Pe o copie SQLite backup consistentă, 10 interogări înainte/după, aceeași
legare hartă/navmesh și același rezultat: mediana 214.9394 → 0.5478 ms.
Nu atribuim acest raport întregului mers; este numai costul rezumatului.

## Schimbare minimă

La deschiderea DynamicExperienceStore adăugăm idempotent indexul de acoperire
(map_name, navmesh_sha256, reaction, observed_at_utc). Rezumatul folosește
numai indexul, fără acces la record_json și fără arbore temporar de grupare.
Indexul se creează și pentru bazele deja v2. Schema datelor și contractele
nu se schimbă. Nicio observație nu se șterge/rescrie, WAL/synchronous FULL
și validările rămân. Costul construirii este la deschidere, înainte de mers.
Interogarea rămâne O(n) în numărul de întâlniri ale lumii selectate; dacă
volumul crește mult, trebuie profilată din nou, nu considerată nelimitată.

Nu schimbăm controllerul, camera, plannerul, navmesh v34, autorizarea,
watchdog-ul sau Anti-AFK. Nu introducem un worker asincron inutil înainte
de a testa această corecție mică.

## Teste și acceptare

301 teste relevante PASS: memorie/evitare dinamică, cronometrare, trace,
movement engine, adaptive steering, cache XYZ. Testul de plan SQL inspectează
interogarea reală a metodei summary_record. Migrarea/reopen repetat păstrează
toate rândurile și rezumatul, separarea hărților și synchronous FULL.

Prima probă live după corecție a parcurs ieșirea, dar s-a încheiat cu
STOPPED_CHILD_ERROR: PermissionError la citirea movement-engine-control.json
în momentul opririi delimitate. Filmul și mostrele watchdog s-au păstrat,
raportul final cu timpii pe etape nu. Nu acceptăm optimizarea live din această
probă incompletă. Incidentul cere tratare fail-closed separată și repetare.
Film runtime: crypt-summary-index-live/crypt-c09-20260907-164532.mp4.
C01/C05/C07 rămân deschise până la acceptare vizuală/repetată.

### Repetare cu raport complet — bd3f37e

După corecția fail-closed separată a citirii comenzii operatorului:
run ebd340cd-ba97-4a5b-a726-40246ce9d0eb, OPERATOR_STOPPED,
298 cadre, 294 forward, zero recuperări, zero handoff-uri combat.
Film: crypt-summary-index-repeat/crypt-c09-20260907-165019.mp4,
105.233333 s, 3157 cadre, 2560×1440. Prima decizie ~83.859 s în film;
preflight-ul lung nu reprezintă durata parcurgerii criptei.

| Măsurătoare live | Înainte 5d3d9fca | După ebd340cd |
|---|---:|---:|
| Etapă dinamică, maxim | 307.80 ms | 10.635 ms |
| Ciclu post→post, maxim | 548.95 ms | 170.31 ms |
| Cicluri peste 200 ms | 9 | 0 |
| Refresh-uri precontrol | 9 | 0 |
| Ciclu median | 46.21 ms | 46.06 ms |
| Abatere maximă de la traseu | 2.807 yd | 2.995 yd |

Este eliminată sursa măsurată de pauze lungi, nu accelerat fiecare cadru și
nu demonstrată îmbunătățirea urmăririi traseului. Proba are alt număr de cadre
în același buget de ~18 s; nu comparăm indici de cadru ca poziții identice.
Ieșirea este vizibilă, dar camera își schimbă distanța în spațiul îngust și
virajele rămân de evaluat. Acceptăm optimizarea latenței ca schimbare de bază;
nu acceptăm încă humanlike, contact-free sau pragul uman de 10 s.

Verificare cumulată: 306 teste din primul grup + 38 de supervisor/autorizare/
gateway/mișcare continuă = 344 PASS. Nicio modificare de v34/controller/cameră.

## Revenire

Codul anterior este 875ada5. Indexul este aditiv și compatibil cu acel cod;
revenirea codului nu necesită ștergerea bazei sau a indexului. Pentru un A/B
strict se folosește o copie separată fără index, nu se șterge memoria reală.
Filmările și baza de profil rămân în runtime ignorat, nu în Git.
