# Prolog Time Table Management

A classroom timetable and room-management system for the ECC building's
8th floor (rooms ECC-801 – ECC-810). A schedule CSV and a config JSON
(semester, academic year, room capacities) go in; a clickable floor plan
with per-room weekly timetables and a printable PDF come out. Any room,
day or time a professor left flexible is filled in by an SWI-Prolog
CLP(FD) constraint solver.

## Current status

| Piece | State |
|---|---|
| Frontend (upload, floor plan, room timetables) | Working |
| Gateway (validation, JSON, PDF rendering) | Working |
| Prolog auto-scheduling (`app/prolog/scheduler.pl`) | Working — fills blank room/day/start, or proves no timetable fits |

## Architecture

```text
Browser
   |
   v
Frontend (Svelte + Vite, served by Nginx in prod)
   |
   | HTTP + multipart/JSON  (/api/*)
   v
Gateway (FastAPI, Python, managed with uv)
   |  - validates the uploaded CSV + config (rooms, periods, capacity,
   |    one class per room / per professor per period)
   |  - returns the schedule as JSON for the floor plan
   |  - renders it to PDF via the `typst` CLI
   |
   | `swipl` subprocess in the same container (stdin/stdout, no network)
   v
Prolog scheduler (SWI-Prolog CLP(FD), app/prolog/scheduler.pl)
   |  - picks a room/day/period for every flexible class
   v
Completed timetable -> re-validated by the gateway -> UI / PDF
```

Prolog used to run as its own container (`Backend/Prolog`), talking to the
gateway over the internal Docker network. It now runs inside the gateway
container: `Backend/Gateway/app/prolog_engine.py` starts `swipl` on
`scheduler.pl` per request, the same way the gateway runs `typst`. (It was
briefly embedded in-process via pyswip, but pyswip 0.3.3 can't read query
results back from SWI-Prolog 10.)

See `MasterPlan.md` for the original design rationale, and
`Prolog-Time-Table-Management-Setup.md` for how the original standalone
Prolog container was bootstrapped.

## Repository layout

```text
Frontend/            Svelte + Vite single-page app
Backend/Gateway/      FastAPI service — CSV/config validation, typst
                      rendering, and the Prolog scheduler (app/prolog/)
test/                 Sample CSVs + config, and hand-test cases (test/cases/)
compose.yaml          Runs Frontend + Gateway together
MasterPlan.md          Design notes for the Frontend/Gateway split
Prolog-Time-Table-Management-Setup.md   Original standalone Prolog
                      container walkthrough (since merged into the gateway)
```

## Running it

### Option A: Docker Compose (recommended)

```bash
docker compose up -d --build
```

- Frontend: http://localhost:9090
- Gateway: http://localhost:8000 (also reachable from the frontend
  container as `http://gateway:8000`, and proxied through the frontend at
  `http://localhost:9090/api/*`)

Prolog runs inside the gateway container (`swipl` is installed in its
image) — there's no separate Prolog container to wire in.

### Option B: run each piece locally

Gateway (needs the `typst` CLI and `swipl` on `PATH` — e.g.
`apt install swi-prolog-nox` on Debian/Ubuntu — plus
[uv](https://docs.astral.sh/uv/)):

```bash
cd Backend/Gateway
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Frontend (in another terminal):

```bash
cd Frontend
npm install
npm run dev
```

Open the URL Vite prints (typically http://localhost:5173) — its dev
server proxies `/api/*` to `http://localhost:8000` automatically.

## Using the app

1. Open the frontend.
2. Choose a schedule CSV and a config JSON (see the formats below, and the
   samples in `test/`).
3. Leave **auto-scheduling** unchecked for a complete CSV and press **Load
   schedule**: the ECC 8th-floor plan appears — click any room to see its
   weekly timetable, and use **Download summary PDF** for the printable
   version (one page per room). Check it for an incomplete CSV: Prolog
   fills in the blanks and the result is shown the same way, plus a
   **Download completed CSV** link.

### Config format

A JSON file with the semester, academic year, and the seat capacity of
every room (all ten must be listed, each a positive integer):

```json
{
  "semester": 1,
  "academic_year": 2026,
  "rooms": {
    "ECC-801": 40, "ECC-802": 40, "ECC-803": 40, "ECC-804": 40,
    "ECC-805": 30, "ECC-806": 60, "ECC-807": 60, "ECC-808": 120,
    "ECC-809": 120, "ECC-810": 40
  }
}
```

### CSV format

Seven columns, in this order:

```text
room,day,start,span,title,prof,students
```

| Column | Meaning | Values |
|---|---|---|
| `room` | Room name | One of the ECC 8th-floor rooms `ECC-801` … `ECC-810` |
| `day` | Day of week | Three-letter code: `Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat`, `Sun` |
| `start` | Starting hour (24h) | Must put the class inside one period (below) |
| `span` | Length in hours | `1`–`3` |
| `title` | Course name | Free text; optional notes in parentheses |
| `prof` | Professor name | Free text |
| `students` | Enrolled students | Positive integer, at most the room's capacity |

Example: `ECC-804,Mon,9,3,Software Design and Architecture,Dr. Veera,35`
means that course runs 09:00–12:00 on Monday in room ECC-804 for 35
students.

Rules enforced by the gateway:

- **Periods** — each day has two periods, **morning 09:00–12:00** and
  **afternoon 13:00–16:00**; a class must fit entirely inside one, and a
  room holds at most one class per period (so at most two per day). A
  shorter class still takes the whole period. 12:00–13:00 is lunch.
- **Capacity** — `students` must not exceed the room's capacity from the
  config (equal is fine).
- **Professor** — a professor teaches at most one class per period per
  day (names compare ignoring case and extra spaces).
- The same course may appear more than once (e.g. several sections); add
  any detail in parentheses in the title, e.g. `Algorithms (Section 2)`.
  Quote the title if it contains a comma: `"Algorithms (Sec 2, English)"`.

The timetable grid in the UI and PDF still shows 09:00–19:00; slots after
16:00 simply stay empty.

### Auto-scheduling (incomplete CSVs)

When the auto-scheduling checkbox is on, `room`, `day`, and `start` may
each be left **blank** or set to the literal text **`NULL`** — meaning the
professor is flexible on that one dimension. `span`, `title`, `prof`, and
`students` are always required (a course's length, identity and size are
never something to solve for). A blank room may only be filled with one
whose capacity fits `students`.

```text
NULL,NULL,13,3,Algorithms,Dr. Veera,35
```
→ any day, any room with ≥ 35 seats, but must start at 13:00.

```text
ECC-804,Mon,NULL,3,Databases,Dr. Suphamit,40
```
→ must be room ECC-804 on Monday, any start time.

The gateway validates this shape (including that a given room is big
enough, or that *some* room is when none is given), then Prolog picks a
room, day and period for every flexible class: each class gets the
smallest room that fits, weekdays fill before the weekend, and no room or
professor is double-booked in a period. A flexible `start` becomes the
start of the chosen period (09:00 or 13:00). If no timetable fits every
rule, the gateway answers 422 with the reason. The solved timetable is
re-checked by the same rules as a hand-written CSV before it's returned.

## Test data

`test/` has sample files for exercising the gateway directly:

- **`test/config.json`** — semester, year, and room capacities
  (808 and 809 are the 120-seat rooms). Placeholder capacities: replace
  with the real ones.
- **`test/schedule-complete.csv`** — a fully-specified schedule (every
  room/day/time filled in), including 100+-student classes in 808/809.
  Use it against `/api/schedule/parse` or `/api/schedule/pdf`.
- **`test/schedule-incomplete.csv`** — the same idea but with `room`,
  `day`, and/or `start` left as `NULL` on several rows, covering every
  combination (fully flexible, fixed-room-flexible-time, fixed-day-only,
  etc). Use it against `/api/schedule/auto`.

With the gateway running on `localhost:8000`:

```bash
# Complete CSV -> PDF
curl -o schedule.pdf \
  -F "csv_file=@test/schedule-complete.csv" \
  -F "config_file=@test/config.json" \
  http://localhost:8000/api/schedule/pdf

# Incomplete CSV -> Prolog fills the blanks; JSON with the completed schedule + `csv`
curl \
  -F "csv_file=@test/schedule-incomplete.csv" \
  -F "config_file=@test/config.json" \
  http://localhost:8000/api/schedule/auto
```

For more detail on each piece, see `Frontend/README.md` and
`Backend/Gateway/README.md`.
