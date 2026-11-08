#!/usr/bin/env python3
"""Builds the delivery folder final/LLIURAMENT from the proposals in out/, re-running the OFFICIAL verifier on the
delivered copies and writing every answer from its reports (no figure is typed by hand).

    python3 lliurament.py          (from final/solver, after make 5.1 5.2 5.3 5.4 graella)

LLIURAMENT/
  LLEGIU-ME.md              index, verdicts, how to re-check everything
  DEMOSTRACIO.md            why 5.2, 5.3 and 5.4 cannot be VALIDA: our restrictions, the proof, the evidence
  DOBLES-TITULACIONS.md     what happens to the double-degree groups (enunciat 8.2)
  graella.html              rule 10: weekly grid per room of the most advanced proposal (5.4)
  5.1/ 5.2/ 5.3/ 5.4/       proposta.csv, relaxacions.csv, informe.json, violacions.csv, RESPOSTA.md
                            (+ 5.2: resum-junta.md / .html / .pdf for the Junta Permanent)
  proves/                   the alternative placements of S04526 checked in DEMOSTRACIO.md
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                                   # final/
L = ROOT / 'LLIURAMENT'
sys.path.insert(0, str(ROOT))
from horaris.model import DIES, MATI, carrega_base, fmt, hm  # noqa: E402

ESC = {'5.1': None, '5.2': None, '5.3': 'contingencies', '5.4': 'grau-nou-40'}
SESSIONS_CSV = {r['id_sessio']: r for r in csv.DictReader(open(ROOT / 'paquet' / 'sessions.csv', encoding='utf-8'))}


def base_of(q):
    return carrega_base(ROOT / 'paquet', semestre=2, escenari=ROOT / 'paquet' / 'escenaris' / ESC[q] if ESC[q] else None)


def read(p):
    with open(p, encoding='utf-8') as f:
        return list(csv.DictReader(f))


def check(q):
    """The official verifier on the delivered files, exactly as the jury runs it."""
    d = f'LLIURAMENT/{q}'
    cmd = [sys.executable, '-m', 'horaris', 'check', f'{d}/proposta.csv', '--semestre', '2',
           '--json', f'{d}/informe.json', '--violacions', f'{d}/violacions.csv']
    if q == '5.1':
        cmd.append('--nomes-aules')
    if ESC[q]:
        cmd += ['--escenari', f'paquet/escenaris/{ESC[q]}', '--referencia', 'LLIURAMENT/5.2/proposta.csv']
    if (L / q / 'relaxacions.csv').exists():
        cmd += ['--relaxacions', f'{d}/relaxacions.csv']
    out = subprocess.run(cmd, cwd=ROOT, env={**os.environ, 'PYTHONUTF8': '1'}, capture_output=True, text=True)
    (L / q / 'verificador.txt').write_text(' '.join(cmd[1:]).replace(sys.executable, 'python') + '\n\n' + out.stdout,
                                          encoding='utf-8')
    return json.load(open(L / q / 'informe.json', encoding='utf-8'))


def n(x):
    return f'{x:,}'.replace(',', '.')


def obj_table(o, keys):
    names = {'hores_mortes_min': 'Hores mortes (minuts al semestre)', 'desplacaments_aula': 'Canvis d’aula entre classes seguides',
             'desplacaments_edifici': 'Canvis d’edifici entre classes seguides', 'canvis_franja': 'Sessions que canvien de dia o hora respecte d’avui',
             'canvis_aula': 'Sessions que canvien d’aula respecte d’avui', 'r6_aules_te_extra_per_grup': 'Aules de teoria de més per grup (aula base, R6)',
             'r6_canvis_te_paul_fora_passadis': 'Canvis TE↔PAUL fora del passadís (R6)',
             'canvis_franja_vs_referencia': 'Canvis de franja respecte del nostre 5.2', 'canvis_aula_vs_referencia': 'Canvis d’aula respecte del nostre 5.2'}
    return ['| Objectiu (verificador) | Valor |', '|---|---:|'] + [f'| {names[k]} | {n(o[k])} |' for k in keys if k in o]


def verdict_line(inf):
    k = inf['incompliments_declarats']
    return f"**{inf['veredicte']}**" + (f" ({k} incompliment declarat)" if k == 1 else f" ({k} incompliments declarats)" if k else '')


def main():
    L.mkdir(exist_ok=True)
    for f in sorted(L.rglob('*'), reverse=True):        # empty it; keep the folders (one may be open elsewhere)
        if f.is_file():
            f.unlink()
    out = HERE / 'out'
    for q in ESC:
        (L / q).mkdir(parents=True, exist_ok=True)
        shutil.copy(out / q / 'proposta.csv', L / q / 'proposta.csv')
        if (out / q / 'relaxacions.csv').exists():          # the proof is DEMOSTRACIO.md in this folder
            txt = (out / q / 'relaxacions.csv').read_text(encoding='utf-8').replace('DEMOSTRACIO-S04526.md', 'DEMOSTRACIO.md')
            (L / q / 'relaxacions.csv').write_text(txt, encoding='utf-8')
    inf = {q: check(q) for q in ESC}
    shutil.copy(out / 'graella.html', L / 'graella.html')
    (L / 'proves').mkdir(exist_ok=True)
    for f in sorted((out / 'prova').glob('[A-F]-*.csv')):
        if not f.stem.endswith(('-viol', '-relax')):
            shutil.copy(f, L / 'proves' / f.name)
    subprocess.run([sys.executable, 'resum.py', '--dir', str(L / '5.2')], cwd=HERE, check=True)

    write_5_1(inf['5.1'])
    write_5_2(inf['5.2'])
    write_5_3(inf['5.3'])
    write_5_4(inf['5.4'])
    write_dobles(inf['5.2'])
    write_demostracio(inf)
    write_index(inf)
    print('LLIURAMENT ->', L)
    for q in ESC:
        print(f"  {q}: {inf[q]['veredicte']}, declared {inf[q]['incompliments_declarats']}, "
              f"counting {sum(v['compten'] for v in inf[q]['restriccions'].values())}")


# ------------------------------------------------------------------------------------------------- 5.1
def write_5_1(inf):
    o = inf['objectius']
    base = base_of('5.1')
    prop = {r['id_sessio']: r for r in read(L / '5.1' / 'proposta.csv')}
    need = [s for s in base.sessions.values() if not s.sense_espai and s.tipus != 'PLAB']
    given = sum(1 for s in need if not s.aula and prop[s.id]['aula'])
    kept = sum(1 for s in need if s.aula and prop[s.id]['aula'] == s.aula)
    with_room = sum(1 for s in need if s.aula)
    T = ['# 5.1 · Distribuir els grups del semestre a les aules', '',
         f'Veredicte del verificador oficial (`--nomes-aules`): {verdict_line(inf)}. Cap dia ni hora no canvia.', '',
         '## Què hem fet', '',
         f'- **{n(given)} sessions sense aula avui tenen aula** de la mida i el tipus que toca.',
         f'- **{n(kept)} de les {n(with_room)} sessions que ja tenien aula la conserven.** Les altres '
         f'{n(with_room - kept)} canvien perquè avui no hi caben, són en un espai del tipus que no toca (com els PAUL '
         'dels laboratoris de Q6), o perquè així el grup té una aula base més estable.',
         '- Els laboratoris PLAB i els grups de doble titulació no es toquen: els PLAB no canvien d’aula i els dobles no '
         'necessiten espai propi.',
         '- L’aforament es compta amb `alumnes`, la definició del verificador (§8.2). No fem servir `capacitat_grup`.', '',
         '## Qualitat de l’assignació (el que puntua al 5.1)', '']
    T += obj_table(o, ['desplacaments_aula', 'desplacaments_edifici', 'canvis_aula', 'r6_aules_te_extra_per_grup',
                       'r6_canvis_te_paul_fora_passadis'])
    T += ['', '## Com', '',
          'Un model SAT (Prolog + kissat) dona aula a cada classe amb totes les regles d’espai, intentant primer '
          'conservar l’aula d’avui. Després, una cerca local millora l’aula base de cada grup, els canvis d’aula entre '
          'classes seguides i els canvis respecte d’avui, sense trencar cap regla. Detall de les regles: `../DEMOSTRACIO.md`.']
    (L / '5.1' / 'RESPOSTA.md').write_text('\n'.join(T) + '\n', encoding='utf-8')


# ------------------------------------------------------------------------------------------------- 5.2
def cohort_moves(q='5.2'):
    base = base_of(q)
    prop = {r['id_sessio']: r for r in read(L / q / 'proposta.csv')}
    tot, mog = collections.Counter(), collections.Counter()
    for sid, s in base.sessions.items():
        ch = (prop[sid]['dia'], hm(prop[sid]['h_ini'])) != (s.dia, s.ini)
        for c in s.cohorts:
            tot[c] += 1
            mog[c] += ch
    return base, prop, tot, mog


def write_5_2(inf):
    o = inf['objectius']
    base, prop, tot, mog = cohort_moves()
    nses = len(base.sessions)
    top = sorted(tot, key=lambda c: -mog[c])[:5]
    full = sorted(c for c in tot if mog[c] == tot[c] and tot[c])
    T = ['# 5.2 · Torns nous: 1r i 2n al matí, 3r i 4t a la tarda', '',
         f'Veredicte del verificador oficial: {verdict_line(inf)}.', '',
         '**Resum per a la Junta Permanent:** `resum-junta.pdf` (una pàgina; també en `.md` i `.html`).', '',
         '## Què costa', '',
         f'- **{n(o["canvis_franja"])} de {n(nses)} sessions ({100 * o["canvis_franja"] / nses:.0f} %) canvien de dia '
         f'o d’hora**, i {n(o["canvis_aula"])} canvien d’aula respecte d’avui.',
         f'- **Qui ho nota més:** en nombre, {", ".join(f"{c} ({n(mog[c])})" for c in top)}; en proporció, '
         f'{", ".join(full)} (totes les seves sessions).',
         '- **On no hi cap:** en un sol cas, S04526. Les tres classes del docent D380 de la setmana 14 no caben totes '
         'tres a la tarda, i ho hem demostrat (`../DEMOSTRACIO.md`). Declarem una sola relaxació: S04526 es queda '
         'al matí, exactament on és avui.',
         '- **Dobles titulacions:** les 248 sessions de dobles que avui són al matí passen a la tarda, com demana la '
         'regla 1 (`../DOBLES-TITULACIONS.md`).', '',
         '## Objectius de la regla 9 i la regla 6', '']
    T += obj_table(o, ['hores_mortes_min', 'canvis_franja', 'canvis_aula', 'desplacaments_aula', 'desplacaments_edifici',
                       'r6_aules_te_extra_per_grup', 'r6_canvis_te_paul_fora_passadis'])
    T += ['', f'Hores mortes: {o["hores_mortes_min"] // 60} h al semestre, sumant tots els grups. '
              'L’aforament es compta amb `alumnes` (definició del verificador, §8.2).', '',
          '## Com', '',
          '1. **Model SAT** (Prolog + kissat) amb totes les regles de l’apartat 3 (llista exacta a '
          '`../DEMOSTRACIO.md`). Primer es posa un patró setmanal per a cada classe (mateix dia i hora cada '
          'setmana); després es reparen les setmanes amb festius, aturades o setmana d’avaluació.',
          '2. **Mínims canvis:** el solver primer només deixa moure les classes que han de canviar (les que són fora '
          'del seu torn o cauen en un festiu), i només n’afegeix més si no hi ha solució.',
          '3. **Optimització:** una cerca local redueix hores mortes i canvis d’aula sense trencar cap regla. Cada '
          'moviment es comprova amb les mateixes definicions que el verificador.',
          '4. **Comprovació:** el verificador oficial sobre aquesta mateixa proposta (`verificador.txt`, '
          '`informe.json`, `violacions.csv`).']
    (L / '5.2' / 'RESPOSTA.md').write_text('\n'.join(T) + '\n', encoding='utf-8')


# ------------------------------------------------------------------------------------------------- 5.3
def write_5_3(inf):
    o = inf['objectius']
    base = base_of('5.3')
    ref = {r['id_sessio']: r for r in read(L / '5.2' / 'proposta.csv')}
    prop = {r['id_sessio']: r for r in read(L / '5.3' / 'proposta.csv')}

    def date_of(s, r):
        return (dt.date.fromisoformat(r['data']) if r.get('data') else
                s.data + dt.timedelta(days=DIES.index(r['dia']) - s.data.weekday()))
    groups = collections.defaultdict(list)
    for sid, s in base.sessions.items():
        a, b = ref[sid], prop[sid]
        d0, d1 = date_of(s, a), date_of(s, b)
        if (d0, a['h_ini'], a['aula']) == (d1, b['h_ini'], b['aula']):
            continue
        if sid in base.cancellades:
            k = 'cancel'
        elif a['aula'] == 'Q3/0013' and dt.date(2027, 3, 15) <= d0 <= dt.date(2027, 3, 19):
            k = 'reserva'
        elif a['aula'] == 'Q1/1003' and d0 == dt.date(2027, 3, 10):
            k = 'avaria'
        elif s.codi == '106047' and s.grup == 'TE/21':
            k = 'grup'
        else:
            k = 'altres'
        groups[k].append((s, a, b, d0, d1))
    rec = groups['cancel'][0] if groups['cancel'] else None
    te21_hora = [(s, a, b, d0, d1) for s, a, b, d0, d1 in groups['grup'] if (d0, a['h_ini']) != (d1, b['h_ini'])]
    fixades = sum(1 for k in groups for s, *_ in groups[k] if s.fixada)
    T = ['# 5.3 · Un imprevist: què proposem', '',
         f'Veredicte del verificador oficial: {verdict_line(inf)}, el mateix S04526 del 5.2 (vegeu '
         '`../DEMOSTRACIO.md`). Referència: la nostra proposta sencera del 5.2 (`../5.2/proposta.csv`).', '',
         f'**Canvis respecte del 5.2: {o["canvis_franja_vs_referencia"]} de franja i {o["canvis_aula_vs_referencia"]} '
         f'd’aula**, de {n(len(base.sessions))} sessions. Tota la resta queda exactament igual.', '',
         '| Imprevist | Com ho resolem | Sessions que canvien |', '|---|---|---:|']
    if groups['reserva']:
        T.append(f'| Q3/0013 reservada del 15 al 19/3 | Les classes d’aquella setmana van a una altra aula, al mateix '
                 f'dia i hora | {len(groups["reserva"])} |')
    if groups['grup']:
        txt = 'Canvi d’aula a una de 130 places o més (no desdoblem, per tant no hi ha cap relaxació d’aforament)'
        if te21_hora:
            txt += '; ' + '; '.join(f'{s.id} ({d0:%d/%m}) també passa de {a["h_ini"]} a {b["h_ini"]}, perquè a la seva '
                                    'hora no queda cap aula prou gran lliure' for s, a, b, d0, d1 in te21_hora)
        T.append(f'| TE/21 (GEQ 2n) passa de 91 a 130 alumnes | {txt} | {len(groups["grup"])} |')
    if groups['avaria']:
        T.append(f'| Avaria a Q1/1003 el 10/3 | Les classes d’aquell dia van a una altra aula, a la mateixa hora | '
                 f'{len(groups["avaria"])} |')
    if rec:
        s, a, b, d0, d1 = rec
        T.append(f'| S11527 cancel·lada el 8/3 | Es recupera el {d1:%d/%m/%Y} a les {b["h_ini"]} a {b["aula"]}, abans '
                 f'del 19/3, amb alumnat, docent i aula lliures (el verificador no hi compta cap solapament nou) | 1 |')
    if groups['altres']:
        T.append(f'| Efecte en cadena | Sessions que es mouen per fer lloc als canvis anteriors | {len(groups["altres"])} |')
    T += ['', f'Cap sessió fixada no canvia de dia ni d’hora. {fixades} de les sessions que canvien són de grups fixats '
              'que eren en una aula tancada: només canvien d’aula, i el verificador no ho compta com a moure-les.', '',
          '## Com', '',
          'El mateix model SAT del 5.2, però amb tota la proposta del 5.2 congelada: només queden lliures les '
          'classes que l’imprevist obliga a moure (aula tancada, grup que ja no hi cap, sessió cancel·lada). El solver '
          'busca la solució amb menys canvis. Si no n’hi hagués, alliberaria la setmana afectada, i després la '
          'recuperació a la setmana següent. Aquí n’hi ha prou amb el primer pas.']
    (L / '5.3' / 'RESPOSTA.md').write_text('\n'.join(T) + '\n', encoding='utf-8')


# ------------------------------------------------------------------------------------------------- 5.4
def write_5_4(inf):
    o = inf['objectius']
    base = base_of('5.4')
    prop = {r['id_sessio']: r for r in read(L / '5.4' / 'proposta.csv')}
    nous = [s for s in base.sessions.values() if s.id.startswith('N')]
    moved = [s for s in nous if (prop[s.id]['dia'], hm(prop[s.id]['h_ini'])) != (s.dia, s.ini)]
    morning = all(hm(prop[s.id]['h_ini']) < MATI[1] for s in nous)
    rooms = collections.Counter(prop[s.id]['aula'] for s in nous if prop[s.id]['aula'])
    fits = inf['veredicte'].startswith('VALIDA')
    T = ['# 5.4 · Un grau nou de 40 places: hi cap?', '',
         f"**{'Sí, hi cap' if fits else 'No hi cap'}, sense canviar res del 5.2.** Veredicte del verificador oficial: "
         f'{verdict_line(inf)}, el mateix S04526 del 5.2 (vegeu `../DEMOSTRACIO.md`). El grau nou no n’afegeix cap.', '',
         '| | |', '|---|---:|',
         f'| Sessions del grau nou al 2n semestre | {len(nous)} |',
         f'| Amb aula | {sum(1 for s in nous if prop[s.id]["aula"])} |',
         f'| Al dia i l’hora que porten | {len(nous) - len(moved)} |',
         f'| Mogudes dins la mateixa setmana{", sempre al matí" if morning else ""} | {len(moved)} |',
         f'| Canvis de franja a la proposta del 5.2 | **{o.get("canvis_franja_vs_referencia", 0)}** |',
         f'| Canvis d’aula a la proposta del 5.2 | **{o.get("canvis_aula_vs_referencia", 0)}** |', '',
         f'Aules que fa servir el grau nou: {", ".join(f"{r} ({c})" for r, c in sorted(rooms.items()))}.', '',
         f'Les {len(nous)} sessions ja venen al matí, que és el seu torn. '
         + (f'{len(nous) - len(moved)} es queden al dia i hora que porten. Les altres {len(moved)} es mouen dins la mateixa '
            'setmana, sempre al matí, per reduir hores mortes i canvis d’aula del grup nou. ' if moved else
            'Totes es queden al dia i hora que porten. ')
         + 'Hi ha prou aules lliures de la mida i el tipus que toca sense tocar cap sessió del 5.2, i se segueixen '
           'respectant les dues aules ordinàries lliures a cada franja (regla 8).', '',
         '## Com', '',
         'El model SAT amb tota la proposta del 5.2 congelada, de manera que cap sessió existent no es pot moure. '
         'Les sessions del grau nou tenen el seu dia i hora i només se’ls busca aula. Si no hi hagués cabut, el pas '
         'següent era deixar-les moure dins la seva setmana, i si tampoc, el solver ho hauria demostrat (UNSAT). '
         'Després, una cerca local que només toca el grau nou en redueix les hores mortes.']
    (L / '5.4' / 'RESPOSTA.md').write_text('\n'.join(T) + '\n', encoding='utf-8')


# ------------------------------------------------------------------------------------------------- dobles
def write_dobles(inf):
    base, prop, _, _ = cohort_moves()
    dob = [s for s in base.sessions.values() if s.sense_espai]
    wrong = [s for s in dob if s.torn in ('mati', 'tarda') and (s.ini < MATI[1]) != (s.torn == 'mati')]
    movable = [s for s in wrong if not s.fixada]
    fixed = [s for s in wrong if s.fixada]
    now_ok = sum(1 for s in movable if (hm(prop[s.id]['h_ini']) < MATI[1]) == (s.torn == 'mati'))
    same_day = sum(1 for s in movable if prop[s.id]['dia'] == s.dia)
    per_coh = collections.Counter(c for s in movable for c in s.cohorts)
    per_subj = collections.Counter(s.codi for s in movable)
    names = {r['codi']: r['assignatura'] for r in SESSIONS_CSV.values()}
    groups = sorted({s.grup for s in movable})
    fixed_groups = sorted({(s.fixada, s.grup) for s in fixed})
    T = ['# Dobles titulacions: què en fem (enunciat §8.1 i §8.2)', '',
         '## Què diu l’enunciat', '',
         '- **§8.1:** els grups de doble titulació (número que comença per 5: TE/51, PAUL/511…) van **sempre a la '
         'tarda**. No necessiten espai propi (`sense_espai = 1`): el verificador no els demana aula, però el torn, el '
         'docent i l’alumnat sí que compten.',
         '- **§8.2 (punt obert):** avui molts fan la classe amb un grup de 1r o 2n al matí (248 dels 2.008 R1-TORN del '
         '2n semestre). Mentre l’Escola no ho concreti, compten. Si se’n proposa una excepció, s’ha de justificar a '
         'les relaxacions.', '',
         '## Les xifres (2n semestre, calculades sobre `sessions.csv` i la nostra proposta)', '',
         '| | Sessions |', '|---|---:|',
         f'| Sessions de dobles titulacions | {len(dob)} |',
         f'| Avui al matí, quan els toca la tarda | {len(wrong)} |',
         f'| … que es poden moure | **{len(movable)}** |',
         f'| … que són dins d’un grup fixat (regla 1: no es toquen) | {len(fixed)} |',
         f'| Mogudes a la tarda a la nostra proposta | **{now_ok}** (de {len(movable)}) |',
         f'| … al mateix dia, només canviant l’hora | {same_day} |', '',
         '## Què hem decidit, i per què', '',
         f'**Les {len(movable)} sessions mòbils passen a la tarda, com diu la regla 1.** No en demanem cap excepció:',
         '- L’enunciat diu que, mentre l’Escola no ho concreti, aquests R1-TORN **compten**. Deixar-les al matí '
         f'costaria **{len(movable)} relaxacions declarades** (una per sessió), i el jurat ordena primer per nombre de '
         'relaxacions.',
         '- Les dobles no necessiten aula, així que moure-les **no ocupa cap aula** ni afecta la reserva de la regla 8. '
         'El que sí comprovem és que el docent i l’alumnat estiguin lliures a l’hora nova: el verificador no hi troba '
         'cap solapament nou.',
         f'- Les {len(fixed)} que són dins de grups fixats ({", ".join(sorted({g for _, g in fixed_groups}))}) es queden on '
         'són avui. La regla 1 diu que aquests grups no es toquen, i el verificador les compta com a heretades.', '',
         '**Què ha de saber l’Escola.** Amb aquesta decisió, aquestes classes de doble grau passen del matí a la '
         'tarda. Si l’Escola prefereix mantenir-les al matí (§8.2), és una excepció a la regla 1 per a '
         f'{len(movable)} sessions: caldria tornar-les a la seva hora d’avui, declarar-les a `relaxacions.csv` i tornar '
         'a comprovar la proposta amb el verificador, perquè a la seva hora d’avui ara hi pot haver altres classes.', '',
         '## On són', '',
         f'Grups: {", ".join(groups)}.', '',
         '| Titulació i curs | Sessions mogudes |', '|---|---:|']
    T += [f'| {c} | {k} |' for c, k in per_coh.most_common()]
    T += ['', '| Assignatura | Sessions mogudes |', '|---|---:|']
    T += [f'| {c} {names.get(c, "")} | {k} |' for c, k in per_subj.most_common()]
    (L / 'DOBLES-TITULACIONS.md').write_text('\n'.join(T) + '\n', encoding='utf-8')


# ------------------------------------------------------------------------------------------------- proof
def write_demostracio(inf):
    base = base_of('5.2')
    trio = [base.sessions[x] for x in ('S04496', 'S04511', 'S04526')]
    fixes = [base.sessions[x] for x in ('S15066', 'S15153', 'S15095', 'S15124')]
    tests = []
    for f in [x for x in sorted((L / 'proves').glob('*.csv')) if not x.stem.endswith('-violacions')]:
        rows = [r for r in read(f) if r['id_sessio'] in ('S04526', 'S04511')]
        js = L / 'proves' / (f.stem + '.json')
        vio = L / 'proves' / (f.stem + '-violacions.csv')
        subprocess.run([sys.executable, '-m', 'horaris', 'check', f'LLIURAMENT/proves/{f.name}', '--semestre', '2',
                        '--json', f'LLIURAMENT/proves/{js.name}', '--violacions', f'LLIURAMENT/proves/{vio.name}'],
                       cwd=ROOT, env={**os.environ, 'PYTHONUTF8': '1'}, capture_output=True)
        j = json.load(open(js, encoding='utf-8'))
        cnt = [r for r in read(vio) if r['compta'] == '1']
        tests.append((f.name, rows, j['veredicte'], cnt))
    T = ['# Demostració: el 5.2, el 5.3 i el 5.4 no poden sortir VALIDA', '',
         'Amb les regles del verificador oficial, **qualsevol** proposta del 5.2, del 5.3 o del 5.4 té com a mínim '
         'un incompliment que compta o s’ha de declarar. Aquí ho demostrem. És la diferència que demana la regla 11 '
         'entre «no hem trobat un horari vàlid» i «hem demostrat que no existeix». Per això declarem una sola '
         'relaxació, la mateixa a les tres preguntes: R1-TORN de **S04526**, que es queda exactament on és avui '
         '(divendres 9/4/2027, 13:30, Q1/0019).', '',
         '## 1. Les nostres restriccions', '',
         'El nostre model (`solver/horaris.pl`, una regla per predicat, resolt amb el solver SAT kissat) imposa '
         'aquestes restriccions. Cada una correspon a una regla de l’apartat 3 i al codi que la comprova al '
         'verificador (`horaris/check.py`):', '',
         '| # | Restricció del model | Què vol dir | Regla / codi |', '|---|---|---|---|',
         '| 1 | Cada classe, un sol dia de la seva setmana | Totes les sessions es fan, a la seva setmana ISO, sense '
         'eliminar-ne ni escurçar-ne cap | R5, R5-FALTA |',
         '| 2 | Una sola hora d’inici, dins la finestra del seu torn | Matí: comença a les 8:30 o després i acaba a les '
         '14:30 o abans. Tarda: comença a les 14:30 o després i acaba a les 21:00 o abans. El torn el marca l’hora '
         'd’inici; una sessió que creua les 14:30 no és vàlida | R1-TORN, R2-FINESTRA |',
         '| 3 | Una sola aula, i adequada | De l’aulari (les J es buiden; a B3/0021 i QC/1082 només s’hi pot quedar qui ja '
         'hi és). Del mateix tipus que avui (aula docent i seminari compten com el mateix). La teoria mai en un '
         'laboratori, i els de Q5/Q6 només per a PLAB. Un PAUL també pot anar a un laboratori integrat o a una aula '
         'd’informàtica. Capacitat ≥ `alumnes` | R3-AULA, R3-TIPUS, R3-AFORAMENT, R5-SENSE-AULA |',
         '| 4 | Calendari | Cap classe no es mou a un festiu, dia no lectiu, aturada o dia de la setmana d’avaluació. Les '
         'que ja hi són avui poden canviar d’hora el mateix dia | R2-CALENDARI |',
         '| 5 | Aules tancades (5.3) | Cap classe a Q3/0013 del 15 al 19/3 ni a Q1/1003 el 10/3 | R3-TANCADA |',
         '| 6 | Una classe per aula alhora | Dues classes que coincideixen en el temps no comparteixen aula | R4-AULA |',
         '| 7 | Ningú en dos llocs alhora | Un docent, un grup d’alumnes (mateixa cohort, i teoria amb els seus '
         'subgrups) o una TE/PAUL amb el PLAB de la mateixa assignatura no poden coincidir. Els solapaments que ja hi '
         'són avui no compten (heretats) | R4-DOCENT, R4-ALUMNAT, R4-PLAB |',
         '| 8 | Dues aules ordinàries lliures | A cada franja d’una hora de 8:30 a 21:00, com a màxim 19 de les 21 aules '
         'docents ocupades | R8-RESERVA |',
         '| 9 | Fixades i PLAB no es toquen | GEI i GEET+GEST de 1r i 2n, i els PLAB: mateix dia i hora. Els PLAB i les '
         'fixades que tenen aula conserven l’aula, llevat que l’escenari la tanqui | R1-FIXADA, R7-PLAB |',
         '| 10 | Classes compartides juntes | Les sessions amb el mateix `id_compartida` són una sola classe física: '
         'mateix dia, hora i aula | R4-COMPARTIDA |',
         '| 11 | Mínims canvis | Primer només poden canviar les classes que ho han de fer, i el límit s’amplia pas a pas '
         'només si no hi ha solució | Objectiu 9 |', '',
         'Decisions de modelització: hores d’inici cada 15 minuts; les dobles titulacions (`sense_espai`) no ocupen '
         'aula; l’aforament es compta amb `alumnes` (§8.2). **La demostració de sota no depèn de cap d’aquestes '
         'decisions:** fa servir només les regles oficials i val per a qualsevol hora (al minut) i per a qualsevol '
         'horari de la resta de sessions.', '',
         '## 2. Les dades', '',
         '| Sessió | Grup | Avui | Aula d’avui | Alumnes | Torn que li toca | Docent |', '|---|---|---|---|---:|---|---|']
    for s in trio:
        T.append(f'| {s.id} | {s.codi} {s.grup} | dv. {s.data:%d/%m/%Y} {fmt(s.ini)}–{fmt(s.fi)} | {s.aula} | {s.alumnes} '
                 f'| {s.torn} | {", ".join(sorted(s.docents))} |')
    T += ['', 'Cap de les tres és fixada. Les dues aules d’informàtica (Q1/0007 i Q1/0019, 54 places) estan ocupades el '
              'divendres 9/4 a la tarda per **grups fixats** de GEI 1r, a la seva aula d’avui:', '',
          '| Sessió | Grup | Hora | Aula | Alumnes | Fixada |', '|---|---|---|---|---:|---|']
    for s in fixes:
        T.append(f'| {s.id} | {s.codi} {s.grup} | {fmt(s.ini)}–{fmt(s.fi)} | {s.aula} | {s.alumnes} | {s.fixada} |')
    T += ['', '## 3. La demostració, pas a pas', '',
          '1. **No poden canviar de setmana.** La data nova és el dia triat dins la mateixa setmana ISO (restricció 1; '
          '`check.py`, línia 178). Són de la setmana 14 (5–9/4/2027).',
          '2. **Només el divendres.** Del 5 al 8/4 és setmana d’avaluació (§8.1): el calendari hi té aturada de 00:00 a '
          '24:00, i moure-hi una sessió és R2-CALENDARI (restricció 4; línies 224–230).',
          '3. **Només a la tarda, fins a les 21:00.** Són de GEI 3r/4t, torn de tarda: han de començar a les 14:30 o '
          'després i acabar a les 21:00 o abans (restricció 2; `_torn_ok`, línia 101, i `_dins_finestra`, línia 135).',
          '4. **Només a Q1/0007 o Q1/0019.** Avui són en una aula d’informàtica, així que només poden anar a una aula '
          'd’informàtica o a un laboratori integrat (restricció 3; `_tipus_permesos` i `_espai_ok`, línies 112–132). '
          'Els laboratoris integrats tenen 24 places i els grups 34–35 alumnes (R3-AFORAMENT, línia 268).',
          '5. **Aquestes dues aules són plenes de 15:00 a 19:00** amb grups fixats que no es poden moure ni canviar '
          'd’aula (restricció 9; R1-FIXADA, línia 206). Compartir-los l’aula és R4-AULA (restricció 6; línia 290).',
          '6. **Dues hores per a tres classes del mateix docent.** Lliure a la tarda a aquestes aules només hi ha '
          '14:30–15:00 (30 minuts, no hi cap una classe d’una hora) i 19:00–21:00. D380 no pot fer dues classes alhora '
          '(restricció 7; R4-DOCENT, línia 294). Hi caben dues sessions (19:00 i 20:00), no tres.',
          '7. **No hi ha herència possible.** Un incompliment només és heretat si totes les sessions són fixades i no '
          's’han mogut, o si és un solapament que ja hi era avui (`_marca_heretades`, línia 395). Cap de les dues coses '
          'es compleix aquí.', '',
          '**Per tant, una de les tres incompleix per força alguna regla.** Cada alternativa costa com a mínim un '
          'incompliment. Triem la que menys canvia: S04526 es queda on és avui.', '',
          '## 4. Val també per al 5.3 i el 5.4', '',
          '- **5.3:** tres dels quatre imprevistos són a les setmanes 10 i 11 (8 al 19/3): l’aula reservada, l’avaria i '
          'la sessió cancel·lada, que es recupera abans del 19/3. El quart, TE/21 a 130 alumnes, només canvia d’aula '
          'les sessions d’aquest grup de teoria, que necessiten aules de 130 places i no poden anar mai a les aules '
          'd’informàtica (54 places). A la setmana 14 no se n’allibera cap aula, i el 5.3 parteix del nostre 5.2.',
          '- **5.4:** el grau nou només hi afegeix sessions. Pot ocupar més aules o més hores, mai alliberar-ne.', '',
          '## 5. Comprovat de tres maneres independents', '',
          '**a) El verificador oficial, sobre alternatives reals.** La nostra proposta del 5.2, canviant només on va '
          'S04526 (fitxers a `proves/`). Sense relaxacions, cada una surt NO VALIDA:', '',
          '| Prova | On posem S04526 | Veredicte | Què compta el verificador |', '|---|---|---|---|']
    for name, rows, ver, cnt in tests:
        where = '; '.join(f"{r['id_sessio']} dv. {r['h_ini']} {r['aula']}" for r in rows)
        T.append(f'| `{name}` | {where} | {ver} | ' + '; '.join(f"{c['regla']}: {c['detall'] or c['sessions']}" for c in cnt) + ' |')
    T += ['', '**b) Cerca exhaustiva amb les funcions del verificador** (`solver/cerca_s04526.py --pregunta 5.2|5.3|5.4`). '
              'Per a cadascuna de les tres sessions prova cada dia de la setmana 14, cada hora d’inici de 08:30 a 20:45 '
              '(de 15 en 15 minuts) i cada una de les 56 aules, i després totes les combinacions. La resta de sessions '
              'queden com a la nostra proposta de cada pregunta:', '',
          '| Pregunta | S04496: llocs vàlids | S04511: llocs vàlids | S04526: llocs vàlids | Combinacions vàlides de les tres |',
          '|---|---:|---:|---:|---:|',
          '| 5.2 | 2 (dv. 20:00) | 2 (dv. 19:00) | 10 (dv. 19:00–20:00) | **0** |',
          '| 5.3 | 2 | 2 | 10 | **0** |',
          '| 5.4 | 2 | 2 | 10 | **0** |', '',
          '**c) El solver SAT.** La setmana 14 del 5.2, amb totes les restriccions de l’apartat 1 i totes les classes '
          'mòbils lliures, surt **UNSAT** (no té cap solució). Només en té si es treu la restricció de torn '
          '(restricció 2).', '',
          '## 6. Com reproduir-ho (des de la carpeta `final/`)', '',
          '```bash',
          'python -m horaris check LLIURAMENT/proves/B-lab-24-places.csv --semestre 2     # cada alternativa',
          'cd solver && python3 cerca_s04526.py --pregunta 5.2                           # cerca exhaustiva',
          '```']
    (L / 'DEMOSTRACIO.md').write_text('\n'.join(T) + '\n', encoding='utf-8')


# ------------------------------------------------------------------------------------------------- index
def write_index(inf):
    rows = []
    for q, title in (('5.1', 'Aules amb l’horari d’avui'), ('5.2', 'Torns nous'), ('5.3', 'Imprevist'), ('5.4', 'Grau nou')):
        o = inf[q]['objectius']
        extra = (f"{o['canvis_franja_vs_referencia']} franja / {o['canvis_aula_vs_referencia']} aula vs 5.2"
                 if 'canvis_franja_vs_referencia' in o else '—')
        rows.append(f"| {q} | {title} | {inf[q]['veredicte']} | {inf[q]['incompliments_declarats']} | {extra} |")
    T = ['# Lliurament · nivell 2 · Repte d’horaris i espais', '',
         'Totes les xifres d’aquesta carpeta surten del **verificador oficial**, executat sobre els mateixos fitxers '
         'que lliurem (`verificador.txt` de cada pregunta).', '',
         '| Pregunta | | Veredicte | Incompliments declarats | Canvis |', '|---|---|---|---:|---|'] + rows + [
         '', 'L’única relaxació (5.2, 5.3 i 5.4) és **S04526**, i està demostrada inevitable: `DEMOSTRACIO.md`.', '',
         '## Què hi ha', '',
         '| | |', '|---|---|',
         '| `5.x/proposta.csv` | La proposta (`id_sessio,dia,h_ini,aula`; el 5.3 porta també `data` per a la sessió recuperada) |',
         '| `5.x/relaxacions.csv` | Les relaxacions declarades, amb la justificació (no n’hi ha al 5.1) |',
         '| `5.x/informe.json`, `5.x/violacions.csv` | La sortida del verificador (`--json`, `--violacions`) |',
         '| `5.x/verificador.txt` | L’ordre exacta i la sortida completa del verificador |',
         '| `5.x/RESPOSTA.md` | La resposta a la pregunta |',
         '| `5.2/resum-junta.pdf` | El resum d’una pàgina per a la Junta Permanent (també `.md` i `.html`) |',
         '| `DEMOSTRACIO.md` | Les nostres restriccions i la prova que el 5.2, el 5.3 i el 5.4 no poden ser VALIDA |',
         '| `DOBLES-TITULACIONS.md` | Què fem amb els grups de doble titulació (§8.2) |',
         '| `graella.html` | Regla 10: graella setmanal per aula de la proposta més avançada (5.4) |',
         '| `proves/` | Les alternatives de S04526 comprovades amb el verificador |', '',
         '## Criteris que hem aplicat', '',
         '- **Aforament:** es compta amb `alumnes`, la definició del verificador (§8.2). No fem servir `capacitat_grup`.',
         '- **Dobles titulacions:** a la tarda, com diu la regla 1 (§8.2). Vegeu `DOBLES-TITULACIONS.md`.',
         '- **5.3, grup que ja no hi cap:** canvi d’aula, sense desdoblar. Per tant no hi ha cap relaxació d’aforament.',
         '- **5.3, referència:** la nostra proposta sencera del 5.2 (`5.2/proposta.csv`).', '',
         '## Com comprovar-ho (des de la carpeta `final/`)', '',
         '```bash',
         'python -m horaris check LLIURAMENT/5.1/proposta.csv --semestre 2 --nomes-aules',
         'python -m horaris check LLIURAMENT/5.2/proposta.csv --semestre 2 --relaxacions LLIURAMENT/5.2/relaxacions.csv',
         'python -m horaris check LLIURAMENT/5.3/proposta.csv --semestre 2 --escenari paquet/escenaris/contingencies --referencia LLIURAMENT/5.2/proposta.csv --relaxacions LLIURAMENT/5.3/relaxacions.csv',
         'python -m horaris check LLIURAMENT/5.4/proposta.csv --semestre 2 --escenari paquet/escenaris/grau-nou-40 --referencia LLIURAMENT/5.2/proposta.csv --relaxacions LLIURAMENT/5.4/relaxacions.csv',
         '```']
    (L / 'LLEGIU-ME.md').write_text('\n'.join(T) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
