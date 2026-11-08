# Lliurament · nivell 2 · Repte d’horaris i espais

Totes les xifres d’aquesta carpeta surten del **verificador oficial**, executat sobre els mateixos fitxers que lliurem (`verificador.txt` de cada pregunta).

| Pregunta | | Veredicte | Incompliments declarats | Canvis |
|---|---|---|---:|---|
| 5.1 | Aules amb l’horari d’avui | VALIDA | 0 | — |
| 5.2 | Torns nous | VALIDA AMB RELAXACIONS DECLARADES | 1 | — |
| 5.3 | Imprevist | VALIDA AMB RELAXACIONS DECLARADES | 1 | 2 franja / 47 aula vs 5.2 |
| 5.4 | Grau nou | VALIDA AMB RELAXACIONS DECLARADES | 1 | 0 franja / 0 aula vs 5.2 |

L’única relaxació (5.2, 5.3 i 5.4) és **S04526**, i està demostrada inevitable: `DEMOSTRACIO.md`.

## Què hi ha

| | |
|---|---|
| `5.x/proposta.csv` | La proposta (`id_sessio,dia,h_ini,aula`; el 5.3 porta també `data` per a la sessió recuperada) |
| `5.x/relaxacions.csv` | Les relaxacions declarades, amb la justificació (no n’hi ha al 5.1) |
| `5.x/informe.json`, `5.x/violacions.csv` | La sortida del verificador (`--json`, `--violacions`) |
| `5.x/verificador.txt` | L’ordre exacta i la sortida completa del verificador |
| `5.x/RESPOSTA.md` | La resposta a la pregunta |
| `5.2/resum-junta.pdf` | El resum d’una pàgina per a la Junta Permanent (també `.md` i `.html`) |
| `DEMOSTRACIO.md` | Les nostres restriccions i la prova que el 5.2, el 5.3 i el 5.4 no poden ser VALIDA |
| `DOBLES-TITULACIONS.md` | Què fem amb els grups de doble titulació (§8.2) |
| `graella.html` | Regla 10: graella setmanal per aula de la proposta més avançada (5.4) |
| `proves/` | Les alternatives de S04526 comprovades amb el verificador |

## Criteris que hem aplicat

- **Aforament:** es compta amb `alumnes`, la definició del verificador (§8.2). No fem servir `capacitat_grup`.
- **Dobles titulacions:** a la tarda, com diu la regla 1 (§8.2). Vegeu `DOBLES-TITULACIONS.md`.
- **5.3, grup que ja no hi cap:** canvi d’aula, sense desdoblar. Per tant no hi ha cap relaxació d’aforament.
- **5.3, referència:** la nostra proposta sencera del 5.2 (`5.2/proposta.csv`).

## Com comprovar-ho (des de la carpeta `final/`)

```bash
python -m horaris check LLIURAMENT/5.1/proposta.csv --semestre 2 --nomes-aules
python -m horaris check LLIURAMENT/5.2/proposta.csv --semestre 2 --relaxacions LLIURAMENT/5.2/relaxacions.csv
python -m horaris check LLIURAMENT/5.3/proposta.csv --semestre 2 --escenari paquet/escenaris/contingencies --referencia LLIURAMENT/5.2/proposta.csv --relaxacions LLIURAMENT/5.3/relaxacions.csv
python -m horaris check LLIURAMENT/5.4/proposta.csv --semestre 2 --escenari paquet/escenaris/grau-nou-40 --referencia LLIURAMENT/5.2/proposta.csv --relaxacions LLIURAMENT/5.4/relaxacions.csv
```
