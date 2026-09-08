# Existing WoW AI player landscape — research report

Data: 2026-08-23

## Outcome

Nu există un proiect public verificat care să acopere produsul Perfect Assassin:
standalone, fără memory/injection, portabil 2.4.3/2.5.x, Journey 1–70,
quest/PvE/PvP learning, world/opponent memory, tactical map, Journal și
Supervisor cu patch promotion/rollback.

Cel mai apropiat proiect matur, Xian55/WowClassicGrindBot, confirmă însă
arhitectura `addon pixels -> external capture -> planner -> Recast -> input` și
arată că navmesh-ul tiled, un follower closed-loop și multi-instance sunt alegeri
practice. Perfect Assassin nu migrează la acest proiect: scope-ul este mai mic,
2.4.3 nu este demonstrat end-to-end, iar repo-ul nu are licență declarată.

Decizia durabilă este în [ADR 0019](../docs/adr/0019-clean-room-prior-art-and-first-movement-gate.md).

## Matrice verificată

| Proiect | Evidence util pentru PA | Verdict |
|---|---|---|
| [Xian55/WowClassicGrindBot](https://github.com/Xian55/WowClassicGrindBot) | addon packet, DXGI/WGC, GOAP, DotRecast, spline WASD, recovery, multi-instance | etalon principal; clean-room reference only |
| [Xian55/DotRecast](https://github.com/Xian55/DotRecast/tree/wow-mods) | Recast/Detour managed, tiled navmesh, tile cache | candidat Zlib de benchmark/pin |
| [doaneruby970-hub/wow-bot](https://github.com/doaneruby970-hub/wow-bot) | telemetry + YOLO/OCR + explicit FSM + emergency stop | prototip fragil; idei CV only |
| [Bourn23/wow_bot](https://github.com/Bourn23/wow_bot) | frame/action recorder, tracking și Gym-shaped experiments | dataset tooling reference only |
| [ber84130/wow-ai-complete](https://github.com/ber84130/wow-ai-complete) | schelet modular MIT | respins ca foundation; placeholders/hard-coded |
| [MatthewOglesby/MKOAgent](https://github.com/MatthewOglesby/MKOAgent) | screenshot -> local VLM -> finite action proof | prea lent/grosier pentru movement/PvP |
| [CMaNGOS Playerbots](https://github.com/cmangos/playerbots) | quest actors, opponents, travel graph și post-run oracle | păstrat în TBC LAB, în afara Brainului |
| [mod-playerbots](https://github.com/mod-playerbots/mod-playerbots) | corpus WotLK de quest/raid/BG strategies | viitor LAB comparativ; fără migrare |
| [namigator](https://github.com/namreeb/namigator) | parser/MapBuilder TBC + Recast, MIT | evaluare offline geometry only |

## Lecții adoptate

1. Addon telemetry trebuie să fie event-cached, versionat și separat de Brain.
2. Global route, local steering și stuck recovery sunt probleme diferite.
3. Dense Recast output are nevoie de un follower care măsoară pose și progres;
   simpla apropiere de waypoint produce overshoot și oscilație.
4. Closed-loop look-ahead, curvature braking și key-state hysteresis produc
   movement natural; random jitter nu.
5. Frame/state/action recording trebuie construit înainte de imitation learning.
6. Playerbots sunt buni ca scenarii și oracle, nu ca teacher policy.
7. Feature labels fără tests/replay/live evidence nu contează.

## Ce nu adoptăm

- cod sau tiles din repo-uri fără licență;
- waypoint routes manuale ca navigation production;
- PostMessage/background input ca shortcut pentru Champion;
- VLM/LLM la fiecare keypress;
- server coordinates, LOS, threat, quest DB ori collision în decision path;
- memory reads, hooks, injection, packet control, kernel/HID ori anti-detection;
- end-to-end RL înainte de un controller determinist și safety shield.

## Acceleration decision

Movement se livrează în două trepte:

1. **Proof of displacement:** pose proaspăt, rotire, primitive de 100–250 ms,
   feedback după fiecare, stop/release-all, replay și takeover.
2. **Production navigation:** Recast corridor, spline fallback, PA-MPPI, tactical
   costs și recovery behavior tree pe benchmark/holdouts.

Prima treaptă nu așteaptă toate continentele navmesh. A doua nu este redusă la
calitatea primei.

## Evidence classification

- `web_primary_source_reviewed`: repository code/docs și license files publice;
- `local_read_only_source_audit`: shallow checkout temporar al snapshotului
  WowClassicGrindBot, în afara repo-ului și serverului;
- `architecture_decision`: ADR 0019;
- niciun proiect terț nu a fost instalat în client, pornit sau conectat la LAB;
- niciun cod/asset/route/navmesh terț fără licență nu a fost copiat în PA.
