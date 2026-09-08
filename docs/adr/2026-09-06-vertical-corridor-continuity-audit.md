# Continuitate verticală — opt interogări offline

Folosește numai XY/candidații deja arhivați în `transition-audit-v1.json`.
WorldPack v3 reverificat; workerul v34 folosit read-only, fără reconstruire,
SHA256 `cb3555065c56a40c45c73d929a89bda6f8237fe5ffa2e018fce50fac84821d3d`.
Nu s-au pornit clientul sau probe live. Nu s-a schimbat CC/anti-AFK.

Au fost cerute toate cele patru alternative de la 98s și 99s către singurul
candidat de la 100s (139.313492). Z start/stop sunt parametri expliciți, nu
poziții observate. Tool-ul păstrează și pozițiile efectiv returnate de navmesh.

| Interval | Candidat start Z | Lungime traseu returnat | Complet |
| --- | --- | --- | --- |
| 98→100s | 155.150 | 5.300 yd | nu |
| 98→100s | 141.849 | 13.612 yd | da |
| 98→100s | 120.719 | 81.173 yd | da |
| 98→100s | 141.015 | 13.612 yd | da |
| 99→100s | 152.568 | 0.948 yd | nu |
| 99→100s | 141.851 | 7.200 yd | da |
| 99→100s | 120.719 | 89.124 yd | da |
| 99→100s | 141.538 | 7.200 yd | da |

Nu există shortcut topologic raportat sau blocker nerezolvat în aceste rezultate.
O rută lungă găsită NU demonstrează că nu există o rută mai scurtă ori un salt;
nu s-a impus aici o limită de viteză și nu s-a ales automat etajul. Ruta scurtă
incompletă de pe acoperiș nu trebuie comparată ca succes cu una completă.

Diferența importantă față de o interogare izolată: o continuitate plauzibilă
pe platforma de sus și traseul subteran produc distanțe foarte diferite către
aceeași observație ulterioară. Aceasta susține investigarea unei estimări pe
secvență, condiționată de modul de mișcare și de limite calibrate, nu `nearest Z`.

Deplasarea produsă de proiecție este explicită: la 98s, candidatul 141.015
este mutat la 141.875641, aproximativ 0.861 yd. Candidatul 141.849 ajunge la
același punct, deplasat doar 0.027 yd. Prin urmare o rută returnată nu verifică
automat suprafața solicitată inițial. Stop-ul este mutat cu circa 0.472 yd.
Nu se deduc identități de poligon numai din coincidența punctelor returnate.

Tool general: `tools/audit_vertical_corridors.py`, maximum 12 perechi, timeout
5s per apel al adaptorului existent, hash extern pentru worker, pack verificat.
Inputul arhivat nu este promovat la sesiune live. Rezultate:
`data/runtime/minimap-wmo-probe/corridor-audit-v1.json`.
Pentru reproducere: inputul de tranziție, `--from-second 98 --from-second 99
--to-second 100`, worker v34 cu hash-ul de mai sus, profilul WorldPack v3,
store-root-ul existent, `--map-id 0` și o cale nouă de output.

Pasul următor: dovezi de continuitate per candidat, cu verificarea explicită
a proiecțiilor și păstrarea ramurilor necunoscute; apoi integrare read-only în
CC. Fără praguri de viteză inventate din aceste două intervale. Goal neîncheiat.
Rollback-ul probei nu afectează runtime-ul: tool-ul nu este importat live.
17 teste relevante PASS: raportarea deplasărilor/proiecțiilor, rute incomplete,
shortcut explicit, interval invalid și contractul candidaților verticali.
