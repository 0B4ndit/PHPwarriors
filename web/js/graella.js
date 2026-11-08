// Graella setmanal d'horaris: per assignatura, aula, docent, o aules lliures de cada franja.
// Dades: GET /api/graella/<consulta> (web/server.py -> database/consultes.py).
import { VERSION_VISTA, initVersions, initViews } from '/js/nav.js';

// ---------- constants ----------
const API = '/api/graella';
const DIES = ['Dilluns', 'Dimarts', 'Dimecres', 'Dijous', 'Divendres'];
const START = 8 * 60, END = 21 * 60, SLOT = 30, SLOTS = (END - START) / SLOT;   // 08:00-21:00, 26 franges (com graella.css)
const TIPUS = { TE: 'Teoria', PLAB: 'Pràctiques de lab', PAUL: "Pràctiques d'aula", SEM: 'Seminari' };   // colors: .t-<tipus> a graella.css
const LIMIT_LLISTA = 150;
const ETIQUETA = { assignatura: 'ASSIGNATURA', aula: 'AULA', docent: 'PROFESSOR' };
const TRIA = { assignatura: 'Tria una assignatura a la llista.', aula: 'Tria una aula a la llista.', docent: 'Tria un docent a la llista.' };

// ---------- helpers ----------
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const hhmm = (m) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
const addDays = (iso, n) => { const d = new Date(`${iso}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const ddmm = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const norm = (s) => String(s ?? '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
const tipusBase = (t) => String(t).split('+')[0];
const tipusNom = (t) => TIPUS[tipusBase(t)] || t;
const tipusClass = (t) => (TIPUS[tipusBase(t)] ? `t-${tipusBase(t)}` : 't-other');
const pct = (min) => ((Math.min(Math.max(min, START), END) - START) / (END - START)) * 100;
const div = (cls, text) => { const d = document.createElement('div'); d.className = cls; if (text != null) d.textContent = text; return d; };
function mondayOf(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
}

// ---------- estat ----------
const st = {
  version: 'BASE',
  mode: 'assignatura',
  setmana: null,     // dilluns de la setmana, AAAA-MM-DD
  opcions: null,     // /api/graella/opcions: setmanes, assignatures, aules, docents
  sel: { assignatura: null, grup: '', aula: null, docent: null },
  lliures: { cap: 30, tipus: '', slot: null },
  data: null,        // última resposta de l'API per a la vista actual
  card: null,        // sessió seleccionada a la graella
  req: 0,
};

// ---------- API ----------
async function api(consulta, params = {}) {
  const qs = new URLSearchParams({ vista: VERSION_VISTA[st.version] });
  for (const [k, v] of Object.entries(params)) if (v) qs.set(k, v);
  const url = `${API}/${consulta}?${qs}`;
  $('api-payload').textContent = `GET ${url}`;
  const r = await fetch(url, { cache: 'no-store' });
  const body = await r.json().catch(() => null);
  if (!r.ok || !body?.ok) throw new Error(body?.errors?.[0] || `HTTP ${r.status}`);
  return body;
}

function setStatus(kind, text, title = '') {
  const s = $('status');
  s.className = `pill ${kind}`;
  s.textContent = text;
  s.title = title;
}

// ---------- modes ----------
function setMode(mode) {
  st.mode = mode;
  st.card = null;
  document.querySelectorAll('#mode-selector button').forEach((b) => b.classList.toggle('on', b.dataset.mode === mode));
  document.querySelectorAll('.filter-panel').forEach((p) => { p.hidden = p.id !== `panel-${mode}`; });
  loadView();
}

// Obre una altra vista amb un element triat (des del detall o de les aules lliures)
function goTo(mode, value) {
  st.sel[mode] = value;
  if (mode === 'assignatura') { st.sel.grup = ''; fillGrups(); }
  $(`search-${mode}`).value = value;   // perquè l'element triat es vegi a la llista
  renderLists();
  setMode(mode);
}

// ---------- setmanes ----------
const weeks = () => st.opcions?.setmanes || [];
const weekText = () => {
  const w = weeks().find((x) => x.dilluns === st.setmana);
  return w ? `${w.setmana} (${ddmm(w.dilluns)}–${ddmm(addDays(w.dilluns, 4))})` : '';
};
const diaDe = (data) => DIES[DIES.findIndex((_, i) => addDays(st.setmana, i) === data)];

function fillWeeks() {
  $('sel-setmana').innerHTML = weeks().map((w) =>
    `<option value="${w.dilluns}">${esc(w.setmana)} · ${ddmm(w.dilluns)}–${ddmm(addDays(w.dilluns, 4))} · S${w.sem} · ${w.n} ses.</option>`).join('');
}

function pickWeek(preferred) {
  const ws = weeks().map((w) => w.dilluns);
  if (!ws.length) return null;
  if (ws.includes(preferred)) return preferred;
  return ws.find((d) => d >= preferred) || ws[ws.length - 1];
}

function setWeek(dilluns) {
  st.setmana = dilluns;
  $('sel-setmana').value = dilluns || '';
  const i = weeks().findIndex((w) => w.dilluns === dilluns);
  $('w-prev').disabled = i <= 0;
  $('w-next').disabled = i < 0 || i >= weeks().length - 1;
  st.lliures.slot = null;
  st.card = null;
}

function stepWeek(d) {
  const ws = weeks();
  const i = ws.findIndex((w) => w.dilluns === st.setmana);
  if (ws[i + d]) { setWeek(ws[i + d].dilluns); loadView(); }
}

// Si l'element triat no té classes la setmana actual, salta a la setmana més propera que en tingui
function jumpToWeekWith(setmanes) {
  if (!setmanes?.length || setmanes.includes(st.setmana)) return;
  setWeek(setmanes.find((d) => d >= st.setmana) || setmanes[setmanes.length - 1]);
}

// ---------- llistes de selecció ----------
const LLISTES = {
  assignatura: {
    items: () => st.opcions?.assignatures || [],
    key: (a) => a.codi,
    text: (a) => `${a.assignatura} ${a.codi} ${a.titulacions.join(' ')}`,
    row: (a) => `<div><strong>${esc(a.assignatura)}</strong><br><span class="sub">${esc(a.codi)} · ${esc(a.titulacions.join(', ') || '—')} · S${a.sems.join('+')}</span></div>
                 <span class="pill">${a.grups.length} gr.</span>`,
    pick: (a) => { st.sel.grup = ''; fillGrups(); jumpToWeekWith(a.setmanes); },
  },
  aula: {
    items: () => st.opcions?.aules || [],
    key: (a) => a.aula,
    text: (a) => `${a.aula} ${a.tipus || ''} ${a.descripcio || ''}`,
    row: (a) => `<div><strong>${esc(a.aula)}</strong><br><span class="sub">${esc(a.cataleg ? `${a.tipus} · ${a.descripcio}` : 'fora del catàleg (altres edificis)')}</span></div>
                 <span class="pill ${a.cataleg ? 'ok' : ''}">${a.capacitat ?? '?'} pl.</span>`,
    pick: () => {},
  },
  docent: {
    items: () => st.opcions?.docents || [],
    key: (d) => d.docent,
    text: (d) => `${d.docent} ${d.assignatures.join(' ')}`,
    row: (d) => `<div><strong>${esc(d.docent)}</strong><br><span class="sub">${esc(d.assignatures.join(', '))}${d.n_assignatures > d.assignatures.length ? '…' : ''}</span></div>
                 <span class="pill">${d.n_assignatures} assig.</span>`,
    pick: (d) => jumpToWeekWith(d.setmanes),
  },
};
const selectedItem = (mode) => LLISTES[mode]?.items().find((x) => LLISTES[mode].key(x) === st.sel[mode]);

function renderList(mode) {
  const L = LLISTES[mode];
  const q = norm($(`search-${mode}`).value).trim();
  const all = L.items().filter((it) => !q || norm(L.text(it)).includes(q));
  const shown = all.slice(0, LIMIT_LLISTA);
  $(`list-${mode}`).innerHTML = shown.map((it) =>
    `<li class="item-row ${L.key(it) === st.sel[mode] ? 'sel' : ''}" data-key="${esc(L.key(it))}">${L.row(it)}</li>`).join('')
    + (all.length > shown.length ? `<li class="item-row more">… ${all.length - shown.length} més: afina la cerca</li>` : '')
    + (all.length ? '' : '<li class="item-row more">Cap resultat</li>');
}
const renderLists = () => Object.keys(LLISTES).forEach(renderList);

function fillGrups() {
  const a = selectedItem('assignatura');
  $('select-grup').innerHTML = '<option value="">Tots els grups</option>'
    + (a ? a.grups.map((g) => `<option value="${esc(g)}">${esc(g)}</option>`).join('') : '');
  if (a && !a.grups.includes(st.sel.grup)) st.sel.grup = '';
  $('select-grup').value = st.sel.grup;
}

// ---------- càrrega ----------
async function loadOpcions() {
  setStatus('warn', 'carregant…');
  try {
    st.opcions = await api('opcions');
  } catch (e) {
    st.opcions = null;
    setStatus('bad', 'error', e.message);
    showEmpty(`No s'han pogut carregar les dades: ${e.message}`);
    return;
  }
  fillWeeks();
  setWeek(pickWeek(st.setmana || mondayOf(new Date())));
  // les seleccions que no existeixen en aquesta versió es treuen
  for (const mode of Object.keys(LLISTES)) if (st.sel[mode] && !selectedItem(mode)) st.sel[mode] = null;
  fillGrups();
  const tipus = [...new Set(st.opcions.aules.filter((a) => a.cataleg).map((a) => a.tipus))].sort();
  $('lliures-tipus').innerHTML = '<option value="">Totes</option>' + tipus.map((t) => `<option>${esc(t)}</option>`).join('');
  $('lliures-tipus').value = tipus.includes(st.lliures.tipus) ? st.lliures.tipus : '';
  st.lliures.tipus = $('lliures-tipus').value;
  renderLists();
  setStatus('ok', `live · DuckDB · ${st.version}`, `vista ${VERSION_VISTA[st.version]}`);
  await loadView();
}

// La consulta de la vista actual: [nom, paràmetres] o null si encara no s'ha triat res
function currentQuery() {
  const { mode, sel } = st;
  if (mode === 'lliures') return ['lliures', {}];
  if (!sel[mode]) return null;
  if (mode === 'assignatura') return ['assignatura', { codi: sel.assignatura, grup: sel.grup }];
  return [mode, { [mode]: sel[mode] }];
}

async function loadView() {
  const req = ++st.req;
  const q = currentQuery();
  if (!q || !st.setmana) { st.data = null; render(); return; }
  try {
    const data = await api(q[0], { setmana: st.setmana, ...q[1] });
    if (req !== st.req) return;          // s'ha demanat una altra cosa mentrestant
    st.data = data;
    render();
  } catch (e) {
    if (req !== st.req) return;
    st.data = null;
    render();
    showEmpty(`Error a la consulta: ${e.message}`);
  }
}

// ---------- graella ----------
// Capçaleres, hores i una columna per dia (amb els festius i aturades). Retorna les columnes.
function buildGrid(cal) {
  const grid = $('horari');
  grid.replaceChildren();
  const corner = div('header-dia');
  corner.style.gridColumn = '1';
  grid.append(corner);

  const cols = DIES.map((dia, i) => {
    const data = st.setmana ? addDays(st.setmana, i) : null;
    const dies = (cal || []).filter((c) => c.data === data);
    const h = div('header-dia');
    h.style.gridColumn = i + 2;
    h.innerHTML = `${dia}<small>${data ? ddmm(data) : ''}</small>`
      + dies.slice(0, 1).map((c) => `<small class="cal" title="${esc(c.motiu)}">${esc(c.tipus)}: ${esc(c.motiu)}</small>`).join('');

    const col = div('day-col');
    col.style.gridColumn = i + 2;
    for (const c of dies) {
      if (c.tipus === 'avaluacio') continue;
      const ini = c.ini ?? START, fi = c.fi ?? END;
      const o = div('closed', `${c.tipus.replace('_', ' ')} · ${c.motiu}`);
      o.style.top = `${pct(ini)}%`;
      o.style.height = `${pct(fi) - pct(ini)}%`;
      col.append(o);
    }
    grid.append(h, col);
    return col;
  });

  for (let i = 0; i < SLOTS; i++) {
    const label = div('hora-label', i % 2 === 0 ? hhmm(START + i * SLOT) : null);
    label.style.gridRow = i + 2;
    grid.append(label);
  }
  return cols;
}

// Posa en carrils les sessions que es solapen el mateix dia (_lane, _lanes)
function lanes(sessions) {
  const sorted = [...sessions].sort((a, b) => a.ini - b.ini || b.fi - a.fi);
  let cluster = [], clusterEnd = -1;
  const flush = () => {
    const ends = [];
    for (const s of cluster) {
      let l = ends.findIndex((e) => e <= s.ini);
      if (l < 0) l = ends.push(0) - 1;
      ends[l] = s.fi;
      s._lane = l;
    }
    for (const s of cluster) s._lanes = ends.length;
    cluster = [];
  };
  for (const s of sorted) {
    if (cluster.length && s.ini >= clusterEnd) flush();
    cluster.push(s);
    clusterEnd = Math.max(clusterEnd, s.fi);
  }
  flush();
  return sorted;
}

const capacitatAula = (aula) => st.opcions?.aules.find((a) => a.aula === aula)?.capacitat ?? null;

// Les tres línies de la targeta: depenen del que ja diu el títol de la vista
function cardText(s) {
  const grups = s.grups.join(', ');
  const docents = s.docents.length ? s.docents.join(', ') : 'sense docent';
  const aula = s.aula ? s.aula + (s.aules_extra.length ? ` + ${s.aules_extra.join(', ')}` : '') : 'sense aula';
  if (st.mode === 'assignatura') return [`${s.tipus} · ${grups}`, docents, aula];
  if (st.mode === 'aula') return [s.assignatura, `${s.tipus} · ${grups}`, `${docents} · ${s.alumnes} al.`];
  return [s.assignatura, `${s.tipus} · ${grups}`, aula];
}

const sameCard = (a, b) => a && b && a.id === b.id && a.data === b.data && a.ini === b.ini;

function render() {
  removeEmpty();
  $('d-tag').textContent = st.version;
  if (st.mode === 'lliures') return renderLliures();

  const d = st.data;
  const cols = buildGrid(d?.calendari);
  renderLegend();
  const sessions = d?.sessions || [];
  const cap = st.mode === 'aula' ? (d?.aula?.capacitat ?? capacitatAula(st.sel.aula)) : null;

  DIES.forEach((_, i) => {
    const data = addDays(st.setmana || '2000-01-03', i);
    for (const s of lanes(sessions.filter((x) => x.data === data))) {
      const [titol, info, peu] = cardText(s);
      const card = div(`classe-card ${tipusClass(s.tipus)}`);
      card.classList.toggle('over', cap != null && s.alumnes > cap);
      card.classList.toggle('sel', sameCard(st.card, s));
      Object.assign(card.style, {
        top: `calc(${pct(s.ini)}% + 1px)`,
        height: `calc(${pct(s.fi) - pct(s.ini)}% - 2px)`,
        left: `calc(${(s._lane / s._lanes) * 100}% + 2px)`,
        width: `calc(${100 / s._lanes}% - 4px)`,
      });
      card.title = `${s.assignatura}\n${hhmm(s.ini)}-${hhmm(s.fi)} · ${s.tipus} · ${s.grups.join(', ')}\n${info}\n${peu}`;
      card.append(div('classe-titol', titol), div('classe-info', info), div('classe-info bottom', peu));
      card.addEventListener('click', () => { st.card = s; render(); });
      cols[i].append(card);
    }
  });

  // títol, comptadors i detall
  const nom = {
    assignatura: () => { const a = selectedItem('assignatura'); return a ? `${a.assignatura} · ${a.codi}${st.sel.grup ? ` · ${st.sel.grup}` : ''}` : null; },
    aula: () => (st.sel.aula ? `${st.sel.aula}${cap != null ? ` · ${cap} places` : ''}` : null),
    docent: () => st.sel.docent,
  }[st.mode]();
  $('grid-title').textContent = `${ETIQUETA[st.mode]} · ${nom || '—'} · ${weekText()}`;
  $('counts').textContent = nom ? `${sessions.length} sessions` : '';

  if (!nom) showEmpty(TRIA[st.mode]);
  else if (d && !sessions.length) {
    const altres = (st.mode === 'aula' ? null : selectedItem(st.mode))?.setmanes?.filter((x) => x !== st.setmana) || [];
    showEmpty(`Cap sessió aquesta setmana${st.version !== 'BASE' ? ` a la versió ${st.version}` : ''}.`,
      altres.length ? ['Anar a la setmana amb classes més propera', () => { jumpToWeekWith(altres); loadView(); }] : null);
  }
  renderDetail(nom, sessions);
}

// ---------- aules lliures ----------
// Aules del catàleg que passen el filtre, i una funció que diu quines estan lliures en una franja
function lliuresDe(d) {
  const aules = d.aules.filter((a) => (a.capacitat ?? 0) >= st.lliures.cap && (!st.lliures.tipus || a.tipus === st.lliures.tipus));
  const ocupades = new Map();
  for (const o of d.ocupades) {
    const k = `${o.aula}|${o.data}`;
    if (!ocupades.has(k)) ocupades.set(k, []);
    ocupades.get(k).push(o);
  }
  const lliures = (data, ini) => aules.filter((a) => !(ocupades.get(`${a.aula}|${data}`) || []).some((o) => o.ini < ini + SLOT && o.fi > ini));
  return { aules, lliures };
}

function renderLliures() {
  const d = st.data;
  const cols = buildGrid(d?.calendari);
  renderLegend();
  $('grid-title').textContent = `AULES LLIURES · ${weekText()}`;
  if (!d) { $('counts').textContent = ''; renderDetail(null, []); return; }

  const { aules, lliures } = lliuresDe(d);
  $('counts').textContent = `${aules.length} aules al filtre`;
  $('lliures-hint').textContent = `${aules.length} aules compleixen el filtre. Cada franja mostra quantes estan lliures; clica-la per veure quines.`;

  const slot = st.lliures.slot;
  DIES.forEach((dia, i) => {
    const data = addDays(st.setmana, i);
    if (d.calendari.some((c) => c.data === data && c.ini == null && c.tipus !== 'avaluacio')) return;   // dia tancat
    for (let s = 0; s < SLOTS; s++) {
      const ini = START + s * SLOT;
      const n = lliures(data, ini).length;
      const cell = div(`slot-cell${n === 0 ? ' none' : ''}`, n);
      cell.classList.toggle('sel', slot?.data === data && slot?.ini === ini);
      cell.style.top = `calc(${pct(ini)}% + 1px)`;
      cell.style.setProperty('--f', aules.length ? (n / aules.length).toFixed(3) : 0);
      cell.title = `${dia} ${ddmm(data)} ${hhmm(ini)}-${hhmm(ini + SLOT)}: ${n} de ${aules.length} aules lliures`;
      cell.addEventListener('click', () => { st.lliures.slot = { data, ini }; renderLliures(); });
      cols[i].append(cell);
    }
  });

  // aules lliures de la franja triada
  const res = $('results-lliures');
  if (!slot) {
    res.innerHTML = '<li class="item-row more">Clica una franja de la graella</li>';
    renderDetail(null, []);
    return;
  }
  const free = lliures(slot.data, slot.ini).sort((a, b) => a.capacitat - b.capacitat || a.aula.localeCompare(b.aula));
  res.innerHTML = free.map((a) => `<li class="item-row" data-aula="${esc(a.aula)}" title="Veure l'horari de l'aula">
      <div><span class="pill ok">${esc(a.aula)}</span><br><span class="sub">${esc(a.tipus)}</span></div>
      <span class="sub">${a.capacitat} pl.</span></li>`).join('') || '<li class="item-row more">Cap aula lliure</li>';
  renderDetail(`${diaDe(slot.data)} ${ddmm(slot.data)} · ${hhmm(slot.ini)}-${hhmm(slot.ini + SLOT)}`, [], free.length, aules.length);
}

function renderLegend() {
  const item = (cls, text) => `<span><i class="${cls}"></i>${text}</span>`;
  const closed = item('sw-closed', 'festiu / aturada');
  $('legend').innerHTML = st.mode === 'lliures'
    ? item('sw-free-all', 'totes lliures') + item('sw-free-few', 'poques lliures') + closed
    : Object.entries(TIPUS).map(([k, nom]) => item(`t-${k}`, `${k} · ${nom}`)).join('')
      + (st.mode === 'aula' ? item('sw-over', 'més alumnes que places') : '') + closed;
}

function showEmpty(text, action) {
  removeEmpty();
  const box = div('empty-msg', text);
  box.id = 'empty-msg';
  if (action) {
    const b = document.createElement('button');
    b.textContent = action[0];
    b.addEventListener('click', action[1]);
    box.append(b);
  }
  document.querySelector('main').append(box);
}
const removeEmpty = () => $('empty-msg')?.remove();

// ---------- detall ----------
const row = (label, html) => `<div class="d-row"><span>${esc(label)}</span><b>${html}</b></div>`;
const links = (mode, values) => values.map((v) => `<span class="link" data-go="${mode}" data-val="${esc(v)}">${esc(v)}</span>`).join(', ');

function renderDetail(nom, sessions, nLliures, nAules) {
  const s = st.card;
  let title, html = '';
  if (s) {
    const cap = s.aula ? capacitatAula(s.aula) : null;
    title = 'SESSIÓ';
    html += row('Assignatura', `${links('assignatura', s.codis)} · ${esc(s.assignatura)}`);
    html += row('Grups', esc(s.grups.join(', ')));
    html += row('Tipus', esc(`${s.tipus} · ${tipusNom(s.tipus)}`));
    html += row('Quan', esc(`${diaDe(s.data) || s.dia} ${ddmm(s.data)} · ${hhmm(s.ini)}-${hhmm(s.fi)}`));
    html += row('Aula', s.aula ? links('aula', [s.aula, ...s.aules_extra]) : '<span class="txt-warn">sense aula</span>');
    html += row('Alumnes', esc(`${s.alumnes}${cap != null ? ` / ${cap} places` : ''}`)
      + (cap != null && s.alumnes > cap ? ' <span class="txt-bad">· massa alumnes</span>' : ''));
    html += row('Docents', s.docents.length ? links('docent', s.docents) : '—');
    html += row('Titulacions', esc(s.titulacions.join(', ') || '—'));
  } else if (st.mode === 'lliures') {
    title = 'AULES LLIURES';
    html += row('Filtre', esc(`≥ ${st.lliures.cap} places · ${st.lliures.tipus || 'tots els tipus'}`));
    html += row('Franja', esc(nom || 'cap (clica la graella)'));
    if (nLliures != null) html += row('Lliures', esc(`${nLliures} de ${nAules}`));
  } else {
    title = 'DETALLS';
    const hores = sessions.reduce((t, x) => t + (x.fi - x.ini), 0) / 60;
    const sense = sessions.filter((x) => !x.aula).length;
    html += row('Consulta', esc({ assignatura: 'Assignatura', aula: 'Aula', docent: 'Professor' }[st.mode]));
    html += row('Element', esc(nom || '—'));
    if (nom) {
      html += row('Sessions', esc(`${sessions.length} · ${hores.toFixed(1)} h`));
      if (st.mode !== 'aula') html += row('Sense aula', sense ? `<span class="txt-warn">${sense}</span>` : '0');
    }
    html += '<div class="hint">Clica una sessió per veure-la en detall.</div>';
  }
  $('d-title').textContent = title;
  $('d-rows').innerHTML = html;
}

// ---------- exportar el que es veu a CSV ----------
function exportCsv() {
  if (!st.data) return;
  let rows;
  if (st.mode === 'lliures') {
    const { lliures } = lliuresDe(st.data);
    rows = [['data', 'inici', 'fi', 'n_lliures', 'aules_lliures']];
    DIES.forEach((_, i) => {
      const data = addDays(st.setmana, i);
      for (let s = 0; s < SLOTS; s++) {
        const ini = START + s * SLOT;
        const ll = lliures(data, ini);
        rows.push([data, hhmm(ini), hhmm(ini + SLOT), ll.length, ll.map((a) => a.aula).join(' ')]);
      }
    });
  } else {
    rows = [['data', 'dia', 'inici', 'fi', 'codis', 'assignatura', 'tipus', 'grups', 'docents', 'aula', 'aules_extra', 'alumnes']];
    for (const s of st.data.sessions) {
      rows.push([s.data, s.dia, hhmm(s.ini), hhmm(s.fi), s.codis.join(' '), s.assignatura, s.tipus, s.grups.join(' '),
        s.docents.join(' '), s.aula, s.aules_extra.join(' '), s.alumnes]);
    }
  }
  const q = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const csv = '﻿' + rows.map((r) => r.map(q).join(',')).join('\n');   // BOM: l'Excel llegeix bé els accents
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  a.download = `graella_${st.mode}_${(st.sel[st.mode] || 'lliures').replace(/[^\w-]+/g, '-')}_${st.setmana}_${st.version}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function reset() {
  if (st.mode === 'lliures') st.lliures.slot = null;
  else {
    st.sel[st.mode] = null;
    if (st.mode === 'assignatura') { st.sel.grup = ''; fillGrups(); }
    renderList(st.mode);
  }
  st.card = null;
  loadView();
}

// ---------- dades en directe: quan la BD canvia, el servidor avisa i es recarrega ----------
let dbVersion = null;
function connect() {
  const es = new EventSource('/api/events');
  es.addEventListener('status', (e) => {
    const s = JSON.parse(e.data);
    if (s.error) setStatus('warn', 'DuckDB · últimes dades bones', s.error);
    if (dbVersion !== null && s.version !== dbVersion) loadOpcions();
    dbVersion = s.version;
  });
  es.onerror = () => setStatus('bad', 'servidor no disponible · reintentant');
}

// ---------- esdeveniments ----------
st.version = initVersions((v) => { st.version = v; loadOpcions(); });
initViews('graella');

document.querySelectorAll('#mode-selector button').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.mode)));
$('sel-setmana').addEventListener('change', (e) => { setWeek(e.target.value); loadView(); });
$('w-prev').addEventListener('click', () => stepWeek(-1));
$('w-next').addEventListener('click', () => stepWeek(1));

for (const mode of Object.keys(LLISTES)) {
  $(`search-${mode}`).addEventListener('input', () => renderList(mode));
  $(`list-${mode}`).addEventListener('click', (e) => {
    const key = e.target.closest('.item-row[data-key]')?.dataset.key;
    const it = LLISTES[mode].items().find((x) => LLISTES[mode].key(x) === key);
    if (!it) return;
    st.sel[mode] = key;
    LLISTES[mode].pick(it);
    renderList(mode);
    st.card = null;
    loadView();
  });
}

$('select-grup').addEventListener('change', (e) => { st.sel.grup = e.target.value; loadView(); });
$('lliures-cap').addEventListener('input', (e) => { st.lliures.cap = Number(e.target.value) || 0; st.lliures.slot = null; render(); });
$('lliures-tipus').addEventListener('change', (e) => { st.lliures.tipus = e.target.value; st.lliures.slot = null; render(); });
$('results-lliures').addEventListener('click', (e) => {
  const row = e.target.closest('[data-aula]');
  if (row) goTo('aula', row.dataset.aula);
});
$('d-rows').addEventListener('click', (e) => {
  const l = e.target.closest('[data-go]');
  if (l) goTo(l.dataset.go, l.dataset.val);
});
$('btn-reset').addEventListener('click', reset);
$('btn-export').addEventListener('click', exportCsv);

// ---------- inici ----------
buildGrid([]);
loadOpcions();
connect();
