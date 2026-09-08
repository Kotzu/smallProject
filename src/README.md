# Source module boundaries

Fiecare folder este un package independent și comunică prin contractele versionate din `contracts/`. `brain` nu importă conectori de joc/web, `journal` nu execută acțiuni, iar `supervisor` nu scrie direct în Stable/Champion.

Implementarea începe cu `adapter`, `observer`, `memory`, `telemetry`, `replay`, `lab` și proiecția read-only `journal`. `brain/read_only.py` este numai un decision stub explicabil; nu există execution gateway în M0/M1.

Entrypoint-ul vertical slice este `perfect_assassin.application.observer_slice.RunObserverFixture`. El acceptă numai fixture sintetic validat și produce JSONL + Journal Markdown în directoarele runtime ignorate de Git.

`perfect_assassin.pose` transformă măsurători vizuale calibrate în `PoseObservation` și combină numai observații client-eligible în `PoseEstimate`. Modulul nu importă captură Windows, pixeli, server, movement sau execution; camera și body pose rămân componente independente.
