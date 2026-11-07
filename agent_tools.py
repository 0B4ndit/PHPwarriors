from datetime import date, timedelta
import json
import sys

from database.consultes import (obrir_db, consultar_totes_les_aules, consultar_sessions,
                                consultar_calendari, consultar_proposta, VISTA_PER_DEFECTE)
from horaris.model import Base, Aula, Sessio, Fila, DIES
from horaris.check import _espai_ok


# ============================================================
# CÀRREGA DE DADES DIRECTAMENT DES DE DUCKDB
# ============================================================

def hora_a_minuts(hora):
    return hora.hour * 60 + hora.minute


def carregar_base_db(vista=VISTA_PER_DEFECTE):
    with obrir_db() as (con, _):
        files_aules = consultar_totes_les_aules(con=con)

        aules = {
            r["aula"]: Aula(
                aula=r["aula"],
                edifici=r["edifici"] or "",
                tipus=(r["tipus"] or "").strip(),
                capacitat=int(r["capacitat"] or 0),
                descripcio=(r["descripcio"] or "").strip()
            )
            for r in files_aules
        }

        files_sessions = consultar_sessions(vista=vista, con=con)

        sessions = {}
        ordre = []

        for r in files_sessions:
            s = Sessio(
                id=r["id_sessio"],
                codi=r["codi"] or "",
                tipus=r["tipus"] or "",
                grup=r["grup"] or "",
                data=r["data"],
                dia=r["dia"] or "",
                ini=hora_a_minuts(r["h_ini"]),
                durada=int(r["durada_min"] or 0),
                alumnes=int(r["alumnes"] or 0),
                aula=r["aula_partida"] or "",
                cohorts=tuple(r["titulacions_curs"] or []),
                torn=r["torn_requerit"] or "",
                fixada=r["fixada"] or "",
                docents=frozenset(r["docents"] or []),
                compartida=r["id_compartida"] or "",
                activitat=r["activitat_id"] or "",
                sense_espai=bool(r["sense_espai"])
            )

            sessions[s.id] = s
            ordre.append(s.id)

        # Dies feiners sense cap sessió, igual que carrega_base().
        dates_amb_classe = {
            s.data for s in sessions.values()
        }

        dies_sense_classe = set()

        if dates_amb_classe:
            d = min(dates_amb_classe)
            ultima = max(dates_amb_classe)

            while d <= ultima:
                if d.weekday() < 5 and d not in dates_amb_classe:
                    dies_sense_classe.add(d)
                d += timedelta(days=1)

        # Calendari oficial.
        aturades = {}

        files_calendari = consultar_calendari(con=con)

        for r in files_calendari:
            if r["h_ini"] is None:
                franja = (0, 24 * 60)
            else:
                franja = (
                    hora_a_minuts(r["h_ini"]),
                    hora_a_minuts(r["h_fi"])
                )

            aturades.setdefault(r["data"], []).append(franja)

        return Base(
            sessions=sessions,
            aules=aules,
            ordre=ordre,
            dies_sense_classe=frozenset(dies_sense_classe),
            aturades=aturades
        )


def carregar_proposta_db(vista=VISTA_PER_DEFECTE):
    files = consultar_proposta(vista=vista)

    return [
        Fila(
            id=r["id_sessio"],
            dia=(r["dia"] or "").strip().upper(),
            h_ini=r["h_ini"].strftime("%H:%M"),
            aula=r["aula"] or "",
            linia=i
        )
        for i, r in enumerate(files, start=1)
    ]


BASE = carregar_base_db()
FILES = carregar_proposta_db()
FILES_PER_ID = {f.id: f for f in FILES}


# ============================================================
# FUNCIONS AUXILIARS
# ============================================================

def minuts_hora(hora):
    h, m = hora.split(":")
    return int(h) * 60 + int(m)


def data_proposta(fila, sessio):
    if fila.data:
        return date.fromisoformat(str(fila.data))

    dilluns = sessio.data - timedelta(
        days=sessio.data.weekday()
    )

    return dilluns + timedelta(
        days=DIES.index(fila.dia)
    )


# ============================================================
# EINA 1: CONSULTAR UNA SESSIÓ
# ============================================================

def consultar_sessio(id_sessio):
    s = BASE.sessions.get(id_sessio)

    if s is None:
        return {"error": f"Sessió desconeguda: {id_sessio}"}

    fila = FILES_PER_ID.get(id_sessio)

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
        "aula_partida": s.aula,
        "aula_actual": fila.aula if fila else None,
        "torn": s.torn,
        "sense_espai": s.sense_espai,
        "fixada": s.fixada
    }


# ============================================================
# EINA 2: COMPROVAR DISPONIBILITAT
# ============================================================

def comprovar_disponibilitat(id_sessio, aula):
    fila_objectiu = FILES_PER_ID.get(id_sessio)
    sessio_objectiu = BASE.sessions.get(id_sessio)

    if fila_objectiu is None or sessio_objectiu is None:
        return {
            "lliure": False,
            "error": "Sessió no trobada."
        }

    data = data_proposta(fila_objectiu, sessio_objectiu)

    inici = minuts_hora(fila_objectiu.h_ini)
    final = inici + sessio_objectiu.durada

    conflictes = []

    for fila in FILES:
        if fila.id == id_sessio or fila.aula != aula:
            continue

        altra = BASE.sessions.get(fila.id)

        if altra is None:
            continue

        altra_data = data_proposta(fila, altra)

        if altra_data != data:
            continue

        altre_inici = minuts_hora(fila.h_ini)
        altre_final = altre_inici + altra.durada

        if inici < altre_final and altre_inici < final:
            conflictes.append({
                "sessio": fila.id,
                "grup": altra.grup,
                "hora_inici": fila.h_ini,
                "durada": altra.durada
            })

    return {
        "lliure": len(conflictes) == 0,
        "data": str(data),
        "conflictes": conflictes
    }


# ============================================================
# EINA 3: BUSCAR AULES COMPATIBLES I DISPONIBLES
# ============================================================

def buscar_aules(id_sessio, limit=20):
    s = BASE.sessions.get(id_sessio)

    if s is None:
        return {
            "error": f"Sessió desconeguda: {id_sessio}"
        }

    if s.sense_espai:
        return {
            "sessio": id_sessio,
            "error": "Aquesta sessió no necessita aula."
        }

    if s.tipus == "PLAB":
        return {
            "sessio": id_sessio,
            "error": "Les sessions PLAB no s'han de reassignar."
        }

    if s.fixada:
        return {
            "sessio": id_sessio,
            "error": f"Aquesta sessió està fixada: {s.fixada}"
        }

    candidates = []

    for aula in BASE.aules.values():
        if aula.capacitat < s.alumnes:
            continue

        if not _espai_ok(BASE, s, aula.aula):
            continue

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
            "conflictes": disponibilitat.get("conflictes", [])
        })

    candidates.sort(
        key=lambda a: (
            not a["disponible"],
            a["places_sobrants"],
            a["aula"]
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
        "aules": candidates[:limit]
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
        resultat = {"error": f"Acció desconeguda: {accio}"}

    print(json.dumps(resultat, indent=2, ensure_ascii=False, default=str))
