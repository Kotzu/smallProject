# PA-024F3a — First controlled-live proven displacement

- Status: `PASS — PROVEN_DISPLACEMENT`
- Date: 2026-08-24
- Scope: local TBC 2.4.3 LAB clone only

## Outcome

Predator executed exactly one `MOVE_FORWARD` primitive with a `100 ms` key-hold
inside a `150 ms` execution envelope. The pre/post client-visible HUD
observations stayed in continent `2`, zone `25`, on the same actor, process,
session, authorization and profile.

- run: `run:f3a:c6c20233-84c9-40c3-9071-2fe25f91d114`;
- authorization SHA-256:
  `0CDF77CF44AFFA851E25F8F5CC5DE436294E87FC1CBA27585FF52F4E23CD228D`;
- movement arm SHA-256:
  `53B6C58B697057C620CB3ED80C6E3795988F76642E6AA172C69B1A4A672AA648`;
- execution result: `EXECUTED / EXECUTED`;
- pre: `(0.2946059357595178, 0.6465247577630274)`, sequence `214`;
- post: `(0.2946822308690013, 0.6462958724345770)`, sequence `218`;
- delta: `dx=0.00007629510948348184`,
  `dy=-0.0002288853284504455`;
- measured distance: `0.00024126632029971526`;
- combined 95% quantization radius: `0.00002157951571485611`;
- conservative proven lower bound: `0.00021968680458485916`.

Distance exceeded the combined uncertainty by more than an order of magnitude.
The result is therefore a measured displacement, not an inferred animation or
key-send claim.

## Evidence

- result JSON:
  `data/runtime/movement-f3a/results/single-forward-pulse-c6c20233-84c9-40c3-9071-2fe25f91d114.json`;
- result SHA-256:
  `BABB02D1C7BC7B8A72FABF07CDAE6AC3B797ACE844A9DB66B8F4FCD393EAAC82`;
- pre observation SHA-256:
  `00129CD052299AA5CD5EB3B91F06DEEAAEFD753C1FCBE6E639F1FC6CDE450A11`;
- post observation SHA-256:
  `50471D10BB52E15F7D97FC7434FBEE86FE30AB754D6490B9E6C3FE462756CEEF`;
- post-run visual checkpoint:
  `data/runtime/operator/20260824T081201962Z-manual-checkpoint.png`;
- checkpoint SHA-256:
  `377C59793E63C684E2D289F652CB5E0739D6761EFB205EFEC86CEA6E291F987C`.

The visual checkpoint shows Predator still in-world in Deathknell, chat closed,
HUD position `X 0.29468 / Y 0.64629`, and the client message `You are no longer
AFK.` The character was not logged out or closed.

## Fail-closed and cleanup evidence

Four earlier composition attempts stopped before the input sink because of
contract mismatches: actor evidence-ref scope, canonical UTC precision, full
build signature, and the execution-specific HUD profile gate. Each returned a
non-authority failure/result with `execution_result=null`; no pulse was sent.

The successful run ended with:

- `arm_disarmed=true`;
- `gateway_closed=true`;
- `manual_takeover_disarmed=true`;
- `release_faulted=false`;
- fixed-UI runtime arm absent;
- movement runtime-arm file count `0`.

The active LAB server has `Player.AFK.DisconnectTimeout = 0`; AFK disconnect is
disabled server-side and no blind anti-AFK movement loop is needed.

## Verification

- focused current-source execution/capture/operator suite: `262/262 PASS`;
- PowerShell parser: PASS;
- Python compile: PASS;
- `git diff --check`: PASS, apart from expected line-ending warnings.

The full discovery suite was not run after the live proof because three
environmental installer/operator tests intentionally require `Wow.exe` to be
closed. Predator remains open by operator request.

## Boundary and next gate

This proves one bounded forward displacement and its complete cleanup. It does
not yet prove heading control, route following, obstacle avoidance or quest
navigation. The next movement gate is closed-loop turn/forward calibration,
then a two-point route backed by the client-asset navmesh and per-actor
Experience Map.
