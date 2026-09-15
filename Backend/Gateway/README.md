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
- `POST /api/schedule/pdf` — multipart form with:
  - `csv_file`: the schedule CSV (`room,day,start,span,title,prof` columns)
  - `semester`: `1` or `2`
  - `academic_year`: integer year

  Returns `application/pdf` on success, or a `422` with a JSON `detail`
  message on invalid input or an unsatisfiable/invalid schedule (e.g.
  overlapping classes in the same room).

## Docker

```bash
docker build -t schedule-gateway .
```

The image downloads a pinned `typst` release binary in a build stage so
the runtime image doesn't need network access. Use the root
`compose.yaml` to run this alongside the frontend.

## Prolog integration

Not wired up yet — this gateway currently only renders whatever CSV it's
given. See `MasterPlan.md` at the repo root for how the Prolog solver is
intended to plug in later (generating the CSV instead of a human).
