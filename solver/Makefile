# Timetable generator for level 2 of the challenge: one target per question.
#   CSV -> exporta.py -> Prolog facts -> horaris.pl (clauses) -> kissat -> proposta.csv -> official verifier
# Run it inside WSL (swipl + kissat):   cd /mnt/c/Users/Usuario/Desktop/PHPwarriors/solver
#
#   make 5.1       only rooms, today's day and hour            -> out/5.1/  (checked with --nomes-aules)
#   make 5.2       new shifts (1r/2n morning, 3r/4t afternoon)  -> out/5.2/  (+ resum-junta.md)
#   make 5.3       contingencies, on top of out/5.2             -> out/5.3/  (checked with --referencia 5.2)
#   make 5.4       grau-nou-40, on top of out/5.2               -> out/5.4/
#   make graella   weekly grid per room of the most advanced proposal (rule 10) -> out/graella.html
#   make tot       all of the above
#
# Each out/<q>/ holds what you hand in: proposta.csv, relaxacions.csv, informe.json, violacions.csv
# (and the facts dades*.pl / solutions solucio*.csv the solver used).
#
#   make 5.2 MAXCANVIS=300        fixed bound on units that change day/hour (default: min, then loosen)
#   make 5.2 PAS=30               30-minute start grid instead of 15
#   make 5.2 MILLORA=0            skip millora.py (keep the raw SAT proposal)
#   make 5.2 TEMPS=600 FILS=12    longer search on more cores (default 180 s x 8 workers)
#   make simbolic Q=5.2 UNIT=b0400   readable clauses about one unit -> out/<q>/clauses-<unit>.txt
#   make clean-5.3 / make clean   remove one question's files / everything

PAS       ?= 15
WORK      ?= /tmp/horaris-sat
PY        ?= python3
SWIPL     ?= swipl
MAXCANVIS ?=
export BOUNDS = $(MAXCANVIS)
RESOL     := sh resol.sh
MILLORA   ?= 1
TEMPS     ?= 180
FILS      ?= 8
IMPROVE    = $(if $(filter 1,$(MILLORA)),cp $(@D)/proposta.csv $(@D)/proposta-sat.csv && $(PY) millora.py --temps $(TEMPS) --fils $(FILS) --pregunta,true)
EXP       := $(PY) exporta.py
CHECK     := cd .. && PYTHONUTF8=1 $(PY) -m horaris check
DATA      := $(wildcard ../paquet/*.csv) $(wildcard ../paquet/escenaris/*/*)
SOLVER    := horaris.pl satlib.pl resol.sh
Q         ?= 5.2
UNIT      ?= b0400

.PHONY: tot 5.1 5.2 5.3 5.4 graella simbolic clean clean-5.1 clean-5.2 clean-5.3 clean-5.4
tot: 5.1 5.2 5.3 5.4 graella

# ---- 5.1 · rooms only -----------------------------------------------------------------------------------
5.1: out/5.1/informe.json
out/5.1/dadesA.pl: exporta.py $(DATA)
	$(EXP) fase-a --pregunta 5.1 --pas $(PAS)
out/5.1/solucioA.csv: out/5.1/dadesA.pl $(SOLVER)
	$(RESOL) $< $@ $(WORK)/5.1 minrooms
out/5.1/proposta.csv: out/5.1/solucioA.csv millora.py
	$(EXP) proposta --pregunta 5.1
	$(IMPROVE) 5.1
out/5.1/informe.json: out/5.1/proposta.csv
	$(CHECK) solver/$< --semestre 2 --nomes-aules --json solver/$@ --violacions solver/out/5.1/violacions.csv

# ---- 5.2 · new shifts: phase A (weekly patterns) + phase B (calendar repair) --------------------------------
5.2: out/5.2/informe.json out/5.2/resum-junta.md
out/5.2/dadesA.pl: exporta.py relaxacions.csv $(DATA)
	$(EXP) fase-a --pregunta 5.2 --pas $(PAS)
out/5.2/solucioA.csv: out/5.2/dadesA.pl $(SOLVER)
	$(RESOL) $< $@ $(WORK)/5.2A
out/5.2/dadesB.pl: out/5.2/solucioA.csv
	$(EXP) fase-b --pregunta 5.2 --pas $(PAS) --allibera peces
out/5.2/solucioB.csv: out/5.2/dadesB.pl $(SOLVER)
	$(RESOL) $< $@ $(WORK)/5.2B || { \
	  echo ">> freeing only the calendar-hit pieces is UNSAT: freeing every movable piece of those weeks"; \
	  $(EXP) fase-b --pregunta 5.2 --pas $(PAS) --allibera setmana && $(RESOL) $< $@ $(WORK)/5.2B; }
out/5.2/proposta.csv: out/5.2/solucioA.csv out/5.2/solucioB.csv millora.py
	$(EXP) proposta --pregunta 5.2
	$(IMPROVE) 5.2
out/5.2/informe.json: out/5.2/proposta.csv
	$(CHECK) solver/$< --semestre 2 --relaxacions solver/out/5.2/relaxacions.csv \
	    --json solver/$@ --violacions solver/out/5.2/violacions.csv
out/5.2/resum-junta.md: out/5.2/informe.json resum.py
	$(PY) resum.py --dir out/5.2

# ---- 5.3 · contingencies on top of 5.2 ------------------------------------------------------------------
5.3: out/5.3/informe.json
out/5.3/dadesA.pl: out/5.2/proposta.csv exporta.py relaxacions.csv
	$(EXP) fase-a --pregunta 5.3 --pas $(PAS) --allibera minim
out/5.3/solucioA.csv: out/5.3/dadesA.pl $(SOLVER)
	$(RESOL) $< $@ $(WORK)/5.3 || { \
	  echo ">> freeing every movable piece of the weeks of the events"; \
	  $(EXP) fase-a --pregunta 5.3 --pas $(PAS) --allibera setmana && $(RESOL) $< $@ $(WORK)/5.3; } || { \
	  echo ">> recovering the cancelled session the following week"; \
	  $(EXP) fase-a --pregunta 5.3 --pas $(PAS) --allibera setmana --recupera 1 && $(RESOL) $< $@ $(WORK)/5.3; }
out/5.3/proposta.csv: out/5.3/solucioA.csv
	$(EXP) proposta --pregunta 5.3
out/5.3/informe.json: out/5.3/proposta.csv
	$(CHECK) solver/$< --semestre 2 --escenari paquet/escenaris/contingencies --referencia solver/out/5.2/proposta.csv \
	    --relaxacions solver/out/5.3/relaxacions.csv --json solver/$@ --violacions solver/out/5.3/violacions.csv

# ---- 5.4 · grau-nou-40 on top of 5.2 -------------------------------------------------------------------
5.4: out/5.4/informe.json
out/5.4/dadesA.pl: out/5.2/proposta.csv exporta.py relaxacions.csv
	$(EXP) fase-a --pregunta 5.4 --pas $(PAS) --allibera minim
out/5.4/solucioA.csv: out/5.4/dadesA.pl $(SOLVER)
	$(RESOL) $< $@ $(WORK)/5.4 || { \
	  echo ">> the new degree may also change day/hour inside each week"; \
	  $(EXP) fase-a --pregunta 5.4 --pas $(PAS) --allibera temps && $(RESOL) $< $@ $(WORK)/5.4; }
out/5.4/proposta.csv: out/5.4/solucioA.csv millora.py
	$(EXP) proposta --pregunta 5.4
	$(IMPROVE) 5.4
out/5.4/informe.json: out/5.4/proposta.csv
	$(CHECK) solver/$< --semestre 2 --escenari paquet/escenaris/grau-nou-40 --referencia solver/out/5.2/proposta.csv \
	    --relaxacions solver/out/5.4/relaxacions.csv --json solver/$@ --violacions solver/out/5.4/violacions.csv

# ---- rule 10 · weekly grid per room, of the most advanced proposal -------------------------------------
graella: out/graella.html
out/graella.html: graella.py $(wildcard out/5.*/proposta.csv)
	$(PY) graella.py

# ---- tools -----------------------------------------------------------------------------------------------
simbolic: out/$(Q)/dadesA.pl
	mkdir -p $(WORK)/S
	$(SWIPL) -g main -t halt horaris.pl -- $< - $(WORK)/S simbolic unit=$(UNIT)
	cp $(WORK)/S/clauses out/$(Q)/clauses-$(UNIT).txt
	@echo "readable clauses that mention $(UNIT): out/$(Q)/clauses-$(UNIT).txt"

clean-%:
	rm -rf out/$* $(WORK)/$**
clean:
	rm -rf out $(WORK)
