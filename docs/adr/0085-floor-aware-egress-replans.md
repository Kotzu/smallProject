# ADR 0085: Replanare egress păstrează nivelul vertical verificat

## Context

O cerere Detour fără `stop_z` este compatibilă cu drumurile 2D, dar într-o
structură cu scări sau podele suprapuse poate rezolva aceeași coordonată X/Y pe
un nivel greșit. În proba Crypt, după prima coliziune, replanarea către anchor
nu mai cerea înălțimea ieșirii și putea transforma drumul pe scări într-o linie
pe podeaua interioară.

## Decizie

Runner-ul citește `requested_stop.z` din corridor-ul verificat și îl transmite
la replanările de coliziune și recenterizare. Picioarele temporare de clearance
transmit și ele înălțimea propriilor ancore. Când corridor-ul nu are un
`requested_stop`, valoarea rămâne `None`, iar contractul 2D existent nu se
schimbă.

Nu se adaugă coordonate de Crypt în cod și nu se folosește server truth pentru
decizie; înălțimea vine numai din rezultatul navmesh-ului local și rămâne
bounded de contractul worker-ului.

## Dovezi

- `tests/test_movement_engine.py`: verifică păstrarea `requested_stop.z` și
  transmiterea sa în replanare.
- `tests/test_client_navigation_runtime.py` și `tests/test_movement_engine.py`:
  `293 passed` după schimbare.
- Suita completă: `1424 passed`; `compileall` fără erori.
- Query local cu blocker-ul observat în proba live: `complete=true`, `20`
  puncte, start Z `121.358002`, stop Z `141.939575`, fără poligoane excluse;
  traseul urcă pe aceeași scară verificată de client.

## Consecințe

Replanarea nu mai pierde scările atunci când apare o coliziune. Drumurile
exterioare rămân 2D când nu există dovadă verticală. O probă offline nu este
declarată automat drept succes live; este necesară o singură probă bounded și
filmata după verificările locale.
