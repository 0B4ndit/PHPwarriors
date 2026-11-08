# Resum per a la Junta Permanent · torns nous (pregunta 5.2)

Proposta: `proposta.csv` · 7739 sessions del 2n semestre · veredicte del verificador: **VALIDA AMB RELAXACIONS DECLARADES** (459 incompliments declarats, vegeu les excepcions).

## 1. Pic de sessions simultànies davant de les aules ordinàries

Aules ordinàries: 21, de les quals 2 queden sempre lliures (regla 8): **19 disponibles** a cada franja.

| Torn | Pic de classes alhora en aules ordinàries | Quan |
|---|---:|---|
| matí | **14** de 19 | 03/05/2027 10:30 |
| tarda | **15** de 19 | 03/02/2027 16:15 |

## 2. Aules per mida (aules docents + seminaris)

Per a cada mida: quantes aules en tenen almenys aquesta capacitat, i el màxim de classes simultànies que la necessiten (alumnes per sobre de la mida anterior). Marge negatiu = falten aules d'aquesta mida.

| Capacitat ≥ | Aules | Pic de classes que la necessiten | Marge |
|---:|---:|---:|---:|
| 10 | 29 | 17 | 12 |
| 16 | 28 | 16 | 12 |
| 20 | 27 | 16 | 11 |
| 24 | 24 | 15 | 9 |
| 30 | 22 | 15 | 7 |
| 34 | 21 | 14 | 7 |
| 48 | 20 | 14 | 6 |
| 50 | 17 | 9 | 8 |
| 63 | 16 | 8 | 8 |
| 88 | 14 | 7 | 7 |
| 90 | 12 | 4 | 8 |
| 100 | 7 | 3 | 4 |
| 117 | 5 | 3 | 2 |
| 130 | 3 | 1 | 2 |
| 160 | 1 | 0 | **1** |

Mides justes (marge ≤ 1): 160. No en falta cap: totes les sessions tenen aula (R5) sense superar l'aforament (R3).

## 3. Sessions mogudes (dia o hora) per titulació i curs

En total **2257** sessions canvien de franja i 102 d'aula respecte d'avui (hores mortes 842 h, 3110 canvis d'aula entre classes seguides, 0 d'edifici).

| Titulació i curs | Sessions | Mogudes | % |
|---|---:|---:|---:|
| GCIS:2n | 124 | 124 | 100 % |
| GEQ:3r | 163 | 163 | 100 % |
| GEST:4t | 112 | 112 | 100 % |
| GEST:3r | 527 | 497 | 94 % |
| GEET:3r | 238 | 208 | 87 % |
| GEET:4t | 83 | 69 | 83 % |
| GEI:3r | 1381 | 882 | 64 % |
| GEI:4t | 1217 | 775 | 64 % |
| GIA:1r | 110 | 70 | 64 % |
| GED:4t | 88 | 53 | 60 % |
| GIA:2n | 94 | 40 | 43 % |
| GCIS:3r | 125 | 41 | 33 % |
| GEQ:1r | 231 | 51 | 22 % |
| GCIS:4t | 69 | 14 | 20 % |
| GEQ:2n | 214 | 37 | 17 % |
| GIA:3r | 163 | 26 | 16 % |
| GED:3r | 181 | 28 | 15 % |
| MRICSE:M | 82 | 11 | 13 % |
| GED:1r | 235 | 27 | 11 % |
| MEBA:M | 79 | 2 | 3 % |

## 4. Excepcions a la regla 1 que demanem

- **R1-TORN**, 1 sessions (S04526): Demostrat impossible sense relaxar (solver/nucli.py, setmana 14): el 5-8/4/2027 és setmana d'avaluació, així que les sessions de la setmana 14 només poden anar el divendres 9/4. El docent D380 hi té tres PAUL d'una hora de 102750 (GEI 3r/4t, 34-35 alumnes, torn de tarda) que per R3-TIPUS van a aula d'informàtica (Q1/0007, Q1/0019; els laboratoris integrats són de 24 places). Les dues aules d'informàtica les ocupen grups fixats de GEI 1r de 15:00 a 19:00, i a la tarda només queden 14:30-15:00 i 19:00-21:00: hi caben dues sessions del docent, no tres. Una d'elles es queda al matí, com avui.
- **R1-TORN**, 458 sessions: Grups de GEI i GEET+GEST de 1r i 2n fixats (R1: no es toquen, R1-FIXADA) que avui fan classe a la tarda i no tenen aula. No es poden moure al matí sense incomplir R1-FIXADA, i sense aula incompleixen R5-SENSE-AULA; en posar-los aula, el verificador deixa de considerar heretat el seu R1-TORN. Mantenim l'horari que l'Escola ha fixat i els donem aula.
