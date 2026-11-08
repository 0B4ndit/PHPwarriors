"""Totes les consultes a la base de dades (dades/paquet.duckdb, la genera migra_duckdb.py).

Les consultes sobre sessions reben el paràmetre `vista`, que diu de quina vista de sessions es llegeix:

    "sessions"                            la taula amb totes les sessions (per defecte)
    "sessions51" ... "sessions54"         vistes amb la mateixa estructura que `sessions`

Si la vista encara no existeix a la BD, la consulta falla (duckdb.CatalogException).

Cada funció accepta també `con`: si se li passa una connexió oberta (amb `obrir_db()`), la reutilitza;
si no, n'obre una de només lectura i la tanca en acabar.

    from database.consultes import consultar_sessio, obrir_db
    consultar_sessio("S00001")                       # taula sessions
    consultar_sessio("S00001", vista="sessions51")   # vista sessions51
    with obrir_db() as (con, _):                     # diverses consultes amb una sola connexió
        sessions = consultar_sessions(vista="sessions52", con=con)
        aules = consultar_totes_les_aules(con=con)
"""
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import duckdb

PROJECTE = Path(__file__).resolve().parent.parent
DB_PATH = PROJECTE / "dades" / "paquet.duckdb"

# Vistes de sessions que es poden consultar (totes amb les columnes de `sessions`).
VISTES = ("sessions", "sessions51", "sessions52", "sessions53", "sessions54")
VISTA_PER_DEFECTE = "sessions"


def taula_vista(vista=VISTA_PER_DEFECTE):
    """Comprova el nom de la vista. Només deixa passar les de VISTES (el nom va dins l'SQL, no pot ser lliure)."""
    if vista not in VISTES:
        raise ValueError(f"vista desconeguda: {vista!r}; opcions: {', '.join(VISTES)}")
    return vista


# ============================================================
# CONNEXIÓ
# ============================================================

def connectar(db_path=None):
    """Obre una connexió de només lectura. Qui la crida l'ha de tancar."""
    return duckdb.connect(str(db_path or DB_PATH), read_only=True)


@contextmanager
def obrir_db(db_path=None):
    """Dona (connexió, snapshot?) i la tanca en acabar.

    DuckDB no deixa obrir el fitxer, ni en només lectura, mentre un altre procés el té bloquejat (p. ex. la
    CLI de duckdb): llavors es copia el fitxer (i el .wal) a una carpeta temporal i es llegeix la còpia.
    """
    path = str(db_path or DB_PATH)
    if not os.path.exists(path):
        raise FileNotFoundError(f"no es troba la base de dades: {path}")
    tmp = None
    try:
        try:
            con, snapshot = duckdb.connect(path, read_only=True), False
        except duckdb.IOException as e:
            if "lock" not in str(e).lower():
                raise
            tmp = tempfile.mkdtemp(prefix="paquet-db-")
            copia = os.path.join(tmp, "snapshot.duckdb")
            shutil.copy2(path, copia)
            if os.path.exists(path + ".wal"):
                shutil.copy2(path + ".wal", copia + ".wal")
            con, snapshot = duckdb.connect(copia), True   # lectura-escriptura: la còpia pot haver de reproduir el WAL
        with con:
            yield con, snapshot
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


@contextmanager
def _con(con):
    if con is not None:
        yield con
    else:
        with obrir_db() as (c, _):
            yield c


def _files(con, sql, params=None):
    """Executa la consulta i retorna una llista de dicts {columna: valor}."""
    res = con.execute(sql, params or [])
    columnes = [c[0] for c in res.description]
    return [dict(zip(columnes, fila)) for fila in res.fetchall()]


def _una(con, sql, params=None):
    files = _files(con, sql, params)
    return files[0] if files else None


# ============================================================
# SESSIONS (depenen de la vista)
# ============================================================

def consultar_sessio(id_sessio, vista=VISTA_PER_DEFECTE, con=None):
    """Una sessió amb l'aula que li assigna la proposta de partida."""
    with _con(con) as c:
        r = _una(c, f"""
            SELECT s.id_sessio, s.activitat_id, s.codi, s.assignatura, s.tipus, s.grup, s.semestre,
                   s.data, s.dia, s.h_ini, s.h_fi, s.durada_min, s.alumnes, s.aula_partida,
                   s.torn_requerit, s.fixada, s.docents, s.sense_espai,
                   p.aula AS aula_assignada
            FROM {taula_vista(vista)} s
            LEFT JOIN proposta_partida p ON s.id_sessio = p.id_sessio
            WHERE s.id_sessio = ?
        """, [id_sessio])
    return r if r is not None else {"error": "Sessió no trobada."}


def consultar_sessions(vista=VISTA_PER_DEFECTE, con=None):
    """Totes les sessions de la vista, amb totes les columnes, per id."""
    with _con(con) as c:
        return _files(c, f"SELECT * FROM {taula_vista(vista)} ORDER BY id_sessio")


def consultar_proposta(vista=VISTA_PER_DEFECTE, con=None):
    """Files de la proposta de partida de les sessions de la vista."""
    with _con(con) as c:
        return _files(c, f"""
            SELECT id_sessio, dia, h_ini, aula
            FROM proposta_partida
            WHERE id_sessio IN (SELECT id_sessio FROM {taula_vista(vista)})
            ORDER BY id_sessio
        """)


def consultar_semestres(vista=VISTA_PER_DEFECTE, con=None):
    """[{sem, inici, fi}] amb les dates 'AAAA-MM-DD'. `sem` el calcula migra_duckdb.py per la data."""
    with _con(con) as c:
        return _files(c, f"""
            SELECT sem, strftime(min(data), '%Y-%m-%d') AS inici, strftime(max(data), '%Y-%m-%d') AS fi
            FROM {taula_vista(vista)} GROUP BY sem ORDER BY sem
        """)


def consultar_sessions_holograma(aules, criteri_informe=False, vista=VISTA_PER_DEFECTE, con=None):
    """Sessions per al holograma: només les d'aules de la llista `aules` (format 'Q1-1011').

    Una classe compartida (id_compartida) és una sola sessió física: se sumen els alumnes de les cohorts.
    Amb `criteri_informe` es descarten les PLAB i les de doble titulació sense espai, com fa l'informe.
    Retorna dicts amb data ('AAAA-MM-DD'), ini (minuts), dur, room, alumnes, assig, grup, docents ('a|b').
    """
    with _con(con) as c:
        return _files(c, f"""
            WITH s AS (
                SELECT *, coalesce(id_compartida, id_sessio) AS clau, replace(aula_partida, '/', '-') AS room
                FROM {taula_vista(vista)}
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
        """, {"rooms": sorted(aules), "criteri": bool(criteri_informe)})


# ============================================================
# AULES I CALENDARI (no depenen de la vista)
# ============================================================

def consultar_aula(nom_aula, con=None):
    """Característiques d'una aula del catàleg."""
    with _con(con) as c:
        r = _una(c, "SELECT * FROM aules WHERE aula = ?", [nom_aula])
    return r if r is not None else {"error": "Aula no trobada al catàleg."}


def consultar_totes_les_aules(con=None):
    """Totes les aules del catàleg, per nom."""
    with _con(con) as c:
        return _files(c, "SELECT * FROM aules ORDER BY aula")


def consultar_calendari(con=None):
    """Dies del calendari oficial (festius, aturades...) per data. h_ini NULL = tot el dia."""
    with _con(con) as c:
        return _files(c, "SELECT * FROM calendari ORDER BY data")


# ============================================================
# GRAELLA (horaris setmanals: assignatura, aula, docent i aules lliures)
# ============================================================
# Totes són SELECT. Les setmanes s'identifiquen pel dilluns ('AAAA-MM-DD'); les hores van en minuts des de
# mitjanit (ini, fi). Una classe compartida (id_compartida) es mostra un sol cop, amb tots els grups, si les
# seves sessions coincideixen en data, hora i aula (a les propostes 5.x no sempre és així).

def _sessions_graella(c, vista, dilluns, filtre, params):
    """Sessions de la setmana que compleixen `filtre` (SQL sobre les columnes de la vista), agrupades."""
    return _files(c, f"""
        WITH v AS (
            SELECT *, coalesce(id_compartida, id_sessio) AS clau
            FROM {taula_vista(vista)}
            WHERE CAST(date_trunc('week', data) AS DATE) = CAST($dilluns AS DATE)
        ), sel AS (
            SELECT DISTINCT clau FROM v WHERE {filtre}
        )
        SELECT min(id_sessio)                                                              AS id,
               strftime(data, '%Y-%m-%d')                                                  AS data,
               any_value(dia)                                                              AS dia,
               CAST(extract(epoch FROM h_ini) / 60 AS INTEGER)                             AS ini,
               CAST(extract(epoch FROM h_fi) / 60 AS INTEGER)                              AS fi,
               list_sort(list_distinct(list(codi)))                                        AS codis,
               array_to_string(list_sort(list_distinct(list(assignatura))), ' + ')         AS assignatura,
               list_sort(list_distinct(list(grup)))                                        AS grups,
               array_to_string(list_sort(list_distinct(list(tipus))), '+')                 AS tipus,
               list_sort(list_distinct(flatten(list(coalesce(docents, [])))))              AS docents,
               aula_partida                                                                AS aula,
               list_sort(list_distinct(flatten(list(coalesce(aules_addicionals_partida, []))))) AS aules_extra,
               CAST(coalesce(sum(alumnes), 0) AS INTEGER)                                  AS alumnes,
               list_sort(list_distinct(flatten(list(coalesce(titulacions_curs, [])))))     AS titulacions
        FROM v JOIN sel USING (clau)
        GROUP BY clau, data, h_ini, h_fi, aula_partida
        ORDER BY data, ini, aula NULLS LAST, id
    """, {"dilluns": dilluns, **params})


def _calendari_setmana(c, dilluns):
    """Festius, aturades i altres dies especials de la setmana (dl-dv)."""
    return _files(c, """
        SELECT strftime(data, '%Y-%m-%d') AS data, tipus, motiu,
               CAST(extract(epoch FROM h_ini) / 60 AS INTEGER) AS ini,
               CAST(extract(epoch FROM h_fi) / 60 AS INTEGER)  AS fi
        FROM calendari
        WHERE data BETWEEN CAST($dilluns AS DATE) AND CAST($dilluns AS DATE) + 4
        ORDER BY data, ini NULLS FIRST
    """, {"dilluns": dilluns})


def consultar_opcions_graella(vista=VISTA_PER_DEFECTE, con=None):
    """Llistes per als filtres de la graella: setmanes, assignatures, aules i docents de la vista."""
    with _con(con) as c:
        t = taula_vista(vista)
        setmanes = _files(c, f"""
            SELECT strftime(date_trunc('week', data), '%Y-%m-%d') AS dilluns,
                   any_value(setmana) AS setmana, min(sem) AS sem, count(*) AS n
            FROM {t} GROUP BY 1 ORDER BY 1
        """)
        assignatures = _files(c, f"""
            SELECT codi, any_value(assignatura) AS assignatura,
                   list_sort(list_distinct(list(grup)))                                    AS grups,
                   list_sort(list_distinct(list(sem)))                                     AS sems,
                   list_sort(list_distinct(flatten(list(coalesce(titulacions_curs, []))))) AS titulacions,
                   list_sort(list_distinct(list(strftime(date_trunc('week', data), '%Y-%m-%d')))) AS setmanes,
                   count(*) AS n
            FROM {t} GROUP BY codi ORDER BY assignatura, codi
        """)
        aules = _files(c, f"""
            WITH us AS (
                SELECT a AS aula, count(*) AS n
                FROM (SELECT unnest(list_prepend(aula_partida, coalesce(aules_addicionals_partida, []))) AS a
                      FROM {t} WHERE aula_partida IS NOT NULL)
                GROUP BY a
            )
            SELECT coalesce(a.aula, us.aula) AS aula, a.tipus, a.descripcio, a.capacitat,
                   a.aula IS NOT NULL AS cataleg, coalesce(us.n, 0) AS n
            FROM aules a FULL JOIN us ON us.aula = a.aula
            ORDER BY cataleg DESC, aula
        """)
        docents = _files(c, f"""
            SELECT d AS docent, count(*) AS n,
                   list_sort(list_distinct(list(assignatura)))[1:3] AS assignatures,
                   count(DISTINCT codi) AS n_assignatures,
                   list_sort(list_distinct(list(strftime(date_trunc('week', data), '%Y-%m-%d')))) AS setmanes
            FROM (SELECT unnest(docents) AS d, assignatura, codi, data FROM {t})
            GROUP BY d ORDER BY d
        """)
    return {"setmanes": setmanes, "assignatures": assignatures, "aules": aules, "docents": docents}


def consultar_horari_assignatura(codi, dilluns, grup=None, vista=VISTA_PER_DEFECTE, con=None):
    """Sessions d'una assignatura (i, si es dona, d'un grup) la setmana del dilluns `dilluns`."""
    with _con(con) as c:
        return {"sessions": _sessions_graella(c, vista, dilluns, "codi = $codi AND ($grup IS NULL OR grup = $grup)",
                                              {"codi": codi, "grup": grup or None}),
                "calendari": _calendari_setmana(c, dilluns)}


def consultar_horari_aula(aula, dilluns, vista=VISTA_PER_DEFECTE, con=None):
    """Sessions que ocupen una aula (com a aula principal o addicional) la setmana del dilluns `dilluns`."""
    with _con(con) as c:
        return {"aula": _una(c, "SELECT * FROM aules WHERE aula = ?", [aula]),
                "sessions": _sessions_graella(c, vista, dilluns,
                                              "aula_partida = $aula OR list_contains(aules_addicionals_partida, $aula)",
                                              {"aula": aula}),
                "calendari": _calendari_setmana(c, dilluns)}


def consultar_horari_docent(docent, dilluns, vista=VISTA_PER_DEFECTE, con=None):
    """Sessions d'un docent la setmana del dilluns `dilluns`."""
    with _con(con) as c:
        return {"sessions": _sessions_graella(c, vista, dilluns, "list_contains(docents, $docent)", {"docent": docent}),
                "calendari": _calendari_setmana(c, dilluns)}


def consultar_ocupacio_aules(dilluns, vista=VISTA_PER_DEFECTE, con=None):
    """Per a les aules lliures: aules del catàleg i franges ocupades de cadascuna la setmana del dilluns `dilluns`."""
    with _con(con) as c:
        ocupades = _files(c, f"""
            SELECT DISTINCT a AS aula, strftime(data, '%Y-%m-%d') AS data,
                   CAST(extract(epoch FROM h_ini) / 60 AS INTEGER) AS ini,
                   CAST(extract(epoch FROM h_fi) / 60 AS INTEGER)  AS fi
            FROM (SELECT unnest(list_prepend(aula_partida, coalesce(aules_addicionals_partida, []))) AS a,
                         data, h_ini, h_fi
                  FROM {taula_vista(vista)}
                  WHERE aula_partida IS NOT NULL
                    AND CAST(date_trunc('week', data) AS DATE) = CAST($dilluns AS DATE))
            WHERE a IN (SELECT aula FROM aules)
            ORDER BY aula, data, ini
        """, {"dilluns": dilluns})
        return {"aules": _files(c, "SELECT aula, tipus, descripcio, capacitat FROM aules ORDER BY aula"),
                "ocupades": ocupades,
                "calendari": _calendari_setmana(c, dilluns)}
