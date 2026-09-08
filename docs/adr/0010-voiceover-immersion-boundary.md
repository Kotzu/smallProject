# ADR 0010 — VoiceOver ca strat de imersiune, nu sursă de adevăr

- Status: accepted
- Date: 2026-08-22

## Context

Predator Journey trebuie să fie ușor de urmărit ca poveste și conținut video. VoiceOver poate reda dialogurile NPC și textele questurilor, inclusiv pe clientul legacy TBC 2.4.3, dacă playerul și modulele audio potrivite sunt instalate.

Emulatorul poate avea texte/IDs diferite de corpusul addonului. Sunetul poate lipsi, iar redarea pe 2.4.3 are limitări API. Audio-ul nu este o bază stabilă pentru logică de quest sau combat.

## Decizie

VoiceOver este o integrare client-side opțională în `Narrative/Presentation`, fără autoritate de execution și fără import în Brain.

- Textul observat legitim din quest/gossip rămâne sursa semantică.
- Audio-ul este pentru operator, stream și filmul Journey.
- Un `NarrativeCue` poate lega NPC/quest, text evidence și intervalul audio de Journal/clip markers.
- Reacțiile Predatorului sunt reflecții generate și etichetate, nu replici canonice ale NPC-ului.
- Lipsa VoiceOver sau a unui fișier audio nu poate bloca questing, combat ori learning.
- Addonul și pachetele audio sunt third-party, ținute în afara repo-ului și inventariate prin versiune/hash/licență.

## Compatibilitate inițială

Există un player VoiceOver dedicat `2.4.3`. Pentru acoperirea Journey sunt necesare separat playerul, modulul Vanilla original și, după zonă, modulele VanillaExtra/TBC. Se activează `Load out of date AddOns` numai după o probă controlată.

## Consecințe

- Nu transcriem audio pentru a recupera un text deja expus legitim de UI.
- Putem adăuga ulterior percepție audio pentru cues care există numai în sunet, cu provenance și confidence distincte.
- Coverage gaps devin observații de producție video, nu erori ale QuestPlannerului.
- Volumul, music-channel fallback și întreruperea sunetului sunt setări de prezentare per client adapter.

