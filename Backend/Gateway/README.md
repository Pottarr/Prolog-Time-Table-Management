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
