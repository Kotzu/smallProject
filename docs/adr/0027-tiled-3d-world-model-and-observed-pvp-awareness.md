# ADR 0027 — Model 3D tiled al lumii și awareness PvP observabil

## Status

Acceptat pentru implementarea LAB; promovarea în Champion cere replay și verificare controlată.

## Context

Un straight path Detour redus la puncte X/Y nu descrie suficient interioare cu etaje
suprapuse, scări, portaluri înguste și pereți. Reglajele legate de o coordonată sau de
o anumită criptă nu sunt portabile și nu construiesc o competență de movement.

Predator trebuie să cunoască geometria statică și priors de lume din jur, dar nu trebuie
să transforme datele LAB ori informații neobservabile despre jucători în ground truth
Champion.

## Decizie

1. Hărțile sunt reprezentate prin tile-uri Recast/Detour construite din asset-urile
   clientului compatibil. Tile-urile din jurul poziției și coridorului sunt încărcate la
   cerere; raza de cunoaștere statică poate ajunge la 1.000 yd fără încărcarea întregului
   continent în memorie. Aceasta nu este o rază de detecție a entităților.
2. Contractul de navigație transportă straight path, poligoanele 3D ordonate și
   portalurile dintre ele. Fiecare portal include marginile și lățimea traversabilă.
3. Steering urmărește o centerline derivată din centrele portalurilor. Panta, Z-ul,
   clearance-ul și etajul corect devin constrângeri de traversare, nu euristici legate
   de o locație.
4. World model separă explicit două raze diferite:
   - geometrie, drumuri, ieșiri, spawn priors și patrol priors cu proveniență;
   - `dynamic_visibility_radius_yards`, configurabil per server/build și limitat la
     obiectele primite în visibility set-ul serverului;
   - entități dinamice active/`last_seen`, cu confidence, timp și expirare;
   - experiență append-only a întâlnirilor mature, păstrată permanent fără a
     pretinde poziția curentă ori coordonatele 3D ale entității.
5. Detectorul PvP poate consuma numai semnale permise de client: combat log, unit
   tokens, target/focus/mouseover, nameplates și alte evenimente documentate. Un player
   neobservat nu primește coordonate exacte inventate. În afara visibility set-ului,
   entitatea nu există în starea clientului; addonul, computer vision-ul și citirea
   memoriei nu pot extinde această limită.
6. Datele emulatorului pot evalua LAB-ul, dar nu intră în decizia Champion. Adaptoarele
   păstrează diferențele dintre patch-uri și servere în afara movement și brain.
7. Movement Lab este un overlay extern, read-only și fără execution authority. Modul
   MESH desenează poligoanele și centerline-ul exact folosite de controller și poate fi
   oprit pentru captură video.
8. Runnerul publică observațiile dinamice prin contractul
   `dynamic-entity-awareness.schema.json`. Poziția rămâne screen-space și
   distanța rămâne necunoscută până când un range witness separat o demonstrează;
   Control Center refuză recordurile expirate, din alt boot sau cu autoritate de
   execuție.
9. Range-ul targetului selectat folosește martori de abilitate legați semantic.
   Pentru abilitățile Rogue cu envelope `0..5 yd`, fuziunea poate demonstra
   numai `0–5 yd`, `>5 yd`, inconsistență sau necunoscut. Distanța exactă rămâne
   `null`; identitatea targetului și expiry-ul de maximum 600 ms previn
   reutilizarea martorului pentru altă țintă ori alt frame.
10. Expirarea unui track elimină numai autoritatea tactică. Întâlnirea matură
    este scrisă tranzacțional în baza SQLite WAL, legată de hartă și hash-ul
    navmesh. Recordul permanent conține poziția observatorului și cue-ul
    screen-space; `entity_world_position` este obligatoriu `null`.

## Consecințe

- Ieșirea din criptă rămâne benchmark, nu traseu scriptat.
- O blocare produce observație, heat și replan/reset LAB; nu adaugă automat un salt sau
  un waypoint specific coordonatei.
- Awareness static poate descrie ce există după un zid. Cei 1.000 yd se aplică numai
  acestui strat. Awareness dinamic despre jucători este limitat de visibility range-ul
  serverului; în afara lui rămâne numai o urmă `last_seen` probabilistică.
- Construirea tuturor hărților este un proces offline versionat; runtime-ul folosește
  streaming de tile-uri și cache verificat prin hash.
- Implementarea curentă este verificată prin 97 de regresii Movement Engine și
  suita completă de 1.045 teste; validarea live a track-urilor rămâne separată de
  această dovadă sintetică.
