# ADR-0095 — Reluarea unei felii după expirarea armului F4a

## Context

Verificările offline pot termina un traseu întreg într-un singur proces, dar
un client live folosește un arm F4a scurt și o revalidare de realm separată.
Într-o secvență semantică, primul copil putea ajunge la o destinație și al
doilea copil primea din nou fișierul deja expirat. Rezultatul live era astfel
`RUNTIME_ARM_EXPIRED`, deși planificarea și WorldPack-ul erau valide.

## Decizie

Supervisorul poate fi pornit explicit cu
`--resume-on-runtime-arm-expiry` împreună cu un
`--runtime-arm-wait-seconds` pozitiv și limitat. După expirare:

1. copilul a eliberat deja toate tastele și mouse-look-ul;
2. supervisorul transmite o singură dată checkpoint-ul copilului prin
   `--resume-result`;
3. următorul copil face din nou preflight read-only și așteaptă un arm F4a nou;
4. dacă operatorul nu înlocuiește armul în fereastra bounded, rularea se oprește
   fail-closed.

Supervisorul nu emite, nu reînnoiește și nu prelungește autorizația. Checkpoint-
ul nu este păstrat după un status diferit sau după o tranziție la altă
destinație. Numărul total de felii rămâne limitat de
`--maximum-navigation-cycles`.

Control Center folosește această opțiune cu o așteptare de 120 de secunde; asta
doar lasă loc operatorului să emită manual revalidarea și armul aprobate. Nu
există rearmare ascunsă și nu se schimbă limitele de input, combat sau client.

## Consecințe

Expirarea nu mai abandonează automat o secvență validă atunci când operatorul
poate furniza armul nou, iar poziția de reluare este cea observată de client.
În același timp, un fișier vechi, lipsa unui checkpoint sau lipsa armului nou
rămâne un stop fail-closed. Dovada este o reluare bounded, nu o confirmare de
autonomie live.
