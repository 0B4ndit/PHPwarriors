#!/usr/bin/env python3
"""The whole year ("Curs complet" on the xaman): semester 1 solved by the SAT alone (out/any/s1/<q>, make any) joined
with our semester-2 proposals (out/<q>), checked by the official verifier on the whole year (no --semestre).

    python3 any.py          -> out/any/<q>/{proposta.csv, relaxacions.csv, informe.json}  + ../entregues/curs-complet-*

    5.1  s1 5.1 (rooms only) + out/5.1
    5.2  s1 5.2 (new shifts) + out/5.2
    5.3  s1 5.2 + out/5.3      (the contingencies are all in March 2027; reference: the whole-year 5.2)
    5.4  s1 5.4 (the new degree's semester-1 sessions on top of s1 5.2) + out/5.4   (reference: the whole-year 5.2)
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / 'out' / 'any'
S1 = {'5.1': '5.1', '5.2': '5.2', '5.3': '5.2', '5.4': '5.4'}
ESC = {'5.3': 'contingencies', '5.4': 'grau-nou-40'}


def read(path: Path):
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))


def join(q):
    d = OUT / q
    d.mkdir(parents=True, exist_ok=True)
    parts = [OUT / 's1' / S1[q], HERE / 'out' / q]
    rows = []
    for p in parts:
        if not (p / 'proposta.csv').exists():
            sys.exit(f'{p / "proposta.csv"} missing: run "make any" (semester 1) / "make {q}" (semester 2)')
        rows += read(p / 'proposta.csv')
    ids = [r['id_sessio'] for r in rows]
    if len(ids) != len(set(ids)):
        sys.exit(f'{q}: a session appears in both semesters')
    fields = ['id_sessio', 'dia', 'h_ini', 'aula'] + (['data'] if any(r.get('data') for r in rows) else [])
    with open(d / 'proposta.csv', 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    rel = [r for p in parts if (p / 'relaxacions.csv').exists() for r in read(p / 'relaxacions.csv')]
    if rel:
        with open(d / 'relaxacions.csv', 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow(['restriccio', 'sessions', 'justificacio'])
            for r in rel:
                w.writerow([r['restriccio'], r['sessions'], r['justificacio']])
    cmd = [sys.executable, '-m', 'horaris', 'check', f'solver/out/any/{q}/proposta.csv',
           '--json', f'solver/out/any/{q}/informe.json', '--violacions', f'solver/out/any/{q}/violacions.csv']
    if q == '5.1':
        cmd.append('--nomes-aules')
    if q in ESC:
        cmd += ['--escenari', f'paquet/escenaris/{ESC[q]}', '--referencia', 'solver/out/any/5.2/proposta.csv']
    if rel:
        cmd += ['--relaxacions', f'solver/out/any/{q}/relaxacions.csv']
    subprocess.run(cmd, cwd=ROOT, env={**os.environ, 'PYTHONUTF8': '1'}, capture_output=True)
    inf = json.load(open(d / 'informe.json', encoding='utf-8'))
    keep = ROOT / 'entregues'
    shutil.copy(d / 'proposta.csv', keep / f'curs-complet-{q}.csv')
    if rel:
        shutil.copy(d / 'relaxacions.csv', keep / f'curs-complet-{q}-relaxacions.csv')
    o = inf['objectius']
    bad = {k: v['compten'] for k, v in inf['restriccions'].items() if v['compten']}
    decl = {k: v['declarades'] for k, v in inf['restriccions'].items() if v['declarades']}
    print(f'{q}: {len(rows)} sessions  {inf["veredicte"]}  declared {inf["incompliments_declarats"]} {decl}'
          + (f'  COUNTING {bad}' if bad else ''))
    print('     ' + '  '.join(f'{k}={v}' for k, v in o.items() if k != 'sessions_avaluades'))


if __name__ == '__main__':
    for q in sys.argv[1:] or ('5.1', '5.2', '5.3', '5.4'):
        join(q)
