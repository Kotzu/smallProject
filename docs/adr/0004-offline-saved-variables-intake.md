# ADR-0004 — Offline SavedVariables pentru intake-ul TBC 2.4.3

- Status: Accepted
- Date: 2026-08-22
- Scope: M1 / PA-017

## Context

M1 are nevoie de observații client-legitime, fără server ground truth și fără să introducă prematur execution, DLL injection, packet interception sau un canal live greu de auditat. Clientul local este un build candidat 2.4.3, iar verificarea live nu a avut încă loc.

## Decision

Folosim un addon read-only `Interface 20400` care lasă clientul WoW să persiste un buffer limitat în `SavedVariables`. Importul are loc offline, după oprirea clientului. Fișierul este tratat ca input neîncrezut și este citit de un parser data-only, nu executat ca Lua.

Adapterul acceptă numai schema `0.1`, targetul `tbc_243_lab`, event formatul `tbc243-legacy-v1` și un allowlist de câmpuri. Combat log-ul legacy este arhivat brut și exclus din ObservationEnvelope până la verificarea fiecărui payload.

## Consequences

- Câștigăm auditabilitate și reproducere deterministă fără control al jocului.
- Nu avem încă telemetry live; datele apar la logout/reload.
- Evenimentele pot lipsi dacă clientul se închide anormal înainte de persistare.
- Un controlled-live probe este obligatoriu înainte de `lab_integrated`.
- Viitorul adapter Anniversary poate păstra același port intern, cu alt collector/parser mapping.

## Rejected for PA-017

- memory reading sau DLL/injection;
- packet capture/proxy;
- server database/GM/playerbots relay pentru input de decizie;
- `SendAddonMessage` ori chat ca transport;
- interpretarea payload-ului modern peste combat log-ul 2.4.3;
- conectarea addon-ului la execution.

## Rollback

În workspace: revert la commit-ul Stable anterior. După un deploy viitor: client oprit, verificare path exact și eliminarea exclusivă a folderului addon; exporturile runtime nu sunt migrate în Champion identity automat.
