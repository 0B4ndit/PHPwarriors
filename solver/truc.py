#!/usr/bin/env python3
"""The "truc" family (out/truc/<q>): the same proposals, but the fixed GEI / GEET+GEST 1r-2n sessions that are in the
afternoon today with no room are left WITHOUT a room. They pay R5-SENSE-AULA (declared) instead of R1-TORN: the same
number of declared violations (459 in 5.2), but their R1-TORN becomes inherited and their rooms are free for the rest.
Only to test whether the xaman scores it better: rule 5 says "totes les sessions amb aula", so the jury may not accept
the justification.

    python3 truc.py --font out/5.2 --dir out/truc/5.2      (make truc does it)

Copies <font>/proposta.csv and proposta-sat.csv into <dir> with those sessions' room blanked (the previous
<dir>/proposta.csv is kept as proposta-anterior.csv, so millora --des-de millor can start from it), rewrites
relaxacions.csv (their R1-TORN rows become one R5-SENSE-AULA row) and starts <dir>/pesos.txt from the learnt weights.
5.3 and 5.4 are not made here: the SAT rebuilds them on top of out/truc/5.2 (exporta.py --sense-aula).
"""
from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

import exporta

HERE = Path(__file__).resolve().parent


def blank(src: Path, dst: Path, ids: set) -> int:
    with open(src, encoding='utf-8') as f:
        rd = csv.DictReader(f)
        fields, rows = rd.fieldnames, list(rd)
    n = 0
    for r in rows:
        if r['id_sessio'] in ids and r['aula']:
            r['aula'] = ''
            n += 1
    with open(dst, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--font', type=Path, default=HERE / 'out' / '5.2', help='the normal proposal folder')
    ap.add_argument('--dir', type=Path, default=HERE / 'out' / 'truc' / '5.2', help='the truc folder')
    ap.add_argument('--pregunta', default='5.2')
    a = ap.parse_args()
    exporta.SENSE_AULA = True
    exporta.load(a.pregunta)
    ids = exporta.NOROOM
    a.dir.mkdir(parents=True, exist_ok=True)
    if (a.dir / 'proposta.csv').exists():
        shutil.copy(a.dir / 'proposta.csv', a.dir / 'proposta-anterior.csv')
    for name in ('proposta-sat.csv', 'proposta.csv'):
        n = blank(a.font / name, a.dir / name, ids)
        print(f'{a.dir / name}: {n} rooms removed')
    with open(a.font / 'relaxacions.csv', encoding='utf-8') as f:
        rel = list(csv.DictReader(f))
    with open(a.dir / 'relaxacions.csv', 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['restriccio', 'sessions', 'justificacio'])
        for r in rel:
            ss = [x for x in r['sessions'].split('|') if not (r['restriccio'] == 'R1-TORN' and x in ids)]
            if ss:
                w.writerow([r['restriccio'], '|'.join(ss), r['justificacio']])
        w.writerow(['R5-SENSE-AULA', '|'.join(sorted(ids)), exporta.JUST_R5])
    print(f'{a.dir / "relaxacions.csv"}: R1-TORN of {len(ids)} sessions -> R5-SENSE-AULA')
    learnt = HERE / f'pesos-{a.pregunta}.txt'
    if learnt.exists() and not (a.dir / 'pesos.txt').exists():
        shutil.copy(learnt, a.dir / 'pesos.txt')
        print(f'{a.dir / "pesos.txt"}: starts from {learnt.name}')


if __name__ == '__main__':
    main()
