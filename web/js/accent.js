// Color d'accent comú a totes les pàgines (holograma, graella i portada).
// Per defecte és el verd UAB de --cyan a css/comu.css; si al mapa 3D se n'ha triat un altre a la paleta,
// js/hologram.js el desa a localStorage i aquí s'aplica abans de pintar la pàgina.
// Es carrega com a <script> normal (no mòdul) al <head> perquè no es vegi el color per defecte un instant.
(function () {
  var KEY = 'hologram.accent';
  function apply(c) {
    if (/^#[0-9a-f]{6}$/i.test(c || '')) document.documentElement.style.setProperty('--cyan', c);
  }
  try { apply(localStorage.getItem(KEY)); } catch (e) { /* sense emmagatzematge */ }
  // si es canvia el color en una altra pestanya, aquesta també s'actualitza
  window.addEventListener('storage', function (e) { if (e.key === KEY) apply(e.newValue); });
})();
