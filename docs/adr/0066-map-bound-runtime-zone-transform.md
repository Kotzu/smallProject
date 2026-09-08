# ADR 0066 — Transformare runtime legată de mapă și zonă

## Context

Prima felie a Movement Engine folosea direct transformarea Tirisfal pentru
poziția HUD, indiferent de profilul selectat. Asta era corect numai pentru
`Azeroth/Tirisfal` și putea converti greșit o destinație RouteTeacher din
Kalimdor sau Outland.

## Decizie

Runner-ul navmesh rezolvă acum transformarea din catalogul client read-only
`WorldMapArea.dbc` după `map_id` și `zone_index`. Când ID-ul de zonă expus de
HUD nu este identic cu `area_id` din asset (de exemplu Tirisfal `25` versus
`85`), este acceptat numai un nume `atlas_calibration` explicit din catalogul
semantic sau aliasul legacy revizuit Tirisfal/Undercity. Lipsa unei potriviri
unice oprește runner-ul fail-closed.

Control Center citește `zone_index` din catalogul semantic selectat și îl
transmite copilului împreună cu calea catalogului de transformări. Nicio
transformare nu furnizează înălțime, poligoane sau autoritate de execuție;
traversabilitatea rămâne responsabilitatea WorldPack/navmesh.

## Consecințe

Această schimbare elimină reutilizarea implicită a Tirisfal și pregătește
profiluri semantice pentru Kalimdor/Outland, fără a promova hărțile care încă
nu au catalog semantic și structure/access graph complet. Testele offline
acoperă un caz non-Tirisfal (`Kalimdor/Durotar`) și păstrează gate-ul live
inert.
