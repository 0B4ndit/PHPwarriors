import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { NEUTRAL, createHologramMaterial } from './hologram-material.js';
import { Schedule, step, semOf, addWeekdays, isWeekend, hhmm, toMin, isoWeek } from './schedule.js';
import { VERSION_VISTA, initVersions, initViews } from '/comu/nav.js';

const COLOR_LERP_SECONDS = 0.35;
const GHOST_LINE = 0x2c6478;
const OVER_COLOR = '#ff4fd8'; // "too many students"

// ---------- top bar: database version (each one reads a sessions view) and page links ----------
let version = initVersions((v) => {
  version = v;
  loadSessions().catch((e) => { $('t-info').textContent = `Cannot load version ${v}: ${e.message}`; });
});
initViews('hologram');

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
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const measureCtx = document.createElement('canvas').getContext('2d');

function canvasSprite(c, height, renderOrder) {
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, depthTest: false }));
  s.scale.set(height * (c.width / c.height), height, 1);
  s.renderOrder = renderOrder;
  return s;
}

// Text sprite sized to its lines so nothing is clipped. `scale` = world units per 100 canvas px,
// so every label draws its text at the same size whatever its number of lines.
function makeLabel(text, { tag = '', sub = '', scale = 2.4, color = '#9fd8e6' } = {}) {
  const lines = [{ t: text, font: 'bold 44px monospace', color, h: 50 }];
  if (tag) lines.push({ t: tag, font: '26px monospace', color: '#7fb8c8', h: 32 });
  if (sub) lines.push({ t: sub, font: '30px monospace', color: '#5f9aab', h: 36 });
  const pad = 20;
  let w = 0;
  for (const l of lines) { measureCtx.font = l.font; w = Math.max(w, measureCtx.measureText(l.t).width); }
  const c = document.createElement('canvas');
  c.width = Math.ceil(w + pad * 2);
  c.height = lines.reduce((a, l) => a + l.h, 0) + 14;
  const g = c.getContext('2d');
  g.textAlign = 'center';
  g.textBaseline = 'alphabetic';
  let y = 4;
  for (const l of lines) { y += l.h; g.font = l.font; g.fillStyle = l.color; g.fillText(l.t, c.width / 2, y - 8); }
  return canvasSprite(c, scale * (c.height / 100), 10);
}

// Room label: code, room type and the current value, shrunk to the room's width so narrow rooms do not overlap.
function roomLabel(room) {
  const l = makeLabel(room.data.code, { tag: room.data.tipus, sub: room.labelSub, scale: 2.2 });
  l.scale.multiplyScalar(Math.min(1, room.width / l.scale.x));
  l.position.copy(room.labelPos);
  l.material.opacity = floorDim[room.floor].v;
  return l;
}

const GHOST_OPACITY = 0.55;
const ghostLineMat = new THREE.LineBasicMaterial({ color: GHOST_LINE, transparent: true, opacity: GHOST_OPACITY });
const ghostFillMat = new THREE.MeshBasicMaterial({ color: 0x0c2a36, transparent: true, opacity: 0.12, depthWrite: false });

function ghostBox(x0, x1, y0, y1, z0, z1, fill = true, lineMat = ghostLineMat) {
  const geo = new THREE.BoxGeometry(x1 - x0, y1 - y0, z1 - z0);
  const g = new THREE.Group();
  g.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo), lineMat));
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

function disposeGroup(g) {
  g.traverse((o) => { o.geometry?.dispose?.(); o.material?.map?.dispose?.(); o.material?.dispose?.(); });
}

// ---------- colour ramp ----------
// One hue (picked in the UI, remembered per browser); a room's value 0-100 drives it:
// 0 % = dim grey (still visible on the dark background), 100 % = the hue at full saturation and brightness.
const V0 = 0.32;
let hue = 200;
try { hue = Number(localStorage.getItem('hologram.hue')) || 200; } catch { /* storage unavailable */ }

function rampColor(v) {
  const t = Math.min(1, Math.max(0, v / 100));
  const val = V0 + (1 - V0) * t;           // HSV: saturation = t, value = val
  const l = val * (1 - t / 2);             // HSV -> HSL
  const sl = l === 0 || l === 1 ? 0 : (val - l) / Math.min(l, 1 - l);
  return new THREE.Color().setHSL(hue / 360, sl, l, THREE.SRGBColorSpace);
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

// ---------- floor filter: the selected planta stays bright, the others fade ----------
const DIM_OTHER_FLOORS = 0.15;
let floorSel = null; // null = all floors
const floorDim = PLANTES.map(() => ({ v: 1, target: 1 }));                   // eased in animate()
const floorGhostMat = PLANTES.map(() => ghostLineMat.clone());              // corridors and ghost cells of each floor

function setFloor(f) {
  floorSel = f;
  floorDim.forEach((d, i) => { d.target = f === null || f === i ? 1 : DIM_OTHER_FLOORS; });
  document.querySelectorAll('[data-floor]').forEach((b) => b.classList.toggle('on', b.dataset.floor === (f === null ? '' : String(f))));
  for (const r of rooms.values()) document.querySelector(`[data-row="${r.id}"]`)?.classList.toggle('off', f !== null && r.floor !== f);
  document.querySelectorAll('#room-list h3').forEach((h) => h.classList.toggle('off', f !== null && Number(h.dataset.floor) !== f));
}

function build(layout) {
  const G = layout.geometry;
  const gap = 0.35;
  let seed = 0;

  for (const slab of layout.slabs) {
    const floor = PLANTES.indexOf(slab.planta);
    const y0 = floor * G.floorHeight;
    const inSpine = ESPINA_ORDER.includes(slab.espina);
    // Q1-Q4: cells laid along the espina by plan area. Q5, Q6, QC: each room carries its own x/z box.
    let spans = [];
    if (inSpine) {
      const z0 = ESPINA_ORDER.indexOf(slab.espina) * G.pitch;
      const z1 = z0 + G.slabDepth;
      world.add(ghostBox(0, G.slabLength, y0, y0 + 0.25, z1, z1 + G.corridorDepth, false, floorGhostMat[floor]));
      spans = split(slab.rooms.map((r) => r.area), G.slabLength).map(([a, b]) => ({ x: [a, b], z: [z0, z1] }));
    }

    slab.rooms.forEach((r, i) => {
      const { x: [a, b], z: [c, d] } = inSpine ? spans[i] : r;
      if (r.ghost) { world.add(ghostBox(a, b, y0, y0 + G.roomHeight, c, d, false, floorGhostMat[floor])); return; }

      const geo = new THREE.BoxGeometry(b - a - gap, G.roomHeight, d - c - gap);
      const mat = createHologramMaterial(seed++ * 1.7);
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set((a + b) / 2, y0 + G.roomHeight / 2, (c + d) / 2);
      const id = `${slab.espina}-${r.code}`;
      mesh.userData.roomId = id;

      const edgeMat = new THREE.LineBasicMaterial({ color: NEUTRAL.clone(), transparent: true, opacity: 0.75 });
      mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo), edgeMat));
      world.add(mesh);

      const room = {
        id, data: { ...r, espina: slab.espina, planta: slab.planta }, floor, mesh, mat, edgeMat,
        current: NEUTRAL.clone(), target: NEUTRAL.clone(), from: NEUTRAL.clone(), t: 1,
        highlight: 0, highlightTarget: 0,
        value: 0, valueText: '', over: null, // time view: 0-100, label text, over-capacity marker
        width: b - a, labelPos: new THREE.Vector3(mesh.position.x, y0 + G.roomHeight + 1.8, mesh.position.z),
        labelSub: String(r.capacity),
      };
      room.label = roomLabel(room);
      labelGroup.add(room.label);
      rooms.set(id, room);
    });
  }

  for (const e of ESPINA_ORDER) {
    const t = makeLabel(e, { scale: 5, color: '#cfeef5' });
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
    const t = makeLabel(c.name, { scale: 5.3, color: '#5b95a6' });
    t.position.set((c.x[0] + c.x[1]) / 2, c.floors * G.floorHeight + 2.4, (c.z[0] + c.z[1]) / 2);
    labelGroup.add(t);
  }

  const grid = new THREE.GridHelper(260, 52, 0x0b2f3c, 0x07202a);
  grid.position.set(20, -0.1, 50);
  world.add(grid);

  addTrees(G);
}

// ---------- trees (architectural-model style, deliberately muted so they never read as a status colour) ----------
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
function recolor(room, instant = false) {
  const tgt = rampColor(room.value);
  if (!tgt.equals(room.target)) {
    room.from.copy(instant ? tgt : room.current);
    room.target.copy(tgt);
    room.t = instant ? 1 : 0;
    if (instant) room.current.copy(tgt);
  }
  updateRow(room);
}
function recolorAll(instant = false) {
  for (const r of rooms.values()) recolor(r, instant);
  $('counts').textContent = scheduleSummary;
}

// ---------- time views, driven by the session dataset (/api/sessions) ----------
// hour = students per room at that moment (colour = students / capacity; "TOO MANY STUDENTS" over capacity)
// day | week | semester = % of the open time the room has a class (students are irrelevant)
let sched = null;
let scheduleSummary = '';
const view = { scope: 'hour', date: '', min: 630, sem: 1 };
const FALLBACK_WINDOW = { start: 510, end: 1260 };
const overLayer = new THREE.Group();
world.add(overLayer);
const winOf = () => (sched ? sched.window : FALLBACK_WINDOW);

function setLabelSub(room, sub) {
  if (room.labelSub === sub) return;
  room.labelSub = sub;
  labelGroup.remove(room.label);
  disposeGroup(room.label);
  room.label = roomLabel(room);
  labelGroup.add(room.label);
}

function setOver(room, info) {
  const txt = info ? `${info.n} / ${info.cap}` : '';
  if ((room.over?.txt || '') === txt) return;
  if (room.over) { overLayer.remove(room.over.group); disposeGroup(room.over.group); room.over = null; }
  if (!info) return;
  const p = room.mesh.geometry.parameters;
  const mat = new THREE.LineBasicMaterial({ color: OVER_COLOR, transparent: true, opacity: 0.9 });
  const group = new THREE.Group();
  const box = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(p.width + 0.9, p.height + 0.9, p.depth + 0.9)), mat);
  box.position.copy(room.mesh.position);
  const badge = makeLabel('TOO MANY STUDENTS', { sub: txt, scale: 2.6, color: OVER_COLOR });
  badge.position.copy(room.labelPos).add(new THREE.Vector3(0, 3.6, 0));
  group.add(box, badge);
  overLayer.add(group);
  room.over = { group, mat, txt, badge };
}

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
  syncTimeControls();
  if (!sched) {
    for (const room of rooms.values()) { room.value = 0; room.valueText = '–'; setLabelSub(room, '–'); setOver(room, null); }
    $('t-info').textContent = dbError ? `Database: ${dbError}` : 'No sessions with a room of the hologram in the database.';
    scheduleSummary = 'no data';
  } else {
    if (!view.date) {
      view.date = sched.semesters[view.sem]?.start || sched.semesters[1]?.start || '2026-09-07';
      if (isWeekend(view.date)) view.date = addWeekdays(view.date, 1);
      syncTimeControls();
    }
    const caps = new Map([...rooms].map(([id, r]) => [id, r.data.capacity]));
    const res = sched.evaluate(view, caps);
    for (const [id, v] of res.rooms) {
      const room = rooms.get(id);
      room.value = v.value; room.valueText = v.label;
      setLabelSub(room, v.label);
      setOver(room, v.over ? v : null);
    }
    $('t-info').textContent = res.info;
    scheduleSummary = res.summary;
  }
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
const semesterStart = (sem) => sched?.semesters[sem]?.start || view.date;

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
    if (!keys[e.key] || e.altKey || e.ctrlKey || e.metaKey) return;
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
  return canvasSprite(c, lines.length * 1.5 + 0.8, 20);
}

const clip = (t, n) => (t.length > n ? `${t.slice(0, n - 1)}…` : t);
const teachersOf = (t) => (t ? t.split('|').join(', ') : '');

function updateBubble() {
  disposeGroup(bubbleLayer); bubbleLayer.clear();
  for (const r of rooms.values()) if (r.over) r.over.badge.visible = true;
  if (view.scope !== 'hour' || !selected || !sched || !view.date) return;
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
  if (view.scope === 'hour' || !selected || !sched) { box.hidden = true; return; }
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

// ---------- data: everything comes from the DuckDB database through server.py ----------
function setStatus(kind, text) { $('status').className = `pill ${kind}`; $('status').textContent = text; }

async function getJSON(path) {
  const r = await fetch(`api/${path}`, { cache: 'no-store' });
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.errors?.[0] || `HTTP ${r.status}`);
  return r.json();
}

// capacity / type of the rooms, to notice when they change in the database
const roomsKey = (layout) => JSON.stringify(layout.slabs.map((s) => s.rooms.map((r) => [r.code, r.capacity, r.tipus])));
let builtKey = '';
let dbError = '';

async function loadLayout() {
  for (;;) {
    try { return await getJSON('layout'); } catch (e) {
      setStatus('bad', 'waiting for the database');
      $('t-info').textContent = `Cannot load the rooms: ${e.message}`;
      await new Promise((ok) => setTimeout(ok, 3000));
    }
  }
}

async function onStatus(s) {
  dbError = s.error || '';
  if (s.error) setStatus('warn', `DuckDB · ${s.count ? 'last good data' : 'no data'}`);
  else setStatus('ok', `live · DuckDB${s.snapshot ? ' (snapshot, file locked)' : ''}`);
  $('status').title = s.error ? `${s.db}: ${s.error}` : `${s.db} · ${s.count} sessions · version ${s.version}`;
  try {
    if (builtKey && roomsKey(await getJSON('layout')) !== builtKey) { location.reload(); return; } // rooms changed: rebuild
    await loadSessions();
  } catch { applyView(); /* keep what is shown */ }
}

// sessions of the view picked with the version selector (BASE, 5.1..5.4)
let sessionsReq = 0;
async function loadSessions() {
  const req = ++sessionsReq;
  const ds = await getJSON(`sessions?vista=${VERSION_VISTA[version]}`);
  if (req !== sessionsReq) return; // another version was picked meanwhile
  sched = ds ? new Schedule(ds) : null;
  fitViewToData();
  applyView();
}

// Some versions only cover one semester (5.1..5.4: the 2nd): if the date shown is outside the
// data (or there is no date yet), jump to the start of the first semester the version has.
function fitViewToData() {
  if (!sched) return;
  const sems = Object.entries(sched.semesters).sort((a, b) => a[1].start.localeCompare(b[1].start));
  if (!sems.length || sems.some(([, s]) => s.start <= view.date && view.date <= s.end)) return;
  const [sem, s] = sems[0];
  view.sem = Number(sem);
  view.date = isWeekend(s.start) ? addWeekdays(s.start, 1) : s.start;
}

function connect() {
  const es = new EventSource('api/events');
  es.addEventListener('status', (e) => onStatus(JSON.parse(e.data))); // on connect and on every reload of the database
  es.onerror = () => setStatus('bad', 'server not reachable · retrying');
}

// ---------- side panel ----------
function updateRow(room) {
  const row = document.querySelector(`[data-row="${room.id}"]`);
  if (!row) return;
  row.querySelector('.dot').style.background = `#${room.target.getHexString(THREE.SRGBColorSpace)}`;
  const val = row.querySelector('.val');
  val.textContent = room.valueText;
  val.style.color = room.over ? OVER_COLOR : '';
}

function refreshLegend() {
  const stops = [0, 25, 50, 75, 100].map((p) => `#${rampColor(p).getHexString(THREE.SRGBColorSpace)} ${p}%`).join(', ');
  $('legend-bar').style.background = `linear-gradient(90deg, ${stops})`;
  $('hue').value = hue;
  $('hue-n').textContent = `${Math.round(hue)}°`;
}

function buildPanel() {
  const list = $('room-list');
  for (const e of PANEL_ORDER) {
    for (const p of PLANTES) {
      const group = [...rooms.values()].filter((r) => r.data.espina === e && r.data.planta === p);
      if (!group.length) continue;
      const h = el('h3', null, `${e} · planta ${p}`);
      h.dataset.floor = String(PLANTES.indexOf(p));
      list.append(h);
      for (const r of group) {
        const row = el('div', 'row');
        row.dataset.row = r.id;
        row.append(el('span', 'dot'), el('span', 'code', r.id), el('span', 'tag', r.data.tipus), el('span', 'val'), el('span', 'cap', String(r.data.capacity)));
        row.addEventListener('click', () => focusRoom(r.id));
        list.append(row);
      }
    }
  }

  const rainbow = Array.from({ length: 13 }, (_, i) => `hsl(${i * 30} 100% 50%)`).join(', ');
  $('hue').style.background = `linear-gradient(90deg, ${rainbow})`;
  $('hue').addEventListener('input', (ev) => {
    hue = Number(ev.target.value);
    try { localStorage.setItem('hologram.hue', String(hue)); } catch { /* storage unavailable */ }
    refreshLegend();
    recolorAll(true);
  });
  $('btn-labels').addEventListener('click', () => { labelGroup.visible = !labelGroup.visible; });
  document.querySelectorAll('[data-floor]').forEach((b) => b.addEventListener('click', () => {
    setFloor(b.dataset.floor === '' ? null : Number(b.dataset.floor));
  }));
  initTimeControls();
  refreshLegend();

  const origin = location.origin.startsWith('http') ? location.origin : 'http://localhost:8000';
  $('api-example').textContent =
`# data source: dades/paquet.duckdb (reloaded when it changes)
curl ${origin}/api/status

# rooms: geometry + capacity / tipus from 'aules'
curl ${origin}/api/layout

# sessions of the time views, from 'sessions' + 'calendari'
curl ${origin}/api/sessions
curl "${origin}/api/sessions?vista=sessions51"   # versions: ${Object.values(VERSION_VISTA).join(', ')}`;
}

// ---------- focus / pick ----------
let selected = null, focusTarget = null;
function focusRoom(id) {
  if (selected) rooms.get(selected).highlightTarget = 0;
  document.querySelectorAll('.row.sel').forEach((e) => e.classList.remove('sel'));
  selected = id;
  const room = rooms.get(id);
  room.highlightTarget = 1;
  setFloor(room.floor); // focus the room's planta (the others fade)
  focusTarget = room.mesh.position.clone();
  const row = document.querySelector(`[data-row="${id}"]`);
  if (row) { row.classList.add('sel'); row.scrollIntoView({ block: 'nearest' }); }
  updateBubble();
  refreshDetail();
}
function clearSelection() {
  if (selected) rooms.get(selected).highlightTarget = 0;
  selected = null;
  document.querySelectorAll('.row.sel').forEach((e) => e.classList.remove('sel'));
  updateBubble();
  refreshDetail();
}

const ray = new THREE.Raycaster();
let downAt = null;
renderer.domElement.addEventListener('pointerdown', (e) => { downAt = [e.clientX, e.clientY]; });
renderer.domElement.addEventListener('pointerup', (e) => {
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 4) return; // a drag, not a click
  const rect = renderer.domElement.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1), camera);
  const hits = ray.intersectObjects([...rooms.values()].map((r) => r.mesh), false);
  // with a planta focused, a faded room of another floor in front does not steal the click
  const hit = hits.find((h) => rooms.get(h.object.userData.roomId).floor === floorSel) || hits[0];
  if (hit) focusRoom(hit.object.userData.roomId);
  else clearSelection(); // click on empty space: drop the selection (bubble / list)
});

// ---------- loop ----------
const clock = new THREE.Clock();
function animate() {
  const dt = clock.getDelta(), time = clock.elapsedTime;
  const pulse = 0.4 + 0.5 * (0.5 + 0.5 * Math.sin(time * 4));
  floorDim.forEach((d, i) => {
    d.v += (d.target - d.v) * Math.min(1, dt * 6);
    floorGhostMat[i].opacity = GHOST_OPACITY * d.v;
  });
  for (const room of rooms.values()) {
    const dim = floorDim[room.floor].v;
    if (room.t < 1) {
      room.t = Math.min(1, room.t + dt / COLOR_LERP_SECONDS);
      room.current.copy(room.from).lerp(room.target, room.t);
    }
    room.highlight += (room.highlightTarget - room.highlight) * Math.min(1, dt * 8);
    const u = room.mat.uniforms;
    u.uColor.value.copy(room.current);
    u.uTime.value = time;
    u.uHighlight.value = room.highlight;
    u.uDim.value = dim;
    room.edgeMat.color.copy(room.current).multiplyScalar(0.9 + room.highlight * 0.6);
    room.edgeMat.opacity = 0.75 * dim;
    room.label.material.opacity = dim;
    if (room.over) { room.over.mat.opacity = pulse * dim; room.over.badge.material.opacity = dim; }
  }
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
  const layout = await loadLayout();
  builtKey = roomsKey(layout);
  build(layout);
  buildPanel();
  applyView();
  recolorAll(true);
  resize();
  frame();
  animate();
  connect();
})();
