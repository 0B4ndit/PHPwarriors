# UAB hologram

3D visualizer of the aules docents of the Escola d'Enginyeria (Edifici Q), traced from plans 2600002 (planta baixa) and 2600003 (planta primera). Colors are driven by an HTTP API: no manual controls, the page updates live.

## Run

```
cd hologram
python server.py 8000        # Python 3, standard library only
```
Open http://localhost:8000. Three.js loads from a CDN.

## API

Room ID = `<espina>-<code>`, e.g. `Q3-1007` (codes repeat across espines). Colors: `red`, `green`, `neutral`.

| Method | Path | Body | Effect |
|---|---|---|---|
| GET | `/api/layout` | | list of rooms `{id, espina, planta, code, capacity}` |
| GET | `/api/rooms` | | `{ "Q3-1007": "red", ... }` for every room |
| GET | `/api/rooms/<id>` | | one room |
| PUT | `/api/rooms/<id>` | `{"color":"red"}` | set one room |
| POST | `/api/rooms` | `{"Q3-1007":"red","Q1-1011":"green"}` | merge; `?replace=1` resets unlisted rooms to neutral |
| PUT | `/api/rooms` | map | replace everything |
| DELETE | `/api/rooms` | | reset all to neutral |
| GET | `/api/events` | | Server-Sent Events, event `state` = full map (what the page listens to) |

Requests are validated all-or-nothing: unknown IDs or colors return `400` with `errors` and change nothing. CORS is open, so a scheduling tool can call it from anywhere.

```
curl -X POST localhost:8000/api/rooms -H "Content-Type: application/json" -d '{"Q3-1007":"red","Q1-1011":"green"}'
```

State persists in `rooms.json`; editing that file by hand also updates the page within ~1 s. Without the server (static hosting) the page falls back to polling `rooms.json`. The in-page "Start demo" button drives the API with random colors. The browser console also has `setRoomColor(id, color)` and `setAllRoomColors(map)`.

## Colormap mode

Besides red/green/neutral, each room can carry a percentage (0-100; default 0 = nothing scheduled). The page shows one mode at a time; switch with the Categories / Colormap buttons or via the API. You pick one hue in the web UI (remembered per browser); the percentage drives intensity: 0% is no color (dim grey), 100% is that hue at full saturation and brightness.

| Method | Path | Body |
|---|---|---|
| GET | `/api/values`, `/api/values/<id>` | |
| PUT | `/api/values/<id>` | `{"value": 73.5}` (`null` resets to 0) |
| POST | `/api/values` | `{"Q3-1007": 73.5, ...}` merge; `?replace=1` resets the rest to 0 |
| PUT / DELETE | `/api/values` | replace all / reset all to 0 |
| GET / PUT | `/api/mode` | `{"mode": "categories" \| "colormap"}` |

SSE events: `state` (colors), `values`, `mode`. Values and mode persist in `colormap.json`. Values outside 0-100 are rejected with `400`.

## Time mode (semester / week / day / hour)

Third mode, **Time**, driven by a session dataset that `nivell1.py` pushes (`PUT /api/sessions`). The page does the maths, so stepping through time is instant.

| Scope | What a room shows |
|---|---|
| **Hour** (date + time) | students in the room at that moment; colour = students / capacity; a **TOO MANY STUDENTS** badge and pulsing outline when they exceed the capacity |
| **Day / Week / Semester** | % of the open time (window 08:30-21:00, taken from the data) the room has a class; the number of students does not matter |

Weekends, holidays, non-teaching days and the assessment weeks are excluded from the denominators; partial stoppages ("aturada") only remove their hours. Sessions without a room, or in a room that is not in the hologram, are ignored.

**Click a room** (in 3D or in the list) for its classes: in **Hour** a floating bubble shows the class name, group and professor(s) at that moment (or "free"); in **Day / Week / Semester** a list appears under the room list: day = hours, week = weekday + hours, semester = weekly pattern with the number of occurrences (`×12`). Professors are the pseudonymous ids of the data (`Dnnn`) and belong to the group, not to each session.

Controls: scope buttons, semester select, date and time pickers (type or pick) with step buttons, and the keyboard (when no field has focus): hour `← →` ±30 min, `↑ ↓` ±1 day; day `← →` ±1 day, `↑ ↓` ±1 week; week `← →` ±1 week; semester `← →` switch. The hue picker works here too.

Dataset shape (`GET/PUT/DELETE /api/sessions`, persisted in `sessions-data.json`): `{window:{start,end}, semesters:{"1":{start,end}}, calendar:[{date,tipus,h_ini,h_fi,motiu}], sessions:[[date,startMin,durMin,roomId,students,labelIdx]], labels:[[className,group,teachers]]}`. A shared class (`id_compartida`) is one physical session; students of its cohorts are added. `PUT /api/mode` accepts `schedule`.

From the analysis: `python nivell1.py --hologram http://localhost:8000` (`--mode categories|colormap|schedule` picks the view it leaves on; `--criteri-informe` also drops PLAB and double-degree sessions as the report does). `schedule.js` holds the logic and has no browser dependencies.

## Layout

`layout.json` holds geometry (metres) and the room list (code, capacity, plan area). Rooms in an espina share the same depth and their length is proportional to the plan area. Muted wireframe trees in the courtyards are decoration only. Dim wireframes are the parts of the building that are not aulas docents (Q1/Q2 planta baixa rooms, passadissos, service spine, Cos Central, Espines 5-6).

Known mismatch: the brief lists 4 rooms for Q3 planta baixa (0003/0009/0011/0013) but the plan shows 3 (0003/0007/0011). The brief's IDs are used, sized by capacity.
