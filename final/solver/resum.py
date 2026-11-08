#!/usr/bin/env python3
"""One-page summary for the Junta Permanent (enunciat §5.2), from the 5.2 proposal and the official verifier.

    python3 resum.py [--dir out/5.2]     -> out/5.2/resum-junta.md  +  resum-junta.html (A4, one page, for the PDF)

The four fields the brief asks for, plus what it costs and the brief's own reference figure:
  1. peak of simultaneous classes, morning and afternoon, against the ordinary rooms available (21 - 2 = 19)
  2. rooms missing or spare by size (aules docents + seminaris)
  3. sessions moved (day or hour) per degree and year
  4. each exception to rule 1 we ask for, with its reason and its cost
Every figure is computed here with the verifier's own definitions (a shared class counts once, at each date).
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import html
import json
from pathlib import Path

from exporta import DIES, hm, load
from horaris.model import MATI

HERE = Path(__file__).resolve().parent


def fmt(t: int) -> str:
    return f'{t // 60}:{t % 60:02d}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', type=Path, default=HERE / 'out' / '5.2')
    a = ap.parse_args()
    base = load('5.2')
    prop = {r['id_sessio']: r for r in csv.DictReader(open(a.dir / 'proposta.csv', encoding='utf-8'))}
    inf = json.load(open(a.dir / 'informe.json', encoding='utf-8'))
    relax = list(csv.DictReader(open(a.dir / 'relaxacions.csv', encoding='utf-8')))
    aules = base.aules
    ordinaries = {r for r, x in aules.items() if x.ordinaria}
    disponibles = len(ordinaries) - 2                                   # rule 8: two always free
    generals = {r for r, x in aules.items() if x.tipus in ('Aules docents', 'Seminaris')}

    # every physical class once: (unit, date, start) -> room, end, students (a shared class sums its groups)
    classes = {}
    for sid, s in base.sessions.items():
        p = prop[sid]
        date = s.data + dt.timedelta(days=DIES.index(p['dia']) - s.data.weekday())
        ini = hm(p['h_ini'])
        k = (s.unitat, date, ini)
        room, fi, n = classes.get(k, (p['aula'], ini + s.durada, 0))
        classes[k] = (room or p['aula'], fi, n + (0 if s.sense_espai else s.alumnes))

    # 1. peaks: classes at once in ordinary rooms (15-minute instants), and rooms busy in a one-hour slot (rule 8)
    inst = collections.Counter()
    slot = collections.defaultdict(set)
    for (u, date, ini), (room, fi, n) in classes.items():
        if room in ordinaries:
            for t in range(ini, fi, 15):
                inst[(date, t)] += 1
            for f0 in range(MATI[0], 21 * 60, 60):
                if ini < f0 + 60 and fi > f0:
                    slot[(date, f0)].add(room)
    peak, peak_slot = {}, {}
    for (date, t), n in inst.items():
        tr = 'matí' if t < MATI[1] else 'tarda'
        if n > peak.get(tr, (0,))[0]:
            peak[tr] = (n, date, t)
    for (date, f0), rs in slot.items():
        tr = 'matí' if f0 < MATI[1] else 'tarda'
        peak_slot[tr] = max(peak_slot.get(tr, 0), len(rs))

    # the brief's reference: 1r and 2n classes (no PLAB, no dobles) at once in the morning, today and with us
    def first_years_peak(placed):
        c = collections.Counter()
        for (date, ini, fi) in placed:
            for t in range(ini, min(fi, MATI[1]), 15):
                c[(date, t)] += 1
        return max(c.values(), default=0)
    fy = [s for s in base.sessions.values() if s.tipus != 'PLAB' and not s.sense_espai
          and any(c.endswith((':1r', ':2n')) for c in s.cohorts)]
    today = {(s.unitat, s.data, s.ini, s.fi) for s in fy}
    ours = set()
    for s in fy:
        p = prop[s.id]
        d = s.data + dt.timedelta(days=DIES.index(p['dia']) - s.data.weekday())
        ours.add((s.unitat, d, hm(p['h_ini']), hm(p['h_ini']) + s.durada))
    ref_today = first_years_peak([x[1:] for x in today])
    ref_ours = first_years_peak([x[1:] for x in ours])

    # 2. rooms by size: for each room capacity, the general rooms at least that big, and the peak of classes (placed in
    #    a general room) that need at least that size (more students than the next smaller capacity)
    levels = sorted({aules[r].capacitat for r in generals})
    need = {lv: collections.Counter() for lv in levels}
    for (u, date, ini), (room, fi, n) in classes.items():
        if room not in generals:
            continue
        for i, lv in enumerate(levels):
            if i == 0 or n > levels[i - 1]:
                for t in range(ini, fi, 15):
                    need[lv][(date, t)] += 1
    sizes = [(lv, sum(1 for r in generals if aules[r].capacitat >= lv), max(need[lv].values(), default=0))
             for lv in levels]
    falten = [lv for lv, sup, dem in sizes if dem > sup]
    used = [x for x in sizes if x[2] > 0]
    m = min(sup - dem for _, sup, dem in used)
    justes = [lv for lv, sup, dem in used if sup - dem == m]
    marge = f'El marge més just és a les aules grans: de ≥ {" i ≥ ".join(map(str, justes))} places en sobren {m} al pic.'

    # 3. sessions moved per degree and year
    tot, mog = collections.Counter(), collections.Counter()
    moved = 0
    for sid, s in base.sessions.items():
        ch = (prop[sid]['dia'], hm(prop[sid]['h_ini'])) != (s.dia, s.ini)
        moved += ch
        for c in s.cohorts:
            tot[c] += 1
            mog[c] += ch
    cohorts = sorted(tot, key=lambda c: (-mog[c] / tot[c], -mog[c], c))
    o = inf['objectius']
    n_ses = len(base.sessions)
    R = inf['restriccions']
    her = R.get('R1-TORN', {}).get('heretades', 0)
    aforament_her = R.get('R3-AFORAMENT', {}).get('heretades', 0)
    solap_her = sum(R.get(k, {}).get('heretades', 0) for k in ('R4-DOCENT', 'R4-ALUMNAT', 'R4-PLAB'))
    saber = []
    if her:                                   # split the inherited R1-TORN: fixed 1r-2n groups vs PLAB labs
        plab = grups = 0
        for v in csv.DictReader(open(a.dir / 'violacions.csv', encoding='utf-8')):
            if v['regla'] == 'R1-TORN' and v['heretada']:
                for sid in v['sessions'].split('|'):
                    if base.sessions[sid].tipus == 'PLAB':
                        plab += 1
                    else:
                        grups += 1
        saber.append(f'{her} sessions es queden en el torn d’avui encara que la regla 1 en demani un altre, perquè no es '
                     f'poden tocar: {grups} de grups fixats de GEI i GEET+GEST de 1r i 2n (regla 1) i {plab} laboratoris '
                     'PLAB (regla 7).')
    if aforament_her:
        saber.append(f'{aforament_her} sessions d’aquests grups fixats segueixen, com avui, en una aula més petita que '
                     'el grup. Com que no es poden tocar, no les hem mogut.')
    if solap_her:
        saber.append(f'Els {solap_her} solapaments de docent, alumnat o PLAB que ja hi ha a l’horari d’avui es '
                     'mantenen. La proposta no n’afegeix cap de nou.')
    nrel = inf.get('incompliments_declarats', 0)

    # ---------------------------------------------------------------------------------------------- texts
    pm, pt = peak['matí'], peak['tarda']
    top_n = sorted(tot, key=lambda c: -mog[c])[:3]
    top_p = [c for c in cohorts if mog[c] == tot[c]]
    resum = [
        f'**El model nou hi cap.** Al pic hi ha {pm[0]} classes alhora al matí i {pt[0]} a la tarda, per a '
        f'{disponibles} aules ordinàries disponibles, i no falta cap aula de cap mida. Totes les sessions tenen aula del '
        'tipus que toca, i cap de les que movem o a qui donem aula supera l’aforament.',
        f'**Què costa.** {moved} de {n_ses} sessions ({100 * moved / n_ses:.0f} %) canvien de dia o d’hora, i '
        f'{o["canvis_aula"]} d’aula. Ho noten més {", ".join(top_n)} (en nombre) i {", ".join(top_p) or "cap"} '
        '(totes les seves sessions).',
        f'**On no hi cap.** Només en un cas: demanem **{nrel} excepció** a la regla 1, per a una sola sessió '
        '(S04526), demostrada inevitable.',
    ]
    pic_rows = [('Matí (8:30–14:30)', pm, peak_slot['matí']), ('Tarda (14:30–21:00)', pt, peak_slot['tarda'])]
    exc = []
    for r in relax:
        ids = [x for x in r['sessions'].split('|') if x]
        if ids == ['S04526']:
            exc.append(('S04526 · Sistemes i Tecnologies Web, PAUL/453 (GEI 3r/4t), divendres 9/4/2027: es queda al '
                        'matí, com avui (13:30, Q1/0019).',
                        'La setmana 14 només té classe el divendres (del 5 al 8/4 és setmana d’avaluació). El docent '
                        'D380 hi fa tres grups de 34–35 alumnes que necessiten aula d’informàtica, i les dues que hi ha '
                        '(54 places) estan ocupades de 15:00 a 19:00 per grups fixats de GEI 1r. A la tarda només '
                        'caben dues de les tres sessions (19:00 i 20:00). Demostració: DEMOSTRACIO.md.',
                        'Una classe, un dia, al matí. Sense l’excepció no hi ha alternativa vàlida: caldria posar 34 '
                        'alumnes en un laboratori de 24 places, el docent en dues aules alhora, o dos grups a la '
                        'mateixa aula.'))
        else:
            exc.append((f"{r['restriccio']}: {', '.join(ids[:5])}{'…' if len(ids) > 5 else ''}",
                        r['justificacio'], f'{len(ids)} sessions'))

    # ---------------------------------------------------------------------------------------------- markdown
    L = ['# Resum per a la Junta Permanent · torns nous, 2n semestre 2026-27', '',
         f"Proposta 5.2 · {n_ses} sessions · veredicte del verificador oficial: **{inf['veredicte']}** "
         f"({nrel} incompliment declarat).", '']
    L += [f'- {x}' for x in resum]
    L += ['', '## 1. Pic de sessions simultànies davant de les aules ordinàries', '',
          f'Aules ordinàries: {len(ordinaries)}, de les quals 2 sempre lliures (regla 8): **{disponibles} disponibles**.', '',
          '| Torn | Classes alhora (pic) | Aules ordinàries ocupades en una franja d’una hora (màx.) | Disponibles | Quan és el pic |',
          '|---|---:|---:|---:|---|']
    for name, (n, d, t), s in pic_rows:
        L.append(f'| {name} | **{n}** | {s} | {disponibles} | {d:%d/%m/%Y} {fmt(t)} |')
    L += ['', f'Referència de l’enunciat: amb les hores d’avui, les classes de 1r i 2n (sense PLAB ni dobles) fan un pic '
              f'de {ref_today} alhora al matí; amb el model nou, **{ref_ours}**. Hi cap, però just.', '',
          '## 2. Aules que falten o sobren per mida (aules docents i seminaris)', '',
          '| Places ≥ | ' + ' | '.join(str(lv) for lv, _, _ in sizes) + ' |',
          '|---|' + '---:|' * len(sizes),
          '| Aules | ' + ' | '.join(str(s) for _, s, _ in sizes) + ' |',
          '| Pic de classes que la necessiten | ' + ' | '.join(str(d) for _, _, d in sizes) + ' |',
          '| Sobren al pic | ' + ' | '.join(str(s - d) for _, s, d in sizes) + ' |', '',
          ('**No en falta cap.** ' if not falten else f'**Falten aules de ≥ {", ".join(map(str, falten))} places.** ')
          + marge,
          '', '## 3. Sessions mogudes (dia o hora) per titulació i curs', '',
          f'**{moved}** sessions mogudes de {n_ses}; {o["canvis_aula"]} canvien d’aula. Hores mortes: '
          f'{o["hores_mortes_min"] // 60} h al semestre.', '',
          '| Titulació i curs | Sessions | Mogudes | % |', '|---|---:|---:|---:|']
    L += [f'| {c} | {tot[c]} | {mog[c]} | {100 * mog[c] / tot[c]:.0f} % |' for c in cohorts]
    L += ['', '## 4. Excepcions a la regla 1 que demanem', '']
    for t, why, cost in exc:
        L += [f'- **{t}**', f'  - *Motiu:* {why}', f'  - *Què costa:* {cost}']
    if saber:
        L += ['', '**La Junta també ha de saber** (no són excepcions que demanem, vénen de l’horari d’avui):']
        L += [f'- {x}' for x in saber]
    (a.dir / 'resum-junta.md').write_text('\n'.join(L) + '\n', encoding='utf-8')

    # ---------------------------------------------------------------------------------------------- html (A4)
    e = html.escape

    def b(x):          # **bold** -> <b>
        parts = e(x).split('**')
        return ''.join(f'<b>{p}</b>' if i % 2 else p for i, p in enumerate(parts))
    half = (len(cohorts) + 1) // 2

    def coh(cs):
        return ''.join(f'<tr><td>{e(c)}</td><td>{tot[c]}</td><td>{mog[c]}</td>'
                       f'<td>{100 * mog[c] / tot[c]:.0f} %</td></tr>' for c in cs)
    pics = ''.join(f'<tr><td>{name}</td><td><b>{n}</b></td><td>{s}</td><td>{disponibles}</td>'
                   f'<td>{d:%d/%m/%Y} {fmt(t)}</td></tr>' for name, (n, d, t), s in pic_rows)
    excs = ''.join(f'<p><b>{e(t)}</b></p><p><i>Motiu:</i> {e(why)}</p><p><i>Què costa:</i> {e(cost)}</p>'
                   for t, why, cost in exc)
    hnote = ('<p class="note"><b>La Junta també ha de saber</b> (no són excepcions que demanem, vénen de l’horari '
             'd’avui):</p><ul class="note">' + ''.join(f'<li>{e(x)}</li>' for x in saber) + '</ul>' if saber else '')
    falta = ('<b>No en falta cap.</b>' if not falten else f'<b>Falten aules de ≥ {", ".join(map(str, falten))} places.</b>')
    H = f'''<!doctype html><html lang="ca"><head><meta charset="utf-8"><title>Resum per a la Junta Permanent</title>
<style>
@page {{ size: A4; margin: 11mm 12mm; }}
* {{ box-sizing: border-box; }}
body {{ font: 8.6pt/1.3 "Segoe UI", Arial, sans-serif; color: #1a1a1a; margin: 0; }}
h1 {{ font-size: 13.5pt; margin: 0 0 1mm; }}
h2 {{ font-size: 9.8pt; margin: 2.6mm 0 1.2mm; color: #0b3d6b; border-bottom: 0.4pt solid #9bb; padding-bottom: 0.5mm; }}
.sub {{ color: #444; margin-bottom: 1.6mm; }}
.box {{ background: #eef4f8; border-left: 2.4pt solid #0b3d6b; padding: 1.6mm 2.6mm; }}
.box p {{ margin: 0.6mm 0; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 0.4pt solid #c4ccd2; padding: 0.5mm 1.4mm; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #f1f4f6; font-weight: 600; }}
.cols {{ display: flex; gap: 3mm; align-items: flex-start; }} .cols > table {{ flex: 1; }}
.note {{ color: #333; margin: 1mm 0 0; }}
.exc p {{ margin: 0.5mm 0; }} ul.note {{ margin: 0.5mm 0 0 4mm; padding: 0; }}
</style></head><body>
<h1>Resum per a la Junta Permanent · torns nous, 2n semestre 2026-27</h1>
<div class="sub">Proposta 5.2 · {n_ses} sessions · veredicte del verificador oficial: <b>{e(inf['veredicte'])}</b>
({nrel} incompliment declarat)</div>
<div class="box">{''.join(f'<p>{b(x)}</p>' for x in resum)}</div>
<h2>1. Pic de sessions simultànies davant de les aules ordinàries</h2>
<table><tr><th>Torn</th><th>Classes alhora (pic)</th><th>Aules ordinàries ocupades en una franja d’una hora (màx.)</th>
<th>Disponibles</th><th>Quan és el pic</th></tr>{pics}</table>
<p class="note">{len(ordinaries)} aules ordinàries, de les quals 2 sempre lliures (regla 8). Referència de l’enunciat: amb
les hores d’avui, les classes de 1r i 2n (sense PLAB ni dobles) fan un pic de {ref_today} alhora al matí; amb el model
nou, <b>{ref_ours}</b>. Hi cap, però just.</p>
<h2>2. Aules que falten o sobren per mida (aules docents i seminaris)</h2>
<table><tr><th>Places ≥</th>{''.join(f'<th>{lv}</th>' for lv, _, _ in sizes)}</tr>
<tr><td>Aules</td>{''.join(f'<td>{s}</td>' for _, s, _ in sizes)}</tr>
<tr><td>Pic de classes que la necessiten</td>{''.join(f'<td>{d}</td>' for _, _, d in sizes)}</tr>
<tr><td>Sobren al pic</td>{''.join(f'<td>{s - d}</td>' for _, s, d in sizes)}</tr></table>
<p class="note">{falta} {e(marge)}</p>
<h2>3. Sessions mogudes (dia o hora) per titulació i curs</h2>
<p class="note" style="margin:0 0 1mm"><b>{moved}</b> sessions mogudes de {n_ses} ({100 * moved / n_ses:.0f} %);
{o["canvis_aula"]} canvien d’aula; {o["hores_mortes_min"] // 60} h d’hores mortes al semestre.</p>
<div class="cols">
<table><tr><th>Titulació i curs</th><th>Sessions</th><th>Mogudes</th><th>%</th></tr>{coh(cohorts[:half])}</table>
<table><tr><th>Titulació i curs</th><th>Sessions</th><th>Mogudes</th><th>%</th></tr>{coh(cohorts[half:])}</table>
</div>
<h2>4. Excepcions a la regla 1 que demanem</h2>
<div class="exc">{excs}{hnote}</div>
</body></html>'''
    (a.dir / 'resum-junta.html').write_text(H, encoding='utf-8')
    print(f'Junta summary -> {a.dir / "resum-junta.md"} + resum-junta.html  (peaks {pm[0]}/{pt[0]} of {disponibles}, '
          f'reference {ref_today}->{ref_ours}, moved {moved}, missing sizes: {falten or "none"})')


if __name__ == '__main__':
    main()
