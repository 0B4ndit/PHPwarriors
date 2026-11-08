# 5.1 · Distribuir els grups del semestre a les aules

Veredicte del verificador oficial (`--nomes-aules`): **VALIDA**. Cap dia ni hora no canvia.

## Què hem fet

- **4.541 sessions sense aula avui tenen aula** de la mida i el tipus que toca.
- **1.455 de les 1.612 sessions que ja tenien aula la conserven.** Les altres 157 canvien perquè avui no hi caben, són en un espai del tipus que no toca (com els PAUL dels laboratoris de Q6), o perquè així el grup té una aula base més estable.
- Els laboratoris PLAB i els grups de doble titulació no es toquen: els PLAB no canvien d’aula i els dobles no necessiten espai propi.
- L’aforament es compta amb `alumnes`, la definició del verificador (§8.2). No fem servir `capacitat_grup`.

## Qualitat de l’assignació (el que puntua al 5.1)

| Objectiu (verificador) | Valor |
|---|---:|
| Canvis d’aula entre classes seguides | 1.472 |
| Canvis d’edifici entre classes seguides | 6 |
| Sessions que canvien d’aula respecte d’avui | 157 |
| Aules de teoria de més per grup (aula base, R6) | 15 |
| Canvis TE↔PAUL fora del passadís (R6) | 462 |

## Com

Un model SAT (Prolog + kissat) dona aula a cada classe amb totes les regles d’espai, intentant primer conservar l’aula d’avui. Després, una cerca local millora l’aula base de cada grup, els canvis d’aula entre classes seguides i els canvis respecte d’avui, sense trencar cap regla. Detall de les regles: `../DEMOSTRACIO.md`.
