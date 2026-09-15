# Prolog Time Table Management

A classroom timetable and room-management system. A professor's course
requirements (room, day, time, duration) go in as a CSV; a printable PDF
timetable comes out. Scheduling *reasoning* — filling in a room/day/time a
professor left flexible, and eventually optimizing for the fewest rooms
used — is meant to be handled by an SWI-Prolog constraint solver.

## Current status

| Piece | State |
|---|---|
| Frontend (upload UI) | Working |
| Gateway (CSV validation + PDF rendering) | Working |
| Gateway → Prolog auto-scheduling call | **Not implemented** — contract documented, returns `501` with the request it would send |
| Prolog solver | Proof-of-concept only (unrelated family-tree demo, see `Prolog-Time-Table-Management-Setup.md`) |

In other words: today you can upload a **complete** schedule CSV and get a
PDF back. You can also upload an **incomplete** one and check the
"auto-scheduling" box, but instead of calling Prolog to solve it, the
gateway shows you the request it *would* send. Solving is future work.

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
   |  - validates the uploaded CSV
   |  - renders it to PDF via the `typst` CLI            [implemented]
   |  - OR builds a request for Prolog and stops there    [stubbed, 501]
   |
   | HTTP + JSON  (internal Docker network only, not built yet)
   v
Prolog service (SWI-Prolog, Backend/Prolog/)
   |  - facts, rules, CLP(FD) constraints, optimization
   v
Resolved room/day/time assignment
```

See `MasterPlan.md` for the fuller design rationale, and
`Prolog-Time-Table-Management-Setup.md` for how the Prolog container itself
was bootstrapped (currently a small family-relationship demo, not yet the
timetable solver).

## Repository layout

```text
Frontend/            Svelte + Vite single-page app
Backend/Gateway/      FastAPI service — CSV validation, typst rendering,
                      the (stubbed) Prolog request builder
Backend/Prolog/       SWI-Prolog HTTP service (proof-of-concept only)
test/                 Sample CSVs for exercising the gateway (see below)
compose.yaml          Runs Frontend + Gateway together
MasterPlan.md          Design notes for the Frontend/Gateway split
Prolog-Time-Table-Management-Setup.md   Prolog container walkthrough
```

## Running it

### Option A: Docker Compose (recommended)

```bash
docker compose up -d --build
```

- Frontend: http://localhost:8080
- Gateway: http://localhost:8000 (also reachable from the frontend
  container as `http://gateway:8000`, and proxied through the frontend at
  `http://localhost:8080/api/*`)

The Prolog service isn't wired into `compose.yaml` yet — see "Current
status" above.

### Option B: run each piece locally

Gateway (needs the `typst` CLI on `PATH`, plus [uv](https://docs.astral.sh/uv/)):

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
2. Choose a schedule CSV (see the format below, and the samples in
   `test/`).
3. Pick a semester (1 or 2) and academic year.
4. Leave **auto-scheduling** unchecked for a complete CSV — this renders
   the PDF directly and lets you preview/download it. Check it for an
   incomplete CSV — since Prolog isn't wired up yet, you'll instead see
   the JSON request the gateway would have sent it.

### CSV format

Six columns, in this order:

```text
room,day,start,span,title,prof
```

| Column | Meaning | Values |
|---|---|---|
| `room` | Room name | e.g. `ECC-804` |
| `day` | Day of week | Three-letter code: `Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat`, `Sun` |
| `start` | Starting hour (24h) | `9`–`11` or `13`–`18` — `12` is a fixed lunch break |
| `span` | Length in hours | Integer, e.g. `3` |
| `title` | Course name | Free text |
| `prof` | Professor name | Free text |

Example: `ECC-804,Mon,9,3,Software Design and Architecture,Dr. Veera`
means that course runs 09:00–12:00 on Monday in room ECC-804.

Rules enforced by the PDF renderer: no two classes may overlap in the same
room, and no class may overlap the 12:00–13:00 lunch slot.

### Auto-scheduling (incomplete CSVs)

When the auto-scheduling checkbox is on, `room`, `day`, and `start` may
each be left **blank** or set to the literal text **`NULL`** — meaning the
professor is flexible on that one dimension. `span`, `title`, and `prof`
are always required (a course's length and identity are never something
to solve for).

```text
NULL,NULL,13,3,Algorithms,Dr. Veera
```
→ any day, any room, but must start at 13:00.

```text
ECC-804,Mon,NULL,3,Databases,Dr. Suphamit
```
→ must be room ECC-804 on Monday, any start time.

The gateway validates this shape and builds the exact JSON payload it will
one day POST to the Prolog service — see the docstring in
`Backend/Gateway/app/prolog_client.py` for the full request/response
contract, including what a resolved answer from Prolog is expected to
look like.

## Test data

`test/` has two sample CSVs for exercising the gateway directly:

- **`test/schedule-complete.csv`** — a fully-specified schedule (every
  room/day/time filled in). Use it against `/api/schedule/pdf`.
- **`test/schedule-incomplete.csv`** — the same idea but with `room`,
  `day`, and/or `start` left as `NULL` on several rows, covering every
  combination (fully flexible, fixed-room-flexible-time, fixed-day-only,
  etc). Use it against `/api/schedule/auto`.

With the gateway running on `localhost:8000`:

```bash
# Complete CSV -> PDF
curl -o schedule.pdf \
  -F "csv_file=@test/schedule-complete.csv" \
  -F "semester=1" -F "academic_year=2026" \
  http://localhost:8000/api/schedule/pdf

# Incomplete CSV -> the Prolog request the gateway would send (501, not implemented yet)
curl \
  -F "csv_file=@test/schedule-incomplete.csv" \
  -F "semester=1" -F "academic_year=2026" \
  http://localhost:8000/api/schedule/auto
```

For more detail on each piece, see `Frontend/README.md` and
`Backend/Gateway/README.md`.
