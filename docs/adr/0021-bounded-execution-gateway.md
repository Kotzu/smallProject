# ADR 0021 — Gateway unic și revocabil pentru execution

- Status: accepted
- Date: 2026-08-23
- Extends: ADR 0013 și ADR 0017

## Context

Plannerul, navigația și brain-ul pot propune mișcare, dar nu trebuie să poată
atinge direct un adaptor de input. O primitivă scurtă poate deveni periculoasă
dacă pose-ul, lease-ul, authorization ori runtime arm expiră în timpul ei sau
dacă takeover-ul manual pierde o cursă cu rezultatul raportat.

## Decizie

Orice viitor input al Predatorului trece printr-un singur `ExecutionGateway`.
Gateway-ul cere simultan:

- actor, instance, target, authorization SHA și owner identice;
- `MOVEMENT_EXECUTION` permis de authorization, lease și runtime arm;
- `ExecutionLeasePolicy` v1.0 din lease este un subset efectiv al politicii
  immutable purtate separat de authorization și de snapshotul runtime arm;
- pose `VALID`, fresh și în limitele de confidence/uncertainty ale lease-ului;
- toate componentele de pose cerute explicit de lease, în același spațiu de
  coordonate pentru `POSITION_2D`;
- sequence continuu, primitive ID nerefolosit și coadă bounded;
- atât `hold_duration_ms`, cât și întregul `max_execution_envelope_ms`
  încadrate în expiry-ul primitivei, pose-ului, lease-ului, runtime armului și
  authorization;
- un sink cu deadline absolut, timp maxim de blocare și anulare cooperativă.

După `apply`, gateway-ul execută `release_all`, re-verifică timpul, epoca de
stare și runtime armul înainte de a putea publica `EXECUTED`. Manual takeover,
close și revocarea runtime armului anulează execuția in-flight, golesc coada și
au prioritate față de commitul rezultatului.

Gateway-ul este strict single-flight. `execute(p)` este asociat atomic cu
primitiva cerută și nu poate consuma head-ul altei cozi. Un watchdog separat
folosește deadline-ul gateway-owned pentru a anula și elibera inputul chiar dacă
un sink defect ignoră bugetul primit; workerul abandonat nu mai poate produce un
rezultat valid. Dacă acel worker revine târziu, rămâne urmărit și execută o
eliberare finală. Contractul interzice lucrul de input detașat și nu pretinde că
un thread Python poate fi oprit forțat.

Un eșec `release_all` este vizibil: takeover-ul raportează eșec, iar gateway-ul
păstrează un latch `release_faulted`; close păstrează starea terminală `CLOSED`,
dar nu poate ascunde fault-ul de release.

Erorile venite dintr-un sink sunt normalizate la coduri semantice finite; numele
claselor Python ori excepțiile native nu traversează contractul.

## Policy binding end-to-end

Authorization și runtime arm nu mai acordă doar un mode/capability generic.
Ambele poartă întreaga politică versionată: `allowed_controls`,
`max_primitives`, hold/envelope/queue, confidence minim, componente pose,
coordinate space și praguri position/yaw. Lease-ul proiectează exact aceeași
structură. Gateway-ul îngheață verificarea față de authorization la inițializare
și o repetă în session gate; politica runtime armului este eșantionată și
verificată la fiecare enqueue/run înainte de sink.

Subset efectiv înseamnă: controls subset, limitele maxime mai mici sau egale,
confidence minim mai mare sau egal, componentele cerute cel puțin la fel de
stricte, coordinate space identic pentru poziția cerută și uncertainty maxim
mai mic sau egal. `LEASE_POLICY_DENIED` și
`RUNTIME_ARM_POLICY_MISMATCH` sunt rezultate fail-closed. Astfel un caller care
construiește manual un lease mai larg nu poate transforma acel obiect în
authority.

## Contract pose v1.0

Versiunea `1.0` este intenționat incompatibilă cu `0.1`. Orice lease declară
`required_pose_components`, iar orice pose declară
`available_pose_components`. Componentele permise sunt `POSITION_2D` și `YAW`.
Gateway-ul cere ca lista lease-ului să fie subset al componentelor disponibile;
în caz contrar răspunde `POSE_COMPONENTS_MISSING` și nu apelează sink-ul.

Pentru `POSITION_2D`, lease-ul și pose-ul trebuie să declare exact același
`position_coordinate_space`; o diferență produce
`POSE_COORDINATE_SPACE_MISMATCH`. Pragul `max_position_radius_95` este verificat
numai dacă lease-ul cere poziție. Similar, `max_yaw_error_95_deg` este verificat
numai dacă lease-ul cere `YAW`. Câmpurile de uncertainty și spațiu care nu
corespund unei componente declarate sunt obligatoriu `null`; astfel contractul
nu poate fabrica un yaw necunoscut.

F3a folosește strict `required_pose_components=["POSITION_2D"]` și
`position_coordinate_space="normalized_current_zone_map"`. Pose-ul F3a are yaw absent și
`yaw_error_95_deg=null`; producătorul pose-ului trebuie să derive uncertainty de
poziție strict din cuantizarea pachetului HUD `uint16`, nu din adevăr world-map.
F1 consumă acea declarație, nu o inventează. Navigația ulterioară folosește
`POSITION_2D` plus `YAW` și nu poate reutiliza un pose F3a fără yaw.

## Limite curente

PA-024F1 a fost verificat cu `FakeInputSink`. PA-024F2 adaugă separat adaptorul
user-mode. PA-024F3a adaugă snapshoturile pure authorization/runtime-arm și
compilerul pentru exact un `MOVE_FORWARD` de maximum `100 ms`; profilul din repo
rămâne inert `pending_evidence`. Nu există runner ori input live în acest slice.

F1 validează componentele, uncertainty și egalitatea spațiului declarat, dar nu
transformă coordonate și nu deduce context de hartă. Delta F3a poate fi
comparată numai în același context continent/zone/map al pachetului; schimbarea
contextului rămâne `INDETERMINATE`. Navigația cross-map/world rămâne blocată.

Operatorul fixed-UI rămâne o capabilitate diferită și nu poate acorda movement.
