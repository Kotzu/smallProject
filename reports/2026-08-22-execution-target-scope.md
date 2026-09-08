# Execution target scope — 2026-08-22

## Outcome

- restricția de produs `localhost only` a fost eliminată;
- executorul acceptă emulator local/LAN/remote numai prin exact target allowlist;
- LAN/remote au momentan numai `configured_endpoint_only`,
  `permitted_modes=[]` și capabilități read-only; inputul remote cere un viitor
  adapter de assurance mai puternic;
- Classic/TBC PTR are scope separat `pending_evidence`;
- orice `public_live` oficial, Classic/legacy sau retail, este deny-by-construction;
- memory read/kernel/injection rămân indisponibile peste tot;
- emulatorul curent are capabilități read-only și
  `LAB_OPERATOR_FIXED_UI`, cu `permitted_modes=[]`; helperul finit cere runtime
  arm, are plafon absolut de 60 minute (profilul poate cere mai puțin), iar
  movement rămâne închis până la Execution Gateway-ul dedicat.

## PTR gate

Înainte de activare trebuie introduse build/client/realm fingerprints și o referință la răspunsul Blizzard redactat. Emailul brut, numele, adresele și identificatorii de cont nu intră în Git.

## Evidence

Schema și configurațiile sunt `contract_tested`. Acest rezultat nu este movement live și nu confirmă încă integrarea PTR.

Checkpoint-ul inițial al acestei schimbări a trecut 60 teste. Acesta este un
număr istoric al slice-ului, nu totalul suitei finale a repository-ului; suita
completă se recalculează după toate hardening-urile.
