# PA-024B2b1 — Minimap geometry detector v0.1

Data: 2026-08-22

Evidence class: `contract_tested` + `synthetic_fixture_tested`

Controlled-live evidence: **nu**

## Outcome

Sidecar-ul Windows poate localiza determinist geometria minimap într-un frame BGRA8, fără OpenCV, memory read sau pixel persistence:

```text
CapturePacket pixels + validated manifest
                 |
       versioned MinimapRoiProfile
                 |
        NumPy geometry detector
                 |
      MinimapVisualObservation
       FOUND / DEGRADED / NOT_FOUND
                 |
       absolute_pose_available=false
```

Această etapă localizează UI-ul, nu Rogue Predator în world coordinates.

## Artefacte

- `contracts/minimap-vision.schema.json`: profil v0.1 + observation v1.0 cu
  actor binding, `authorization_sha256` și scope contextual;
- `config/pose/minimap-tbc243-8606.json`: profil build-pinned, `synthetic_only`;
- `integrations/windows-capture/minimap_detector.py`: detector read-only;
- `tests/test_minimap_vision_detector.py`: fixture generator și cazuri negative.

## Algoritm v0.1

1. validează `CaptureFrameManifest` v2.0, binding-ul configurat așteptat al
   actorului și identitatea exactă profile/build/signature; nu pretinde că
   personajul efectiv logat a fost observat;
2. construiește o vedere BGRA caller-owned, respectând row stride;
3. limitează căutarea la ROI normalizat din colțul dreapta-sus;
4. caută circular edge coverage pe raze și centre bounded;
5. caută markerul configurat cromatic numai în discul central;
6. estimează orientarea markerului prin axa principală a pixelilor;
7. publică numai geometrie screen-space, confidence și provenance.

Nu există import OpenCV și nu a fost adăugată o dependență nouă; NumPy 2.5.2 este deja pin-uit în wheelhouse-ul capture.

## State machine

- `FOUND`: cerc și marker validate;
- `DEGRADED`: cerc valid, marker absent/nesigur;
- `NOT_FOUND`: cercul nu trece ring coverage/confidence;
- mismatch de profile/build/pixel format sau buffer invalid: error fail-closed.

## Cazuri verificate

- cerc + marker orientat: pass;
- cerc fără marker: `DEGRADED`;
- loading/solid frame: `NOT_FOUND`;
- noise nestructurat seeded: `NOT_FOUND`;
- build mismatch: refuz;
- buffer scurt/shape greșit: refuz;
- orice claim `absolute_pose_available=true`: respins de contract;
- două LAB clones păstrează binding-uri configurate așteptate distincte:
  `instance_id`, `actor_id`, memory namespace și authorization hash;
- replay-ul rămâne `synthetic_fixture`, LAB live rămâne
  `lab_evaluation_only`, iar Champion configurat rămâne
  `unpromoted_evaluation_only`;
- relabeling-ul provenance replay → Champion: respins;
- determinism pentru același frame: pass;
- suită focalizată curentă: `11/11` pass.

Contractul observației a fost migrat incompatibil de la v0.1 la v1.0 pentru a
propaga binding-ul configurat așteptat al actorului, assurance-ul sursei și
`authorization_sha256` din manifestul v2.0. Hash-ul autorizației fixează bytes
exacți validați; nu transformă actorul așteptat într-o identitate observată.
Fixture-urile vechi nu sunt promovate implicit.

## Corecție arhitecturală importantă

În minimap-ul WoW, markerul playerului este de regulă central, iar lumea se deplasează în jurul lui. Detectarea markerului nu oferă automat normalized map position. În rotating-minimap mode, nici orientarea screen-space nu este direct body yaw fără calibrarea rotației hărții.

Prin urmare, acest record nu este convertibil direct în `PoseObservation`. Conversia va cere o sursă legitimă de map registration, un profil north-up/rotating verificat și uncertainty măsurată.

## Limite

- pragurile cromatice și geometrice sunt validate numai sintetic;
- UI scale, addons, minimap skins și locale pot modifica ROI-ul;
- marker orientation păstrează posibilă ambiguitatea de 180° pe forme aproape simetrice;
- nu există world/zone texture registration;
- nu există benchmark live sau deadline claim;
- clientul WoW nu era pornit la închiderea acestei etape, deci nu s-a încercat proba live.

## Următorul gate: PA-024B2b2

1. captură controlată in-memory a clientului la login și in-world;
2. selecție explicită a UI scale și minimap rotation mode;
3. cadre redactate reprezentative: minimap normal, marker absent, map open, loading, combat clutter, resize;
4. calibrare thresholds fără a suprascrie profilul `synthetic_only`;
5. profil nou `replay_calibrated`, benchmark și holdout frames;
6. probă live read-only înaintea oricărei legături cu pose fusion.
