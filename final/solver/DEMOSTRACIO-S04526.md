# Per què cap proposta del 5.2 pot sortir VALIDA: la relaxació de S04526

**Què declarem.** Una sola relaxació: `R1-TORN` de la sessió **S04526**: Sistemes i Tecnologies Web (102750),
PAUL/453, GEI 3r/4t, docent D380. La deixem **exactament on la té avui l'Escola**: divendres 9/4/2027, 13:30–14:30,
aula Q1/0019. És un sol incompliment: una classe de tarda que es fa una hora abans, a l'aula i el dia de sempre.

**Què demostrem.** Amb les regles del verificador oficial (`horaris/check.py`, versió de la xaman c5dd933), les tres
sessions PAUL de D380 de la setmana 14 **no hi caben totes tres sense incomplir alguna regla dura**. Per tant
qualsevol 5.2 (i qualsevol 5.3 o 5.4, que les inclouen) té com a mínim un incompliment que compta o s'ha de declarar.

## Les dades

| Sessió | Grup | Data d'avui | Hora d'avui | Aula d'avui | Alumnes | Torn que li toca |
|---|---|---|---|---|---|---|
| S04496 | PAUL/451 | dv. 9/4/2027 | 11:30–12:30 | Q1/0019 | 35 | tarda |
| S04511 | PAUL/452 | dv. 9/4/2027 | 12:30–13:30 | Q1/0019 | 34 | tarda |
| S04526 | PAUL/453 | dv. 9/4/2027 | 13:30–14:30 | Q1/0019 | 34 | tarda |

Totes tres són de 60 minuts, del mateix docent (D380) i **no són fixades**.

Les dues aules d'informàtica, Q1/0007 i Q1/0019 (54 places cadascuna), el divendres 9/4 a la tarda tenen **grups
fixats** de GEI 1r (107890, "R1: GEI 1r", no es toquen), a la seva aula de partida:

| Aula | 15:00–17:00 | 17:00–19:00 |
|---|---|---|
| Q1/0007 | S15066 (PAUL/451, 42 al.) | S15153 (PAUL/472, 24 al.) |
| Q1/0019 | S15095 (PAUL/452, 32 al.) | S15124 (PAUL/471, 32 al.) |

## La demostració, pas a pas (cada pas és una línia del verificador)

1. **No poden canviar de setmana.** El verificador calcula la data nova dins la mateixa setmana ISO
   (`check.py`, línia 178). Són de la setmana 14 (5–9/4/2027).
2. **Només el divendres.** Del dilluns 5 al dijous 8/4 és la setmana d'avaluació del 2n semestre (enunciat §8.1),
   i el calendari hi té aturada de 00:00 a 24:00. Moure-hi una sessió és `R2-CALENDARI` (línies 224–230).
   Només queda el divendres 9/4.
3. **Només a la tarda, fins a les 21:00.** Són de GEI 3r/4t, `torn = tarda`: han de començar a les 14:30 o més tard
   (`R1-TORN`, `_torn_ok`, línia 101) i acabar a les 21:00 o abans (`R2-FINESTRA`, línia 135; `TARDA = 14:30–21:00`).
4. **Només a les dues aules d'informàtica.** Avui fan classe a Q1/0019, que és "Aules informàtiques". Per
   `R3-TIPUS` (`_tipus_permesos` i `_espai_ok`, línies 112–132) només poden anar a una aula d'informàtica o a un
   laboratori integrat. Els laboratoris integrats tenen 24 places i els grups en tenen 34–35: `R3-AFORAMENT`
   (línia 268). Només queden **Q1/0007 i Q1/0019**.
5. **Aquestes dues aules són plenes de 15:00 a 19:00** amb els grups fixats de la taula. Moure'ls, o canviar-los
   d'aula, és `R1-FIXADA` (línia 206). Compartir-los l'aula és `R4-AULA` (línia 290).
6. **Dues hores per a tres classes del mateix docent.** A les aules d'informàtica, a la tarda, només queden lliures
   14:30–15:00 (30 minuts: no hi cap una sessió d'una hora) i 19:00–21:00 (dues hores). D380 no pot fer dues classes
   alhora: `R4-DOCENT` (línia 294). Hi caben **dues** sessions (19:00 i 20:00), no tres.
7. **No hi ha herència possible.** Un incompliment només és "heretat" si totes les sessions implicades són fixades i
   no s'han mogut, o si és un solapament de docent o alumnat que ja hi era avui (`_marca_heretades`, línia 395).
   Aquestes tres sessions no són fixades, i avui no se solapen.

**Conclusió.** Una de les tres incompleix per força alguna regla. Cada alternativa costa exactament un
incompliment, i triem la menys greu.

## Comprovació amb el verificador oficial

Hem passat el verificador oficial (`python -m horaris check … --semestre 2`, sense relaxacions) sobre la nostra
proposta del 5.2, canviant només on va S04526:

| On posem S04526 | Veredicte | Què compta el verificador |
|---|---|---|
| Matí, on és avui (13:30, Q1/0019): **el que declarem** | NO VALIDA | `R1-TORN`: tarda 13:30–14:30 |
| Tarda, laboratori integrat Q2/0007 | NO VALIDA | `R3-AFORAMENT`: 34 alumnes a Q2/0007 (24) |
| 19:00 a Q1/0007, alhora que S04511 | NO VALIDA | `R4-DOCENT`: D380 |
| 15:00 a Q1/0019, compartint aula amb S15095 | NO VALIDA | `R4-AULA`: Q1/0019 9/4 15:00 |
| 15:00 a l'aula docent Q1/1003 (90 places) | NO VALIDA | `R3-TIPUS` + `R4-AULA` |

A més, de dues maneres independents:
- **Cerca exhaustiva amb les funcions del verificador** (`solver/cerca_s04526.py`). Prova cada dia de la setmana 14,
  cada hora d'inici de 08:30 a 20:45 (de 15 en 15 minuts) i cada una de les 56 aules, per a cadascuna de les tres
  sessions i després totes tres juntes. Resultat: **cap combinació** sense incompliments.
- **Solver SAT (kissat).** La setmana 14 amb totes les regles i totes les sessions mòbils lliures surt
  **UNSAT** (no hi ha cap solució). Només en té si es treu la regla del torn per a aquestes sessions.

## Per què declarem R1-TORN i no una altra

- **És la que menys canvia:** S04526 queda exactament com avui (dia, hora i aula). Ningú no canvia d'aula ni de
  professor.
- **No afecta ningú més:** no posa ningú en una aula massa petita (aforament) ni en una aula d'un altre tipus, ni fa
  coincidir el docent en dues classes, ni comparteix aula amb un altre grup.
- **És una sola sessió:** la resta del 5.2 compleix totes les regles. Els 458 grups fixats de tarda sense aula són
  heretats amb el verificador actual.

## Com reproduir-ho

```bash
cd final/solver
python3 cerca_s04526.py                                            # cerca exhaustiva: 0 combinacions
cd .. && python -m horaris check solver/out/prova/B-lab-24-places.csv --semestre 2   # cada alternativa
```

Les cinc propostes de prova són a `solver/out/prova/` (A–E).
