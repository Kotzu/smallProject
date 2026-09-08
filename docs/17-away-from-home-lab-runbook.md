# 17 — Away-from-home LAB runbook

Acest runbook este pentru probele în care utilizatorul a autorizat explicit operarea clientului, dar nu este la calculator. El automatizează numai tranzițiile repetitive; deciziile despre ecran rămân la operatorul care inspectează checkpoint-ul.

## Boundary

```text
Codex / human LAB operator
        ↓ bounded phase + visual checkpoint
External LAB client operator harness
        ↓ keyboard/mouse to local client
TBC 2.4.3 client

Predator Brain: OBSERVE_ONLY
```

Nu se folosesc server DB coordinates, hidden unit state sau alte informații pe care clientul/addonul nu le-ar putea cunoaște pentru deciziile Predatorului.

## Start and login

Clientul legacy refuză explicit Remote Desktop. `Launch` verifică sesiunea și se oprește înainte de pornire dacă operatorul rulează prin RDP. Pentru o probă vizuală, Codex/operatorul și clientul trebuie să fie în sesiunea Windows local-console; faptul că RDP este doar deconectat nu garantează că procesul existent a migrat în console session.

From `E:\WoWserver\PerfectAssassin-Workspace`:

```powershell
.\scripts\Invoke-LabClientOperator.ps1 -Action Status
.\scripts\Invoke-LabClientOperator.ps1 -Action Launch -AcknowledgeClientRisk
.\scripts\Invoke-LabClientOperator.ps1 -Action Capture
```

`Launch` creează un receipt de identitate LAB cu durată limitată, legat de PID,
HWND, build, hash, actorul configurat și realm-ul așteptat. Assurance-ul realm
din receipt descrie verificarea făcută la launch; fiecare input reface
verificarea listenerelor/configurațiilor curente și a înregistrării sanitizate
de routing (`realm ID/address/port/build`) pe care auth serverul o livrează
clientului. Acest query este gate de target, nu sursă pentru deciziile
Predatorului. Receipt-ul nu acordă drept de input. Inspect the latest
checkpoint. Continue only if it visibly shows the TBC login screen, apoi
armează explicit sesiunea bounded:

```powershell
.\scripts\Invoke-LabClientOperator.ps1 -Action ArmSession -AcknowledgeRuntimeArm
.\scripts\Invoke-LabClientOperator.ps1 -Action Login -ConfirmedVisualState LoginScreen
.\scripts\Invoke-LabClientOperator.ps1 -Action Capture
```

Ordinea obligatorie este `Launch → ArmSession → input bounded`. Arm-ul expiră cel
mai târziu la limita `approval.max_session_minutes`, nu poate depăși plafonul
absolut de 60 minute și nu supraviețuiește receipt-ului de launch. Profilul
curent are `permitted_modes=[]` și autorizează separat numai capabilitatea
auxiliară `LAB_OPERATOR_FIXED_UI`; aceasta nu acordă movement/combat.
`Status`, `Launch`, `Capture` și `Import` nu cer arm;
orice acțiune care emite keyboard, mouse, console text sau resize îl reverifică.
În interiorul unei acțiuni, fiecare token text rămâne legat de același nonce,
hash și expiry al arm-ului și de un deadline monotonic; un credential prea lung
este refuzat înaintea primului click.

Inspect the checkpoint and verify realm `MaNGOS`, character `Predator`, level/class/location and no unexpected dialog. Then:

```powershell
.\scripts\Invoke-LabClientOperator.ps1 -Action InspectAddons -ConfirmedVisualState CharacterSelect
.\scripts\Invoke-LabClientOperator.ps1 -Action EnterWorld -ConfirmedVisualState CharacterSelect
.\scripts\Invoke-LabClientOperator.ps1 -Action Capture
```

`InspectAddons` este o fază read-only bounded: deschide lista, salvează checkpoint-ul și o închide cu Escape fără a schimba checkbox-uri.

## Probe rules

- define the probe card before world actions;
- keep the action set short and reversible;
- capture before and after quest acceptance, loot, death, level-up or another promotion-relevant event;
- stop if target/UI/location cannot be visually reconciled;
- never claim movement/combat success from elapsed time or keypresses alone;
- never convert external operator input into Champion memory or Predator decision evidence.

Pentru gate-ul explicit al contextului de hartă, după o captură care confirmă `InWorld`:

```powershell
.\scripts\Invoke-LabClientOperator.ps1 -Action OpenWorldMap -ConfirmedVisualState InWorld
# inspectează checkpoint-ul și confirmă că world map este deschis
.\scripts\Invoke-LabClientOperator.ps1 -Action CloseWorldMap -ConfirmedVisualState WorldMapOpen
# inspectează checkpoint-ul și confirmă revenirea în world
```

Aceste două acțiuni trimit exclusiv tasta implicită `M`, o singură dată, și produc checkpoint înainte/după. Nu sunt acțiuni de movement și nu aparțin Predator Brain.

Pentru matricea controlată de calibrare HUD există numai două valori explicite de UI scale și două dimensiuni fixe de fereastră:

```powershell
.\scripts\Invoke-LabClientOperator.ps1 -Action SetUiScale80 -ConfirmedVisualState InWorldChatClosed
.\scripts\Invoke-LabClientOperator.ps1 -Action ResizeWindowCompact -ConfirmedVisualState InWorld
# rulează proba HUD și inspectează checkpoint-ul
.\scripts\Invoke-LabClientOperator.ps1 -Action ResizeWindowBaseline -ConfirmedVisualState InWorld
.\scripts\Invoke-LabClientOperator.ps1 -Action SetUiScale100 -ConfirmedVisualState InWorldChatClosed
# rulează proba explicită la 1.0, apoi revino la setarea implicită a clientului
.\scripts\Invoke-LabClientOperator.ps1 -Action RestoreUiScaleDefault -ConfirmedVisualState InWorldChatClosed
```

Acțiunile nu acceptă comenzi console ori dimensiuni arbitrare. `SetUiScale100` păstrează `useUiScale=1`, deci verifică realmente valoarea explicită `1.0`; `RestoreUiScaleDefault` dezactivează apoi override-ul. Profilul inițial trebuie restaurat chiar dacă proba intermediară eșuează; fiecare tranziție produce checkpoint și audit.

`InWorldChatClosed` înseamnă că checkpoint-ul imediat anterior a fost inspectat și câmpul de chat nu este activ. Helperul refuză comenzile console și logout cu simplul label `InWorld`, astfel încât un text rămas în chat să nu poată schimba sensul secvenței fixe.

Pentru a reîncărca addonurile fără logout și fără a scoate personajul din
world, inspectează mai întâi un checkpoint care confirmă `InWorldChatClosed`, apoi:

```powershell
.\scripts\Invoke-LabClientOperator.ps1 -Action ReloadUi -ConfirmedVisualState InWorldChatClosed
```

Acțiunea trimite numai comanda canonică TBC 2.4.3 `/console reloadui`, așteaptă
cinci secunde și salvează checkpoint stabil înainte/după. Nu ne bazăm pe aliasul
retail `/reload`. Acțiunea nu face logout, nu închide clientul și nu acceptă o
comandă de la apelant. Checkpoint-ul final trebuie inspectat; auditul rămâne
`requires_visual_verification` chiar dacă inputul a fost trimis.

The current harness intentionally offers no movement, target, combat or generic slash-command action. Those remain manual controlled probes until the execution gateway and visual state estimator exist.

## Normal save, exit and import

After inspecting a checkpoint that proves the character is in-world and out of combat:

```powershell
.\scripts\Invoke-LabClientOperator.ps1 -Action Logout -ConfirmedVisualState InWorldChatClosed
.\scripts\Invoke-LabClientOperator.ps1 -Action Close
.\scripts\Invoke-LabClientOperator.ps1 -Action Import
```

`Close` normal elimină atât runtime arm-ul, cât și launch receipt-ul. Pentru a
lăsa clientul deschis fără autoritate de input, rulează `-Action DisarmSession`;
înainte de un `Close` ulterior trebuie creat un arm nou cu acknowledgement
explicit.

Inspect the generated Journal and reconcile every promotion-relevant event with the screenshots. Generated screenshots, audit, telemetry and Journal are local runtime evidence and remain ignored by Git.

## Fail closed

If the UI differs from the expected state, capture it, rulează `-Action
DisarmSession` și stop. The harness has no forced close and does not retry
credentials, delete characters, accept quests or continue combat by itself.
Diagnose first, then create a new bounded probe card.
