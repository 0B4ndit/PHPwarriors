"""Nivell 1: les 5 troballes sobre l'ús dels espais (docs/NIVELL1.md). python analisi/nivell1.py"""
from pathlib import Path

import pandas as pd

ARREL = Path(__file__).resolve().parents[1]   # arrel del projecte: funciona des de qualsevol carpeta
PAQUET = ARREL / "final" / "paquet"

s = pd.read_csv(PAQUET / "sessions.csv", parse_dates=["data"])

# Semestre segons la data: 1r = setembre a gener, 2n = la resta
s["sem"] = s["data"].dt.month.isin([9, 10, 11, 12, 1]).map({True: 1, False: 2})

print("Sessions per semestre:")
print(s["sem"].value_counts().sort_index())

s2 = s[s["sem"] == 2]
sense_aula = s2["aula_partida"].isna()
pl  = s2["tipus"] == "PLAB"
dob = s2["sense_espai"] == 1

print("\nSessions del 2n semestre sense aula:", sense_aula.sum())
print("Percentatge:", round(100 * sense_aula.mean(), 1), "%")
print("PLAB sense aula:            ", (sense_aula & pl).sum())
print("Dobles sense aula (no PLAB):", (sense_aula & dob & ~pl).sum())
print("Per assignar de debò:       ", (sense_aula & ~pl & ~dob).sum())

# ---------- Troballa 3 (revisada): hi cap el matí? ----------
m = s2[(s2["torn_requerit"] == "mati")
       & (s2["tipus"] != "PLAB")
       & (s2["sense_espai"] != 1)].copy()

# una classe compartida compta una sola vegada
m["clau"] = m["id_compartida"].fillna(m["id_sessio"])
m = m.drop_duplicates("clau")
print("Sessions úniques que demanen matí:", len(m))

# hores-aula per setmana: veiem les setmanes bones, no només la mitjana
h_set = m.groupby("setmana")["durada_min"].sum() / 60
print("\nHores-aula per setmana:")
print(h_set.round(0).to_string())
print("Setmana típica (mediana):", round(h_set.median(), 1),
      "->", round(100 * h_set.median() / 570, 1), "% de 570 h")
print("Setmana màxima:", round(h_set.max(), 1),
      "->", round(100 * h_set.max() / 570, 1), "%")

# simultaneïtat: franges de 30 min, per data
ini = pd.to_datetime(m["h_ini"], format="%H:%M")
m["ini_min"] = ini.dt.hour * 60 + ini.dt.minute
m["fi_min"] = m["ini_min"] + m["durada_min"]
m["slot"] = [list(range(i // 30, -(-f // 30)))
             for i, f in zip(m["ini_min"], m["fi_min"])]
oc = m.explode("slot").groupby(["data", "slot"]).size()
print("\nPic de classes alhora (19 aules disponibles):", oc.max())
top = oc.sort_values(ascending=False).head(8)
for (d, sl), n in top.items():
    print(f"  {d.date()}  {sl*30//60:02d}:{sl*30%60:02d}  ->  {n}")

# ---------- Troballa 2: qui no és al seu torn ----------
t = s2.copy()
ini = pd.to_datetime(t["h_ini"], format="%H:%M")
t["minut"] = ini.dt.hour * 60 + ini.dt.minute
t["torn_real"] = (t["minut"] < 14 * 60 + 30).map({True: "mati", False: "tarda"})
t["fora_torn"] = t["torn_real"] != t["torn_requerit"]

print("\nSessions fora de torn (totes):", t["fora_torn"].sum())

# les fixades (GEI i GEET+GEST de 1r i 2n, i PLAB) no es poden moure
mobles = t[t["fixada"].isna()]
print("Fora de torn i es poden moure:", mobles["fora_torn"].sum())

# per titulació i curs
r = (mobles[mobles["fora_torn"]]
     .groupby("titulacions_curs").size()
     .sort_values(ascending=False))
print("\nTop 10 titulacions/curs més fora de torn:")
print(r.head(10).to_string())

# ---------- Troballa 2b: en quina direcció ----------
print("\nDirecció (només sessions que es poden moure):")
print(mobles[mobles["fora_torn"]]
      .groupby(["torn_real", "torn_requerit"]).size().to_string())

# ---------- Troballa 4: grups que no hi caben ----------
a = pd.read_csv(PAQUET / "aules.csv")
cap = a.set_index("aula")["capacitat"]

g = s2[s2["aula_partida"].notna() & (s2["sense_espai"] != 1)].copy()
g["cap_aula"] = g["aula_partida"].map(cap)       # NaN si l'aula no és a l'inventari
g = g[g["cap_aula"].notna()]
g["excedeix"] = g["alumnes"] > g["cap_aula"]

print("\nSessions amb aula de l'inventari:", len(g))
print("Amb més alumnes que places:", g["excedeix"].sum())   # control: 43
print("Grups (assignatura+grup) afectats:",
      g.loc[g["excedeix"], ["codi", "grup"]].drop_duplicates().shape[0])

pitjors = g[g["excedeix"]].copy()
pitjors["falten"] = pitjors["alumnes"] - pitjors["cap_aula"]
print("\nEls 8 casos amb més places que falten:")
print(pitjors.drop_duplicates(["codi", "grup"])
      .sort_values("falten", ascending=False)
      [["assignatura", "grup", "aula_partida", "alumnes", "cap_aula", "falten"]]
      .head(8).to_string(index=False))

# PAUL en un laboratori de Q6 (no hi poden anar)
tipus = a.set_index("aula")["tipus"]
g["tipus_aula"] = g["aula_partida"].map(tipus)
q6 = g[(g["tipus"] == "PAUL")
       & (g["tipus_aula"] == "Laboratoris docents")
       & g["aula_partida"].str.startswith("Q6")]
print("\nPAUL en laboratori de Q6:", len(q6))                  # control: 54

# ---------- Troballa 5: ocupació per aula ----------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

o = s2[(s2["tipus"] != "PLAB") & (s2["sense_espai"] != 1)].copy()
o["clau"] = o["id_compartida"].fillna(o["id_sessio"])
o = o.drop_duplicates("clau")
o["aula_tag"] = o["aula_partida"].fillna("(sense aula)")
o["hores"] = o["durada_min"] / 60

nsetm = 17
taula = (o.pivot_table(index="aula_tag", columns="dia", values="hores",
                       aggfunc="sum", fill_value=0)
         .reindex(columns=["L", "M", "X", "J", "V"], fill_value=0) / nsetm)

# afegim les aules sense cap sessió (buides)
inv = a[a["tipus"] != "Laboratoris docents"]["aula"]
taula = taula.reindex(sorted(set(taula.index) | set(inv)), fill_value=0)

fig, ax = plt.subplots(figsize=(7, 14))
im = ax.imshow(taula.values, aspect="auto", cmap="YlOrRd")
ax.set_xticks(range(5)); ax.set_xticklabels(taula.columns)
ax.set_yticks(range(len(taula))); ax.set_yticklabels(taula.index, fontsize=6)
fig.colorbar(im, label="hores de classe per setmana (mitjana)")
ax.set_title("Ocupació per aula i dia, 2n semestre (aulari, sense PLAB)")
plt.tight_layout()
plt.savefig(ARREL / "docs" / "ocupacio.png", dpi=130)

tot = taula.sum(axis=1).drop("(sense aula)", errors="ignore")
aul = tot[tot.index.isin(a[a["ordinaria"] == 1]["aula"])]
print("\nAules docents (21), hores/setmana avui:")
print("  les 5 més plenes:\n", aul.sort_values(ascending=False).head(5).round(1).to_string())
print("  les 5 més buides:\n", aul.sort_values().head(5).round(1).to_string())
print("Sessions sense aula (hores/setmana):", round(taula.loc["(sense aula)"].sum(), 1))

# ---------- Troballa 3b: hi cap per mida? ----------
ord_ = a[a["ordinaria"] == 1]
print("\nAules docents per capacitat:", sorted(ord_["capacitat"].tolist()))

setm = h_set.idxmax()
ms = m[m["setmana"] == setm]
print("Setmana analitzada:", setm)

print("\nllindar | sessions | hores/setm | aules >= llindar | hores oferta | % ocupació")
for t_ in [24, 50, 63, 90, 100, 117, 130]:
    dem = ms.loc[ms["alumnes"] >= t_, "durada_min"].sum() / 60
    n = (ord_["capacitat"] >= t_).sum()
    ofe = n * 6 * 5
    ns = (ms["alumnes"] >= t_).sum()
    print(f"{t_:>7} | {ns:>8} | {dem:>10.0f} | {n:>16} | {ofe:>12} | {100*dem/max(ofe,1):>6.0f} %")
