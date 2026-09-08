# 09 — Decizii blocate și întrebări deschise

## Locked

- Terminologie: AI player/Rogue Predator; Champion și LAB clones.
- Core/Brain portabil prin compatibility adapters; 2.4.3 LAB nu dictează modelul intern.
- Zygor = route teacher; Wowhead = Knowledge Broker; Armory/inspect = gated legitimate source.
- Fără server-only knowledge în decizii și fără amintiri LAB importate ca experiențe reale.
- Brain și execution sunt separate; movement are takeover modes.
- Champion are o identitate persistentă; LAB produce skill knowledge.
- Supervisor live este local-independent, event-driven și promovează numai patch-uri testate, versionate, cu rollback.
- Journal/HUD, tactical world map, opponent/mistake memory, replay și ShadowPlay hooks sunt parte din produs.
- Journey 1–70 include PvE, PvP, leveling, talents, gear, consumables/toys legitime, moarte și corpse run.
- Outcome-ul nu este echivalent cu decision quality; learning value contează.
- Runtime M0/M1: Python 3.11+; JSON Schema Draft 2020-12; telemetry/replay JSONL append-only.
- Produsul final este standalone prin target fingerprint, compatibility adapters, capability negotiation și scenario packs; targeturile necunoscute degradează sigur la `OBSERVE_ONLY`/unsupported.
- WoWSims `tbc-new` este analist PvE local printr-un port separat; nu intră direct în Brain și nu declară disponibilitatea obiectelor.
- Journey optimizează implicit `leveling_balanced`, nu numai raid DPS; numai equipment/bags/reward options observate legitim pot fi alese imediat.
- VoiceOver este strat opțional de imersiune/video; textul quest/gossip rămâne sursa semantică, iar audio-ul nu are execution authority.
- Movement folosește nucleu ierarhic portabil + Recast/Detour; actuatorul minim este semantic keyboard/mouse prin Execution Gateway, fără packet injection/memory/server GPS.
- CMaNGOS mmaps/pathfinder sunt LAB oracle exclusiv; Champion path proposals folosesc numai surse permise, semnate și cu provenance.
- Navigation production stack este Recast/Detour + PA-MPPI + pose fusion; Havok este eliminat și orice componentă comercială trebuie să fie sub USD 500 și benchmarkată.
- Nu folosim client memory read/write, process/DLL/packet injection, kernel/virtual-HID sau anti-detection. Actuatorul viitor este Win32 user-mode, auditat și target-allowlisted.
- Execution scope curent: emulator local/LAN/remote allowlisted + Classic/TBC PTR autorizat specific; orice `public_live` oficial, Classic/legacy sau retail, este denied.
- Prior art: WowClassicGrindBot este etalon clean-room, nu dependency; repo-urile fără licență nu furnizează cod/assets/tiles. Numai componente permisive pin-uite pot intra prin ports.
- First movement: un first-displacement gate precede navmesh-ul complet pentru calibrare și evidence vizibilă; controllerul final rămâne Recast/Detour + spline fallback + PA-MPPI, fără waypoint downgrade.

## De verificat înainte de cod target-specific

- Core/client exact pentru LAB și limitele Compatibility Spike.
- Capabilitățile reale ale addon/API pentru fiecare target și patch.
- Formatul și drepturile de acces Zygor; integrarea trebuie să respecte licența.
- Metoda permisă/fiabilă pentru Wowhead cache și rate limits.
- Armory/inspect parity și restriction matrix.
- Transportul live pentru intake și store-ul telemetry de termen lung; PA-017 folosește temporar SavedVariables offline, iar JSONL este formatul M0/M1, nu o decizie permanentă de producție.
- ShadowPlay integration disponibilă pe sistem.
- Intake-ul redactat al autorizării PTR, scope-ul exact și client/realm fingerprint înainte de PTR execution.
- Acuratețea WoWSims pentru level 1–69 și calibrarea separată 2.4.3 vs Anniversary.
- Coverage real VoiceOver pe quest IDs/textul emulatorului, locale și comportamentul music-channel pe clientul nostru 2.4.3.
- Metoda client-asset geometry și pose provider validă pentru fiecare target; lipsa coordonatelor exacte trebuie să degradeze prin uncertainty, nu omnisciență.

Acestea nu blochează M0 cu fixture adapter și contracte.
