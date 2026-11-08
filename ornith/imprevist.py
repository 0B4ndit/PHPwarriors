"""Agent d'imprevistos: detectar -> proposar -> validar amb el verificador -> redactar avisos i registre.

Tot és determinista: les propostes surten d'una cerca sobre les dades, la validació és horaris.check.avalua i els
avisos són plantilles (el LLM no hi escriu cap dada). Els avisos es redacten però no s'envien a ningú.

    python -m ornith imprevist-aula Q1/1003 2027-03-10 --motiu "Projector i ordinador avariats"
    python -m ornith imprevist-cancellacio S11527 2027-03-19 --motiu "Cancel·lada el 8/3"
"""
from __future__ import annotations

import csv
import dataclasses
import datetime as dt
from collections import defaultdict
from pathlib import Path

from horaris.check import _alumnat_comparteix, _espai_ok, passadis
from horaris.model import DIES, MATI, TARDA, Fila, Relaxacio, Tancament, fmt

from .dades import PROJECTE

REGISTRE = PROJECTE / "dades" / "registre_canvis.csv"
CAMPS_REGISTRE = ["data_avis", "id_sessio", "assignatura", "grup", "de", "a", "motiu", "afecta", "estat"]
FRANGES = [MATI[0] + 60 * i for i in range(13)]


# ---------------------------------------------------------------- ocupació

class Ocupacio:
    """Qui és a cada aula / cada docent / cada alumnat, per data. Comença amb la vista i s'hi afegeixen els canvis."""

    def __init__(self, v, treure=()):
        self.v = v
        self.per_data = defaultdict(list)   # data -> [(ini, fi, aula, Sessio)]
        for sid, c in v.col.items():
            if sid not in treure:
                self.per_data[c.data].append((c.ini, c.fi, c.aula, c.s))

    def afegeix(self, data, ini, fi, aula, s):
        self.per_data[data].append((ini, fi, aula, s))

    def aula_lliure(self, data, ini, fi, aula, unitat=None):
        return not any(a == aula and i < fi and f > ini and (unitat is None or s.unitat != unitat)
                       for i, f, a, s in self.per_data.get(data, ()) if not s.sense_espai)

    def persones_lliures(self, data, ini, fi, s):
        for i, f, _, o in self.per_data.get(data, ()):
            if i < fi and f > ini and o.unitat != s.unitat:
                if s.docents & o.docents or _alumnat_comparteix(s, o):
                    return False
                if s.codi == o.codi and {"PLAB"} & {s.tipus, o.tipus} and {"TE", "PAUL"} & {s.tipus, o.tipus}:
                    return False
        return True

    def reserva_ok(self, data, ini, fi, aula):
        """Regla 8: després de posar-hi la classe, queden almenys 2 aules ordinàries lliures a cada franja."""
        aules = self.v.base.aules
        if aula not in aules or not aules[aula].ordinaria:
            return True
        n_ord = sum(1 for x in aules.values() if x.ordinaria)
        for f0 in FRANGES:
            if ini < f0 + 60 and fi > f0:
                ocup = {a for i, f, a, s in self.per_data.get(data, ())
                        if a in aules and aules[a].ordinaria and not s.sense_espai and i < f0 + 60 and f > f0}
                ocup.add(aula)
                if n_ord - len(ocup) < 2:
                    return False
        return True


def _tancada(base, aula, data, ini, fi):
    return any(t.aula == aula and t.data_ini <= data <= t.data_fi and ini < t.fi and fi > t.ini for t in base.tancaments)


def _aules_candidates(v, base, s, data, ini, fi, ocup, aula_origen):
    """Aules on pot anar la sessió, de millor a pitjor: mateix passadís, mateix edifici, menys places sobrants."""
    out = []
    for a, x in base.aules.items():
        if a == aula_origen or x.capacitat < s.alumnes or not _espai_ok(base, s, a):
            continue
        if s.tipus != "PLAB" and x.tipus == "Laboratoris docents" and not x.integrat:
            continue
        if _tancada(base, a, data, ini, fi) or not ocup.aula_lliure(data, ini, fi, a, s.unitat):
            continue
        if not ocup.reserva_ok(data, ini, fi, a):
            continue
        origen = aula_origen or ""
        out.append(((passadis(a) != passadis(origen), a.split("/")[0] != origen.split("/")[0],
                     x.capacitat - s.alumnes, a), a))
    return [a for _, a in sorted(out)]


# ---------------------------------------------------------------- avisos i registre

NOM_DIA = ("dilluns", "dimarts", "dimecres", "dijous", "divendres")


def _descriu(data, ini, fi, aula):
    return f"{NOM_DIA[data.weekday()]} {data.strftime('%d/%m/%Y')} de {fmt(ini)} a {fmt(fi)} a l'aula {aula or '(sense aula)'}"


def avisos(canvi, noms, avui=None):
    """Plantilles: cap dada no la inventa el LLM. Retorna (avisos, fila del registre)."""
    s = canvi["sessio"]
    avui = avui or dt.date.today()
    nom = noms.get(s.id, "") or s.codi
    de, a = canvi["de"], canvi["a"]
    docents = ", ".join(sorted(s.docents)) or "(sense docent a les dades)"
    cohorts = ", ".join(s.cohorts)
    motiu = canvi["motiu"]
    text = {
        "docent": (f"A l'atenció de {docents}: la sessió {s.id} de {nom} ({s.codi}, {s.grup}), prevista el "
                   f"{de}, es farà el {a}. Motiu: {motiu}."),
        "estudiants": (f"Estudiants de {nom} ({s.grup}, {cohorts}): la classe prevista el {de} es farà el {a}. "
                       f"Motiu: {motiu}."),
        "gestio_academica": (f"Canvi d'horari {s.id} · {s.codi} {nom} {s.grup} · de {de} a {a} · motiu: {motiu} · "
                             f"validat amb el verificador · afecta {docents} i {cohorts}."),
    }
    registre = {"data_avis": avui.isoformat(), "id_sessio": s.id, "assignatura": f"{s.codi} {nom}", "grup": s.grup,
                "de": de, "a": a, "motiu": motiu, "afecta": f"{docents}; {s.grup} ({cohorts}); Gestió Acadèmica",
                "estat": "redactat, no enviat"}
    return text, registre


def desa_registre(files, path=REGISTRE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nou = not path.exists()
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPS_REGISTRE)
        if nou:
            w.writeheader()
        w.writerows(files)
    return str(path)


def _resultat(v, base, canvis, sense_solucio, motiu, extra=None):
    from .dades import _noms_assignatura
    from .eines import avalua_files
    per_id = {f.id: f for f in v.files}
    nous = {c["fila"].id: c["fila"] for c in canvis}
    files = [nous.get(f.id, f) for f in v.files]
    validacio = avalua_files(v, files, base=base)
    noves = validacio.pop("_noves")
    # el que ve imposat per l'imprevist (una sessió fixada o un PLAB que només canvia d'aula perquè la seva és
    # inutilitzable) es declara com a relaxació, igual que al 5.3; tota la resta ha de ser zero
    imposades = [x for x in noves if x.regla in ("R1-FIXADA", "R7-PLAB")
                 and all(s in nous and v.base.sessions[s].fixada and nous[s].dia == per_id[s].dia
                         and nous[s].h_ini == per_id[s].h_ini for s in x.sessions)]
    if imposades:
        just = ("Sessió fixada a una aula que l'imprevist deixa inutilitzable (R3-TANCADA, no relaxable): manté dia "
                "i hora i només canvia d'aula.")
        relax = [Relaxacio(regla, frozenset(s for x in imposades if x.regla == regla for s in x.sessions), just)
                 for regla in sorted({x.regla for x in imposades})]
        validacio = avalua_files(v, files, base=base, relaxacions_extra=relax)
        validacio.pop("_noves")
    noms = _noms_assignatura()
    avs, registre = [], []
    for c in canvis:
        t, r = avisos(c, noms)
        avs.append({"id_sessio": c["sessio"].id, **t})
        registre.append(r)
    valida = validacio["violacions_noves"] == 0 and not sense_solucio
    return {
        "vista": v.nom, "motiu": motiu,
        "canvis": [{"id_sessio": c["sessio"].id, "grup": c["sessio"].grup, "codi": c["sessio"].codi,
                    "de": c["de"], "a": c["a"],
                    **({"classe_compartida": c["sessio"].compartida} if c["sessio"].compartida else {})}
                   for c in canvis],
        "nota_compartides": "les sessions amb la mateixa classe_compartida són una sola classe física per a diverses "
                            "titulacions: van juntes a la mateixa aula",
        "sense_solucio": sense_solucio,
        "validat": valida,
        "validacio": validacio,
        "relaxacions_declarades": [{"restriccio": r.restriccio, "sessions": sorted(r.sessions),
                                    "justificacio": r.justificacio} for r in (relax if imposades else [])],
        "avisos": avs, "registre": registre,
        "proposta_csv": [{"id_sessio": f.id, "dia": f.dia, "h_ini": f.h_ini, "aula": f.aula,
                          **({"data": f.data} if f.data else {})} for f in nous.values()],
        **(extra or {}),
        "fonts": [c["sessio"].id for c in canvis] + [x["id_sessio"] for x in sense_solucio],
        "nota": "avisos redactats, no enviats a ningú; el registre només es desa amb --desa (CLI)",
    }


# ---------------------------------------------------------------- imprevist 1: una aula no es pot fer servir

def aula_no_disponible(v, aula, data_ini, data_fi=None, ini=None, fi=None, motiu=""):
    aula = str(aula).strip().upper()
    if aula not in v.base.aules:
        from .eines import ErrorEina
        raise ErrorEina(f"l'aula {aula} no és a l'inventari")
    data_fi = data_fi or data_ini
    t = Tancament(aula, data_ini, data_fi, ini if ini is not None else 0, fi if fi is not None else 24 * 60)
    base = dataclasses.replace(v.base, tancaments=list(v.base.tancaments) + [t])
    motiu = motiu or f"l'aula {aula} no es pot fer servir"
    afectades = sorted((c for c in v.col.values()
                        if c.aula == aula and data_ini <= c.data <= data_fi and c.ini < t.fi and c.fi > t.ini
                        and not c.s.sense_espai), key=lambda c: (c.data, c.ini, -c.s.alumnes))
    ocup = Ocupacio(v, treure={c.s.id for c in afectades})
    per_id = {f.id: f for f in v.files}
    canvis, sense = [], []
    fet = {}   # unitat compartida -> aula triada (totes les files d'una classe compartida van juntes)
    for c in afectades:
        s = c.s
        clau = (s.unitat, c.data, c.ini)
        nova = fet.get(clau)
        if nova is None:
            cands = _aules_candidates(v, base, s, c.data, c.ini, c.fi, ocup, aula)
            if not cands:
                sense.append({"id_sessio": s.id, "grup": s.grup, "on": _descriu(c.data, c.ini, c.fi, aula),
                              "per_que": f"cap aula del tipus que toca amb {s.alumnes} places lliure a aquella hora "
                                         f"(cal moure-la de franja: decisió de Gestió Acadèmica)"})
                continue
            nova = fet[clau] = cands[0]
        ocup.afegeix(c.data, c.ini, c.fi, nova, s)
        f = per_id[s.id]
        canvis.append({"sessio": s, "fila": Fila(s.id, f.dia, f.h_ini, nova, f.linia, f.data), "motiu": motiu,
                       "de": _descriu(c.data, c.ini, c.fi, aula), "a": _descriu(c.data, c.ini, c.fi, nova)})
    return _resultat(v, base, canvis, sense, motiu, {
        "imprevist": {"aula": aula, "de": data_ini.isoformat(), "fins": data_fi.isoformat(),
                      "hores": f"{fmt(t.ini)}-{fmt(t.fi)}" if (ini is not None or fi is not None) else "tot el dia"},
        "sessions_afectades": len(afectades)})


# ---------------------------------------------------------------- imprevist 2: una sessió cancel·lada

def recupera_sessio(v, sid, fins, motiu=""):
    from .eines import ErrorEina
    c = v.col.get(sid)
    if c is None:
        raise ErrorEina(f"la sessió {sid} no és a la vista {v.nom}")
    s = c.s
    if not fins or fins <= c.data:
        raise ErrorEina(f"cal una data límit posterior al {c.data.isoformat()}")
    base = dataclasses.replace(v.base, cancellades={**v.base.cancellades, sid: fins})
    motiu = motiu or f"sessió cancel·lada el {c.data.strftime('%d/%m/%Y')}"
    ocup = Ocupacio(v, treure={sid})
    dies_amb_classe = set(ocup.per_data)
    finestra = MATI if c.ini < MATI[1] else TARDA   # es recupera al mateix torn
    hores = sorted(range(finestra[0], finestra[1] - s.durada + 1, 30), key=lambda h: (abs(h - c.ini), h))
    d = c.data + dt.timedelta(days=1)
    while d <= fins:
        if d.weekday() < 5 and d in dies_amb_classe and d not in base.dies_sense_classe:
            for h in hores:
                if any(h < b and h + s.durada > a for a, b in base.aturades.get(d, ())):
                    continue
                if not ocup.persones_lliures(d, h, h + s.durada, s):
                    continue
                pref = [c.aula] if c.aula and ocup.aula_lliure(d, h, h + s.durada, c.aula) \
                    and not _tancada(base, c.aula, d, h, h + s.durada) and ocup.reserva_ok(d, h, h + s.durada, c.aula) else []
                cands = pref or _aules_candidates(v, base, s, d, h, h + s.durada, ocup, c.aula)
                if not cands:
                    continue
                f = next(x for x in v.files if x.id == sid)
                canvi = {"sessio": s, "fila": Fila(sid, DIES[d.weekday()], fmt(h), cands[0], f.linia, d.isoformat()),
                         "motiu": motiu, "de": _descriu(c.data, c.ini, c.fi, c.aula),
                         "a": _descriu(d, h, h + s.durada, cands[0])}
                return _resultat(v, base, [canvi], [], motiu, {
                    "criteri": "primer dia lectiu possible, a l'hora més propera a l'original i al mateix torn; "
                               "alumnat, docent i aula lliures; regla 8 respectada"})
        d += dt.timedelta(days=1)
    return _resultat(v, base, [], [{"id_sessio": sid, "grup": s.grup, "on": _descriu(c.data, c.ini, c.fi, c.aula),
                                    "per_que": f"no hi ha cap franja abans del {fins.isoformat()} amb alumnat, docent "
                                               f"i aula lliures"}], motiu)
