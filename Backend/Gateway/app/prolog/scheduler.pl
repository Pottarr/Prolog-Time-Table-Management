:- use_module(library(clpfd)).
:- use_module(library(pairs)).
:- use_module(library(time)).

% ======================================================================
% Auto-scheduling (run by app/prolog_engine.py as `swipl -g main_timetable`)
% ======================================================================
%
% The gateway encodes everything as plain integers before calling in, so
% no user text ever reaches Prolog:
%
%   Rooms   0..NumRooms-1, ordered by capacity ascending, so trying low
%           values first gives each class the smallest room that fits,
%           leaving the big rooms free for big classes.
%   Days    0..6 (Mon..Sun), so weekdays are tried before the weekend.
%   Periods 0 = morning (09-12), 1 = afternoon (13-16).
%
% Each course is c(MinRoom, Prof, Room, Day, Period):
%   MinRoom — the smallest room index whose capacity fits the class
%   Prof    — an integer id per professor
%   Room/Day/Period — a fixed value, or -1 for "Prolog picks"
%
% Rules:
%   - a room holds at most one class per (day, period)
%   - a professor teaches at most one class per (day, period)
%   - a class only goes in a room with enough capacity (MinRoom)

%!  solve_timetable(+Courses, +NumRooms, +TimeLimit, -Status, -Flat)
%
%   Status is `ok` with Flat = [Room1, Day1, Period1, Room2, ...] in
%   course order; or `unsatisfiable` / `timeout` with Flat = [].
solve_timetable(Courses, NumRooms, TimeLimit, Status, Flat) :-
    catch(call_with_time_limit(TimeLimit, solve(Courses, NumRooms, Status, Flat)),
          time_limit_exceeded,
          (Status = timeout, Flat = [])).

%!  main_timetable
%
%   Entry point for the gateway: reads one term
%   `request(Courses, NumRooms, TimeLimit).` from stdin (read_term only
%   parses data, it never runs it) and prints one line to stdout:
%   "ok R1 D1 P1 R2 ...", "unsatisfiable" or "timeout".
main_timetable :-
    read_term(user_input, request(Courses, NumRooms, TimeLimit), []),
    solve_timetable(Courses, NumRooms, TimeLimit, Status, Flat),
    atomic_list_concat([Status | Flat], ' ', Answer),
    format("~w~n", [Answer]).

solve(Courses, NumRooms, ok, Flat) :-
    place(Courses, NumRooms, Placements),
    !,
    placements_flat(Placements, Flat).
solve(_, _, unsatisfiable, []).

% One variable per class: Slot = Time * NumRooms + Room, where
% Time = Day * 2 + Period. Labeling tries low slots first, i.e. Monday
% morning before Monday afternoon before Tuesday ..., and within a time
% the smallest room that fits — so weekdays fill before the weekend.
%
%   - all_distinct(Slots): a room holds one class per (day, period)
%   - all_distinct on each professor's Times: one class at a time
place(Courses, NumRooms, Placements) :-
    maplist(course_slot(NumRooms), Courses, Slots, ProfTimes),
    all_distinct(Slots),
    keysort(ProfTimes, Sorted),
    group_pairs_by_key(Sorted, ByProf),
    maplist(prof_free, ByProf),
    labeling([ff], Slots),
    maplist(slot_placement(NumRooms), Slots, Placements).

% A class's Slot domain is exactly the set of slots it may use (right
% day/period/room if fixed, a room big enough) — an explicit set rather
% than arithmetic on Slot, so all_distinct can see e.g. that 30 big
% classes don't fit in the 28 big-room slots and fail straight away.
course_slot(NumRooms, c(MinRoom, Prof, FixedRoom, FixedDay, FixedPeriod), Slot, Prof-Time) :-
    MaxRoom is NumRooms - 1,
    findall(S,
            ( between(0, 6, Day), matches(Day, FixedDay),
              between(0, 1, Period), matches(Period, FixedPeriod),
              between(MinRoom, MaxRoom, Room), matches(Room, FixedRoom),
              S is (Day * 2 + Period) * NumRooms + Room ),
            Allowed),
    list_to_fdset(Allowed, Domain),
    Slot in_set Domain,
    Time #= Slot // NumRooms.

matches(_, -1) :- !.
matches(Value, Value).

prof_free(_-Times) :- all_distinct(Times).

slot_placement(NumRooms, Slot, p(Room, Day, Period)) :-
    Room is Slot mod NumRooms,
    Time is Slot // NumRooms,
    Day is Time // 2,
    Period is Time mod 2.

placements_flat([], []).
placements_flat([p(R, D, P) | Ps], [R, D, P | Rest]) :- placements_flat(Ps, Rest).

% ======================================================================
% Several cases (run by app/prolog_engine.py as `swipl -g main_cases`)
% ======================================================================
%
% Same course encoding as above. A class's fixed room/day/period is what
% it *asked for*. Rooms and professors are never double-booked and a class
% never goes in a room too small for it — those are hard rules. Prints up
% to MaxCases timetables, one per line, as soon as each is found:
%
%   - OK cases first: every timetable in which every class got what it
%     asked for, in labeling order. If there is at least one, only OK
%     cases are printed.
%   - Otherwise unsatisfied cases, fewest unsatisfied classes first: all
%     timetables in which exactly 1 class was moved off its requested
%     room/day/period (to a free spot), then 2, 3, ... until MaxCases are
%     printed. A class counts once however many of its values moved.
%
% MaxCases =< 0 means no cap, and TimeLimit =< 0 means no time limit.

%!  main_cases
%
%   Reads `request(Courses, NumRooms, TimeLimit, MaxCases).` from stdin
%   and prints "case -1 R1 D1 P1 R2 ..." per case (-1 = let the gateway
%   score it). With no case at all it prints "unsatisfiable" or
%   "timeout"; if the time limit cuts the search short after some cases,
%   a final "timeout" line follows them.
main_cases :-
    read_term(user_input, request(Courses, NumRooms, TimeLimit, MaxCases), []),
    nb_setval(cases_printed, 0),
    (   TimeLimit > 0
    ->  catch(call_with_time_limit(TimeLimit, all_cases(Courses, NumRooms, MaxCases)),
              time_limit_exceeded,
              TimedOut = true)
    ;   all_cases(Courses, NumRooms, MaxCases)
    ),
    nb_getval(cases_printed, Printed),
    (   TimedOut == true
    ->  format("timeout~n")
    ;   Printed =:= 0
    ->  format("unsatisfiable~n")
    ;   true
    ).

all_cases(Courses, NumRooms, MaxCases) :-
    catch(enumerate_cases(Courses, NumRooms, MaxCases), enough_cases, true).

enumerate_cases(Courses, NumRooms, MaxCases) :-
    forall(place(Courses, NumRooms, Placements), emit_case(Placements, MaxCases)),
    nb_getval(cases_printed, Printed),
    (   Printed > 0
    ->  true
    ;   include(has_request, Courses, Requesting),
        length(Requesting, MaxMoved),
        forall(between(1, MaxMoved, Moved),
               forall(relaxed_place(Courses, NumRooms, Moved, Placements),
                      emit_case(Placements, MaxCases)))
    ).

has_request(c(_, _, Room, Day, Period)) :-
    ( Room >= 0 ; Day >= 0 ; Period >= 0 ), !.

emit_case(Placements, MaxCases) :-
    placements_flat(Placements, Flat),
    atomic_list_concat([case, -1 | Flat], ' ', Line),
    format("~w~n", [Line]),
    flush_output,
    nb_getval(cases_printed, Printed0),
    Printed is Printed0 + 1,
    nb_setval(cases_printed, Printed),
    (   MaxCases > 0, Printed >= MaxCases
    ->  throw(enough_cases)
    ;   true
    ).

% Like place/3 (same all_distinct rules), but every class may go to any
% free slot in a room big enough for it, and exactly Moved classes end up
% somewhere other than what they asked for.
relaxed_place(Courses, NumRooms, Moved, Placements) :-
    maplist(free_slot(NumRooms), Courses, Slots, ProfTimes, Flags),
    all_distinct(Slots),
    keysort(ProfTimes, Sorted),
    group_pairs_by_key(Sorted, ByProf),
    maplist(prof_free, ByProf),
    sum(Flags, #=, Moved),
    % Decide who moves first (staying put before moving), then where.
    labeling([], Flags),
    labeling([ff], Slots),
    maplist(slot_placement(NumRooms), Slots, Placements).

% Slot: any day/period, any room that fits. Flag is 1 iff the class
% misses at least one of its requested room/day/period.
free_slot(NumRooms, c(MinRoom, Prof, FixedRoom, FixedDay, FixedPeriod), Slot, Prof-Time, Flag) :-
    MaxRoom is NumRooms - 1,
    findall(S,
            ( between(0, 6, Day), between(0, 1, Period), between(MinRoom, MaxRoom, Room),
              S is (Day * 2 + Period) * NumRooms + Room ),
            Allowed),
    list_to_fdset(Allowed, Domain),
    Slot in_set Domain,
    Time #= Slot // NumRooms,
    Room #= Slot mod NumRooms,
    Day #= Time // 2,
    Period #= Time mod 2,
    include(asked, [Room-FixedRoom, Day-FixedDay, Period-FixedPeriod], Asked),
    (   Asked == []
    ->  Flag = 0
    ;   maplist(differs, Asked, Misses),
        foldl(or_, Misses, 0, Missed),
        Flag #<==> Missed
    ).

asked(_-Fixed) :- Fixed >= 0.

differs(Var-Fixed, (Var #\= Fixed)).

or_(Miss, 0, Miss) :- !.
or_(Miss, Acc, (Acc #\/ Miss)).
