from pathlib import Path
from datetime import timedelta
import json
import sys

from horaris.model import carrega_base, llegeix_proposta, DIES
from horaris.check import _espai_ok


# ============================================================
# CONFIGURACIÓ I CÀRREGA DE DADES
# ============================================================

BASE = carrega_base(Path("paquet"))

FITXER_PROPOSTA = Path("paquet/proposta_partida.csv")

FILES = llegeix_proposta(FITXER_PROPOSTA)

FILES_PER_ID = {f.id: f for f in FILES}


# ============================================================
# FUNCIONS AUXILIARS
# ============================================================

def minuts_hora(hora):
    """Converteix una hora HH:MM en minuts."""
    h, m = hora.split(":")
    return int(h) * 60 + int(m)


def data_proposta(fila, sessio):
    """
    Calcula la data real de la sessió segons el dia de la proposta.

    Si hi ha una data explícita, utilitza aquesta.
    Si no, conserva la setmana original i adapta el dia.
    """
    if fila.data:
        from datetime import date
        return date.fromisoformat(str(fila.data))

    dilluns = sessio.data - timedelta(
        days=sessio.data.weekday()
    )

    return dilluns + timedelta(
        days=DIES.index(fila.dia)
    )


# ============================================================
# EINA 1: CONSULTAR INFORMACIÓ D'UNA SESSIÓ
# ============================================================

def consultar_sessio(id_sessio):
    """Retorna la informació principal d'una sessió."""

    s = BASE.sessions.get(id_sessio)

    if s is None:
        return {
            "error": f"Sessió desconeguda: {id_sessio}"
        }

    return {
        "id": s.id,
        "codi": s.codi,
        "tipus": s.tipus,
        "grup": s.grup,
        "data": str(s.data),
        "dia": s.dia,
        "hora": s.ini,
        "durada": s.durada,
        "alumnes": s.alumnes,
        "aula_actual": s.aula,
        "torn": s.torn,
        "sense_espai": s.sense_espai,
        "fixada": s.fixada,
    }


# ============================================================
# EINA 2: COMPROVAR DISPONIBILITAT D'UNA AULA
# ============================================================

def comprovar_disponibilitat(id_sessio, aula):
    """
    Comprova si una aula està ocupada durant la data i
    la franja horària de la sessió indicada.

    Utilitza les assignacions actuals de la proposta.
    """

    fila_objectiu = FILES_PER_ID.get(id_sessio)
    sessio_objectiu = BASE.sessions.get(id_sessio)

    if fila_objectiu is None or sessio_objectiu is None:
        return {
            "lliure": False,
            "error": "Sessió no trobada."
        }

    data = data_proposta(
        fila_objectiu,
        sessio_objectiu
    )

    inici = minuts_hora(fila_objectiu.h_ini)
    final = inici + sessio_objectiu.durada

    conflictes = []

    for fila in FILES:

        # No comparem la sessió amb ella mateixa
        if fila.id == id_sessio:
            continue

        # Només ens interessen sessions assignades a aquesta aula
        if fila.aula != aula:
            continue

        altra = BASE.sessions.get(fila.id)

        if altra is None:
            continue

        altra_data = data_proposta(fila, altra)

        # Les sessions d'altres dates no interfereixen
        if altra_data != data:
            continue

        altre_inici = minuts_hora(fila.h_ini)
        altre_final = altre_inici + altra.durada

        # Comprovació de solapament entre intervals
        if inici < altre_final and altre_inici < final:

            conflictes.append({
                "sessio": fila.id,
                "grup": altra.grup,
                "hora_inici": fila.h_ini,
                "durada": altra.durada,
            })

    return {
        "lliure": len(conflictes) == 0,
        "data": str(data),
        "conflictes": conflictes,
    }


# ============================================================
# EINA 3: BUSCAR AULES COMPATIBLES I DISPONIBLES
# ============================================================

def buscar_aules(id_sessio, limit=20):
    """
    Busca aules que compleixin:
      - Capacitat suficient.
      - Tipus d'aula compatible.
      - Disponibilitat horària.

    Les aules lliures apareixen primer.
    """

    s = BASE.sessions.get(id_sessio)

    if s is None:
        return {
            "error": f"Sessió desconeguda: {id_sessio}"
        }

    # Sessions que no necessiten espai
    if s.sense_espai:
        return {
            "sessio": id_sessio,
            "error": "Aquesta sessió no necessita aula."
        }

    # Les sessions PLAB no es poden reassignar
    if s.tipus == "PLAB":
        return {
            "sessio": id_sessio,
            "error": "Les sessions PLAB no s'han de reassignar."
        }

    # No modifiquem sessions fixades
    if s.fixada:
        return {
            "sessio": id_sessio,
            "error": f"Aquesta sessió està fixada: {s.fixada}"
        }

    candidates = []

    for aula in BASE.aules.values():

        # Comprovació de capacitat
        if aula.capacitat < s.alumnes:
            continue

        # Comprovació del tipus d'espai
        if not _espai_ok(BASE, s, aula.aula):
            continue

        # Comprovació de disponibilitat horària
        disponibilitat = comprovar_disponibilitat(
            id_sessio,
            aula.aula
        )

        candidates.append({
            "aula": aula.aula,
            "tipus": aula.tipus,
            "capacitat": aula.capacitat,
            "descripcio": aula.descripcio,
            "places_sobrants": aula.capacitat - s.alumnes,
            "disponible": disponibilitat["lliure"],
            "conflictes": disponibilitat.get(
                "conflictes", []
            ),
        })

    # Primer les aules lliures.
    # Després, les que tenen menys places sobrants.
    candidates.sort(
        key=lambda a: (
            not a["disponible"],
            a["places_sobrants"],
            a["aula"],
        )
    )

    disponibles = [
        a for a in candidates
        if a["disponible"]
    ]

    return {
        "sessio": id_sessio,
        "grup": s.grup,
        "tipus": s.tipus,
        "alumnes": s.alumnes,
        "total_candidates": len(candidates),
        "total_disponibles": len(disponibles),
        "aules": candidates[:limit],
    }


# ============================================================
# EXECUCIÓ DES DE TERMINAL
# ============================================================

if __name__ == "__main__":

    if len(sys.argv) < 3:
        print(
            "Ús:\n"
            "  python agent_tools.py sessio ID_SESSIO\n"
            "  python agent_tools.py aules ID_SESSIO"
        )
        sys.exit(1)

    accio = sys.argv[1]
    sid = sys.argv[2]

    if accio == "sessio":
        resultat = consultar_sessio(sid)

    elif accio == "aules":
        resultat = buscar_aules(sid)

    else:
        resultat = {
            "error": f"Acció desconeguda: {accio}"
        }

    print(
        json.dumps(
            resultat,
            indent=2,
            ensure_ascii=False
        )
    )
