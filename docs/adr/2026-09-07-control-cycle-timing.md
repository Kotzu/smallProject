# Cronometrare completă înaintea optimizării virajului

## Dovezi care schimbă următoarea intervenție

Proba C09 (42a590bb) se reproduce geometric exact pe primele 100 cadre cu v34.
Abaterea maximă 3.362623 yd apare în cadrele 92–93, la al doilea palier,
aproximativ 8.4 s după prima decizie. Nu este abatere de pe drumul exterior.
Sondele geometrice sunt condiționale pe Z proiectat, nu probe de contact fizic.

Între observația după cadrul 79 (160009.6465005) și observația folosită în
decizia 80 (160009.9132266) sunt 266.7261 ms. Actorul avansează aproximativ
1.8 yd. Câmpul existent observation_gap_s al cadrului 80 este doar 87.1633 ms:
refresh-ul a înlocuit ancora temporală. Opt astfel de intervale de 267–307 ms
există în probă, asociate evenimentelor PRECONTROL_POSE_REFRESHED. Nu înseamnă
input neautorizat: există watchdog și observația este reîmprospătată înainte
de input. Totuși, raportarea veche nu arată integral cadența controlului.

În porțiunea verificată, comenzile verticale sunt zero. Profilul exterior al
camerei este amânat până la oprire. Nu atribuim saltul camerei unei comenzi
verticale sau acelui profil; coliziunea camerei și virajul rămân de separat.

## Ce am exclus prin măsurare offline

Requery + replay 100/100: eroare geometrică 0. Profilul replay-ului: 100
decizii ~132 ms cumulat, nu 240 ms per decizie. Zece evaluări reale de mediu
și deschideri: ~21 ms cumulat. Aceste probe nu reproduc contendența proceselor
live și nu exclud întârzieri de scheduling; nu justifică rescrierea indexului
sau a controllerului. Motivul istoric al evenimentului numește overlay-ul,
dar nu măsoară separat etapele și nu demonstrează cauza.

## Schimbare

Jurnalul CONTINUOUS_FRAME primește control_cycle_timing: interval post→post,
intervalul până la observația de decizie și durata decizie→post, plus etape
de timp real: planificare, awareness, steering, memorie dinamică, pregătirea
afișării, recovery/handoff, refresh, autorizare și input/observație.
Etapele includ așteptarea procesorului; nu sunt atribuire exclusivă de CPU.
Valorile vechi rămân intacte. Nu schimbăm controller, navmesh, cameră, praguri,
watchdog sau verificările de autorizare. Nimic nu acordă autoritate.

Teste: 283 PASS (6 noi de cronometrare, 9 trace, 255 engine, 8 adaptive,
5 cache XYZ). Testul intervalului 267+87 ms verifică explicit că refresh-ul
nu mai ascunde timpul. Testul legării în runner verifică păstrarea ancorei
înainte de orice refresh. Acestea nu dovedesc o îmbunătățire live a mersului.

## Urmează / rollback

O singură probă filmată delimitată cu aceste măsurători, același v34/controller.
Abia apoi optimizăm etapa lentă dovedită și repetăm. Nu reglăm virajele pentru
a compensa latență neidentificată. C01/C05/C07 rămân neacceptate.
Rollback: eliminarea câmpului și a checkpoint-urilor din runner; funcția și
testele de cronometrare pot rămâne fără efect asupra mișcării. Baza c70b27a.
