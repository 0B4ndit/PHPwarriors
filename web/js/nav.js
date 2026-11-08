// Notch flotant compartit per totes les pàgines (holograma, graella i portada). Estils: css/notch.css.
//   · pàgines: Inici, Mapa 3D, Graella (enllaços; la pàgina actual queda marcada)
//   · versió de les dades: un botó que obre un menú amb l'horari real (BASE) i les propostes 5.1-5.4;
//     cada versió llegeix una vista de sessions (database/consultes.VISTES)
// La versió triada es recorda al navegador i és la mateixa a totes les pàgines.
// Escriptori: càpsula fixa a dalt al centre. Mòbil (≤700px): barra fixa a baix.

export const VERSION_VISTA = { BASE: 'sessions', '5.1': 'sessions51', '5.2': 'sessions52', '5.3': 'sessions53', '5.4': 'sessions54' };
const VERSION_KEY = 'hologram.version';

// nom i descripció de cada versió (el que veu l'usuari al menú)
const VERSION_INFO = {
  BASE: ['Horari actual', "L'horari d'avui, tal com és"],
  '5.1': ['Només aules', 'Mateixes hores, aules reassignades'],
  '5.2': ['Torns nous', 'Horari amb els torns nous'],
  '5.3': ['Imprevistos', 'Avaries i reserves, sobre el 5.2'],
  '5.4': ['Grau nou', 'Un grau nou, sobre el 5.2'],
};

const svg = (paths, size = 16) =>
  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
const ICON = {
  home: svg('<path d="M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z"/>'),
  cube: svg('<path d="M12 2 3 7v10l9 5 9-5V7z"/><path d="M3 7l9 5 9-5"/><path d="M12 12v10"/>'),
  grid: svg('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>'),
  layers: svg('<path d="M12 3 2 8l10 5 10-5z"/><path d="M2 13l10 5 10-5"/>'),
  chevron: svg('<path d="M6 9l6 6 6-6"/>', 14),
  check: svg('<path d="M5 12l5 5 9-10"/>'),
};

// id: [nom llarg, nom curt (mòbil), adreça, icona]
const PAGES = {
  home: ['Inici', 'Inici', '/home.html', ICON.home],
  hologram: ['Mapa 3D', '3D', '/', ICON.cube],
  graella: ['Graella', 'Graella', '/graella.html', ICON.grid],
};

function savedVersion() {
  try {
    const v = localStorage.getItem(VERSION_KEY);
    if (v in VERSION_VISTA) return v;
  } catch { /* sense emmagatzematge */ }
  return 'BASE';
}

const el = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
};

// Crea el notch un sol cop (initViews i initVersions el comparteixen).
let notch = null;
function getNotch() {
  if (notch) return notch;
  const root = el('div');
  root.id = 'notch';
  const bar = el('nav', 'nt-bar');
  bar.setAttribute('aria-label', 'Navegació principal');
  const tabs = el('div', 'nt-tabs');
  const chip = el('button', 'nt-chip',
    `${ICON.layers}<span class="nt-chip-text"><small>DADES</small><b class="nt-name"></b></span>` +
    `<span class="nt-code"></span>${ICON.chevron.replace('<svg', '<svg class="nt-chev"')}<span class="nt-s">Dades</span>`);
  chip.type = 'button';
  chip.setAttribute('aria-haspopup', 'menu');
  chip.setAttribute('aria-expanded', 'false');
  chip.setAttribute('aria-controls', 'nt-menu');
  chip.hidden = true; // es mostra quan initVersions l'activa
  bar.append(el('span', 'nt-brand', '<i></i>UAB·Q'), tabs, el('span', 'nt-sep'), chip);
  const menu = el('div', 'nt-menu');
  menu.id = 'nt-menu';
  menu.setAttribute('role', 'menu');
  menu.setAttribute('aria-label', 'Versió de les dades');
  menu.hidden = true;
  root.append(bar, menu);
  document.body.append(root);
  notch = { root, tabs, chip, menu };
  return notch;
}

// Omple les pestanyes de pàgina; `page` és la pàgina actual (hologram | graella | home).
export function initViews(page) {
  const { tabs } = getNotch();
  tabs.replaceChildren(...Object.entries(PAGES).map(([id, [label, short, href, icon]]) => {
    const a = el('a', 'nt-tab', `${icon}<span class="nt-l">${label}</span><span class="nt-s">${short}</span>`);
    a.href = href;
    a.title = label;
    a.setAttribute('aria-label', label);
    if (id === page) a.setAttribute('aria-current', 'page');
    return a;
  }));
}

// Activa el selector de versió i crida onChange(versió) quan se'n tria una altra. Retorna la versió inicial.
export function initVersions(onChange) {
  const { root, chip, menu } = getNotch();
  let current = savedVersion();

  const item = (v) => {
    const [name, desc] = VERSION_INFO[v];
    const b = el('button', 'nt-item',
      `<span class="nt-code">${v}</span><span class="nt-item-text"><b>${name}</b><span>${desc}</span></span>` +
      `<span class="nt-check">${ICON.check}</span>`);
    b.type = 'button';
    b.dataset.version = v;
    b.title = `vista ${VERSION_VISTA[v]}`;
    b.setAttribute('role', 'menuitemradio');
    return b;
  };
  const versions = Object.keys(VERSION_VISTA);
  menu.replaceChildren(
    el('span', 'nt-group', 'Horari real'),
    ...versions.filter((v) => v === 'BASE').map(item),
    el('span', 'nt-group', 'Propostes del solver · 2n semestre'),
    ...versions.filter((v) => v !== 'BASE').map(item),
    el('span', 'nt-foot', 'La versió triada es manté a totes les pàgines.'),
  );
  const items = () => [...menu.querySelectorAll('[data-version]')];

  const mark = () => {
    const [name] = VERSION_INFO[current];
    chip.querySelector('.nt-name').textContent = name;
    chip.querySelector('.nt-code').textContent = current;
    chip.setAttribute('aria-label', `Versió de les dades: ${current} · ${name}`);
    items().forEach((b) => b.setAttribute('aria-checked', String(b.dataset.version === current)));
  };
  const setOpen = (open, focusChip = false) => {
    menu.hidden = !open;
    chip.setAttribute('aria-expanded', String(open));
    if (open) (menu.querySelector('[aria-checked="true"]') || items()[0]).focus();
    else if (focusChip) chip.focus();
  };

  chip.addEventListener('click', () => setOpen(menu.hidden));
  menu.addEventListener('click', (e) => {
    const b = e.target.closest('[data-version]');
    if (!b) return;
    setOpen(false, true);
    if (b.dataset.version === current) return;
    current = b.dataset.version;
    try { localStorage.setItem(VERSION_KEY, current); } catch { /* no es recorda */ }
    mark();
    onChange(current);
  });
  // teclat dins del notch: Esc tanca, fletxes es mouen pel menú
  root.addEventListener('keydown', (e) => {
    if (menu.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); setOpen(false, true); return; }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const list = items();
    const i = list.indexOf(document.activeElement);
    list[(i + (e.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length].focus();
  });
  // un clic fora del notch tanca el menú
  document.addEventListener('pointerdown', (e) => { if (!menu.hidden && !root.contains(e.target)) setOpen(false); });

  chip.hidden = false;
  mark();
  return current;
}
