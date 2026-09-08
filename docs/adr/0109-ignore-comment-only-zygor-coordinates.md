# ADR-0109: Comentariile Zygor nu sunt coordonate de rută

## Context

Ghidurile Anniversary folosesc atât comentarii Lua (`--`), cât și comentarii
moștenite (`//`). Un rând comentat poate conține `|goto`, dar acel text este
instrucțiune pentru cititor, nu un pas activ. Parserul bounded căuta înainte în
blocul întreg și putea atașa o astfel de coordonată instanței greșite.

## Decizie

`route_teacher` elimină liniile care încep cu `--` sau `//` înainte de a căuta
coordonate în pașii moderni sau legacy. Liniile active rămân neschimbate; nu se
execută Lua și nu se păstrează payload-ul ghidului.

## Consecințe

Auditul proaspăt Anniversary are `11.686/11.686` coordonate active transformate
și `0` nerezolvate. O coordonată documentară de Black Temple nu mai umflă ruta
și nu mai cere o transformare 2D inventată. Datele rămân statice, cu provenance,
advisory și fără autoritate de input.
