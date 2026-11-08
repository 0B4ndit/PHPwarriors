#!/usr/bin/env python3
"""Servidor del holograma, la Home i la Graella. Totes les dades surten de la BD DuckDB (dades/paquet.duckdb).

    python web/server.py [PORT] [--db PATH] [--criteri-informe] [--vista sessions51]   (des de l'arrel del projecte)

Pàgines:   /  (= /hologram.html)  holograma 3D      web/html/hologram.html
           /home.html             portada           web/html/home.html
           /graella.html          graella d'horaris web/html/graella.html
Estàtics:  /css/..., /js/..., /img/...              web/css, web/js, web/img
API:       vegeu web/README.md (GET /api/layout, sessions, status, events, graella/<consulta>; POST /api/ornith)
"""

import argparse
import json
import os
import queue
import sys
import threading
import time
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import db

ROOT = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.dirname(ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database import consultes  # noqa: E402  (després de la línia de sys.path)

DEFAULT_DB = os.path.join(PROJECT_ROOT, "dades", "paquet.duckdb")
WATCH_SECONDS = 2
STATIC_DIRS = ("css", "js", "img")          # carpetes de web/ servides tal qual a /<carpeta>/...
PAGES = {                                   # adreça -> fitxer de web/html/
    "": "hologram.html", "index.html": "hologram.html", "hologram.html": "hologram.html",
    "home.html": "home.html", "graella.html": "graella.html",
    "home/home.html": "home.html", "graella/graella.html": "graella.html",   # adreces antigues
}
ICONA = os.path.join(ROOT, "img", "favicon.svg")   # /favicon.ico, que els navegadors demanen sols
MAX_BODY = 100_000                          # bytes d'una pregunta a Ornith

ap = argparse.ArgumentParser(description="Hologram server (data from DuckDB).")
ap.add_argument("port", nargs="?", type=int, default=8000)
ap.add_argument("--db", default=DEFAULT_DB)
ap.add_argument("--criteri-informe", action="store_true")
ap.add_argument("--vista", default=db.VISTA_PER_DEFECTE, choices=db.VISTES, help="sessions view to read")
args = ap.parse_args()
DB_PATH = os.path.abspath(args.db)

with open(os.path.join(ROOT, "layout.json"), encoding="utf-8") as f:
    GEOMETRY = json.load(f)

ROOM_IDS = {f"{s['espina']}-{r['code']}" for s in GEOMETRY["slabs"] for r in s["rooms"] if not r.get("ghost")}

lock = threading.RLock()
load_lock = threading.Lock()   # una càrrega sota demanda alhora
clients = []                   # cues dels clients SSE connectats
state = {
    "layout": None,
    "dataset": None,
    "version": 0,
    "snapshot": False,
    "error": None,
    "others": {},   # vista -> (version, dataset) de les vistes que no són --vista, carregades sota demanda
}


# ============================================================
# DADES
# ============================================================

def status():
    d = state["dataset"]
    return {
        "version": state["version"],
        "count": len(d["sessions"]) if d else 0,
        "snapshot": state["snapshot"],
        "error": state["error"],
        "db": os.path.relpath(DB_PATH, PROJECT_ROOT),
        "vista": args.vista,
    }


def emit(event, payload):
    msg = (event, json.dumps(payload))
    for q in list(clients):
        q.put(msg)


def layout_with(rooms):
    """layout.json amb capacity / tipus / descripcio de cada aula; retorna (layout, aules que falten a 'aules')."""
    out = json.loads(json.dumps(GEOMETRY))   # còpia profunda
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
        res = db.load(DB_PATH, ROOM_IDS, args.criteri_informe, args.vista)
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
        print("database: rooms missing from 'aules': " + ", ".join(missing), file=sys.stderr)

    with lock:
        state.update(layout=layout, dataset=res["dataset"], snapshot=res["snapshot"], error=None)
        state["version"] += 1
        state["others"] = {}   # la BD ha canviat: les altres vistes es tornen a llegir quan es demanin

    s = status()
    locked = " (snapshot: the file is locked by another process)" if s["snapshot"] else ""
    print(f"database: {s['count']} sessions loaded from {s['db']}{locked}", flush=True)
    emit("status", s)


def dataset_for(vista):
    """Dataset de sessions d'una vista (sessions, sessions51..54).

    --vista és la que carrega (i recarrega) reload(); les altres es llegeixen el primer cop que es demanen
    i es guarden fins que la BD canvia.
    """
    if vista == args.vista:
        return state["dataset"]
    with load_lock:
        with lock:
            version = state["version"]
            cached = state["others"].get(vista)
        if cached and cached[0] == version:
            return cached[1]
        dataset = db.load(DB_PATH, ROOM_IDS, args.criteri_informe, vista)["dataset"]
        with lock:
            if state["version"] == version:   # no s'ha recarregat mentrestant
                state["others"][vista] = (version, dataset)
        print(f"database: view {vista} loaded ({len(dataset['sessions']) if dataset else 0} sessions)", flush=True)
        return dataset


def watch():
    """Recarrega quan el fitxer de la BD (o el seu .wal) canvia, o mentre hi hagi un error."""
    def stamp():
        return tuple(os.path.getmtime(p) if os.path.exists(p) else None for p in (DB_PATH, DB_PATH + ".wal"))

    last = stamp()
    while True:
        time.sleep(WATCH_SECONDS)
        now = stamp()
        if now != last or state["error"]:
            last = now
            reload()


# ============================================================
# HTTP
# ============================================================

# Paràmetres obligatoris de cada consulta de /api/graella/<consulta> (funcions de database/consultes.py).
# setmana = el dilluns de la setmana, AAAA-MM-DD.
GRAELLA = {
    "opcions": ([], lambda q, v, c: consultes.consultar_opcions_graella(v, con=c)),
    "assignatura": (["setmana", "codi"],
                    lambda q, v, c: consultes.consultar_horari_assignatura(q["codi"], q["setmana"], q.get("grup"), v, con=c)),
    "aula": (["setmana", "aula"], lambda q, v, c: consultes.consultar_horari_aula(q["aula"], q["setmana"], v, con=c)),
    "docent": (["setmana", "docent"],
               lambda q, v, c: consultes.consultar_horari_docent(q["docent"], q["setmana"], v, con=c)),
    "lliures": (["setmana"], lambda q, v, c: consultes.consultar_ocupacio_aules(q["setmana"], v, con=c)),
}


class Handler(SimpleHTTPRequestHandler):

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def translate_path(self, path):
        # les pàgines surten de web/html/, i /css, /js, /img de les seves carpetes; la resta (server.py...) no se serveix
        rel = unquote(urlparse(path).path).lstrip("/")
        if rel in PAGES:
            return os.path.join(ROOT, "html", PAGES[rel])
        if rel == "favicon.ico":
            return ICONA
        first = rel.partition("/")[0]
        if first in STATIC_DIRS:
            base = os.path.join(ROOT, first)
            target = os.path.realpath(os.path.join(ROOT, rel))
            if os.path.commonpath([base, target]) == base:   # no surt de la carpeta (../)
                return target
        return os.path.join(ROOT, "html", "no-existeix")     # -> 404

    def log_message(self, fmt, *a):
        if "/api/events" not in str(a[0] if a else ""):
            sys.stderr.write(f"{self.address_string()} - {fmt % a}\n")

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, obj, status_code=200):
        body = json.dumps(obj, default=str).encode()   # default=str: dates / hores de la BD
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def fail(self, message, status_code):
        return self.send_json({"ok": False, "errors": [message]}, status_code)

    def route(self):
        url = urlparse(self.path)
        return [p for p in url.path.split("/") if p], {k: v[0] for k, v in parse_qs(url.query).items()}

    def vista(self, qs):
        """La vista demanada (?vista=), o None si no existeix (i ja s'ha respost 400)."""
        vista = qs.get("vista", args.vista)
        if vista not in db.VISTES:
            self.fail(f"unknown vista {vista!r}; options: {', '.join(db.VISTES)}", 400)
            return None
        return vista

    # ---------- GET: pàgines i API ----------
    def do_GET(self):
        parts, qs = self.route()
        if parts[:1] != ["api"]:
            return super().do_GET()

        if parts == ["api", "layout"]:
            if state["layout"] is None:
                return self.fail(state["error"] or "database not loaded yet", 503)
            return self.send_json(state["layout"])

        if parts == ["api", "sessions"]:
            vista = self.vista(qs)
            if vista is None:
                return None
            try:
                return self.send_json(dataset_for(vista))
            except Exception as e:   # vista que no és a la BD, fitxer bloquejat...
                return self.fail(str(e), 503)

        if parts == ["api", "status"]:
            return self.send_json(status())

        if parts == ["api", "events"]:
            return self.sse()

        if parts[:2] == ["api", "graella"] and len(parts) == 3:
            return self.graella(parts[2], qs)

        return self.fail("not found", 404)

    def graella(self, consulta, qs):
        """GET /api/graella/<consulta>: horaris setmanals de graella.html (consultes de només lectura)."""
        vista = self.vista(qs)
        if vista is None:
            return None
        if consulta not in GRAELLA:
            return self.fail(f"unknown query {consulta!r}; options: {', '.join(GRAELLA)}", 404)
        needs, run = GRAELLA[consulta]
        missing = [p for p in needs if not qs.get(p)]
        if missing:
            return self.fail(f"missing parameter(s): {', '.join(missing)}", 400)
        if "setmana" in qs:
            try:
                date.fromisoformat(qs["setmana"])
            except ValueError:
                return self.fail("setmana must be the Monday of the week, AAAA-MM-DD", 400)
        try:
            with consultes.obrir_db(DB_PATH) as (con, _):
                out = run(qs, vista, con)
            if consulta == "opcions":
                # la franja horària de la graella és la mateixa finestra oberta que fa servir el mapa 3D
                out = {**out, "finestra": (dataset_for(vista) or {}).get("window")}
        except Exception as e:   # vista que no és a la BD, fitxer bloquejat...
            return self.fail(str(e), 503)
        return self.send_json({"ok": True, "vista": vista, **out})

    # ---------- POST /api/ornith: el xatbot ----------
    def do_POST(self):
        parts, _ = self.route()
        if parts != ["api", "ornith"]:
            return self.fail("not found", 404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                return self.fail("Petició buida o massa gran.", 400)
            pregunta = str(json.loads(self.rfile.read(length)).get("question", "")).strip()
            if not pregunta:
                return self.fail("Escriu una pregunta.", 400)

            from ornith.agent import format_text, respon   # aquí: carrega les dades i la clau només quan algú pregunta
            r = respon(pregunta)
            # text: la resposta (markdown) que ornith.js pinta amb les fonts a part; answer: tot en text pla
            return self.send_json({"ok": True, "text": r["answer"], "answer": format_text(r), "estat": r["estat"],
                                   "verificada": r["verificada"], "no_verificades": r["no_verificades"],
                                   "xifres_sense_font": r["xifres_sense_font"], "fonts": r["fonts"], "eines": r["eines"]})
        except Exception as e:
            print(f"Ornith error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            return self.fail(f"{type(e).__name__}: {e}", 500)

    # ---------- Server-Sent Events ----------
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
        except OSError:   # el client ha tancat (BrokenPipeError, ConnectionResetError...)
            pass
        finally:
            clients.remove(q)


if __name__ == "__main__":
    reload()
    threading.Thread(target=watch, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    srv.daemon_threads = True
    print(f"Hologram on http://localhost:{args.port} (data: {DB_PATH})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
