# Probă reversibilă: navigator separat de producătorul grafului

Rezultat ulterior: proba candidatului s-a încheiat ARRIVED, calitate FAIL.
Runtime revenit la v34 fără flag, gate restaurat byte-exact. Separarea
rolurilor rămâne opt-in; nu reprezintă promovarea corecției geometrice.
Raport: `../LIVE_CORNER_CANDIDATE_REJECTION_2026-09-06.md`.

Graful existent rămâne imuabil și verificat cu executabilul v34 care l-a
produs. Candidatul `7015e3f` schimbă numai calculul traseului, nu proveniența
grafului. Nu rescriem hash-ul grafului pentru a-l potrivi cu un executabil nou.

CC acceptă explicit `--horizontal-clearance-candidate` numai pentru artefactul
cu SHA256 `ca2b19def8517afbdad9ded7facde66e7e86d74182744a426a527f03db7935f3`.
Lansarea normală rămâne v34. Supervisorul transmite separat navigatorul și
`--structure-probe-worker`; acesta din urmă este hash-uit din fișierul real,
iar validarea integrală a grafului rămâne neschimbată. Serviciul read-only
publică identitatea navigatorului pentru gate, dar validează graful cu v34.

Gate-ul temporar se construiește prin API-ul existent din validarea completă
finală arhivată: șase cazuri PASS, 529 etape, hash-ul artefactului și al
executabilului reverificate. Nu se repetă inutil aceleași interogări offline.
Identitatea WorldPack/profil/client trebuie să coincidă. Autorizarea runtime,
armarea și preflight-ul CC nu sunt ocolite.

Verificări: 255 teste movement engine, 22 supervisor, 100 client navigation
runtime și 7 teste noi de separare a rolurilor/opt-in/hash/refuz implicit.
Sunt dovezi offline, nu aprobare humanlike. Singura modificare geometrică
rămâne candidatul restrâns pentru colțuri comune orizontale.

Rollback: închiderea CC candidat, restaurarea copiei gate-ului v34 și
relansarea normală. Nu se suprascrie executabilul v34, WorldPack-ul, graful
sau shortcut-ul. La final se consemnează rezultatul și revenirea/promovarea;
ARRIVED singur nu justifică Stable.

## Istoric: stare după pregătire, înaintea probei

Commit `922f160`. Gate candidat verificat cu API-ul existent; gate v34 salvat
byte-exact în `live-evidence/20260906-corner-candidate/gate-before-live-trial.json`.
CC candidat pornit explicit, graph worker v34 verificat în comanda serviciului.
Client autentificat de operator, intrare în world, reset canonic, godmode și
stay-online confirmate. Deathknell selectat și 21 citiri staționare BINE.
Nicio pornire a navigației/supervisorului. Filmarea nu a început: NVIDIA cere
activarea capturii desktopului. Cererea rămâne pentru operator; nu este
ocolită și nu se execută mers nefilmat. Candidatul rămâne temporar, oprit.
