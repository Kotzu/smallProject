# 00 — Project charter

## Outcome

Construim un AI player Rogue adaptiv, **Predator**, capabil să parcurgă o singură istorie persistentă de la nivelul 1 la 70, să învețe din PvE și PvP, să navigheze lumea, să modeleze adversari și să folosească terenul tactic. La nivelul 70, Championul păstrează biografia și memoria reală dobândite în Journey; skill knowledge verificat poate fi promovat din LAB.

## Principii

- Decizia bună se evaluează după informația disponibilă atunci, nu doar după win/loss.
- Un loss produs de RNG, level sau gear nu este automat o greșeală.
- Curiozitatea și valoarea de învățare împiedică evitarea sistematică a fight-urilor dificile.
- PvE este curriculum real: melee, ranged, caster, elite, packs, bosses, pathing și recovery.
- PvP include stalk, ambush, bait, control, disengage, reset, re-engage și tactici de mediu.
- Gear, spells, consumables, toys, talents și respec sunt folosite numai dacă sunt obținute și disponibile legitim.
- CMaNGOS AI players pot fi oponenți și ajutor temporar la questuri grele; nu sunt fundația Predator Brain.
- Combat loop-ul rămâne local și nu depinde de internet sau Supervisor.

## Non-goals v0.1

- Nu construim încă un Rogue complet autonom.
- Nu promitem compatibilitate live cu Blizzard sau un produs viitor neanunțat.
- Nu folosim date server-only în decizii.
- Nu facem optimizare black-box bazată exclusiv pe win rate.
- Nu conectăm încă input live; Observerul este read-only.

## Journey

`level 1 -> quest -> navigate -> PvE -> loot/recover -> learn -> level/talent/gear review -> opportunistic PvP -> corpse run -> continue -> level 70`

Journey nu folosește teleportări sau progresie artificială. Checkpoint-urile 10/20/30/40/50/60/70 sunt snapshot-uri de evaluare, nu resetări de identitate.

