"""Les eines d'Ornith. Totes són deterministes, de només lectura, i retornen {"...": ..., "fonts": [id_sessio]}.

Les fonts són els id_sessio que demostren la resposta: qui l'escolta els pot buscar al CSV en un segon.

    python -m ornith eina horari '{"grup": "81", "dia": "dimarts"}'
"""
from __future__ import annotations

import datetime as dt
import re
import threading
from collections import Counter, defaultdict

import duckdb

from horaris.check import DESCRIPCIO, passadis
from horaris.model import DIES, MATI, TARDA, TIPUS_ORDINARIA, Fila, fmt, hm

from . import dades
from .dades import TIPUS_AULA, VISTA_PER_DEFECTE, VISTES

MAX_FILES = 40
MAX_SQL_FILES = 50
SQL_TIMEOUT_S = 10
AULA_GENERAL = ("Aules docents", "Seminaris")
FRANGES = [MATI[0] + 60 * i for i in range(13)]   # les franges horàries de la regla 8 (com el verificador)

NOMS_DIA = {
    "l": "L", "dl": "L", "dilluns": "L", "lunes": "L", "monday": "L",
    "m": "M", "dt": "M", "dimarts": "M", "martes": "M", "tuesday": "M",
    "x": "X", "dc": "X", "dimecres": "X", "miercoles": "X", "miércoles": "X", "wednesday": "X",
    "j": "J", "dj": "J", "dijous": "J", "jueves": "J", "thursday": "J",
    "v": "V", "dv": "V", "divendres": "V", "viernes": "V", "friday": "V",
}


NOM_DIA = {"L": "dilluns", "M": "dimarts", "X": "dimecres", "J": "dijous", "V": "divendres"}


class ErrorEina(ValueError):
    """Un error que s'explica al LLM (paràmetre dolent, sessió que no existeix...)."""


# ---------------------------------------------------------------- paràmetres

def _vista(nom):
    nom = (nom or VISTA_PER_DEFECTE).strip().lower().replace("proposta", "").strip() or VISTA_PER_DEFECTE
    if nom in ("partida", "actual", "today"):
        nom = "avui"
    if nom not in VISTES:
        raise ErrorEina(f"vista desconeguda «{nom}»; opcions: {', '.join(VISTES)}")
    return dades.vista(nom)


def _dia(dia):
    if not dia:
        return None
    d = NOMS_DIA.get(str(dia).strip().lower())
    if d is None:
        raise ErrorEina(f"dia desconegut «{dia}»: fes servir L, M, X, J, V o el nom (dilluns...)")
    return d


def _data(data):
    if not data:
        return None
    if isinstance(data, dt.date):
        return data
    s = str(data).strip()
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            pass
    raise ErrorEina(f"data il·legible «{data}»: fes servir AAAA-MM-DD")


def _hora(h):
    s = str(h).strip().lower().replace("h", ":").replace(".", ":")
    if re.fullmatch(r"\d{1,2}", s):
        s += ":00"
    s = s.rstrip(":")
    if not re.fullmatch(r"\d{1,2}:\d{2}", s):
        raise ErrorEina(f"hora il·legible «{h}»: fes servir HH:MM")
    return hm(s)


def _tipus_aula(tipus):
    if not tipus:
        return AULA_GENERAL
    t = str(tipus).strip()
    if t in TIPUS_AULA.values():
        return (t,)
    if t.lower() in TIPUS_AULA:
        return (TIPUS_AULA[t.lower()],)
    if t.lower() in ("tots", "totes", "qualsevol", "all"):
        return tuple(sorted(set(TIPUS_AULA.values())))
    raise ErrorEina(f"tipus d'aula desconegut «{tipus}»; opcions: {', '.join(sorted(set(TIPUS_AULA.values())))}")


def _registre(df, cols):
    out = []
    for r in df[cols].itertuples(index=False):
        d = {}
        for k, v in zip(cols, r):
            if isinstance(v, (dt.date, dt.datetime)):
                v = v.isoformat()[:10]
            elif hasattr(v, "tolist"):
                v = v.tolist()
            elif v != v:   # NaN
                v = None
            d[k] = v
        out.append(d)
    return out


# ---------------------------------------------------------------- eina 1: horari

def horari(grup=None, assignatura=None, docent=None, aula=None, titulacio=None, dia=None, data=None,
           semestre=None, vista=None):
    """On i quan té classe un grup, una assignatura, un docent, una aula o una titulació."""
    v = _vista(vista)
    if not any((grup, assignatura, docent, aula, titulacio)):
        raise ErrorEina("cal almenys un filtre: grup, assignatura, docent, aula o titulacio")
    on, params, filtre = [], [], {}
    if grup:
        g = str(grup).strip().upper().replace(" ", "")
        if "/" in g:
            on.append("grup = ?"); params.append(g)
        elif g.isdigit():
            # «grup 81» = TE/81, PAUL/81 i els seus subgrups PAUL/811, PAUL/812... (regla 8.3)
            on.append("regexp_matches(grup, ?)"); params.append(f"/{g}[0-9]*$")
        else:
            raise ErrorEina(f"grup il·legible «{grup}»: p. ex. 81 o TE/81")
        filtre["grup"] = g
    if assignatura:
        a = str(assignatura).strip()
        if a.isdigit():
            on.append("codi = ?"); params.append(a)
        else:
            on.append("assignatura ILIKE ?"); params.append(f"%{a}%")
        filtre["assignatura"] = a
    if docent:
        on.append("list_contains(docents, ?)"); params.append(str(docent).strip().upper()); filtre["docent"] = docent
    if aula:
        on.append("aula = ?"); params.append(str(aula).strip().upper()); filtre["aula"] = aula
    if titulacio:
        t = str(titulacio).strip()
        if ":" in t:
            on.append("list_contains(titulacions_curs, ?)"); params.append(t)
        else:
            on.append("array_to_string(titulacions_curs, '|') ILIKE ?"); params.append(f"%{t}%")
        filtre["titulacio"] = t
    d, data = _dia(dia), _data(data)
    if data:
        on.append("data = ?"); params.append(data); filtre["data"] = data.isoformat()
    elif d:
        on.append("dia = ?"); params.append(d); filtre["dia"] = NOM_DIA[d]
    if semestre:
        on.append("semestre = ?"); params.append(int(semestre)); filtre["semestre"] = int(semestre)
    where = " AND ".join(on)

    if data:
        df = v.sql(f"""SELECT id_sessio, data, h_ini, h_fi, codi, assignatura, tipus, grup,
                              coalesce(aula, CASE WHEN sense_espai THEN 'sense aula (doble titulació)'
                                                  ELSE 'SENSE AULA' END) AS aula,
                              alumnes, docents, titulacions_curs
                       FROM horari WHERE {where} ORDER BY ini_min, codi, grup""", params)
        files = _registre(df.head(MAX_FILES), list(df.columns))
        for f in files:
            f["data"] = f"{NOM_DIA[DIES[dt.date.fromisoformat(f['data']).weekday()]]} {f['data']}"
        fonts = df["id_sessio"].tolist()
        mode = "sessions d'aquest dia"
    else:
        # patró setmanal: cada classe que es repeteix, amb quantes setmanes i les sessions que ho proven
        df = v.sql(f"""SELECT dia, h_ini, h_fi, codi, assignatura, tipus, grup,
                              array_to_string(titulacions_curs, ', ') AS titulacions,
                              coalesce(aula, CASE WHEN bool_and(sense_espai) THEN 'sense aula (doble titulació)'
                                                  ELSE 'SENSE AULA' END) AS aula,
                              count(*) AS setmanes, min(data) AS primera, max(data) AS darrera,
                              list(id_sessio ORDER BY data) AS ids
                       FROM horari WHERE {where}
                       GROUP BY dia, h_ini, h_fi, codi, assignatura, tipus, grup, titulacions, aula
                       ORDER BY list_position(['L','M','X','J','V'], dia), h_ini, codi, grup""", params)
        fonts = [i for ids in df["ids"] for i in ids]
        df["exemples"] = [list(ids[:3]) for ids in df["ids"]]
        cols = ["dia", "h_ini", "h_fi", "codi", "assignatura", "tipus", "grup", "titulacions", "aula", "setmanes",
                "primera", "darrera", "exemples"]
        files = _registre(df.head(MAX_FILES), cols)
        for f in files:
            f["dia"] = NOM_DIA[f["dia"]]
        mode = ("patró setmanal (una fila per classe que es repeteix; «setmanes» = quantes vegades). "
                "El número de grup es repeteix entre titulacions: separa-les per «titulacions»")
    return {
        "vista": v.nom, "vista_descripcio": v.descripcio, "filtre": filtre, "mode": mode,
        "n_files": len(df), "truncat": len(df) > MAX_FILES, "files": files,
        "fonts": fonts,
        "com_comprovar": "filtra el CSV de la vista per aquests id_sessio (columnes dia, h_ini, aula)",
    }


# ---------------------------------------------------------------- eina 2: aules lliures

def aules_lliures(hora, dia=None, data=None, durada_min=60, places_min=0, tipus=None, semestre=None, vista=None):
    """Quines aules estan lliures a una hora: un dia concret (data) o cada setmana (dia)."""
    v = _vista(vista)
    ini = _hora(hora)
    durada = int(durada_min or 60)
    fi = ini + durada
    places = int(places_min or 0)
    tipus_ok = _tipus_aula(tipus)
    d, data = _dia(dia), _data(data)
    if not d and not data:
        raise ErrorEina("cal el dia de la setmana (dia) o una data concreta (data)")
    avisos = []
    if not (MATI[0] <= ini and fi <= TARDA[1]):
        avisos.append("l'edifici només té classes de 8:30 a 21:00 (regla 2)")

    if data:
        dates = [data]
    else:
        on, params = ["dia = ?"], [d]
        if semestre:
            on.append("semestre = ?"); params.append(int(semestre))
        dates = sorted(v.sql(f"SELECT DISTINCT data FROM horari WHERE {' AND '.join(on)}", params)["data"])
        dates = [x.date() if hasattr(x, "date") else x for x in dates]
        semestres = sorted({1 if x.month >= 9 or x.month == 1 else 2 for x in dates})
        if len(semestres) > 1:
            avisos.append("la vista té els dos semestres i no has dit quin: es miren totes les setmanes de tots dos")
    if not dates:
        raise ErrorEina("aquell dia no hi ha classes en aquesta vista (festiu, no lectiu o fora del semestre)")

    candidates = {a: x for a, x in v.base.aules.items() if x.tipus in tipus_ok and x.capacitat >= places}
    ordinaries = {a for a, x in v.base.aules.items() if x.ordinaria}
    ocup = v.sql("""SELECT id_sessio, data, h_ini, h_fi, aula, codi, grup FROM horari
                    WHERE aula IS NOT NULL AND NOT sense_espai AND data IN (SELECT unnest(?))
                      AND ini_min < ? AND fi_min > ?""", [dates, fi, ini])
    ocup["data"] = [x.date() if hasattr(x, "date") else x for x in ocup["data"]]
    per_aula = defaultdict(list)
    for r in ocup.itertuples(index=False):
        per_aula[r.aula].append(r)
    # regla 8: quantes aules ordinàries queden lliures en cada franja horària que toca la classe
    ord_ocup = defaultdict(set)
    for r in ocup.itertuples(index=False):
        if r.aula in ordinaries:
            ri, rf = hm(r.h_ini), hm(r.h_fi)
            for f0 in FRANGES:
                if ri < f0 + 60 and rf > f0 and ini < f0 + 60 and fi > f0:
                    ord_ocup[(r.data, f0)].add(r.aula)
    franges_classe = [f0 for f0 in FRANGES if ini < f0 + 60 and fi > f0]
    min_lliures_ord = min((len(ordinaries) - len(ord_ocup.get((x, f0), ())) for x in dates for f0 in franges_classe),
                          default=len(ordinaries))
    tancades = defaultdict(list)
    for t in v.base.tancaments:
        for x in dates:
            if t.data_ini <= x <= t.data_fi and ini < t.fi and fi > t.ini:
                tancades[t.aula].append(x)
    sense_aula = v.sql("""SELECT count(*) FROM horari WHERE aula IS NULL AND NOT sense_espai AND tipus <> 'PLAB'
                          AND data IN (SELECT unnest(?)) AND ini_min < ? AND fi_min > ?""", [dates, fi, ini]).iloc[0, 0]
    if sense_aula:
        avisos.append(f"{int(sense_aula)} sessions d'aquesta franja no tenen aula a les dades d'aquesta vista: "
                      f"una aula que surt lliure pot ser que no ho estigui a la realitat")

    lliures, ocupades, fonts = [], [], []
    for a, x in sorted(candidates.items(), key=lambda kv: (kv[1].capacitat, kv[0])):
        rs = per_aula.get(a, [])
        dies_ocupada = sorted({r.data for r in rs} | set(tancades.get(a, [])))
        fitxa = {"aula": a, "tipus": x.tipus, "capacitat": x.capacitat, "passadis": passadis(a)}
        if not dies_ocupada:
            if x.ordinaria and min_lliures_ord - 1 < 2:
                fitxa["avis_R8"] = (f"ocupar-la deixaria {min_lliures_ord - 1} aules ordinàries lliures en alguna "
                                    f"franja (la regla 8 en vol 2 de reserva)")
            lliures.append(fitxa)
        else:
            fitxa["ocupada_dies"] = len(dies_ocupada)
            fitxa["de"] = len(dates)
            fitxa["per"] = sorted({f"{r.codi} {r.grup} ({r.id_sessio})" for r in rs})[:3]
            if a in tancades:
                fitxa["tancada"] = "aula tancada per l'escenari"
            ocupades.append(fitxa)
            fonts += [r.id_sessio for r in rs]
    return {
        "vista": v.nom, "vista_descripcio": v.descripcio,
        "consulta": {"hora": f"{fmt(ini)}-{fmt(fi)}", "dia": NOM_DIA.get(d), "data": data.isoformat() if data else None,
                     "places_min": places, "tipus": list(tipus_ok)},
        "dates_mirades": len(dates), "primera_data": dates[0].isoformat(), "darrera_data": dates[-1].isoformat(),
        "lliures": lliures,
        "ocupades": sorted(ocupades, key=lambda o: (o["ocupada_dies"], o["capacitat"]))[:15],
        "n_ocupades": len(ocupades),
        "aules_ordinaries_lliures_minim": min_lliures_ord,
        "avisos": avisos,
        "fonts": fonts,
        "com_comprovar": ("les lliures no tenen cap sessió a la vista amb aquesta aula, aquestes dates i una hora que "
                          "se solapi; les ocupades citen la sessió que les ocupa"),
    }


# ---------------------------------------------------------------- eina 3: simulació amb el verificador

def _clau(vi):
    return (vi.regla, vi.sessions, vi.detall)


def avalua_files(v, files_noves, base=None, relaxacions_extra=()):
    """Passa el verificador oficial i el compara amb la proposta tal com és. Retorna el resum."""
    from horaris.check import avalua
    base = base or v.base
    abans = v.informe_base() if base is v.base else avalua(base, v.files, v.relaxacions, nomes_aules=v.nom == "5.1")
    despres = avalua(base, files_noves, list(v.relaxacions) + list(relaxacions_extra), referencia=v.files,
                     nomes_aules=v.nom == "5.1")
    ka = {_clau(x) for x in abans.violacions if x.compta}
    kd = {_clau(x) for x in despres.violacions if x.compta}
    noves = [x for x in despres.violacions if x.compta and _clau(x) not in ka]
    resoltes = [x for x in abans.violacions if x.compta and _clau(x) not in kd]
    obj_a, obj_d = abans.objectius, despres.objectius
    return {
        "veredicte_abans": abans.veredicte, "veredicte_despres": despres.veredicte,
        "violacions_noves": len(noves),
        "violacions_noves_per_regla": dict(Counter(x.regla for x in noves)),
        "exemples_noves": [{"regla": x.regla, "que_vol_dir": DESCRIPCIO.get(x.regla, ""),
                            "sessions": list(x.sessions), "detall": x.detall} for x in noves[:15]],
        "violacions_resoltes": len(resoltes),
        "objectius_despres": {k: obj_d[k] for k in obj_d if k != "sessions_avaluades"},
        "objectius_variacio": {k: obj_d[k] - obj_a.get(k, 0) for k in obj_d
                               if k in obj_a and k != "sessions_avaluades" and obj_d[k] != obj_a.get(k, 0)},
        "_noves": noves,
    }


def simula_canvi(canvis, vista=None):
    """Què passa si moc una sessió (id_sessio) o tota una classe (codi + grup [+ tipus]): el verificador ho diu."""
    v = _vista(vista)
    if isinstance(canvis, dict):
        canvis = [canvis]
    if not canvis:
        raise ErrorEina("cal almenys un canvi")
    per_id = {f.id: f for f in v.files}
    nous = {}
    afectades = []
    for c in canvis:
        if c.get("id_sessio"):
            ids = [str(c["id_sessio"]).strip().upper()]
            if ids[0] not in per_id:
                raise ErrorEina(f"la sessió {ids[0]} no és a la vista {v.nom}")
        elif c.get("codi") and c.get("grup"):
            ids = [sid for sid, s in v.base.sessions.items()
                   if s.codi == str(c["codi"]).strip() and s.grup == str(c["grup"]).strip().upper()
                   and (not c.get("tipus") or s.tipus == str(c["tipus"]).strip().upper()) and sid in per_id]
            if not ids:
                raise ErrorEina(f"cap sessió de {c['codi']} {c['grup']} a la vista {v.nom}")
        else:
            raise ErrorEina("cada canvi necessita id_sessio, o bé codi i grup")
        dia = _dia(c.get("dia"))
        h = fmt(_hora(c["h_ini"])) if c.get("h_ini") else None
        aula = str(c["aula"]).strip().upper() if c.get("aula") else None
        if aula and aula not in v.base.aules:
            raise ErrorEina(f"l'aula {aula} no és a l'inventari (aules.csv)")
        if not (dia or h or aula):
            raise ErrorEina("cada canvi ha de dir què canvia: dia, h_ini o aula")
        for sid in ids:
            f = per_id[sid]
            nous[sid] = Fila(sid, dia or f.dia, h or f.h_ini, aula if aula is not None else f.aula, f.linia, f.data)
            afectades.append(sid)
    files = [nous.get(f.id, f) for f in v.files]
    r = avalua_files(v, files)
    r.pop("_noves")
    fonts = afectades + [s for x in r["exemples_noves"] for s in x["sessions"]]
    return {"vista": v.nom, "sessions_canviades": len(afectades), "exemples_canviades": afectades[:10], **r,
            "fonts": fonts,
            "com_comprovar": "és la sortida del verificador oficial (horaris.check.avalua) sobre la proposta modificada"}


# ---------------------------------------------------------------- eina 4: SQL de només lectura

def consulta_sql(sql, vista=None):
    """Consulta SELECT lliure sobre les taules horari, aules i calendari de la vista."""
    v = _vista(vista)
    q = str(sql).strip().rstrip(";").strip()
    try:
        sts = duckdb.extract_statements(q)
    except duckdb.Error as e:
        raise ErrorEina(f"SQL il·legible: {e}") from None
    if len(sts) != 1 or sts[0].type != duckdb.StatementType.SELECT:
        raise ErrorEina("només s'accepta una sola consulta SELECT (o WITH ... SELECT)")
    temporitzador = threading.Timer(SQL_TIMEOUT_S, v.con.interrupt)
    temporitzador.start()
    try:
        df = v.sql(f"SELECT * FROM ({q}) AS consulta LIMIT {MAX_SQL_FILES + 1}")
    except duckdb.InterruptException:
        raise ErrorEina(f"la consulta ha trigat més de {SQL_TIMEOUT_S} s") from None
    except duckdb.Error as e:
        raise ErrorEina(f"error de la consulta: {str(e).splitlines()[0]}") from None
    finally:
        temporitzador.cancel()
    truncat = len(df) > MAX_SQL_FILES
    df = df.head(MAX_SQL_FILES)
    fonts = []
    if "id_sessio" in df.columns:
        fonts = [str(x) for x in df["id_sessio"]]
    else:
        for col in df.columns:
            for x in df[col]:
                fonts += re.findall(r"\bS\d{5}\b", str(x))
    return {"vista": v.nom, "sql": q, "columnes": list(df.columns), "files": _registre(df, list(df.columns)),
            "n_files": len(df), "truncat": truncat, "fonts": fonts,
            "com_comprovar": "torna a executar aquest SQL sobre el CSV (DuckDB el llegeix directament)"}


# ---------------------------------------------------------------- eina 5: una sessió

def sessio(id_sessio, vista=None):
    """Tota la informació d'una sessió: on és a la vista i on era a l'horari d'avui."""
    v = _vista(vista)
    sid = str(id_sessio).strip().upper()
    df = v.sql("SELECT * FROM horari WHERE id_sessio = ?", [sid])
    if df.empty:
        raise ErrorEina(f"la sessió {sid} no és a la vista {v.nom}")
    return {"vista": v.nom, "sessio": _registre(df, list(df.columns))[0], "fonts": [sid]}


# ---------------------------------------------------------------- imprevistos (vegeu imprevist.py)

def imprevist_aula(aula, data_ini, data_fi=None, h_ini=None, h_fi=None, motiu="", vista=None):
    from . import imprevist
    return imprevist.aula_no_disponible(_vista(vista), aula, _data(data_ini), _data(data_fi) if data_fi else None,
                                        _hora(h_ini) if h_ini else None, _hora(h_fi) if h_fi else None, motiu)


def imprevist_cancellacio(id_sessio, fins, motiu="", vista=None):
    from . import imprevist
    return imprevist.recupera_sessio(_vista(vista), str(id_sessio).strip().upper(), _data(fins), motiu)


EINES = {
    "horari": horari,
    "aules_lliures": aules_lliures,
    "simula_canvi": simula_canvi,
    "consulta_sql": consulta_sql,
    "sessio": sessio,
    "imprevist_aula": imprevist_aula,
    "imprevist_cancellacio": imprevist_cancellacio,
}


def executa(nom, arguments):
    """Executa una eina i sempre retorna un dict (els errors també, perquè el LLM els pugui explicar)."""
    f = EINES.get(nom)
    if f is None:
        return {"error": f"eina desconeguda: {nom}", "fonts": []}
    try:
        return f(**(arguments or {}))
    except ErrorEina as e:
        return {"error": str(e), "fonts": []}
    except TypeError as e:
        return {"error": f"paràmetres incorrectes per a {nom}: {e}", "fonts": []}
