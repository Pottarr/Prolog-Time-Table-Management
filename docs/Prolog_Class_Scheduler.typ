// main.typ: Typst version of the "Prolog Class Scheduler" AI project report
// (converted from the Google Doc), followed by the source-code appendix.
//
// Compile:  typst compile main.typ
//
// Pictures: put the files in images/ (logo.png, screen1.png ... screen6.png)
// and set `show-pictures` to true. While it is false, each picture's space is
// kept empty so the layout does not move when you add them.

#let show-pictures = true

#let body-font = "Carlito"            // same letter widths as Calibri
#let mono-font = "Liberation Mono"    // same letter widths as Courier New

#let picture(path, width: auto, height: auto) = {
  if show-pictures { image(path, width: width) } else { box(width: width, height: height) }
}

#[
  #set page(
    paper: "a4",
    margin: 72pt,
    // Page number on every page except the cover, as in the Google Doc.
    footer: context {
      if here().page() > 1 {
        align(center, text(font: body-font, size: 11pt, counter(page).display()))
      }
    },
  )
  #set text(font: body-font, size: 14pt, lang: "en")
  #set par(justify: true, leading: 0.72em, spacing: 0.72em + 8pt)
  #set smartquote(enabled: false)
  #set list(indent: 18pt, body-indent: 12pt, marker: [•])
  #show raw: set text(font: mono-font)
  #show raw.where(block: false): set text(size: 12pt)
  #show raw.where(block: true): it => block(
    inset: (left: 18pt), above: 10pt, below: 14pt,
    { set par(leading: 0.55em, justify: false); set text(size: 10pt); it },
  )

  #let section-title(body) = block(
    above: 0pt, below: 22pt,
    text(size: 18pt, weight: "bold", underline(body)),
  )
  #let subhead(body) = block(
    above: 14pt, below: 10pt, sticky: true,
    text(weight: "bold", body),
  )
  #let screen(label, path) = block(breakable: false, below: 22pt, {
    align(center, label)
    v(4pt)
    align(center, picture(path, width: 440.25pt, height: 211pt))
  })

  // ---------------------------------------------------------------- Cover
  #align(center)[
    #v(14pt)
    #picture("./images/KMITL.png", width: 145.18pt, height: 145.18pt)
    #v(16pt)
    #text(16pt, weight: "bold")[AI Project Report \ Prolog Class Scheduler]
    #v(42pt)
    #text(16pt, weight: "bold")[01286342 Artificial Intelligence \ Software Engineering Program]
    #v(42pt)
    #text(16pt)[By]
    #v(36pt)
    #text(16pt)[
      67011093#h(2em)Chavit#h(2em)Saritdeechaikul \
      67011287#h(2em)Ramida#h(2em)Laphasphokin \
      67011352#h(2em)Theepakorn#h(2em)Phayonrat
    ]
  ]

  #pagebreak()

  // ---------------------------------------------------------------- Title
  #align(center)[
    #text(16pt, weight: "bold")[AI Project] \
    #text(14pt, weight: "bold")[Prolog Class Scheduler]
  ]
  #v(22pt)

  // ---------------------------------------------------------------- Project Description
  #section-title[Project Description]

Prolog Time Table Management is a classroom timetabling system for the ten rooms on the 8th floor of the ECC building (ECC-801 to ECC-810). It builds weekly timetables with a constraint solver written in SWI-Prolog, which fills any room, day or start time a professor leaves open and resolves clashing requests.

The user uploads a schedule CSV with one row per class (room, day, start, span, title, prof, students) and a config JSON with the semester, academic year and seat capacity of every room, where 0 marks a room not used for lectures, such as ECC-806. Each day has a morning period (09:00 to 12:00) and an afternoon period (13:00 to 16:00), and every class fills one whole period.

The CSV opens in an editor. Its Classes tab edits each row, where "Any" leaves a room, day or period to Prolog, and its Professors tab applies a professor's preferred day or period to all their classes. Clashes are flagged but allowed.

Every timetable must satisfy these hard rules:

- A room holds at most one class per period.
- A professor teaches at most one class per period.
- The number of students never exceeds the room's capacity.

A room, day or start in the CSV is a request, not a fixed rule, and Prolog fills every blank, giving each class the smallest room that fits and filling weekdays before the weekend. Every CSV, complete or not, goes through the scheduler, which returns up to N timetables, called cases (10 by default, 0 for no limit). If every class can get what it asked for, only OK cases are returned, and a complete CSV without clashes gives exactly one. Otherwise it returns unsatisfied cases, with some classes moved to a free spot, fewest moved first. Only when moving classes cannot help, such as with more 100-student classes than big-room periods, is the user told no timetable exists. Invalid rows, such as an unknown room, are rejected with their row number.

A Svelte frontend has the editor, a tab per case with moved classes in red, and a clickable floor plan with each room's weekly timetable. A FastAPI gateway validates the files, runs Prolog as a subprocess, re-validates, scores and ranks the cases, and renders a PDF of the chosen case, one page per classroom.

  #pagebreak()

  // ---------------------------------------------------------------- AI Concepts
  #section-title[The AI Concepts to Apply in this Project]

The scheduler models timetabling as a #strong[Constraint Satisfaction Problem] (CSP) and solves it with SWI-Prolog's finite-domain constraint library, `library(clpfd)`. The model is in `scheduler.pl`, and the gateway's `prolog_engine.py` prepares its input and reads its output. `scheduler.pl` has two entry points that share one model: `main_cases`, which the web app uses and which returns several timetables, and `main_timetable`, which returns one.

#subhead[Knowledge representation]

The gateway encodes each course as an integer term `c(MinRoom, Prof, Room, Day, Period)`. Rooms are numbered in order of capacity, days 0 to 6 from Monday and periods 0 (morning) and 1 (afternoon). MinRoom is the smallest room that seats the class, and −1 means "Prolog picks". Each professor gets a number, and names that differ only in case or spacing count as the same professor. The sample CSV becomes one term, read with `read_term/3`, which parses data but never runs it. The last two numbers are the time limit in seconds and the number of cases to return:

```erlang
request([c(2,0,-1,-1,1), c(2,1,5,0,-1),
         c(8,2,-1,4,-1), c(2,3,4,-1,-1)], 10, 10, 10).
```

#subhead[CSP formulation]

- #strong[Variables:] one Slot per class, where Slot = (Day × 2 + Period) × NumRooms + Room, so a single variable holds the room, day and period.
- #strong[Domains:] the slots with a room from MinRoom upward that match the room, day or period the class asks for.
- #strong[Hard constraints:] all slots differ, and each professor's times differ.
- #strong[Soft constraints:] each class's requested room, day and period, set in the CSV or the editor. They stay in the domains while every request can be met, and are relaxed only when they cannot.
- #strong[Goal:] up to N solutions that move the fewest classes off their requests: OK cases (none moved) if any exist, otherwise 1 moved class, then 2, and so on. Solutions with the same number of moved classes come in the preferred order.

#subhead[Node consistency]

`course_slot/4` enumerates every allowed (Day, Period, Room) with `findall/3` and `between/3` and turns the list into the variable's domain:

```erlang
course_slot(NumRooms, c(MinRoom, Prof, FixedRoom, FixedDay,
                        FixedPeriod), Slot, Prof-Time) :-
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
```

Removing values that break unary constraints before search is node consistency: a class never gets a room that is too small, and ECC-806 (capacity 0) is in no domain. `matches/2` treats −1 as "any value".

#subhead[Global constraints and propagation]

```erlang
place(Courses, NumRooms, Placements) :-
    maplist(course_slot(NumRooms), Courses, Slots, ProfTimes),
    all_distinct(Slots),
    keysort(ProfTimes, Sorted),
    group_pairs_by_key(Sorted, ByProf),
    maplist(prof_free, ByProf),
    labeling([ff], Slots),
    maplist(slot_placement(NumRooms), Slots, Placements).

prof_free(_-Times) :- all_distinct(Times).
```

`all_distinct(Slots)` gives each room one class per period, and `all_distinct` on each professor's times, grouped with `group_pairs_by_key/2`, gives each professor one class per period. `all_distinct/1` reasons over all domains together, so 30 flexible 100-student classes, which fit only the 28 slots of ECC-808 and ECC-809, fail in about 0.1 seconds without search. Each assignment also prunes the domains of clashing classes (forward checking).

#subhead[Backtracking search and heuristics]

`labeling([ff], Slots)` is a depth-first search with chronological backtracking: choose a variable, try a value, propagate, and undo the choice on failure. Two heuristics guide it:

- #strong[Variable order (ff):] the class with the fewest slots left goes first (minimum remaining values).
- #strong[Value order:] lowest slot first, so each class gets the earliest period and the smallest room that fits.

#subhead[Enumerating several solutions]

`main_cases` runs the same search but does not stop at the first answer:

```erlang
forall(place(Courses, NumRooms, Placements),
       emit_case(Placements, MaxCases))
```

`forall/2` prints each timetable as soon as it is found and then backtracks into `labeling/2` for the next one. The cases therefore come out in labeling order, and consecutive cases first differ in the class that was decided last. Once MaxCases timetables are printed, `emit_case/2` throws an exception that ends the search.

#subhead[Soft constraints and relaxation]

If no timetable meets every request, `relaxed_place/4` solves a relaxed problem with the same hard constraints:

```erlang
relaxed_place(Courses, NumRooms, Moved, Placements) :-
    maplist(free_slot(NumRooms), Courses, Slots, ProfTimes, Flags),
    all_distinct(Slots),
    keysort(ProfTimes, Sorted),
    group_pairs_by_key(Sorted, ByProf),
    maplist(prof_free, ByProf),
    sum(Flags, #=, Moved),
    labeling([], Flags),
    labeling([ff], Slots),
    maplist(slot_placement(NumRooms), Slots, Placements).
```

`free_slot/5` gives each class every slot in a room big enough for it, plus a 0/1 variable Flag tied to its request by reification. Using only the fields the class asked for, it amounts to:

```erlang
Flag #<==> (Room #\= R #\/ Day #\= D #\/ Period #\= P)
```

`sum/3` makes exactly Moved flags equal to 1, and `main_cases` tries Moved = 1, then 2, 3 and so on, so the first cases always move the fewest classes possible. Labeling the flags first, 0 before 1, keeps classes in place where possible, and a flag of 0 narrows the slot back to the request by propagation. This is a Max-CSP: every hard constraint holds, and as many soft constraints as possible.

#subhead[Completeness, time limit and verification]

The search is complete. If even the fully relaxed problem has no solution, for example with more 100-student classes than big-room periods, the answer is unsatisfiable, which proves no timetable fits. `call_with_time_limit/2` stops the search after 10 seconds and keeps the cases found so far; with no case limit (N = 0) there is no time limit either. For the sample, the first case Prolog prints is "case -1 2 0 1 5 0 0 8 4 0 4 0 0": Algorithms in ECC-801 on Monday afternoon, Databases and Operating Systems on Monday morning, and Compiler Design in ECC-808 on Friday morning. When Databases and Software Design both ask for ECC-804 on Monday morning, every case moves exactly one class; in the first, Software Design moves to ECC-801. The gateway scores each case as the percentage of classes that got what they asked for, drops duplicates, ranks the cases by moved classes and re-validates each one.

  #pagebreak()

  // ---------------------------------------------------------------- Screen designs
  #section-title[Draft of Screen Design of your Program]

#screen("Screen 1: Main Page", "./images/01_Main.png")

#screen("Screen 2: Main Page when files got uploaded", "./images/02_Main_Uploaded.png")

#screen("Screen 3: Ran Invalid Test with limit = 10, choice = 1, room capacity = 50", "./images/03_Ran_Invalid_N10_C1_S50.png")

#screen("Screen 4: Ran Invalid Test with limit = 10, choice = 10, room capacity = 0", "./images/04_Ran_Invalid_N10_C10_S0.png")

#screen("Screen 5: Ran Invalid Test with limit = 30, choice = 1, room capacity = 50", "./images/05_Ran_Invalid_N30_C1_S50.png")

#screen("Screen 6: Ran Invalid Test with limit = 30, choice = 27, room capacity = 50", "./images/06_Ran_Invalid_N30_C27_S50.png")

#screen("Screen 7: Ran Valid Test with limit = 10, choice = 1, room capacity = 100", "./images/07_Ran_Valid_N10_C1_S5.png")

#screen("Screen 8: Ran Valid Test with limit = 5, choice = 1, room capacity = 100", "./images/08_Ran_Valid_N5_C1_S100.png")

#screen("Screen 9: Ran Valid Test with limit = 5, choice = 1, room capacity = 0", "./images/09_Ran_Valid_N5_C1_S0.png")

#screen("Screen 10: CSV Editor Page", "./images/10_CSV_Editor.png")

#screen("Screen 11: Constraints Editor Initially", "./images/11_Constraint_Editor_Before.png")

#screen("Screen 12: Constraints Editor After Edit", "./images/12_Constrain_Editor_After.png")

#screen("Screen 13: Constraints Editor Toggling to show Professor's classes", "./images/13_Constraint_Editor_Show_Classes.png")

#screen("Screen 14: Preview of Output PDF of the Valid Case", "./images/14_Output_Valid_PDF.png")
]

// ------------------------------------------------------------------ Appendix
#include "./Test.typ"
#include "./Codebase.typ"
