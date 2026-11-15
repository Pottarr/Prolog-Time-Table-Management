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
% Demo facts (used by the /api/prolog/parent smoke-test endpoint)
% ======================================================================

%!  main_parent
%
%   Reads `query(Parent, Child).` from stdin and prints `true` or `false`.
main_parent :-
    read_term(user_input, query(Parent, Child), []),
    (   parent(Parent, Child) -> Answer = true ; Answer = false ),
    format("~w~n", [Answer]).

parent(alice, bob).
parent(alice, charlie).
parent(bob, david).
parent(bob, eve).
parent(charlie, frank).

% X is a grandparent of Z if:
% X is parent of Y AND Y is parent of Z.
grandparent(X, Z) :-
    parent(X, Y),
    parent(Y, Z).

% Two people are siblings if they share a parent.
sibling(X, Y) :-
    parent(P, X),
    parent(P, Y),
    X \= Y.

% Recursive ancestor rule
ancestor(X, Y) :-
    parent(X, Y).

ancestor(X, Y) :-
    parent(X, Z),
    ancestor(Z, Y).
