# UAB hologram

3D visualizer of every room of the Escola d'Enginyeria (Edifici Q) inventory (56 rooms: aules docents, aules d'informàtica, laboratoris and seminaris), traced from plans 2600002-2600005 (planta baixa to tercera). It shows the rooms over time (semester / week / day / hour). All the data comes from the project's DuckDB database, `dades/paquet.duckdb` (built by `migra_duckdb.py`): rooms from `aules`, classes from `sessions`, holidays and stoppages from `calendari`.

## Run

```
cd hologram
../.venv/bin/python server.py 8000          # needs duckdb (requirements.txt)
#   --db PATH            another DuckDB file (default ../dades/paquet.duckdb)
#   --criteri-informe    drop PLAB and double-degree sessions, as the report does
```
Open http://localhost:8000. Three.js loads from a CDN.

The server opens the database read-only for a moment on every load, and watches the file (and its `.wal`): when it changes the data is reloaded and open pages refresh by themselves (the whole page when a room's capacity or type changed). If another process holds the file (e.g. the `duckdb` CLI), DuckDB refuses even a read-only open: the server then reads a temporary copy, and the status pill says *snapshot, file locked*. If the database cannot be read at all, the page keeps the last good data and shows the error.

## Time views

| Scope | What a room shows |
|---|---|
| **Hour** (date + time) | students in the room at that moment; colour = students / capacity; a **TOO MANY STUDENTS** badge and pulsing outline when they exceed the capacity |
| **Day / Week / Semester** | % of the open time (window taken from the data, e.g. 08:00-21:00) the room has a class; the number of students does not matter |

Each room label shows its code, its type (Aula docent, Informàtica, Laboratori, Seminari, from `aules.tipus`) and the value of the current view. You pick the hue of the colour ramp in the panel (remembered per browser): 0% is dim grey, 100% is that hue at full saturation and brightness.

Weekends, holidays, non-teaching days and the assessment weeks are excluded from the denominators; partial stoppages ("aturada") only remove their hours. Sessions without a room, or in a room that is not in the hologram, are ignored.

**Click a room** (in 3D or in the list) for its classes: in **Hour** a floating bubble shows the class name, group and professor(s) at that moment (or "free"); in **Day / Week / Semester** a list appears under the room list: day = hours, week = weekday + hours, semester = weekly pattern with the number of occurrences (`×12`). Professors are the pseudonymous ids of the data (`Dnnn`) and belong to the group, not to each session.

Controls: scope buttons, semester select, date and time pickers (type or pick) with step buttons, and the keyboard (when no field has focus): hour `← →` ±30 min, `↑ ↓` ±1 day; day `← →` ±1 day, `↑ ↓` ±1 week; week `← →` ±1 week; semester `← →` switch. The floating **Planta** buttons over the scene (P3-P0 / Totes) keep one floor bright and fade the rooms, labels and corridors of the others (the room list fades them too). Selecting a room focuses its floor; while a floor is focused, a click in 3D prefers its rooms over faded ones in front.

Every session with a room of the hologram counts. A shared class (`id_compartida`) is one physical session; students of its cohorts are added. Semesters come from `sessions.sem` (computed by `migra_duckdb.py`: September-January = 1). `db.py` builds the dataset from the queries in `database/consultes.py`; `schedule.js` holds the time logic and has no browser dependencies.

## Files

The server also serves the other pages of the project, all with the same API:

| Path | Folder | Files |
|---|---|---|
| `/` | `hologram/` | `index.html` (markup only), `hologram.css`, `app.js` (scene + panel), `schedule.js`, `hologram-material.js`, `ornith.css` / `ornith.js` (chatbot) |
| `/home/home.html` | `home/` | `home.html`, `home.css` |
| `/graella/graella.html` | `graella/` | `graella.html` (markup only), `graella.css`, `graella.js` |
| `/comu/` | `comu/` | `comu.css` (colours, buttons, pills, toolbars shared by the hologram and the graella), `nav.js` (database-version and page bars; the version picked is shared by every page) |

## API

Room ID = `<espina>-<code>`, e.g. `Q3-1007` (codes repeat across espines). CORS is open.

Read-only; everything comes from the database.

| Path | Returns |
|---|---|
| `/api/layout` | `layout.json` with `capacity`, `tipus` and `descripcio` of every room from `aules` (`503` until the database has been read once) |
| `/api/sessions?vista=` | the session dataset (below) of a sessions view (`sessions`, `sessions51`..`sessions54`; default `--vista`), or `null` |
| `/api/status` | `{version, count, snapshot, error, db}` |
| `/api/events` | Server-Sent Events: `status` on connect and on every reload |
| `/api/graella/<consulta>` | weekly timetables for the graella: `opcions`, `assignatura?setmana=&codi=[&grup=]`, `aula?setmana=&aula=`, `docent?setmana=&docent=`, `lliures?setmana=` (`setmana` = Monday, `AAAA-MM-DD`; all take `vista=`) |
| `POST /api/ornith` | `{"question": "..."}` → `{"ok": true, "answer": "..."}`: the Ornith chatbot (`test_tools.py`, needs `UTH_KEY` in `.env`) |

Errors are `{"ok": false, "errors": ["..."]}` with a 4xx / 5xx status.

Dataset shape: `{window:{start,end}, semesters:{"1":{start,end}}, calendar:[{date,tipus,h_ini,h_fi,motiu}], sessions:[[date,startMin,durMin,roomId,students,labelIdx]], labels:[[className,group,teachers]]}`.

## Layout

`layout.json` holds only geometry (metres): one entry per room of the `aules` table, ID = `aula` with `/` → `-` (`QC/3115.1` → `QC-3115.1`). Capacity and type are added by the server from the database; a room missing from `aules` is logged and drawn with capacity 0. A new room in `aules` needs its box here to appear.

- **Q1-Q4** (planta baixa, primera): cells along each espina, length proportional to the plan area, same depth. Cells marked `ghost` (Sala de graus, Sala d'estudis, servidors...) are not in the inventory and stay as dim wireframes.
- **Q5, Q6** (Espines 5-6, planta baixa to segona) and **QC** (Cos Central seminaris, planta baixa and tercera): each room has an explicit `x`/`z` box measured on the plans (scale 22.1 m per 284 pt, the espina pitch; origin calibrated per plan on the Q4 walls).
- Floors follow the plans: Q1-Q4 and the service spine have only baixa and primera (roof above), Espines 5-6 reach segona, and only the Cos Central has a tercera. Context volumes outline each floor. Trees are decoration only.

Known mismatches between the plans and the inventory (the inventory wins, IDs are matched by door number):
- Q3 planta baixa: the plan shows 0003 / 0007 / 0011; the inventory splits 0007 into 0007 (lab) + 0009 and 0011 into 0011 + 0013, sized by capacity.
- QC planta baixa: the plan names differ (QC/0015 is 'Despatx + sala tutories', QC/0019 is 'Seminari B'); QC/0036.B is placed on the plan's 'Seminari D'.
- QC/3115.1-.4 are one L-shaped 71 m2 'Espai' on the plan (a 53 m2 room plus a 17.5 m2 annex behind the lift): the room is split in 3 equal parts (.1-.3) and the annex is .4, all ~17.5 m2. The plan does not say which number is which part.
