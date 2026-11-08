# Nivell 1 · Anàlisi de dades: com s'usen avui els espais i hi cap el model nou?

Totes les xifres són del **2n semestre** del curs 2026-27 (7.739 sessions). El semestre es dedueix de la **data** (setembre-gener = 1r), no del camp T/V de Sigma, que no és fiable. El codi és a `analisi/nivell1.py` i es pot tornar a executar amb `python analisi/nivell1.py`.

**Criteris comuns.** Les PLAB i els grups de doble titulació (`sense_espai = 1`) no ocupen aulari i s'exclouen dels càlculs d'espai. Una classe compartida entre titulacions (`id_compartida`) compta una sola vegada. Les xifres s'han contrastat amb el verificador de l'organització.

## Resum

| # | Troballa | Xifra clau |
|---|---|---|
| 1 | Sessions que cal assignar a una aula | 4.541 de 5.722 sense aula |
| 2 | Sessions fora del torn del model nou | 2.008 mobles; el 88 % van de matí a tarda |
| 3 | Hi cap el matí? | Sí: 69,6 % de les hores-aula, pic de 15 classes alhora sobre 19 aules, sense coll d'ampolla per mida |
| 4 | Grups que no hi caben a l'aula d'avui | 101 sessions en 6 grups; 54 PAUL en un laboratori de Q6 |
| 5 | Ocupació per aula | El 74 % de les sessions no té aula a les dades |

## 1. El 74 % de les sessions no tenen aula, però només 4.541 són un problema real

- **Conclusió.** 5.722 de les 7.739 sessions (73,9 %) no tenen aula a les dades. D'aquestes, 919 són PLAB (les assignen els departaments) i 262 són dobles titulacions (no necessiten espai propi). Les **4.541** restants són les que cal assignar, i coincideixen amb el R5-SENSE-AULA del verificador.
- **Càlcul.** Sessions del 2n semestre amb `aula_partida` buida, separades per `tipus == PLAB` i `sense_espai == 1`.

## 2. 2.008 sessions mobles són fora del torn nou, quasi totes de matí a tarda

- **Conclusió.** Hi ha 3.246 sessions fora de torn, però 1.238 són fixades (GEI i GEET+GEST de 1r i 2n, i PLAB) i no es poden moure. De les **2.008** mobles, **1.774 (88 %) són de matí i haurien d'anar a la tarda** i només **234 són de tarda i haurien d'anar al matí**. Les més afectades són GEI 3r/4t (691), GEST 3r (244), GEI 3r (192), GEET+GEST 3r (167) i GEQ 3r (163).
- **Càlcul.** Torn real = matí si `h_ini` és abans de les 14.30. Es compara amb `torn_requerit` i s'agrupa per `titulacions_curs`. El 2.008 coincideix amb R1-TORN.

## 3. El matí hi cap, i no hi ha coll d'ampolla per mida

- **Conclusió.** La setmana més carregada, les classes de matí demanen 397 h-aula de les 570 disponibles (19 aules × 6 h × 5 dies), és a dir el **69,6 %** (mediana 67,2 %). El pic és de **15 classes alhora sobre 19 aules**. Per mida tampoc hi ha problema: només 25 sessions setmanals tenen 90 alumnes o més (37 h), davant de 12 aules d'aquesta mida (360 h d'oferta). Cap sessió de matí arriba als 130 alumnes.
- **Càlcul.** Hores-aula setmanals de les sessions amb `torn_requerit = mati`. Pic de simultaneïtat per franges de 30 minuts i data. Demanda i oferta per llindar de capacitat, a la setmana 2027-W06.
- **Límits.** El pic compta les sessions amb l'hora d'avui: quan les 234 sessions de tarda passin al matí, pujarà, i la xifra definitiva surt de la proposta del 5.2. Les sessions amb 0 alumnes a les dades (`sense_dada`) no es poden classificar per mida.

## 4. 101 sessions no caben a l'aula on són avui, però només en 6 grups

- **Conclusió.** 101 sessions (6 grups) tenen més alumnes que places. L'excés és petit, d'1 a 8 places. El pitjor cas és Física TE/21: 125 alumnes a Q4/0011, que té 117 places. A més, **54 sessions de PAUL són en un laboratori de Q6**, on no poden anar. Es resol amb canvis d'aula, sense cap aula nova.
- **Càlcul.** `alumnes` contra `capacitat` de l'aula (`aules.csv`), només sessions amb aula de l'inventari. Les 101 es reparteixen en 43 que compten i 58 d'heretades al verificador (R3-AFORAMENT).

## 5. Només es veu el 26 % de l'ocupació real

- **Conclusió.** De les aules docents, la més plena és Q3/0013 (13,8 h de classe per setmana), seguida de Q4/0011 (10,4), Q4/1003 i Q1/1003 (9,6) i Q1/1007 (8,8). Q1/1011, Q3/1011, Q4/0007, Q4/0003 i Q3/1007 no tenen cap sessió assignada. Hi ha 379,7 h setmanals de classe sense aula.
- **Límit important.** Una aula pot funcionar unes 65 h a la setmana. Com que el 74 % de les sessions no té aula a les dades, les aules «buides» poden estar en ús avui sense que el pla ho reculli. Aquesta xifra descriu la qualitat de les dades, no que sobrin aules.
- **Càlcul.** Hores de classe per aula i dia dividides per 17 setmanes (algunes són gairebé buides pels festius, així que les xifres són una mica baixes). El mapa de calor és a [`ocupacio.png`](ocupacio.png).

## Pendent

- Contrastar l'ocupació amb `validacio/` (ocupació real d'una setmana d'octubre) per saber si les aules «buides» de la troballa 5 s'usen de veritat.
