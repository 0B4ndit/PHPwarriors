#!/usr/bin/env python3
"""Minimal UNSAT core over units (deletion-based): which classes, together, make a facts file infeasible?

    python3 nucli.py out/dadesB.pl            # prints a minimal set of units that is still UNSAT

Each step removes one unit (every fact that mentions it) and re-runs horaris.pl + kissat; if it stays UNSAT
the unit is not needed for the conflict. What is left is a small, human-checkable proof of infeasibility
for this model (rule 11 of the enunciat: "hem demostrat que no existeix").
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def solve(lines, units, work):
    keep = [l for l in lines if not (m := re.findall(r"'([^']+)'", l)) or not (set(m) & units)]
    f = Path(work) / 'core.pl'
    f.write_text('\n'.join(keep) + '\n', encoding='utf-8')
    r = subprocess.run(['swipl', '-g', 'main', '-t', 'halt', 'horaris.pl', '--', str(f), str(Path(work) / 'x.csv'),
                        work, 'skip=preferNoChanges'], cwd=HERE, capture_output=True, text=True)
    return r.returncode            # 0 SAT, 20 UNSAT


def main():
    if len(sys.argv) != 2 or not Path(sys.argv[1]).exists():
        sys.exit('usage: python3 nucli.py FACTS.pl   (a facts file that horaris.pl finds UNSAT, e.g.\n'
                 '       python3 exporta.py fase-b --allibera setmana --setmana 14 --relaxacions /dev/null '
                 '--out /tmp/w14.pl && python3 nucli.py /tmp/w14.pl)')
    src = Path(sys.argv[1])
    lines = src.read_text(encoding='utf-8').splitlines()
    units = re.findall(r"^unit\('([^']+)'\)", '\n'.join(lines), re.M)
    work = tempfile.mkdtemp(prefix='nucli-')
    if solve(lines, set(), work) != 20:
        sys.exit(f'{src} is SAT: there is no conflict to explain (nucli.py only makes sense on an UNSAT file)')
    removed: set = set()
    for i, u in enumerate(units, 1):
        if solve(lines, removed | {u}, work) == 20:
            removed.add(u)
        print(f'\r{i}/{len(units)} tested, core size <= {len(units) - len(removed)}', end='', flush=True)
    core = [u for u in units if u not in removed]
    print('\nMinimal UNSAT core:', ' '.join(core))
    for l in lines:
        m = re.findall(r"^\w+\('([^']+)'", l)
        if m and m[0] in core and not l.startswith(('cohortGroup', 'subject')):
            print('  ', l)


if __name__ == '__main__':
    main()
