# ADR 0130 — Lumea topografică localizată este baza MovementEngine

## Decizie

Predator se deplasează autonom folosind aceeași fundație în orice zonă:

1. un WorldPack static și versionat descrie suprafețele 3D, înălțimile,
   marginile, structurile și obstacolele cunoscute;
2. observația clientului furnizează continuu poziția curentă în același sistem
   de coordonate;
3. facingul corpului și direcția controlată a camerei sunt două valori separate;
4. planificatorul calculează un coridor nou din poziția curentă către destinație;
5. controllerul urmărește coridorul și verifică din nou poziția după fiecare
   cadru de control.

Datele statice sunt codate în WorldPack, nu ca ramuri speciale pentru Cryptă,
Deathknell, Brill sau alt loc. Navmesh-ul rămâne o rețea de suprafețe și
legături, nu o listă manuală de comenzi.

## Autoritatea observațiilor

- Poziția provine din observația vizibilă a clientului și transformarea
  versionată către coordonatele WorldPack.
- Facingul corpului este acceptat ca exact numai când sursa declară
  `COORDINATE_HUD_EXACT`.
- Direcția estimată a camerei este păstrată separat pentru controller.
- Detectorul siluetei personajului este diagnostic. El nu este sursă de
  poziție, facing sau autoritate de mers în navigarea normală.
- Dacă poziția sau facingul nu sunt suficient de proaspete, starea fundației
  declară clar că nu este pregătită; nu inventează valori.

## Regula de protejare a progresului

O schimbare de hartă, localizare sau controller nu poate fi promovată dacă
înrăutățește ultima dovadă live acceptată. Testele offline verifică doar codul;
acceptarea comportamentului necesită o probă live filmată și comparată cu
baseline-ul anterior.

## Consecință

Crypta este primul test, nu o excepție în cod. Aceeași fundație trebuie să poată
descrie și traversa o casă, un pod, un oraș, un câmp sau un dungeon prin datele
WorldPack potrivite.
