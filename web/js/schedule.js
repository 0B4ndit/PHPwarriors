// Time-aware occupancy: pure functions, no DOM / three.js.
//
// Dataset (GET /api/sessions, built by db.py from the DuckDB database):
//   { window: {start, end}              minutes of the day that count as "open" (e.g. 510..1260 = 08:30..21:00)
//     semesters: {"1": {start, end}, "2": {...}}   ISO dates of the first/last teaching day
//     calendar: [{date, tipus, h_ini, h_fi, motiu}]  festiu | no_lectiu | avaluacio | aturada
//     sessions: [[date, startMin, durMin, roomId, students, labelIdx], ...]   only sessions in rooms shown by the hologram
//     labels: [[className, group, teachers], ...] }
//
// Views:
//   hour     -> students in each room at that minute (colour = students / capacity, flag when over capacity)
//   day|week|semester -> % of the open time the room has a class (students are irrelevant)

const DAY = 86400000;
export const parse = (iso) => new Date(`${iso}T00:00:00Z`);
export const fmt = (d) => d.toISOString().slice(0, 10);
export const addDays = (iso, n) => fmt(new Date(parse(iso).getTime() + n * DAY));
export const weekday = (iso) => parse(iso).getUTCDay(); // 0 = Sunday
export const isWeekend = (iso) => [0, 6].includes(weekday(iso));
export const semOf = (iso) => { const m = Number(iso.slice(5, 7)); return m >= 9 || m === 1 ? 1 : 2; };
export const toMin = (hhmm) => { const [h, m] = hhmm.split(':').map(Number); return h * 60 + m; };
export const hhmm = (min) => `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;
export const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export function addWeekdays(iso, n) {
  let d = iso;
  const sgn = n < 0 ? -1 : 1;
  for (let i = 0; i < Math.abs(n); i++) { do { d = addDays(d, sgn); } while (isWeekend(d)); }
  return d;
}
export const mondayOf = (iso) => addDays(iso, -((weekday(iso) + 6) % 7));
export function isoWeek(iso) { // "2027-W05"
  const d = parse(addDays(mondayOf(iso), 3)); // Thursday decides the ISO year
  const y = d.getUTCFullYear();
  const jan1 = new Date(Date.UTC(y, 0, 1));
  return `${y}-W${String(Math.floor((d - jan1) / DAY / 7) + 1).padStart(2, '0')}`;
}

const overlap = (a0, a1, b0, b1) => Math.max(0, Math.min(a1, b1) - Math.max(a0, b0));

export class Schedule {
  constructor(ds) {
    this.window = ds.window;
    this.labels = ds.labels || []; // [[className, group, teachers 'D1|D2'], ...]
    this.semesters = ds.semesters || {};
    this.cal = new Map((ds.calendar || []).map((c) => [c.date, c]));
    this.byRoom = new Map(); // room -> date -> [{s, e, n}]
    for (const [date, start, dur, room, n, l] of ds.sessions) {
      if (!this.byRoom.has(room)) this.byRoom.set(room, new Map());
      const days = this.byRoom.get(room);
      if (!days.has(date)) days.set(date, []);
      days.get(date).push({ s: start, e: start + dur, n, l: l ?? -1 });
    }
    this.count = ds.sessions.length;
  }

  inSemester(date) {
    const r = this.semesters[semOf(date)];
    return !r || (date >= r.start && date <= r.end);
  }

  /** Is it a teaching day, and how many open minutes does it have? */
  dayInfo(date) {
    const { start, end } = this.window;
    if (isWeekend(date)) return { lective: false, avail: 0, reason: 'weekend' };
    if (!this.inSemester(date)) return { lective: false, avail: 0, reason: 'outside the semester' };
    const c = this.cal.get(date);
    if (c && ['festiu', 'no_lectiu', 'avaluacio'].includes(c.tipus)) {
      return { lective: false, avail: 0, reason: `${c.tipus}${c.motiu ? `: ${c.motiu}` : ''}` };
    }
    let closed = null, avail = end - start;
    if (c && c.tipus === 'aturada' && c.h_ini && c.h_fi) {
      closed = [toMin(c.h_ini), toMin(c.h_fi)];
      avail -= overlap(start, end, closed[0], closed[1]);
    }
    return { lective: true, avail, closed, reason: c && c.motiu ? `${c.tipus}: ${c.motiu}` : '' };
  }

  /** Minutes the room has a class inside the open window (overlapping classes counted once). */
  occupiedMinutes(room, date, info = this.dayInfo(date)) {
    const list = this.byRoom.get(room)?.get(date);
    if (!list || !info.lective) return 0;
    const { start, end } = this.window;
    const iv = list.map((x) => [Math.max(x.s, start), Math.min(x.e, end)]).filter(([a, b]) => b > a).sort((a, b) => a[0] - b[0]);
    let total = 0, cur = null;
    const flush = () => { if (cur) total += (cur[1] - cur[0]) - (info.closed ? overlap(cur[0], cur[1], info.closed[0], info.closed[1]) : 0); };
    for (const [a, b] of iv) {
      if (cur && a <= cur[1]) cur[1] = Math.max(cur[1], b);
      else { flush(); cur = [a, b]; }
    }
    flush();
    return total;
  }

  studentsAt(room, date, min) {
    let n = 0, sessions = 0;
    for (const x of this.byRoom.get(room)?.get(date) || []) if (x.s <= min && min < x.e) { n += x.n; sessions++; }
    return { n, sessions };
  }

  labelOf(l) {
    const x = this.labels[l];
    return x ? { name: x[0], group: x[1], teachers: x[2] } : { name: '(unnamed class)', group: '', teachers: '' };
  }

  /** Classes taking place in a room at a given minute (for the hour bubble). */
  sessionsAt(room, date, min) {
    if (!this.dayInfo(date).lective) return [];
    return (this.byRoom.get(room)?.get(date) || []).filter((x) => x.s <= min && min < x.e)
      .map((x) => ({ ...this.labelOf(x.l), n: x.n, s: x.s, e: x.e }));
  }

  /** Classes of a room over the view's period, for the side list.
   *  day: hours only. week: weekday + hours. semester: weekly pattern (weekday + hours, xN occurrences). */
  listing(room, view) {
    const days = view.scope === 'day' ? (this.dayInfo(view.date).lective ? [view.date] : []) : this.lectiveDays(view);
    const groups = new Map();
    for (const d of days) {
      for (const x of this.byRoom.get(room)?.get(d) || []) {
        const wd = (weekday(d) + 6) % 7; // Monday = 0
        const key = view.scope === 'week' ? `${d}|${x.s}|${x.e}|${x.l}` : `${view.scope === 'day' ? '' : wd}|${x.s}|${x.e}|${x.l}`;
        const g = groups.get(key) || { wd, s: x.s, e: x.e, l: x.l, count: 0, date: d };
        g.count++;
        groups.set(key, g);
      }
    }
    const hours = (g) => `${hhmm(g.s)}–${hhmm(g.e)}`;
    return [...groups.values()]
      .sort((a, b) => (view.scope === 'week' ? a.date.localeCompare(b.date) : a.wd - b.wd) || a.s - b.s)
      .map((g) => ({ when: view.scope === 'day' ? hours(g) : `${DOW[(g.wd + 1) % 7]} ${hours(g)}`, count: g.count, ...this.labelOf(g.l) }));
  }

  lectiveDays(view) {
    const sem = semOf(view.date);
    if (view.scope === 'week') {
      const mon = mondayOf(view.date);
      return [0, 1, 2, 3, 4].map((i) => addDays(mon, i)).filter((d) => this.dayInfo(d).lective);
    }
    const r = this.semesters[view.scope === 'semester' ? view.sem : sem];
    const out = [];
    if (r) for (let d = r.start; d <= r.end; d = addDays(d, 1)) if (this.dayInfo(d).lective) out.push(d);
    return out;
  }

  /** rooms: Map id -> capacity. Returns { rooms: Map id -> {value 0..100, label, over, n?}, info: string } */
  evaluate(view, rooms) {
    const out = new Map();
    const win = `${hhmm(this.window.start)}–${hhmm(this.window.end)}`;
    if (view.scope === 'hour') {
      const di = this.dayInfo(view.date);
      let inUse = 0, students = 0;
      for (const [id, cap] of rooms) {
        const { n, sessions } = di.lective ? this.studentsAt(id, view.date, view.min) : { n: 0, sessions: 0 };
        if (sessions) inUse++;
        students += n;
        out.set(id, { value: cap ? Math.min(100, (n / cap) * 100) : 0, label: `${n}/${cap}`, over: n > cap, n, cap, sessions });
      }
      const head = `${DOW[weekday(view.date)]} ${view.date} · ${hhmm(view.min)}`;
      const info = di.lective
        ? `${head} — ${inUse}/${rooms.size} rooms in use, ${students} students${di.reason ? ` (${di.reason})` : ''}`
        : `${head} — no classes (${di.reason})`;
      return { rooms: out, info, summary: di.lective ? `${inUse}/${rooms.size} in use · ${students} students` : 'no classes' };
    }

    const days = view.scope === 'day' ? [view.date] : this.lectiveDays(view);
    const infos = days.map((d) => [d, this.dayInfo(d)]);
    const avail = infos.reduce((a, [, i]) => a + i.avail, 0);
    let used = 0;
    for (const [id] of rooms) {
      const occ = infos.reduce((a, [d, i]) => a + this.occupiedMinutes(id, d, i), 0);
      const pct = avail ? (occ / avail) * 100 : 0;
      if (occ > 0) used++;
      out.set(id, { value: pct, label: `${Math.round(pct)}%`, over: false });
    }
    const lect = infos.filter(([, i]) => i.lective).length;
    let info;
    if (view.scope === 'day') {
      const i = infos[0][1];
      info = `${DOW[weekday(view.date)]} ${view.date} — ${i.lective ? `open ${win}${i.reason ? ` (${i.reason})` : ''}` : `no classes (${i.reason})`}`;
    } else if (view.scope === 'week') {
      const mon = mondayOf(view.date);
      info = `${isoWeek(view.date)} (${mon} → ${addDays(mon, 4)}) · ${lect} teaching days · open ${win}`;
    } else {
      const r = this.semesters[view.sem];
      info = `Semester ${view.sem}${r ? ` (${r.start} → ${r.end})` : ''} · ${lect} teaching days · open ${win}`;
    }
    const mean = rooms.size ? [...out.values()].reduce((a, v) => a + v.value, 0) / rooms.size : 0;
    return { rooms: out, info, summary: `${used}/${rooms.size} with classes · mean ${Math.round(mean)}%` };
  }
}

/** Keyboard/button navigation. dir: left|right|up|down. Back = left/up. */
export function step(view, dir, win) {
  const sgn = dir === 'left' || dir === 'up' ? -1 : 1;
  const horiz = dir === 'left' || dir === 'right';
  const v = { ...view };
  if (v.scope === 'hour') {
    if (horiz) {
      let m = sgn > 0 ? (Math.floor(v.min / 30) + 1) * 30 : (Math.ceil(v.min / 30) - 1) * 30;
      if (m >= win.end) { v.date = addWeekdays(v.date, 1); m = Math.ceil(win.start / 30) * 30; }
      else if (m < win.start) { v.date = addWeekdays(v.date, -1); m = Math.floor((win.end - 1) / 30) * 30; }
      v.min = m;
    } else v.date = addWeekdays(v.date, sgn);
  } else if (v.scope === 'day') {
    v.date = addWeekdays(v.date, horiz ? sgn : 5 * sgn);
  } else if (v.scope === 'week') {
    v.date = addDays(v.date, 7 * sgn);
  } else {
    v.sem = v.sem === 1 ? 2 : 1;
  }
  if (v.scope !== 'semester') v.sem = semOf(v.date);
  return v;
}
