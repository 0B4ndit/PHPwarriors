from pathlib import Path

html_path = Path("index.html")
js_path = Path("app.js")

html = html_path.read_text()
js = js_path.read_text()

# ---------- CSS del segon selector i de l'iframe ----------
css = """
  #views {
    position: absolute;
    top: 12px;
    left: calc(50% + 125px);
    z-index: 4;
    display: flex;
    gap: 6px;
    padding: 6px;
    background: rgba(7,18,26,.85);
    border: 1px solid var(--line);
    border-radius: 6px;
    backdrop-filter: blur(4px);
  }

  #views button {
    min-width: 54px;
    padding: 6px 12px;
  }

  #views button.on {
    background: #0f3a4e;
    border-color: var(--cyan);
    color: #e6f7fb;
  }

  #external-view {
    display: none;
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
    background: var(--bg);
    z-index: 1;
  }

  @media (max-width: 900px) {
    #versions {
      top: 12px;
    }

    #views {
      top: 62px;
      left: 50%;
      transform: translateX(-50%);
    }
  }
"""

if "#external-view" not in html:
    html = html.replace("</style>", css + "\n</style>")

# ---------- HTML del selector de vistes ----------
views_html = """
    <nav id="views" aria-label="Vista">
      <button data-view="hologram" class="on">3D</button>
      <button data-view="home">Home</button>
      <button data-view="graella">Graella</button>
    </nav>

    <iframe id="external-view" title="Vista seleccionada"></iframe>
"""

if 'id="views"' not in html:
    marker = '    </nav>\n\n    <nav id="floors"'
    if marker not in html:
        raise SystemExit("No s'ha trobat el selector de plantes a index.html")
    html = html.replace(
        marker,
        '    </nav>\n' + views_html + '\n    <nav id="floors"',
        1
    )

html_path.write_text(html)

# ---------- JavaScript per canviar de vista ----------
js_code = """
// ---------- main view selector ----------
const viewButtons = document.querySelectorAll('[data-view]');
const externalView = document.getElementById('external-view');
const sidePanel = document.querySelector('aside');
const floorSelector = document.getElementById('floors');

function setDisplayMode(mode) {
  viewButtons.forEach((button) => {
    button.classList.toggle('on', button.dataset.view === mode);
  });

  const canvas = document.querySelector('#scene canvas');
  const isHologram = mode === 'hologram';

  if (canvas) canvas.style.display = isHologram ? 'block' : 'none';

  floorSelector.hidden = !isHologram;
  sidePanel.hidden = !isHologram;

  if (isHologram) {
    externalView.style.display = 'none';
  } else {
    externalView.src = mode === 'home'
      ? '/home/home.html'
      : '/graella/graella.html';

    externalView.style.display = 'block';
  }

  console.log('Vista seleccionada:', mode);
}

viewButtons.forEach((button) => {
  button.addEventListener('click', () => {
    setDisplayMode(button.dataset.view);
  });
});
"""

if "function setDisplayMode(mode)" not in js:
    marker = "// ---------- scene ----------"
    if marker not in js:
        raise SystemExit("No s'ha trobat el punt d'inserció a app.js")
    js = js.replace(marker, js_code + "\n" + marker, 1)

js_path.write_text(js)

print("Selectors de vistes afegits correctament.")
