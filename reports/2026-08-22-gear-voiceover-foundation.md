# Gear Intelligence, standalone portability și VoiceOver — foundation report

Data: 2026-08-22

## Outcome

- Portabilitatea standalone este fixată prin ADR 0008: fingerprint, capability negotiation, adapters și scenario packs.
- WoWSims este fixat prin ADR 0009 ca analist PvE advisory, separat de Brain și de availability truth.
- VoiceOver este fixat prin ADR 0010 ca strat opțional de imersiune, separat de QuestPlanner/execution.
- Au fost adăugate contracte executabile pentru target negotiation, gear analysis, NarrativeCue și external integration manifests.
- Availability firewall respinge recomandarea unui obiect care există numai ca `researched_only`.

## WoWSims evidence

- Source checkout extern: `E:\WoWserver\PerfectAssassin-Dependencies\wowsims\tbc-new`
- Commit: `3267f8dfa4a20746d4982c1522fdec1d4eb77f4c`
- Release: `v0.0.119`
- CLI: pornește și raportează `v0.0.119`.
- UI server: răspuns HTTP 200 pentru `http://127.0.0.1:3334/tbc/rogue/dps/`, apoi procesul de probă a fost oprit.
- Nu există încă dovadă pentru acuratețe level 1–69 sau calibrare 2.4.3.

## VoiceOver evidence

- Patru arhive au fost descărcate în depozitul extern, verificate pentru ZIP path traversal și hash-uite SHA-256.
- Playerul și modulele Vanilla, VanillaExtra și TBC au fost instalate în client.
- TOC-urile deployate declară exact `Interface: 20400`.
- Arhivele upstream au rămas nemodificate pentru rollback/reproducere.
- Prima lansare controlată a afișat mesajul explicit că WoW nu suportă Remote Desktop și iese. Operatorul nu a trimis login/input. Blocajul a fost sesiunea RDP, nu VoiceOver.
- Operatorul are acum un preflight care refuză `Launch` din Remote Desktop înainte de pornirea clientului legacy.
- După trecerea sesiunii în local console, loginul și Character Select au fost reconciliate vizual.
- Lista AddOns a arătat `Perfect Assassin Observer`, `VoiceOver`, `VoiceOver Data - TBC`, `VoiceOver Data - Vanilla` și `VoiceOver Data - Vanilla Extra`, toate activate; `Load out of date AddOns` a rămas dezactivat.
- In-world smoke nu a afișat eroare Lua sau avertisment de sound-pack lipsă. Logout/close au fost normale, iar `AI_VoiceOver.lua` SavedVariables a fost scris pentru `Predator - MaNGOS`, confirmând încărcarea main playerului.
- Statusul manifestului rămâne prudent `deployed_unverified` până la redarea audibilă a unui dialog real; addon discovery/main-player load sunt `controlled_live_verified` pe suprafața lor.

## Tests

- Suita completă după RDP guard și faza bounded `InspectAddons`: 40 tests, toate trecute.
- Evidence classes: `contract_tested`, `static_integration_verified`, `local_service_smoke_tested`.
- Nu declarăm `controlled_live_verified` pentru VoiceOver sau Gear Advisor.

## Următorul gate

1. PA-020b: quest NPC, loot și zone recapture.
2. PA-021: QuestPlanner/Route Drift/QuestNarrator read-only.
3. PA-022: gear snapshot, leveling evaluator și golden WoWSims request/result.
4. PA-023: client VoiceOver load + audible NPC/quest probe și coverage note.
