# ADR 0030 — Demonstrațiile manuale sunt prior-uri de navigație, nu rute executabile

## Context

Editorul extern are atlasul Tirisfal calibrat exact din `WorldMapArea.dbc`, dar
operatorul trebuie să poată demonstra rapid un traseu greu: ieșire din criptă,
scări, porți, interior de clădire ori orientarea corectă într-un viraj. Un șir
desenat cu mouse-ul nu păstrează felul în care personajul a parcurs geometria.

## Decizie

Movement Engine oferă un recorder read-only. După `START`, operatorul conduce
personajul normal în client, iar recorderul citește numai HUD-ul vizibil cu
coordonate proprii. Eșantioanele sunt convertite prin aceeași transformare
`tbc243_client_world_xy` / `WorldMapArea.dbc:Tirisfal` folosită de atlas și de
planner.

- un punct este păstrat după minimum `0.75 yd`, pentru a elimina jitter-ul;
- facing-ul este tangenta deplasării înainte, nu o valoare inventată;
- un salt de peste `15 yd` sau lipsa observației peste `2 s` refuză conectarea;
- traseul live apare pe atlas, iar `STOP` îl importă drept
  `manual_demonstration` cu `execution_authority=false`;
- săgețile de sens sunt desenate separat de coridorul Detour;
- recorderul nu armează și nu emite input.

Pentru ca tangenta să reprezinte facing-ul real, demonstrația se face mergând
înainte și orientând camera/personajul cu RMB. Strafing-ul ori backpedal-ul pot
fi demonstrații legitime de locomoție, dar nu sunt folosite drept adevăr absolut
despre yaw fără un senzor separat verificat pentru clientul 2.4.3.

## Consecințe

Plannerul poate trata demonstrația ca preferință de cost și ca exemplu pentru
învățare, dar trebuie să confirme traversabilitatea prin navmesh și observații
curente. Poate devia de la traseu, îl poate inversa semantic și îl poate ignora
dacă apare un obstacol. Astfel editorul accelerează predarea rutelor dificile
fără a transforma Predator într-un follower de coordonate hardcodate.

Excepția strictă este o contradicție dovedită: clientul a confirmat coliziunea,
dar navmesh-ul continuă să ofere o coardă completă prin același obstacol. Atunci
o demonstrație continuă din același build poate deveni dovadă pozitivă de
suprafață locală traversată. Se consumă numai de lângă poziția curentă până la
prima reintrare apropiată în ruta autonomă și numai pentru celulele de coliziune
intersectate. Nu stabilește destinația, nu înlocuiește A* global și nu se aplică
unei rute fără contradicție confirmată.
