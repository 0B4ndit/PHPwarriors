#!/usr/bin/env python3
"""Trivial proposals that declare everything: a probe of how the xaman scores, NOT something to hand in.

    python3 trivial.py                    -> out/trivial/<q>/<variant>/  (+ copies in ../entregues/trivial-*)

Every session keeps today's day and hour (so canvis_franja = 0). Two variants:
    avui         today's room too (canvis_aula = 0); the sessions with no room today stay without one
    sense-aules  no room at all, except the PLAB labs (rule 7: their room cannot change); the room objectives go to 0
    fixes        a room only for the fixed sessions (R1, R7) and labs: no R1-FIXADA, the rest without a room
Then the official verifier runs, and EVERY violation that counts is declared, in one relaxacions.csv row per rule
(R8-RESERVA with the "*" wildcard). Non-relaxable violations are removed instead: R3-TANCADA (a room closed by the 5.3
scenario) -> the session loses that room; R5-RECUPERACIO -> the cancelled session is recovered the next weekday
at the same hour. 5.3 and 5.4 use the same variant of the trivial 5.2 as their reference (0 changes).

The jury ranks "VALIDA AMB RELAXACIONS" by the number of declared violations (incompliments_declarats, thousands
here) and rejects a relaxation "sense una justificació que s'aguanti": this would lose to any real proposal.
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
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from horaris.model import DIES, carrega_base, fmt  # noqa: E402

PAQUET = ROOT / 'paquet'
ESC = {'5.1': None, '5.2': None, '5.3': 'contingencies', '5.4': 'grau-nou-40'}
NO_RELAX = {'R0-FORMAT', 'R0-HORARI', 'R5-FALTA', 'R5-RECUPERACIO', 'R3-TANCADA'}
WHY = ("Proposta trivial per contrastar la puntuació orientativa: es manté l'horari d'avui (dia i hora) i es declara "
       "tot el que incompleix. No és una proposta per lliurar.")


def check(q, d: Path, ref: Path | None):
    rel = d / 'relaxacions.csv'
    cmd = [sys.executable, '-m', 'horaris', 'check', str((d / 'proposta.csv').relative_to(ROOT)), '--semestre', '2',
           '--json', str((d / 'informe.json').relative_to(ROOT)),
           '--violacions', str((d / 'violacions.csv').relative_to(ROOT))]
    if q == '5.1':
        cmd.append('--nomes-aules')
    if ESC[q]:
        cmd += ['--escenari', f'paquet/escenaris/{ESC[q]}', '--referencia', str(ref.relative_to(ROOT))]
    if rel.exists():
        cmd += ['--relaxacions', str(rel.relative_to(ROOT))]
    subprocess.run(cmd, cwd=ROOT, env={**os.environ, 'PYTHONUTF8': '1'}, capture_output=True)
    with open(d / 'violacions.csv', encoding='utf-8') as f:
        viol = list(csv.DictReader(f))
    return json.load(open(d / 'informe.json', encoding='utf-8')), viol


def write(d: Path, base, rows, data):
    with open(d / 'proposta.csv', 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        extra = ['data'] if base.cancellades else []
        w.writerow(['id_sessio', 'dia', 'h_ini', 'aula', *extra])
        for sid in base.ordre:
            w.writerow([sid, *rows[sid], *([data.get(sid, '')] if extra else [])])


def build(q, variant):
    base = carrega_base(PAQUET, semestre=2, escenari=PAQUET / 'escenaris' / ESC[q] if ESC[q] else None)
    d = HERE / 'out' / 'trivial' / q / variant
    d.mkdir(parents=True, exist_ok=True)
    (d / 'relaxacions.csv').unlink(missing_ok=True)
    ref = HERE / 'out' / 'trivial' / '5.2' / variant / 'proposta.csv'
    rows, data = {}, {}
    for sid in base.ordre:
        s = base.sessions[sid]
        keep = variant == 'avui' or s.tipus == 'PLAB' or (variant == 'fixes' and s.fixada)
        room = s.aula if keep else ''
        rows[sid] = [s.dia, fmt(s.ini), room]
    for sid, until in base.cancellades.items():           # 5.3: recover it the next weekday, same hour
        s = base.sessions[sid]
        day = s.data + dt.timedelta(days=1)
        while day.weekday() >= 5 or day in base.dies_sense_classe:
            day += dt.timedelta(days=1)
        assert day <= until, sid
        rows[sid][0] = DIES[day.weekday()]
        data[sid] = day.isoformat()
    for _ in range(3):                                     # remove what cannot be declared
        write(d, base, rows, data)
        inf, viol = check(q, d, ref)
        bad = [v for v in viol if v['compta'] == '1' and v['regla'] in NO_RELAX]
        if not bad:
            break
        for v in bad:
            if v['regla'] != 'R3-TANCADA':
                sys.exit(f'{q} {variant}: cannot fix {v}')
            for sid in v['sessions'].split('|'):
                rows[sid][2] = ''
    by_rule = collections.defaultdict(set)
    for v in viol:
        if v['compta'] == '1':
            by_rule[v['regla']] |= set(v['sessions'].split('|')) if v['sessions'] else {'*'}
    with open(d / 'relaxacions.csv', 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['restriccio', 'sessions', 'justificacio'])
        for rule, ids in sorted(by_rule.items()):
            w.writerow([rule, '*' if '*' in ids else '|'.join(sorted(ids)), WHY])
    inf, viol = check(q, d, ref)
    keep = ROOT / 'entregues'
    shutil.copy(d / 'proposta.csv', keep / f'trivial-{q}-{variant}.csv')
    shutil.copy(d / 'relaxacions.csv', keep / f'trivial-{q}-{variant}-relaxacions.csv')
    decl = {k: v['declarades'] for k, v in inf['restriccions'].items() if v['declarades']}
    obj = {k: v for k, v in inf['objectius'].items() if k != 'sessions_avaluades'}
    print(f'{q} {variant:11} {inf["veredicte"]}  declared {inf["incompliments_declarats"]} in {len(by_rule)} rows {decl}')
    print(f'{"":16} {obj}')


def main():
    for variant in sys.argv[1:] or ('avui', 'sense-aules', 'fixes'):
        for q in ('5.2', '5.1', '5.3', '5.4'):             # 5.2 first: 5.3 and 5.4 use it as their reference
            build(q, variant)


if __name__ == '__main__':
    main()
