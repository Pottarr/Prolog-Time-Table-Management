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

Prolog Time Table Management is a classroom timetabling system for the ten rooms on the 8th floor of the ECC building (ECC-801 to ECC-810). It builds a weekly timetable in which no room or professor is double-booked and every class has enough seats. Any room, day or start time a professor leaves open is chosen by a constraint solver written in SWI-Prolog.

The user uploads a schedule CSV with one row per class (room, day, start, span, title, prof, students) and a config JSON with the semester, academic year and seat capacity of every room, where 0 marks a room not used for lectures, such as ECC-806. Each day has a morning period (09:00 to 12:00) and an afternoon period (13:00 to 16:00), and every class fills one whole period.

Every timetable must satisfy these rules:

- A room holds at most one class per period.
- A professor teaches at most one class per period.
- The number of students never exceeds the room's capacity.
- Rooms, days and start times fixed in the CSV are kept.

With a complete CSV, the system checks the rules and reports the first row that breaks one. With auto-scheduling on, room, day and start may be blank or NULL, and Prolog fills every blank, giving each class the smallest room that fits and filling weekdays before the weekend. If no valid timetable exists, the user is told so.

A Svelte frontend takes the uploads and shows a clickable floor plan with each room's weekly timetable. A FastAPI gateway validates the files, runs the Prolog solver as a subprocess and renders a PDF with one page per classroom. The solver's answer is checked again by the same validator before it is shown.

  #pagebreak()

  // ---------------------------------------------------------------- AI Concepts
  #section-title[The AI Concepts to Apply in this Project]

The auto-scheduler models timetabling as a #strong[Constraint Satisfaction Problem] (CSP) and solves it with SWI-Prolog's finite-domain constraint library, `library(clpfd)`. The model is in `scheduler.pl`, and the gateway's `prolog_engine.py` prepares its input and checks its output.

#subhead[Knowledge representation]

The gateway encodes each course as an integer term `c(MinRoom, Prof, Room, Day, Period)`. Rooms are numbered in order of capacity, days 0 to 6 from Monday and periods 0 (morning) and 1 (afternoon). MinRoom is the smallest room that seats the class, and −1 means "Prolog picks". The sample CSV becomes one term, read with `read_term/3`, which parses data but never runs it:

```erlang
request([c(2,0,-1,-1,1), c(2,1,5,0,-1),
         c(8,2,-1,4,-1), c(2,3,4,-1,-1)], 10, 10).
```

#subhead[CSP formulation]

- #strong[Variables:] one Slot per class, where Slot = (Day × 2 + Period) × NumRooms + Room, so a single variable holds the room, day and period.
- #strong[Domains:] the slots with a room from MinRoom upward that match any fixed room, day or period.
- #strong[Constraints:] all slots differ, and each professor's times differ.
- #strong[Goal:] the first assignment found in the preferred order. There is no objective function.

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

#subhead[Completeness, time limit and verification]

The cut in `solve/4` keeps the first solution. If labeling exhausts the search space, the answer is unsatisfiable, which proves no timetable fits. `call_with_time_limit/2` stops the search after 10 seconds. For the sample, Prolog prints "ok 2 0 1 5 0 0 8 4 0 4 0 0": Algorithms in ECC-801 on Monday afternoon, Databases and Operating Systems on Monday morning, and Compiler Design in ECC-808 on Friday morning. The gateway re-validates this answer before showing it.

  #pagebreak()

  // ---------------------------------------------------------------- Screen designs
  #section-title[Draft of Screen Design of your Program]

#screen("Screen 1", "./images/screen1.png")

#screen("Screen 2", "./images/screen2.png")

#screen("Screen 3", "./images/screen3.png")

#screen("Screen 4", "./images/screen4.png")

#screen("Screen 5", "./images/screen5.png")

#screen("Screen 6", "./images/screen6.png")
]

// ------------------------------------------------------------------ Appendix
#include "./Codebase.typ"
#include "./Test.typ"
