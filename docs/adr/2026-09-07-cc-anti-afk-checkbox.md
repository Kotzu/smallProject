# Anti-AFK controlabil din CC

## Decizie

Bifa Anti-AFK este în antet, independentă de acordul pentru mers și de controlul
manual Codex. Nu schimbă algoritmul guardului sau execuția inputului. Folosește
scripturile existente, cu rădăcină explicită și maximum 24 h per pornire.
Debifarea cere oprire cooperativă și elimină opțiunea locală de autostart.
Închiderea CC păstrează guardul independent; validarea identității, observației
AFK și autorizației continuă să limiteze orice Space. CC nu prelungește limita
guardului și nu îl repornește continuu după expirare.

Un worker separat gestionează procesele și citirea stării. Tk primește rezultate
prin coadă, cu numărul comenzii pentru a respinge rezultate anterioare clickului.
Starea verifică PID, calea exactă a scriptului, timpul de creare și prospețimea
datelor. Proces prezent nu înseamnă automat observație AFK validă sau input permis.
Lansatorul nu folosește pipe-uri capturate care pot rămâne moștenite de procesul
de fundal. Identitatea/armarea și excluderea mișcării rămân în guard/gateway.

Windows PowerShell: rădăcina implicită se rezolvă în corpul scriptului, iar
stop.request folosește UTF-8 compatibil cu 5.1. Nicio parolă/configurație privată
nu intră în această modificare.

## Verificare și limite

- 23 teste Anti-AFK/control și 255 teste movement_engine trecute.
- Corectat testul structural vechi care presupunea constructor CC fără parametri;
  constructorul cu parametri exista deja în HEAD anterior acestei schimbări.
- Verificare vizuală CC și adoptarea guardului manual fără dublare.
- Prima probă start/stop a identificat și eliminat așteptarea pe pipe-uri moștenite.
- Repetare finală din bifa UI: STOPPED cu opțiunea eliminată, apoi RUNNING,
  observație AFK validă și opțiune 24 h salvată. Butoanele de mers rămân vizibile;
  poziția afișată 1809.58, 1592.79, motorul oprit. Fără AFK forțat în această probă.
- Nu reprezintă test de anduranță 24 h și nu revalidează mersul/sonarul/combatul.

## Rollback

Revenire numai la modificările acestui ADR față de baza 1cd6a75. Guardul și
scripturile pot fi folosite manual în continuare; dezactivarea din CC oprește
cooperativ serviciul. Nu modifica v34 sau telemetria/addonul pentru rollback UI.
