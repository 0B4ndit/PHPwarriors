%% =====================================================================================================
%% horaris.pl -- timetable of the Escola d'Enginyeria (UAB THE HACK 2026, level 2: questions 5.1 - 5.4)
%%
%%   swipl -g main -t halt horaris.pl -- DATA.pl SOLUTION.csv WORKDIR [Options]
%%   Options:  min | min+N | N      hard bound on units that change day/hour (min = only those that must)
%%             minrooms             units whose preferred room is still allowed must keep it (5.1)
%%             skip=Rule            switch one rule off (diagnosis)        simbolic [unit=U]   readable clauses
%%
%% DATA.pl is produced by exporta.py from the CSVs of paquet/ (+ the question's scenario). It describes UNITS:
%% a unit is a class that moves as one piece (an activity = same group/weekday/hour every week, merged with
%% everything it shares a physical class with). For every unit we decide
%%
%%      day(U,D)      on which weekday      (its week never changes: rule 5)
%%      start(U,T)    at which start time   (minutes after midnight, on a 15/30-min grid)
%%      room(U,R)     in which room         (only units that need one)
%%
%% The rules are the official ones (enunciat §3 + §8, and what the verifier horaris/check.py checks).
%% Each rule is one predicate under writeClauses, written with the classic  Generator, writeClause, fail.
%% pattern: "for every X that matches, write this clause".
%% =====================================================================================================
:- encoding(utf8).
:- use_module(library(lists)).
:- use_module(library(yall)).
:- use_module(library(apply)).
:- ['satlib.pl'].
:- dynamic pDay/2, pStart/2, pRoom/2, pOcc/2, occRange/3, sigShare/2, needOverlap/2, roomPair/3,
           clashPair/2, ordinaryRoom/1, maxChanges/1, frozen/1, busyKey/4, inHourOf/2, skip/1,
           keepRooms/0.
%% facts that come from DATA.pl (declared so that a phase without any of them still runs)
:- dynamic step/1, sig/2, unit/1, duration/2, shift/2, weekSig/2, days/2, original/3, sessionType/2,
           students/2, movable/1, fixedStart/2, fixedRoom/2, needsRoom/1, originalRoom/2, teacher/2,
           cohortGroup/5, subject/3, forbidden/4, inherited/2, room/3, integrated/1, outsideBuilding/1,
           mustLeave/1, preferred/3, preferredRoom/2, closedRoom/5, roomlessSession/1.

%% ------------------------------------------------------------------------------------------------------
%% 0. Official constants
%% ------------------------------------------------------------------------------------------------------
window(mati,  510,  870).          % 8:30 - 14:30   (rule 2; the shift is decided by the start time)
window(tarda, 870, 1260).          % 14:30 - 21:00  (building closes at 21:00)
reserveHour(H) :- between(0, 12, I), H is 510 + 60 * I.   % R8 checks hourly slots 8:30, 9:30, ..., 20:30
freeOrdinaryRooms(2).              % R8: two ordinary rooms free in every slot
generalTypes(['Aules docents', 'Seminaris']).                    % "aula docent i seminari compten com el mateix"
practiceTypes(['Laboratoris docents', 'Aules informàtiques']).

%% ======================================================================================================
%% 1. THE RULES
%% ======================================================================================================
writeClauses :-
    rule(eachUnitOneDay),                  % every session takes place (R5) on one weekday of its own week
    rule(eachUnitOneStart),                % ... at one start time, inside its shift window (R1-TORN, R2-FINESTRA)
    rule(eachUnitOneRoom),                 % ... in one room that suits it (R3-*, R5-SENSE-AULA)
    rule(notOnHolidaysOrStoppages),        % R2-CALENDARI (pieces re-placed inside their week carry forbidden/4)
    rule(noClassInAClosedRoom),            % R3-TANCADA (5.3: room reserved / broken by the scenario)
    rule(aStartOccupiesItsQuarters),       % helper: start(U,T) -> occ(U,Q) for every quarter of the class
    rule(whenDoTwoUnitsOverlap),           % helper: overlap(A,B) if same day and a common quarter
    rule(noTwoClassesInTheSameRoom),       % R4-AULA
    rule(noTeacherStudentsOrLabClash),     % R4-DOCENT, R4-ALUMNAT, R4-PLAB
    rule(twoOrdinaryRoomsFreeEveryHour),   % R8-RESERVA
    rule(preferNoChanges),                 % objective 9: few changes w.r.t. today (heuristic + optional bound)
    true.

%% Diagnosis: "skip=Name" on the command line drops one rule, to see which one makes a problem UNSAT.
%% Names: the predicates above, and also  shifts  teachers  students  labs  (parts of a rule).
rule(G) :- skip(G), !, format('   (rule ~w switched off)~n', [G]).
rule(G) :- call(G).

%% ---- R5: one day, one start, one room ----------------------------------------------------------------
eachUnitOneDay :- unit(U), findall(day(U,D), pDay(U,D), L), exactlyOne(L), fail.
eachUnitOneDay.

eachUnitOneStart :- unit(U), findall(start(U,T), pStart(U,T), L), exactlyOne(L), fail.
eachUnitOneStart.

eachUnitOneRoom :- unit(U), hasRoom(U), findall(room(U,R), pRoom(U,R), L), exactlyOne(L), fail.
eachUnitOneRoom.

exactlyOne(L) :- atLeast(1, L), atMostOne(L).

%% ---- R2-CALENDARI: a piece moved to a day with a stoppage (e.g. 17/3 13:00-15:00) must avoid it -------
notOnHolidaysOrStoppages :-
    forbidden(U, D, From, To), pDay(U, D), duration(U, Dur),
    pStart(U, T), T < To, T + Dur > From,
    writeClause([-day(U,D), -start(U,T)]), fail.
notOnHolidaysOrStoppages.

%% ---- R3-TANCADA: a room closed by the scenario on that day and time cannot be used ----------------------
noClassInAClosedRoom :-
    closedRoom(U, R, D, From, To), pRoom(U, R), pDay(U, D), duration(U, Dur),
    pStart(U, T), T < To, T + Dur > From,
    writeClause([-room(U,R), -day(U,D), -start(U,T)]), fail.
noClassInAClosedRoom.

%% ---- helpers: occupation and overlap -------------------------------------------------------------------
aStartOccupiesItsQuarters :-
    pStart(U, T), duration(U, Dur), quarterOf(T, Dur, Q),
    writeClause([-start(U,T), occ(U,Q)]), fail.
aStartOccupiesItsQuarters.

%% overlap(A,B) <- day(A,D) & day(B,D) & occ(A,Q) & occ(B,Q)      (only for pairs that need it)
whenDoTwoUnitsOverlap :-
    needOverlap(A, B),
    ( pDay(A, D), pDay(B, D), implies([day(A,D), day(B,D)], sameDay(A,B)), fail ; true ),
    pOcc(A, Q), pOcc(B, Q),
    implies([sameDay(A,B), occ(A,Q), occ(B,Q)], overlap(A,B)), fail.
whenDoTwoUnitsOverlap.

%% ---- R4-AULA: two classes that overlap in time cannot share a room --------------------------------------
noTwoClassesInTheSameRoom :-
    roomPair(A, B, Rooms), member(R, Rooms),
    writeClause([-overlap(A,B), -room(A,R), -room(B,R)]), fail.
noTwoClassesInTheSameRoom.

%% ---- R4-DOCENT / R4-ALUMNAT / R4-PLAB: these pairs may not overlap at all ---------------------------------
noTeacherStudentsOrLabClash :- clashPair(A, B), writeClause([-overlap(A,B)]), fail.
noTeacherStudentsOrLabClash.

%% ---- R8-RESERVA: in every week, day and hourly slot, at most 19 of the 21 ordinary rooms are busy ---------
%% busy(R,W,D,H): ordinary room R is used on weekday D of week W during slot [H, H+60).
%% To keep it small we go through busySig(R,S,D,H) ("used by some unit whose weeks are the signature S").
twoOrdinaryRoomsFreeEveryHour :-
    unitBusiesARoom, busyInEachWeek, atMostNineteenBusy.

unitBusiesARoom :-                                  % room(U,R) & day(U,D) & inHour(U,H) -> busySig(R,S,D,H)
    unit(U), weekSig(U, S), once(( pRoom(U, R0), ordinaryRoom(R0) )),
    ( pOcc(U, Q), reserveHour(H), Q >= H, Q < H + 60,
      writeClause([-occ(U,Q), inHour(U,H)]), assertOnce(inHourOf(U,H)), fail ; true ),
    pRoom(U, R), ordinaryRoom(R), pDay(U, D), inHourOf(U, H),
    implies([room(U,R), day(U,D), inHour(U,H)], busySig(R,S,D,H)),
    assertOnce(busyKey(R,S,D,H)), fail.
unitBusiesARoom.

busyInEachWeek :-                                   % busySig(R,S,D,H) -> busy(R,W,D,H) for every week W of S
    busyKey(R, S, D, H), sig(S, Weeks), member(W, Weeks),
    writeClause([-busySig(R,S,D,H), busy(R,W,D,H)]), fail.
busyInEachWeek.

atMostNineteenBusy :-
    freeOrdinaryRooms(Free), aggregate_all(count, ordinaryRoom(_), NOrd), Max is NOrd - Free,
    findall((W-D-H)-R, ( busyKey(R,S,D,H), sig(S,Ws), member(W,Ws) ), L0),
    sort(L0, L1), group_pairs_by_key(L1, Slots),          % (Week-Day-Hour) - [rooms that could be busy]
    member((W-D-H)-Rooms, Slots),
    findall(busy(R,W,D,H), member(R, Rooms), L),
    atMost(Max, L), fail.
atMostNineteenBusy.

%% ---- objective 9: kissat runs with --phase=false, so it first tries changedSlot(U)=false = "keep it" ------
%% preferred/3 = today's slot (5.1, 5.2 phase A), the phase-A pattern (5.2 phase B) or the 5.2 proposal (5.3, 5.4)
preferNoChanges :-
    movable(U), preferred(U, D0, T0),
    ( pDay(U, D0), pStart(U, T0)
    -> writeClause([day(U,D0), changedSlot(U)]), writeClause([start(U,T0), changedSlot(U)])
    ;  writeClause([changedSlot(U)]) ),                         % that slot is not allowed any more
    fail.
preferNoChanges :-
    movable(U), hasRoom(U), preferredRoom(U, R0), pRoom(U, R0),
    writeClause([room(U,R0), changedRoom(U)]), fail.
preferNoChanges :-                                             % hard bound: MAXCANVIS = K | min | min+N
    maxChanges(K0), findall(changedSlot(U), movable(U), L),
    ( K0 = min(Extra) -> aggregate_all(count, mustChange(_), K1), K is K1 + Extra,   % K1 = cannot stay
                         format('Hard bound: ~w units may change day/hour (~w must, + ~w)~n', [K, K1, Extra])
    ; K = K0 ),
    atMost(K, L), fail.
preferNoChanges :-                                             % 5.1: a room that is still valid is kept
    keepRooms, movable(U), hasRoom(U), preferredRoom(U, R0), pRoom(U, R0),
    writeClause([-changedRoom(U)]), fail.
preferNoChanges.

mustChange(U) :- movable(U), preferred(U, D0, T0), \+ ( pDay(U, D0), pStart(U, T0) ).

%% ======================================================================================================
%% 2. WHAT EACH UNIT *COULD* BE (domains, computed once before writing clauses)
%% ======================================================================================================
buildDomains :-
    forall(( room(R, 'Aules docents', _), \+ outsideBuilding(R) ), assertz(ordinaryRoom(R))),
    forall(( unit(U), days(U, Ds), member(D, Ds) ), assertz(pDay(U,D))),
    forall(( unit(U), possibleStart(U, T) ), assertz(pStart(U,T))),
    forall(( unit(U), possibleRoom(U, R) ), assertz(pRoom(U,R))),
    forall(( unit(U), duration(U, Dur), setof(Q, T^(pStart(U,T), quarterOf(T,Dur,Q)), Qs) ),
           ( forall(member(Q, Qs), assertz(pOcc(U,Q))), Qs = [Lo|_], last(Qs, Hi), assertz(occRange(U,Lo,Hi)) )),
    forall(( unit(U), fixedStart(U,_), ( fixedRoom(U,_) ; \+ hasRoom(U) ) ), assertz(frozen(U))),
    sanityChecks,
    buildPairs.

possibleStart(U, T) :- fixedStart(U, T), !.
possibleStart(U, T) :-                                   % R1-TORN + R2-FINESTRA on the start grid
    ( skip(shifts) -> true ; shift(U, any) -> true ; shift(U, Shift) ),   % any = declared R1-TORN relaxation
    window(Shift, Lo, Hi), duration(U, Dur), step(Step),
    Last is Hi - Dur, between(0, 1000, K), T is Lo + K * Step, ( T > Last -> !, fail ; true ).

hasRoom(U) :- needsRoom(U) ; fixedRoom(U, _).

possibleRoom(U, R) :- fixedRoom(U, R), !.               % PLAB (R7) and fixed groups that already have one
possibleRoom(U, R) :- needsRoom(U), room(R, Type, Cap), roomAllowed(U, R, Type, Cap).

roomAllowed(_, R, _, _) :- mustLeave(R), !, fail.        % J rooms: must come back to the aulari (R3-AULA)
roomAllowed(U, R, outside, _) :- !, originalRoom(U, R).  % B3/QC: may stay, nobody new (R3-AULA)
roomAllowed(U, R, Type, Cap) :-
    students(U, N), N =< Cap,                            % R3-AFORAMENT (the "alumnes" column)
    typeOK(U, R, Type).                                  % R3-TIPUS

%% R3-TIPUS (enunciat §8.1): theory never in a lab; a PAUL may also use the integrated labs and the computer
%% rooms; Q5/Q6 labs are only for PLAB; otherwise the same kind of space as today. The verifier looks at every
%% session on its own, so the type must suit ALL the rooms the unit's sessions have today (in the 1st semester one
%% group may be in a classroom some weeks and in a computer room others), and the default for those with none.
typeOK(U, R, Type) :- sessionType(U, 'PAUL'), ( integrated(R) ; Type == 'Aules informàtiques' ), !.
typeOK(U, _, Type) :- \+ ( typesFor(U, Ts), \+ memberchk(Type, Ts) ), !.
typeOK(U, R, Type) :- originalRoom(U, R), \+ ( originalRoom(U, R2), R2 \== R ),
                      \+ ( Type == 'Laboratoris docents', \+ sessionType(U, 'PLAB') ).

typesFor(U, Ts) :- originalRoom(U, R0), room(R0, T0, _), T0 \== outside, typesFromToday(U, T0, Ts).
typesFor(U, Ts) :- ( roomlessSession(U) ; \+ ( originalRoom(U, R0), room(R0, T0, _), T0 \== outside ) ),
                   allowedTypes(U, Ts).
typesFromToday(U, T0, Ts) :-
    generalTypes(G),
    ( T0 == 'Laboratoris docents', \+ sessionType(U, 'PLAB') -> Ts = G
    ; memberchk(T0, G) -> Ts = G
    ; Ts = [T0] ).
allowedTypes(U, Ts) :- sessionType(U, 'PLAB') -> practiceTypes(Ts) ; generalTypes(Ts).   % no room today

quarterOf(T, Dur, Q) :- Last is T + Dur - 15, between(0, 100, K), Q is T + 15 * K, ( Q > Last -> !, fail ; true ).

%% ---- which pairs of units need clauses -----------------------------------------------------------------
buildPairs :-
    forall(( sig(S1, W1), sig(S2, W2), \+ \+ ( member(W, W1), memberchk(W, W2) ) ), assertz(sigShare(S1,S2))),
    forall(( unit(A), \+ frozen(A), unit(B), B \== A, ( frozen(B) ; A @< B ), mayMeet(A, B) ),
           classifyPair(A, B)),                         % frozen-frozen pairs need nothing (inherited / given)
    aggregate_all(count, needOverlap(_,_), NO), aggregate_all(count, roomPair(_,_,_), NR),
    aggregate_all(count, clashPair(_,_), NC),
    format('Pairs that may meet: ~D (room-sharing ~D, teacher/students/lab ~D)~n', [NO, NR, NC]).

mayMeet(A, B) :-                                         % same week, a common day, intersecting hours
    weekSig(A, SA), weekSig(B, SB), sigShare(SA, SB),
    occRange(A, LA, HA), occRange(B, LB, HB), LA =< HB, LB =< HA,
    pDay(A, D), pDay(B, D), !.

classifyPair(A, B) :-
    ( \+ ( frozen(A), frozen(B) ), findall(R, ( pRoom(A,R), pRoom(B,R) ), Rs), Rs \== []
    -> assertz(roomPair(A,B,Rs)) ; true ),
    ( \+ ( fixedStart(A,_), fixedStart(B,_) ), \+ inherited(A,B), \+ inherited(B,A), clash(A, B)
    -> assertz(clashPair(A,B)) ; true ),
    ( ( roomPair(A,B,_) ; clashPair(A,B) ) -> assertz(needOverlap(A,B)) ; true ).

%% the three reasons why two classes can never be at the same time
clash(A, B) :- \+ skip(teachers), teacher(A, D), teacher(B, D), !.                % R4-DOCENT
clash(A, B) :- \+ skip(students),                                                   % R4-ALUMNAT
               cohortGroup(A, C, TA, LA, NA), cohortGroup(B, C, TB, LB, NB),
               sameStudents(TA, LA, NA, TB, LB, NB), !.
clash(A, B) :- \+ skip(labs), subject(A, Code, TA), subject(B, Code, TB), labAndClass(TA, TB), !. % R4-PLAB

%% same cohort and (a theory group blocks all subgroups of its line; two subgroups clash if same number)
sameStudents(TA, LA, NA, TB, LB, NB) :- ( TA == 'TE' ; TB == 'TE' ), !, ( LA == LB ; NA == NB ), !.
sameStudents(_, _, N, _, _, N).

labAndClass('PLAB', T) :- memberchk(T, ['TE', 'PAUL']), !.
labAndClass(T, 'PLAB') :- memberchk(T, ['TE', 'PAUL']).

sanityChecks :-
    forall(( unit(U), \+ pStart(U, _) ), format('WARNING: ~w has no possible start time~n', [U])),
    forall(( unit(U), needsRoom(U), \+ pRoom(U, _) ),
           ( students(U, N), format('WARNING: ~w (~w students) fits in no allowed room~n', [U, N]) )).

assertOnce(F) :- ( call(F) -> true ; assertz(F) ).

%% ======================================================================================================
%% 3. MAIN: generate, solve with kissat, show the solution
%% ======================================================================================================
main :-
    current_prolog_flag(argv, Argv),
    ( append(_, ['--'|Args], Argv) -> true ; Args = Argv ),
    Args = [Data, SolFile, Dir | Opt],
    style_check(-discontiguous),
    load_files(Data, [encoding(utf8)]),
    ( member(K, Opt), atom_number(K, N) -> assertz(maxChanges(N)), format('Hard bound: at most ~w moved units~n', [N])
    ; memberchk(min, Opt) -> assertz(maxChanges(min(0)))
    ; member(K, Opt), atom_concat('min+', E, K), atom_number(E, NE) -> assertz(maxChanges(min(NE)))
    ; true ),
    ( memberchk(minrooms, Opt) -> assertz(keepRooms) ; true ),
    forall(( member(O, Opt), atom_concat('skip=', G, O) ), assertz(skip(G))),
    buildDomains,
    (   memberchk(simbolic, Opt)
    ->  nb_setval(symbolic, true),
        ( member(O, Opt), atom_concat('unit=', UA, O) -> nb_setval(symbolicUnit, UA) ; true ),
        generate(Dir, _, _), halt(0)
    ;   solve(Dir, '-q --phase=false', Result),
        report(Result, SolFile)
    ).

report(sat, File) :- !,
    writeSolution(File), displaySummary,
    halt(0).
report(unsat, _) :- !,
    writeln('UNSAT: no timetable satisfies all the rules with this model'), halt(20).
report(_, _) :- writeln('kissat gave no answer (time out or error)'), halt(1).

writeSolution(File) :-
    open(File, write, S),
    format(S, 'unit,day,start,room~n', []),
    forall(unit(U), ( isTrue(day(U,D)), isTrue(start(U,T)),
                      ( isTrue(room(U,R)) -> true ; R = '' ),
                      format(S, '~w,~w,~w,~w~n', [U, D, T, R]) )),
    close(S),
    format('Solution written to ~w~n', [File]).

displaySummary :-
    aggregate_all(count, movable(_), NM),
    aggregate_all(count, ( movable(U), preferred(U,D0,T0), \+ ( isTrue(day(U,D0)), isTrue(start(U,T0)) ) ), NS),
    aggregate_all(count, ( hasRoom(U), \+ frozen(U), preferredRoom(U,R0), \+ isTrue(room(U,R0)) ), NR),
    aggregate_all(count, ( unit(U), needsRoom(U), \+ originalRoom(U,_) ), NNew),
    format('~nSAT. Movable units: ~w; changed day/hour: ~w; changed room: ~w; rooms given to ~w units that had none~n',
           [NM, NS, NR, NNew]).
