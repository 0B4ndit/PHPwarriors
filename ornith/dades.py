"""Les dades que consulta Ornith: el paquet + una proposta, carregats amb el model del verificador oficial.

Cada «vista» és un horari complet: l'horari d'avui (proposta_partida.csv) o una de les propostes del solver.
Es carrega amb `horaris.model.carrega_base` i `horaris.check._col_loca`, és a dir, exactament com ho llegeix el
verificador del jurat (data real de cada sessió, escenari aplicat), i es bolca en una DuckDB en memòria
(taules `horari`, `aules`, `calendari`) per a les consultes.

No depèn de dades/paquet.duckdb: només dels CSV del paquet i de final/solver/out/, que són el que avalua el jurat.
"""
from __future__ import annotations

import csv
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd

from horaris.check import Colocada, Informe, _col_loca, avalua, passadis
from horaris.model import DIES, Base, Fila, carrega_base, fmt, llegeix_proposta, llegeix_relaxacions, semestre_de

PROJECTE = Path(__file__).resolve().parent.parent
PAQUET = PROJECTE / "final" / "paquet"
SOLVER = PROJECTE / "final" / "solver" / "out"

# nom -> (proposta, semestre, escenari, relaxacions, descripció)
VISTES = {
    "avui": (PAQUET / "proposta_partida.csv", None, None, None,
             "horari actual 2026-27 (proposta_partida.csv), els dos semestres; 4.541 sessions del 2n semestre no hi "
             "tenen aula"),
    "5.1": (SOLVER / "5.1" / "proposta.csv", 2, None, None,
            "proposta 5.1: horari d'avui del 2n semestre amb aula a cada sessió"),
    "5.2": (SOLVER / "5.2" / "proposta.csv", 2, None, SOLVER / "5.2" / "relaxacions.csv",
            "proposta 5.2: torns nous (1r i 2n al matí, 3r i 4t a la tarda), 2n semestre"),
    "5.3": (SOLVER / "5.3" / "proposta.csv", 2, PAQUET / "escenaris" / "contingencies",
            SOLVER / "5.3" / "relaxacions.csv", "proposta 5.3: la 5.2 amb els imprevistos de l'escenari contingencies"),
    "5.4": (SOLVER / "5.4" / "proposta.csv", 2, PAQUET / "escenaris" / "grau-nou-40",
            SOLVER / "5.4" / "relaxacions.csv", "proposta 5.4: la 5.2 amb el grau nou de 40 places"),
}
VISTA_PER_DEFECTE = "5.2"

TIPUS_AULA = {   # paraules que fa servir la gent -> tipus d'aules.csv
    "aula": "Aules docents", "aules": "Aules docents", "aula docent": "Aules docents", "aules docents": "Aules docents",
    "seminari": "Seminaris", "seminaris": "Seminaris",
    "informatica": "Aules informàtiques", "informàtica": "Aules informàtiques", "aules informàtiques": "Aules informàtiques",
    "laboratori": "Laboratoris docents", "laboratoris": "Laboratoris docents", "laboratoris docents": "Laboratoris docents",
}


@dataclass
class Vista:
    nom: str
    descripcio: str
    base: Base
    files: list[Fila]
    col: dict[str, Colocada]
    relaxacions: list
    proposta: Path
    con: duckdb.DuckDBPyConnection
    lock: threading.Lock = field(default_factory=threading.Lock)
    _informe: object = None

    def sql(self, query: str, params=None) -> pd.DataFrame:
        """Consulta de només lectura (la connexió no pot llegir fitxers ni canviar la configuració)."""
        with self.lock:
            return self.con.execute(query, params or []).df()

    def informe_base(self):
        """L'informe del verificador sobre la proposta tal com és (en memòria cau)."""
        if self._informe is None:
            self._informe = avalua(self.base, self.files, self.relaxacions, nomes_aules=self.nom == "5.1")
        return self._informe


def _noms_assignatura() -> dict[str, str]:
    noms = {}
    fonts = [PAQUET / "sessions.csv", PAQUET / "escenaris" / "grau-nou-40" / "sessions_extra.csv"]
    for path in fonts:
        if path.exists():
            with open(path, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    noms[r["id_sessio"]] = r.get("assignatura", "")
    return noms


def _taula_horari(base: Base, col: dict[str, Colocada], noms: dict[str, str]) -> pd.DataFrame:
    files = []
    for sid in base.ordre:
        c = col.get(sid)
        if c is None:
            continue
        s = c.s
        files.append({
            "id_sessio": sid, "codi": s.codi, "assignatura": noms.get(sid, ""), "tipus": s.tipus, "grup": s.grup,
            "data": c.data, "dia": DIES[c.data.weekday()], "h_ini": fmt(c.ini), "h_fi": fmt(c.fi),
            "ini_min": c.ini, "fi_min": c.fi, "durada_min": s.durada, "setmana": c.data.isocalendar().week,
            "semestre": semestre_de(c.data), "aula": c.aula or None, "alumnes": s.alumnes,
            "titulacions_curs": list(s.cohorts), "docents": sorted(s.docents), "torn_requerit": s.torn,
            "fixada": s.fixada or None, "sense_espai": s.sense_espai, "id_compartida": s.compartida or None,
            "activitat_id": s.activitat or None,
            "data_partida": s.data, "h_ini_partida": fmt(s.ini), "aula_partida": s.aula or None,
            "franja_canviada": (c.data, c.ini) != (s.data, s.ini), "aula_canviada": (c.aula or "") != (s.aula or ""),
        })
    return pd.DataFrame(files)


def _taula_aules(base: Base) -> pd.DataFrame:
    return pd.DataFrame([{
        "aula": a.aula, "edifici": a.edifici, "tipus": a.tipus, "descripcio": a.descripcio,
        "capacitat": a.capacitat, "ordinaria": a.ordinaria, "passadis": passadis(a.aula),
    } for a in base.aules.values()])


@lru_cache(maxsize=None)
def vista(nom: str = VISTA_PER_DEFECTE) -> Vista:
    if nom not in VISTES:
        raise ValueError(f"vista desconeguda: {nom!r}; opcions: {', '.join(VISTES)}")
    proposta, semestre, escenari, relax, desc = VISTES[nom]
    base = carrega_base(PAQUET, semestre=semestre, escenari=escenari)
    files = llegeix_proposta(proposta)
    col = _col_loca(base, files, Informe())
    relaxacions = llegeix_relaxacions(relax) if relax and relax.exists() else []

    con = duckdb.connect(":memory:")
    horari = _taula_horari(base, col, _noms_assignatura())
    aules = _taula_aules(base)
    calendari = pd.read_csv(PAQUET / "calendari.csv", dtype=str).fillna("")
    for nom_taula, df in (("horari", horari), ("aules", aules), ("calendari", calendari)):
        con.register("_df", df)
        con.execute(f"CREATE TABLE {nom_taula} AS SELECT * FROM _df")
        con.unregister("_df")
    con.execute("ALTER TABLE calendari ALTER data TYPE DATE")
    # a partir d'aquí, la connexió no pot llegir ni escriure fitxers ni tornar a obrir-se la porta
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return Vista(nom, desc, base, files, col, relaxacions, proposta, con)


def esquema() -> str:
    """Esquema de les taules per al prompt del LLM."""
    return (
        "horari(id_sessio, codi, assignatura, tipus [TE|PAUL|PLAB|SEM], grup [p. ex. TE/81, PAUL/811], data DATE, "
        "dia [L|M|X|J|V], h_ini 'HH:MM', h_fi 'HH:MM', ini_min INT, fi_min INT, durada_min, setmana INT, "
        "semestre [1|2], aula [NULL = sense aula], alumnes, titulacions_curs VARCHAR[] [p. ex. 'GEI:1r'], "
        "docents VARCHAR[] [p. ex. 'D017'], torn_requerit [mati|tarda], fixada, sense_espai BOOL [doble titulació, "
        "no necessita aula], id_compartida, activitat_id, data_partida, h_ini_partida, aula_partida, "
        "franja_canviada BOOL, aula_canviada BOOL [respecte de l'horari d'avui]) · "
        "aules(aula, edifici, tipus [Aules docents|Seminaris|Aules informàtiques|Laboratoris docents], descripcio, "
        "capacitat, ordinaria BOOL, passadis) · calendari(data DATE, tipus, h_ini, h_fi, motiu, font)"
    )
