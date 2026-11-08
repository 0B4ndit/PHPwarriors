# 5.3 · Un imprevist: què proposem

Veredicte del verificador oficial: **VALIDA AMB RELAXACIONS DECLARADES** (1 incompliment declarat), el mateix S04526 del 5.2 (vegeu `../DEMOSTRACIO.md`). Referència: la nostra proposta sencera del 5.2 (`../5.2/proposta.csv`).

**Canvis respecte del 5.2: 2 de franja i 47 d’aula**, de 7.739 sessions. Tota la resta queda exactament igual.

| Imprevist | Com ho resolem | Sessions que canvien |
|---|---|---:|
| Q3/0013 reservada del 15 al 19/3 | Les classes d’aquella setmana van a una altra aula, al mateix dia i hora | 14 |
| TE/21 (GEQ 2n) passa de 91 a 130 alumnes | Canvi d’aula a una de 130 places o més (no desdoblem, per tant no hi ha cap relaxació d’aforament); S11543 (03/05) també passa de 11:30 a 09:30, perquè a la seva hora no queda cap aula prou gran lliure | 28 |
| Avaria a Q1/1003 el 10/3 | Les classes d’aquell dia van a una altra aula, a la mateixa hora | 5 |
| S11527 cancel·lada el 8/3 | Es recupera el 09/03/2027 a les 10:30 a Q3/1007, abans del 19/3, amb alumnat, docent i aula lliures (el verificador no hi compta cap solapament nou) | 1 |

Cap sessió fixada no canvia de dia ni d’hora. 14 de les sessions que canvien són de grups fixats que eren en una aula tancada: només canvien d’aula, i el verificador no ho compta com a moure-les.

## Com

El mateix model SAT del 5.2, però amb tota la proposta del 5.2 congelada: només queden lliures les classes que l’imprevist obliga a moure (aula tancada, grup que ja no hi cap, sessió cancel·lada). El solver busca la solució amb menys canvis. Si no n’hi hagués, alliberaria la setmana afectada, i després la recuperació a la setmana següent. Aquí n’hi ha prou amb el primer pas.
