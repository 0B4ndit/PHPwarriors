#!/usr/bin/env python3
"""Estimate how much the xaman values each objective, from the scores of the variants (variants.py).

    python3 pesos.py --pregunta 5.1             # reads every out/5.1/variants/ronda*.csv with a `puntuacio`

Model:  score ~ a - sum_k w_k * objective_k / REF_k      (REF = the objective in the SAT proposal, as in millora.py)
fitted by least squares with a little ridge regularisation (few points, correlated objectives). Prints the weights,
the fit (R2, predicted vs real score) and writes solver/pesos-<q>.txt, which `make <q>` then uses automatically
(delete the file to go back to the priority order). Negative weights (an objective that seems to *raise* the score)
are reported but get a minimum weight (--minim, 0.1 of the largest): with few, rounded scores they are usually noise,
and an objective with no weight at all would be left free to get much worse.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ORDER = ('hores_mortes_min', 'canvis_franja', 'desplacaments_aula', 'desplacaments_edifici',
         'r6_aules_te_extra_per_grup', 'r6_canvis_te_paul_fora_passadis', 'canvis_aula')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pregunta', default='5.1')
    ap.add_argument('--ridge', type=float, default=0.05, help='regularisation strength')
    ap.add_argument('--minim', type=float, default=0.1, help='minimum relative weight of every objective that varies')
    ap.add_argument('--dir', help='folder of the proposals, relative to solver/ (default out/<q>; e.g. out/truc/5.2): '
                                  'its weights go to <dir>/pesos.txt')
    a = ap.parse_args()
    d = (HERE / a.dir).resolve() if a.dir else HERE / 'out' / a.pregunta
    vd = d / 'variants'
    # scores can also come from a plain text file: one "r1-v03 81" per line (puntuacions.txt)
    extra = {}
    for t in sorted(vd.glob('puntuacions*.txt')):
        for line in open(t, encoding='utf-8-sig'):
            parts = line.replace(';', ' ').replace('	', ' ').split()
            if len(parts) >= 2:
                extra[parts[0]] = parts[1]
    rows, ref = [], None
    for t in sorted(vd.glob('ronda*.csv')):
        text = open(t, encoding='utf-8-sig').read()
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=',;	')   # Excel may save with ";"
        for r in csv.DictReader(text.splitlines(), dialect=dialect):
            r = {k.strip(): (v or '').strip() for k, v in r.items() if k}
            for o in ORDER:
                r[o] = r[o].replace(',', '.')
            if r['variant'].endswith('-v00') and ref is None:
                ref = {o: max(1.0, float(r[o])) for o in ORDER}         # the SAT proposal: same REF as millora.py
            if r['variant'] in extra:
                r['puntuacio'] = extra[r['variant']]
            if r.get('puntuacio', ''):
                rows.append(r)
    if ref is None or len(rows) < 3:
        raise SystemExit(f'need scores: fill the "puntuacio" column of {vd}/ronda*.csv and SAVE it, or write them in '
                         f'{vd}/puntuacions.txt, one "r1-v03 81" per line (at least 3, ideally 10+)')
    X = np.array([[float(r[o]) / ref[o] for o in ORDER] for r in rows])
    y = np.array([float(r['puntuacio'].replace(',', '.')) for r in rows])
    vary = [k for k in range(len(ORDER)) if X[:, k].std() > 1e-9]
    Xv = X[:, vary]
    mu, sd = Xv.mean(0), Xv.std(0)
    Z = (Xv - mu) / sd                                              # standardise, fit, map back
    A = np.hstack([np.ones((len(y), 1)), Z])
    lam = a.ridge * len(y) * np.eye(A.shape[1])
    lam[0, 0] = 0
    coef = np.linalg.solve(A.T @ A + lam, A.T @ y)
    b = coef[1:] / sd                                               # d(score)/d(objective/REF)
    pred = A @ coef
    r2 = 1 - ((y - pred) ** 2).sum() / max(1e-12, ((y - y.mean()) ** 2).sum())
    print(f'{len(rows)} scored variants, {len(vary)} objectives that vary · fit R2 = {r2:.2f}'
          + ('   (more points than objectives + 2 recommended)' if len(rows) < len(vary) + 2 else ''))
    print(f'\n{"objective":34} {"weight":>8}   (score lost when the objective goes from 0 to its SAT value)')
    weights = {}
    for k, bk in zip(vary, b):
        w = -bk
        weights[ORDER[k]] = w
        print(f'{ORDER[k]:34} {w:8.2f}' + ('   <- raises the score? treated as 0' if w < 0 else ''))
    print(f'\n{"variant":12} {"real":>6} {"predicted":>9}')
    for r, p in zip(rows, pred):
        print(f'{r["variant"]:12} {float(r["puntuacio"]):6.1f} {p:9.1f}')
    pos = {o: w for o, w in weights.items() if w > 0}
    if not pos:
        raise SystemExit('\nno objective lowers the score: nothing to optimise for (keep the priority order)')
    top = max(pos.values())
    # every objective that varies keeps at least a small weight: 'not measured' is not 'does not matter'
    text = ','.join(f'{o}={max(a.minim, w / top):.3f}' for o, w in weights.items())
    out = (d / 'pesos.txt') if a.dir else HERE / f'pesos-{a.pregunta}.txt'
    out.write_text(text + '\n', encoding='utf-8')
    print(f'\nweights -> {out.name}: {text}\nnow run:  ' + (f'make bucle Q={a.pregunta} DIR={a.dir}   (next round)'
          if a.dir else f'make clean-{a.pregunta} && make {a.pregunta}   (or just rebuild the proposal: make {a.pregunta})'))


if __name__ == '__main__':
    main()
