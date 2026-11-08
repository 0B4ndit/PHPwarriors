
#!/usr/bin/env python3
"""Hologram server with Home and Graella pages."""

import argparse
import json
import os
import queue
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, unquote

import db

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ROOT)

DEFAULT_DB = os.path.join(ROOT, "..", "dades", "paquet.duckdb")
WATCH_SECONDS = 2

ap = argparse.ArgumentParser(description="Hologram server (data from DuckDB).")
ap.add_argument("port", nargs="?", type=int, default=8000)
ap.add_argument("--db", default=DEFAULT_DB)
ap.add_argument("--criteri-informe", action="store_true")
ap.add_argument(
    "--vista",
    default=db.VISTA_PER_DEFECTE,
    choices=db.VISTES,
    help="sessions view to read"
)
args = ap.parse_args()
DB_PATH = os.path.abspath(args.db)

with open(os.path.join(ROOT, "layout.json"), encoding="utf-8") as f:
    GEOMETRY = json.load(f)

ROOM_IDS = {
    f"{s['espina']}-{r['code']}"
    for s in GEOMETRY["slabs"]
    for r in s["rooms"]
    if not r.get("ghost")
}

lock = threading.RLock()
clients = []

state = {
    "layout": None,
    "dataset": None,
    "version": 0,
    "snapshot": False,
    "error": None,
    "others": {}   # vista -> (version, dataset) for the views other than --vista, loaded on demand
}
load_lock = threading.Lock()   # one on-demand load at a time


def status():
    d = state["dataset"]
    return {
        "version": state["version"],
        "count": len(d["sessions"]) if d else 0,
        "snapshot": state["snapshot"],
        "error": state["error"],
        "db": os.path.relpath(DB_PATH, PROJECT_ROOT),
        "vista": args.vista
    }


def emit(event, payload):
    msg = (event, json.dumps(payload))
    for q in list(clients):
        q.put(msg)


def layout_with(rooms):
    out = json.loads(json.dumps(GEOMETRY))
    missing = []

    for slab in out["slabs"]:
        for r in slab["rooms"]:
            if r.get("ghost"):
                continue

            rid = f"{slab['espina']}-{r['code']}"
            meta = rooms.get(rid)

            if meta is None:
                missing.append(rid)
                meta = {
                    "capacity": 0,
                    "tipus": "?",
                    "descripcio": "not in the aules table"
                }

            r.update(meta)

    return out, missing


def reload():
    try:
        res = db.load(
            DB_PATH,
            ROOM_IDS,
            args.criteri_informe,
            args.vista
        )
    except Exception as e:
        with lock:
            changed = state["error"] != str(e)
            state["error"] = str(e)

        if changed:
            print(f"database: {e}", file=sys.stderr)
            emit("status", status())

        return

    layout, missing = layout_with(res["rooms"])

    if missing:
        print(
            "database: rooms missing from 'aules': "
            + ", ".join(missing),
            file=sys.stderr
        )

    with lock:
        state.update(
            layout=layout,
            dataset=res["dataset"],
            snapshot=res["snapshot"],
            error=None
        )
        state["version"] += 1
        state["others"] = {}   # the database changed: the other views are read again when asked for

    s = status()

    print(
        f"database: {s['count']} sessions loaded from {s['db']}"
        + (
            " (snapshot: the file is locked by another process)"
            if s["snapshot"] else ""
        ),
        flush=True
    )

    emit("status", s)


def dataset_for(vista):
    """Sessions dataset of a view (sessions, sessions51..54).

    --vista is the one loaded (and reloaded) by reload(); the others are read the first time
    they are asked for and kept until the database changes.
    """
    if vista == args.vista:
        return state["dataset"]
    with load_lock:
        with lock:
            version = state["version"]
            cached = state["others"].get(vista)
        if cached and cached[0] == version:
            return cached[1]
        res = db.load(DB_PATH, ROOM_IDS, args.criteri_informe, vista)
        with lock:
            if state["version"] == version:   # not reloaded meanwhile
                state["others"][vista] = (version, res["dataset"])
        print(f"database: view {vista} loaded ({len(res['dataset']['sessions']) if res['dataset'] else 0} sessions)", flush=True)
        return res["dataset"]


def watch():
    def stamp():
        return tuple(
            os.path.getmtime(p) if os.path.exists(p) else None
            for p in (DB_PATH, DB_PATH + ".wal")
        )

    last = stamp()

    while True:
        time.sleep(WATCH_SECONDS)
        now = stamp()

        if now != last or state["error"]:
            last = now
            reload()


class Handler(SimpleHTTPRequestHandler):

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def translate_path(self, path):
        url_path = unquote(urlparse(path).path)

        # Pàgina Home i els seus recursos
        if url_path == "/home" or url_path.startswith("/home/"):
            base = os.path.realpath(
                os.path.join(PROJECT_ROOT, "home")
            )
            relative = url_path[len("/home"):].lstrip("/")
            target = os.path.realpath(
                os.path.join(base, relative)
            )

            if os.path.commonpath([base, target]) == base:
                return target

        # Pàgina Graella i els seus recursos
        if url_path == "/graella" or url_path.startswith("/graella/"):
            base = os.path.realpath(
                os.path.join(PROJECT_ROOT, "graella")
            )
            relative = url_path[len("/graella"):].lstrip("/")
            target = os.path.realpath(
                os.path.join(base, relative)
            )

            if os.path.commonpath([base, target]) == base:
                return target

        # La resta de fitxers es serveixen des de Hologram
        return super().translate_path(path)

    def log_message(self, fmt, *a):
        if "/api/events" not in str(a[0] if a else ""):
            sys.stderr.write(
                "%s - %s\n" % (self.address_string(), fmt % a)
            )

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, obj, status_code=200):
        body = json.dumps(obj).encode()

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parts = [
            p for p in urlparse(self.path).path.split("/") if p
        ]

        if parts[:1] != ["api"]:
            return super().do_GET()

        if parts == ["api", "layout"]:
            if state["layout"] is None:
                return self.send_json({
                    "ok": False,
                    "errors": [
                        state["error"] or "database not loaded yet"
                    ]
                }, 503)

            return self.send_json(state["layout"])

        if parts == ["api", "sessions"]:
            qs = parse_qs(urlparse(self.path).query)
            vista = qs.get("vista", [args.vista])[0]
            if vista not in db.VISTES:
                return self.send_json({
                    "ok": False,
                    "errors": [f"unknown vista {vista!r}; options: {', '.join(db.VISTES)}"]
                }, 400)
            try:
                return self.send_json(dataset_for(vista))
            except Exception as e:   # view missing from the database, file locked...
                return self.send_json({"ok": False, "errors": [str(e)]}, 503)

        if parts == ["api", "status"]:
            return self.send_json(status())

        if parts == ["api", "events"]:
            return self.sse()

        self.send_json({
            "ok": False,
            "errors": ["not found"]
        }, 404)

    def sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        q = queue.Queue()
        clients.append(q)

        try:
            q.put(("status", json.dumps(status())))

            while True:
                try:
                    event, data = q.get(timeout=15)
                    self.wfile.write(
                        f"event: {event}\ndata: {data}\n\n".encode()
                    )
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")

                self.wfile.flush()

        except (
            BrokenPipeError,
            ConnectionResetError,
            OSError
        ):
            pass

        finally:
            clients.remove(q)


if __name__ == "__main__":
    reload()

    threading.Thread(
        target=watch,
        daemon=True
    ).start()

    srv = ThreadingHTTPServer(
        ("0.0.0.0", args.port),
        Handler
    )

    srv.daemon_threads = True

    print(
        f"Hologram on http://localhost:{args.port} "
        f"(data: {DB_PATH})",
        flush=True
    )

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass

