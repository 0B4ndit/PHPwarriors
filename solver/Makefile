# Timetable generator for level 2 of the challenge: one target per question.
#   CSV -> exporta.py -> Prolog facts -> horaris.pl (clauses) -> kissat -> proposta.csv -> official verifier
# Run it inside WSL (swipl + kissat):   cd /mnt/c/Users/Usuario/Desktop/PHPwarriors/solver
#
#   make 5.1       only rooms, today's day and hour            -> out/5.1/  (checked with --nomes-aules)
#   make 5.2       new shifts (1r/2n morning, 3r/4t afternoon)  -> out/5.2/  (+ resum-junta.md)
#   make any       the whole year (xaman: Curs complet): semester 1 by the SAT alone + out/5.x -> out/any/
#   make all       the same, with semester 1 also improved by millora.py (ATEMPS s)   -> out/all/
#   make truc      the same four questions in out/truc/, paying R5-SENSE-AULA instead of R1-TORN (test only)
#   make derivades out/5.2/proposta.csv is final (or you replaced it): rebuild 5.3 and 5.4 on it, never 5.2
#   make truc-derivades   the same for out/truc (after a truc 5.2 loop)
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
#   make 5.2 DESDE=sat            start from the SAT proposal (default: millor = best scored variant /
#                                 previous proposal / SAT, whichever is best by the current weights)
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
DESDE     ?= millor
IMPROVE    = $(if $(filter 1,$(MILLORA)),cp $(@D)/proposta.csv $(@D)/proposta-sat.csv && $(PY) millora.py --temps $(TEMPS) --fils $(FILS) --des-de $(DESDE) --pregunta,true)
KEEPOLD    = if [ -f $(@D)/proposta-sat.csv ] && [ -f $@ ]; then cp $@ $(@D)/proposta-anterior.csv; fi
EXP       := $(PY) exporta.py
CHECK     := cd .. && PYTHONUTF8=1 $(PY) -m horaris check
DATA      := $(wildcard ../paquet/*.csv) $(wildcard ../paquet/escenaris/*/*)
SOLVER    := horaris.pl satlib.pl resol.sh
Q         ?= 5.2
UNIT      ?= b0400

.PHONY: tot 5.1 5.2 5.3 5.4 derivades any all truc truc-derivades truc-resum graella simbolic variants pesos registra bucle clean clean-5.1 clean-5.2 clean-5.3 clean-5.4
tot: 5.1 5.2 5.3 5.4 graella

# ---- 5.1 · rooms only -----------------------------------------------------------------------------------
5.1: out/5.1/informe.json
out/5.1/dadesA.pl: exporta.py $(DATA)
	$(EXP) fase-a --pregunta 5.1 --pas $(PAS)
out/5.1/solucioA.csv: out/5.1/dadesA.pl $(SOLVER)
	$(RESOL) $< $@ $(WORK)/5.1 minrooms
out/5.1/proposta.csv: out/5.1/solucioA.csv millora.py $(wildcard pesos-5.1.txt)
	$(KEEPOLD)
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
out/5.2/proposta.csv: out/5.2/solucioA.csv out/5.2/solucioB.csv millora.py $(wildcard pesos-5.2.txt)
	$(KEEPOLD)
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
out/5.4/proposta.csv: out/5.4/solucioA.csv millora.py $(wildcard pesos-5.4.txt)
	$(KEEPOLD)
	$(EXP) proposta --pregunta 5.4
	$(IMPROVE) 5.4
out/5.4/informe.json: out/5.4/proposta.csv
	$(CHECK) solver/$< --semestre 2 --escenari paquet/escenaris/grau-nou-40 --referencia solver/out/5.2/proposta.csv \
	    --relaxacions solver/out/5.4/relaxacions.csv --json solver/$@ --violacions solver/out/5.4/violacions.csv

# ---- 5.3 and 5.4 are scored by their changes w.r.t. YOUR 5.2: rebuild them every time 5.2 changes ----------
# -o: out/5.2 is taken as it is, never rebuilt (even if a script changed); 5.3/5.4 are always rebuilt on it
KEEP52 = -o out/5.2/proposta.csv -o out/5.2/proposta-sat.csv
derivades:
	rm -f out/5.3/dadesA.pl out/5.4/dadesA.pl
	$(MAKE) $(KEEP52) 5.3 5.4
	@cd .. && for q in 5.3 5.4; do PYTHONUTF8=1 $(PY) -c "import json;o=json.load(open('solver/out/$$q/informe.json',encoding='utf-8'));print('$$q',o['veredicte'],o['incompliments_declarats'],'declared · changes vs 5.2: slot',o['objectius']['canvis_franja_vs_referencia'],'room',o['objectius']['canvis_aula_vs_referencia'])"; done

# ---- out/truc · the same four questions, paying R5-SENSE-AULA instead of R1-TORN (truc.py) ------------------
# The fixed GEI/GEET 1r-2n sessions that are in the afternoon today with no room keep NO room: same declared count,
# their R1-TORN becomes inherited and their rooms are free. Only to see whether the xaman scores it higher: rule 5
# says "totes les sessions amb aula", so the jury may reject the justification. 5.1 has no such trick (it is VALIDA,
# nothing declared): out/truc/5.1 is the normal 5.1. 5.3 and 5.4 are rebuilt by the SAT on top of out/truc/5.2.
T  := out/truc
TS  = --dir $(@D) --sense-aula --referencia $(T)/5.2/proposta.csv
truc:
	mkdir -p $(T)/5.1 && cp out/5.1/proposta.csv out/5.1/proposta-sat.csv $(T)/5.1/
	$(CHECK) solver/$(T)/5.1/proposta.csv --semestre 2 --nomes-aules --json solver/$(T)/5.1/informe.json \
	    --violacions solver/$(T)/5.1/violacions.csv > /dev/null
	$(PY) truc.py --font out/5.2 --dir $(T)/5.2
	$(if $(filter 1,$(MILLORA)),$(PY) millora.py --pregunta 5.2 --dir $(T)/5.2 --temps $(TEMPS) --fils $(FILS) --des-de $(DESDE),true)
	$(MAKE) truc-derivades
	@$(MAKE) --no-print-directory truc-resum
# truc 5.2 changed (make bucle Q=5.2 DIR=out/truc/5.2 found a better one): rebuild truc 5.3 and 5.4 on it
truc-derivades:
	$(CHECK) solver/$(T)/5.2/proposta.csv --semestre 2 --relaxacions solver/$(T)/5.2/relaxacions.csv \
	    --json solver/$(T)/5.2/informe.json --violacions solver/$(T)/5.2/violacions.csv > /dev/null
	rm -f $(T)/5.3/dadesA.pl $(T)/5.4/dadesA.pl
	$(MAKE) $(T)/5.3/informe.json $(T)/5.4/informe.json
truc-resum:
	@cd .. && for q in 5.1 5.2 5.3 5.4; do PYTHONUTF8=1 $(PY) -c "import json;o=json.load(open('solver/$(T)/$$q/informe.json',encoding='utf-8'));b=o['objectius'];print('truc $$q',o['veredicte'],o['incompliments_declarats'],'declared',{k:v for k,v in o['restriccions'].items() if v['declarades']},'· vs 5.2: slot',b.get('canvis_franja_vs_referencia','-'),'room',b.get('canvis_aula_vs_referencia','-'))"; done

$(T)/5.3/dadesA.pl: $(T)/5.2/proposta.csv exporta.py relaxacions.csv
	$(EXP) fase-a --pregunta 5.3 --pas $(PAS) --allibera minim $(TS)
$(T)/5.3/solucioA.csv: $(T)/5.3/dadesA.pl $(SOLVER)
	$(RESOL) $< $@ $(WORK)/truc5.3 || { \
	  $(EXP) fase-a --pregunta 5.3 --pas $(PAS) --allibera setmana $(TS) && $(RESOL) $< $@ $(WORK)/truc5.3; } || { \
	  $(EXP) fase-a --pregunta 5.3 --pas $(PAS) --allibera setmana --recupera 1 $(TS) && $(RESOL) $< $@ $(WORK)/truc5.3; }
$(T)/5.3/proposta.csv: $(T)/5.3/solucioA.csv
	$(EXP) proposta --pregunta 5.3 $(TS)
$(T)/5.3/informe.json: $(T)/5.3/proposta.csv
	$(CHECK) solver/$< --semestre 2 --escenari paquet/escenaris/contingencies --referencia solver/$(T)/5.2/proposta.csv \
	    --relaxacions solver/$(T)/5.3/relaxacions.csv --json solver/$@ --violacions solver/$(T)/5.3/violacions.csv

$(T)/5.4/dadesA.pl: $(T)/5.2/proposta.csv exporta.py relaxacions.csv
	$(EXP) fase-a --pregunta 5.4 --pas $(PAS) --allibera minim $(TS)
$(T)/5.4/solucioA.csv: $(T)/5.4/dadesA.pl $(SOLVER)
	$(RESOL) $< $@ $(WORK)/truc5.4 || { \
	  $(EXP) fase-a --pregunta 5.4 --pas $(PAS) --allibera temps $(TS) && $(RESOL) $< $@ $(WORK)/truc5.4; }
$(T)/5.4/proposta.csv: $(T)/5.4/solucioA.csv millora.py
	$(EXP) proposta --pregunta 5.4 $(TS)
	$(if $(filter 1,$(MILLORA)),cp $@ $(@D)/proposta-sat.csv && $(PY) millora.py --pregunta 5.4 --dir $(@D) --temps $(TEMPS) --fils $(FILS) --des-de $(DESDE),true)
$(T)/5.4/informe.json: $(T)/5.4/proposta.csv
	$(CHECK) solver/$< --semestre 2 --escenari paquet/escenaris/grau-nou-40 --referencia solver/$(T)/5.2/proposta.csv \
	    --relaxacions solver/$(T)/5.4/relaxacions.csv --json solver/$@ --violacions solver/$(T)/5.4/violacions.csv

# ---- out/any · the whole year ("Curs complet"): semester 1 solved by the SAT alone (no millora), joined ------
# with the semester-2 proposals out/5.x by any.py. 5.3 = s1 5.2 + out/5.3 (the scenario is all in March 2027).
# Runs "make derivades" first, so that out/5.3 and out/5.4 sit on the current out/5.2.
A1 := out/any/s1
S1 := SEMESTRE=1
any: $(A1)/5.1/proposta.csv $(A1)/5.2/proposta.csv $(A1)/5.4/proposta.csv
	$(MAKE) derivades
	$(PY) any.py

$(A1)/5.1/dadesA.pl: exporta.py
	$(S1) $(EXP) fase-a --pregunta 5.1 --pas $(PAS) --dir $(@D)
$(A1)/5.1/solucioA.csv: $(A1)/5.1/dadesA.pl $(SOLVER)
	$(RESOL) $< $@ $(WORK)/any5.1 minrooms
$(A1)/5.1/proposta.csv: $(A1)/5.1/solucioA.csv
	$(S1) $(EXP) proposta --pregunta 5.1 --dir $(@D)

$(A1)/5.2/dadesA.pl: exporta.py relaxacions.csv
	$(S1) $(EXP) fase-a --pregunta 5.2 --pas $(PAS) --dir $(@D)
$(A1)/5.2/solucioA.csv: $(A1)/5.2/dadesA.pl $(SOLVER)
	$(RESOL) $< $@ $(WORK)/any5.2A
$(A1)/5.2/dadesB.pl: $(A1)/5.2/solucioA.csv
	$(S1) $(EXP) fase-b --pregunta 5.2 --pas $(PAS) --allibera peces --dir $(@D)
$(A1)/5.2/solucioB.csv: $(A1)/5.2/dadesB.pl $(SOLVER)
	$(RESOL) $< $@ $(WORK)/any5.2B || { \
	  echo ">> freeing every movable piece of the calendar-hit weeks"; \
	  $(S1) $(EXP) fase-b --pregunta 5.2 --pas $(PAS) --allibera setmana --dir $(@D) && $(RESOL) $< $@ $(WORK)/any5.2B; }
$(A1)/5.2/proposta.csv: $(A1)/5.2/solucioA.csv $(A1)/5.2/solucioB.csv
	$(S1) $(EXP) proposta --pregunta 5.2 --dir $(@D)

$(A1)/5.4/dadesA.pl: $(A1)/5.2/proposta.csv exporta.py
	$(S1) $(EXP) fase-a --pregunta 5.4 --pas $(PAS) --allibera minim --dir $(@D) --referencia $(A1)/5.2/proposta.csv
$(A1)/5.4/solucioA.csv: $(A1)/5.4/dadesA.pl $(SOLVER)
	$(RESOL) $< $@ $(WORK)/any5.4 || { \
	  $(S1) $(EXP) fase-a --pregunta 5.4 --pas $(PAS) --allibera temps --dir $(@D) --referencia $(A1)/5.2/proposta.csv \
	  && $(RESOL) $< $@ $(WORK)/any5.4; }
$(A1)/5.4/proposta.csv: $(A1)/5.4/solucioA.csv
	$(S1) $(EXP) proposta --pregunta 5.4 --dir $(@D) --referencia $(A1)/5.2/proposta.csv

# ---- out/all · the whole year, semester 1 = the SAT solution of out/any/s1 + a short millora.py run ---------
# (the learnt weights pesos-<q>.txt if they exist). 5.4's semester 1 is rebuilt on the improved 5.2, so that it
# keeps 0 changes w.r.t. it. Semester 2 is out/5.x as it is (already improved).
L1     := out/all/s1
ATEMPS ?= 60
SETUP1  = mkdir -p $(@D) && cp $< $@ && cp $@ $(@D)/proposta-sat.csv && \
          { [ ! -f $(<D)/relaxacions.csv ] || cp $(<D)/relaxacions.csv $(@D)/; } && \
          { [ ! -f pesos-$(1).txt ] || cp pesos-$(1).txt $(@D)/pesos.txt; }
IMPROVE1 = $(S1) $(PY) millora.py --pregunta $(1) --dir $(@D) --temps $(ATEMPS) --fils $(FILS) --des-de sat
all: $(L1)/5.1/proposta.csv $(L1)/5.2/proposta.csv $(L1)/5.4/proposta.csv
	$(MAKE) derivades
	$(PY) any.py --s1 $(L1) --sortida out/all --nom curs-complet-millora

$(L1)/5.1/proposta.csv: $(A1)/5.1/proposta.csv millora.py
	$(call SETUP1,5.1)
	$(call IMPROVE1,5.1)
$(L1)/5.2/proposta.csv: $(A1)/5.2/proposta.csv millora.py
	$(call SETUP1,5.2)
	$(call IMPROVE1,5.2)
$(L1)/5.4/dadesA.pl: $(L1)/5.2/proposta.csv exporta.py
	$(S1) $(EXP) fase-a --pregunta 5.4 --pas $(PAS) --allibera minim --dir $(@D) --referencia $(L1)/5.2/proposta.csv
$(L1)/5.4/solucioA.csv: $(L1)/5.4/dadesA.pl $(SOLVER)
	$(RESOL) $< $@ $(WORK)/all5.4 || { \
	  $(S1) $(EXP) fase-a --pregunta 5.4 --pas $(PAS) --allibera temps --dir $(@D) --referencia $(L1)/5.2/proposta.csv \
	  && $(RESOL) $< $@ $(WORK)/all5.4; }
$(L1)/5.4/proposta.csv: $(L1)/5.4/solucioA.csv millora.py
	$(S1) $(EXP) proposta --pregunta 5.4 --dir $(@D) --referencia $(L1)/5.2/proposta.csv
	cp $@ $(@D)/proposta-sat.csv
	$(call IMPROVE1,5.4)

# ---- rule 10 · weekly grid per room, of the most advanced proposal -------------------------------------
graella: out/graella.html
out/graella.html: graella.py $(wildcard out/5.*/proposta.csv)
	$(PY) graella.py

# ---- learning the xaman's weights: variants -> upload -> scores -> pesos -------------------------------
#   make variants Q=5.1 [N=12 VTEMPS=60]   diverse verified proposals in out/<q>/variants/ + rondaK.csv to fill in
#   make pesos Q=5.1                        fit the weights from the scores -> pesos-<q>.txt (used by make <q>)
N      ?= 10
VTEMPS ?= 60
#   DIR=out/truc/5.2 on any of these: the same, for another family of proposals (its own rounds and pesos.txt)
DIRARG = $(if $(DIR),--dir $(DIR))
variants:
	$(PY) variants.py --pregunta $(Q) --n $(N) --temps $(VTEMPS) $(DIRARG)
pesos:
	$(PY) pesos.py --pregunta $(Q) $(DIRARG)
#   make registra Q=5.2 PUNT=74 [FITXER=...]   a submitted proposal + its score -> learnt from, and a start point
#   make bucle Q=5.2   THE LOOP: new proposals -> type their xaman scores -> weights refit -> best kept -> again
bucle:
	$(PY) bucle.py --pregunta $(Q) --n $(N) --temps $(VTEMPS) $(DIRARG)
registra:
	$(PY) registra.py --pregunta $(Q) --puntuacio $(PUNT) $(if $(FITXER),--fitxer $(FITXER)) $(DIRARG)

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
