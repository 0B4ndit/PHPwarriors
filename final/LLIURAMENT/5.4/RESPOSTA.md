# 5.4 · Un grau nou de 40 places: hi cap?

**Sí, hi cap, sense canviar res del 5.2.** Veredicte del verificador oficial: **VALIDA AMB RELAXACIONS DECLARADES** (1 incompliment declarat), el mateix S04526 del 5.2 (vegeu `../DEMOSTRACIO.md`). El grau nou no n’afegeix cap.

| | |
|---|---:|
| Sessions del grau nou al 2n semestre | 235 |
| Amb aula | 235 |
| Al dia i l’hora que porten | 221 |
| Mogudes dins la mateixa setmana, sempre al matí | 14 |
| Canvis de franja a la proposta del 5.2 | **0** |
| Canvis d’aula a la proposta del 5.2 | **0** |

Aules que fa servir el grau nou: Q1/0007 (14), Q1/1003 (45), Q2/0017 (28), Q2/1003 (14), Q3/0009 (26), Q4/0007 (13), Q4/1005 (39), QC/0015 (14), QC/3115.2 (42).

Les 235 sessions ja venen al matí, que és el seu torn. 221 es queden al dia i hora que porten. Les altres 14 es mouen dins la mateixa setmana, sempre al matí, per reduir hores mortes i canvis d’aula del grup nou. Hi ha prou aules lliures de la mida i el tipus que toca sense tocar cap sessió del 5.2, i se segueixen respectant les dues aules ordinàries lliures a cada franja (regla 8).

## Com

El model SAT amb tota la proposta del 5.2 congelada, de manera que cap sessió existent no es pot moure. Les sessions del grau nou tenen el seu dia i hora i només se’ls busca aula. Si no hi hagués cabut, el pas següent era deixar-les moure dins la seva setmana, i si tampoc, el solver ho hauria demostrat (UNSAT). Després, una cerca local que només toca el grau nou en redueix les hores mortes.
