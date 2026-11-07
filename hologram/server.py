#!/usr/bin/env python3
"""Serves the hologram with its data read from the project's DuckDB database.

    python server.py [port] [--db PATH] [--criteri-informe]      (default 8000, ../dades/paquet.duckdb)

  GET /api/layout     layout.json (geometry) with each room's capacity, tipus and descripcio from the 'aules' table
  GET /api/sessions   dataset for the time views, built from the 'sessions' and 'calendari' tables (see schedule.js):
                      {window, semesters, calendar, sessions:[[date,startMin,durMin,roomId,students,labelIdx]],
                       labels:[[className,group,teachers]]}
  GET /api/status     {version, count, snapshot, error, db}
  GET /api/events     Server-Sent Events: "status" (as /api/status) on connect and whenever the data is reloaded

The database file (and its .wal) is watched: when it changes the data is reloaded and pages refresh.
--criteri-informe drops PLAB and double-degree (sense_espai) sessions, as the report does.
Needs the duckdb package (requirements.txt); run it with the project's virtualenv.
"""
import argparse
import json
import os
import queue
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import db

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(ROOT, "..", "dades", "paquet.duckdb")
WATCH_SECONDS = 2

ap = argparse.ArgumentParser(description="Hologram server (data from DuckDB).")
ap.add_argument("port", nargs="?", type=int, default=8000)
ap.add_argument("--db", default=DEFAULT_DB, help="DuckDB file (default: ../dades/paquet.duckdb)")
ap.add_argument("--criteri-informe", action="store_true", help="drop PLAB and double-degree sessions, as the report does")
args = ap.parse_args()
DB_PATH = os.path.abspath(args.db)

with open(os.path.join(ROOT, "layout.json"), encoding="utf-8") as f:
    GEOMETRY = json.load(f)
ROOM_IDS = {f"{s['espina']}-{r['code']}" for s in GEOMETRY["slabs"] for r in s["rooms"] if not r.get("ghost")}

lock = threading.RLock()
clients = []  # one queue per SSE connection
state = {"layout": None, "dataset": None, "version": 0, "snapshot": False, "error": None}


def status():
    d = state["dataset"]
    return {"version": state["version"], "count": len(d["sessions"]) if d else 0, "snapshot": state["snapshot"],
            "error": state["error"], "db": os.path.relpath(DB_PATH, os.path.join(ROOT, ".."))}


def emit(event, payload):
    msg = (event, json.dumps(payload))
    for q in list(clients):
        q.put(msg)


def layout_with(rooms):
    """layout.json plus capacity / tipus / descripcio of every room from the database."""
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
                meta = {"capacity": 0, "tipus": "?", "descripcio": "not in the aules table"}
            r.update(meta)
    return out, missing


def reload():
    try:
        res = db.load(DB_PATH, ROOM_IDS, args.criteri_informe)
    except Exception as e:  # locked copy, missing file, schema change...: keep the last good data
        with lock:
            changed = state["error"] != str(e)
            state["error"] = str(e)
        if changed:
            print(f"database: {e}", file=sys.stderr)
            emit("status", status())
        return
    layout, missing = layout_with(res["rooms"])
    if missing:
        print(f"database: rooms of layout.json missing from 'aules': {', '.join(missing)}", file=sys.stderr)
    with lock:
        state.update(layout=layout, dataset=res["dataset"], snapshot=res["snapshot"], error=None)
        state["version"] += 1
    s = status()
    print(f"database: {s['count']} sessions loaded from {s['db']}{' (snapshot: the file is locked by another process)' if s['snapshot'] else ''}", flush=True)
    emit("status", s)


def watch():
    def stamp():
        return tuple(os.path.getmtime(p) if os.path.exists(p) else None for p in (DB_PATH, DB_PATH + ".wal"))
    last = stamp()
    while True:
        time.sleep(WATCH_SECONDS)
        now = stamp()
        if now != last or state["error"]:
            last = now
            reload()


# ---------- HTTP ----------
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *a):
        if "/api/events" not in (a[0] if a else ""):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % a))

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
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        if parts[:1] != ["api"]:
            return super().do_GET()
        if parts == ["api", "layout"]:
            if state["layout"] is None:
                return self.send_json({"ok": False, "errors": [state["error"] or "database not loaded yet"]}, 503)
            return self.send_json(state["layout"])
        if parts == ["api", "sessions"]:
            return self.send_json(state["dataset"])
        if parts == ["api", "status"]:
            return self.send_json(status())
        if parts == ["api", "events"]:
            return self.sse()
        self.send_json({"ok": False, "errors": ["not found"]}, 404)

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
                    self.wfile.write(f"event: {event}\ndata: {data}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            clients.remove(q)


if __name__ == "__main__":
    reload()
    threading.Thread(target=watch, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    srv.daemon_threads = True
    print(f"Hologram on http://localhost:{args.port}  (data: {DB_PATH})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
