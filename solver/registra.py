#!/usr/bin/env python3
"""Register a proposal you submitted to the xaman, with its score, so that pesos.py learns from it and
millora.py --des-de millor can start from it.

    python3 registra.py --pregunta 5.2 --puntuacio 74                 # registers out/5.2/proposta.csv
    python3 registra.py --pregunta 5.2 --puntuacio 74 --fitxer ../entregues/5.2-run1.csv

It copies the file to out/<q>/variants/extra-N.csv, checks it with the official verifier and appends a row (its seven
objectives, verdict and score) to out/<q>/variants/rondaextra.csv. Same format as the variant rounds.
"""
from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

from variants import CHECK, HERE, ORDER, qdir, verify


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pregunta', required=True, choices=sorted(CHECK))
    ap.add_argument('--puntuacio', required=True, help='the score the xaman gave it')
    ap.add_argument('--fitxer', type=Path, help='default: <dir>/proposta.csv')
    ap.add_argument('--dir', help='folder of the proposals, relative to solver/ (default out/<q>; e.g. out/truc/5.2)')
    a = ap.parse_args()
    q = a.pregunta
    d = qdir(q, a.dir)
    src = a.fitxer or d / 'proposta.csv'
    vd = d / 'variants'
    vd.mkdir(parents=True, exist_ok=True)
    n = 1 + max([int(p.stem.split('-')[1]) for p in vd.glob('extra-*.csv')] or [0])
    dst = vd / f'extra-{n}.csv'
    shutil.copy(src, dst)
    ver, decl, obj = verify(q, dst, d)
    table = vd / 'rondaextra.csv'
    new = not table.exists()
    with open(table, 'a', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        if new:
            w.writerow(['variant', 'pesos', 'veredicte', 'declarades', *ORDER, 'puntuacio'])
        w.writerow([dst.stem, f'registered from {src.name}', ver, decl, *[obj[o] for o in ORDER], a.puntuacio])
    print(f'{dst.stem}: {ver}, score {a.puntuacio} -> {table}')
    print('  ' + '  '.join(f'{o}={obj[o]}' for o in ORDER))
    if not ver.startswith('VALIDA'):
        print('  WARNING: not valid for the verifier: pesos.py will use it, millora.py will never start from it')


if __name__ == '__main__':
    main()
