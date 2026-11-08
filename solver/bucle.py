#!/usr/bin/env python3
"""The learning loop, interactive: you only upload files and type scores.

    python3 bucle.py --pregunta 5.2          (or: make bucle Q=5.2)

Every round:
  1. builds N new verified proposals (variants.py): the first round explores, later ones refine around the weights
     learnt so far, starting from the best proposal found so far;
  2. asks you, one by one, the xaman's score of each file (Enter = not submitted / skip);
  3. saves the scores, refits the weights (pesos.py) and shows them, heaviest first;
  4. copies the best-scored proposal so far to out/<q>/proposta.csv (+ a copy in ../entregues/) and asks whether to
     do another round.
All scores ever typed stay in out/<q>/variants/ronda*.csv, so every round learns from all the previous ones.
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def ask(prompt, default=''):
    try:
        v = input(prompt).strip()
    except EOFError:
        sys.exit('\n(no terminal input: run it from your own WSL terminal)')
    return v or default


def read_table(path: Path):
    text = open(path, encoding='utf-8-sig').read()
    dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=',;\t')
    rows = [{k.strip(): (v or '').strip() for k, v in r.items() if k} for r in csv.DictReader(text.splitlines(), dialect=dialect)]
    return rows


def write_table(path: Path, rows):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def all_scored(vd: Path):
    out = []
    for t in sorted(vd.glob('ronda*.csv')):
        for r in read_table(t):
            if r.get('puntuacio') and r['veredicte'].startswith('VALIDA') and (vd / f"{r['variant']}.csv").exists():
                out.append((float(r['puntuacio'].replace(',', '.')), r['variant']))
    return sorted(out, reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pregunta', default='5.2', choices=['5.1', '5.2', '5.4'])
    ap.add_argument('--n', type=int, default=10, help='proposals per round (the xaman allows 30 per hour)')
    ap.add_argument('--temps', type=int, default=60, help='seconds of search per proposal')
    ap.add_argument('--dir', help='folder of the proposals, relative to solver/ (default out/<q>; e.g. out/truc/5.2)')
    a = ap.parse_args()
    q = a.pregunta
    d = (HERE / a.dir).resolve() if a.dir else HERE / 'out' / q
    vd = d / 'variants'
    extra = ['--dir', a.dir] if a.dir else []
    tag = 'truc-' if a.dir and 'truc' in a.dir else ''
    py = sys.executable
    while True:
        # ---- 1. new proposals
        before = set(vd.glob('ronda*.csv')) if vd.exists() else set()
        r = subprocess.run([py, 'variants.py', '--pregunta', q, '--n', str(a.n), '--temps', str(a.temps), *extra],
                           cwd=HERE)
        if r.returncode:
            sys.exit('variants.py failed')
        table = max(set(vd.glob('ronda*.csv')) - before, key=lambda p: p.stat().st_mtime)
        rows = read_table(table)
        # ---- 2. scores
        print(f'\n=== Upload these files to the xaman and type the score of each one (Enter = skip) ===')
        print(f'    folder: solver/{vd.relative_to(HERE).as_posix()}/')
        for row in rows:
            if not row['veredicte'].startswith('VALIDA'):
                continue
            while True:
                v = ask(f'  {row["variant"]}.csv   score: ')
                if not v or re.fullmatch(r'\d+([.,]\d+)?', v):
                    break
                print('    (a number, or Enter to skip)')
            row['puntuacio'] = v.replace(',', '.')
            write_table(table, rows)                     # saved after every answer: nothing is lost
        # ---- 3. weights
        print('\n=== What the xaman seems to value (refit with every score so far) ===')
        subprocess.run([py, 'pesos.py', '--pregunta', q, *extra], cwd=HERE)
        # ---- 4. best so far
        scored = all_scored(vd)
        if scored:
            top, name = scored[0]
            dst = d / 'proposta.csv'
            shutil.copy(vd / f'{name}.csv', dst)
            keep = HERE.parent / 'entregues'
            keep.mkdir(exist_ok=True)
            shutil.copy(vd / f'{name}.csv', keep / f'{tag}{q}-{name}-score{top:g}.csv')
            print(f'\nBest so far: {name} with {top:g}  -> copied to {dst.relative_to(HERE).as_posix()} and entregues/')
            if q == '5.2':
                print('  (then "make ' + ('truc' if tag else 'derivades') + '" rebuilds 5.3 and 5.4 on top of it)')
        if ask('\nAnother round? [Y/n] ', 'y').lower().startswith('n'):
            break


if __name__ == '__main__':
    main()
