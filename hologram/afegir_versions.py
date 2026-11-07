from pathlib import Path

html_path = Path("index.html")
js_path = Path("app.js")

html = html_path.read_text()
js = js_path.read_text()

# Afegir CSS
css = """
  #versions {
    position: absolute;
    top: 12px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 3;
    display: flex;
    gap: 6px;
    padding: 6px;
    background: rgba(7,18,26,.85);
    border: 1px solid var(--line);
    border-radius: 6px;
    backdrop-filter: blur(4px);
  }

  #versions button {
    min-width: 48px;
    padding: 6px 12px;
  }

  #versions button.on {
    background: #0f3a4e;
    border-color: var(--cyan);
    color: #e6f7fb;
  }
"""

if "#versions {" not in html:
    html = html.replace("</style>", css + "\n</style>")

# Afegir selectors HTML
nav = """    <nav id="versions" aria-label="Versió de la base de dades">
      <button data-version="5.1" class="on">5.1</button>
      <button data-version="5.2">5.2</button>
      <button data-version="5.3">5.3</button>
      <button data-version="5.4">5.4</button>
    </nav>
"""

if 'id="versions"' not in html:
    html = html.replace(
        '  <div id="scene">',
        '  <div id="scene">\n' + nav
    )

# Afegir variable i esdeveniments JS
js_code = """
// ---------- database version selector ----------
let window_seleccionat = '5.1';

document.querySelectorAll('[data-version]').forEach((b) => {
  b.addEventListener('click', () => {
    window_seleccionat = b.dataset.version;

    document.querySelectorAll('[data-version]').forEach((btn) => {
      btn.classList.toggle('on', btn === b);
    });

    console.log('Versió seleccionada:', window_seleccionat);
  });
});
"""

if "let window_seleccionat" not in js:
    js = js.replace(
        "const OVER_COLOR = '#ff4fd8'; // \"too many students\"",
        "const OVER_COLOR = '#ff4fd8'; // \"too many students\"\n" + js_code
    )

html_path.write_text(html)
js_path.write_text(js)

print("Modificacions aplicades correctament.")
