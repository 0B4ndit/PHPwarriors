// Xatbot Ornith: obre / tanca la finestra i envia les preguntes a POST /api/ornith (server.py -> ornith.agent).
// La resposta del LLM arriba en markdown: es pinta amb un intèrpret petit i segur (primer s'escapa tot l'HTML,
// després s'hi posen només les etiquetes que generem nosaltres). Les fonts, les eines i la verificació van a part.

const $ = (id) => document.getElementById(id);
const chat = $('ornith-chat');
const input = $('ornith-input');
const send = $('ornith-send');
const messages = $('ornith-messages');
const MAX_FONTS = 60;

// ---------------------------------------------------------------- markdown -> HTML (segur)

const escapa = (s) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function enLinia(s) {
  // s ja està escapat: només hi afegim etiquetes nostres
  return s
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*\w])\*([^*\s][^*]*)\*(?!\w)/g, '$1<em>$2</em>')
    .replace(/\b(S\d{5})\b(?![^<]*<\/code>)/g, '<code class="ornith-id">$1</code>');
}

const celes = (fila) => fila.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
const esSeparador = (fila) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(fila);

function markdown(text) {
  const linies = escapa(text || '').split('\n');
  const out = [];
  let i = 0;
  while (i < linies.length) {
    const l = linies[i];
    if (/^\s*\|/.test(l) && i + 1 < linies.length && esSeparador(linies[i + 1])) {
      const cap = celes(l);
      const cos = [];
      i += 2;
      while (i < linies.length && /^\s*\|/.test(linies[i])) cos.push(celes(linies[i++]));
      out.push('<div class="ornith-taula"><table><thead><tr>' + cap.map((c) => `<th>${enLinia(c)}</th>`).join('') +
               '</tr></thead><tbody>' + cos.map((f) => '<tr>' + f.map((c) => `<td>${enLinia(c)}</td>`).join('') + '</tr>').join('') +
               '</tbody></table></div>');
      continue;
    }
    const h = l.match(/^\s*(#{1,4})\s+(.*)$/);
    if (h) { out.push(`<p class="ornith-titol">${enLinia(h[2])}</p>`); i++; continue; }
    if (/^\s*([-*•]|\d+[.)])\s+/.test(l)) {
      const ordenada = /^\s*\d/.test(l);
      const items = [];
      while (i < linies.length && /^\s*([-*•]|\d+[.)])\s+/.test(linies[i])) {
        items.push(`<li>${enLinia(linies[i].replace(/^\s*([-*•]|\d+[.)])\s+/, ''))}</li>`);
        i++;
      }
      out.push(ordenada ? `<ol>${items.join('')}</ol>` : `<ul>${items.join('')}</ul>`);
      continue;
    }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(l)) { out.push('<hr>'); i++; continue; }
    if (!l.trim()) { i++; continue; }
    const para = [];
    while (i < linies.length && linies[i].trim() && !/^\s*(\||#{1,4}\s|[-*•]\s|\d+[.)]\s)/.test(linies[i])) para.push(linies[i++]);
    if (!para.length) para.push(linies[i++]);   // línia que no encaixa amb res: com a paràgraf
    out.push(`<p>${para.map(enLinia).join('<br>')}</p>`);
  }
  return out.join('');
}

// ---------------------------------------------------------------- missatges

function afegeix(node) {
  messages.append(node);
  messages.scrollTop = messages.scrollHeight;
  return node;
}

function say(text, type = 'bot') {
  const m = document.createElement('div');
  m.className = `ornith-message ${type}`;
  m.textContent = text;
  return afegeix(m);
}

function plegable(titol, contingut) {
  const d = document.createElement('details');
  const s = document.createElement('summary');
  s.textContent = titol;
  d.append(s, contingut);
  return d;
}

function resposta(data) {
  const m = document.createElement('div');
  m.className = 'ornith-message bot';

  if (data.verificada === false) {
    const av = document.createElement('div');
    av.className = 'ornith-avis';
    av.textContent = `⚠️ No verificada: ${(data.no_verificades || []).join(', ')} no surt de les dades. Comprova-ho abans de fer-ne cas.`;
    m.append(av);
  }

  const cos = document.createElement('div');
  cos.className = 'ornith-md';
  if (data.text !== undefined) cos.innerHTML = markdown(data.text);   // markdown() escapa tot el text abans
  else cos.textContent = data.answer || 'Ornith no ha retornat cap resposta.';
  m.append(cos);

  const peu = document.createElement('div');
  peu.className = 'ornith-peu';
  if (data.verificada !== undefined) {
    const v = document.createElement('span');
    v.className = `ornith-segell ${data.verificada ? 'ok' : 'ko'}`;
    v.textContent = data.verificada ? '✓ verificada amb les dades' : '✗ no verificada';
    peu.append(v);
  }
  const fonts = data.fonts || [];
  if (fonts.length) {
    const llista = document.createElement('div');
    llista.className = 'ornith-fonts';
    llista.textContent = fonts.slice(0, MAX_FONTS).join('  ') + (fonts.length > MAX_FONTS ? `  … i ${fonts.length - MAX_FONTS} més` : '');
    const copia = document.createElement('button');
    copia.type = 'button';
    copia.className = 'ornith-copia';
    copia.textContent = 'Copia els id';
    copia.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(fonts.join(',')); copia.textContent = 'Copiats'; }
      catch { copia.textContent = 'No s\'han pogut copiar'; }
    });
    const caixa = document.createElement('div');
    caixa.append(llista, copia);
    peu.append(plegable(`Fonts: ${fonts.length} id_sessio`, caixa));
  }
  const eines = data.eines || [];
  if (eines.length) {
    const ul = document.createElement('ul');
    for (const e of eines) {
      const li = document.createElement('li');
      li.textContent = `${e.eina} ${JSON.stringify(e.arguments)}` + (e.error ? `  ERROR: ${e.error}` : '');
      ul.append(li);
    }
    peu.append(plegable(`Eines: ${eines.map((e) => e.eina).join(', ')}`, ul));
  }
  if (peu.childElementCount) m.append(peu);
  return afegeix(m);
}

// ---------------------------------------------------------------- interfície

function busy(on) {
  input.disabled = on;
  send.disabled = on;
  if (!on) input.focus();
}

$('chatbot-btn').addEventListener('click', () => {
  chat.hidden = !chat.hidden;
  if (!chat.hidden) input.focus();
});
$('ornith-close').addEventListener('click', () => { chat.hidden = true; });

$('ornith-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) return;

  say(question, 'user');
  input.value = '';
  busy(true);
  const waiting = say('Ornith està consultant...');
  waiting.classList.add('ornith-esperant');
  try {
    const r = await fetch('/api/ornith', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const data = await r.json().catch(() => null);
    if (!r.ok || !data?.ok) throw new Error(data?.errors?.[0] || `HTTP ${r.status}`);
    waiting.remove();
    resposta(data);
  } catch (e) {
    waiting.remove();
    say(`Error: ${e.message}`, 'error');
  } finally {
    busy(false);
  }
});
