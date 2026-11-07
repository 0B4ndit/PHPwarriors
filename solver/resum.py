#!/usr/bin/env python3
"""One-page summary for the Junta Permanent (enunciat 5.2), from out/5.2/proposta.csv.

    python3 resum.py --dir out/5.2          -> out/5.2/resum-junta.md

Fields asked by the brief: peak of simultaneous sessions in the morning and in the afternoon against the ordinary
rooms available; rooms missing / spare by size; sessions moved per degree and year; the exceptions to rule 1 we ask
for, each with its reason. Everything is computed from the proposal and the package, nothing is typed by hand.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
from pathlib import Path

from exporta import DIES, load, week_of, monday
from horaris.model import hm

MATI_FI = 870


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', type=Path, default=Path(__file__).resolve().parent / 'out' / '5.2')
    ap.add_argument('--pregunta', default='5.2')
    a = ap.parse_args()
    base = load(a.pregunta)
    prop = {r['id_sessio']: r for r in csv.DictReader(open(a.dir / 'proposta.csv', encoding='utf-8'))}
    informe = json.load(open(a.dir / 'informe.json', encoding='utf-8'))
    relax = list(csv.DictReader(open(a.dir / 'relaxacions.csv', encoding='utf-8')))
    aules = base.aules
    ordinaries = sorted(r for r, x in aules.items() if x.ordinaria)
    generals = sorted(r for r, x in aules.items() if x.tipus in ('Aules docents', 'Seminaris'))

    # placed sessions (a shared class counts once), with their new date, start and end
    placed = {}
    for sid, s in base.sessions.items():
        p = prop[sid]
        date = monday(week_of(s.data)) + dt.timedelta(days=DIES.index(p['dia']))
        ini = hm(p['h_ini'])
        key = s.compartida or sid
        n = placed.get(key, (None, None, None, None, 0))[4] + (0 if s.sense_espai else s.alumnes)
        placed[key] = (date, ini, ini + s.durada, p['aula'], n)

    # 1. peak of simultaneous classes in ordinary rooms, morning / afternoon (15-minute instants)
    load_ = collections.Counter()
    for date, ini, fi, room, _ in placed.values():
        if room in ordinaries:
            for t in range(ini, fi, 15):
                load_[(date, t)] += 1
    peak = {}
    for (date, t), n in load_.items():
        torn = 'matí' if t < MATI_FI else 'tarda'
        if n > peak.get(torn, (0,))[0]:
            peak[torn] = (n, date, t)

    # 2. rooms by size: for every capacity level, the peak number of classes that need at least that size
    #    (placed in a general room: aula docent or seminari) against the general rooms that big
    levels = sorted({aules[r].capacitat for r in generals})
    need = collections.defaultdict(collections.Counter)    # level -> (date, t) -> classes needing >= level
    for date, ini, fi, room, n in placed.values():
        if room not in generals:
            continue
        for lv in levels:
            prev = max([x for x in levels if x < lv], default=0)
            if n > prev:
                for t in range(ini, fi, 15):
                    need[lv][(date, t)] += 1
    size_rows = []
    for lv in levels:
        supply = sum(1 for r in generals if aules[r].capacitat >= lv)
        dem = max(need[lv].values(), default=0)
        size_rows.append((lv, supply, dem, supply - dem))

    # 3. sessions moved (day or hour) per degree and year
    moved, total = collections.Counter(), collections.Counter()
    for sid, s in base.sessions.items():
        p = prop[sid]
        ch = (p['dia'], hm(p['h_ini'])) != (s.dia, s.ini)
        for c in s.cohorts:
            total[c] += 1
            moved[c] += ch
    n_moved = sum(1 for sid, s in base.sessions.items() if (prop[sid]['dia'], hm(prop[sid]['h_ini'])) != (s.dia, s.ini))
    obj = informe['objectius']

    hh = lambda t: f'{t // 60}:{t % 60:02d}'
    L = ['# Resum per a la Junta Permanent · torns nous (pregunta 5.2)', '',
         f"Proposta: `proposta.csv` · {len(base.sessions)} sessions del 2n semestre · veredicte del verificador: "
         f"**{informe['veredicte']}** ({informe.get('incompliments_declarats', 0)} incompliments declarats, "
         'vegeu les excepcions).', '',
         '## 1. Pic de sessions simultànies davant de les aules ordinàries', '',
         f'Aules ordinàries: {len(ordinaries)}, de les quals 2 queden sempre lliures (regla 8): '
         f'**{len(ordinaries) - 2} disponibles** a cada franja.', '',
         '| Torn | Pic de classes alhora en aules ordinàries | Quan |', '|---|---:|---|']
    for torn in ('matí', 'tarda'):
        if torn in peak:
            n, d, t = peak[torn]
            L.append(f'| {torn} | **{n}** de {len(ordinaries) - 2} | {d:%d/%m/%Y} {hh(t)} |')
    L += ['', '## 2. Aules per mida (aules docents + seminaris)', '',
          'Per a cada mida: quantes aules en tenen almenys aquesta capacitat, i el màxim de classes simultànies '
          'que la necessiten (alumnes per sobre de la mida anterior). Marge negatiu = falten aules d\'aquesta mida.', '',
          '| Capacitat ≥ | Aules | Pic de classes que la necessiten | Marge |', '|---:|---:|---:|---:|']
    L += [f'| {lv} | {sup} | {dem} | {"**" + str(m) + "**" if m <= 1 else m} |' for lv, sup, dem, m in size_rows]
    tight = [lv for lv, _, _, m in size_rows if m <= 1]
    L += ['', f"Mides justes (marge ≤ 1): {', '.join(map(str, tight)) or 'cap'}. No en falta cap: "
              'totes les sessions tenen aula (R5) sense superar l\'aforament (R3).', '',
          '## 3. Sessions mogudes (dia o hora) per titulació i curs', '',
          f'En total **{n_moved}** sessions canvien de franja i {obj["canvis_aula"]} d\'aula respecte d\'avui '
          f'(hores mortes {obj["hores_mortes_min"] // 60} h, {obj["desplacaments_aula"]} canvis d\'aula entre classes '
          f'seguides, {obj["desplacaments_edifici"]} d\'edifici).', '',
          '| Titulació i curs | Sessions | Mogudes | % |', '|---|---:|---:|---:|']
    for c in sorted(total, key=lambda c: (-moved[c] / total[c], c)):
        if moved[c]:
            L.append(f'| {c} | {total[c]} | {moved[c]} | {100 * moved[c] / total[c]:.0f} % |')
    L += ['', '## 4. Excepcions a la regla 1 que demanem', '']
    for r in relax:
        ids = [x for x in r['sessions'].split('|') if x]
        L.append(f"- **{r['restriccio']}**, {len(ids)} sessions"
                 + (f" ({', '.join(ids)})" if len(ids) <= 5 else '') + f": {r['justificacio']}")
    if not relax:
        L.append('- Cap.')
    out = a.dir / 'resum-junta.md'
    out.write_text('\n'.join(L) + '\n', encoding='utf-8')
    print(f'Junta summary -> {out}')


if __name__ == '__main__':
    main()
