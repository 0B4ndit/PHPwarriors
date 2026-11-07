#!/usr/bin/env python3
"""Rule 10: weekly grid per room of the most advanced proposal -> out/graella.html (one self-contained file).

    python3 graella.py                    # out/5.4 if it exists, else 5.3, 5.2, 5.1
    python3 graella.py --pregunta 5.2

Pick a week and a room (or all rooms); every class shows subject, group, type and students.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path

from exporta import DIES, load, monday, week_of
from horaris.model import hm

HERE = Path(__file__).resolve().parent

PAGE = r"""<!doctype html>
<html lang="ca"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Graella per aula</title>
<style>
:root{--bg:#fff;--fg:#1d2327;--dim:#68737d;--line:#dde2e6;--head:#f3f5f7;--TE:#cfe3ff;--PAUL:#d7f2dd;--PLAB:#fde5c8;--SEM:#eadcfb}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#15191c;--fg:#e4e8eb;--dim:#93a0aa;--line:#2c343a;--head:#1d2327;--TE:#22406a;--PAUL:#1f4a2c;--PLAB:#5a3d16;--SEM:#43305e}}
body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.35 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center;z-index:2}
h1{font-size:15px;margin:0 12px 0 0}select,button{font:inherit;padding:3px 6px;background:var(--head);color:var(--fg);border:1px solid var(--line);border-radius:4px}
.room{margin:14px 16px 24px}.room h2{font-size:14px;margin:0 0 6px}.room h2 span{color:var(--dim);font-weight:400}
.grid{display:grid;grid-template-columns:44px repeat(5,minmax(0,1fr));border:1px solid var(--line);position:relative}
.col{position:relative;border-left:1px solid var(--line)}.dh{background:var(--head);text-align:center;padding:3px;border-bottom:1px solid var(--line);font-weight:600}
.hr{height:22px;border-top:1px dashed var(--line);box-sizing:border-box;font-size:10px;color:var(--dim);padding-left:2px}
.ev{position:absolute;left:2px;right:2px;border-radius:4px;padding:1px 4px;overflow:hidden;font-size:11px;border:1px solid rgba(0,0,0,.08)}
.ev b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ev i{font-style:normal;color:var(--dim)}
.off{background:repeating-linear-gradient(45deg,transparent 0 6px,var(--line) 6px 7px)}
.note{color:var(--dim);margin:8px 16px}@media print{header{position:static}.room{break-inside:avoid}}
</style></head><body>
<header><h1>Graella setmanal per aula · __TITLE__</h1>
<label>Setmana <select id="wk"></select></label><label>Aula <select id="rm"><option value="*">Totes</option></select></label>
<button onclick="print()">Imprimeix</button></header>
<p class="note">Franja 8:30-21:00 · ratllat = dia sense classes (festiu, no lectiu o setmana d'avaluació) · __SRC__</p>
<div id="out"></div>
<script>
const D=__DATA__, H0=510, H1=1260, PX=22/30, DAYS=['Dl','Dt','Dc','Dj','Dv'];
const wk=document.getElementById('wk'), rm=document.getElementById('rm'), out=document.getElementById('out');
D.weeks.forEach(w=>wk.add(new Option(`${w.label} (${w.n} classes)`, w.id)));
D.rooms.forEach(r=>rm.add(new Option(`${r.id} · ${r.cap} places`, r.id)));
wk.value=D.weeks.reduce((a,b)=>b.n>a.n?b:a).id;
function el(t,c,h){const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e}
function hh(m){return `${Math.floor(m/60)}:${String(m%60).padStart(2,'0')}`}
function draw(){
  out.textContent='';const w=D.weeks.find(x=>x.id==wk.value);
  const rooms=D.rooms.filter(r=>rm.value=='*'||r.id==rm.value);
  for(const r of rooms){
    const evs=D.ses.filter(s=>s.r==r.id&&s.w==w.id);if(rm.value=='*'&&!evs.length)continue;
    const box=el('section','room');box.append(el('h2',null,`${r.id} <span>${r.tipus} · ${r.cap} places · ${evs.length} classes</span>`));
    const g=el('div','grid');g.append(el('div','dh',''));w.dates.forEach((d,i)=>g.append(el('div','dh',`${DAYS[i]} ${d.slice(8)}/${d.slice(5,7)}`)));
    const axis=el('div');for(let t=H0;t<H1;t+=30)axis.append(el('div','hr',t%60==30?hh(t):''));g.append(axis);
    w.dates.forEach((d,i)=>{const c=el('div','col'+(w.off.includes(d)?' off':''));
      for(let t=H0;t<H1;t+=30)c.append(el('div','hr',''));
      evs.filter(s=>s.d==d).forEach(s=>{const e=el('div','ev',`<b>${s.a}</b>${s.g} · ${s.k}<br><i>${hh(s.s)}-${hh(s.e)} · ${s.n} alumnes</i>`);
        e.style.top=((s.s-H0)*PX)+'px';e.style.height=((s.e-s.s)*PX-2)+'px';e.style.background=`var(--${s.k})`;e.title=`${s.a} ${s.g} (${s.c})`;c.append(e)});
      g.append(c)});
    box.append(g);out.append(box)}
  if(!out.children.length)out.append(el('p','note','Cap classe en aquesta aula aquesta setmana.'))}
wk.onchange=rm.onchange=draw;draw();
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pregunta', help='which proposal (default: the most advanced one that exists)')
    a = ap.parse_args()
    q = a.pregunta or next((x for x in ('5.4', '5.3', '5.2', '5.1') if (HERE / 'out' / x / 'proposta.csv').exists()), None)
    if not q:
        raise SystemExit('no proposal yet: run "make 5.2" (or 5.4) first')
    base = load(q)
    src = HERE / 'out' / q / 'proposta.csv'
    prop = {r['id_sessio']: r for r in csv.DictReader(open(src, encoding='utf-8'))}
    names = {}                                   # subject code -> name (sessions.csv + scenario extras)
    for f in [HERE.parent / 'paquet' / 'sessions.csv', *(HERE.parent / 'paquet' / 'escenaris').glob('*/sessions_extra.csv')]:
        for r in csv.DictReader(open(f, encoding='utf-8')):
            names.setdefault(r['codi'], r['assignatura'])
    shared = {}                                  # a shared class counts once, with all its students
    for x in base.sessions.values():
        if x.compartida:
            shared[x.compartida] = shared.get(x.compartida, 0) + (0 if x.sense_espai else x.alumnes)
    ses, seen, weeks = [], set(), {}
    for sid, s in base.sessions.items():
        p = prop[sid]
        if not p['aula'] or s.sense_espai:
            continue
        date = (dt.date.fromisoformat(p['data']) if p.get('data') else
                monday(week_of(s.data)) + dt.timedelta(days=DIES.index(p['dia'])))
        key = (s.compartida or sid, p['aula'])
        if key in seen:
            continue
        seen.add(key)
        ini = hm(p['h_ini'])
        n = shared[s.compartida] if s.compartida else s.alumnes
        w = week_of(date)
        weeks[w] = weeks.get(w, 0) + 1
        ses.append({'r': p['aula'], 'w': w, 'd': date.isoformat(), 's': ini, 'e': ini + s.durada,
                    'a': names.get(s.codi, s.codi), 'g': s.grup, 'k': s.tipus, 'n': n, 'c': ' | '.join(s.cohorts)})
    week_list = []
    for w in sorted(weeks):
        dates = [monday(w) + dt.timedelta(days=i) for i in range(5)]
        off = [d.isoformat() for d in dates if d in base.dies_sense_classe or any(
            a <= 0 and b >= 1440 for a, b in base.aturades.get(d, ()))]
        week_list.append({'id': w, 'label': f'{dates[0]:%d/%m}-{dates[4]:%d/%m/%Y}', 'n': weeks[w],
                          'dates': [d.isoformat() for d in dates], 'off': off})
    used = {x['r'] for x in ses}
    rooms = [{'id': r, 'tipus': x.tipus, 'cap': x.capacitat} for r, x in sorted(base.aules.items()) if r in used]
    rooms += [{'id': r, 'tipus': 'fora de l\'aulari', 'cap': '-'} for r in sorted(used - set(base.aules))]
    data = json.dumps({'weeks': week_list, 'rooms': rooms, 'ses': ses}, ensure_ascii=False, separators=(',', ':'))
    out = HERE / 'out' / 'graella.html'
    out.write_text(PAGE.replace('__DATA__', data).replace('__TITLE__', f'proposta {q}')
                   .replace('__SRC__', f'font: out/{q}/proposta.csv'), encoding='utf-8')
    print(f'weekly grid of {q} ({len(ses)} classes, {len(rooms)} rooms, {len(week_list)} weeks) -> {out}')


if __name__ == '__main__':
    main()
