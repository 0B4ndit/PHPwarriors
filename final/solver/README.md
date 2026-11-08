# solver/ — SAT timetable (Prolog → kissat), level 2: questions 5.1 · 5.2 · 5.3 · 5.4

> **`final/`: the version for the new verifier (xaman c5dd933).** `final/horaris` is the updated official verifier
> and `final/paquet` is the same data. Two rule changes from 07/11/2026:
> - A fixed GEI/GEET 1r–2n session that isn't moved keeps an *inherited* R1-TORN, whatever room we give it. The 458
>   declared R1-TORN are gone.
> - A fixed session whose own room is closed by the 5.3 scenario may change room without counting as moved. The 10
>   R1-FIXADA/R7-PLAB of 5.3 are gone.
>
> `exporta.py` now declares only the hand-written, proven relaxations (`relaxacions.csv`: S04526). New scoring:
> VALIDA 70–100, with relaxations 40–69 (fewer is better), not valid 0–39.
>
> Same workflow as before, from `final/solver` in WSL: `make 5.1` … `make 5.4`, `make derivades`,
> `make bucle Q=5.2` (variants + your scores + weights), `python3 millora.py --pregunta 5.2 --temps 1800 --fils 12
> --des-de millor`. It uses its own scratch folder (`/tmp/horaris-final`), so it can't clash with `solver/` runs.
> The `truc` family is obsolete here: the 458 cost nothing now.

One `make` target per question of the enunciat (§5). Each one builds its own facts and clauses, solves them with
kissat, writes the proposal in the official format and runs the **jury's verifier** on it, exactly as it will be
checked.

```
paquet/*.csv ─exporta.py─▶ out/<q>/dades*.pl ─horaris.pl─▶ clauses ─kissat─▶ out/<q>/solucio*.csv
                                         exporta.py proposta ─▶ out/<q>/proposta.csv + relaxacions.csv ─▶ verifier
```

## Run it (WSL: `swipl`, `kissat`, `python3 ≥ 3.10`)

```bash
cd /mnt/c/Users/Usuario/Desktop/PHPwarriors/solver
make 5.1        # rooms only (today's day and hour)                 ~10 s
make 5.2        # new shifts + summary for the Junta                ~3-5 min
make 5.3        # contingencies, on top of out/5.2                  ~30 s   (runs 5.2 first if needed)
make 5.4        # grau-nou-40, on top of out/5.2                    ~30 s   (runs 5.2 first if needed)
make graella    # rule 10: weekly grid per room of the most advanced proposal -> out/graella.html
make tot        # all of it
make derivades  # 5.2 changed (millora run, bucle, a file you copied in): rebuild 5.3 and 5.4 on it   ~5 min
```

**5.3 and 5.4 are scored by their changes with respect to *your* 5.2.** Every time `out/5.2/proposta.csv` changes,
run `make derivades`. Otherwise 5.3/5.4 still sit on the old 5.2 and show thousands of "changes". It never rebuilds
5.2 itself. Order to submit: 5.2 first, then 5.3 and 5.4 built on that same file.

What to hand in for each question is in `out/<q>/`:

| File | |
|---|---|
| `proposta.csv` | `id_sessio,dia,h_ini,aula` (+ `data` in 5.3, for the recovered session) |
| `relaxacions.csv` | declared relaxations, each with its justification (none in 5.1) |
| `informe.json`, `violacions.csv` | the verifier's output (`--json`, `--violacions`) |
| `resum-junta.md` | 5.2 only: the one-page summary for the Junta Permanent |

Options: `make 5.2 MAXCANVIS=300` (fixed bound on units that change day/hour), `make 5.2 PAS=30` (30-minute start
grid), `make simbolic Q=5.2 UNIT=b0400` (every clause about one unit, readable), `make clean-5.3`, `make clean`.
After changing an option, `make clean-<q>` so that the facts are rebuilt.

## Results (run of 07/11/2026, after `millora.py`, 8 workers x 180 s)

| Q | Verdict | Changes | hores mortes (min) | desplaç. aula / edifici | r6 extra / passadís | canvis aula |
|---|---|---|---:|---:|---:|---:|
| **5.1** | **VALIDA** | 0 slots | 72,930 (fixed by today's hours) | 1,970 / 0 | **32** / 671 | 452 |
| **5.2** | **VALIDA AMB RELAXACIONS** (459) | 2,213 slots | **49,515** | 1,665 / 0 | 84 / 548 | 564 |
| **5.3** | **VALIDA AMB RELAXACIONS** (469) | vs 5.2: **1 slot** (S11527 recovered), 41 rooms | 49,575 | 1,681 / 0 | 89 / 567 | 574 |
| **5.4** | **VALIDA AMB RELAXACIONS** (459) | vs 5.2: **0 slots, 0 rooms** | 50,415 | 1,665 / 0 | 84 / 548 | 564 |

Raw SAT proposal → improved: 5.2 hores mortes 138,090 → 49,515 (−64 %), desplaçaments 3,418 → 1,665, edifici 6 → 0,
r6 114 → 84 and 1,906 → 548 (slot changes 2,008 → 2,213, second in the order); 5.1 r6 extra 96 → 32, desplaçaments
3,569 → 1,970, edifici 17 → 0, passadís 1,627 → 671 (room changes w.r.t. today 97 → 452, last in the order).
The search is time-limited and random: two runs give slightly different (always valid) results.

Starting point (today, semester 2): R1-TORN 2,008 · R5-SENSE-AULA 4,541 · R3-AFORAMENT 43 · R3-TIPUS 54 · R2-FINESTRA 13.

## What each question solves

* **5.1** — `--nomes-aules`: every unit has its day and start fixed (`fixedStart`), only `room/2` is free. Option
  `minrooms`: a unit whose current room is still allowed must keep it.
* **5.2** — phase A gives each *block* (an activity + everything it shares a class with) one weekly pattern; phase B
  re-places, inside its week, every piece whose pattern lands on a holiday / stoppage / evaluation week, first only
  those pieces, then (if UNSAT) every movable piece of those weeks, preferring the phase-A pattern.
* **5.3** — every piece (block × week) is frozen at its 5.2 slot and room except the ones the scenario touches:
  in a closed room (Q3/0013 15–19/3, Q1/1003 10/3: `closedRoom/5`, rule `noClassInAClosedRoom`), newly over capacity
  (TE/21 of 106047 → 130 students), or cancelled (S11527: recovered on a later lective day up to 19/3, same week first).
  Fixed groups / PLAB in a closed room keep their time and only change room.
* **5.4** — every 5.2 piece frozen; the grau-nou blocks keep their (morning) day and hour and get rooms. If that were
  UNSAT, they would be allowed to change day/hour inside each week (`--allibera temps`).

Every solve starts with the smallest possible number of changes (`min`: only units whose preferred slot is no longer
allowed may move) and loosens it step by step (`resol.sh`: min, min+1, +2, +3, +5, +10, +20, +60, no bound).

## Improving the objectives (rule 9): `millora.py`

The SAT solve only guarantees validity and the fewest changes of day/hour. Afterwards `millora.py` improves the
rule-9 objectives **in priority order** (lexicographic: what matters is the first objective that changes):

* 5.2 / 5.4: `hores_mortes_min` › `canvis_franja` › `desplacaments_aula` › `desplacaments_edifici` ›
  `r6_aules_te_extra_per_grup` › `r6_canvis_te_paul_fora_passadis` › `canvis_aula`
* 5.1 (the brief's order: base room, consecutive changes, changes w.r.t. today): `r6_aules_te_extra_per_grup` ›
  `desplacaments_aula` › `desplacaments_edifici` › `r6_canvis_te_paul_fora_passadis` › `canvis_aula`

Three stages:

1. **Greedy descent.** *day/hour*: each weekly unit (the sessions of a block with the same weekday and hour) tries
   the slots right before / after another class of one of its groups, or back to today's slot; *rooms*: with times
   fixed, each unit tries every allowed room. Keeps the best improving move; repeats until a pass improves nothing.
2. **Late Acceptance Hill Climbing**, `TEMPS` seconds (default 180) on `FILS` parallel workers (default 8), each with
   its own random seed. Random moves: another room, a **swap** of rooms between two units that meet in time (what
   single changes cannot do when rooms are full), or another slot. A move is accepted if the result is not worse
   than the current one *or than the one 2,000 moves ago*, so the search can cross worse areas and leave local
   optima; each worker keeps the best timetable it saw.
3. **Polish**: the best worker's timetable goes through the greedy descent again.

The result is a strong local optimum, not a proof of the best one. Every move is checked against the hard rules with the verifier's own definitions (R1-TORN, R2, R3, R4, R8; a clash
the verifier forgives is accepted only for the very same pair of sessions), its objective numbers are identical to
the verifier's, and `make` runs the official verifier on the result. The SAT proposal is kept as
`out/<q>/proposta-sat.csv`; `make … MILLORA=0` skips this step, `make 5.2 TEMPS=600 FILS=12` searches longer.

Scope: 5.1 rooms only (times are fixed) · 5.2 everything that may move · 5.4 only the new degree (5.2 stays as it
is: 0 changes w.r.t. the reference) · 5.3 nothing (its criterion is the fewest changes w.r.t. 5.2).

## Learning what the xaman values: `variants.py` + `pesos.py`

**The easy way — one interactive command:**  `make bucle Q=5.2`. Each round it builds 10 new verified proposals,
asks you in the terminal for the xaman score of each one, refits and prints the weights (what the xaman values), and
copies the best-scored proposal so far to `out/<q>/proposta.csv` and `../entregues/`. Then it asks for another round.
Everything below is what it does step by step.

The xaman's score formula is not published (enunciat §9: "una estimació, no la nota"; §7: objectives are compared
between teams). Instead of guessing the priority order, measure it:

```bash
make variants Q=5.1            # ~4 min: 12 different, verified proposals in out/5.1/variants/ + ronda1.csv
#   upload out/5.1/variants/r1-v*.csv to the xaman, write each score in the "puntuacio" column of ronda1.csv
make pesos Q=5.1               # least-squares fit: how many points each objective costs -> pesos-5.1.txt
make 5.1                       # millora.py now minimises that weighted sum (delete pesos-5.1.txt to undo)
```

Each round contains v00 (raw SAT), v01 (current proposal), one variant per objective with that objective alone
(the extreme points) and random mixes; all start from the same SAT proposal, run in parallel (one core each) and are
checked by the official verifier. More rounds (`make variants` again) add points to the same fit. Model:
score ≈ a − Σ wₖ · objectiveₖ / (its value in the SAT proposal), with light ridge regularisation; on a synthetic
test with known weights it recovered them with R² 0.99 from 12 points. `millora.py --pesos "canvis_aula=1,…"`
also takes weights by hand. Works for 5.1, 5.2 and 5.4 (5.3 follows 5.2).

**Results accumulate.** `millora.py --des-de millor` (the default in `make`, `DESDE=millor`) starts from the best
proposal known: the variants tied for the best xaman score, the previous `proposta.csv` (kept as
`proposta-anterior.csv` before a rebuild) and the SAT one, whichever is best by the current weights; it never ends
worse than where it started. Once `pesos-<q>.txt` exists, new rounds of `make variants` refine: they use the fitted
weights and random perturbations of them, starting from that best proposal. Every objective keeps at least 10 % of
the largest weight (`pesos.py --minim`), so one the scores could not measure is not left free to get much worse.
Long run:  `python3 millora.py --pregunta 5.2 --temps 1800 --fils 12 --des-de millor`, then `make tot`.
After submitting it: `make registra Q=5.2 PUNT=74` adds that proposal and its score to the fit (and as a start point).

## The `out/truc/` family: paying R5-SENSE-AULA instead of R1-TORN (a test for the xaman)

The 458 fixed GEI / GEET+GEST 1r–2n sessions that are in the afternoon today with no room cost one declared violation
each, whatever we do. Leaving them **without a room** declares R5-SENSE-AULA (the verifier allows relaxing it). Their
R1-TORN then becomes inherited, and their rooms are free for the rest. The count is the same (459 in 5.2), and the room
objectives get slightly better. Risk: rule 5 says *"Totes les sessions amb aula"*, so the jury may reject the
justification. Use it only if the xaman clearly scores it higher.

```bash
make truc                                   # out/truc/5.1..5.4 from the current out/5.1 and out/5.2 (never rebuilt)
make bucle Q=5.2 DIR=out/truc/5.2           # the learning loop for the truc 5.2 (own rounds, own pesos.txt)
make truc-derivades                         # truc 5.2 changed: rebuild truc 5.3 and 5.4 on it
```

- **5.1:** has no such trick. It is VALIDA with nothing declared, so `out/truc/5.1` is the normal 5.1.
- **5.3 / 5.4:** rebuilt by the SAT on top of `out/truc/5.2` (`exporta.py --sense-aula`).
- **Submitting:** the truc 5.2 first, then its 5.3 and 5.4. Never mix the families: a normal 5.3 checked against a
  truc 5.2 shows 458 room changes.

`make derivades` and `make truc` never rebuild `out/5.1` or `out/5.2` (`make -o`), even after a script changes.

## Files

| File | What it is |
|---|---|
| `horaris.pl` | **The rules.** `writeClauses :-` lists one predicate per official rule; below, what each unit *could* be |
| `satlib.pl` | Generic SAT machinery: variable numbering, `writeClause`, at-most-one / at-most-K, kissat, reading the model |
| `exporta.py` | CSV → facts per question (through the verifier's own loader), solution → `proposta.csv` + relaxations |
| `resol.sh` | Solve with a bound on changes, loosening it until SAT |
| `millora.py` | Local search on the rule-9 objectives, in priority order, keeping every hard rule |
| `variants.py`, `pesos.py` | Diverse verified proposals to submit, and the weight fit from their xaman scores |
| `resum.py`, `graella.py` | Junta summary (5.2) and weekly grid per room (rule 10) |
| `nucli.py` | Minimal UNSAT core: which classes, together, make a facts file impossible |
| `relaxacions.csv` | Hand-written relaxations that were proved necessary (see below) |
| `Makefile` | The pipeline |

## The model

Variables: `day(U,D)`, `start(U,T)`, `room(U,R)` (+ helpers `occ(U,Q)` "U occupies quarter Q", `sameDay(A,B)`,
`overlap(A,B)`, `busy(R,W,D,H)`, `changedSlot(U)`, `changedRoom(U)`).

| Predicate under `writeClauses` | Official rule |
|---|---|
| `eachUnitOneDay`, `eachUnitOneStart`, `eachUnitOneRoom` | R5 (every session, own week, with a room), R1-TORN + R2-FINESTRA (start inside 8:30–14:30 or 14:30–21:00, never crossing), R1-FIXADA / R7-PLAB (fixed units have a single possible day/start/room), R3-AULA / R3-TIPUS / R3-AFORAMENT (only allowed rooms are candidates) |
| `notOnHolidaysOrStoppages` | R2-CALENDARI |
| `noClassInAClosedRoom` | R3-TANCADA (5.3) |
| `noTwoClassesInTheSameRoom` | R4-AULA |
| `noTeacherStudentsOrLabClash` | R4-DOCENT, R4-ALUMNAT (same cohort and theory↔its subgroups, or same subgroup), R4-PLAB |
| `twoOrdinaryRoomsFreeEveryHour` | R8-RESERVA (≤ 19 of the 21 ordinary rooms busy in every hourly slot of every week) |
| `preferNoChanges` | objective 9: kissat runs with `--phase=false` (tries "unchanged" first) + the hard bound on changes |

What the verifier forgives is not constrained either: overlaps that only involve fixed, unmoved sessions, and
teacher/student/lab overlaps already present in today's schedule (`inherited/2`).

## Relaxations (rule 11): all proved, none guessed

1. **R1-TORN, 458 sessions — forced by the verifier itself.** Fixed GEI / GEET+GEST 1r–2n groups (R1: "no es toquen")
   that are in the afternoon today and have no room. Moving them breaks R1-FIXADA; leaving them without a room breaks
   R5-SENSE-AULA; giving them a room makes their R1-TORN count (it is only "inherited" if the proposal does not touch
   them). We keep the Escola's time, give the room and declare R1-TORN (`exporta.py proposta` lists them).
2. **R1-TORN, 1 session (S04526) — proved infeasible with the solver** (`nucli.py`, minimal UNSAT core, week 14).
   5–8/4/2027 is the evaluation week, so week-14 sessions can only be on Friday 9/4. Teacher D380 has three 1-hour
   PAUL of 102750 (GEI 3r/4t, afternoon, 34–35 students) that may only use the two computer rooms (R3-TIPUS; the
   integrated labs have 24 places). Fixed GEI 1r groups fill **both** computer rooms 15:00–19:00, so the afternoon
   leaves 14:30–15:00 and 19:00–21:00: room for two of them, not three. One stays in the morning.
3. **5.3 only: R1-FIXADA 8 + R7-PLAB 2.** Fixed groups and labs whose own room is closed by the scenario: R3-TANCADA
   cannot be relaxed (the verifier forbids it), so they keep day and hour and change room.

To find out *why* something is UNSAT: `skip=<rule>` switches one rule off
(`swipl -g main -t halt horaris.pl -- DATA.pl out.csv /tmp/x skip=teachers`; also `shifts`, `students`, `labs`, or
any predicate name above), and `python3 nucli.py DATA.pl` shrinks it to a minimal set of classes that still conflict.

### Choices that are ours, not the rules' (so an UNSAT would be *"not found"*, not *"impossible"*)
- start times on a 15-minute grid (`PAS`);
- 5.2: one weekly pattern per block (phase A) + calendar repair (phase B);
- a shared class uses one room for all its rows (the verifier only checks the time);
- capacity = `alumnes` (verifier definition); 0 students = fits anywhere.
