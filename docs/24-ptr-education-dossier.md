# 24 — PTR education dossier

## Scop

Acest dosar păstrează comunicarea cu platform owner verificabilă și ușor de actualizat, fără a publica date personale sau credentiale.

## Authorization summary

- status: `pending_redacted_evidence_intake`;
- purpose: education, research și transparent video content;
- target: Classic/TBC PTR separat și autorizat, nu niciun realm oficial `public_live` (Classic/legacy sau retail);
- prohibited: herbing, mining, fishing, economy farming/auctioning, memory read/write, injection și kernel/HID;
- execution modes: none până la evidence intake + exact target fingerprint.

## Ce arhivăm local

1. copia redactată a răspunsului platform owner;
2. SHA-256 al copiei redactate;
3. data, reference ID și scope-ul exact;
4. client build/hash și realm fingerprint folosite la test;
5. versiunea Perfect Assassin și commit hash;
6. session manifest, durată și execution modes;
7. video/clip links și rezumatul outcome-ului;
8. lista schimbărilor trimise ulterior către platform owner.

## Ce nu intră în Git

- email complet, nume sau adresă personală;
- Battle.net account/BattleTag dacă nu este deja public și necesar;
- headers cu identificatori sensibili;
- credentiale, cookies sau session tokens;
- telemetry/player identifiers brute.

Repo-ul păstrează numai hash, reference ID, scope și restricții.

## Pre-session checklist PTR

- authorization status `approved_bounded`;
- evidence hash verificat;
- exact client/build/realm match;
- public-live detector negativ;
- gathering/economy intents dezactivate;
- memory/kernel/injection invariants trecute;
- video capture și audit active;
- runtime arm bounded;
- emergency `MANUAL`/`release_all` verificat.

## Post-session update

- stop executor și confirmă `release_all`;
- salvează manifestul și clip markers;
- redactează orice player identifier;
- publică/trimite linkul video conform comunicării stabilite;
- înregistrează feedbackul și orice nouă restricție;
- revocă authorization dacă scope-ul s-a schimbat sau a expirat.
