// Barres compartides pel holograma i la graella:
//   <nav id="versions" class="toolbar">  versió de la BD: cada botó llegeix una vista de sessions (database/consultes.VISTES)
//   <nav id="views" class="toolbar">     enllaços a les altres pàgines
// La versió triada es recorda al navegador i és la mateixa a totes les pàgines.

export const VERSION_VISTA = { BASE: 'sessions', '5.1': 'sessions51', '5.2': 'sessions52', '5.3': 'sessions53', '5.4': 'sessions54' };
const VERSION_KEY = 'hologram.version';

const PAGES = {
  hologram: ['3D', '/'],
  home: ['Home', '/home/home.html'],
  graella: ['Graella', '/graella/graella.html'],
};

function savedVersion() {
  try {
    const v = localStorage.getItem(VERSION_KEY);
    if (v in VERSION_VISTA) return v;
  } catch { /* sense emmagatzematge */ }
  return 'BASE';
}

// Omple #versions i crida onChange(versió) quan se'n tria una altra. Retorna la versió inicial.
export function initVersions(onChange) {
  const nav = document.getElementById('versions');
  let current = savedVersion();
  const mark = () => nav.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.version === current));

  nav.replaceChildren(...Object.keys(VERSION_VISTA).map((v) => {
    const b = document.createElement('button');
    b.dataset.version = v;
    b.textContent = v;
    b.title = `vista ${VERSION_VISTA[v]}`;
    return b;
  }));
  nav.addEventListener('click', (e) => {
    const b = e.target.closest('[data-version]');
    if (!b || b.dataset.version === current) return;
    current = b.dataset.version;
    try { localStorage.setItem(VERSION_KEY, current); } catch { /* no es recorda */ }
    mark();
    onChange(current);
  });
  mark();
  return current;
}

// Omple #views amb els enllaços a les pàgines; `page` és la pàgina actual.
export function initViews(page) {
  document.getElementById('views').replaceChildren(...Object.entries(PAGES).map(([id, [label, href]]) => {
    const a = document.createElement('a');
    a.href = href;
    a.textContent = label;
    if (id === page) { a.className = 'on'; a.setAttribute('aria-current', 'page'); }
    return a;
  }));
}
