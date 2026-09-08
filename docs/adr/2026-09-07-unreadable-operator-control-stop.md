# Comanda operatorului inaccesibilă trebuie să oprească și să păstreze raportul

## Incident

În proba filmată crypt-summary-index-live/crypt-c09-20260907-164532.mp4,
după parcurgerea segmentului, citirea movement-engine-control.json a ridicat
PermissionError. Nu este dovedit ce proces a ținut fișierul. Excepția nu era
convertită în OperatorStopRequested; supervisorul a raportat CHILD_ERROR și
nu s-a produs rezultatul final de navigație. Filmul/watchdog-ul au rămas.

## Corecție separată de optimizarea memoriei

read_operator_command convertește orice OSError de citire în oprire explicită
cu motivul „unreadable”; cazul missing își păstrează motivul existent.
checkpoint eliberează mișcarea și când comanda este absentă/invalidă/inaccesibilă.
Nu reîncearcă folosind RUN vechi, nu ignoră eroarea și nu acordă autoritate.
Handlerul existent OperatorStopRequested din runner eliberează inputul și
salvează rezultatul. PAUSE continuă să țină inputul eliberat și nu reia mersul
dacă citirea eșuează.

Teste noi: PermissionError și OSError la checkpoint, eliberare exact o dată,
fără retry; eroare în PAUSE fără resume. Schimbarea este fail-closed și nu
modifică planificarea, camera sau inputul normal. Baza anterioară: 7fe2ea1.
Validarea prin injecție de eroare este offline; o probă normală live nu
reproduce automat incidentul de acces la fișier.
