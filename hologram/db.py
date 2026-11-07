"""Reads the hologram data from the project's DuckDB database (dades/paquet.duckdb, built by migra_duckdb.py).

    load(db, room_ids) -> {"rooms":    {"Q3-1007": {"capacity": 130, "tipus": "Aula docent", "descripcio": ...}, ...},
                           "dataset":  session dataset of the time views (shape documented in schedule.js) or None,
                           "snapshot": True when it had to read a copy (see below)}

The database is opened read-only and closed straight away, so other tools can keep writing to it.
DuckDB refuses even a read-only open while another process holds the file (e.g. the duckdb CLI):
then the file (and its .wal) is copied to a temporary folder and the copy is read instead.
"""
import os
import shutil
import tempfile
from contextlib import contextmanager

import duckdb

# aules.tipus -> the short name shown on the room labels
SHORT_TIPUS = {"Aules docents": "Aula docent", "Aules informàtiques": "Informàtica",
               "Laboratoris docents": "Laboratori", "Seminaris": "Seminari"}

# A shared class (id_compartida) is one physical session: its cohorts' students are added.
# Only sessions in a room drawn by the hologram count. Semester by month: Sep-Jan = 1, Feb-Aug = 2.
SESSIONS_SQL = """
WITH s AS (
    SELECT *, coalesce(id_compartida, id_sessio) AS clau, replace(aula_partida, '/', '-') AS room
    FROM sessions
    WHERE aula_partida IS NOT NULL AND list_contains($rooms, replace(aula_partida, '/', '-'))
      AND (NOT $criteri OR (tipus <> 'PLAB' AND NOT coalesce(sense_espai, false)))
)
SELECT strftime(arg_min(data, id_sessio), '%Y-%m-%d')                            AS data,
       CAST(extract(epoch FROM arg_min(h_ini, id_sessio)) / 60 AS INTEGER)       AS ini,
       arg_min(durada_min, id_sessio)                                            AS dur,
       arg_min(room, id_sessio)                                                  AS room,
       CAST(coalesce(sum(alumnes), 0) AS INTEGER)                                AS alumnes,
       array_to_string(list_sort(list_distinct(list(assignatura))), ' + ')       AS assig,
       array_to_string(list_sort(list_distinct(list(grup))), ' + ')              AS grup,
       array_to_string(list_sort(list_distinct(flatten(list(coalesce(docents, []))))), '|') AS docents
FROM s
GROUP BY clau
ORDER BY data, ini, room
"""

SEMESTERS_SQL = """
SELECT CASE WHEN month(data) IN (9, 10, 11, 12, 1) THEN 1 ELSE 2 END AS semestre_n,
       strftime(min(data), '%Y-%m-%d'), strftime(max(data), '%Y-%m-%d')
FROM sessions GROUP BY 1 ORDER BY 1
"""

CALENDAR_SQL = """
SELECT strftime(data, '%Y-%m-%d'), tipus,
       coalesce(left(CAST(h_ini AS VARCHAR), 5), ''), coalesce(left(CAST(h_fi AS VARCHAR), 5), ''), coalesce(motiu, '')
FROM calendari ORDER BY data
"""


@contextmanager
def open_db(path):
    """Yields (connection, snapshot?)."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"database not found: {path}")
    tmp = None
    try:
        try:
            con, snapshot = duckdb.connect(path, read_only=True), False
        except duckdb.IOException as e:
            if "lock" not in str(e).lower():
                raise
            tmp = tempfile.mkdtemp(prefix="hologram-db-")
            copy = os.path.join(tmp, "snapshot.duckdb")
            shutil.copy2(path, copy)
            if os.path.exists(path + ".wal"):
                shutil.copy2(path + ".wal", copy + ".wal")
            con, snapshot = duckdb.connect(copy), True   # read-write: the copy may need its WAL replayed
        with con:
            yield con, snapshot
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def load(path, room_ids, criteri_informe=False):
    with open_db(path) as (con, snapshot):
        aules = con.execute("SELECT aula, tipus, descripcio, capacitat FROM aules").fetchall()
        rows = con.execute(SESSIONS_SQL, {"rooms": sorted(room_ids), "criteri": criteri_informe}).fetchall()
        semesters = {str(sem): {"start": a, "end": b} for sem, a, b in con.execute(SEMESTERS_SQL).fetchall()}
        calendar = [{"date": d, "tipus": t, "h_ini": hi, "h_fi": hf, "motiu": m}
                    for d, t, hi, hf, m in con.execute(CALENDAR_SQL).fetchall()]
    rooms = {aula.replace("/", "-"): {"capacity": cap, "tipus": SHORT_TIPUS.get(tipus, tipus), "descripcio": desc}
             for aula, tipus, desc, cap in aules}
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
