# Audit read-only: sursă legacy GGL / StreamOverlay

Data auditului: 2026-08-22  
Sursă locală: `E:\_ForGames\WoW\_FromPCdesktop\ScreenRecorder`  
Scop: identificarea unor concepte reutilizabile pentru combat knowledge, fără executarea sau importarea pachetului.

## Verdict

Pachetul nu este o bază de cod potrivită pentru Perfect Assassin. Cele două fișiere Rogue principale nu sunt sursă Lua lizibilă, iar containerele lor nu pot fi citite ca arhive ZIP standard. Fișierele Lua lizibile sunt exporturi de configurare `TellMeWhenDB`, nu implementarea motorului de combat.

Materialul rămâne util numai ca sursă secundară de idei și vocabular. Orice regulă inspirată de el trebuie rescrisă ca ipoteză semantică, validată separat pentru TBC 2.4.3 și testată în LAB înainte de a putea deveni candidat pentru Champion.

## Limita auditului

- Nu a fost pornit niciun executabil, DLL, driver sau script.
- Nu s-au deschis `ChromeProfile`, baze de date, loguri, fișiere de cont sau configurații care pot conține date personale.
- Nu s-a încercat decriptarea, spargerea parolelor sau ocolirea containerelor proprietare.
- Nu s-a copiat cod sau conținut licențiat în workspace.
- Analiza a folosit numai nume, dimensiuni, semnături, hash-uri, metadate și mostre text limitate din exporturile lizibile.

## Inventar relevant

Au fost găsite 35 de fișiere cu extensia `.lua`.

| Fișier | Dimensiune | Observație |
|---|---:|---|
| `Spiken\SpikenBasicRogue.lua` | 235331 bytes | Prefix `PK`, dar structură incompatibilă cu o arhivă ZIP standard; conținut nelizibil |
| `Spiken\SpikenGladRogue.lua` | 337219 bytes | Prefix `PK`, dar structură incompatibilă cu o arhivă ZIP standard; conținut nelizibil |
| `ScortchRotations.lua` | 3526198 bytes | Export text `TellMeWhenDB`; conține profilul `[Scortch] Rogue` |
| `JMR_CR.lua` | 3162218 bytes | Export text `TellMeWhenDB`; referințe multi-clasă |
| `TripRoutines.lua` | 8308879 bytes | Export text `TellMeWhenDB`; referințe multi-clasă |
| `Berserker_Druid_v2.0.lua` | 3267799 bytes | Export text `TellMeWhenDB`; profil Druid, nerelevant direct pentru Rogue |

Directoarele `_classic_` și `_classic_era_` conțin doar câte un `WTF\Config.wtf` gol; nu oferă logică Classic/TBC.

## Proveniență reproductibilă

| Artefact | Last write local | SHA-256 |
|---|---|---|
| `SpikenBasicRogue.lua` | 2024-05-15 15:09:58 +03:00 | `8709B824294292D22DBCAD81996AD1DD6E82DEBA40B09B99A74AA8C4DDFB01D8` |
| `SpikenGladRogue.lua` | 2025-12-08 20:51:47 +02:00 | `0F6D6D2D5049EC90D5BD7188FB6D135BB6F60F1A4DF51326983BD9152B606715` |
| `ScortchRotations.lua` | 2024-05-15 15:09:51 +03:00 | `0A1878A5CA954FA7D4E68E092569F30134E5F1A502877E33C629CD0972FEA52C` |

Hash-urile identifică fișierele inspectate; ele nu confirmă autenticitatea, autorul, licența sau compatibilitatea.

## Compatibilitate observată

Exporturile lizibile raportează câmpuri `Version = 90201`, iar interfața din capturi enumeră clase și mecanici din ere ulterioare TBC, inclusiv Monk, Demon Hunter, Evoker, `Dismantle`, `Tricks of the Trade` și `Shadow Dance`.

Concluzie: pachetul este mixt și orientat în principal către versiuni mult mai noi decât TBC 2.4.3. Niciun spell ID, prag numeric, timing sau prioritate din el nu poate traversa direct compatibility adapter-ul.

## Adoptăm ca idei, nu ca implementare

1. **Arbitraj ierarhic al intențiilor**: survival, escape, interrupt, hard CC, control maintenance, damage, recovery. Combatul nu trebuie redus la o rotație liniară.
2. **Canale semantice distincte**: `target`, `focus`, party member și adversar urmărit. Adapterul decide ce canale există legitim pe clientul curent.
3. **Cast commitment estimator**: conceptul numit în UI „AntiFake” devine o estimare explicită a probabilității că adversarul își va termina cast-ul, bazată pe observații legitime, latență și istoric. Nu este mecanism anti-detection.
4. **LOS ca stare tactică**: line-of-sight intră atât în selecția acțiunii, cât și în obiectivul de movement/reposition.
5. **Suspend/withhold gates**: uneori decizia corectă este păstrarea unui cooldown sau CC pentru o fereastră cu valoare mai mare. Pragurile trebuie învățate/testate, nu copiate.
6. **Separarea PvE/PvP**: aceeași abilitate poate avea politici și valoare diferite după tipul întâlnirii, fără a duplica catalogul semantic de abilități.

## Respingem explicit

- random timings concepute în jurul riscului de ban;
- `AntiAFK`, `Random Exe`, `Random Icon`, ascunderea aplicației sau alte mecanisme de camuflare;
- driver, kernel input, virtual HID, memory read, injection sau process hooks;
- importul profilurilor ca rotații Champion;
- copierea codului, payload-urilor sau configurațiilor fără proveniență și drept clar de reutilizare;
- orice afirmație că profilul este TBC doar pentru că există directoare cu numele `classic`.

Aceste respingeri sunt aliniate cu `docs/adr/0013-client-integrity-and-input-execution-boundary.md` și cu regulile repository-ului.

## Contract recomandat pentru intake

Orice idee externă de combat intră mai întâi ca `CombatKnowledgeCandidate`, nu ca regulă activă:

```text
candidate_id
source_ref + source_hash
license_status
claimed_game_family + claimed_build
semantic_intent
observed_preconditions
observed_exclusions
confidence
validation_status
allowed_destination = LAB_RESEARCH_ONLY
```

Promovarea cere: mapare prin compatibility adapter, dovadă independentă pentru build, teste de contract, replay-uri seeded, scenarii negative și comparație cu Stable. Până atunci, candidatul nu poate influența Champion.

## Acțiunea următoare

Nu investim timp în reverse engineering-ul containerelor GGL. Extragem numai taxonomia de mai sus în viitorul model semantic de combat și continuăm ordinea curentă de implementare. Când ajungem la combat policy, construim întâi catalogul TBC 2.4.3 din surse verificabile și din observațiile LAB proprii, apoi folosim această sursă doar ca listă de ipoteze pentru teste.
