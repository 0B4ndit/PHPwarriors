%% =====================================================================================================
%% satlib.pl -- generic SAT machinery (nothing about timetables here)
%%
%%   * every Prolog term used as a boolean (dia(b0001,l), room(b0001,'Q1/1003'), ...) gets a DIMACS number
%%   * writeClause([L1,L2,...])  writes  L1 v L2 v ...   where a literal is Term or -Term
%%   * cardinality helpers: exactly/3, atMost/2, atLeast/2, atMostOne/1
%%   * implies(Conjunction, Lit): (A1 & A2 & ...) -> Lit   as one clause
%%   * solve/3: writes header+clauses, runs kissat, reads the model back (isTrue/1)
%% =====================================================================================================
:- dynamic varNumber/3, varTerm/2, isTrue/1.

%% ---------- variable numbering (hash-indexed: term_hash + term, so lookups stay O(1)) ----------------
var2num(T, N) :- term_hash(T, H), varNumber(H, T, N), !.
var2num(T, N) :-
    nb_getval(numVars, N0), N is N0 + 1, nb_setval(numVars, N),
    term_hash(T, H), assertz(varNumber(H, T, N)), assertz(varTerm(N, T)).

lit2num(-T, M) :- !, var2num(T, N), M is -N.
lit2num(T, N)  :- var2num(T, N).

%% ---------- clauses ----------------------------------------------------------------------------------
writeClause(Lits) :-
    nb_getval(clauseStream, S),
    ( nb_current(symbolic, true)                       % readable form:  -day(b0001,l) v start(b0001,510)
    -> ( nb_current(symbolicUnit, U), \+ sub_term(U, Lits) -> true      % only clauses about one unit
       ; maplist([L, A]>>format(atom(A), '~q', [L]), Lits, As), atomic_list_concat(As, ' v ', Txt),
         format(S, '~a~n', [Txt]) )
    ;  maplist(lit2num, Lits, Nums), atomic_list_concat(Nums, ' ', A), format(S, '~a 0~n', [A]) ),
    nb_getval(numClauses, C0), C is C0 + 1, nb_setval(numClauses, C).

%% (A1 & A2 & ... & An) -> L      ==   -A1 v -A2 v ... v -An v L
implies(Conj, L) :- maplist(neg, Conj, NegConj), append(NegConj, [L], C), writeClause(C).

neg(-T, T) :- !.
neg(T, -T).

%% ---------- cardinality --------------------------------------------------------------------------------
exactly(1, Lits) :- !, atLeast(1, Lits), atMostOne(Lits).
exactly(K, Lits) :- atMost(K, Lits), maplist(neg, Lits, Neg), length(Lits, N), K1 is N - K, atMost(K1, Neg).

atLeast(1, Lits) :- writeClause(Lits).

%% at most one: pairwise for short lists, "ladder" (sequential) encoding with auxiliary vars otherwise
atMostOne(Lits) :- length(Lits, N), N =< 6, !,
    forall(( append(_, [A|Rest], Lits), member(B, Rest) ), writeClause([-A, -B])).
atMostOne(Lits) :-
    newAux(Id),
    ladder(Lits, Id, 1).

ladder([_], _, _) :- !.                         % s(I) means "one of the first I literals is true"
ladder([X|Xs], Id, I) :-
    S = aux(Id, I), I1 is I + 1, S1 = aux(Id, I1),
    writeClause([-X, S]),                       % x_i -> s_i
    writeClause([-S, S1]),                      % s_i -> s_{i+1}
    Xs = [Y|_], writeClause([-S, -Y]),          % s_i -> not x_{i+1}
    ladder(Xs, Id, I1).

%% at most K of Lits.  If few subsets of size K+1 exist, forbid each of them (no new variables);
%% otherwise a sequential counter (Sinz 2005).
atMost(K, Lits) :- length(Lits, N), N =< K, !.
atMost(0, Lits) :- !, forall(member(L, Lits), writeClause([-L])).
atMost(1, Lits) :- !, atMostOne(Lits).
atMost(K, Lits) :- length(Lits, N), binomial(N, K + 1, B), B =< 300, !,
    K1 is K + 1,
    forall(subsetOfSize(K1, Lits, Sub), ( maplist(neg, Sub, C), writeClause(C) )).
atMost(K, Lits) :-
    newAux(Id), length(Lits, N),
    forall(nth1(I, Lits, X), counter(Id, I, N, K, X)).

%% r(Id,I,J): "at least J of the first I literals are true"
counter(Id, I, N, K, X) :-
    ( I < N -> writeClause([-X, aux(Id, I, 1)]) ; true ),
    ( I > 1 -> I0 is I - 1,
        forall(between(1, K, J), ( I < N -> writeClause([-aux(Id, I0, J), aux(Id, I, J)]) ; true )),
        forall(between(2, K, J), ( J0 is J - 1, I < N ->
                writeClause([-X, -aux(Id, I0, J0), aux(Id, I, J)]) ; true )),
        writeClause([-X, -aux(Id, I0, K)])
    ; true ),
    ( I =:= 1, K < 1 -> writeClause([-X]) ; true ).

subsetOfSize(0, _, []) :- !.
subsetOfSize(K, [X|Xs], [X|S]) :- K1 is K - 1, subsetOfSize(K1, Xs, S).
subsetOfSize(K, [_|Xs], S) :- length(Xs, N), N >= K, subsetOfSize(K, Xs, S).

binomial(N, K0, B) :- K is K0, ( K > N -> B = 0 ; binom(N, K, 1, 1, B) ).
binom(N, K, I, Acc, B) :- ( I > K -> B = Acc ; Acc1 is Acc * (N - K + I) // I, I1 is I + 1, binom(N, K, I1, Acc1, B) ).

newAux(Id) :- nb_getval(numAux, Id), Id1 is Id + 1, nb_setval(numAux, Id1).

%% ---------- solving --------------------------------------------------------------------------------------
%% solve(+Dir, +KissatOptions, -Result)   Result = sat | unsat | unknown
solve(Dir, Opts, Result) :-
    generate(Dir, V, C),
    format(atom(Cmd), 'cd ~w && echo "p cnf ~w ~w" > header && cat header clauses > infile.cnf && \c
                       kissat ~w infile.cnf > model', [Dir, V, C, Opts]),
    format('Running kissat ~w ...~n', [Opts]), flush_output,
    statistics(walltime, [W0, _]),
    shell(Cmd, Code),
    statistics(walltime, [W1, _]), Ts is (W1 - W0) / 1000,
    format('kissat finished in ~1f s (exit code ~w)~n', [Ts, Code]),
    result(Code, Dir, Result).

%% generate(+Dir, -NumVars, -NumClauses): runs writeClauses into Dir/clauses
generate(Dir, V, C) :-
    nb_setval(numVars, 0), nb_setval(numClauses, 0), nb_setval(numAux, 0),
    retractall(varNumber(_, _, _)), retractall(varTerm(_, _)), retractall(isTrue(_)),
    atom_concat(Dir, '/clauses', ClausesFile),
    open(ClausesFile, write, S, [buffer(full)]), nb_setval(clauseStream, S),
    statistics(cputime, T0),
    writeClauses,
    close(S),
    statistics(cputime, T1), Tg is T1 - T0,
    nb_getval(numVars, V), nb_getval(numClauses, C),
    format('Generated ~D variables and ~D clauses in ~1f s~n', [V, C, Tg]).

result(10, Dir, sat) :- !, atom_concat(Dir, '/model', M), readModel(M).
result(20, _, unsat) :- !.
result(_, _, unknown).

readModel(File) :-
    setup_call_cleanup(open(File, read, S), readLines(S), close(S)).

readLines(S) :-
    read_line_to_string(S, L),
    ( L == end_of_file -> true
    ; ( sub_string(L, 0, 2, _, "v ") ->
          sub_string(L, 2, _, 0, Rest), split_string(Rest, " ", " ", Parts),
          forall(( member(P, Parts), P \== "", number_string(N, P), N > 0, varTerm(N, T) ), assertz(isTrue(T)))
      ; true ),
      readLines(S) ).
