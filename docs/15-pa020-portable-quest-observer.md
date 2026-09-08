# 15 — PA-020 portable quest observer

## Outcome target

Capture what the client legitimately knows about a quest before any questing execution is enabled:

```text
NPC dialog / quest detail / quest log / spellbook
                    ↓
        PerfectAssassinObserver 0.2
                    ↓
        SavedVariables schema 0.2
                    ↓
    TBC adapter + provenance firewall
                    ↓
     replay / Journal / QuestPlanner later
```

## Live status — 2026-08-22

The first live capture verified `quest_detail`, accepted quest state in `quest_log_snapshot` and a non-empty level-1 Rogue `spellbook_snapshot`. The complete PA-020 gate remains open because the direct single-quest dialog did not emit a separate greeting snapshot and no loot window was captured. Exact evidence and gaps are recorded in [16 — PA-020 first live quest capture](16-pa020-first-live-quest-capture.md).

Addon `0.2.1` additionally recaptures location on zone-change events after the live export showed that the earliest login snapshots could contain empty zone strings.

## New observation contracts

- `quest_npc_snapshot`: NPC identity, greeting text, available and active quest titles;
- `quest_detail`: title, narrative description, objective text, suggested group and NPC identity;
- `quest_log_snapshot`: client-visible quest entries, completion flag and objective progress;
- `spellbook_snapshot`: spellbook index, tab, localized name/rank and passive flag;
- existing `loot_snapshot`: remains the only source for actual visible loot-window contents.

TBC 2.4.3 does not expose a stable quest ID through the `GetQuestLogTitle` signature used by its FrameXML. We therefore record the observed title/level/context and do not insert an emulator DB ID. A quest appearing in the quest log proves `present_in_log`; it does not prove which server packet caused it.

Empty Lua arrays are serialized as `{}` by the client. The adapter normalizes this legacy representation only for known list fields before schema validation. Unknown or server-only fields are rejected.

## Narrative reaction

The future `QuestNarrator` may produce lines such as:

> „Minunat. M-am trezit de câteva minute și deja trebuie să rezolv problema lui Undertaker Mordo.”

This is labeled personality/interpretation, not an observed fact. It may quote or paraphrase the quest, but it cannot invent kill counts, targets, locations or rewards. It runs asynchronously and never blocks combat or movement.

Provider priority:

1. local model for routine Journey voice;
2. optional cloud model for higher-quality milestone scenes;
3. deterministic template fallback when no model is available.

API keys remain in a local secret store and never in addon SavedVariables, telemetry, Git or chat logs.

## Zygor and emulator drift

Zygor is accepted as an optional `RouteTeacher`, not installed as a hard dependency. Each route step will have:

- provider and guide version;
- target profile/build;
- expected quest/title/objective/waypoint;
- observed compatibility state: `matched | blocked | divergent | completed`;
- fallback/replan reason.

If the emulator differs, the client observation wins. Playerbots may help with a difficult quest or supply LAB comparison traces, but does not supply quest facts to the Predator Brain.

## Controlled probe card

The client must be closed while addon 0.2 is installed.

1. Log in manually with the non-GM observer account and the temporary Rogue LAB clone.
2. Talk to a quest giver and leave the greeting visible briefly.
3. Open one quest detail and read it; do not accept immediately.
4. Accept it manually, then open the quest log and select it.
5. Perform one objective step if nearby.
6. Kill one appropriate mob and open the loot window before taking the items.
7. Logout normally and close the client.
8. Import SavedVariables and reconcile quest title/text/log/objectives, spellbook and loot against the screen.

Predator remains `OBSERVE_ONLY`; the operator performs every click and movement in this probe.

## Promotion gate

PA-020 becomes `controlled_live_verified` only if the real export contains:

- a quest NPC snapshot;
- quest detail text and objective text;
- the same quest present in the quest log after manual acceptance;
- a non-empty level-1 Rogue spellbook;
- a real loot snapshot or an explicitly documented no-loot result;
- no unknown/server-only field and no protected action from the addon.
