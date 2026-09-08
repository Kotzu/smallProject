# ADR-0126 — Bounded decoder pentru alpha-map ADT comprimat

## Context

Unele dale `Sunwell5ManFix` din clientul TBC `2.4.3.8606` folosesc alpha-map
comprimat în secțiunea MCAL. Parserul îl respingea ca necunoscut, deși datele
clientului sunt valide.

## Decizie

Decodăm doar formatul RLE bounded folosit de MCAL: octetul de control indică
un bloc repetat sau literal. Ieșirea trebuie să aibă exact `4096` octeți;
blocurile zero, trunchiate sau mai mari decât limita sunt respinse. Nu există
fallback la date inventate și nu se modifică asset-urile originale.

## Dovezi

Testul unitar pentru alpha-map comprimat trece. Bake-ul offline Sunwell trece
`64/64` ADT și `64/64` nav tiles; validatorul geometric independent trece
`64/64`, cu `0` eșecuri. Diagnosticele Recast rămân raportate în audit și nu
devin automat dovadă de rută autonomă.
