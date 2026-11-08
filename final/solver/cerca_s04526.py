#!/usr/bin/env python3
"""Brute force with the OFFICIAL verifier: can S04496, S04511, S04526 (teacher D380, week 14) be placed with no
violation that counts, everything else as in out/5.2/proposta.csv?

    python3 cerca_s04526.py [--pregunta 5.2|5.3|5.4]

For each of the three sessions: every weekday of week 14 x every start 08:30..20:45 (15 min) x every room. Each
candidate is checked with the verifier's own functions on the timetable of that date (all other sessions as in the
proposal, the other two of the three removed). Then every combination of the per-session survivors is checked
together. Prints how many placements survive at each stage.
"""
from __future__ import annotations

import csv
import datetime as dt
import itertools
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import horaris.check as C  # noqa: E402
from horaris.model import DIES, carrega_base, fmt, hm  # noqa: E402

import argparse
ap = argparse.ArgumentParser()
ap.add_argument('--pregunta', default='5.2', choices=['5.2', '5.3', '5.4'])
Q = ap.parse_args().pregunta
ESC = {'5.2': None, '5.3': 'contingencies', '5.4': 'grau-nou-40'}[Q]
TRIO = ('S04496', 'S04511', 'S04526')
base = carrega_base(ROOT / 'paquet', semestre=2, escenari=ROOT / 'paquet' / 'escenaris' / ESC if ESC else None)
print(f'{Q}: everything else as in out/{Q}/proposta.csv' + (f', scenario {ESC}' if ESC else ''))
PARTIDA = C._solapaments_de_partida(base)
C._solapaments_de_partida = lambda b: PARTIDA          # computed once (it is the same every call)
prop = {r['id_sessio']: r for r in csv.DictReader(open(HERE / 'out' / Q / 'proposta.csv', encoding='utf-8'))}


def place(sid, dia, h, aula, data_txt=''):
    s = base.sessions[sid]
    data = (dt.date.fromisoformat(data_txt) if data_txt else
            s.data + dt.timedelta(days=DIES.index(dia) - s.data.weekday()))
    return C.Colocada(s, data, hm(h), aula)


def counting(col, focus):
    inf = C.Informe()
    C._per_sessio(base, col, inf)
    C._compartides_i_aforament(base, col, inf)
    C._solapaments(base, col, inf)
    C._reserva(base, col, inf)
    C._marca_heretades(base, col, inf)
    return [v for v in inf.violacions if v.compta and (set(v.sessions) & focus or not v.sessions)]


rest = {sid: place(sid, r['dia'], r['h_ini'], r['aula'], r.get('data', '')) for sid, r in prop.items() if sid not in TRIO}
week = base.sessions['S04526'].data.isocalendar()[:2]
by_date = {}
for sid, c in rest.items():
    if c.data.isocalendar()[:2] == week:
        by_date.setdefault(c.data, {})[sid] = c
starts = [f'{m // 60:02d}:{m % 60:02d}' for m in range(510, 1260, 15)]
rooms = sorted(base.aules)
ok = {}
for sid in TRIO:
    ok[sid] = []
    for dia in DIES:
        for h in starts:
            for aula in rooms:
                c = place(sid, dia, h, aula)
                col = dict(by_date.get(c.data, {}))
                col[sid] = c
                if not counting(col, {sid}):
                    ok[sid].append((dia, h, aula))
    print(f'{sid}: {len(ok[sid])} placements with nothing counting on their own', flush=True)
    for x in ok[sid][:12]:
        print('    ', x)
found = 0
for combo in itertools.product(*(ok[s] for s in TRIO)):
    cs = {sid: place(sid, *p) for sid, p in zip(TRIO, combo)}
    dates = {c.data for c in cs.values()}
    col = {k: v for d in dates for k, v in by_date.get(d, {}).items()}
    col.update(cs)
    if not counting(col, set(TRIO)):
        found += 1
        print('VALID placement for all three:', combo)
        if found >= 5:
            break
print('combinations with nothing counting:', found)
