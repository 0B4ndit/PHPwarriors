# Demostració: el 5.2, el 5.3 i el 5.4 no poden sortir VALIDA

Amb les regles del verificador oficial, **qualsevol** proposta del 5.2, del 5.3 o del 5.4 té com a mínim un incompliment que compta o s’ha de declarar. Aquí ho demostrem. És la diferència que demana la regla 11 entre «no hem trobat un horari vàlid» i «hem demostrat que no existeix». Per això declarem una sola relaxació, la mateixa a les tres preguntes: R1-TORN de **S04526**, que es queda exactament on és avui (divendres 9/4/2027, 13:30, Q1/0019).

## 1. Les nostres restriccions

El nostre model (`solver/horaris.pl`, una regla per predicat, resolt amb el solver SAT kissat) imposa aquestes restriccions. Cada una correspon a una regla de l’apartat 3 i al codi que la comprova al verificador (`horaris/check.py`):

| # | Restricció del model | Què vol dir | Regla / codi |
|---|---|---|---|
| 1 | Cada classe, un sol dia de la seva setmana | Totes les sessions es fan, a la seva setmana ISO, sense eliminar-ne ni escurçar-ne cap | R5, R5-FALTA |
| 2 | Una sola hora d’inici, dins la finestra del seu torn | Matí: comença a les 8:30 o després i acaba a les 14:30 o abans. Tarda: comença a les 14:30 o després i acaba a les 21:00 o abans. El torn el marca l’hora d’inici; una sessió que creua les 14:30 no és vàlida | R1-TORN, R2-FINESTRA |
| 3 | Una sola aula, i adequada | De l’aulari (les J es buiden; a B3/0021 i QC/1082 només s’hi pot quedar qui ja hi és). Del mateix tipus que avui (aula docent i seminari compten com el mateix). La teoria mai en un laboratori, i els de Q5/Q6 només per a PLAB. Un PAUL també pot anar a un laboratori integrat o a una aula d’informàtica. Capacitat ≥ `alumnes` | R3-AULA, R3-TIPUS, R3-AFORAMENT, R5-SENSE-AULA |
| 4 | Calendari | Cap classe no es mou a un festiu, dia no lectiu, aturada o dia de la setmana d’avaluació. Les que ja hi són avui poden canviar d’hora el mateix dia | R2-CALENDARI |
| 5 | Aules tancades (5.3) | Cap classe a Q3/0013 del 15 al 19/3 ni a Q1/1003 el 10/3 | R3-TANCADA |
| 6 | Una classe per aula alhora | Dues classes que coincideixen en el temps no comparteixen aula | R4-AULA |
| 7 | Ningú en dos llocs alhora | Un docent, un grup d’alumnes (mateixa cohort, i teoria amb els seus subgrups) o una TE/PAUL amb el PLAB de la mateixa assignatura no poden coincidir. Els solapaments que ja hi són avui no compten (heretats) | R4-DOCENT, R4-ALUMNAT, R4-PLAB |
| 8 | Dues aules ordinàries lliures | A cada franja d’una hora de 8:30 a 21:00, com a màxim 19 de les 21 aules docents ocupades | R8-RESERVA |
| 9 | Fixades i PLAB no es toquen | GEI i GEET+GEST de 1r i 2n, i els PLAB: mateix dia i hora. Els PLAB i les fixades que tenen aula conserven l’aula, llevat que l’escenari la tanqui | R1-FIXADA, R7-PLAB |
| 10 | Classes compartides juntes | Les sessions amb el mateix `id_compartida` són una sola classe física: mateix dia, hora i aula | R4-COMPARTIDA |
| 11 | Mínims canvis | Primer només poden canviar les classes que ho han de fer, i el límit s’amplia pas a pas només si no hi ha solució | Objectiu 9 |

Decisions de modelització: hores d’inici cada 15 minuts; les dobles titulacions (`sense_espai`) no ocupen aula; l’aforament es compta amb `alumnes` (§8.2). **La demostració de sota no depèn de cap d’aquestes decisions:** fa servir només les regles oficials i val per a qualsevol hora (al minut) i per a qualsevol horari de la resta de sessions.

## 2. Les dades

| Sessió | Grup | Avui | Aula d’avui | Alumnes | Torn que li toca | Docent |
|---|---|---|---|---:|---|---|
| S04496 | 102750 PAUL/451 | dv. 09/04/2027 11:30–12:30 | Q1/0019 | 35 | tarda | D380 |
| S04511 | 102750 PAUL/452 | dv. 09/04/2027 12:30–13:30 | Q1/0019 | 34 | tarda | D380 |
| S04526 | 102750 PAUL/453 | dv. 09/04/2027 13:30–14:30 | Q1/0019 | 34 | tarda | D380 |

Cap de les tres és fixada. Les dues aules d’informàtica (Q1/0007 i Q1/0019, 54 places) estan ocupades el divendres 9/4 a la tarda per **grups fixats** de GEI 1r, a la seva aula d’avui:

| Sessió | Grup | Hora | Aula | Alumnes | Fixada |
|---|---|---|---|---:|---|
| S15066 | 107890 PAUL/451 | 15:00–17:00 | Q1/0007 | 42 | R1: GEI 1r |
| S15153 | 107890 PAUL/472 | 17:00–19:00 | Q1/0007 | 24 | R1: GEI 1r |
| S15095 | 107890 PAUL/452 | 15:00–17:00 | Q1/0019 | 32 | R1: GEI 1r |
| S15124 | 107890 PAUL/471 | 17:00–19:00 | Q1/0019 | 32 | R1: GEI 1r |

## 3. La demostració, pas a pas

1. **No poden canviar de setmana.** La data nova és el dia triat dins la mateixa setmana ISO (restricció 1; `check.py`, línia 178). Són de la setmana 14 (5–9/4/2027).
2. **Només el divendres.** Del 5 al 8/4 és setmana d’avaluació (§8.1): el calendari hi té aturada de 00:00 a 24:00, i moure-hi una sessió és R2-CALENDARI (restricció 4; línies 224–230).
3. **Només a la tarda, fins a les 21:00.** Són de GEI 3r/4t, torn de tarda: han de començar a les 14:30 o després i acabar a les 21:00 o abans (restricció 2; `_torn_ok`, línia 101, i `_dins_finestra`, línia 135).
4. **Només a Q1/0007 o Q1/0019.** Avui són en una aula d’informàtica, així que només poden anar a una aula d’informàtica o a un laboratori integrat (restricció 3; `_tipus_permesos` i `_espai_ok`, línies 112–132). Els laboratoris integrats tenen 24 places i els grups 34–35 alumnes (R3-AFORAMENT, línia 268).
5. **Aquestes dues aules són plenes de 15:00 a 19:00** amb grups fixats que no es poden moure ni canviar d’aula (restricció 9; R1-FIXADA, línia 206). Compartir-los l’aula és R4-AULA (restricció 6; línia 290).
6. **Dues hores per a tres classes del mateix docent.** Lliure a la tarda a aquestes aules només hi ha 14:30–15:00 (30 minuts, no hi cap una classe d’una hora) i 19:00–21:00. D380 no pot fer dues classes alhora (restricció 7; R4-DOCENT, línia 294). Hi caben dues sessions (19:00 i 20:00), no tres.
7. **No hi ha herència possible.** Un incompliment només és heretat si totes les sessions són fixades i no s’han mogut, o si és un solapament que ja hi era avui (`_marca_heretades`, línia 395). Cap de les dues coses es compleix aquí.

**Per tant, una de les tres incompleix per força alguna regla.** Cada alternativa costa com a mínim un incompliment. Triem la que menys canvia: S04526 es queda on és avui.

## 4. Val també per al 5.3 i el 5.4

- **5.3:** tres dels quatre imprevistos són a les setmanes 10 i 11 (8 al 19/3): l’aula reservada, l’avaria i la sessió cancel·lada, que es recupera abans del 19/3. El quart, TE/21 a 130 alumnes, només canvia d’aula les sessions d’aquest grup de teoria, que necessiten aules de 130 places i no poden anar mai a les aules d’informàtica (54 places). A la setmana 14 no se n’allibera cap aula, i el 5.3 parteix del nostre 5.2.
- **5.4:** el grau nou només hi afegeix sessions. Pot ocupar més aules o més hores, mai alliberar-ne.

## 5. Comprovat de tres maneres independents

**a) El verificador oficial, sobre alternatives reals.** La nostra proposta del 5.2, canviant només on va S04526 (fitxers a `proves/`). Sense relaxacions, cada una surt NO VALIDA:

| Prova | On posem S04526 | Veredicte | Què compta el verificador |
|---|---|---|---|
| `A-mati-avui.csv` | S04511 dv. 19:00 Q1/0019; S04526 dv. 13:30 Q1/0019 | NO VALIDA | R1-TORN: tarda: 13:30-14:30 |
| `B-lab-24-places.csv` | S04511 dv. 19:00 Q1/0019; S04526 dv. 15:00 Q2/0007 | NO VALIDA | R3-AFORAMENT: 34 alumnes a Q2/0007 (24) |
| `C-mateix-docent.csv` | S04511 dv. 19:00 Q1/0019; S04526 dv. 19:00 Q1/0007 | NO VALIDA | R4-DOCENT: D380 |
| `D-aula-compartida.csv` | S04511 dv. 19:00 Q1/0019; S04526 dv. 15:00 Q1/0019 | NO VALIDA | R4-AULA: Q1/0019 2027-04-09 15:00 |
| `E-aula-docent-gran.csv` | S04511 dv. 19:00 Q1/0019; S04526 dv. 15:00 Q1/1003 | NO VALIDA | R3-TIPUS: Q1/1003 és «Aules docents»; cal Aules informàtiques; R4-AULA: Q1/1003 2027-04-09 15:00 |
| `F-mateixa-aula-mateix-docent.csv` | S04511 dv. 19:00 Q1/0019; S04526 dv. 19:00 Q1/0019 | NO VALIDA | R4-AULA: Q1/0019 2027-04-09 19:00; R4-DOCENT: D380 |

**b) Cerca exhaustiva amb les funcions del verificador** (`solver/cerca_s04526.py --pregunta 5.2|5.3|5.4`). Per a cadascuna de les tres sessions prova cada dia de la setmana 14, cada hora d’inici de 08:30 a 20:45 (de 15 en 15 minuts) i cada una de les 56 aules, i després totes les combinacions. La resta de sessions queden com a la nostra proposta de cada pregunta:

| Pregunta | S04496: llocs vàlids | S04511: llocs vàlids | S04526: llocs vàlids | Combinacions vàlides de les tres |
|---|---:|---:|---:|---:|
| 5.2 | 2 (dv. 20:00) | 2 (dv. 19:00) | 10 (dv. 19:00–20:00) | **0** |
| 5.3 | 2 | 2 | 10 | **0** |
| 5.4 | 2 | 2 | 10 | **0** |

**c) El solver SAT.** La setmana 14 del 5.2, amb totes les restriccions de l’apartat 1 i totes les classes mòbils lliures, surt **UNSAT** (no té cap solució). Només en té si es treu la restricció de torn (restricció 2).

## 6. Com reproduir-ho (des de la carpeta `final/`)

```bash
python -m horaris check LLIURAMENT/proves/B-lab-24-places.csv --semestre 2     # cada alternativa
cd solver && python3 cerca_s04526.py --pregunta 5.2                           # cerca exhaustiva
```
