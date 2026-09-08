# ADR-0112: Auditul registry-ului acceptă queue-uri candidate multiple

## Context

Fiecare WorldPack candidat are propriul bake queue. Când auditul combină mai
multe rădăcini imutabile, referința text concatenată poate depăși limita veche
de 320 de caractere chiar dacă fiecare referință individuală rămâne bounded.

## Decizie

Schema auditului permite `queue_reference` concatenat până la `8192` de
caractere, iar `queue_references[]` păstrează limita de `320` pe element și
limita de `32` queue-uri. Scriptul continuă să verifice fiecare queue și să
aleagă doar starea cu rang mai bun; conflictele la același rang rămân erori.

## Dovezi

- testul adaugă patru queue-uri imutabile și validează recordul;
- auditul Monastery combinat raportează `35` mapări și `8` complete;
- schimbarea este doar de contract/audit, fără autoritate de execuție și fără
input live.

## Consecințe

Candidate-urile noi pot fi urmărite în același audit fără a copia sau rescrie
queue-urile existente. Registry-ul runtime nu este modificat automat.
