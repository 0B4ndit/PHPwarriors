# 5.2 · Torns nous: 1r i 2n al matí, 3r i 4t a la tarda

Veredicte del verificador oficial: **VALIDA AMB RELAXACIONS DECLARADES** (1 incompliment declarat).

**Resum per a la Junta Permanent:** `resum-junta.pdf` (una pàgina; també en `.md` i `.html`).

## Què costa

- **2.056 de 7.739 sessions (27 %) canvien de dia o d’hora**, i 151 canvien d’aula respecte d’avui.
- **Qui ho nota més:** en nombre, GEI:3r (882), GEI:4t (775), GEST:3r (497), GEET:3r (208), GEQ:3r (163); en proporció, GCIS:2n, GEQ:3r, GEST:4t (totes les seves sessions).
- **On no hi cap:** en un sol cas, S04526. Les tres classes del docent D380 de la setmana 14 no caben totes tres a la tarda, i ho hem demostrat (`../DEMOSTRACIO.md`). Declarem una sola relaxació: S04526 es queda al matí, exactament on és avui.
- **Dobles titulacions:** les 248 sessions de dobles que avui són al matí passen a la tarda, com demana la regla 1 (`../DOBLES-TITULACIONS.md`).

## Objectius de la regla 9 i la regla 6

| Objectiu (verificador) | Valor |
|---|---:|
| Hores mortes (minuts al semestre) | 49.950 |
| Sessions que canvien de dia o hora respecte d’avui | 2.056 |
| Sessions que canvien d’aula respecte d’avui | 151 |
| Canvis d’aula entre classes seguides | 1.291 |
| Canvis d’edifici entre classes seguides | 0 |
| Aules de teoria de més per grup (aula base, R6) | 9 |
| Canvis TE↔PAUL fora del passadís (R6) | 247 |

Hores mortes: 832 h al semestre, sumant tots els grups. L’aforament es compta amb `alumnes` (definició del verificador, §8.2).

## Com

1. **Model SAT** (Prolog + kissat) amb totes les regles de l’apartat 3 (llista exacta a `../DEMOSTRACIO.md`). Primer es posa un patró setmanal per a cada classe (mateix dia i hora cada setmana); després es reparen les setmanes amb festius, aturades o setmana d’avaluació.
2. **Mínims canvis:** el solver primer només deixa moure les classes que han de canviar (les que són fora del seu torn o cauen en un festiu), i només n’afegeix més si no hi ha solució.
3. **Optimització:** una cerca local redueix hores mortes i canvis d’aula sense trencar cap regla. Cada moviment es comprova amb les mateixes definicions que el verificador.
4. **Comprovació:** el verificador oficial sobre aquesta mateixa proposta (`verificador.txt`, `informe.json`, `violacions.csv`).
