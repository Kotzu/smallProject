# ADR 0008 — Portabilitate prin target fingerprint și capability negotiation

- Status: accepted
- Date: 2026-08-22

## Context

Perfect Assassin trebuie să poată fi testat pe versiuni WoW, emulatoare, servere și contexte diferite fără ca Brain-ul, memoria Championului sau skill-urile învățate să depindă de CMaNGOS ori de clientul TBC 2.4.3.

„Standalone” nu înseamnă că un build necunoscut este controlat fără verificare. Înseamnă că produsul pornește cu un nucleu stabil, identifică targetul, negociază capabilitățile și încarcă numai adapterele compatibile. Un target necunoscut cade sigur în `OBSERVE_ONLY` sau `unsupported`.

## Decizie

Separăm:

1. `Perfect Assassin Core`: domain, Brain, movement policy, memory, Journal, replay, Supervisor și learning.
2. `Target Adapter`: traducere client/build/core către contractele semantice.
3. `Capability Profile`: ce poate fi observat sau executat legitim și cu ce restricții.
4. `Scenario Pack`: open world, questing, PvP, dungeon sau alt benchmark, fără IDs patch-specific.
5. `Deployment Policy`: LAB privat, server terț permis sau platformă oficială, cu reguli proprii.

La conectare, `TargetFingerprint` identifică familia, versiunea/build-ul clientului, tipul serverului, locale și dovezile disponibile. `CapabilityNegotiation` alege un adapter numai dacă fingerprint-ul și probele corespund.

Statusurile de compatibilitate sunt:

- `exact`: target verificat și adapter testat pentru build.
- `compatible`: suprafața folosită a trecut probele, deși targetul nu este identic.
- `observe_only`: putem colecta legitim, dar execution nu este aprobat.
- `unsupported`: nu există o cale sigură și verificată.

Necunoscut înseamnă deny. Nu folosim server core detection sau DB access ca input pentru Champion. Acestea pot exista numai în LAB diagnostics.

## Consecințe

- Brain-ul folosește semantic IDs și nu importă adaptere.
- Fiecare target nou intră printr-un compatibility spike și golden replay suite.
- Skill-urile transferabile sunt promovate semantic; datele sau mecanicile specifice rămân în adapter/scenario profile.
- Dungeon strategies vor fi scenario packs versionate și observabile, nu scripturi îngropate în Brain.
- Nu promitem execution pe orice server; promitem degradare sigură și o cale explicită de integrare.

