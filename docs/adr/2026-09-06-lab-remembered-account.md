# Cont memorat pentru lansarea clientului LAB

Utilizatorul a cerut memorarea numelui și folosirea datelor de autentificare
furnizate pentru emulatorul său local.

`Invoke-LabClientOperator.ps1` folosește implicit fișierul local
`E:\WoWserver\TBC-LAB\database\predator-login.local.json`. Fișierul anterior
`observer-account.local.json` a fost păstrat nemodificat. Datele sunt locale,
în afara repository-ului; parola nu este inclusă în acest document, script,
configurația WoW sau argumentele comenzilor. Fișierul local este JSON simplu,
nu un seif criptat, și nu trebuie publicat ori inclus în arhive de distribuit.

La `Launch`, după verificarea că WoW nu rulează, scrierea configurației clientului
setează `accountName` la contul așteptat. Elimină intrările duplicate, păstrează
setările fără legătură și nu scrie parola. Nu se schimbă rezoluția sau camera
față de politica de lansare existentă.

`Launch` și `Login` rămân acțiuni separate. Loginul existent citește fișierul
local, dar continuă să ceară o sesiune validă, armare și confirmarea vizuală
distinctă a ecranului de login. Această schimbare nu introduce un autologin
necondiționat și nu conferă agentului excepții de la regulile instrumentelor
sale. Nu s-a executat loginul și nu s-a modificat configurația clientului activ
în această etapă; efectul vizual al opțiunii rămâne de confirmat la relansare.
