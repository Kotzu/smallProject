# ADR-0102: Bounded live heading evidence before locomotion

## Context

Offline replay poate continua cu un yaw integrat chiar și atunci când cadrul
clientului nu mai oferă un marker util. În urma ME-328, acest lucru a permis
369 din 419 cadre să folosească doar `MOUSE_INTEGRATED_MINIMAP_FALLBACK`, iar
camera reală a putut rămâne în perete sau în tavan.

## Decision

Înainte de fiecare cadru de control, runner-ul verifică o poartă pură de
integritate a headingului. Un heading curent este acceptat numai dacă sursa
brută este `COORDINATE_HUD_EXACT` sau `MINIMAP_VISION_FALLBACK` și rezultatul
este heading vizibil, fuzionat și bounded. O lipsă de facing poate ține ultimul
heading vizual cel mult `0,30 s` (șase cadre la 20 Hz). După această limită,
runner-ul eliberează inputul, scrie `HEADING_EVIDENCE_LOST` și încheie felia;
nu transformă yaw-ul integrat într-o dovadă nouă.

Poarta nu citește memoria clientului, nu folosește server truth și nu acordă
autoritate de execuție. `camera_integrity` rămâne o poartă separată: actorul
trebuie să fie vizibil pe ecran.

## Consequences

- Un marker pierdut pentru o singură clipă nu produce o oprire inutilă.
- O cameră blocată sau un minimap lipsă nu mai poate împinge Predatorul înainte
  pe o direcție veche pentru o perioadă lungă.
- Urma live va arăta clar dacă oprirea a fost cauzată de heading sau de
  ancora camerei; testul live rămâne bounded și necesită confirmare explicită.
