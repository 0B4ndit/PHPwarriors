#!/usr/bin/env python3
"""Improve a valid proposal on the rule-9 objectives, in priority order, without breaking any hard rule.

    python3 millora.py --pregunta 5.2        # rewrites out/5.2/proposta.csv (the SAT one is kept as proposta-sat.csv)

Order (lexicographic: a move is kept only if it makes the first objective that changes smaller):
    hores_mortes_min > canvis_franja > desplacaments_aula > desplacaments_edifici
    > r6_aules_te_extra_per_grup > r6_canvis_te_paul_fora_passadis > canvis_aula

1. Greedy descent. Phase "day/hour" moves whole weekly units (the sessions of a block that share weekday and hour)
   to a slot that closes a gap of one of their groups; phase "rooms" keeps every time and only changes rooms.
   Each stops when a whole pass improves nothing.
2. Late Acceptance Hill Climbing (LAHC), --temps seconds on --fils parallel workers with different random seeds:
   random moves (change a unit's room, SWAP the rooms of two units, move a unit to another slot); a move is accepted
   if the result is not worse than the current one or than the one L moves ago, which lets the search leave local
   optima. Every worker keeps the best timetable it saw; the best of all workers wins, then a final greedy polish.

Every move is checked against the hard rules with the verifier's own definitions (R1-TORN, R2-FINESTRA,
R2-CALENDARI, R3-*, R4-AULA/DOCENT/ALUMNAT/PLAB, R8); clashes the verifier forgives (inherited from today's
schedule) are allowed only for the exact same pair of sessions. The Makefile runs the official verifier afterwards.

Scope per question: 5.1 rooms only (times are fixed by --nomes-aules) · 5.2 everything that may move ·
5.4 only the grau-nou sessions (5.2 stays as it is) · 5.3 nothing (its goal is the fewest changes w.r.t. 5.2).
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import multiprocessing as mp
import os
import random
import shutil
import time
from pathlib import Path

from exporta import DIES, HERE, a_traslladar, blocks, calendar_ok, hm, load, monday, week_of
from horaris.check import FRANGES, _alumnat_comparteix, _espai_ok, _solapaments_de_partida, passadis
from horaris.model import MATI, TARDA

ORDER = ('hores_mortes_min', 'canvis_franja', 'desplacaments_aula', 'desplacaments_edifici',
         'r6_aules_te_extra_per_grup', 'r6_canvis_te_paul_fora_passadis', 'canvis_aula')
WIN = {'mati': [MATI], 'tarda': [TARDA], 'any': [MATI, TARDA]}
RULE = {'teacher': 'R4-DOCENT', 'students': 'R4-ALUMNAT', 'lab': 'R4-PLAB'}
# priority per question (indices into ORDER). 5.1 follows the brief: "una aula base estable per grup, pocs canvis
# d'aula entre classes seguides i pocs canvis respecte de l'aula d'avui"
PRIORITY = {
    '5.1': (0, 1, 4, 2, 3, 5, 6),
    '5.2': (0, 1, 2, 3, 4, 5, 6),
    '5.4': (0, 1, 2, 3, 4, 5, 6),
}
PRIO = PRIORITY['5.2']
# Weighted mode (--pesos or solver/pesos-<q>.txt): minimise  sum_k  w_k * objective_k / REF_k , where REF is the value of
# each objective in the SAT proposal (so that weights of objectives with very different sizes are comparable).
WEIGHTS: dict = {}
REF = (1,) * len(ORDER)
NOROOM: set = set()       # R5-SENSE-AULA declared in the folder's relaxacions.csv (out/truc): never get a room


def key(v):
    """What is compared: the vector in priority order (lexicographic), or the weighted sum (weighted mode)."""
    if WEIGHTS:
        return (sum(w * v[i] / REF[i] for i, w in WEIGHTS.items()),)
    return tuple(v[i] for i in PRIO)


def parse_weights(text):
    out = {}
    for part in text.replace(';', ',').split(','):
        if part.strip():
            k, v = part.split('=')
            out[ORDER.index(k.strip())] = float(v)
    return out


def vsub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def vadd(a, b):
    return tuple(x + y for x, y in zip(a, b))


class Timetable:
    def __init__(self, base, prop: dict, relaxed_shift: set, scope, with_time=True):
        self.b, self.S = base, base.sessions
        self.ordinary = {r for r, a in base.aules.items() if a.ordinaria}
        self.key = {sid: s.compartida or sid for sid, s in self.S.items()}
        self.rank = {sid: k for k, sid in enumerate(base.ordre)}      # file order: the verifier's tie-break
        self.pos = {}                                   # sid -> (date, ini, room)
        for sid, s in self.S.items():
            r = prop[sid]
            date = (dt.date.fromisoformat(r['data']) if r.get('data') else
                    monday(week_of(s.data)) + dt.timedelta(days=DIES.index(r['dia'])))
            self.pos[sid] = (date, hm(r['h_ini']), r['aula'])
        self.inh = {(regla, ids) for regla, ids in _solapaments_de_partida(base)}
        self.relaxed = relaxed_shift
        # indices
        self.room_occ, self.t_occ, self.c_occ, self.k_occ = (collections.defaultdict(set) for _ in range(4))
        self.busy = collections.defaultdict(collections.Counter)      # (date, slot) -> Counter(ordinary room)
        self.grp = collections.defaultdict(set)                       # (cohort, line, date) -> sids
        self.te = collections.defaultdict(collections.Counter)        # (cohort, line) -> Counter(TE room)
        for sid in self.S:
            self._index(sid, +1)
        # units: sessions of one block with the same weekday and start
        self.units = []
        for bl in blocks(base):
            g = collections.defaultdict(list)
            for s in bl:
                d, t, _ = self.pos[s.id]
                g[(d.weekday(), t)].append(s.id)
            self.units += list(g.values())
        self.unit_of = {sid: i for i, u in enumerate(self.units) for sid in u}
        self.can_time, self.can_room, self.allowed = {}, {}, {}
        for i, u in enumerate(self.units):
            ss = [self.S[x] for x in u]
            inside = scope(ss)
            fixed = any(s.fixada for s in ss)
            self.can_time[i] = with_time and inside and not fixed       # 5.1: times never move
            needs = [s for s in ss if not s.sense_espai and s.tipus != 'PLAB']
            locked = (any(s.fixada and s.aula and not a_traslladar(s.aula) for s in needs)
                      or any(s.id in NOROOM for s in ss))
            self.can_room[i] = inside and bool(needs) and not locked
            self.allowed[i] = self._allowed_rooms(needs) if self.can_room[i] else []

    # ------------------------------------------------------------------ indices
    def _index(self, sid, sign):
        s = self.S[sid]
        date, ini, room = self.pos[sid]
        fi = ini + s.durada
        upd = (lambda st, x: st.add(x)) if sign > 0 else (lambda st, x: st.discard(x))
        if room and not s.sense_espai:
            upd(self.room_occ[(date, room)], sid)
            if room in self.ordinary:
                for f0 in FRANGES:
                    if ini < f0 + 60 and fi > f0:
                        self.busy[(date, f0)][room] += sign
        for d in s.docents:
            upd(self.t_occ[(date, d)], sid)
        for c in s.cohorts:
            upd(self.c_occ[(date, c)], sid)
            upd(self.grp[(c, s.linia, date)], sid)
            if s.tipus == 'TE' and room:
                self.te[(c, s.linia)][room] += sign
        upd(self.k_occ[(date, s.codi)], sid)

    def move(self, new: dict):
        """Apply {sid: (date, ini, room)}; returns the old positions (to undo)."""
        old = {sid: self.pos[sid] for sid in new}
        for sid in new:
            self._index(sid, -1)
        for sid, p in new.items():
            self.pos[sid] = p
        for sid in new:
            self._index(sid, +1)
        return old

    # ------------------------------------------------------------------ rooms allowed (R3)
    def _allowed_rooms(self, needs):
        per_date = collections.Counter()
        for s in needs:
            per_date[s.data] += s.alumnes
        n = max(per_date.values(), default=0)
        out = []
        for r, a in self.b.aules.items():
            if n > a.capacitat:
                continue
            if all((r == s.aula and not (s.tipus != 'PLAB' and a.tipus == 'Laboratoris docents'))
                   or _espai_ok(self.b, s, r) for s in needs):
                out.append(r)
        out += sorted({s.aula for s in needs if s.aula and s.aula not in self.b.aules and not a_traslladar(s.aula)})
        return out

    # ------------------------------------------------------------------ objectives (same definitions as the verifier)
    def group_cost(self, gk):
        sids = self.grp.get(gk)
        if not sids:
            return (0, 0, 0, 0)
        agenda = collections.defaultdict(list)
        for sid in sorted(sids, key=self.rank.__getitem__):
            s = self.S[sid]
            agenda['*' if s.tipus == 'TE' else s.num_grup].append(sid)
        teoria = agenda.get('*', [])
        dead = desp = edif = corr = 0
        for sg in [k for k in agenda if k != '*'] or ['*']:
            seq = sorted(dict.fromkeys(teoria + (agenda[sg] if sg != '*' else [])), key=lambda x: self.pos[x][1])
            for a, b in zip(seq, seq[1:]):
                _, ia, ra = self.pos[a]
                _, ib, rb = self.pos[b]
                fa = ia + self.S[a].durada
                if ib - fa > 0 and (fa <= MATI[1]) == (ib < MATI[1]):
                    dead += ib - fa
                if ra and rb and ra != rb:
                    desp += 1
                    ea, eb = self.b.aules.get(ra), self.b.aules.get(rb)
                    if (ea.edifici if ea else ra.split('/')[0]) != (eb.edifici if eb else rb.split('/')[0]):
                        edif += 1
                    if {self.S[a].tipus, self.S[b].tipus} == {'TE', 'PAUL'} and passadis(ra) != passadis(rb):
                        corr += 1
        return (dead, desp, edif, corr)

    def session_cost(self, sid):
        s = self.S[sid]
        date, ini, room = self.pos[sid]
        cf = int((date, ini) != (s.data, s.ini))
        ca = int(bool(s.aula) and not a_traslladar(s.aula) and not s.sense_espai and room != s.aula)
        return cf, ca

    def cost(self, sids, gkeys, tkeys):
        """Objective vector (ORDER) restricted to what `sids` can change."""
        dead = desp = edif = corr = 0
        for gk in gkeys:
            d1, d2, d3, d4 = self.group_cost(gk)
            dead, desp, edif, corr = dead + d1, desp + d2, edif + d3, corr + d4
        cf = ca = 0
        for sid in sids:
            x, y = self.session_cost(sid)
            cf, ca = cf + x, ca + y
        r6 = sum(max(0, sum(1 for v in self.te[k].values() if v > 0) - 1) for k in tkeys)
        return (dead, cf, desp, edif, r6, corr, ca)

    def keys_of(self, sids, extra_dates=()):
        g, t = set(), set()
        for sid in sids:
            s = self.S[sid]
            for c in s.cohorts:
                g.add((c, s.linia, self.pos[sid][0]))
                for d in extra_dates:
                    g.add((c, s.linia, d))
                if s.tipus == 'TE':
                    t.add((c, s.linia))
        return g, t

    def total(self):
        gk = list(self.grp)
        return self.cost(list(self.S), gk, list(self.te))

    def delta(self, new: dict):
        sids = list(new)
        g0, t0 = self.keys_of(sids)
        g0 |= {(c, self.S[sid].linia, p[0]) for sid, p in new.items() for c in self.S[sid].cohorts}
        before = self.cost(sids, g0, t0)
        old = self.move(new)
        after = self.cost(sids, g0, t0)
        self.move(old)
        return vsub(after, before)

    # ------------------------------------------------------------------ hard rules
    def _clash(self, a, b, kind):
        pair = tuple(sorted((a, b)))
        return (RULE[kind], pair) not in self.inh

    def time_ok(self, new: dict, unit: set) -> bool:
        """Everything that does not depend on the room: shift, window, calendar, teachers, students, labs."""
        for sid, (date, ini, _) in new.items():
            s = self.S[sid]
            fi = ini + s.durada
            torn = 'any' if sid in self.relaxed else s.torn
            if not any(a <= ini and fi <= b for a, b in WIN.get(torn, WIN['any'])):
                return False                                      # R1-TORN / R2-FINESTRA
            if torn in ('mati', 'tarda') and (ini < MATI[1]) != (torn == 'mati'):
                return False
            if not calendar_ok(self.b, s, date, ini):              # R2-CALENDARI
                return False
            others = set()
            for d in s.docents:
                others |= {(o, 'teacher') for o in self.t_occ[(date, d)]}
            for c in s.cohorts:
                others |= {(o, 'students') for o in self.c_occ[(date, c)]}
            others |= {(o, 'lab') for o in self.k_occ[(date, s.codi)]}
            for o, kind in others:
                if o in unit or self.key[o] == self.key[sid]:
                    continue
                od, oi, _ = self.pos[o]
                os_ = self.S[o]
                if not (ini < oi + os_.durada and oi < fi):
                    continue
                if kind == 'teacher' and self._clash(sid, o, kind):
                    return False
                if kind == 'students' and _alumnat_comparteix(s, os_) and self._clash(sid, o, kind):
                    return False
                if kind == 'lab':
                    tt = {s.tipus, os_.tipus}
                    if 'PLAB' in tt and tt & {'TE', 'PAUL'} and self._clash(sid, o, kind):
                        return False
        return True

    def room_ok(self, new: dict, unit: set) -> bool:
        """R4-AULA, R3-TANCADA and R8-RESERVA for the rooms in `new` (applied tentatively)."""
        if not self.room_free(new, unit):
            return False
        slots = self.slots_of(new)
        old = self.move(new)
        ok = self.r8_ok(slots)
        self.move(old)
        return ok

    def slots_of(self, new):
        out = {(date, f0) for sid, (date, ini, room) in new.items() for f0 in FRANGES
               if ini < f0 + 60 and ini + self.S[sid].durada > f0}
        return out | {(self.pos[sid][0], f0) for sid in new for f0 in FRANGES}

    def r8_ok(self, slots):
        lim = len(self.ordinary) - 2
        return all(sum(1 for v in self.busy[k].values() if v > 0) <= lim for k in slots)

    def attempt(self, new: dict, unit: set, accept, check_time: bool):
        """Apply `new` if it keeps every hard rule and accept(delta) says yes; returns the delta or None."""
        if check_time and not self.time_ok(new, unit):
            return None
        if not self.room_free(new, unit):
            return None
        sids = list(new)
        g, t = self.keys_of(sids)
        g |= {(c, self.S[sid].linia, p[0]) for sid, p in new.items() for c in self.S[sid].cohorts}
        slots = self.slots_of(new)
        before = self.cost(sids, g, t)
        old = self.move(new)
        if self.r8_ok(slots):
            d = vsub(self.cost(sids, g, t), before)
            if accept(d):
                return d
        self.move(old)
        return None

    def room_free(self, new: dict, unit: set) -> bool:
        """R4-AULA and R3-TANCADA for the rooms in `new` (nothing applied)."""
        for sid, (date, ini, room) in new.items():
            s = self.S[sid]
            if s.sense_espai or not room:
                continue
            fi = ini + s.durada
            for o in self.room_occ[(date, room)]:
                if o in unit or self.key[o] == self.key[sid]:
                    continue
                _, oi, _ = self.pos[o]
                if ini < oi + self.S[o].durada and oi < fi:
                    return False
            for t in self.b.tancaments:
                if room == t.aula and t.data_ini <= date <= t.data_fi and ini < t.fi and fi > t.ini:
                    return False
        return True


# ---------------------------------------------------------------------------------------- the two phases
def better(d):
    for x in key(d):
        if abs(x) > 1e-12:
            return x < 0
    return False


def candidates_time(T: Timetable, i):
    """Weekday/start pairs that put the unit right after or right before another class of one of its groups."""
    u = T.units[i]
    s0 = T.S[u[0]]
    dur = s0.durada
    cur = (T.pos[u[0]][0].weekday(), T.pos[u[0]][1])
    out = {(DIES.index(s0.dia), s0.ini)}                        # going back to today's slot is always a candidate
    for sid in u:
        s = T.S[sid]
        mon = T.pos[sid][0] - dt.timedelta(days=T.pos[sid][0].weekday())
        for wd in range(5):
            date = mon + dt.timedelta(days=wd)
            for c in s.cohorts:
                for o in T.grp.get((c, s.linia, date), ()):
                    if T.unit_of[o] == i:
                        continue
                    oi = T.pos[o][1]
                    out.add((wd, oi + T.S[o].durada))
                    out.add((wd, oi - dur))
    out.discard(cur)
    return out


def phase_time(T: Timetable, log):
    moved = 0
    for i in range(len(T.units)):
        if not T.can_time[i]:
            continue
        u = T.units[i]
        unit = set(u)
        cands = []
        for wd, ini in candidates_time(T, i):
            new = {}
            for sid in u:
                d, _, r = T.pos[sid]
                new[sid] = (d - dt.timedelta(days=d.weekday() - wd), ini, r)
            d = T.delta(new)
            if better(d):
                cands.append((d, new))
        cands.sort(key=lambda x: key(x[0]))
        for d, new in cands:
            if not T.time_ok(new, unit):
                continue
            if T.room_ok(new, unit):
                T.move(new)
                moved += 1
                log(d)
                break
            for r in rooms_by_preference(T, i):                     # same slot, another room
                new2 = {sid: (p[0], p[1], r if T.S[sid].tipus != 'PLAB' and not T.S[sid].sense_espai else p[2])
                        for sid, p in new.items()}
                if T.room_ok(new2, unit):
                    d2 = T.delta(new2)
                    if better(d2):
                        T.move(new2)
                        moved += 1
                        log(d2)
                    break
            else:
                continue
            break
    return moved


def rooms_by_preference(T, i):
    cur = collections.Counter(T.pos[sid][2] for sid in T.units[i])
    return sorted(T.allowed[i], key=lambda r: (-cur[r], T.b.aules[r].capacitat if r in T.b.aules else 0))


def phase_rooms(T: Timetable, log):
    moved = 0
    for i, u in enumerate(T.units):
        if not T.can_room[i]:
            continue
        unit = set(u)
        cands = []
        for r in T.allowed[i]:
            new = {sid: (p[0], p[1], r if not T.S[sid].sense_espai and T.S[sid].tipus != 'PLAB' else p[2])
                   for sid in u for p in [T.pos[sid]]}
            if all(new[sid] == T.pos[sid] for sid in u):
                continue
            d = T.delta(new)
            if better(d):
                cands.append((d, r, new))
        cands.sort(key=lambda x: key(x[0]))
        for d, r, new in cands:
            if T.room_ok(new, unit):
                T.move(new)
                moved += 1
                log(d)
                break
    return moved


# ---------------------------------------------------------------------------------------- LAHC
def needs_room(T, sid):
    s = T.S[sid]
    return not s.sense_espai and s.tipus != 'PLAB'


def with_room(T, i, r):
    return {sid: (p[0], p[1], r if needs_room(T, sid) else p[2]) for sid in T.units[i] for p in [T.pos[sid]]}


def move_room(T, rng):
    """A unit goes to another allowed room."""
    i = rng.choice(T.room_units)
    r = rng.choice(T.allowed[i])
    return with_room(T, i, r), set(T.units[i]), False


def move_swap(T, rng):
    """Two units that meet in time exchange their rooms (what single moves cannot do when rooms are full)."""
    i = rng.choice(T.room_units)
    u = T.units[i]
    sid = rng.choice([x for x in u if needs_room(T, x)])
    date, ini, room = T.pos[sid]
    r = rng.choice(T.allowed[i])
    if r == room:
        return None
    fi = ini + T.S[sid].durada
    occ = [o for o in T.room_occ[(date, r)] if T.pos[o][1] < fi and ini < T.pos[o][1] + T.S[o].durada]
    if not occ:
        return with_room(T, i, r), set(u), False
    j = T.unit_of[occ[0]]
    if j == i or not T.can_room.get(j) or room not in T.allowed[j]:
        return None
    new = with_room(T, i, r)
    new.update(with_room(T, j, room))
    return new, set(u) | set(T.units[j]), False


def move_time(T, rng):
    """A unit goes to a slot next to another class of one of its groups (rooms kept, or a random free one)."""
    i = rng.choice(T.time_units)
    cands = list(candidates_time(T, i))
    if not cands:
        return None
    wd, ini = rng.choice(cands)
    new = {}
    for sid in T.units[i]:
        d, _, r = T.pos[sid]
        new[sid] = (d - dt.timedelta(days=d.weekday() - wd), ini, r)
    unit = set(T.units[i])
    if T.can_room[i] and T.allowed[i] and not T.room_free(new, unit):
        r = rng.choice(T.allowed[i])
        new = {sid: (p[0], p[1], r if needs_room(T, sid) else p[2]) for sid, p in new.items()}
    return new, unit, True


def lahc(T, seconds, seed, hist_len=2000):
    """Late Acceptance Hill Climbing. Returns (best vector, best positions, moves tried, moves accepted)."""
    rng = random.Random(seed)
    T.room_units = [i for i in range(len(T.units)) if T.can_room[i] and T.allowed[i]]
    T.time_units = [i for i in range(len(T.units)) if T.can_time[i]]
    kinds = ([move_time] * 3 if T.time_units else []) + ([move_room] * 2 + [move_swap] * 3 if T.room_units else [])
    cur = T.total()
    if not kinds:
        return cur, dict(T.pos), 0, 0
    best, best_pos = cur, dict(T.pos)
    hist = [key(cur)] * hist_len
    t_end = time.time() + seconds
    it = acc = 0
    while True:
        it += 1
        if it % 200 == 0 and time.time() > t_end:
            break
        mv = rng.choice(kinds)(T, rng)
        if not mv:
            continue
        new, unit, check_time = mv
        k = it % hist_len
        limit = max(hist[k], key(cur))
        d = T.attempt(new, unit, lambda dd: key(vadd(cur, dd)) <= limit, check_time)
        if d is not None:
            acc += 1
            cur = vadd(cur, d)
            if key(cur) < key(best):
                best, best_pos = cur, dict(T.pos)
        hist[k] = key(cur)
    return best, best_pos, it, acc


_T = None


def _worker(args):
    seconds, seed = args
    best, pos, it, acc = lahc(_T, seconds, seed)
    return best, pos, it, acc, seed


def rows_from_pos(sid, p, prop):
    date, ini, room = p
    return {'dia': DIES[date.weekday()], 'h_ini': f'{ini // 60:02d}:{ini % 60:02d}', 'aula': room,
            'data': prop[sid].get('data', '')}


def show(v):
    order = list(WEIGHTS) + [i for i in PRIO if i not in WEIGHTS] if WEIGHTS else PRIO
    txt = '  '.join(f'{ORDER[i]}={v[i]}' for i in order)
    return txt + (f'  [score {key(v)[0]:.4f}]' if WEIGHTS else '')


def starting_points(d: Path, src: Path):
    """For --des-de millor: the best-scored verified variant(s) and the previous proposal."""
    out = []
    vd = d / 'variants'
    scores = {}
    for t in sorted(vd.glob('puntuacions*.txt')):
        for line in open(t, encoding='utf-8-sig'):
            parts = line.replace(';', ' ').split()
            if len(parts) >= 2:
                scores[parts[0]] = parts[1]
    for t in sorted(vd.glob('ronda*.csv')):
        text = open(t, encoding='utf-8-sig').read()
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=',;\t')
        for r in csv.DictReader(text.splitlines(), dialect=dialect):
            sc = (scores.get(r['variant']) or r.get('puntuacio') or '').strip().replace(',', '.')
            if sc and r['veredicte'].startswith('VALIDA'):
                scores[r['variant']] = sc
            elif r['variant'] in scores and not r['veredicte'].startswith('VALIDA'):
                scores.pop(r['variant'])
    ranked = sorted(((float(v), k) for k, v in scores.items() if (vd / f'{k}.csv').exists()), reverse=True)
    if ranked:
        top = ranked[0][0]
        out += [vd / f'{k}.csv' for v, k in ranked if v == top]   # every variant tied for the best score
        print(f'  best xaman score so far: {top:g} ({", ".join(k for v, k in ranked if v == top)})')
    for prev in (d / 'proposta-anterior.csv', src):
        if prev.exists():
            out.append(prev)
    return out


# ---------------------------------------------------------------------------------------- main
SCOPE = {
    '5.1': (lambda ss: True, False),
    '5.2': (lambda ss: True, True),
    '5.4': (lambda ss: all(s.id.startswith('N') for s in ss), True),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pregunta', default='5.2', choices=['5.1', '5.2', '5.3', '5.4'])
    ap.add_argument('--dir', type=Path)
    ap.add_argument('--passades', type=int, default=20, help='maximum passes per greedy phase')
    ap.add_argument('--temps', type=int, default=180, help='seconds of LAHC (0 = greedy only)')
    ap.add_argument('--fils', type=int, default=min(8, os.cpu_count() or 1), help='parallel LAHC workers')
    ap.add_argument('--llavor', type=int, default=1, help='first random seed')
    ap.add_argument('--pesos', help='weighted mode, e.g. "canvis_aula=3,desplacaments_aula=1" '
                                    '(default: solver/pesos-<q>.txt if it exists, else the priority order)')
    ap.add_argument('--ordre', action='store_true', help='ignore pesos-<q>.txt and use the priority order')
    ap.add_argument('--sortida', type=Path, help='write the proposal here instead of out/<q>/proposta.csv')
    ap.add_argument('--des-de', dest='des_de', default='sat',
                    help='start from: "sat" (the SAT proposal), "millor" (the best known: the best-scored variant, '
                         'the previous proposta.csv or the SAT one, whichever is best) or a proposal file')
    a = ap.parse_args()
    global PRIO, _T, WEIGHTS, REF
    if a.pregunta not in SCOPE:
        print(f'{a.pregunta}: nothing to improve (its objective is the fewest changes w.r.t. 5.2)')
        return
    d = a.dir or HERE / 'out' / a.pregunta
    src, keep = d / 'proposta.csv', d / 'proposta-sat.csv'
    if not keep.exists():
        shutil.copy(src, keep)
    base = load(a.pregunta)

    def read(path):
        with open(path, encoding='utf-8') as f:
            rd = csv.DictReader(f)
            return rd.fieldnames, {r['id_sessio']: r for r in rd}

    fields, prop = read(keep)
    relaxed = set()
    rel = d / 'relaxacions.csv'
    if rel.exists():
        for r in csv.DictReader(open(rel, encoding='utf-8')):
            if r['restriccio'] == 'R1-TORN':
                relaxed |= set(r['sessions'].split('|'))
            if r['restriccio'] == 'R5-SENSE-AULA':
                NOROOM.update(r['sessions'].split('|'))
    if NOROOM:
        print(f'  {len(NOROOM)} sessions declared R5-SENSE-AULA: they keep no room')
    scope, with_time = SCOPE[a.pregunta]
    PRIO = PRIORITY[a.pregunta]
    # a folder of its own (--dir, e.g. out/truc/5.2) learns its own weights: <dir>/pesos.txt
    wfile = (d / 'pesos.txt') if a.dir else HERE / f'pesos-{a.pregunta}.txt'
    text = a.pesos or (wfile.read_text(encoding='utf-8').strip() if wfile.exists() and not a.ordre else '')
    if text:
        WEIGHTS = parse_weights(text)
        print('weighted: ' + ' + '.join(f'{w:g}*{ORDER[i]}' for i, w in WEIGHTS.items())
              + ('' if a.pesos else f'   (from {wfile.name})'))
    else:
        print('priority: ' + ' > '.join(ORDER[i] for i in PRIO))
    t0 = time.time()
    T = Timetable(base, prop, relaxed, scope, with_time)
    REF = tuple(max(1, x) for x in T.total())       # weights are always relative to the SAT proposal
    if a.des_de != 'sat':
        cands = [Path(a.des_de)] if a.des_de != 'millor' else starting_points(d, src)
        best_t, best_name = T, keep.name
        for c in cands:
            try:
                _, pc = read(c)
                if a.pregunta == '5.4':
                    # 5.4 sits on top of 5.2: a start built on an older 5.2 would bring back thousands of changes
                    stale = sum(1 for sid, r in prop.items() if not sid.startswith('N') and pc.get(sid) != r)
                    if stale:
                        print(f'  (skipping {c.name}: {stale} sessions of 5.2 differ from the current 5.2)')
                        continue
                Tc = Timetable(base, pc, relaxed, scope, with_time)
            except (OSError, KeyError, ValueError) as e:
                print(f'  (skipping {c.name}: {e})')
                continue
            print(f'  candidate start {c.name}: ' + show(Tc.total()))
            if key(Tc.total()) < key(best_t.total()) or (a.des_de != 'millor' and best_name == keep.name):
                best_t, best_name, prop = Tc, c.name, pc
        T = best_t
        print(f'  starting from {best_name}')
    start = T.total()
    print(f'{a.pregunta}: {len(T.units)} units ({sum(T.can_time.values())} may move, '
          f'{sum(T.can_room.values())} may change room)')
    print('  start  ' + show(start))
    acc = [0] * len(ORDER)

    def log(dv):
        for k, x in enumerate(dv):
            acc[k] += x

    def greedy(T, label):
        for name, phase, on in (('day/hour', phase_time, with_time), ('rooms', phase_rooms, True)):
            if not on:
                continue
            for p in range(1, a.passades + 1):
                n = phase(T, log)
                print(f'  {label} {name:8} pass {p}: {n:4} moves -> ' + show(T.total())
                      + f'  ({time.time() - t0:.0f} s)', flush=True)
                if not n:
                    break

    greedy(T, 'greedy')
    if a.temps > 0:
        print(f'  LAHC: {a.fils} workers x {a.temps} s ...', flush=True)
        _T = T
        with mp.get_context('fork').Pool(a.fils) as pool:
            res = pool.map(_worker, [(a.temps, a.llavor + k) for k in range(a.fils)])
        for best, _, it, acc_, seed in sorted(res, key=lambda r: key(r[0])):
            print(f'    seed {seed}: {it} moves tried, {acc_} accepted -> ' + show(best))
        best, pos = min(((r[0], r[1]) for r in res), key=lambda r: key(r[0]))
        if key(best) < key(T.total()):
            for sid, p in pos.items():
                prop[sid].update(rows_from_pos(sid, p, prop))
            T = Timetable(base, prop, relaxed, scope, with_time)
            greedy(T, 'polish')
    end = T.total()
    print('  end    ' + show(end))
    out = a.sortida or src
    with open(out, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(fields)
        for sid in base.ordre:
            date, ini, room = T.pos[sid]
            row = {'id_sessio': sid, 'dia': DIES[date.weekday()], 'h_ini': f'{ini // 60:02d}:{ini % 60:02d}',
                   'aula': room, 'data': prop[sid].get('data', '')}
            w.writerow([row[k] for k in fields])
    print(f'improved proposal -> {out} (the SAT one stays in {keep.name})')


if __name__ == '__main__':
    main()
