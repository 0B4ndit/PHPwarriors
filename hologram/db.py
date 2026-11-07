"""Reads the hologram data from the project's DuckDB database (dades/paquet.duckdb, built by migra_duckdb.py).

    load(db, room_ids) -> {"rooms":    {"Q3-1007": {"capacity": 130, "tipus": "Aula docent", "descripcio": ...}, ...},
                           "dataset":  session dataset of the time views (shape documented in schedule.js) or None,
                           "snapshot": True when it had to read a copy (see below)}

The queries are in database/consultes.py (shared with the rest of the project). The database is opened read-only and
closed straight away; if another process holds the lock, database.consultes.obrir_db reads a temporary copy instead.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))   # per trobar database/
from database.consultes import (obrir_db, consultar_totes_les_aules, consultar_sessions_holograma,  # noqa: E402
                                consultar_semestres, consultar_calendari, VISTES, VISTA_PER_DEFECTE)

# aules.tipus -> the short name shown on the room labels
SHORT_TIPUS = {"Aules docents": "Aula docent", "Aules informàtiques": "Informàtica",
               "Laboratoris docents": "Laboratori", "Seminaris": "Seminari"}

SESSION_COLS = ("data", "ini", "dur", "room", "alumnes", "assig", "grup", "docents")


def _hhmm(t):
    return t.strftime("%H:%M") if t is not None else ""


def load(path, room_ids, criteri_informe=False, vista=VISTA_PER_DEFECTE):
    """All the queries live in database/consultes.py; `vista` picks the sessions view (sessions, sessions51..54)."""
    with obrir_db(path) as (con, snapshot):
        aules = consultar_totes_les_aules(con=con)
        rows = [tuple(r[c] for c in SESSION_COLS)
                for r in consultar_sessions_holograma(room_ids, criteri_informe, vista=vista, con=con)]
        semesters = {str(r["sem"]): {"start": r["inici"], "end": r["fi"]}
                     for r in consultar_semestres(vista=vista, con=con)}
        calendar = [{"date": r["data"].isoformat(), "tipus": r["tipus"], "h_ini": _hhmm(r["h_ini"]),
                     "h_fi": _hhmm(r["h_fi"]), "motiu": r["motiu"] or ""}
                    for r in consultar_calendari(con=con)]
    rooms = {r["aula"].replace("/", "-"): {"capacity": r["capacitat"], "tipus": SHORT_TIPUS.get(r["tipus"], r["tipus"]),
                                           "descripcio": r["descripcio"]}
             for r in aules}
    return {"rooms": rooms, "dataset": build_dataset(rows, semesters, calendar), "snapshot": snapshot}


def build_dataset(rows, semesters, calendar):
    if not rows:
        return None

    labels, index = [], {}   # [className, group, teachers] table; each session points at one entry

    def label(key):
        if key not in index:
            index[key] = len(labels)
            labels.append(list(key))
        return index[key]

    sessions = [[d, ini, dur, room, n, label((assig, grup, doc))] for d, ini, dur, room, n, assig, grup, doc in rows]
    start = min(r[1] for r in rows) // 30 * 30
    end = -(-max(r[1] + r[2] for r in rows) // 30) * 30   # rounded up to the half hour
    return {"window": {"start": start, "end": end}, "semesters": semesters, "calendar": calendar,
            "sessions": sessions, "labels": labels}
