#!/usr/bin/env python3
"""CSV -> Prolog facts for the SAT timetable generator (horaris.pl), and solution -> proposta.csv.

The CSVs are read through the official verifier's own loader (horaris.model.carrega_base), so semester-by-date,
the scenarios (grau-nou-40, contingencies), the calendar and the double-degree flag mean exactly what the jury's
checker says. One command per step; every step takes --pregunta (5.1 | 5.2 | 5.3 | 5.4) and --dir (out/<pregunta>):

    python3 exporta.py fase-a   --pregunta 5.2 --dir out/5.2                # facts for the main solve
    python3 exporta.py fase-b   --pregunta 5.2 --dir out/5.2                # 5.2 only: calendar repair
    python3 exporta.py proposta --pregunta 5.2 --dir out/5.2                # units -> one row per session

What each question solves (enunciat §5):
  5.1  only rooms: today's day and hour stay (verifier --nomes-aules); keep every room that is still valid
  5.2  new shifts: day, hour and room of the movable classes (phase A weekly patterns + phase B calendar repair)
  5.3  contingencies on top of out/5.2/proposta.csv: everything frozen except what the four events force
  5.4  grau-nou-40 on top of out/5.2/proposta.csv: everything frozen, the 235 new sessions get rooms

A *block* is what moves as one piece: an activity (same group, weekday and hour every week) merged with every
activity it shares a physical class with (id_compartida). A *piece* is a block in one single week.
"""
from __future__ import annotations

import argparse
import os
import collections
import csv
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from horaris.check import _solapaments_de_partida  # noqa: E402  (official "inherited overlap" set)
from horaris.model import DIES, a_traslladar, carrega_base, hm  # noqa: E402

PAQUET = ROOT / 'paquet'
HERE = Path(__file__).resolve().parent
ESCENARI = {'5.1': None, '5.2': None, '5.3': 'contingencies', '5.4': 'grau-nou-40'}
DAY_ATOM = dict(zip(DIES, 'lmxjv'))          # Prolog atoms for the weekdays
ATOM_DAY = {v: k for k, v in DAY_ATOM.items()}


def q(x) -> str:
    """Quoted Prolog atom."""
    return "'" + str(x).replace('\\', '\\\\').replace("'", "\\'") + "'"


def week_of(d: dt.date) -> int:
    y, w, _ = d.isocalendar()
    return y * 100 + w


def monday(week: int) -> dt.date:
    return dt.date.fromisocalendar(week // 100, week % 100, 1)


def date_of(week: int, day_atom: str) -> dt.date:
    return monday(week) + dt.timedelta(days='lmxjv'.index(day_atom))


# --sense-aula (the out/truc/ family): the fixed GEI/GEET 1r-2n sessions that are in the afternoon today with no room
# are left without a room. They pay R5-SENSE-AULA (declared) instead of R1-TORN: same count, but their R1-TORN becomes
# inherited and their rooms are free for the rest. Inside this script they are treated like the dobles (no room).
# the semester being solved: 2 (the four questions) or 1 (out/any, the whole year): SEMESTRE=1 in the environment
SEMESTRE = int(os.environ.get('SEMESTRE', '2'))
SENSE_AULA = False
NOROOM: set = set()
JUST_R5 = ("Grups de GEI i GEET+GEST de 1r i 2n fixats (R1: no es toquen) que avui fan classe a la tarda i no tenen "
           "aula. Qualsevol opció en deixa un incompliment per sessió: moure'ls al matí incompleix R1-FIXADA, posar-los "
           "aula fa que el seu R1-TORN deixi de ser heretat, i deixar-los sense aula incompleix R5-SENSE-AULA. Els "
           "deixem exactament com els té l'Escola avui: mateix dia, hora i (cap) aula.")


def wrong_shift_fixed_roomless(s) -> bool:
    return (s.fixada.startswith('R1') and not s.aula and not s.sense_espai and s.tipus != 'PLAB'
            and s.torn in ('mati', 'tarda') and (s.ini < 870) != (s.torn == 'mati'))


def load(pregunta: str):
    esc = ESCENARI[pregunta]
    base = carrega_base(PAQUET, semestre=SEMESTRE, escenari=PAQUET / 'escenaris' / esc if esc else None)
    if SENSE_AULA:
        for s in base.sessions.values():
            if wrong_shift_fixed_roomless(s):
                s.sense_espai = True
                NOROOM.add(s.id)
    return base


def blocks(base) -> list[list]:
    """Union-find: activity + shared class (id_compartida) -> block. Sorted for stable unit names."""
    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def key(s):  # grau-nou sessions have no activitat_id: rebuild it from (code, group, weekday, start)
        return s.activitat or f'N:{s.codi}:{s.grup}:{s.dia}:{s.ini}'

    for s in base.sessions.values():
        find(key(s))
        if s.compartida:
            parent[find(key(s))] = find('C:' + s.compartida)
    out = collections.defaultdict(list)
    for sid in base.ordre:
        s = base.sessions[sid]
        out[find(key(s))].append(s)
    return sorted(out.values(), key=lambda v: v[0].id)


def by_week(sessions) -> dict:
    out = collections.defaultdict(list)
    for s in sessions:
        out[week_of(s.data)].append(s)
    return dict(sorted(out.items()))


# ----------------------------------------------------------------------------------------------- calendar
def calendar_ok(base, s, date: dt.date, ini: int) -> bool:
    """Same test as the verifier's R2-CALENDARI for session s placed on (date, ini)."""
    fi = ini + s.durada
    if date != s.data and date in base.dies_sense_classe:
        return False
    moved = (date, ini) != (s.data, s.ini)
    hits = any(ini < b and fi > a for a, b in base.aturades.get(date, ()))
    excused = date == s.data and any(s.ini < b and s.fi > a for a, b in base.aturades.get(s.data, ()))
    return not (moved and hits and not excused)


def day_rules(base, s, date: dt.date):
    """For a free session: None if the day is forbidden, else the list of forbidden (from, to) ranges that day."""
    if date != s.data and date in base.dies_sense_classe:
        return None
    if date == s.data and any(s.ini < b and s.fi > a for a, b in base.aturades.get(s.data, ())):
        return []                       # already on a stoppage day in the partida: any time that day is fine
    ranges = base.aturades.get(date, ())
    if any(a <= 0 and b >= 24 * 60 for a, b in ranges):
        return None
    return list(ranges)


def free_days(base, sess, week, after=None, until=None):
    """Days of `week` where all of `sess` may go (R2-CALENDARI), and the forbidden time ranges on them."""
    days, forb = [], []
    for dd in 'lmxjv':
        date = date_of(week, dd)
        if (after and date <= after) or (until and date > until):
            continue
        rules = [day_rules(base, s, date) for s in sess]
        if any(x is None for x in rules):
            continue
        days.append(dd)
        forb += [(dd, a, b) for x in rules for a, b in x]
    return days, sorted(set(forb))


# ----------------------------------------------------------------------------------------------- facts
class Facts:
    def __init__(self, base, step: int, relax: Path | None = None):
        self.base = base
        self.lines: list[str] = []
        self.step = step
        self.sigs: dict[tuple, str] = {}
        self.units: dict[str, list] = {}           # unit -> session ids (for proposta)
        self.recover: dict[str, int] = {}          # cancelled session -> week where it is recovered
        self.relax: dict[str, set] = collections.defaultdict(set)   # rule -> session ids declared relaxed
        if relax and Path(relax).exists():
            with open(relax, encoding='utf-8-sig', newline='') as f:
                for r in csv.DictReader(f):
                    self.relax[r['restriccio'].strip().upper()] |= {x.strip() for x in r['sessions'].split('|')}

    def add(self, s: str):
        self.lines.append(s)

    def sig(self, weeks) -> str:
        weeks = tuple(sorted(weeks))
        if weeks not in self.sigs:
            self.sigs[weeks] = f's{len(self.sigs) + 1}'
        return self.sigs[weeks]

    def rooms(self):
        b = self.base
        self.add('% room(Room, Type, Capacity): the 56 spaces of aules.csv')
        for r, a in sorted(b.aules.items()):
            self.add(f'room({q(r)}, {q(a.tipus)}, {a.capacitat}).')
            if a.integrat:
                self.add(f'integrated({q(r)}).')
        outside = sorted({s.aula for s in b.sessions.values() if s.aula and s.aula not in b.aules})
        self.add('% rooms used today that are not in aules.csv: a session may stay there, nobody new may enter')
        for r in outside:
            self.add(f'room({q(r)}, outside, 0).')
            self.add(f'outsideBuilding({q(r)}).')
            if a_traslladar(r):
                self.add(f'mustLeave({q(r)}).')

    def unit(self, u: str, sess: list, *, movable: bool, days: list[str], fixed_start=None, fixed_room=None,
             forbidden=(), preferred=None, week=None, force_room=False):
        """sess: the sessions this unit stands for (a whole block, or one piece = one week of a block).
        preferred: (day, start, room) the solver should try to keep (default: today's slot and room).
        week: force the week (a cancelled session recovered in another week)."""
        self.units[u] = [s.id for s in sess]
        s0 = sess[0]
        weeks = {week} if week else {week_of(s.data) for s in sess}
        need_room = force_room or any(not s.sense_espai and s.tipus != 'PLAB' for s in sess)
        per_week = collections.Counter()
        for s in sess:
            if not s.sense_espai:
                per_week[week_of(s.data)] += s.alumnes
        torns = {s.torn for s in sess}
        shift = s0.torn if len(torns) == 1 else 'mixed'
        if all(s.id in self.relax.get('R1-TORN', ()) for s in sess):
            shift = 'any'                                # declared R1-TORN relaxation (relaxacions.csv)
        add = self.add
        add(f'unit({q(u)}).')
        add(f'duration({q(u)}, {s0.durada}).')
        add(f'shift({q(u)}, {shift}).')
        add(f'weekSig({q(u)}, {self.sig(weeks)}).')
        add(f'days({q(u)}, [{",".join(days)}]).')
        add(f'original({q(u)}, {DAY_ATOM[s0.dia]}, {s0.ini}).')
        pd, pt, pr = preferred or (DAY_ATOM[s0.dia], s0.ini, s0.aula if not s0.sense_espai else '')
        add(f'preferred({q(u)}, {pd}, {pt}).')
        if pr:
            add(f'preferredRoom({q(u)}, {q(pr)}).')
        add(f'sessionType({q(u)}, {q(s0.tipus)}).')
        add(f'students({q(u)}, {max(per_week.values(), default=0)}).')
        if movable:
            add(f'movable({q(u)}).')
        if fixed_start is not None:
            add(f'fixedStart({q(u)}, {fixed_start}).')
        if fixed_room:
            add(f'fixedRoom({q(u)}, {q(fixed_room)}).')
        elif need_room:
            add(f'needsRoom({q(u)}).')
        for r in sorted({s.aula for s in sess if s.aula and not s.sense_espai}):
            add(f'originalRoom({q(u)}, {q(r)}).')
        for d in sorted({d for s in sess for d in s.docents}):
            add(f'teacher({q(u)}, {q(d)}).')
        for t in sorted({(c, s.tipus, s.linia, s.num_grup) for s in sess for c in s.cohorts}):
            add(f'cohortGroup({q(u)}, {q(t[0])}, {q(t[1])}, {q(t[2])}, {q(t[3])}).')
        for c, t in sorted({(s.codi, s.tipus) for s in sess}):
            add(f'subject({q(u)}, {q(c)}, {q(t)}).')
        for d, a, b in forbidden:
            add(f'forbidden({q(u)}, {d}, {a}, {b}).')
        # R3-TANCADA: rooms closed by the scenario on one of this unit's possible days
        for t in self.base.tancaments:
            for w in weeks:
                for dd in days:
                    if t.data_ini <= date_of(w, dd) <= t.data_fi:
                        add(f'closedRoom({q(u)}, {q(t.aula)}, {dd}, {t.ini}, {t.fi}).')

    def inherited(self):
        """Pairs that already clashed (teacher / students / lab) in today's schedule: the verifier forgives them."""
        unit_of = {sid: u for u, ids in self.units.items() for sid in ids}
        pairs = set()
        for _regla, ids in _solapaments_de_partida(self.base):
            us = sorted({unit_of[i] for i in ids if i in unit_of})
            if len(us) == 2:
                pairs.add(tuple(us))
        self.add('% inherited(U1, U2): overlap already present in the starting schedule (not counted by the verifier)')
        for a, b in sorted(pairs):
            self.add(f'inherited({q(a)}, {q(b)}).')

    def write(self, path: Path, header: str):
        self.inherited()
        sigl = [f'sig({k}, [{",".join(map(str, w))}]).' for w, k in sorted(self.sigs.items(), key=lambda x: x[1])]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'%% {header}\n%% generated by exporta.py: do not edit\n\nstep({self.step}).\n\n'
                        + '\n'.join(sigl) + '\n\n' + '\n'.join(self.lines) + '\n', encoding='utf-8')
        json.dump({'units': self.units, 'recover': self.recover}, open(path.with_suffix('.json'), 'w'))


# ----------------------------------------------------------------------------------------------- 5.1 / 5.2
def phase_a_blocks(args, base):
    """One unit per block (weekly pattern). 5.1: day and hour fixed for everybody, only rooms are chosen."""
    nomes_aules = args.pregunta == '5.1'
    F = Facts(base, args.pas, args.relaxacions)
    F.rooms()
    for i, bl in enumerate(blocks(base), 1):
        fixed = bool(bl[0].fixada)
        time_fixed = fixed or nomes_aules
        # a block whose sessions do not all have the same day, hour (and, if fixed, room) today is split, so that
        # every fixed session keeps its own (the 1st semester has many; the 2nd none: there it is one unit)
        parts = collections.defaultdict(list)
        for s in bl:
            parts[(s.dia, s.ini, s.aula if fixed or s.tipus == 'PLAB' else '') if time_fixed else ()].append(s)
        for k, part in enumerate(parts.values()):
            s0 = part[0]
            plab_room = s0.aula if s0.tipus == 'PLAB' and s0.aula else None       # R7: PLAB keeps its room
            keep_room = s0.aula if fixed and s0.aula and not a_traslladar(s0.aula) and not s0.sense_espai else None
            F.unit(f'b{i:04d}' + (f'p{k}' if len(parts) > 1 else ''), part, movable=not fixed,
                   days=[DAY_ATOM[s0.dia]] if time_fixed else list('lmxjv'),
                   fixed_start=s0.ini if time_fixed else None,
                   fixed_room=plab_room or keep_room)
    what = 'only rooms (today\'s day and hour)' if nomes_aules else 'one weekly pattern per block'
    F.write(args.dir / 'dadesA.pl', f'{args.pregunta} PHASE A: {what}')
    print(f'{args.pregunta} phase A: {len(F.units)} units, {len(F.sigs)} week signatures')


def read_solution(path: Path) -> dict:
    with open(path, encoding='utf-8') as f:
        return {r['unit']: (r['day'], int(r['start']), r['room']) for r in csv.DictReader(f)}


def phase_b(args):
    """5.2: pieces whose phase-A pattern lands on a holiday / stoppage are placed again inside their week."""
    base = load(args.pregunta)
    A = json.load(open(args.dir / 'dadesA.json'))['units']
    solA = read_solution(args.dir / 'solucioA.csv')
    pieces = collections.defaultdict(list)        # (unit, week) -> sessions
    for u, ids in A.items():
        for sid in ids:
            s = base.sessions[sid]
            pieces[(u, week_of(s.data))].append(s)
    bad = {(u, w) for (u, w), ss in pieces.items()
           if not all(calendar_ok(base, s, date_of(w, solA[u][0]), solA[u][1]) for s in ss)}
    weeks = sorted({w for _, w in bad})
    if args.setmana:                                   # debugging: one week only
        weeks = [w for w in weeks if w % 100 == args.setmana]
        bad = {x for x in bad if x[1] in weeks}
    F = Facts(base, args.pas, args.relaxacions)
    F.rooms()
    for (u, w), ss in sorted(pieces.items()):
        if w not in weeks:
            continue
        name = f'{u}_w{w % 100:02d}'
        d, t, r = solA[u]
        s0 = ss[0]
        if not ((u, w) in bad or (args.allibera == 'setmana' and not s0.fixada)):   # frozen at its pattern
            F.unit(name, ss, movable=False, days=[d], fixed_start=t, fixed_room=r or None)
            continue
        days, forb = free_days(base, ss, w)
        F.unit(name, ss, movable=True, days=days, fixed_room=(s0.aula if s0.tipus == 'PLAB' and s0.aula else None),
               forbidden=forb, preferred=(d, t, r))   # stay as close as possible to the weekly pattern
    out = args.out or args.dir / 'dadesB.pl'
    F.write(out, f'{args.pregunta} PHASE B: calendar repair for weeks {weeks}; {len(bad)} pieces hit the calendar')
    print(f'{args.pregunta} phase B: {len(bad)} pieces land on a holiday/stoppage -> re-placed inside their week '
          f'(weeks {", ".join(str(w % 100) for w in weeks) or "-"}); allibera={args.allibera}')


# ----------------------------------------------------------------------------------------------- 5.3 / 5.4
def read_proposta(path: Path) -> dict:
    with open(path, encoding='utf-8-sig') as f:
        return {r['id_sessio']: (DAY_ATOM[r['dia']], hm(r['h_ini']), r['aula']) for r in csv.DictReader(f)}


def time_ok(s) -> bool:
    """Today's hour keeps R2-FINESTRA (inside 8:30-14:30 or 14:30-21:00) and R1-TORN (start in its shift)."""
    window = any(a <= s.ini and s.fi <= b for a, b in ((510, 870), (870, 1260)))
    return window and (s.torn not in ('mati', 'tarda') or (s.ini < 870) == (s.torn == 'mati'))


def phase_a_reference(args, base):
    """5.3 / 5.4: start from the 5.2 proposal (--referencia). Every piece (block x week) is frozen at its 5.2
    slot and room, except the ones the scenario forces to change. --allibera widens that if it is UNSAT:
        minim     only what the scenario touches                                  (default)
        setmana   + every movable piece of the weeks with a closure / the cancelled session   (5.3)
        temps     the grau-nou sessions may also change day and hour inside their week          (5.4)"""
    ref = read_proposta(args.referencia)
    F = Facts(base, args.pas, args.relaxacions)
    F.rooms()
    closures = base.tancaments
    hot_weeks = {week_of(t.data_ini + dt.timedelta(days=k)) for t in closures
                 for k in range((t.data_fi - t.data_ini).days + 1)}
    hot_weeks |= {week_of(base.sessions[c].data) for c in base.cancellades}
    hot_weeks |= {week_of(base.sessions[c].data) + 1 for c in base.cancellades}
    nfree = 0
    for i, bl in enumerate(blocks(base), 1):
        s0 = bl[0]
        if s0.id not in ref:                         # 5.4: a grau-nou block (not in the 5.2 proposal)
            if args.allibera == 'temps':
                for w, ss in by_week(bl).items():
                    days, forb = free_days(base, ss, w)
                    F.unit(f'b{i:04d}_w{w % 100:02d}', ss, movable=True, days=days, forbidden=forb)
                    nfree += 1
            elif all(time_ok(s) for s in bl):          # keep the day and hour it already has, find rooms
                F.unit(f'b{i:04d}', bl, movable=True, days=[DAY_ATOM[s0.dia]], fixed_start=s0.ini)
                nfree += 1
            else:                                    # its given hour breaks R1/R2 (1st semester): free it in its week
                for w, ss in by_week(bl).items():
                    days, forb = free_days(base, ss, w)
                    F.unit(f'b{i:04d}_w{w % 100:02d}', ss, movable=True, days=days, forbidden=forb)
                    nfree += 1
            continue
        for w, ss in by_week(bl).items():
            name = f'b{i:04d}_w{w % 100:02d}'
            d, t, _ = ref[ss[0].id]
            r = next((ref[s.id][2] for s in ss if ref[s.id][2] and not s.sense_espai), '')  # dobles carry no room
            if any(ref[s.id][:2] != (d, t) for s in ss):
                sys.exit(f'{name}: the sessions of one piece have different slots in the reference')
            date = date_of(w, d)
            fixed = bool(s0.fixada)
            cancelled = [s for s in ss if s.id in base.cancellades]
            closed = r and any(c.aula == r and c.data_ini <= date <= c.data_fi and t < c.fi and t + s0.durada > c.ini
                               for c in closures)
            cap = base.aules[r].capacitat if r in base.aules else 10 ** 6
            too_big = (r and sum(s.alumnes for s in ss if not s.sense_espai) > cap
                       and not (fixed and r == s0.aula))     # a fixed group in its own room is 'inherited'
            free = cancelled or closed or too_big or (args.allibera == 'setmana' and not fixed and w in hot_weeks)
            if not free:
                F.unit(name, ss, movable=False, days=[d], fixed_start=t, fixed_room=r or None)
                continue
            nfree += 1
            if cancelled:                            # R5-RECUPERACIO: a later date up to the deadline
                c = cancelled[0]
                rw = week_of(c.data) + args.recupera
                days, forb = free_days(base, ss, rw, after=c.data, until=base.cancellades[c.id])
                F.unit(name, ss, movable=True, days=days, forbidden=forb, preferred=(d, t, r), week=rw)
                F.recover[c.id] = rw
            elif fixed:                              # fixed group (R1/R7): same time, only another room
                F.unit(name, ss, movable=False, days=[d], fixed_start=t, preferred=(d, t, r), force_room=True)
            else:
                days, forb = free_days(base, ss, w)
                F.unit(name, ss, movable=True, days=days, forbidden=forb, preferred=(d, t, r))
    F.write(args.dir / 'dadesA.pl', f'{args.pregunta}: on top of {args.referencia.name}, '
                                     f'{nfree} units free (allibera={args.allibera}), the rest frozen')
    print(f'{args.pregunta}: {len(F.units)} units, {nfree} free (allibera={args.allibera}), the rest frozen at 5.2')


def phase_a(args):
    base = load(args.pregunta)
    if args.pregunta in ('5.1', '5.2'):
        phase_a_blocks(args, base)
    else:
        if not args.referencia.exists():
            sys.exit(f'{args.referencia} does not exist: run "make 5.2" first')
        phase_a_reference(args, base)


# ----------------------------------------------------------------------------------------------- proposta
def proposta(args):
    base = load(args.pregunta)
    rows, recovered = {}, {}
    for phase in ('A', 'B'):
        sol = args.dir / f'solucio{phase}.csv'
        dades = args.dir / f'dades{phase}.json'
        if not (sol.exists() and dades.exists()):
            continue
        info = json.load(open(dades))
        for u, (d, t, r) in read_solution(sol).items():
            for sid in info['units'][u]:
                s = base.sessions[sid]
                room = (r or s.aula) if s.tipus == 'PLAB' else ('' if s.sense_espai else r)
                rows[sid] = (ATOM_DAY[d], f'{t // 60:02d}:{t % 60:02d}', room)
                if sid in info['recover']:
                    recovered[sid] = date_of(info['recover'][sid], d).isoformat()
    missing = [sid for sid in base.ordre if sid not in rows]
    if missing:
        sys.exit(f'{len(missing)} sessions without a solution (e.g. {missing[:3]})')
    out = args.dir / 'proposta.csv'
    with open(out, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        extra = ['data'] if base.cancellades else []        # 5.3: the recovered session carries its new date
        w.writerow(['id_sessio', 'dia', 'h_ini', 'aula', *extra])
        for sid in base.ordre:
            w.writerow([sid, *rows[sid], *([recovered.get(sid, '')] if extra else [])])
    print(f'{len(rows)} sessions -> {out}' + (f'  (recovered: {recovered})' if recovered else ''))
    if args.pregunta != '5.1':                 # 5.1 is checked with --nomes-aules: no shift rule, nothing to declare
        write_relaxations(base, rows, args)


def write_relaxations(base, rows, args):
    """relaxacions.csv (hand-written, proven ones) + the ones the verifier leaves no way around."""
    def fixed_afternoon(s):
        return (s.fixada.startswith('R1') and not s.aula and not s.sense_espai and s.torn in ('mati', 'tarda')
                and (s.ini < 870) != (s.torn == 'mati') and rows[s.id][2])

    def closed_today(s):          # a session that cannot move (R1 / R7) whose own room is closed by the scenario
        return s.fixada and s.aula and any(c.aula == s.aula and c.data_ini <= s.data <= c.data_fi
                                           and s.ini < c.fi and s.fi > c.ini for c in base.tancaments)

    S = [base.sessions[sid] for sid in base.ordre]
    auto = [
        ('R1-TORN', [s.id for s in S if fixed_afternoon(s)],
         "Grups de GEI i GEET+GEST de 1r i 2n fixats (R1: no es toquen, R1-FIXADA) que avui fan classe a la tarda i "
         "no tenen aula. No es poden moure al matí sense incomplir R1-FIXADA, i sense aula incompleixen "
         "R5-SENSE-AULA; en posar-los aula, el verificador deixa de considerar heretat el seu R1-TORN. Mantenim "
         "l'horari que l'Escola ha fixat i els donem aula."),
        ('R1-FIXADA', [s.id for s in S if closed_today(s) and s.fixada.startswith('R1') and rows[s.id][2] != s.aula],
         "Sessions fixades (R1) la seva aula de sempre està tancada per l'escenari (R3-TANCADA, no relaxable): "
         "mantenen dia i hora i canvien només d'aula."),
        ('R7-PLAB', [s.id for s in S if closed_today(s) and s.tipus == 'PLAB'],
         "Laboratori PLAB en una aula tancada per l'escenari: no es pot fer allà (R3-TANCADA, no relaxable)."),
        ('R5-SENSE-AULA', [s.id for s in S if s.id in NOROOM and not rows[s.id][2]], JUST_R5),
    ]
    out = args.dir / 'relaxacions.csv'
    with open(out, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['restriccio', 'sessions', 'justificacio'])
        if args.relaxacions and Path(args.relaxacions).exists():
            with open(args.relaxacions, encoding='utf-8-sig', newline='') as g:
                for r in csv.DictReader(g):
                    if any(x.strip() in base.sessions for x in r['sessions'].split('|')):
                        w.writerow([r['restriccio'], r['sessions'], r['justificacio']])
        for rule, ids, why in auto:
            if ids:
                w.writerow([rule, '|'.join(ids), why])
    print(f'relaxations -> {out}: ' + ', '.join(f'{rule} {len(ids)}' for rule, ids, _ in auto if ids))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fase', choices=['fase-a', 'fase-b', 'proposta'])
    ap.add_argument('--pregunta', choices=sorted(ESCENARI), default='5.2')
    ap.add_argument('--dir', type=Path, help='output folder (default out/<pregunta>)')
    ap.add_argument('--out', type=Path, help='fase-b: write the facts somewhere else (debugging)')
    ap.add_argument('--pas', type=int, default=15, help='start-time grid in minutes (15 or 30)')
    ap.add_argument('--referencia', type=Path, default=HERE / 'out' / '5.2' / 'proposta.csv',
                    help='5.3 / 5.4: the proposal they start from')
    ap.add_argument('--allibera', choices=['peces', 'setmana', 'minim', 'temps'], default=None,
                    help='how much may move (fase-b: peces|setmana; 5.3: minim|setmana; 5.4: minim|temps)')
    ap.add_argument('--recupera', type=int, default=0,
                    help='5.3: recover the cancelled session in its own week (0) or the next one (1)')
    ap.add_argument('--relaxacions', type=Path, default=HERE / 'relaxacions.csv',
                    help='declared relaxations (official format); R1-TORN rows let those sessions take either shift')
    ap.add_argument('--setmana', type=int, help='fase-b: only this ISO week (to find which week is infeasible)')
    ap.add_argument('--sense-aula', dest='sense_aula', action='store_true',
                    help='trick family (out/truc): leave the fixed afternoon GEI 1r-2n sessions with no room today '
                         'without a room and declare R5-SENSE-AULA instead of R1-TORN')
    a = ap.parse_args()
    global SENSE_AULA
    SENSE_AULA = a.sense_aula
    a.dir = a.dir or HERE / 'out' / a.pregunta
    a.dir.mkdir(parents=True, exist_ok=True)
    a.allibera = a.allibera or ('peces' if a.fase == 'fase-b' else 'minim')
    {'fase-a': phase_a, 'fase-b': phase_b, 'proposta': proposta}[a.fase](a)


if __name__ == '__main__':
    main()
