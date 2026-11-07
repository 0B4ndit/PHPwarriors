import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { PALETTE, createHologramMaterial } from './hologram-material.js';
import { Schedule, step, semOf, addWeekdays, isWeekend, hhmm, toMin, isoWeek } from './schedule.js';

const COLOR_LERP_SECONDS = 0.35;
const GHOST_LINE = 0x2c6478;
const CMAP_V0 = 0.32; // brightness of a 0 % room (grey, still visible on the dark background)

// ---------- scene ----------
const canvasHost = document.getElementById('scene');
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
canvasHost.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x03070c);

const camera = new THREE.PerspectiveCamera(40, 1, 0.5, 1000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI * 0.49;

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
composer.addPass(new UnrealBloomPass(new THREE.Vector2(1, 1), 0.28, 0.35, 0.4)); // subtle glow
composer.addPass(new OutputPass());

function resize() {
  const w = canvasHost.clientWidth, h = canvasHost.clientHeight;
  renderer.setSize(w, h);
  composer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(canvasHost);

// ---------- helpers ----------
// Label sprite sized to its text so nothing is clipped. `height` is the sprite's world height.
const measureCtx = document.createElement('canvas').getContext('2d');
function makeLabel(text, sub, height = 2.4, color = '#9fd8e6') {
  const main = 'bold 44px monospace', small = '30px monospace';
  measureCtx.font = main;
  let w = measureCtx.measureText(text).width;
  if (sub) { measureCtx.font = small; w = Math.max(w, measureCtx.measureText(sub).width); }
  const pad = 20;
  const c = document.createElement('canvas');
  c.width = Math.ceil(w + pad * 2);
  c.height = sub ? 100 : 64;
  const g = c.getContext('2d');
  g.textAlign = 'center';
  g.textBaseline = 'alphabetic';
  g.fillStyle = color;
  g.font = main;
  g.fillText(text, c.width / 2, sub ? 44 : 46);
  if (sub) { g.fillStyle = '#5f9aab'; g.font = small; g.fillText(sub, c.width / 2, 86); }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, depthTest: false }));
  s.scale.set(height * (c.width / c.height), height, 1);
  s.renderOrder = 10;
  return s;
}

// room label, shrunk to the room's width so narrow rooms (e.g. QC-3115.x) do not overlap
function roomLabel(code, sub, width) {
  const l = makeLabel(code, sub, 2.2);
  l.scale.multiplyScalar(Math.min(1, width / l.scale.x));
  return l;
}

const ghostLineMat =new THREE.LineBasicMaterial({ color: GHOST_LINE, transparent: true, opacity: 0.55 });
const ghostFillMat = new THREE.MeshBasicMaterial({ color: 0x0c2a36, transparent: true, opacity: 0.12, depthWrite: false });

function ghostBox(x0, x1, y0, y1, z0, z1, fill = true) {
  const geo = new THREE.BoxGeometry(x1 - x0, y1 - y0, z1 - z0);
  const g = new THREE.Group();
  g.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo), ghostLineMat));
  if (fill) g.add(new THREE.Mesh(geo, ghostFillMat));
  g.position.set((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
  return g;
}

function split(weights, len) {
  const total = weights.reduce((a, b) => a + b, 0);
  let x = 0;
  return weights.map((w) => { const s = x; x += (w / total) * len; return [s, x]; });
}

function mulberry32(a) {
  return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

// ---------- colour model ----------
// categories: red | green | neutral.
// colormap: one hue (chosen in the UI); 0 % = no colour (dim grey), 100 % = full saturation and brightness.
const cmap = { mode: 'categories', hue: 200 };
try { cmap.hue = Number(JSON.parse(localStorage.getItem('hologram.hue') || '200')) || 200; } catch { /* ignore */ }
const saveHue = () => { try { localStorage.setItem('hologram.hue', String(cmap.hue)); } catch { /* ignore */ } };

const clamp01 = (x) => Math.min(1, Math.max(0, x));
function cmapColor(v) {
  const t = clamp01(v / 100);
  const s = t;                              // saturation: 0 -> 1
  const val = CMAP_V0 + (1 - CMAP_V0) * t;  // brightness: dim grey -> full
  const l = val * (1 - s / 2);              // HSV -> HSL
  const sl = l === 0 || l === 1 ? 0 : (val - l) / Math.min(l, 1 - l);
  return new THREE.Color().setHSL(cmap.hue / 360, sl, l, THREE.SRGBColorSpace);
}

// ---------- build from layout.json ----------
const rooms = new Map();
const world = new THREE.Group();
scene.add(world);
const labelGroup = new THREE.Group();
world.add(labelGroup);
const ESPINA_ORDER = ['Q4', 'Q3', 'Q2', 'Q1']; // north -> south, as in the plans
const PANEL_ORDER = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'QC']; // room list groups
const PLANTES = ['baixa', 'primera', 'segona', 'tercera'];
let layout;

function build() {
  const G = layout.geometry;
  const gap = 0.35;
  let seed = 0;

  for (const slab of layout.slabs) {
    const y0 = PLANTES.indexOf(slab.planta) * G.floorHeight;
    const inSpine = ESPINA_ORDER.includes(slab.espina);
    // Q1-Q4: cells laid along the espina by plan area. Q5, Q6, QC: each room carries its own x/z box.
    let spans = [];
    if (inSpine) {
      const z0 = ESPINA_ORDER.indexOf(slab.espina) * G.pitch;
      const z1 = z0 + G.slabDepth;
      world.add(ghostBox(0, G.slabLength, y0, y0 + 0.25, z1, z1 + G.corridorDepth, false));
      spans = split(slab.rooms.map((r) => r.area), G.slabLength).map(([a, b]) => ({ x: [a, b], z: [z0, z1] }));
    }

    slab.rooms.forEach((r, i) => {
      const box = inSpine ? spans[i] : r;
      const [a, b] = box.x, [c, d] = box.z;
      if (r.ghost) { world.add(ghostBox(a, b, y0, y0 + G.roomHeight, c, d, false)); return; }

      const geo = new THREE.BoxGeometry(b - a - gap, G.roomHeight, d - c - gap);
      const mat = createHologramMaterial(seed++ * 1.7);
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set((a + b) / 2, y0 + G.roomHeight / 2, (c + d) / 2);
      const id = `${slab.espina}-${r.code}`;
      mesh.userData.roomId = id;

      const edgeMat = new THREE.LineBasicMaterial({ color: PALETTE.neutral.clone(), transparent: true, opacity: 0.75 });
      mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo), edgeMat));
      world.add(mesh);

      const label = roomLabel(r.code, String(r.capacity), b - a);
      label.position.set(mesh.position.x, y0 + G.roomHeight + 1.4, mesh.position.z);
      labelGroup.add(label);

      rooms.set(id, {
        id, data: { ...r, espina: slab.espina, planta: slab.planta }, mesh, mat, edgeMat,
        current: PALETTE.neutral.clone(), target: PALETTE.neutral.clone(), from: PALETTE.neutral.clone(),
        t: 1, colorName: 'neutral', value: 0, highlight: 0, highlightTarget: 0,
        label, labelPos: label.position.clone(), labelSub: String(r.capacity), labelWidth: b - a, tvalue: 0, tlabel: '', over: null,
      });
    });
  }

  for (const e of ESPINA_ORDER) {
    const t = makeLabel(e, null, 3.2, '#cfeef5');
    t.position.set(G.slabLength + 6, 1.8, ESPINA_ORDER.indexOf(e) * G.pitch + G.slabDepth / 2);
    labelGroup.add(t);
  }

  for (const c of layout.context) {
    world.add(ghostBox(c.x[0], c.x[1], 0, c.floors * G.floorHeight, c.z[0], c.z[1]));
    // one outline per floor slab, so each planta reads as its own level
    for (let f = 1; f < c.floors; f++) {
      const y = f * G.floorHeight;
      const ring = [[c.x[0], c.z[0]], [c.x[1], c.z[0]], [c.x[1], c.z[1]], [c.x[0], c.z[1]]]
        .map(([x, z]) => new THREE.Vector3(x, y, z));
      world.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(ring), ghostLineMat));
    }
    const t = makeLabel(c.name, null, 3.4, '#5b95a6');
    t.position.set((c.x[0] + c.x[1]) / 2, c.floors * G.floorHeight + 2.4, (c.z[0] + c.z[1]) / 2);
    labelGroup.add(t);
  }

  const grid = new THREE.GridHelper(260, 52, 0x0b2f3c, 0x07202a);
  grid.position.set(20, -0.1, 50);
  world.add(grid);

  addTrees(G);
}

// ---------- trees (architectural-model style, deliberately muted so they never read as "green = status") ----------
function addTrees(G) {
  const rnd = mulberry32(7);
  const lineMat = new THREE.LineBasicMaterial({ color: 0x7f9f98, transparent: true, opacity: 0.5 });
  const fillMat = new THREE.MeshBasicMaterial({ color: 0x24443f, transparent: true, opacity: 0.14, depthWrite: false });
  const ball = new THREE.IcosahedronGeometry(1, 1);
  const ballWire = new THREE.WireframeGeometry(ball);
  const cone = new THREE.ConeGeometry(1, 2.4, 7);
  const coneWire = new THREE.WireframeGeometry(cone);
  const trunk = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 1, 0)]);

  function tree(x, z) {
    const conifer = rnd() < 0.3;
    const r = 1.3 + rnd() * 0.9;
    const trunkH = 1.3 + rnd() * 0.6;
    const g = new THREE.Group();
    const tr = new THREE.Line(trunk, lineMat);
    tr.scale.y = trunkH;
    g.add(tr);
    const crown = new THREE.Group();
    crown.add(new THREE.LineSegments(conifer ? coneWire : ballWire, lineMat));
    crown.add(new THREE.Mesh(conifer ? cone : ball, fillMat));
    crown.scale.setScalar(r);
    crown.position.y = trunkH + (conifer ? 1.2 * r : 0.85 * r);
    g.add(crown);
    g.position.set(x, 0, z);
    world.add(g);
  }

  // rows in the open courtyards between the espines, north of Q4, between Q1 and the Cos Central, south of it
  const courtyardZ = [-5];
  for (let k = 0; k < 3; k++) courtyardZ.push(G.slabDepth + G.corridorDepth + (G.pitch - G.slabDepth - G.corridorDepth) / 2 + k * G.pitch);
  courtyardZ.push(83.9);
  for (const z of courtyardZ) {
    for (let x = 3; x <= 42; x += 5.5 + rnd() * 2.5) {
      if (rnd() < 0.25) continue;
      tree(x + (rnd() - 0.5) * 1.5, z + (rnd() - 0.5) * 2.2);
    }
  }
  for (let x = -55; x <= 95; x += 14 + rnd() * 6) tree(x, 109 + (rnd() - 0.5) * 2);
}

function frame() {
  const target = new THREE.Vector3(25, 3, 52);
  const dist = 105 * Math.max(1, 1.25 / camera.aspect);
  controls.target.copy(target);
  camera.position.copy(target).addScaledVector(new THREE.Vector3(-0.3, 0.55, 0.78).normalize(), dist);
}

// ---------- recolouring ----------
function targetFor(room) {
  if (cmap.mode === 'colormap') return cmapColor(room.value);
  if (cmap.mode === 'schedule') return cmapColor(room.tvalue);
  return PALETTE[room.colorName];
}
function recolor(room, instant = false) {
  const tgt = targetFor(room);
  if (!tgt.equals(room.target)) {
    room.from.copy(instant ? tgt : room.current);
    room.target.copy(tgt);
    room.t = instant ? 1 : 0;
    if (instant) room.current.copy(tgt);
  }
  updateRow(room);
}
const recolorAll = (instant = false) => { for (const r of rooms.values()) recolor(r, instant); updateSummary(); };

// ---------- public API (also used by the live connection) ----------
const VALID = new Set(['red', 'green', 'neutral']);

window.setRoomColor = function setRoomColor(id, color) {
  const room = rooms.get(id);
  if (!room) { console.warn(`[hologram] unknown room id: ${id}`); return false; }
  room.colorName = VALID.has(color) ? color : 'neutral';
  recolor(room);
  updateSummary();
  return true;
};
window.setAllRoomColors = (map) => { for (const id of rooms.keys()) window.setRoomColor(id, (map && map[id]) || 'neutral'); };

window.setRoomValue = function setRoomValue(id, v) {
  const room = rooms.get(id);
  if (!room) { console.warn(`[hologram] unknown room id: ${id}`); return false; }
  room.value = typeof v === 'number' && isFinite(v) ? Math.min(100, Math.max(0, v)) : 0; // nothing scheduled = 0 %
  recolor(room);
  updateSummary();
  return true;
};
window.setAllRoomValues = (map) => { for (const id of rooms.keys()) window.setRoomValue(id, map ? map[id] : null); };

window.setMode = function setMode(m) {
  cmap.mode = m === 'colormap' || m === 'schedule' ? m : 'categories';
  document.querySelectorAll('[data-mode]').forEach((b) => b.classList.toggle('on', b.dataset.mode === cmap.mode));
  document.getElementById('cmap-controls').hidden = cmap.mode === 'categories';
  document.getElementById('time-controls').hidden = cmap.mode !== 'schedule';
  if (cmap.mode === 'schedule') applyView();
  else for (const room of rooms.values()) { setLabelSub(room, String(room.data.capacity)); setOver(room, null); }
  recolorAll();
  updateBubble();
  refreshDetail();
};

// ---------- schedule mode: time views driven by the session dataset (/api/sessions) ----------
// hour = students per room at that moment (colour = students / capacity; "TOO MANY STUDENTS" over capacity)
// day | week | semester = % of the open time the room has a class (students are irrelevant)
let sched = null;
let scheduleSummary = '';
const view = { scope: 'hour', date: '', min: 630, sem: 1 };
const FALLBACK_WINDOW = { start: 510, end: 1260 };
const overLayer = new THREE.Group();
world.add(overLayer);
const winOf = () => (sched ? sched.window : FALLBACK_WINDOW);

function disposeGroup(g) {
  g.traverse((o) => { o.geometry?.dispose?.(); o.material?.map?.dispose?.(); o.material?.dispose?.(); });
}
function setLabelSub(room, sub) {
  if (room.labelSub === sub) return;
  labelGroup.remove(room.label);
  disposeGroup(room.label);
  room.label = roomLabel(room.data.code, sub, room.labelWidth);
  room.label.position.copy(room.labelPos);
  labelGroup.add(room.label);
  room.labelSub = sub;
}
function setOver(room, info) {
  const txt = info ? `${info.n} / ${info.cap}` : '';
  if ((room.over?.txt || '') === txt) return;
  if (room.over) { overLayer.remove(room.over.group); disposeGroup(room.over.group); room.over = null; }
  if (!info) return;
  const p = room.mesh.geometry.parameters;
  const mat = new THREE.LineBasicMaterial({ color: 0xff4fd8, transparent: true, opacity: 0.9 });
  const group = new THREE.Group();
  const box = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(p.width + 0.9, p.height + 0.9, p.depth + 0.9)), mat);
  box.position.copy(room.mesh.position);
  const badge = makeLabel('TOO MANY STUDENTS', txt, 2.6, '#ff4fd8');
  badge.position.copy(room.labelPos).add(new THREE.Vector3(0, 3.6, 0));
  group.add(box, badge);
  overLayer.add(group);
  room.over = { group, mat, txt, badge };
}

const $ = (id) => document.getElementById(id);
function syncTimeControls() {
  document.querySelectorAll('[data-scope]').forEach((b) => b.classList.toggle('on', b.dataset.scope === view.scope));
  $('row-sem').hidden = view.scope !== 'semester';
  $('row-date').hidden = view.scope === 'semester';
  $('row-time').hidden = view.scope !== 'hour';
  $('t-sem').value = String(view.sem);
  if (view.date) $('t-date').value = view.date;
  $('t-time').value = hhmm(view.min);
  $('t-hint').textContent = {
    hour: '← → ±30 min · ↑ ↓ ±1 day', day: '← → ±1 day · ↑ ↓ ±1 week',
    week: '← → ±1 week', semester: '← → switch semester',
  }[view.scope];
  $('legend-hi').textContent = view.scope === 'hour' ? '100% = at capacity' : '100%';
}

function applyView() {
  if (cmap.mode !== 'schedule') return;
  const infoEl = $('t-info');
  syncTimeControls();
  if (!sched) {
    for (const room of rooms.values()) { room.tvalue = 0; room.tlabel = '–'; setLabelSub(room, '–'); setOver(room, null); }
    infoEl.textContent = 'No session data yet: run nivell1.py (or PUT /api/sessions).';
    scheduleSummary = 'no data';
    recolorAll();
    return;
  }
  if (!view.date) {
    view.date = sched.semesters[view.sem]?.start || sched.semesters[1]?.start || '2026-09-07';
    if (isWeekend(view.date)) view.date = addWeekdays(view.date, 1);
    syncTimeControls();
  }
  const caps = new Map([...rooms].map(([id, r]) => [id, r.data.capacity]));
  const res = sched.evaluate(view, caps);
  for (const [id, v] of res.rooms) {
    const room = rooms.get(id);
    room.tvalue = v.value; room.tlabel = v.label;
    setLabelSub(room, v.label);
    setOver(room, v.over ? v : null);
  }
  infoEl.textContent = res.info;
  scheduleSummary = res.summary;
  recolorAll();
  updateBubble();
  refreshDetail();
}

function navigate(dir) {
  Object.assign(view, step(view, dir, winOf()));
  applyView();
}
function stepDate(sgn) { // the date arrows move by the natural unit of the scope
  const unit = view.scope === 'hour' ? 'day' : view.scope;
  const v = step({ ...view, scope: unit }, sgn < 0 ? 'left' : 'right', winOf());
  view.date = v.date; view.sem = v.sem;
  applyView();
}
function semesterStart(sem) { return sched?.semesters[sem]?.start || view.date; }

function initTimeControls() {
  $('d-close').addEventListener('click', clearSelection);
  document.querySelectorAll('[data-scope]').forEach((b) => b.addEventListener('click', () => {
    view.scope = b.dataset.scope;
    if (view.scope !== 'semester' && (!view.date || semOf(view.date) !== view.sem)) view.date = semesterStart(view.sem);
    applyView();
  }));
  $('t-sem').addEventListener('change', (e) => {
    view.sem = Number(e.target.value);
    if (!view.date || semOf(view.date) !== view.sem) view.date = semesterStart(view.sem);
    applyView();
  });
  $('t-date').addEventListener('change', (e) => { if (e.target.value) { view.date = e.target.value; view.sem = semOf(view.date); applyView(); } });
  $('t-time').addEventListener('change', (e) => { if (e.target.value) { view.min = toMin(e.target.value); applyView(); } });
  $('d-prev').addEventListener('click', () => stepDate(-1));
  $('d-next').addEventListener('click', () => stepDate(1));
  $('h-prev').addEventListener('click', () => navigate('left'));
  $('h-next').addEventListener('click', () => navigate('right'));
  const keys = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' };
  document.addEventListener('keydown', (e) => {
    if (cmap.mode !== 'schedule' || !keys[e.key] || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.target.matches?.('input, select, textarea')) return; // let form fields use their own arrow keys
    e.preventDefault();
    navigate(keys[e.key]);
  });
}

// ---------- click info: bubble (hour) / list (day, week, semester) ----------
const bubbleLayer = new THREE.Group();
world.add(bubbleLayer);

function makeBubble(lines) {
  const f = (l) => `${l.bold ? 'bold ' : ''}${l.bold ? 30 : 24}px sans-serif`;
  const pad = 20, lh = 40;
  let w = 0;
  for (const l of lines) { measureCtx.font = f(l); w = Math.max(w, measureCtx.measureText(l.t).width); }
  const c = document.createElement('canvas');
  c.width = Math.ceil(w + pad * 2); c.height = lines.length * lh + pad;
  const g = c.getContext('2d');
  g.fillStyle = 'rgba(6,24,34,0.94)'; g.strokeStyle = '#3a8fb0'; g.lineWidth = 3;
  g.beginPath(); g.roundRect(2, 2, c.width - 4, c.height - 4, 14); g.fill(); g.stroke();
  g.textAlign = 'center'; g.textBaseline = 'middle';
  lines.forEach((l, i) => { g.font = f(l); g.fillStyle = l.color || '#cfeef5'; g.fillText(l.t, c.width / 2, pad / 2 + lh * (i + 0.5)); });
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, depthTest: false }));
  const height = lines.length * 1.5 + 0.8;
  s.scale.set(height * (c.width / c.height), height, 1);
  s.renderOrder = 20;
  return s;
}

const clip = (t, n) => (t.length > n ? `${t.slice(0, n - 1)}…` : t);
const teachersOf = (t) => (t ? t.split('|').join(', ') : '');

function updateBubble() {
  disposeGroup(bubbleLayer); bubbleLayer.clear();
  for (const r of rooms.values()) if (r.over) r.over.badge.visible = true;
  if (cmap.mode !== 'schedule' || view.scope !== 'hour' || !selected || !sched || !view.date) return;
  const room = rooms.get(selected);
  const list = sched.sessionsAt(selected, view.date, view.min);
  const lines = [];
  if (!list.length) lines.push({ t: `${room.data.code} · free`, color: '#6a98a8' });
  for (const x of list) {
    lines.push({ t: clip(x.name, 42), bold: true });
    const meta = [x.group, x.teachers ? `Prof. ${teachersOf(x.teachers)}` : ''].filter(Boolean).join(' · ');
    if (meta) lines.push({ t: clip(meta, 46), color: '#8fc3d3' });
  }
  const b = makeBubble(lines);
  b.position.copy(room.labelPos).add(new THREE.Vector3(0, 2.6 + lines.length * 0.75, 0));
  bubbleLayer.add(b);
  if (room.over) room.over.badge.visible = false; // the bubble takes its place; the outline keeps pulsing
}

function refreshDetail() {
  const box = $('detail');
  if (cmap.mode !== 'schedule' || view.scope === 'hour' || !selected || !sched) { box.hidden = true; return; }
  const items = sched.listing(selected, view);
  const period = view.scope === 'day' ? view.date : view.scope === 'week' ? isoWeek(view.date) : `semester ${view.sem}`;
  $('d-title').textContent = `${selected} · ${period} · ${items.reduce((a, x) => a + x.count, 0)} classes`;
  const list = $('d-list');
  list.replaceChildren();
  if (!items.length) list.append(el('div', 'd-empty', 'No classes in this period.'));
  for (const x of items) {
    const row = el('div', 'd-row');
    const name = el('span', 'd-name', x.name);
    if (x.group) name.append(el('i', null, ` ${x.group}`));
    row.append(el('span', 'd-when', x.when), name, el('span', 'd-n', view.scope === 'semester' && x.count > 1 ? `×${x.count}` : ''));
    list.append(row);
  }
  box.hidden = false;
}

function clearSelection() {
  if (selected) rooms.get(selected).highlightTarget = 0;
  selected = null;
  document.querySelectorAll('.row.sel').forEach((e) => e.classList.remove('sel'));
  updateBubble(); refreshDetail();
}
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

async function fetchDataset() {
  try { const ds = await api('GET', 'sessions'); sched = ds ? new Schedule(ds) : null; } catch { sched = null; }
  applyView();
}

// ---------- live connection ----------
const statusEl = document.getElementById('status');
function setStatus(kind, text) { statusEl.className = `pill ${kind}`; statusEl.textContent = text; }

function startPolling() {
  setStatus('warn', 'polling files (no API)');
  const tick = async () => {
    try {
      const res = await fetch('rooms.json', { cache: 'no-store' });
      if (!res.ok) throw new Error(res.status);
      window.setAllRoomColors(await res.json());
      try {
        const c = await (await fetch('colormap.json', { cache: 'no-store' })).json();
        window.setAllRoomValues(c.values || {});
        window.setMode(c.mode);
      } catch { /* colormap.json optional */ }
      setStatus('warn', 'polling files (no API)');
    } catch { setStatus('bad', 'no data source'); }
  };
  fetch('sessions-data.json', { cache: 'no-store' }).then((r) => r.json()).then((ds) => { sched = new Schedule(ds); applyView(); }).catch(() => {});
  tick();
  setInterval(tick, 2000);
}

function connect() {
  if (!window.EventSource) return startPolling();
  const es = new EventSource('api/events');
  let gotData = false;
  const on = (name, fn) => es.addEventListener(name, (e) => { gotData = true; fn(JSON.parse(e.data)); setStatus('ok', 'live · API connected'); });
  on('mode', (d) => window.setMode(d.mode));
  on('values', (d) => window.setAllRoomValues(d));
  on('state', (d) => window.setAllRoomColors(d));
  on('sessions', () => fetchDataset());
  es.onerror = () => {
    if (!gotData) { es.close(); startPolling(); }
    else setStatus('warn', 'reconnecting…');
  };
}

async function api(method, path, body) {
  const r = await fetch(`api/${path}`, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

// ---------- side panel ----------
const list = document.getElementById('room-list');
const summary = document.getElementById('counts');

function updateRow(room) {
  const row = document.querySelector(`[data-row="${room.id}"]`);
  if (!row) return;
  row.querySelector('.dot').style.background = `#${room.target.getHexString(THREE.SRGBColorSpace)}`;
  const val = row.querySelector('.val');
  val.textContent = cmap.mode === 'colormap' ? `${Math.round(room.value)}%` : cmap.mode === 'schedule' ? room.tlabel : '';
  val.style.color = cmap.mode === 'schedule' && room.over ? '#ff4fd8' : '';
}

function updateSummary() {
  if (cmap.mode === 'schedule') {
    summary.textContent = scheduleSummary;
  } else if (cmap.mode === 'colormap') {
    const vs = [...rooms.values()].map((r) => r.value);
    const mean = Math.round(vs.reduce((a, b) => a + b, 0) / vs.length);
    summary.textContent = `${vs.filter((v) => v > 0).length}/${rooms.size} in use · mean ${mean}%`;
  } else {
    const n = { red: 0, green: 0, neutral: 0 };
    for (const r of rooms.values()) n[r.colorName]++;
    summary.innerHTML = `<span class="dot red"></span>${n.red} <span class="dot green"></span>${n.green} <span class="dot neutral"></span>${n.neutral}`;
  }
}

function refreshLegend() {
  const stops = [0, 25, 50, 75, 100].map((p) => `#${cmapColor(p).getHexString(THREE.SRGBColorSpace)} ${p}%`).join(', ');
  document.getElementById('legend-bar').style.background = `linear-gradient(90deg, ${stops})`;
  document.getElementById('hue').value = cmap.hue;
  document.getElementById('hue-n').textContent = `${Math.round(cmap.hue)}°`;
}

function buildPanel() {
  for (const e of PANEL_ORDER) {
    for (const p of PLANTES) {
      const group = [...rooms.values()].filter((r) => r.data.espina === e && r.data.planta === p);
      if (!group.length) continue;
      const h = document.createElement('h3');
      h.textContent = `${e} · planta ${p}`;
      list.appendChild(h);
      for (const r of group) {
        const row = document.createElement('div');
        row.className = 'row';
        row.dataset.row = r.id;
        row.innerHTML = `<span class="dot"></span><span class="code">${r.id}</span><span class="val"></span><span class="cap">${r.data.capacity}</span>`;
        row.addEventListener('click', () => focusRoom(r.id));
        list.appendChild(row);
      }
    }
  }
  const rainbow = Array.from({ length: 13 }, (_, i) => `hsl(${i * 30} 100% 50%)`).join(', ');
  document.getElementById('hue').style.background = `linear-gradient(90deg, ${rainbow})`;
  document.getElementById('hue').addEventListener('input', (ev) => {
    cmap.hue = Number(ev.target.value); saveHue(); refreshLegend(); recolorAll(true);
  });
  document.querySelectorAll('[data-mode]').forEach((b) => b.addEventListener('click', async () => {
    window.setMode(b.dataset.mode);                       // instant locally...
    try { await api('PUT', 'mode', { mode: b.dataset.mode }); } catch { /* no API: local only */ } // ...and published for everyone
  }));
  initTimeControls();
  refreshLegend();
  updateSummary();

  const origin = location.origin.startsWith('http') ? location.origin : 'http://localhost:8000';
  document.getElementById('api-example').textContent =
`# categories
curl -X PUT ${origin}/api/rooms/Q3-1007 \\
  -H "Content-Type: application/json" -d '{"color":"red"}'

# colormap: percentage 0-100 (unlisted rooms = 0%)
curl -X POST ${origin}/api/values \\
  -H "Content-Type: application/json" \\
  -d '{"Q3-1007":82,"Q1-1011":15.5}'

# switch what the page shows
curl -X PUT ${origin}/api/mode \\
  -H "Content-Type: application/json" -d '{"mode":"colormap"}'`;
}

document.getElementById('btn-labels').addEventListener('click', () => { labelGroup.visible = !labelGroup.visible; });

// demo: random updates through the API, like an external client would
let demoTimer = null;
const demoBtn = document.getElementById('btn-demo');
demoBtn.addEventListener('click', () => {
  if (demoTimer) { clearInterval(demoTimer); demoTimer = null; demoBtn.textContent = 'Start demo'; return; }
  demoBtn.textContent = 'Stop demo';
  const ids = [...rooms.keys()];
  demoTimer = setInterval(async () => {
    const id = ids[Math.floor(Math.random() * ids.length)];
    const useValue = cmap.mode === 'colormap';
    const v = useValue ? Math.round(Math.random() * 1000) / 10 : ['red', 'green', 'neutral'][Math.floor(Math.random() * 3)];
    try { await api('PUT', `${useValue ? 'values' : 'rooms'}/${id}`, useValue ? { value: v } : { color: v }); }
    catch { useValue ? window.setRoomValue(id, v) : window.setRoomColor(id, v); }
  }, 600);
});

// ---------- focus / pick ----------
let selected = null, focusTarget = null;
function focusRoom(id) {
  if (selected) rooms.get(selected).highlightTarget = 0;
  document.querySelectorAll('.row.sel').forEach((el) => el.classList.remove('sel'));
  selected = id;
  const room = rooms.get(id);
  room.highlightTarget = 1;
  focusTarget = room.mesh.position.clone();
  const row = document.querySelector(`[data-row="${id}"]`);
  if (row) { row.classList.add('sel'); row.scrollIntoView({ block: 'nearest' }); }
  updateBubble();
  refreshDetail();
}
const ray = new THREE.Raycaster();
let downAt = null;
renderer.domElement.addEventListener('pointerdown', (e) => { downAt = [e.clientX, e.clientY]; });
renderer.domElement.addEventListener('pointerup', (e) => {
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 4) return;
  const rect = renderer.domElement.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1), camera);
  const hit = ray.intersectObjects([...rooms.values()].map((r) => r.mesh), false)[0];
  if (hit) focusRoom(hit.object.userData.roomId);
  else clearSelection(); // click on empty space: drop the selection (bubble / list)
});

// ---------- loop ----------
const clock = new THREE.Clock();
function animate() {
  const dt = clock.getDelta(), time = clock.elapsedTime;
  for (const room of rooms.values()) {
    if (room.t < 1) {
      room.t = Math.min(1, room.t + dt / COLOR_LERP_SECONDS);
      room.current.copy(room.from).lerp(room.target, room.t);
    }
    room.mat.uniforms.uColor.value.copy(room.current);
    room.mat.uniforms.uTime.value = time;
    room.highlight += (room.highlightTarget - room.highlight) * Math.min(1, dt * 8);
    room.mat.uniforms.uHighlight.value = room.highlight;
    room.edgeMat.color.copy(room.current).multiplyScalar(0.9 + room.highlight * 0.6);
  }
  const pulse = 0.4 + 0.5 * (0.5 + 0.5 * Math.sin(time * 4));
  for (const r of rooms.values()) if (r.over) r.over.mat.opacity = pulse;
  if (focusTarget) {
    controls.target.lerp(focusTarget, Math.min(1, dt * 5));
    if (controls.target.distanceTo(focusTarget) < 0.05) focusTarget = null;
  }
  controls.update();
  composer.render();
  requestAnimationFrame(animate);
}

// ---------- start ----------
(async () => {
  layout = await (await fetch('layout.json', { cache: 'no-store' })).json();
  build();
  buildPanel();
  recolorAll(true);
  window.setMode('categories');
  resize();
  frame();
  animate();
  connect();
})();
