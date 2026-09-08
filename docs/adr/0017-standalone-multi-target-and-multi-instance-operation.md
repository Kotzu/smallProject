# ADR 0017 — Operare standalone, multi-target și multi-instance

- Status: accepted
- Date: 2026-08-22
- Scope: deployment, identitate, izolare și operare de la distanță

## Context

Perfect Assassin trebuie să poată continua Predator Journey pe infrastructura
principală și, în paralel, să ruleze scenarii LAB pe alte realm-uri private.
Dezvoltarea inițială folosește un emulator local deoarece este mediul cel mai
ușor de reprodus, nu pentru că produsul ar depinde de `localhost`.

Verificarea exactă a clientului, realm-ului, ferestrei și sesiunii poate părea o
restricție de deployment dacă este confundată cu topologia rețelei. În realitate,
aceasta previne controlarea din greșeală a altei instanțe și face rezultatele
reproductibile. Este un control de identitate și calitate, nu o expresie de
neîncredere în operator.

## Decizie

Perfect Assassin este un produs standalone și nu este blocat pe `localhost`.
Core-ul nu conține adrese de realm, căi de client sau presupuneri despre un
singur server. Sunt targeturi suportabile prin profile versionate:

- emulator local;
- emulator din LAN;
- emulator remote controlat sau un server privat autorizat;
- PTR acoperit de o autorizare specifică și de un profil separat.

Orice `public_live` oficial rămâne în afara scope-ului curent, Classic/legacy
sau retail; numai un PTR separat și autorizat explicit poate fi eligibil.
Schimbarea unui realm eligibil este selecție de `TargetProfile`,
`RealmFingerprint`, adapter și capability
profile; nu cere modificarea Brain-ului și nu cere un fork de cod. Un target nou
trece prin probele de compatibilitate și poate porni `OBSERVE_ONLY` până când
capabilitățile sale de execution sunt validate.

Pentru emulator LAN/remote, assurance-ul disponibil acum este numai
`configured_endpoint_only`; aceste profile au `permitted_modes=[]` și rămân
`OBSERVE_ONLY`/read-only. Un viitor input remote necesită un adapter de assurance
mai puternic, contract și autorizare noi; endpointul configurat nu este suficient.

### Environment identity și actor identity

Cele două identități sunt independente:

```text
Environment identity
  target profile + realm fingerprint + client/build + adapter/capabilities

Actor identity
  Champion sau LAB clone + journey/scenario + memory namespace + policy
```

Același actor poate migra controlat între targeturi compatibile fără a schimba
Brain-ul. Același target poate găzdui mai mulți actori izolați. O schimbare de
realm nu schimbă automat actorul, iar pornirea unei instanțe noi nu moștenește
identitatea Championului.

### Un Champion Journey și N LAB clones

Orchestratorul poate rula simultan:

- o singură identitate canonică `Champion`, care deține Predator Journey și
  progresia level 1–70;
- zero sau mai multe identități `LAB clone`, fiecare cu propriul scenario,
  progres, memorie și evidence namespace.

Championul și clonele pot folosi aceeași versiune Stable de Core și aceeași
bază read-only de cunoștințe semantice. Nu împart memorie mutabilă, opponent
memory, Journal identity, progression state sau rezultate brute. O clonă care
se luptă continuu pe un realm separat produce numai evidence LAB. Un skill
devine disponibil Championului doar prin replay-uri, teste, evaluare și un gate
explicit de promotion; simpla reușită a clonei nu îl promovează.

### Izolare per instanță

Fiecare instanță are propriile:

- `instance_id`, `actor_id` și rol `Champion`/`LAB clone`;
- client root și proces de client;
- PID, HWND și window identity;
- target/realm/capability profile;
- runtime session, runtime arm și approval expiry;
- directoare runtime pentru checkpoints, telemetry, replay, Journal și audit;
- takeover channel și `release_all` state.

`ExecutionTargetAuthorization` v2.0 leagă explicit autorizația de actorul
instanței. `decision_context` se derivă din acel actor binding și nu poate fi
ales liber de probe sau de caller pentru a schimba provenance-ul unui rezultat.
Binding-ul fixează `instance_id`, `actor_role`, `actor_id`, `decision_context`,
`memory_namespace`, `expected_character_name`, `credential_alias` și
`binding_assurance`. Numele configurat nu este tratat drept personaj observat;
până la o dovadă client-visible, assurance rămâne `configured_expected_only` și
outputul Champion este nepromovabil. Operatorul nu acceptă override ad-hoc de la
caller.

Inputul este serializat de Executor Worker și reverifică identitatea instanței
chiar înainte de fiecare primitive. Armarea unei clone nu armează Championul și
nu armează altă clonă. O instanță care eșuează se oprește izolat, fără a opri
sau a contamina celelalte instanțe.

### Concurență și desktop interactiv

Win32 `SendInput` este global pentru desktopul interactiv și acționează asupra
ferestrei foreground. Din acest motiv, două instanțe care încearcă gameplay
fluid simultan pe același desktop s-ar lupta pentru focus, chiar dacă PID/HWND
sunt corect legate. Arhitectura de producție folosește:

```text
multi-instance orchestrator
  -> Executor Worker A -> interactive desktop/session/VM/host A -> Champion
  -> Executor Worker B -> interactive desktop/session/VM/host B -> LAB clone 1
  -> Executor Worker N -> interactive desktop/session/VM/host N -> LAB clone N
```

Există cel mult un Executor Worker care emite input pe un desktop interactiv.
Instanțele pot fi observate în paralel, dar time-slicing-ul mai multor clienți
activi pe același desktop rămâne doar o tehnică LAB de test și nu satisface
standardul de gameplay fluid al Championului. Pentru Champion Journey plus o
clonă care luptă non-stop sunt necesare două desktopuri interactive izolate,
de exemplu sesiuni/VM-uri/hosturi separate, fiecare cu worker și takeover propriu.

Client root separat nu înseamnă obligatoriu duplicarea tuturor asseturilor.
Implementarea poate folosi o imagine de bază read-only și overlay-uri separate,
dacă verificarea hash-urilor și izolarea `WTF`, `Interface`, cache și output sunt
păstrate. Alegerea este o optimizare de deployment, nu o schimbare de contract.

### Operare când utilizatorul este plecat

Fiecare client legacy activ rulează într-un desktop Windows interactiv păstrat
de workerul său; pentru hostul principal acesta este sesiunea `local-console`.
RDP nu este transportul clientului, deoarece clientul TBC legacy îl refuză și
poate schimba sesiunea desktop. Accesul de la distanță se separă în:

```text
phone/laptop
  -> secure Control Panel transport (commands, status, takeover)
  -> secure video/stream transport (view and recording supervision)
  -> interactive local-console host
  -> one or more isolated PA instances
```

Transportul trebuie să fie autentificat, criptat, revocabil și să nu expună
direct Execution Gateway-ul pe internet. Control Panel-ul cere alegerea
explicită a instanței, arată actorul și realm-ul înainte de armare și păstrează
un takeover global plus takeover per instanță. Stream-ul este observație; nu
devine automat evidence pentru Brain.

Tehnologia exactă de stream/control este un adapter evaluat într-un milestone
ulterior. ADR-ul fixează proprietățile cerute și păstrarea consolei interactive,
nu blochează produsul într-un anumit vendor sau protocol.

Această topologie permite monitorizarea Championului, înregistrarea video și
administrarea clonelor de pe telefon, în timp ce jocurile continuă în sesiunea
local-console. Căderea Control Panel-ului sau a stream-ului nu acordă acțiuni
noi; politica configurată decide între continuare bounded, pause sau safe stop.

### Rolul operatorului LAB curent

`scripts/Invoke-LabClientOperator.ps1` este un helper de bootstrap și probe
controlate pentru profilul curent `emulator_local`. Nu este Execution Gateway-ul
global al produsului și nu definește portabilitatea Perfect Assassin. El va fi
înlocuit sau încapsulat de orchestrarea per instanță; orice acțiuni dezvoltate
pentru el rămân explicit legate de profilul LAB curent până la promovare.

Exact target binding și runtime arm rămân obligatorii și în produsul standalone.
Ele confirmă clientul, fereastra și realm-ul selectate și leagă acțiunea de
binding-ul actorului configurat așteptat. Nu pretind că personajul efectiv logat
a fost observat; aceasta cere evidence client-visible separată. Controalele oferă
rollback/audit reproductibil, nu impun ca endpoint-ul să fie local și nu
limitează numărul de instanțe.

## Consecințe

- deployment-ul poate adăuga realm-uri prin date/profile, fără patch în Brain;
- Champion Journey poate continua în paralel cu benchmark-uri PvP/PvE LAB;
- un proces sau realm identificat greșit nu primește input;
- memoria și evidence-ul clonelor nu se pot confunda cu identitatea Championului;
- remote operation se construiește peste sesiunea local-console, Control Panel
  și stream securizat, nu peste RDP;
- viitorul Execution Gateway trebuie să fie multi-instance și target-agnostic;
- primul operator LAB rămâne un instrument temporar și restrâns, nu o limitare
  arhitecturală a produsului.

## Legături

- [Portabilitate standalone](../18-standalone-portability.md)
- [Execution target authorization](../23-execution-target-authorization.md)
- [Away-from-home LAB runbook](../17-away-from-home-lab-runbook.md)
- [ADR 0018 — Predator Pack / Hunt Party post-M7](0018-predator-pack-hunt-party.md)
- [ADR 0008 — capability-negotiated target portability](0008-capability-negotiated-target-portability.md)
- [ADR 0013 — client integrity și execution boundary](0013-client-integrity-and-input-execution-boundary.md)
