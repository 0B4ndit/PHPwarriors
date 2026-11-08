import collections, csv
from horaris.model import a_traslladar
viol = list(csv.DictReader(open('solver/out/5.2/violacions.csv', encoding='utf-8')))
ses = {r['id_sessio']: r for r in csv.DictReader(open('paquet/sessions.csv', encoding='utf-8'))}
prop = {r['id_sessio']: r for r in csv.DictReader(open('solver/out/5.2/proposta.csv', encoding='utf-8'))}
c = collections.Counter(); ex = collections.defaultdict(list)
for v in viol:
    if v['regla'] != 'R1-TORN' or v['heretada']:
        continue
    sid = v['sessions']; s = ses[sid]; p = prop[sid]
    oa = s['aula_partida']
    key = (s['fixada'][:12], s['tipus'], s['torn_requerit'],
           'orig=' + ('J' if a_traslladar(oa) else ('buida' if not oa else 'aula')),
           'moved_time=' + str((p['dia'], p['h_ini']) != (s['dia'], s['h_ini'])), 'prop=' + (p['aula'] or '-'))
    c[key[:5]] += 1
    if len(ex[key[:5]]) < 3: ex[key[:5]].append((sid, s['codi'], s['assignatura'][:30], s['titulacions_curs'][:30], s['dia'], s['h_ini'], oa, '->', p['aula'], s['alumnes']))
for k, n in c.most_common(): print(n, k); [print('    ', e) for e in ex[k]]
