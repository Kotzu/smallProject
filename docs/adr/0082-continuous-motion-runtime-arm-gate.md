# ADR-0082 — Arm separat pentru mișcare continuă

## Context

Runnerul de navmesh ținea W/A/D și RMB prin `WindowsContinuousMotionSession`,
dar pornea direct din autorizația fixed-UI. Acea autorizație permite doar
captură, HUD și controlul vizibil al ferestrei. Nu este o permisiune pentru
mișcare.

## Decizie

Navigația folosește `ContinuousMotionExecutionGateway`. Gateway-ul cere un arm
F4a separat, cu binding pentru procesul WoW, ceasul monotonic, hash-ul
autorizației aprobate și hash-ul receipt-ului exact. Arm-ul permite doar
`MOVE_FORWARD`, `MOVE_BACKWARD`, `STRAFE_LEFT` și `STRAFE_RIGHT`, ține lease-ul
scurt și este revocabil. Un fișier fixed-UI sau arm-ul F3a single-pulse este
respins.

Issuerul F4a este separat de runner și cere ack-ul operatorului; arm-ul mai
cere receipt-ul exact și o revalidare de realm proaspătă. Până când aceste
fișiere există pentru procesul curent, runnerul se oprește înainte de orice
input de mers. Nu se inventează `approval` și nu se pornește live cu
autorizația de UI.

## Consecințe

- Testele offline pot verifica poarta și binding-urile fără client.
- Un test live următor are nevoie de trei fișiere noi: autorizația F4a, arm-ul
  scurt și revalidarea de realm pentru procesul curent.
- Combatul rămâne pe arm-ul lui separat; acest ADR nu îi acordă autoritate.
