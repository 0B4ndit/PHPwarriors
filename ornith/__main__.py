"""Línia d'ordres d'Ornith.

    python -m ornith "on té classe el grup 81 dimarts?"           # pregunta a l'agent (cal UTH_KEY a .env)
    python -m ornith eina horari '{"grup": "81", "dia": "M"}'      # una eina sola, sense LLM
    python -m ornith imprevist-aula Q1/1003 2027-03-10 --motiu "Projector avariat" [--fins AAAA-MM-DD] [--desa]
    python -m ornith imprevist-cancellacio S11527 2027-03-19 --motiu "Cancel·lada" [--desa]
"""
import argparse
import json
import sys


def _imprimeix(r):
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))


def _imprevist(r, desa):
    from .imprevist import desa_registre
    print(f"Imprevist: {r.get('motiu')} · vista {r['vista']}")
    print(f"Validat amb el verificador: {'SÍ' if r['validat'] else 'NO'} "
          f"({r['validacio']['veredicte_despres']}; violacions noves: {r['validacio']['violacions_noves']})")
    for c in r["canvis"]:
        print(f"  {c['id_sessio']} {c['codi']} {c['grup']}: {c['de']}  ->  {c['a']}")
    for x in r["sense_solucio"]:
        print(f"  SENSE SOLUCIÓ {x['id_sessio']} {x['grup']} ({x['on']}): {x['per_que']}")
    for x in r.get("relaxacions_declarades", []):
        print(f"  Relaxació declarada {x['restriccio']}: {', '.join(x['sessions'])}")
    print("\nAvisos (redactats, no enviats):")
    for a in r["avisos"]:
        print(f"- {a['id_sessio']}\n  Docent: {a['docent']}\n  Estudiants: {a['estudiants']}\n"
              f"  Gestió Acadèmica: {a['gestio_academica']}")
    if desa and r["registre"]:
        print(f"\nRegistre de canvis desat a {desa_registre(r['registre'])}")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "eina":
        from . import eines
        _imprimeix(eines.executa(argv[1], json.loads(argv[2]) if len(argv) > 2 else {}))
        return 0
    if argv[0] in ("imprevist-aula", "imprevist-cancellacio"):
        from . import eines
        ap = argparse.ArgumentParser(prog=f"python -m ornith {argv[0]}")
        ap.add_argument("objecte")
        ap.add_argument("data")
        ap.add_argument("--fins")
        ap.add_argument("--h-ini")
        ap.add_argument("--h-fi")
        ap.add_argument("--motiu", default="")
        ap.add_argument("--vista", default="5.2")
        ap.add_argument("--desa", action="store_true", help="afegeix les files a dades/registre_canvis.csv")
        a = ap.parse_args(argv[1:])
        if argv[0] == "imprevist-aula":
            r = eines.executa("imprevist_aula", dict(aula=a.objecte, data_ini=a.data, data_fi=a.fins, h_ini=a.h_ini,
                                                     h_fi=a.h_fi, motiu=a.motiu, vista=a.vista))
        else:
            r = eines.executa("imprevist_cancellacio", dict(id_sessio=a.objecte, fins=a.data, motiu=a.motiu,
                                                            vista=a.vista))
        if "error" in r:
            print("Error:", r["error"])
            return 1
        _imprevist(r, a.desa)
        return 0
    from .agent import format_text, respon
    r = respon(" ".join(argv))
    print(format_text(r))
    for e in r["eines"]:
        print(f"  · {e['eina']} {json.dumps(e['arguments'], ensure_ascii=False)}"
              + (f"  ERROR: {e['error']}" if e.get("error") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
