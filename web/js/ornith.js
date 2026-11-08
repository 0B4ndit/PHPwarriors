
// Xatbot Ornith
// Envia preguntes a POST /api/ornith.
// Les respostes es mostren amb Markdown, verificacions, fonts i eines.

const $ = (id) => document.getElementById(id);

const chat = $('ornith-chat');
const input = $('ornith-input');
const send = $('ornith-send');
const messages = $('ornith-messages');

const MAX_FONTS = 60;
const AVATAR_ORNITH = '/chiikawa.png';

// ----------------------------------------------------------------
// Markdown -> HTML segur

const escapa = (s) => s.replace(/[&<>"']/g, (c) => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
}[c]));

function enLinia(s) {
  return s
    .replace(/&(?!#?\w+;)/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

const celes = (fila) =>
  fila.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());

const esSeparador = (fila) =>
  /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(fila);

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

      while (i < linies.length && /^\s*\|/.test(linies[i])) {
        cos.push(celes(linies[i++]));
      }

      out.push(
        '<div class="ornith-taula"><table><thead><tr>' +
        cap.map((c) => `<th>${enLinia(c)}</th>`).join('') +
        '</tr></thead><tbody>' +
        cos.map((f) => '<tr>' + f.map((c) => `<td>${enLinia(c)}</td>`).join('') + '</tr>').join('') +
        '</tbody></table></div>'
      );

      continue;
    }

    const h = l.match(/^\s*(#{1,4})\s+(.*)$/);

    if (h) {
      out.push(`<p class="ornith-titol">${enLinia(h[2])}</p>`);
      i++;
      continue;
    }

    if (/^\s*([-*•]|\d+[.)])\s+/.test(l)) {
      const ordenada = /^\s*\d/.test(l);
      const items = [];

      while (i < linies.length && /^\s*([-*•]|\d+[.)])\s+/.test(linies[i])) {
        items.push(
          `<li>${enLinia(linies[i].replace(/^\s*([-*•]|\d+[.)])\s+/, ''))}</li>`
        );
        i++;
      }

      out.push(ordenada ? `<ol>${items.join('')}</ol>` : `<ul>${items.join('')}</ul>`);
      continue;
    }

    if (/^\s*(-{3,}|\*{3,})\s*$/.test(l)) {
      out.push('<hr>');
      i++;
      continue;
    }

    if (!l.trim()) {
      i++;
      continue;
    }

    const para = [];

    while (
      i < linies.length &&
      linies[i].trim() &&
      !/^\s*(\||#{1,4}\s|[-*•]\s|\d+[.)]\s)/.test(linies[i])
    ) {
      para.push(linies[i++]);
    }

    if (!para.length) {
      para.push(linies[i++]);
    }

    out.push(`<p>${para.map(enLinia).join('<br>')}</p>`);
  }

  return out.join('');
}

// ----------------------------------------------------------------
// Avatar de l'Ornith

function creaAvatar() {
  const avatar = document.createElement('img');

  avatar.src = AVATAR_ORNITH;
  avatar.alt = 'Ornith';
  avatar.className = 'ornith-avatar';

  avatar.onerror = () => {
    avatar.style.display = 'none';
  };

  return avatar;
}

// ----------------------------------------------------------------
// Missatges

function afegeix(node) {
  // Només els missatges del bot tenen avatar.
  if (node.classList.contains('bot')) {
    const fila = document.createElement('div');
    fila.className = 'ornith-fila-bot';

    fila.append(creaAvatar(), node);
    messages.append(fila);
  } else {
    messages.append(node);
  }

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

// ----------------------------------------------------------------
// Construcció de les respostes

function resposta(data) {
  const m = document.createElement('div');
  m.className = 'ornith-message bot';

  // Estat: verificada | sense_dades | no_verificada
  const estat = data.estat ||
    (data.verificada === false
      ? 'no_verificada'
      : data.verificada
        ? 'verificada'
        : null);

  // Avís de resposta no verificada
  if (estat === 'no_verificada') {
    const av = document.createElement('div');

    av.className = 'ornith-avis';
    av.textContent =
      `⚠️ No verificada: ${(data.no_verificades || []).join(', ')} no surt de les dades. Comprova-ho abans de fer-ne cas.`;

    m.append(av);
  }

  // Avís de xifres sense font
  if ((data.xifres_sense_font || []).length) {
    const av = document.createElement('div');

    av.className = 'ornith-avis xifres';
    av.textContent =
      `⚠️ Xifres que no surten literalment de cap eina (pot ser una suma o un arrodoniment): ${data.xifres_sense_font.join(', ')}`;

    m.append(av);
  }

  // Cos de la resposta
  const cos = document.createElement('div');
  cos.className = 'ornith-md';

  if (data.text !== undefined) {
    cos.innerHTML = markdown(data.text);
  } else {
    cos.textContent = data.answer || 'Chiikawa no ha retornat cap resposta.';
  }

  m.append(cos);

  // Peu de la resposta
  const peu = document.createElement('div');
  peu.className = 'ornith-peu';

  const SEGELLS = {
    verificada: [
      'ok',
      '✓ verificada amb les dades',
      'Les aules i sessions que cita surten de les eines; comprova-les amb les fonts'
    ],

    sense_dades: [
      'buit',
      '○ sense dades',
      'No s\'ha consultat cap dada: la resposta no es pot comprovar amb el CSV'
    ],

    no_verificada: [
      'ko',
      '✗ no verificada',
      'Cita aules o sessions que no surten de cap eina'
    ],
  };

  if (SEGELLS[estat]) {
    const [cls, txt, ajuda] = SEGELLS[estat];

    const v = document.createElement('span');

    v.className = `ornith-segell ${cls}`;
    v.textContent = txt;
    v.title = ajuda;

    peu.append(v);
  }

  // Fonts
  const fonts = data.fonts || [];

  if (fonts.length) {
    const llista = document.createElement('div');

    llista.className = 'ornith-fonts';

    llista.textContent =
      fonts.slice(0, MAX_FONTS).join('  ') +
      (fonts.length > MAX_FONTS
        ? `  … i ${fonts.length - MAX_FONTS} més`
        : '');

    const copia = document.createElement('button');

    copia.type = 'button';
    copia.className = 'ornith-copia';
    copia.textContent = 'Copia els id';

    copia.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(fonts.join(','));
        copia.textContent = 'Copiats';
      } catch {
        copia.textContent = 'No s\'han pogut copiar';
      }
    });

    const caixa = document.createElement('div');

    caixa.append(llista, copia);
    peu.append(plegable(`Fonts: ${fonts.length} id_sessio`, caixa));
  }

  // Eines utilitzades
  const eines = data.eines || [];

  if (eines.length) {
    const ul = document.createElement('ul');

    for (const e of eines) {
      const li = document.createElement('li');

      li.textContent =
        `${e.eina} ${JSON.stringify(e.arguments)}` +
        (e.error ? `  ERROR: ${e.error}` : '');

      ul.append(li);
    }

    peu.append(
      plegable(`Eines: ${eines.map((e) => e.eina).join(', ')}`, ul)
    );
  }

  if (peu.childElementCount) {
    m.append(peu);
  }

  return afegeix(m);
}

// ----------------------------------------------------------------
// Interfície

function busy(on) {
  input.disabled = on;
  send.disabled = on;

  if (!on) {
    input.focus();
  }
}

// Obrir i tancar el xatbot
$('chatbot-btn').addEventListener('click', () => {
  chat.hidden = !chat.hidden;

  if (!chat.hidden) {
    input.focus();
  }
});

$('ornith-close').addEventListener('click', () => {
  chat.hidden = true;
});

// ----------------------------------------------------------------
// Enviament de preguntes

$('ornith-form').addEventListener('submit', async (event) => {
  event.preventDefault();

  const question = input.value.trim();

  if (!question) return;

  // Missatge de l'usuari: sense avatar
  say(question, 'user');

  input.value = '';
  busy(true);

  // Missatge de càrrega: amb avatar
  const waiting = say('Chiikawa està consultant...');
  waiting.classList.add('ornith-esperant');

  try {
    const r = await fetch('/api/ornith', {
      method: 'POST',

      headers: {
        'Content-Type': 'application/json'
      },

      body: JSON.stringify({ question }),
    });

    const data = await r.json().catch(() => null);

    if (!r.ok || !data?.ok) {
      throw new Error(data?.errors?.[0] || `HTTP ${r.status}`);
    }

    // Eliminar el missatge de càrrega
    waiting.closest('.ornith-fila-bot')?.remove();

    // Mostrar la resposta real
    resposta(data);

  } catch (e) {
    waiting.closest('.ornith-fila-bot')?.remove();

    say(`Error: ${e.message}`, 'error');

  } finally {
    busy(false);
  }
});

