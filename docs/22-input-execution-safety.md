# 22 — Input execution safety

## Outcome

Perfect Assassin va controla clientul LAB printr-un actuator user-mode simplu și transparent. Nu încercăm să facem inputul automat să pară hardware. Rogue-ul va arăta natural deoarece Movement Brain controlează bine traiectoria, nu pentru că transportul ascunde sursa evenimentelor.

```text
MovementGoal
  -> Path corridor
  -> PA-MPPI trajectory
  -> short MovementPrimitive
  -> Safety/Policy Gateway
  -> Win32 SendInput authorized-target adapter
  -> observed effect
  -> recalibrate/replan
```

## Responsabilități separate

### PA-MPPI

- decide direcția, curba, viteza și durata;
- anticipează players/mobs și target movement;
- minimizează jerk, oscillation, tapping și overshoot;
- emite o singură propunere scurtă, cu deadline.

### MovementPrimitiveCompiler

- transformă traiectoria în key/button state transitions;
- păstrează body turn și camera turn separate;
- nu trimite input;
- produce un artifact reproductibil pentru replay.

### Execution Gateway

- aplică target policy și execution mode;
- verifică focus, HWND/process fingerprint, pose freshness și safety state;
- arbitrează manual input versus Predator;
- aprobă sau respinge fiecare primitive;
- comandă `release_all` la orice fail-safe.

### Win32SendInputAdapter

- trimite numai primitive aprobate;
- folosește keyboard scan codes și relative mouse motion;
- menține ledger-ul tastelor apăsate;
- raportează exact succes/failure și timestamps;
- nu citește jocul și nu conține tactică;
- nu rulează pe targeturi pending, necunoscute sau public live.

## State machine

```text
DISABLED
   -> ARMED           operator + LAB policy + exact target
   -> EXECUTING       fresh authorized primitive
   -> YIELDING        physical/manual input detected
   -> MANUAL          release_all complete

Any state
   -> FAIL_SAFE       focus/process/pose/watchdog failure
   -> DISABLED        release_all + audit
```

Revenirea din `FAIL_SAFE` nu este automată. Necesită un nou arm token bounded.

## Test order

1. contract tests: primitive, deadline, ownership și policy;
2. fake input sink: order, duplicate key-down, missing key-up, cancellation;
3. dummy local window: foreground/focus loss și emergency stop;
4. deterministic replay: proposed versus authorized versus observed;
5. bounded LAB course fără combat;
6. crowd replay și recovery;
7. numai după gates: Journey movement cohort.

## Gates înainte de LAB

- zero input pentru target necunoscut, pending sau public live;
- zero input dacă realm fingerprint-ul ori executable hash-ul nu este allowlisted;
- zero input în `OBSERVE_ONLY`, `MANUAL` sau pose `LOST`;
- `release_all` idempotent și verificat la fiecare failure path;
- stale primitives sunt respinse;
- target window mismatch este fail-closed;
- operator input câștigă arbitration;
- watchdog independent poate opri executorul;
- telemetry nu conține secrete și separă clar proposal de execution.

## Ce nu evaluăm

- kernel/VHF/device spoofing;
- memory/process injection;
- bypass sau anti-cheat evasion;
- timing randomizat pentru a evita clasificarea;
- rulare autonomă pe orice `public_live` oficial, Classic/legacy sau retail;

## Ce măsurăm pentru fluiditate

- input-to-observed-motion latency;
- key-hold și yaw-response calibration;
- curvature/yaw-rate/jerk distributions;
- micro-correction și oscillation rate;
- stop distance și range overshoot;
- camera/body coupling;
- stuck/recovery și manual intervention rate.
