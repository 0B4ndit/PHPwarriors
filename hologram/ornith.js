// Xatbot Ornith: obre / tanca la finestra i envia les preguntes a POST /api/ornith (server.py -> test_tools.parlar).

const $ = (id) => document.getElementById(id);
const chat = $('ornith-chat');
const input = $('ornith-input');
const send = $('ornith-send');
const messages = $('ornith-messages');

function say(text, type = 'bot') {
  const m = document.createElement('div');
  m.className = `ornith-message ${type}`;
  m.textContent = text;
  messages.append(m);
  messages.scrollTop = messages.scrollHeight;
  return m;
}

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
  try {
    const r = await fetch('/api/ornith', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const data = await r.json().catch(() => null);
    if (!r.ok || !data?.ok) throw new Error(data?.errors?.[0] || `HTTP ${r.status}`);
    waiting.remove();
    say(data.answer || 'Ornith no ha retornat cap resposta.');
  } catch (e) {
    waiting.remove();
    say(`Error: ${e.message}`, 'error');
  } finally {
    busy(false);
  }
});
