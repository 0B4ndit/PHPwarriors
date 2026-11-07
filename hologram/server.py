#!/usr/bin/env python3
"""Tiny dependency-free server: serves the hologram and exposes a colour API.

    python server.py [port]        (default 8000)

Two ways to colour rooms (the page shows one at a time, see /api/mode):

  categories : room -> "red" | "green" | "neutral"
      GET    /api/rooms              {"Q3-1007": "red", ...}  (every room, default "neutral")
      GET    /api/rooms/<id>         {"id": "Q3-1007", "color": "red"}
      PUT    /api/rooms/<id>         {"color": "red"}
      POST   /api/rooms              {"Q3-1007": "red", ...}  merge; ?replace=1 resets the rest
      PUT    /api/rooms              {...}                    replace everything
      DELETE /api/rooms              reset all to neutral

  colormap   : room -> percentage 0..100 (default 0 = nothing scheduled). The hue ramp is chosen in the web UI.
      GET    /api/values             {"Q3-1007": 73.5, "Q1-1003": 0, ...}
      GET    /api/values/<id>
      PUT    /api/values/<id>        {"value": 73.5}   (null resets to 0)
      POST   /api/values             {"Q3-1007": 73.5, ...}   merge; ?replace=1 resets the rest to 0
      PUT    /api/values             {...}                    replace everything
      DELETE /api/values             reset all to 0

  GET /api/mode, PUT /api/mode {"mode": "categories" | "colormap"}
  GET /api/layout                    room list [{id, espina, planta, code, capacity}]
  GET /api/events                    Server-Sent Events: "state", "values", "mode"

  GET/PUT/DELETE /api/sessions       dataset for the time views: {window, semesters, calendar, sessions:[[date,startMin,durMin,roomId,students,labelIdx?]], labels:[[className,group,teachers]]}
                                     (SSE event "sessions" {version,count} tells pages to refetch; persisted in sessions-data.json)

State persists in rooms.json (categories) and colormap.json (mode + values); edits to those
files are picked up live.
"""
import json
import os
import queue
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
COLORS_FILE = os.path.join(ROOT, "rooms.json")
CMAP_FILE = os.path.join(ROOT, "colormap.json")
COLORS = ("red", "green", "neutral")
MODES = ("categories", "colormap", "schedule")


def load_rooms():
    with open(os.path.join(ROOT, "layout.json"), encoding="utf-8") as f:
        layout = json.load(f)
    rooms = []
    for slab in layout["slabs"]:
        for r in slab["rooms"]:
            rooms.append({"id": f"{slab['espina']}-{r['code']}", "espina": slab["espina"],
                          "planta": slab["planta"], "code": r["code"], "capacity": r["capacity"]})
    return rooms


ROOMS = load_rooms()
IDS = [r["id"] for r in ROOMS]
lock = threading.RLock()
colors = {i: "neutral" for i in IDS}
values = {i: 0 for i in IDS}   # no session attached = 0 %
mode = ["categories"]          # boxed so handlers can mutate it
clients = []                   # one queue per SSE connection
mtimes = {}

# session dataset for the time views (pushed by nivell1.py): see schedule.js for the shape
DATASET_FILE = os.path.join(ROOT, "sessions-data.json")
dataset = [None]
dataset_version = [0]


# ---------- broadcast / persistence ----------
def emit(event, payload):
    msg = (event, json.dumps(payload))
    for q in list(clients):
        q.put(msg)


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)
    mtimes[path] = os.path.getmtime(path)


def persist_colors():
    write_json(COLORS_FILE, {k: v for k, v in colors.items() if v != "neutral"})


def persist_cmap():
    write_json(CMAP_FILE, {"mode": mode[0], "values": {k: v for k, v in values.items() if v != 0}})


# ---------- validation ----------
def valid_value(v):
    return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100)


def check(incoming, store, ok, hint):
    errors = []
    for k, v in incoming.items():
        if k not in store:
            errors.append(f"unknown room id: {k}")
        elif not ok(v):
            errors.append(f"invalid {hint} for {k}: {v!r}")
    return errors


def apply_colors(incoming, replace=False):
    errors = check(incoming, colors, lambda v: v in COLORS, "color (use red|green|neutral)")
    if errors:
        return False, errors
    with lock:
        before = dict(colors)
        if replace:
            colors.update({k: "neutral" for k in colors})
        colors.update(incoming)
        changed = before != colors
        if changed:
            persist_colors()
    if changed:
        emit("state", dict(colors))
    return changed, []


def apply_values(incoming, replace=False):
    errors = check(incoming, values, valid_value, "value (use a number 0-100; null resets to 0)")
    if errors:
        return False, errors
    incoming = {k: (0 if v is None else v) for k, v in incoming.items()}
    with lock:
        before = dict(values)
        if replace:
            values.update({k: 0 for k in values})
        values.update(incoming)
        changed = before != values
        if changed:
            persist_cmap()
    if changed:
        emit("values", dict(values))
    return changed, []


def apply_mode(m):
    if m not in MODES:
        return False, [f"invalid mode: {m!r} (use categories|colormap|schedule)"]
    with lock:
        changed = mode[0] != m
        mode[0] = m
        if changed:
            persist_cmap()
    if changed:
        emit("mode", {"mode": m})
    return changed, []


# ---------- session dataset (schedule mode) ----------
def check_dataset(d):
    if d is None:
        return []
    if not isinstance(d, dict):
        return ["dataset must be an object or null"]
    errs = []
    w = d.get("window")
    if not (isinstance(w, dict) and all(isinstance(w.get(k), int) for k in ("start", "end")) and w["start"] < w["end"]):
        errs.append("window: need integer minutes {start, end} with start < end")
    ss = d.get("sessions")
    if not isinstance(ss, list):
        return errs + ["sessions must be a list of [date, startMin, durMin, roomId, students]"]
    bad = 0
    for r in ss:
        ok = (isinstance(r, list) and len(r) in (5, 6) and (len(r) == 5 or isinstance(r[5], int))
              and isinstance(r[0], str) and len(r[0]) == 10
              and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (r[1], r[2], r[4]))
              and r[3] in colors)
        if not ok:
            bad += 1
            if bad <= 3:
                errs.append(f"invalid session row: {r!r}")
    if bad > 3:
        errs.append(f"... {bad} invalid rows in total")
    if not isinstance(d.get("calendar", []), list):
        errs.append("calendar must be a list")
    if not isinstance(d.get("semesters", {}), dict):
        errs.append("semesters must be an object")
    if not isinstance(d.get("labels", []), list):
        errs.append("labels must be a list of [className, group, teachers]")
    return errs


def apply_dataset(d):
    errs = check_dataset(d)
    if errs:
        return False, errs
    with lock:
        dataset[0] = d
        dataset_version[0] += 1
        if d is None:
            try:
                os.remove(DATASET_FILE)
            except OSError:
                pass
        else:
            tmp = DATASET_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, separators=(",", ":"))
            os.replace(tmp, DATASET_FILE)
    emit("sessions", dataset_info())
    return True, []


def dataset_info():
    d = dataset[0]
    return {"version": dataset_version[0], "count": len(d["sessions"]) if d else 0}


def load_dataset_file():
    try:
        with open(DATASET_FILE, encoding="utf-8") as f:
            apply_dataset(json.load(f))
    except (OSError, ValueError):
        pass


# ---------- load / watch files ----------
def load_files():
    try:
        with open(COLORS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        clean = {k: v for k, v in data.items() if k in colors and v in COLORS}
        apply_colors(clean, replace=True)
    except (OSError, ValueError, AttributeError):
        pass
    try:
        with open(CMAP_FILE, encoding="utf-8") as f:
            data = json.load(f)
        clean = {k: v for k, v in (data.get("values") or {}).items() if k in values and valid_value(v)}
        apply_values(clean, replace=True)
        apply_mode(data.get("mode", mode[0]))
    except (OSError, ValueError, AttributeError):
        pass
    for p in (COLORS_FILE, CMAP_FILE):
        try:
            mtimes[p] = os.path.getmtime(p)
        except OSError:
            pass


def watch_files():
    while True:
        time.sleep(1)
        for p in (COLORS_FILE, CMAP_FILE):
            try:
                m = os.path.getmtime(p)
            except OSError:
                continue
            if mtimes.get(p) != m:
                mtimes[p] = m
                load_files()
                break


# ---------- HTTP ----------
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        if "/api/events" not in (args[0] if args else ""):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw.decode() or "null")
        except ValueError:
            return ValueError

    def bad(self, errors, status=400):
        self.send_json({"ok": False, "errors": errors if isinstance(errors, list) else [errors]}, status)

    def route(self):
        u = urlparse(self.path)
        return [p for p in u.path.split("/") if p], parse_qs(u.query)


    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parts, _ = self.route()
        if parts[:1] != ["api"]:
            return super().do_GET()
        if parts == ["api", "layout"]:
            return self.send_json(ROOMS)
        if parts == ["api", "rooms"]:
            return self.send_json(dict(colors))
        if parts == ["api", "values"]:
            return self.send_json(dict(values))
        if parts == ["api", "mode"]:
            return self.send_json({"mode": mode[0]})
        if len(parts) == 3 and parts[1] in ("rooms", "values"):
            if parts[2] not in colors:
                return self.bad(f"unknown room id: {parts[2]}", 404)
            if parts[1] == "rooms":
                return self.send_json({"id": parts[2], "color": colors[parts[2]]})
            return self.send_json({"id": parts[2], "value": values[parts[2]]})
        if parts == ["api", "sessions"]:
            return self.send_json(dataset[0])
        if parts == ["api", "events"]:
            return self.sse()
        self.bad("not found", 404)

    def do_PUT(self):
        parts, _ = self.route()
        body = self.read_json()
        if body is ValueError:
            return self.bad("invalid JSON")
        if parts == ["api", "sessions"]:
            changed, errs = apply_dataset(body)
            return self.bad(errs) if errs else self.send_json({"ok": True, **dataset_info()})
        if parts == ["api", "mode"]:
            m = body.get("mode") if isinstance(body, dict) else body
            changed, errs = apply_mode(m)
            return self.bad(errs) if errs else self.send_json({"ok": True, "mode": mode[0], "changed": changed})
        if len(parts) == 3 and parts[1] in ("rooms", "values"):
            rid, kind = parts[2], parts[1]
            if rid not in colors:
                return self.bad(f"unknown room id: {rid}", 404)
            key = "color" if kind == "rooms" else "value"
            v = body.get(key) if isinstance(body, dict) else body
            changed, errs = (apply_colors if kind == "rooms" else apply_values)({rid: v})
            if errs:
                return self.bad(errs)
            return self.send_json({"ok": True, "id": rid, key: (colors if kind == "rooms" else values)[rid], "changed": changed})
        if len(parts) == 2 and parts[1] in ("rooms", "values") and isinstance(body, dict):
            changed, errs = (apply_colors if parts[1] == "rooms" else apply_values)(body, replace=True)
            return self.bad(errs) if errs else self.send_json({"ok": True, "changed": changed})
        self.bad("not found", 404)

    def do_POST(self):
        parts, qs = self.route()
        body = self.read_json()
        if body is ValueError or not isinstance(body, dict):
            return self.bad("body must be a JSON object")
        if len(parts) == 2 and parts[0] == "api" and parts[1] in ("rooms", "values"):
            replace = qs.get("replace", ["0"])[0] in ("1", "true")
            changed, errs = (apply_colors if parts[1] == "rooms" else apply_values)(body, replace=replace)
            return self.bad(errs) if errs else self.send_json({"ok": True, "changed": changed})
        self.bad("not found", 404)

    def do_DELETE(self):
        parts, _ = self.route()
        if parts == ["api", "sessions"]:
            apply_dataset(None)
            return self.send_json({"ok": True})
        if len(parts) == 2 and parts[0] == "api" and parts[1] in ("rooms", "values"):
            changed, _ = (apply_colors if parts[1] == "rooms" else apply_values)({}, replace=True)
            return self.send_json({"ok": True, "changed": changed})
        self.bad("not found", 404)

    def sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = queue.Queue()
        clients.append(q)
        try:
            with lock:
                q.put(("mode", json.dumps({"mode": mode[0]})))
                q.put(("values", json.dumps(values)))
                q.put(("state", json.dumps(colors)))
                if dataset[0]:
                    q.put(("sessions", json.dumps(dataset_info())))
            while True:
                try:
                    event, data = q.get(timeout=15)
                    self.wfile.write(f"event: {event}\ndata: {data}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            clients.remove(q)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    load_files()
    load_dataset_file()
    threading.Thread(target=watch_files, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    srv.daemon_threads = True
    print(f"Hologram on http://localhost:{port}  (API: /api/rooms, /api/values, /api/mode, /api/events)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
