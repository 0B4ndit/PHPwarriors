"""Ornith: l'assistent del nivell 3 (IA) per a Gestió Acadèmica.

Principi: tota xifra, aula o sessió que diu Ornith surt d'una eina determinista sobre les dades del paquet o
del verificador oficial (horaris.check.avalua). El LLM només tria eines i redacta; una comprovació posterior
rebutja les respostes que citen aules o sessions que no han sortit de cap eina.

    from ornith.agent import parlar, respon      # xat (cal UTH_KEY a .env)
    from ornith import eines                     # les eines, sense LLM
"""
