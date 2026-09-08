# Grupurile WMO nu sunt etaje și cutiile lor nu sunt volume interioare

## Întrebarea verificată

Putem compara IsIndoors/IsOutdoors cu geometria actuală pentru a diferenția
cele două niveluri alternative? Nu doar pe baza marcajului WMO/navmesh sau
a încadrării într-o cutie de delimitare. Proba de mai jos schimbă pasul următor:
este necesară asocierea cu suprafețele/grupurile reale, nu o filtrare după AABB.

## Dovezi din codul local

În dependența NAMIGATOR, parser/Wmo/GroupFile/WmoGroupFile.cpp citește Flags
din MOGP. parser/Wmo/Wmo.cpp concatenează triunghiurile grupurilor și reduce
asocierea zonă/arie la name-set; comentariul local recunoaște limita reducerii.
MapBuilder/MeshBuilder.cpp, SerializeWmo, serializă arborele geometric comun,
root ID, asocierile name-set și doodad-urile. pathfind/Model.hpp și încărcarea
Map::EnsureWmoModelLoaded nu păstrează identitatea/flags/bounds per grup.
Prin urmare marcajele interior/exterior nu pot fi recuperate direct din API-ul
sonar actual. Nu am modificat dependența, WorldPack-ul sau workerul v34.

## Instrument offline nou

adapter/wmo_groups.py citește strict WMO v17: MVER, MOHD și MOGI, maximum
16 MiB/512 grupuri, fără scanare arbitrară după semnături în interiorul datelor.
Respinge versiuni necunoscute, chunk-uri trunchiate/duplicate, număr incoerent,
bounds inversate/nonfinite. Păstrează hash-ul assetului, root ID, index, flags
brute și bounds în coordonatele modelului. Nu exportă numele grupurilor.

Semnificația documentată a biților 0x8/0x2000 este folosită numai ca etichetă
de metadate. Ambii/niciunul rămân stări distincte, nu alegeri arbitrare.
Referință de format consultată: [MaNGOS WMO](https://www.getmangos.eu/wiki/referenceinfo/clientfiles/wmo-file-r20030/).
Echivalența cu decizia API a clientului nu este încă validată.

tools/audit_wmo_group_bounds.py transformă punctele de audit din world în
model folosind inversa matricei instanței din index. Nu folosește orientarea
camerei sau o translație presupusă. Toate cutiile compatibile sunt păstrate.
Toolul nu validează legătura binară dintre assetul primit și instanța indexului;
raportează explicit asset_instance_binding_verified=false. Este diagnostic
offline, nu un importor de artefacte în runtime. Înainte de runtime trebuie
fixate proveniența/precedența MPQ, hash-urile și asocierea cu WorldPack-ul.

## Probe cu date originale ale clientului, nu serverului

Extractorul existent v3 a citit read-only două rădăcini din MPQ-urile locale;
fișierele sunt numai în data/runtime/wmo-semantic-probe-20260906, ignorate Git.
Această verificare nu folosește poziții runtime ale serverului sau process memory.

- md_cryptonerm: root ID 712, cinci grupuri (unul cu bit exterior, patru interior).
  SHA256 058f40d5ca2a4e7fdbb0c2a7883f37a3662c203908b89e35924f68643de3ba92.
  Instanța de audit 0:wmo:85944. Cele două puncte de referință la același XY
  1676,369629 /1677,466919, Z121,797379 și Z138,729095 sunt ambele în bounds
  ale grupului 4, marcat interior. Nu înseamnă apartenență reală la grup și
  nici că ambele puncte sunt în interior; tocmai această deducție este refuzată.
- goldshireinn: root ID 53, 12 grupuri (două cu bit exterior, zece interior).
  SHA256 079608e789723183b6b2f226a60ce885c8b080eb25cba59f572ed2150e3841a1.
  La centrul instanței 0:wmo:71414, punct pur geometric, cutiile 4/5/9 se
  suprapun: una exterior și două interior. Nu am deplasat actorul acolo.

Teste abstracte protejează ambele mecanisme fără a comite geometrie licențiată.
23 teste noi PASS; selecția împreună cu environment/location/sonar/height scan:
195 PASS în 0,62 s. Ruff și git diff --check trec. Eroarea inițială de setup
pytest provenea din ID-ul parametrizat uriaș al fixture-ului de 513 grupuri;
ID-uri explicite scurte au reparat infrastructura testului, nu parserul.
Probele offline nu înlocuiesc validarea live interior/exterior sau a etajului.

## Pasul următor și rollback

Asociere per triunghi/suprafață cu grupul WMO și verificarea limitelor dintre
grupuri; doar apoi comparație cu observația API. Portalurile grafice nu vor fi
tratate automat ca treceri traversabile. Nivelurile rămân alternative dacă
observația nu le diferențiază, inclusiv două etaje interioare identice semantic.
Pentru astfel de cazuri este necesară o altă observație sau o tranziție urmărită.

Acest commit este offline: CC, addonul 0.5.10, anti-AFK și navigația v34 rămân
neschimbate. Rollback înseamnă revenirea acestui commit; nimic de reinstalat.
