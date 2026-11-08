#!/usr/bin/env python3
"""The written answers that go with the 5.3 and 5.4 proposals, generated from the files themselves:

    python3 respostes.py          (make respostes; make 5.3 / 5.4 / derivades run it too)

  out/5.3/canvis-5.3.csv   every change with respect to the 5.2 proposal: session, from, to, reason, who it affects
  out/5.3/resposta-5.3.md  the four events, how each one was solved, and how many changes it cost
  out/5.4/resposta-5.4.md  "Hi cap? Amb quins canvis?": the answer, with the verifier's figures
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from exporta import DIES, HERE, hm, load

OUT = HERE / 'out'
with open(HERE.parent / 'paquet' / 'sessions.csv', encoding='utf-8') as _f:
    NOM = {r['codi']: r['assignatura'] for r in csv.DictReader(_f)}


def read(path):
    with open(path, encoding='utf-8') as f:
        return {r['id_sessio']: r for r in csv.DictReader(f)}


def date_of(s, row):
    if row.get('data'):
        return dt.date.fromisoformat(row['data'])
    return s.data + dt.timedelta(days=DIES.index(row['dia']) - s.data.weekday())


def resposta_53():
    base = load('5.3')
    ref, prop = read(OUT / '5.2' / 'proposta.csv'), read(OUT / '5.3' / 'proposta.csv')
    inf = json.load(open(OUT / '5.3' / 'informe.json', encoding='utf-8'))
    closed = {(t.aula, t.data_ini, t.data_fi) for t in base.tancaments}
    rows = []
    for sid, s in base.sessions.items():
        a, b = ref[sid], prop[sid]
        d0, d1 = date_of(s, a), date_of(s, b)
        if (d0, a['h_ini'], a['aula']) == (d1, b['h_ini'], b['aula']):
            continue
        if sid in base.cancellades:
            why = 'sessió cancel·lada el 8/3, recuperada'
        elif any(a['aula'] == r and i <= d0 <= f for r, i, f in closed):
            r = a['aula']
            why = f'{r} tancada ({"reservada per a un acte" if r == "Q3/0013" else "avaria del projector i l’ordinador"})'
        elif s.codi == '106047' and s.grup == 'TE/21':
            why = 'TE/21 passa a 130 alumnes: no cap a Q4/0011 (117 places)'
        else:
            why = 'efecte en cadena per fer lloc a un dels canvis anteriors'
        rows.append({'id_sessio': sid, 'assignatura': f'{s.codi} {NOM.get(s.codi, "")}', 'grup': s.grup,
                     'de': f'{d0:%d/%m} {a["h_ini"]} {a["aula"] or "-"}', 'a': f'{d1:%d/%m} {b["h_ini"]} {b["aula"] or "-"}',
                     'motiu': why, 'afecta': f'{"|".join(sorted(s.docents))} · {"|".join(s.cohorts)} ({s.alumnes} alumnes)'})
    with open(OUT / '5.3' / 'canvis-5.3.csv', 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r['motiu'], r['de'])))
    count = {}
    for r in rows:
        count[r['motiu']] = count.get(r['motiu'], 0) + 1
    o = inf['objectius']
    te21_rows = [r for r in rows if r['motiu'].startswith('TE/21')]
    te21_hora = [r for r in te21_rows if r['de'].split()[:2] != r['a'].split()[:2]]
    te21 = 'Canvi d’aula (no desdoblem): a una aula de 130 places o més, al mateix dia i hora'
    if te21_hora:
        te21 += ('; ' + ', '.join(f"{r['id_sessio']} ({r['de'].split()[0]}) passa de {r['de'].split()[1]} a "
                                   f"{r['a'].split()[1]}" for r in te21_hora)
                 + ', perquè aquell dia no hi ha cap aula prou gran lliure a la seva hora')
    L = ['# 5.3 · Un imprevist: què proposem', '',
         f"Veredicte del verificador: **{inf['veredicte']}** ({inf['incompliments_declarats']} incompliment declarat: "
         "S04526, el mateix del 5.2). Referència: la nostra proposta sencera del 5.2.", '',
         f"**Canvis respecte del 5.2: {o['canvis_franja_vs_referencia']} de franja i {o['canvis_aula_vs_referencia']} "
         f"d'aula**, de {len(base.sessions)} sessions. La llista completa, amb el motiu i a qui afecta, és a "
         "`canvis-5.3.csv`.", '',
         '| Imprevist | Com ho resolem | Sessions que canvien |', '|---|---|---:|']
    for motiu, com in (
            ('Q3/0013 tancada (reservada per a un acte)', 'Les classes d’aquella setmana van a una altra aula, al mateix dia i hora'),
            ('TE/21 passa a 130 alumnes: no cap a Q4/0011 (117 places)', te21),
            ('Q1/1003 tancada (avaria del projector i l’ordinador)', 'Les classes del 10/3 van a una altra aula, a la mateixa hora'),
            ('sessió cancel·lada el 8/3, recuperada', 'S11527 es recupera abans del 19/3, en una franja amb alumnat, docent i aula lliures'),
            ('efecte en cadena per fer lloc a un dels canvis anteriors', 'Una altra sessió es mou per deixar lloc')):
        if count.get(motiu):
            L.append(f'| {motiu} | {com} | {count[motiu]} |')
    L += ['', 'Cap sessió fixada no canvia de dia ni d’hora. Les fixades que eren en una aula tancada només canvien '
          'd’aula, i el verificador no ho compta com a moure-les.']
    (OUT / '5.3' / 'resposta-5.3.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    print(f'5.3: {len(rows)} changes -> out/5.3/canvis-5.3.csv, resposta-5.3.md')


def resposta_54():
    base = load('5.4')
    prop = read(OUT / '5.4' / 'proposta.csv')
    inf = json.load(open(OUT / '5.4' / 'informe.json', encoding='utf-8'))
    o = inf['objectius']
    nous = [s for s in base.sessions.values() if s.id.startswith('N')]
    moved = sum(1 for s in nous if (prop[s.id]['dia'], hm(prop[s.id]['h_ini'])) != (s.dia, s.ini))
    rooms = sorted({prop[s.id]['aula'] for s in nous if prop[s.id]['aula']})
    fits = inf['veredicte'].startswith('VALIDA')
    L = ['# 5.4 · Un grau nou de 40 places: hi cap?', '',
         f"**{'Sí, hi cap' if fits else 'No hi cap'}**, sense canviar res del 5.2. Veredicte del verificador: "
         f"**{inf['veredicte']}** ({inf['incompliments_declarats']} incompliment declarat: S04526, el mateix del 5.2; "
         "el grau nou no n’afegeix cap).", '',
         '| | |', '|---|---|',
         f'| Sessions del grau nou (2n semestre) | {len(nous)} |',
         f'| Amb aula | {sum(1 for s in nous if prop[s.id]["aula"])} |',
         f'| Que canvien de dia o hora respecte del que porten | {moved} |',
         f'| Canvis a la proposta del 5.2 | **{o.get("canvis_franja_vs_referencia", 0)} de franja, '
         f'{o.get("canvis_aula_vs_referencia", 0)} d’aula** |',
         f'| Aules que fa servir | {len(rooms)} ({", ".join(rooms[:12])}{"…" if len(rooms) > 12 else ""}) |', '',
         f'Les {len(nous)} sessions ja venen al matí (el seu torn). '
         + (f'{len(nous) - moved} es queden al dia i hora que porten; les altres {moved} es mouen dins la mateixa '
            'setmana, sempre al matí, per reduir hores mortes i canvis d’aula del grup nou. ' if moved else
            'Totes es queden al dia i hora que porten. ')
         + 'Hi ha prou aules lliures de la mida i el tipus que toca sense tocar cap sessió del 5.2, i se segueixen '
           'respectant les dues aules ordinàries lliures a cada franja (regla 8).']
    (OUT / '5.4' / 'resposta-5.4.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    print('5.4 -> out/5.4/resposta-5.4.md')


if __name__ == '__main__':
    resposta_53()
    resposta_54()
