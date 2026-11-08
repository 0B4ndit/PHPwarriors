#!/usr/bin/env python3
"""Build N deliberately different, verified proposals for one question, to learn from the xaman's scores which
objectives it values (then pesos.py fits the weights).

    python3 variants.py --pregunta 5.1 --n 12 --temps 60

Writes out/<q>/variants/rK-vNN.csv (one proposal each, ready to upload), their verifier reports rK-vNN.json, and the
round's table out/<q>/variants/rondaK.csv: weights used, verdict, the seven objectives and an empty `puntuacio`
column. Upload the files, write each score in that column, then run  make pesos Q=<q>.

    v00  the raw SAT proposal (no millora)          v01  the current out/<q>/proposta.csv
    first round (no pesos-<q>.txt yet): v02… one objective alone (the extreme points), the rest random mixes,
        all starting from the SAT proposal
    later rounds (pesos-<q>.txt exists): the fitted weights and random perturbations of them, all starting from the
        best proposal known so far (--des-de millor): refining around what scored well
Variants run in parallel (one core each).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ORDER = ('hores_mortes_min', 'canvis_franja', 'desplacaments_aula', 'desplacaments_edifici',
         'r6_aules_te_extra_per_grup', 'r6_canvis_te_paul_fora_passadis', 'canvis_aula')
# objectives a question can actually change (5.1 keeps every time: dead time and slot changes are fixed)
FREE = {'5.1': ORDER[2:], '5.2': ORDER, '5.4': ORDER}
CHECK = {'5.1': [], '5.2': [], '5.3': [], '5.4': []}      # questions the tools accept (arguments: check_args)


def qdir(q, d=None) -> Path:
    """The question's folder: out/<q>, or another family of proposals such as out/truc/<q> (--dir)."""
    return (HERE / d).resolve() if d else HERE / 'out' / q


def check_args(q, d: Path):
    """Verifier arguments for a proposal of folder d: its own relaxacions.csv and, for 5.3/5.4, the 5.2 of the same
    family (d/../5.2/proposta.csv) as the reference."""
    rel = d / 'relaxacions.csv'
    out = ['--relaxacions', rel.relative_to(ROOT).as_posix()] if rel.exists() else []
    ref = ['--referencia', (d.parent / '5.2' / 'proposta.csv').relative_to(ROOT).as_posix()]
    return {'5.1': ['--nomes-aules'] + out,
            '5.2': out,
            '5.3': ['--escenari', 'paquet/escenaris/contingencies'] + ref + out,
            '5.4': ['--escenari', 'paquet/escenaris/grau-nou-40'] + ref + out}[q]


def weight_sets(q, n, rng, wfile: Path):
    objs = FREE[q]
    sets = []
    if wfile.exists():                                        # refine: random perturbations of the fitted weights
        fitted = dict(p.split('=') for p in wfile.read_text(encoding='utf-8').strip().split(','))
        fitted = {k: float(v) for k, v in fitted.items() if k in objs}
        sets.append(dict(fitted))
        while len(sets) < n - 2:
            sets.append({k: round(fitted.get(k, 0.02) * rng.lognormvariate(0, 0.6), 3) for k in objs})
        return sets[:max(0, n - 2)]
    for o in objs:                                            # one objective dominates (a tiny bit of the rest)
        sets.append({k: (1.0 if k == o else 0.02) for k in objs})
    while len(sets) < n - 2:                                  # random mixes
        raw = {k: rng.expovariate(1.0) for k in objs}
        tot = sum(raw.values())
        sets.append({k: round(v / tot, 3) for k, v in raw.items()})
    return sets[:max(0, n - 2)]


def verify(q, csv_path: Path, d: Path | None = None):
    js = csv_path.with_suffix('.json')
    cmd = [sys.executable, '-m', 'horaris', 'check', str(csv_path.relative_to(ROOT)), '--semestre', '2',
           *check_args(q, d or qdir(q)), '--json', str(js.relative_to(ROOT))]
    subprocess.run(cmd, cwd=ROOT, env={**os.environ, 'PYTHONUTF8': '1'}, capture_output=True)
    j = json.load(open(js, encoding='utf-8'))
    return j['veredicte'], j.get('incompliments_declarats', 0), j['objectius']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pregunta', default='5.1', choices=sorted(FREE))
    ap.add_argument('--n', type=int, default=12, help='number of variants (including v00 and v01)')
    ap.add_argument('--temps', type=int, default=60, help='seconds of LAHC per variant')
    ap.add_argument('--fils', type=int, default=os.cpu_count() or 4, help='variants built at the same time')
    ap.add_argument('--dir', help='folder of the proposals, relative to solver/ (default out/<q>; e.g. out/truc/5.2)')
    a = ap.parse_args()
    q = a.pregunta
    d = qdir(q, a.dir)
    if not (d / 'proposta-sat.csv').exists() or not (d / 'proposta.csv').exists():
        sys.exit(f'{d}: no proposta.csv / proposta-sat.csv yet (run "make {q}", or "make truc" for out/truc)')
    vd = d / 'variants'
    vd.mkdir(exist_ok=True)
    rnd = 1 + max([int(p.stem[5:]) for p in vd.glob('ronda*.csv') if p.stem[5:].isdigit()] or [0])
    rng = random.Random(1000 * rnd)
    names = {}
    shutil.copy(d / 'proposta-sat.csv', vd / f'r{rnd}-v00.csv')
    names['v00'] = 'SAT (no millora)'
    shutil.copy(d / 'proposta.csv', vd / f'r{rnd}-v01.csv')
    names['v01'] = 'current proposta.csv'
    jobs = []
    wfile = (d / 'pesos.txt') if a.dir else HERE / f'pesos-{q}.txt'
    for k, w in enumerate(weight_sets(q, a.n, rng, wfile), start=2):
        txt = ','.join(f'{o}={v:g}' for o, v in w.items())
        names[f'v{k:02d}'] = txt
        out = vd / f'r{rnd}-v{k:02d}.csv'
        jobs.append([sys.executable, 'millora.py', '--pregunta', q, '--pesos', txt, '--temps', str(a.temps),
                     '--fils', '1', '--llavor', str(100 * rnd + k), '--sortida', str(out),
                     '--des-de', 'millor' if wfile.exists() else 'sat', *(['--dir', str(d)] if a.dir else [])])
    print(f'round {rnd}: building {len(jobs)} variants ({a.fils} at a time, ~{a.temps} s of search each) ...', flush=True)
    t0, running, pending = time.time(), [], list(jobs)
    while pending or running:
        while pending and len(running) < a.fils:
            running.append(subprocess.Popen(pending.pop(0), cwd=HERE, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.PIPE, text=True))
        for p in list(running):
            if p.poll() is not None:
                running.remove(p)
                if p.returncode:
                    print('   a variant failed:', p.stderr.read()[-500:])
        time.sleep(1)
    print(f'   built in {time.time() - t0:.0f} s; verifying ...', flush=True)
    rows = []
    for v, txt in names.items():
        f = vd / f'r{rnd}-{v}.csv'
        if not f.exists():
            continue
        ver, decl, obj = verify(q, f, d)
        rows.append({'variant': f.stem, 'pesos': txt, 'veredicte': ver, 'declarades': decl,
                     **{o: obj[o] for o in ORDER}, 'puntuacio': ''})
    table = vd / f'ronda{rnd}.csv'
    with open(table, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f'\n{"variant":10} {"verdict":12} ' + ' '.join(f'{o[:14]:>14}' for o in FREE[q]))
    for r in rows:
        print(f'{r["variant"]:10} {r["veredicte"][:12]:12} ' + ' '.join(f'{r[o]:>14}' for o in FREE[q]))
    rel = vd.relative_to(HERE).as_posix()
    print(f'\nUpload {rel}/r{rnd}-v*.csv to the xaman, write each score in the "puntuacio" column of '
          f'{rel}/ronda{rnd}.csv, then:  make pesos Q={q}' + (f' DIR={a.dir}' if a.dir else ''))


if __name__ == '__main__':
    main()
