from pathlib import Path
import duckdb

# Ruta absoluta de la base de dades
PROJECTE = Path(__file__).resolve().parent.parent
DB_PATH = PROJECTE / "dades" / "paquet.duckdb"


def connectar():
    """Obre una connexió amb la base de dades."""
    return duckdb.connect(str(DB_PATH), read_only=True)


def consultar_sessio(id_sessio):
    """Consulta una sessió i la seva aula assignada."""

    con = connectar()

    try:
        resultat = con.execute("""
            SELECT
                s.id_sessio,
                s.activitat_id,
                s.codi,
                s.assignatura,
                s.tipus,
                s.grup,
                s.semestre,
                s.data,
                s.dia,
                s.h_ini,
                s.h_fi,
                s.durada_min,
                s.alumnes,
                s.aula_partida,
                s.torn_requerit,
                s.fixada,
                s.docents,
                s.sense_espai,
                p.aula AS aula_assignada
            FROM sessions s
            LEFT JOIN proposta_partida p
                ON s.id_sessio = p.id_sessio
            WHERE s.id_sessio = ?
        """, [id_sessio]).fetchone()

        if resultat is None:
            return {"error": "Sessió no trobada."}

        columnes = [c[0] for c in con.description]

        return dict(zip(columnes, resultat))

    finally:
        con.close()


def consultar_aula(nom_aula):
    """Consulta les característiques d'una aula."""

    con = connectar()

    try:
        resultat = con.execute("""
            SELECT *
            FROM aules
            WHERE aula = ?
        """, [nom_aula]).fetchone()

        if resultat is None:
            return {"error": "Aula no trobada al catàleg."}

        columnes = [c[0] for c in con.description]

        return dict(zip(columnes, resultat))

    finally:
        con.close()


def consultar_totes_les_aules():
    """Retorna totes les aules del catàleg."""

    con = connectar()

    try:
        resultats = con.execute("""
            SELECT *
            FROM aules
            ORDER BY aula
        """).fetchdf()

        return resultats.to_dict(orient="records")

    finally:
        con.close()
