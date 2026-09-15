"""Contract for the (not-yet-implemented) call from the gateway to the
Prolog auto-scheduling service.

This module only builds the request payload described below — it does not
perform any network call yet. `Backend/Prolog` doesn't expose an
auto-scheduling endpoint at this point, so `/api/schedule/auto` stops after
building this payload and reports back what it *would* have sent (see
`app/main.py`). Wiring up the actual HTTP call is future work, once the
Prolog side of this contract exists.

--------------------------------------------------------------------------
Planned request: gateway -> Prolog
--------------------------------------------------------------------------

    POST http://prolog:8081/generate-timetable
    Content-Type: application/json

    (internal Docker-network call only — never exposed to the browser,
    same rule as every other Prolog endpoint; see the root MasterPlan.md)

Body:

    {
      "semester": 1,
      "academic_year": 2026,
      "courses": [
        {
          "title": "Real Time Embedded System",
          "prof": "Dr. Pipat",
          "span": 3,
          "room": null,
          "day": null,
          "start": 13
        },
        {
          "title": "Theory of Computation",
          "prof": "Dr. Natthapong",
          "span": 3,
          "room": "ECC-803",
          "day": "Mon",
          "start": null
        }
      ]
    }

Each entry corresponds to one row of the uploaded CSV:

  - `title`, `prof`, `span`  — always present (never solved for).
  - `room`   — a fixed room name, or `null` meaning "any room works".
  - `day`    — a fixed three-letter day code (Mon..Sun), or `null` meaning
               "any day works".
  - `start`  — a fixed starting hour (9-11 or 13-18; 12 is lunch, same as
               the typst template's rule), or `null` meaning "any time
               that day works".

`null` is exactly the CSV's blank/"NULL" convention carried into JSON —
see `app.csv_validation.parse_partial_schedule_csv`.

--------------------------------------------------------------------------
Planned response: Prolog -> gateway
--------------------------------------------------------------------------

Success — every course could be placed without conflicts:

    {
      "status": "ok",
      "assignments": [
        {
          "title": "Real Time Embedded System",
          "prof": "Dr. Pipat",
          "room": "ECC-804",
          "day": "Thu",
          "start": 13,
          "span": 3
        },
        ...
      ]
    }

Failure — no assignment satisfies every constraint:

    {
      "status": "unsatisfiable",
      "reason": "human-readable explanation of the conflicting constraint"
    }

On success, the gateway turns `assignments` back into a complete
`room,day,start,span,title,prof` CSV and renders it through the same
typst template `/api/schedule/pdf` already uses — auto-scheduling and
manual upload converge on the same rendering path once Prolog has
resolved the blanks.
"""

from typing import TypedDict


class CourseConstraint(TypedDict):
    room: str | None
    day: str | None
    start: int | None
    span: int
    title: str
    prof: str


def build_prolog_request(
    semester: int, academic_year: int, courses: list[CourseConstraint]
) -> dict:
    """Builds the JSON payload the gateway will POST to the Prolog service.

    Pure data shaping, no network call — see the module docstring for the
    full contract this payload is expected to satisfy once implemented.
    """
    return {
        "semester": semester,
        "academic_year": academic_year,
        "courses": courses,
    }
