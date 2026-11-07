#!/usr/bin/env python3
"""
exportar_yaml.py - Exportador i visualitzador d'horaris en YAML
Permet analitzar l'horari d'un dia/setmana concret, aplicant opcionalment
un fitxer de proposta (solver) sobre la base de dades DuckDB.
"""

import argparse
import sys
from pathlib import Path
import duckdb
import pandas as pd
import yaml


def carregar_dades(db_path: str, proposta_csv: str = None) -> pd.DataFrame:
    """Carrega les sessions de DuckDB i sobreescriu dia/hora/aula si hi ha proposta."""
    con = duckdb.connect(db_path, read_only=True)
    df = con.execute("SELECT * FROM sessions").df()
    con.close()

    # Normalitzar noms d'aules
    df["aula_efectiva"] = df["aula_partida"].fillna("SENSE_AULA")

    # Si s'ha passat una proposta del solver, aplicar el desplaçament
    if proposta_csv and Path(proposta_csv).exists():
        print(f"Applying proposal override from: {proposta_csv}")
        df_prop = pd.read_csv(proposta_csv, dtype=str)

        # La proposta sol tenir: id_sessio, dia, h_ini, aula
        prop_dict = df_prop.set_index("id_sessio").to_dict(orient="index")

        for idx, row in df.iterrows():
            s_id = row["id_sessio"]
            if s_id in prop_dict:
                p = prop_dict[s_id]
                if "dia" in p and pd.notna(p["dia"]):
                    df.at[idx, "dia"] = p["dia"]
                if "h_ini" in p and pd.notna(p["h_ini"]):
                    # Recalcular h_fi segons durada_min si ha canviat l'hora
                    df.at[idx, "h_ini"] = p["h_ini"]
                if "aula" in p and pd.notna(p["aula"]):
                    df.at[idx, "aula_efectiva"] = p["aula"]

    return df


def filtrar_sessions(
    df: pd.DataFrame,
    dia: str = None,
    setmana: str = None,
    data: str = None,
    semestre: str = "C/2",
    grau: str = None,
    aula: str = None,
) -> pd.DataFrame:
    """Filtra el DataFrame segons els paràmetres passats per CLI."""
    cond = pd.Series(True, index=df.index)

    if semestre:
        cond &= df["semestre"] == semestre
    if data:
        cond &= df["data"] == data
    if setmana:
        cond &= df["setmana"] == setmana
    if dia and not data:
        cond &= df["dia"] == dia
    if grau:
        cond &= df["titulacions_curs"].str.contains(grau, na=False, case=False)
    if aula:
        cond &= df["aula_efectiva"] == aula

    return df[cond].copy()


def estructurar_yaml(df_filtrat: pd.DataFrame, meta_info: dict) -> dict:
    """Converteix el DataFrame filtrat en una estructura jeràrquica neta per a YAML."""
    # Ordenar cronològicament per hora i aula
    df_filtrat = df_filtrat.sort_values(by=["h_ini", "aula_efectiva", "codi"])

    horari_per_franja = {}

    for _, row in df_filtrat.iterrows():
        franja = f"{row['h_ini']} - {row['h_fi']}"

        sessio_dict = {
            "id_sessio": str(row["id_sessio"]),
            "activitat_id": str(row["activitat_id"]),
            "codi": str(row["codi"]),
            "assignatura": str(row["assignatura"]),
            "tipus": str(row["tipus"]),
            "grup": str(row["grup"]),
            "aula": str(row["aula_efectiva"]),
            "alumnes": int(row["alumnes"]) if pd.notna(row["alumnes"]) else 0,
            "cohorts": (
                str(row["titulacions_curs"])
                if pd.notna(row["titulacions_curs"])
                else ""
            ),
            "docents": (
                str(row["docents"]) if pd.notna(row["docents"]) else "SENSE_DOCENT"
            ),
            "fixada": str(row["fixada"]) if pd.notna(row["fixada"]) else "",
        }

        if franja not in horari_per_franja:
            horari_per_franja[franja] = []

        horari_per_franja[franja].append(sessio_dict)

    # Estructura final del document YAML
     fitxer_yaml = {
        "meta": {
            "semestre": meta_info.get("semestre"),
            "setmana": meta_info.get("setmana") or "Totes",
            "dia": meta_info.get("dia") or "Tots",
            "data": meta_info.get("data") or "N/A",
            "total_sessions": len(df_filtrat),
            "aules_ocupades_uniques": int(
                df_filtrat["aula_efectiva"].nunique()
            ),
            "total_alumnes_afectats": int(df_filtrat["alumnes"].sum()),
        },
        "horari": horari_per_franja,
    }

    return fitxer_yaml


def main():
    parser = argparse.ArgumentParser(
        description="Exportador d'horaris en format YAML des de DuckDB / Propostes."
    )
    parser.add_argument(
        "--db",
        default="dades/paquet.duckdb",
        help="Ruta a la BBDD DuckDB (default: dades/paquet.duckdb)",
    )
    parser.add_argument(
        "--proposta",
        default=None,
        help="Fitxer CSV de proposta del solver per comparar (opcional)",
    )
    parser.add_argument(
        "-d",
        "--dia",
        choices=["L", "M", "X", "J", "V"],
        help="Dia de la setmana (L, M, X, J, V)",
    )
    parser.add_argument(
        "-w",
        "--setmana",
        help="Setmana ISO (ex: 2027-W09 o 2026-W40)",
    )
    parser.add_argument(
        "--data",
        help="Data exacta ISO (ex: 2027-03-02)",
    )
    parser.add_argument(
        "-s",
        "--semestre",
        default="C/2",
        help="Semestre (default: C/2)",
    )
    parser.add_argument(
        "-g",
        "--grau",
        help="Filtrar per titulació (ex: GEI, GEQ, GED)",
    )
    parser.add_argument(
        "-a",
        "--aula",
        help="Filtrar per aula (ex: Q1/1011)",
    )
    parser.add_argument(
        "-o",
        "--out",
        help="Fitxer YAML d'eixida (si no s'indica, s'imprimeix per pantalla)",
    )

    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Error: No s'ha trobat la base de dades '{args.db}'.")
        sys.exit(1)

    df = carregar_dades(args.db, args.proposta)

    df_filtrat = filtrar_sessions(
        df,
        dia=args.dia,
        setmana=args.setmana,
        data=args.data,
        semestre=args.semestre,
        grau=args.grau,
        aula=args.aula,
    )

    if df_filtrat.empty:
        print("No s'ha trobat cap sessió amb els filtres indicats.")
        sys.exit(0)

    meta_info = {
        "semestre": args.semestre,
        "setmana": args.setmana,
        "dia": args.dia,
        "data": args.data,
    }

    estructures_yaml = estructurar_yaml(df_filtrat, meta_info)
    yaml_text = yaml.dump(
        estructures_yaml, sort_keys=False, allow_unicode=True, default_flow_style=False
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(yaml_text)
        print(
            f"Exportades {len(df_filtrat)} sessions correctament a '{args.out}'."
        )
    else:
        print(yaml_text)


if __name__ == "__main__":
    main()