# Gateway — Classroom Schedule Generator

FastAPI service (managed with [uv](https://docs.astral.sh/uv/)) that turns
an uploaded schedule CSV into a PDF timetable by compiling it through the
bundled typst template (`app/templates/classroom-schedule.typ`).

## Develop

Requires the `typst` CLI on `PATH` (v0.12.x) in addition to Python deps.

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

## API

- `GET /api/health` — liveness check.
- `POST /api/schedule/parse` — same form fields and checks as
  `/api/schedule/pdf`, but returns the schedule as JSON
  (`building`, `floor`, `rooms`, `periods`, `semester`, `academic_year`,
  `capacities`, `classes`). The frontend uses this to draw the clickable
  floor plan and per-room timetables.
- `POST /api/schedule/pdf` — multipart form with:
  - `csv_file`: the schedule CSV (`room,day,start,span,title,prof,students`)
  - `config_file`: JSON with `semester`, `academic_year`, and `rooms`
    (capacity of each of `ECC-801` … `ECC-810`; `0` = not used for classes)
    — see `app/schedule_config.py`

  Returns `application/pdf` on success, or a `422` with a JSON `detail`
  message on invalid input — e.g. a room that isn't one of the ten (see
  `app/building.py`), a class that isn't exactly 3 hours starting at 9
  (morning, 09–12) or 13 (afternoon, 13–16), two classes in one room's period,
  a professor teaching two classes in the same period, or more students
  than the room's capacity.
- `POST /api/schedule/auto` — same two files, for an incomplete CSV.
  Prolog fills in every blank room/day/start; the response has the same
  shape as `/api/schedule/parse` plus `csv` (the completed schedule, to
  post to `/api/schedule/pdf`). `422` if no timetable fits every rule.
- `POST /api/schedule/cases` — what the frontend uses. Same two files
  plus `max_cases` (default 10; `0` or less = no cap *and* no time limit).
  A given room/day/start is what that class *asks for*, and requests may
  clash (a room or professor asked twice for one period). Rooms and
  professors are never double-booked in a case. If every class can get
  what it asked for, only those cases (`status` `ok`) come back;
  otherwise `unsatisfied` ones, in which some classes were moved to a
  free spot — fewest moved classes first. Response: `cases: [{rank,
  errors, score, status, unsatisfied, classes, csv}]` plus `complete`
  (false if the 10 s limit cut a capped search short). `unsatisfied`
  lists each moved class (`row`, `missed`, `asked`, `message`), `errors`
  is how many, `score` the % of classes satisfied. Capacity, room, day
  and format errors are still a `422`.
- `POST /api/csv/rows` — `csv_file` only; returns its rows for the
  editor (`rows: [{room, day, start, span, title, prof, students}]`,
  blank/NULL as `null`). Only the header is checked.
- `POST /api/csv/professor-preference` — JSON `{rows, prof, day,
  period}`; rewrites `day` / `start` on every row of that professor
  (`day`: `keep` | `any` | `Mon`…`Sun`, `period`: `keep` | `any` |
  `morning` | `afternoon`; `any` writes NULL). Returns `{rows, csv}`.

## Tests

```bash
uv run pytest
```

- `tests/test_schedule_config.py` — the uploaded config JSON.
- `tests/test_csv_validation.py` — every scheduling rule (rooms, days,
  periods, one class per room/professor per period, capacity), for both
  complete and auto-scheduling CSVs.
- `tests/test_api.py` — the HTTP routes end to end (PDF tests are skipped
  if `typst` isn't installed).
- `tests/test_case_files.py` — runs each hand-test file in `test/cases/`
  and checks the result documented in `test/cases/README.md`.

## Docker

```bash
docker build -t schedule-gateway .
```

The image downloads a pinned `typst` release binary in a build stage, and
installs `swi-prolog-nox` for the embedded Prolog engine (see below), so
the runtime image doesn't need network access to build or run. Use the
root `compose.yaml` to run this alongside the frontend.

## Prolog integration

`app/prolog/scheduler.pl` is the auto-scheduler: a CLP(FD) model with one
slot variable per class (`Slot = (Day*2 + Period) * NumRooms + Room`),
`all_distinct` over all slots (one class per room per period) and over
each professor's times (one class at a time), and each class's domain
limited to rooms big enough for it plus any fixed room/day/period.

`app/prolog_engine.py` runs it as a `swipl` subprocess: it encodes the
courses as plain integers (no user text ever reaches Prolog), writes one
`request(...)` term to stdin (read with `read_term/3`, never executed) and
reads one answer line back. The solver has a 10 s limit. It was briefly
embedded in-process via pyswip, but pyswip 0.3.3 can't read query results
back from SWI-Prolog 10.

### Several cases (`main_cases`)

`/api/schedule/cases` runs `main_cases` in `scheduler.pl` (if that goal is
ever missing it falls back to `main_timetable` as one case):

- **stdin:** `request(Courses, NumRooms, TimeLimit, MaxCases).` — the
  same courses/rooms as `main_timetable`; `MaxCases =< 0` means no cap and
  `TimeLimit =< 0` no time limit (the gateway sends 0/0 for "no cap").
- **Hard rules, always:** one class per room per period, one class per
  professor per period, a room big enough for the class.
- **OK cases:** every timetable in which every class gets the room/day/
  period it asked for (`place/3`), in labeling order. If there is at
  least one, nothing else is printed.
- **Unsatisfied cases:** otherwise `relaxed_place/4` lets every class go
  to any free slot in a room that fits, with one 0/1 flag per class
  ("didn't get what it asked for" — room, day or period, counted once),
  and asks for exactly *K* flags set: K = 1, then 2, 3, … until
  `MaxCases` are printed or every level is done.
- **stdout:** one `case -1 R1 D1 P1 R2 ...` line per case as it's found
  (`-1` = the gateway scores it: % of classes satisfied); `unsatisfiable`
  or `timeout` alone if there's none (e.g. more big classes than big-room
  periods); a trailing `timeout` line if the limit stopped the search
  after some cases.
- With no cap the search really runs to the end — for a CSV with many
  flexible classes that can be an enormous number of cases and a very
  long wait. Nginx (`Frontend/nginx.conf`) allows a day per request.
