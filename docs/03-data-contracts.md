# 03 — Contracte de date v0.1

Contractele sunt versionate și append-only în telemetry. Schema incompatibilă cere major version nou.

## ObservationEnvelope

Conține: `record_type`, `schema_version`, `event_id`, `session_id`, `champion_id`, `target_profile`, `game_time_ms`, `captured_at`, `adapter`, `capabilities_hash`, `facts[]`. Fiecare fact are semantic `key`, `value`, `source`, `capability`, `confidence`, `observed_at` și eventual `expires_at`/`restriction_evidence`.

## DecisionRecord

Conține state-ul legitim referențiat, `intent`, `candidates[]` cu score/reasons/constraints, acțiunea aleasă, latența, brain version și execution mode. O decizie fără observation reference este invalidă.

## EncounterRecord

Conține tipul (`pve|pvp|mixed`), participanții observați, intervalul, brain/adapter versions, rezultat, decision quality, factori externi estimați, greșeli, lecții și replay/clip refs. `result` și `decision_quality` sunt câmpuri separate.

## MemoryRecord

Namespace obligatoriu: `champion_identity`, `opponent`, `world`, `mistake`, `skill`. Câmpul `origin` separă `champion_lived`, `champion_observed`, `lab_derived`, `external_research`. `lab_derived` nu poate fi scris în `champion_identity`.

## PatchManifest

Conține base/candidate version, scope, autor, evidență, risk class, teste obligatorii, artifacts, promotion decision, deploy target și rollback version.

## TargetFingerprint și CapabilityNegotiation

`TargetFingerprint` descrie build/version/locale/server kind exclusiv din probe și configurație permisă. `CapabilityNegotiation` înregistrează adapterul ales, statusul `exact|compatible|observe_only|unsupported`, profilul de capabilități, confidence și evidence refs. Necunoscut rămâne deny.

## GearAnalysisRequest și GearAnalysisResult

Request-ul referă un snapshot legitim de level/talents/equipment și obiecte candidate cu `availability`. Result-ul păstrează analyzer/simulator version, target/mechanic profile, assumptions, metrics, confidence, warnings, ranking și evidence refs. Este analiză counterfactuală și nu poate declara disponibil un obiect `researched_only`.

## NarrativeCue

Leagă un text quest/gossip observat de NPC/quest semantic refs, interval audio opțional, coverage state și clip marker. VoiceOver nu devine sursă de adevăr și cue-ul nu are execution authority.

## MovementGoal și PathProposal

`MovementGoal` descrie destinația semantică sau metrică, provenance, confidence și evidence refs. `PathProposal` păstrează planner/map signature/nav-source/waypoints/cost și are obligatoriu `execution_authority=false`. `lab_oracle` este invalid când `decision_context=champion`.

## PoseObservation și PoseEstimate

`PoseObservation` păstrează o măsurătoare individuală, iar `PoseEstimate` rezultatul fuziunii. Player/body și camera sunt componente separate, fiecare cu tracking state, pose, covariance/uncertainty, confidence, freshness și provenance. Build/map signatures și coordinate space sunt obligatorii. În `LOST`, player pose nu poate fi inventat; devine `null`, confidence este zero și movement rămâne interzis. `lab_oracle`/`server_ground_truth` sunt valide numai în context `lab_clone` cu scope `lab_evaluation_only`.

## MotionCalibrationTrace și CalibratedMotionModel

Trace-ul sincronizează pose/action pe același monotonic clock și păstrează
identity, authorization SHA, client/build/map signatures, uncertainty și sync
skew. Modelul derivă determinist forward speed, turn rate și input latency.
Datele oracle sunt evaluation-only și nu pot fi fitted pentru control;
configured-only Champion rămâne nepromovat. Ambele recorduri au
`execution_authority=false`.

## ExecutionLease, MovementPrimitive și ExecutionResult

Contractul breaking PA-024F1 v1.0 separă proposal-ul de authority. Lease-ul
temporar este legat exact de actor/context/target/authorization/runtime arm și
declară `required_pose_components`; pose-ul declară separat
`available_pose_components`. Listele sunt unice și folosesc numai
`POSITION_2D|YAW`. Gateway-ul cere ca toate componentele lease-ului să fie
disponibile, iar pentru `POSITION_2D` cere egalitate exactă între
`position_coordinate_space` din lease și pose.

Nullabilitatea este condițională și strictă. `position_coordinate_space` și
uncertainty `position_radius_95`/`max_position_radius_95` sunt valori numai când
componenta `POSITION_2D` este declarată; altfel sunt explicit `null`.
`yaw_error_95_deg`/`max_yaw_error_95_deg` urmează aceeași regulă pentru `YAW`.
Gateway-ul verifică numai pragurile componentelor cerute și nu inventează yaw.
F3a folosește exact `POSITION_2D` în
`normalized_current_zone_map`, cu uncertainty derivată de producător strict din
cuantizarea pachetului HUD `uint16` și toate câmpurile yaw `null`. Navigația cere
`POSITION_2D+YAW`; un pose F3a nu satisface acel lease.

Primitivele sunt scurte, secvențiale și fără authority proprie. Gateway-ul
separă hold-ul cerut de envelope-ul total, verifică toate deadline-urile imediat
înainte de sink și după `release_all`, iar takeover/release-all câștigă înaintea
confirmării rezultatului.

`ExecutionLeasePolicy` v1.0 este un obiect Python immutable purtat separat atât
de `ExecutionAuthorization`, cât și de `RuntimeArmSnapshot`. El fixează
mode/capability, controls, numărul de primitive, hold/envelope/queue, confidence,
componentele pose, coordinate space și pragurile position/yaw. La construcție și
la fiecare session gate, lease-ul trebuie să fie un subset efectiv al ambelor
politici: controale și limite numerice nu pot fi lărgite, confidence nu poate fi
slăbit, iar componentele/coordinate space/uncertainty nu pot elimina o cerință.
Politica runtime armului este recitită înainte de fiecare sink call.

PA-024F2 oferă un adaptor Win32 scan-code izolat și testat fake-only. PA-024F3a
adaugă numai fundația de authorization/runtime-arm pentru un singur
`MOVE_FORWARD`, maximum `100 ms` hold, `150 ms` envelope, coadă și buget de o
primitivă. Nu există runner ori execuție live în acest slice.

### Migrare execution-gateway v0.1 → v1.0

- toate cele patru recorduri din bundle (`ExecutionLease`, `MovementPrimitive`,
  `ExecutionPoseState`, `ExecutionResult`) trec la `schema_version="1.0"`;
- lease-ul adaugă `required_pose_components` și
  `position_coordinate_space`, `allowed_controls` și `max_primitives`; pragurile
  position/yaw devin nullable conform componentelor cerute;
- pose-ul adaugă `available_pose_components` și
  `position_coordinate_space`; uncertainty position/yaw devine nullable conform
  componentelor disponibile;
- F3a migrează la `required_pose_components=["POSITION_2D"]`, spațiul exact
  `normalized_current_zone_map` și yaw `null`; nu există alias acceptat;
- navigația declară `required_pose_components=["POSITION_2D","YAW"]` și
  furnizează ambele uncertainty;
- recordurile `0.1`, câmpurile condiționale omise, componentele duplicate ori
  necunoscute și valori non-null pentru componente absente sunt respinse.

## MovementRuntimeArm și identity issuance

`movement_runtime_arm` v0.1 este authority temporară exclusiv pentru F3a. Este
legat de snapshotul authorization aprobat, receipt-ul de sesiune v1.0, exact
PID/HWND/process creation FILETIME/path/hash, actor LAB, routing localhost și un
receipt separat de realm revalidation. Lanțul temporal cere authorization și
receipt înainte de revalidation, apoi arm issuance și `now`; ferestrele UTC și
monotonic trebuie să aibă elapsed și remaining consistente. Arm-ul poartă exact
`ExecutionLeasePolicy` F3a și nu autorizează combat ori economy.

`lab_client_identity_issuance` v1.0 este commitul immutable per receipt pentru
`Launch|AdoptSession|RenewSessionIdentity`. Markerul păstrează parent/new
receipt și authorization hashes, identity origin, PID/HWND/native FILETIME,
session și receipt-ul UTF-8 în base64. Este scris durabil înaintea proiecției
receipt-ului, permite recovery și are obligatoriu
`execution_authority=false`; JSONL rămâne numai observațional.

## Pgeom, Pnav și NavigationDebugSnapshot

`pgeom v1` și `pnav v1` sunt manifesturi actor-free, partajabile per build/map,
cu asset-manifest hash, coordinate system, bounds, Recast/profile/tile hashes și
artifact scope. Starea locală curentă este `candidate_untrusted` și
`unpromoted`. Pnav referă tile-uri binare opace prin size+SHA; nu le include în
JSON. Numai snapshotul de debug conține actor/auth binding și este explicit
`render_only`, `decision_input=false`, `execution_authority=false` pentru
`OFF|ROUTE|MESH`. Oracle-ul server/LAB nu poate intra în pgeom/pnav.

## CaptureFrameManifest

Indexează un frame read-only fără a include raw pixels: target/build, backend, monitor/regiune, dimensiuni/stride/format, timestamps, provenance, retention și artifact reference opțional. Versiunea curentă este `capture_frame_manifest` v2.0 și cere `actor_binding` v1.0 plus `authorization_sha256`. Binding-ul actorului rămâne așteptarea configurată din autorizație, nu identitate observată, iar hash-ul leagă fiecare frame de bytes exacți ai autorizației validate. Default-ul este in-memory/no retention. Un artifact persistat cere path, SHA-256 și privacy classification. Contractul impune `execution_authority=false`.

## ExecutionTargetAuthorization

Separă capabilitatea tehnică de permisiunea de deployment. Versiunea v2.0 fixează environment scope, client build/hash, expected realm profile, `actor_binding`, restrictions, evidence, limita sesiunii și runtime arm obligatoriu. `permitted_capabilities` autorizează suprafețe auxiliare bounded precum captură read-only sau `LAB_OPERATOR_FIXED_UI`; `permitted_modes` autorizează separat moduri Predator (`MOVEMENT_ONLY|COMBAT_ONLY|FULL_AI`). O capabilitate fixed-UI nu implică movement, iar un profil poate avea capabilities aprobate cu `permitted_modes=[]`. Emulatorul poate fi local/LAN/remote, cu remote limitat la assurance-ul declarat de profil. PTR cere approval `platform_owner`; `pending_evidence` nu are modes/capabilities, iar orice `public_live` este deny-by-construction.

## TBC 2.4.3 addon export

Contractul intermediar `tbc243-addon-export` descrie exclusiv bufferul client-persisted: versiune, target profile, event format, session binding, capability probes și evenimente raw. Nu este ObservationEnvelope și nu poate ocoli adapterul sau firewall-ul. Fișierul `.lua` este parsat ca date neîncrezute, niciodată executat.

## Catalogul executabil curent

Directorul `contracts/` conține exact 27 scheme JSON executabile:

| Schema | Boundary validat |
|---|---|
| [capability-profile.schema.json](../contracts/capability-profile.schema.json) | profil de capabilități, availability, provenance și default deny |
| [capture-frame.schema.json](../contracts/capture-frame.schema.json) | manifest de frame v2.0, actor binding, authorization hash, privacy și timing |
| [coordinate-hud-profile.schema.json](../contracts/coordinate-hud-profile.schema.json) | profil detector HUD build-pinned, geometrie, praguri și deadline-uri |
| [coordinate-hud-sequence-summary.schema.json](../contracts/coordinate-hud-sequence-summary.schema.json) | rezultat bounded multi-frame pentru freshness, continuity și fail-closed |
| [coordinate-hud.schema.json](../contracts/coordinate-hud.schema.json) | observație HUD individuală, poziție proprie, actor/auth binding și provenance |
| [core.schema.json](../contracts/core.schema.json) | `ObservationEnvelope`, `DecisionRecord`, `EncounterRecord` și `MemoryRecord` |
| [execution-gateway.schema.json](../contracts/execution-gateway.schema.json) | lease/primitive/pose/result v1.0, componente pose explicite, nullabilitate condițională, deadlines, takeover și release semantics |
| [execution-target-authorization.schema.json](../contracts/execution-target-authorization.schema.json) | autorizare target v2.0, actor binding, capabilities, modes, approval și runtime-arm policy |
| [external-integration.schema.json](../contracts/external-integration.schema.json) | pin, licență, artifacts și deployment state pentru integrări externe |
| [gear-analysis.schema.json](../contracts/gear-analysis.schema.json) | request/result pentru analiză gear cu availability firewall |
| [lab-client-identity-issuance.schema.json](../contracts/lab-client-identity-issuance.schema.json) | commit immutable și non-authority pentru Launch/Adopt/Renew, recovery receipt și chain hashes |
| [lab-client-launch-receipt.schema.json](../contracts/lab-client-launch-receipt.schema.json) | receipt expiring pentru exact PID/HWND/client/realm și configured expected actor binding |
| [lab-client-runtime-arm.schema.json](../contracts/lab-client-runtime-arm.schema.json) | arm temporar legat de receipt, authorization hash și set finit de acțiuni |
| [minimap-vision.schema.json](../contracts/minimap-vision.schema.json) | profil ROI v0.1 și observație minimap v1.0 fără absolute pose |
| [motion-calibration.schema.json](../contracts/motion-calibration.schema.json) | trace pose/action sincronizat și model determinist speed/turn/latency fără execution authority |
| [movement-runtime-arm.schema.json](../contracts/movement-runtime-arm.schema.json) | arm F3a exact, receipt/revalidation/process-bound, un singur MOVE_FORWARD și fără combat/economy |
| [single-forward-pulse-result.schema.json](../contracts/single-forward-pulse-result.schema.json) | rezultat F3a non-authority: pre/post HUD, execuție, incertitudine, deplasare dovedită și cleanup obligatoriu |
| [movement.schema.json](../contracts/movement.schema.json) | `MovementGoal` și `PathProposal`, ambele fără execution authority |
| [narrative-cue.schema.json](../contracts/narrative-cue.schema.json) | cue narativ din text client-observed și referințe audio/clip |
| [navigation-debug-snapshot.schema.json](../contracts/navigation-debug-snapshot.schema.json) | snapshot top-down `OFF|ROUTE|MESH`, actor-bound și strict render-only |
| [navigation-geometry.schema.json](../contracts/navigation-geometry.schema.json) | manifest `pgeom v1` actor-free din asseturi client, coordonate și tile hashes |
| [navigation-mesh.schema.json](../contracts/navigation-mesh.schema.json) | manifest `pnav v1` actor-free cu Recast pin și referințe binare size/SHA |
| [pose.schema.json](../contracts/pose.schema.json) | `PoseObservation` și `PoseEstimate`, cu player/camera separate și uncertainty |
| [raw-fixture.schema.json](../contracts/raw-fixture.schema.json) | fixture sintetic brut pentru adapter/replay testing |
| [fight-learning-bundle.schema.json](../contracts/fight-learning-bundle.schema.json) | timeline PvE/PvP complet, action-to-effect, diagnostic și evidence fără promovare dintr-un singur fight |
| [target-profile.schema.json](../contracts/target-profile.schema.json) | `TargetFingerprint` și `CapabilityNegotiation` |
| [tbc243-addon-export.schema.json](../contracts/tbc243-addon-export.schema.json) | exportul SavedVariables neîncrezut al Observerului TBC 2.4.3 |
| [world-map-area-profile.schema.json](../contracts/world-map-area-profile.schema.json) | calibrare client-asset hash-pinned pentru transformarea world-map 2D |
