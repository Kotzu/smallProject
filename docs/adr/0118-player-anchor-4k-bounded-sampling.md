# ADR-0118: Eșantionare bounded pentru captura 4K a ancorei Predatorului

## Context

În singura probă live confirmată, fereastra LAB a avut `3643x2093` pixeli.
Profilul v2 folosea `sample_stride=3` și `detector_deadline_ms=12.0`; pe cadrele
reale păstrate, detectorul a ieșit cu `player actor detector operation budget
exceeded`. Codul a scris atunci un fallback `1x1`, care putea fi confundat cu o
captură mică, deși imaginea era mare și validă.

## Decizie

Profilul v2 păstrează aceleași praguri de culoare, ROI și confidence, dar trece
la `sample_stride=4`. La captura LAB 4K rezultatul offline este `VISIBLE` în
limita de `12 ms`, iar dimensiunea eșantionată este `911x524`. Profilul v1
rămâne rollback.

În plus, `failure_record` primește dimensiunea eșantionată reală și mesajul
bounded al erorii. Astfel un timeout rămâne `UNKNOWN` și eliberează controlul,
dar jurnalul nu mai pretinde că sursa a fost `1x1`.

## Dovezi și limite

Auditul offline al celor trei checkpoint-uri LAB (`3643x2093`) cu profilul nou
este în
`data/runtime/navigation-f3b/actor-frame-audit-live-check-me380-stride4.json`:
`3/3 VISIBLE`, `0` erori, `input_emitted=false`,
`execution_authority=false`, `server_truth_used=false`. Nu este test live și
nu promovează profilul la `controlled_live_verified`; o nouă probă live cere
confirmare explicită.
