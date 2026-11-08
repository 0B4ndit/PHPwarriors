"""Bolca el paquet de dades (paquet/) a una base de dades DuckDB.

    python database/migra_duckdb.py [--paquet paquet] [--db dades/paquet.duckdb]   (des de l'arrel del projecte)

La base es reconstrueix de zero cada vegada a partir dels CSV i JSON del paquet, que continuen sent la
font original (el verificador `python -m horaris` els llegeix directament).

Tipus:
  - dates -> DATE, hores HH:MM -> TIME, recomptes -> INTEGER
  - camps 0/1 (`ordinaria`, `sense_espai`) -> BOOLEAN (buit = false)
  - camps amb diversos valors separats per `|` (docents, plans, titulacions_curs...) -> VARCHAR[]
  - codis i identificadors (codi, pla, id_sessio...) es queden com a text

Columnes afegides a `sessions` i `escenari_sessions_extra`: `sem` (semestre per data) i `torn_actual`
(per l'hora d'inici).

En acabar crida crea_vistes.py: les vistes sessions51..54 de les propostes de solver/out/, si ja n'hi ha.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))   # crea_vistes <-> migra_duckdb

ARREL = Path(__file__).resolve().parents[1]   # arrel del projecte (aquest fitxer és a database/)

# Columnes de cada taula i com es converteixen del text del CSV.
# str: text tal qual | int | bool: 0/1 | date: AAAA-MM-DD | date_dmy: DD/MM/AAAA | time: HH:MM | list: a|b|c
SESSIONS = [
    ("id_sessio", "str"), ("activitat_id", "str"), ("id_compartida", "str"), ("codi", "str"),
    ("assignatura", "str"), ("tipus", "str"), ("grup", "str"), ("semestre", "str"), ("data", "date"),
    ("setmana", "str"), ("dia", "str"), ("h_ini", "time"), ("h_fi", "time"), ("durada_min", "int"),
    ("alumnes", "int"), ("capacitat_grup", "int"), ("aula_partida", "str"),
    ("aules_addicionals_partida", "list"), ("plans", "list"), ("titulacions_curs", "list"), ("dc", "str"),
    ("torn_requerit", "str"), ("fixada", "str"), ("docents", "list"), ("alumnes_origen", "str"),
    ("sense_espai", "bool"),
]

TAULES_CSV = {
    "sessions": ("sessions.csv", SESSIONS),
    "aules": ("aules.csv", [
        ("aula", "str"), ("edifici", "str"), ("tipus", "str"), ("descripcio", "str"),
        ("capacitat", "int"), ("ordinaria", "bool"),
    ]),
    "activitats": ("activitats.csv", [
        ("activitat_id", "str"), ("codi", "str"), ("grup", "str"), ("semestre", "str"), ("dia", "str"),
        ("h_ini", "time"), ("h_fi", "time"), ("assignatura", "str"), ("tipus", "str"),
        ("n_sessions", "int"), ("setmana_primera", "str"), ("setmana_ultima", "str"), ("alumnes", "int"),
        ("aules_partida", "list"), ("sessions_sense_aula", "int"), ("titulacions_curs", "list"),
        ("torn_requerit", "str"), ("fixada", "str"), ("docents", "list"), ("sense_espai", "bool"),
    ]),
    "proposta_partida": ("proposta_partida.csv", [
        ("id_sessio", "str"), ("dia", "str"), ("h_ini", "time"), ("aula", "str"),
    ]),
    "plans": ("plans.csv", [
        ("pla", "str"), ("titulacions", "str"), ("descripcio", "str"), ("fitxer_origen", "str"),
        ("data_extraccio", "date_dmy"),
    ]),
    "calendari": ("calendari.csv", [
        ("data", "date"), ("tipus", "str"), ("h_ini", "time"), ("h_fi", "time"), ("motiu", "str"),
        ("font", "str"),
    ]),
}

CLAUS = {  # columnes que han de ser úniques i no buides; es comprova en acabar
    "sessions": "id_sessio", "aules": "aula", "activitats": "activitat_id",
    "proposta_partida": "id_sessio", "plans": "pla", "calendari": "data",
}

TIPUS_SQL = {"str": "VARCHAR", "int": "INTEGER", "bool": "BOOLEAN", "date": "DATE",
             "date_dmy": "DATE", "time": "TIME", "list": "VARCHAR[]"}


def _expr(col: str, kind: str) -> str:
    c = f'"{col}"'
    return {
        "str": c,
        "int": f"CAST({c} AS INTEGER)",
        "bool": f"coalesce(CAST({c} AS INTEGER) = 1, false)",
        "date": f"CAST({c} AS DATE)",
        "date_dmy": f"CAST(strptime({c}, '%d/%m/%Y') AS DATE)",
        "time": f"CAST({c} || ':00' AS TIME)",
        "list": f"string_split({c}, '|')",
    }[kind] + f" AS {c}"


def _select_csv(con: duckdb.DuckDBPyConnection, path: Path, cols: list[tuple[str, str]]) -> str:
    """SELECT que llegeix el CSV com a text i converteix cada columna. Les que el fitxer no té -> NULL."""
    src = f"read_csv('{path.as_posix()}', header=true, all_varchar=true, delim=',', quote='\"')"
    presents = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()}
    falten_al_spec = presents - {c for c, _ in cols}
    if falten_al_spec:
        raise SystemExit(f"{path.name}: columnes no previstes {sorted(falten_al_spec)}; afegiu-les a l'script")
    parts = [_expr(c, k) if c in presents else f'NULL::{TIPUS_SQL[k]} AS "{c}"' for c, k in cols]
    return f"SELECT {', '.join(parts)} FROM {src}"


def carrega_escenaris(con: duckdb.DuckDBPyConnection, dir_esc: Path) -> None:
    con.sql("CREATE TABLE escenaris (nom VARCHAR PRIMARY KEY, ficticia BOOLEAN, descripcio VARCHAR[])")
    con.sql("CREATE TABLE escenari_aules_tancades (escenari VARCHAR, aula VARCHAR, data_ini DATE, data_fi DATE)")
    con.sql("CREATE TABLE escenari_alumnes (escenari VARCHAR, codi VARCHAR, grup VARCHAR, alumnes INTEGER)")
    con.sql("CREATE TABLE escenari_cancellades (escenari VARCHAR, id_sessio VARCHAR, recuperar_fins DATE)")
    extra = []
    for f in sorted(dir_esc.glob("*/escenari.json")):
        e = json.loads(f.read_text(encoding="utf-8"))
        nom = e["nom"]
        desc = e.get("descripcio")
        desc = desc if isinstance(desc, list) else ([desc] if desc else [])
        con.execute("INSERT INTO escenaris VALUES (?, ?, ?)", [nom, e.get("ficticia"), desc])
        for a in e.get("aules_tancades", []):
            con.execute("INSERT INTO escenari_aules_tancades VALUES (?, ?, ?, ?)",
                        [nom, a["aula"], a["data_ini"], a["data_fi"]])
        for a in e.get("alumnes", []):
            con.execute("INSERT INTO escenari_alumnes VALUES (?, ?, ?, ?)",
                        [nom, a["codi"], a["grup"], a["alumnes"]])
        for c in e.get("cancellades", []):
            con.execute("INSERT INTO escenari_cancellades VALUES (?, ?, ?)",
                        [nom, c["id_sessio"], c["recuperar_fins"]])
        if e.get("sessions_extra"):
            extra.append((nom, f.parent / e["sessions_extra"]))
    # sessions extra: mateixes columnes que `sessions` més el nom de l'escenari
    sel = " UNION ALL ".join(f"SELECT '{nom}' AS escenari, * FROM ({_select_csv(con, p, SESSIONS)})"
                             for nom, p in extra)
    if not sel:
        cols = ", ".join(f'NULL::{TIPUS_SQL[k]} AS "{c}"' for c, k in SESSIONS)
        sel = f"SELECT NULL::VARCHAR AS escenari, {cols} WHERE false"
    con.sql(f"CREATE TABLE escenari_sessions_extra AS {sel}")


def afegeix_derivades(con: duckdb.DuckDBPyConnection) -> None:
    """Columnes calculades segons les regles de l'enunciat (apartat 8.3).

    sem         1 o 2 segons la data (1r = setembre a gener). El camp `semestre` de Sigma no és fiable.
    torn_actual 'mati' si la sessió comença abans de les 14.30; si no, 'tarda'. Es compara amb torn_requerit.
    """
    for taula in ("sessions", "escenari_sessions_extra"):
        con.sql(f"ALTER TABLE {taula} ADD COLUMN sem INTEGER")
        con.sql(f"ALTER TABLE {taula} ADD COLUMN torn_actual VARCHAR")
        con.sql(f"""UPDATE {taula} SET
            sem = CASE WHEN month(data) IN (9, 10, 11, 12, 1) THEN 1 ELSE 2 END,
            torn_actual = CASE WHEN h_ini < TIME '14:30' THEN 'mati' ELSE 'tarda' END""")


def migra(paquet: Path, db: Path) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    tmp = db.with_name(db.name + ".tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    try:
        for taula, (fitxer, cols) in TAULES_CSV.items():
            con.sql(f"CREATE TABLE {taula} AS {_select_csv(con, paquet / fitxer, cols)}")

        cob = json.loads((paquet / "cobertura.json").read_text(encoding="utf-8"))
        con.sql("CREATE TABLE cobertura (clau VARCHAR PRIMARY KEY, valor JSON)")
        con.executemany("INSERT INTO cobertura VALUES (?, ?)",
                        [[k, json.dumps(v, ensure_ascii=False)] for k, v in cob.items()])

        carrega_escenaris(con, paquet / "escenaris")
        afegeix_derivades(con)

        from crea_vistes import crea_vistes   # (és a la mateixa carpeta, database/) vistes sessions51..54 de les propostes del solver, si n'hi ha
        vistes = crea_vistes(con, ARREL / "solver" / "out")

        for taula, clau in CLAUS.items():
            n, dist, nuls = con.execute(f"SELECT count(*), count(DISTINCT {clau}), count(*) - count({clau}) "
                                        f"FROM {taula}").fetchone()
            if dist != n or nuls:
                raise SystemExit(f"{taula}.{clau}: {n} files però {dist} valors diferents i {nuls} buits")
    finally:
        con.close()
    os.replace(tmp, db)
    print("Vistes de les propostes (crea_vistes.py):")
    print("\n".join(vistes))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--paquet", type=Path, default=ARREL / "paquet")
    ap.add_argument("--db", type=Path, default=ARREL / "dades" / "paquet.duckdb")
    a = ap.parse_args()
    migra(a.paquet, a.db)
    con = duckdb.connect(str(a.db), read_only=True)
    print(f"Creada {a.db}")
    for (t,) in con.execute("SELECT table_name FROM duckdb_tables() ORDER BY table_name").fetchall():
        print(f"  {t:<26} {con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:>7} files")
    for (v,) in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal ORDER BY 1").fetchall():
        print(f"  {v:<26} {con.execute(f'SELECT count(*) FROM {v}').fetchone()[0]:>7} files (vista)")
    con.close()


if __name__ == "__main__":
    main()
