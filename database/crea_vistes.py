"""Crea (o actualitza) les vistes sessions51..sessions54 a partir de les propostes del solver.

    python crea_vistes.py                       # totes les preguntes que tinguin proposta
    python crea_vistes.py 5.2 5.4               # només aquestes
    python crea_vistes.py --proposta 5.2=altra/proposta.csv   # una proposta d'un altre lloc
    python crea_vistes.py [--dir solver/out] [--db dades/paquet.duckdb]

Cada proposta és un CSV `id_sessio,dia,h_ini,aula` (+ `data` a la 5.3, la data de la sessió recuperada), el que
escriu el solver a solver/out/<pregunta>/proposta.csv. Per a cada pregunta:

  - la proposta es desa a la taula `proposta_5X` (es reemplaça cada vegada);
  - la vista `sessions5X` té exactament les columnes de `sessions`, amb les sessions de la proposta i:
        dia, h_ini, aula_partida   els de la proposta (aula buida -> NULL)
        data                       el dia triat dins la mateixa setmana (o la `data` de la proposta, si n'hi ha)
        h_fi                       h_ini + durada_min
        sem, torn_actual           recalculades com a migra_duckdb.py
    i, segons l'escenari de la pregunta (5.3 contingencies, 5.4 grau-nou-40), les sessions extra de l'escenari
    i el nou nombre d'alumnes d'escenari_alumnes.

Com que les vistes llegeixen la taula `proposta_5X`, tornar a executar l'script amb una proposta nova les deixa
al dia. migra_duckdb.py també el crida en acabar, perquè reconstruir la base no les esborri.

La base es modifica sobre una còpia que després substitueix l'original (com fa migra_duckdb.py), de manera que
funciona encara que una altra eina (el holograma, la CLI de duckdb) la tingui oberta.
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

import duckdb

ARREL = Path(__file__).resolve().parent

# pregunta -> (vista, escenari que s'hi aplica)
PREGUNTES = {
    "5.1": ("sessions51", None),
    "5.2": ("sessions52", None),
    "5.3": ("sessions53", "contingencies"),
    "5.4": ("sessions54", "grau-nou-40"),
}

COLS_PROPOSTA = [("id_sessio", "str"), ("dia", "str"), ("h_ini", "time"), ("aula", "str"), ("data", "date")]


def carrega_proposta(con: duckdb.DuckDBPyConnection, taula: str, csv: Path) -> None:
    from migra_duckdb import _select_csv   # mateixa lectura i conversió de tipus que la resta del paquet
    con.sql(f"CREATE OR REPLACE TABLE {taula} AS "
            f"SELECT id_sessio, upper(trim(dia)) AS dia, h_ini, nullif(trim(aula), '') AS aula, data "
            f"FROM ({_select_csv(con, csv, COLS_PROPOSTA)})")


def sql_vista(taula_proposta: str, escenari: str | None) -> str:
    extra = (f"UNION ALL BY NAME SELECT * EXCLUDE (escenari) FROM escenari_sessions_extra "
             f"WHERE escenari = '{escenari}'") if escenari else ""
    alumnes = (f"LEFT JOIN escenari_alumnes ea ON ea.escenari = '{escenari}' AND ea.codi = b.codi "
               f"AND ea.grup = b.grup") if escenari else "LEFT JOIN (SELECT NULL::INTEGER AS alumnes) ea ON false"
    return f"""
        WITH base AS (
            SELECT * FROM sessions {extra}
        ), nou AS (
            SELECT b.*,
                   p.dia AS p_dia, p.h_ini AS p_h_ini, p.aula AS p_aula, ea.alumnes AS p_alumnes,
                   coalesce(p.data, b.data + CAST(list_position(['L', 'M', 'X', 'J', 'V'], p.dia)
                                                  - isodow(b.data) AS INTEGER)) AS p_data
            FROM base b
            JOIN {taula_proposta} p USING (id_sessio)
            {alumnes}
        )
        SELECT * EXCLUDE (p_dia, p_h_ini, p_aula, p_alumnes, p_data) REPLACE (
            p_data                                                      AS data,
            p_dia                                                       AS dia,
            p_h_ini                                                     AS h_ini,
            p_h_ini + to_minutes(durada_min)                            AS h_fi,
            coalesce(p_alumnes, alumnes)                                AS alumnes,
            p_aula                                                      AS aula_partida,
            CASE WHEN month(p_data) IN (9, 10, 11, 12, 1) THEN 1 ELSE 2 END AS sem,
            CASE WHEN p_h_ini < TIME '14:30' THEN 'mati' ELSE 'tarda' END    AS torn_actual
        )
        FROM nou
    """


def crea_vista(con: duckdb.DuckDBPyConnection, pregunta: str, csv: Path) -> str:
    vista, escenari = PREGUNTES[pregunta]
    taula = "proposta_" + vista.removeprefix("sessions")
    carrega_proposta(con, taula, csv)
    con.sql(f"CREATE OR REPLACE VIEW {vista} AS {sql_vista(taula, escenari)}")

    n_prop = con.execute(f"SELECT count(*) FROM {taula}").fetchone()[0]
    n_vista = con.execute(f"SELECT count(*) FROM {vista}").fetchone()[0]
    dies = con.execute(f"SELECT count(*) FROM {taula} WHERE dia NOT IN ('L', 'M', 'X', 'J', 'V')").fetchone()[0]
    msg = f"  {vista:<11} {n_vista:>6} sessions  ({csv})"
    if n_prop != n_vista:
        msg += f"\n              atenció: {n_prop - n_vista} files de la proposta no són a sessions{" ni a l'escenari" if escenari else ""}"
    if dies:
        msg += f"\n              atenció: {dies} files amb un dia que no és L M X J V"
    return msg


def crea_vistes(con: duckdb.DuckDBPyConnection, dir_out: Path, preguntes=None, propostes=None) -> list[str]:
    """Crea les vistes de les preguntes que tenen proposta. Retorna les línies del resum."""
    propostes = dict(propostes or {})
    linies = []
    for p in preguntes or PREGUNTES:
        csv = propostes.get(p, dir_out / p / "proposta.csv")
        if not csv.exists():
            linies.append(f"  {PREGUNTES[p][0]:<11} sense proposta ({csv}): no es crea")
            continue
        linies.append(crea_vista(con, p, csv))
    return linies


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("preguntes", nargs="*", metavar="PREGUNTA",
                    help=f"preguntes a actualitzar ({', '.join(PREGUNTES)}); per defecte totes")
    ap.add_argument("--dir", type=Path, default=ARREL / "solver" / "out", help="carpeta out/ del solver")
    ap.add_argument("--db", type=Path, default=ARREL / "dades" / "paquet.duckdb")
    ap.add_argument("--proposta", action="append", default=[], metavar="PREGUNTA=CSV",
                    help="fes servir aquest CSV per a la pregunta (es pot repetir)")
    a = ap.parse_args()

    for p in a.preguntes:
        if p not in PREGUNTES:
            ap.error(f"pregunta desconeguda: {p!r}; opcions: {', '.join(PREGUNTES)}")
    propostes = {}
    for x in a.proposta:
        p, _, f = x.partition("=")
        if p not in PREGUNTES or not f:
            ap.error(f"--proposta {x!r}: ha de ser PREGUNTA=CSV, amb PREGUNTA a {', '.join(PREGUNTES)}")
        propostes[p] = Path(f)
    preguntes = a.preguntes or (list(propostes) if propostes else None)

    if not a.db.exists():
        raise SystemExit(f"no es troba {a.db}: executeu abans python migra_duckdb.py")
    tmp = a.db.with_name(a.db.name + ".tmp")
    shutil.copy2(a.db, tmp)
    if a.db.with_name(a.db.name + ".wal").exists():
        shutil.copy2(a.db.with_name(a.db.name + ".wal"), tmp.with_name(tmp.name + ".wal"))
    try:
        con = duckdb.connect(str(tmp))
        try:
            linies = crea_vistes(con, a.dir, preguntes, propostes)
            con.execute("CHECKPOINT")
        finally:
            con.close()
        os.replace(tmp, a.db)
    finally:
        tmp.unlink(missing_ok=True)
        tmp.with_name(tmp.name + ".wal").unlink(missing_ok=True)
    print(f"Vistes a {a.db}")
    print("\n".join(linies))


if __name__ == "__main__":
    main()
