from pathlib import Path

html_path = Path("index.html")
js_path = Path("app.js")

html = html_path.read_text()
js = js_path.read_text()

# 1. Eliminar l'iframe de l'HTML
html = html.replace(
    '    <iframe id="external-view" title="Vista seleccionada"></iframe>\n',
    ''
)

# 2. Eliminar els estils de l'iframe
iframe_css = """  #external-view {
    display: none;
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
    background: var(--bg);
    z-index: 1;
  }

"""
html = html.replace(iframe_css, '')

# 3. Substituir la lògica de selecció de vista a app.js
start = js.find('// ---------- main view selector ----------')
end = js.find('// ---------- scene ----------', start)

if start == -1 or end == -1:
    raise SystemExit("No he trobat el bloc de selecció de vista a app.js")

new_selector = """// ---------- main view selector ----------
// Cada opció obre una pàgina independent del navegador.
document.querySelectorAll('[data-view]').forEach((button) => {
  button.addEventListener('click', () => {
    const mode = button.dataset.view;

    if (mode === 'hologram') {
      window.location.href = './index.html';
    } else if (mode === 'home') {
      window.location.href = '../home/home.html';
    } else if (mode === 'graella') {
      window.location.href = '../graella/graella.html';
    }
  });
});

"""

js = js[:start] + new_selector + js[end:]

html_path.write_text(html)
js_path.write_text(js)

print("Canvis aplicats correctament.")
print("Home i Graella ara obren pàgines independents.")
