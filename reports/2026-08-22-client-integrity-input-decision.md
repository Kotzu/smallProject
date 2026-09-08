# Client integrity/input decision — 2026-08-22

## Outcome

- Havok și orice produs peste USD 500 sunt eliminate din roadmapul curent.
- Client memory read/write, process/DLL/packet injection și kernel/virtual-HID input sunt interzise.
- Inputul viitor folosește un adapter Win32 `SendInput` user-mode, auditat și target-allowlisted.
- Emulatorul poate fi local/LAN/remote; adresa nu înlocuiește fingerprint-ul și approval-ul.
- Classic/TBC PTR poate fi activat numai după evidence intake redactat și exact client/realm fingerprint; orice `public_live` oficial, Classic/legacy sau retail, rămâne denied.
- PA-024B1 continuă read-only; nicio mișcare live nu a fost activată.

## Motiv

Kernel/HID nu îmbunătățește Movement Brain și adaugă un risc disproporționat. Fluiditatea trebuie obținută prin pose fusion, motion calibration, PA-MPPI, feedback și recovery. `SendInput` este suficient ca transport determinist pentru un target autorizat și poate fi izolat curat în spatele Execution Gateway.
