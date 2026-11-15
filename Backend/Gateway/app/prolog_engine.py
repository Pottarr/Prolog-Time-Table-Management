"""Runs the SWI-Prolog scheduler (`prolog/scheduler.pl`) inside the gateway.

Prolog used to run as its own container (`Backend/Prolog`), reachable
over the internal Docker network — see `Prolog-Time-Table-Management-Setup.md`
for how that was bootstrapped. It now runs in the gateway's own container:
each call starts `swipl` on `scheduler.pl` (the same way `app.typst_render`
shells out to `typst`), writes one request term to its stdin and reads one
answer line back. No HTTP hop, no second container, and a hung or crashed
solver can't take the gateway down with it.

(It was briefly embedded in-process via pyswip, but pyswip 0.3.3 — the
latest release — can't read query results back from SWI-Prolog 10.)

Per the "never expose a raw query endpoint" rule (see §10 of the setup
doc), Prolog only ever runs fixed, known entry points (`main_parent`,
`main_timetable`), and its stdin is read with `read_term/3`, which parses
data and never executes it. `_as_atom` rejects anything that isn't a plain
lowercase atom, and the timetable request is built purely from integers
this module computes — room names, days, titles and professor names never
reach Prolog.
"""

import re
import subprocess
from pathlib import Path

from app.building import DAYS, PERIODS, period_of
from app.csv_validation import prof_key

SCHEDULER_PL = Path(__file__).parent / "prolog" / "scheduler.pl"
SOLVE_TIME_LIMIT_SECONDS = 10
# Headroom over the in-Prolog limit for swipl's own startup.
PROCESS_TIMEOUT_SECONDS = SOLVE_TIME_LIMIT_SECONDS + 10

_ATOM_RE = re.compile(r"^[a-z][a-zA-Z0-9_]*$")
_PERIOD_NAMES = list(PERIODS)
_FREE = -1  # "Prolog picks" in the integer encoding scheduler.pl expects


class PrologError(RuntimeError):
    """Raised when swipl exits abnormally or prints something unexpected."""


def _run(goal: str, request: str) -> str:
    """Runs `goal` from scheduler.pl with `request` on stdin; returns its stdout line."""
    try:
        result = subprocess.run(
            ["swipl", "-q", "-g", goal, "-t", "halt", str(SCHEDULER_PL)],
            input=request,
            capture_output=True,
            text=True,
            timeout=PROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise PrologError(f"swipl didn't finish within {PROCESS_TIMEOUT_SECONDS}s") from exc
    if result.returncode != 0:
        raise PrologError(result.stderr.strip() or f"swipl exited with {result.returncode}")
    return result.stdout.strip()


def _as_atom(value: str) -> str | None:
    """Returns `value` unchanged if it's safe to write as a Prolog atom, else None."""
    return value if _ATOM_RE.match(value) else None


def is_parent(parent: str, child: str) -> bool:
    """Queries the known `parent/2` fact — the successor to the old
    `main.pl` HTTP handler's `parent(Parent, Child)` check."""
    parent_atom = _as_atom(parent)
    child_atom = _as_atom(child)
    if parent_atom is None or child_atom is None:
        return False

    return _run("main_parent", f"query({parent_atom}, {child_atom}).\n") == "true"


def generate_timetable(capacities: dict[str, int], courses: list[dict]) -> dict:
    """Fills in every course's missing room/day/start via `main_timetable`.

    `courses` is the output of `app.csv_validation.parse_partial_schedule_csv`
    (room/day/start may be None). Returns:

        {"status": "ok", "assignments": [{room, day, start, span, period,
                                          title, prof, students}, ...]}
        {"status": "unsatisfiable" | "timeout", "reason": "..."}
    """
    # Smallest rooms first, so Prolog's low-values-first labeling prefers
    # the tightest room that fits each class.
    rooms = sorted(capacities, key=lambda room: (capacities[room], room))
    room_index = {room: i for i, room in enumerate(rooms)}
    prof_ids: dict[str, int] = {}

    terms = []
    for course in courses:
        min_room = next(i for i, room in enumerate(rooms) if capacities[room] >= course["students"])
        prof = prof_ids.setdefault(prof_key(course["prof"]), len(prof_ids))
        room = room_index[course["room"]] if course["room"] is not None else _FREE
        day = DAYS.index(course["day"]) if course["day"] is not None else _FREE
        period = (
            _PERIOD_NAMES.index(period_of(course["start"], course["span"]))
            if course["start"] is not None
            else _FREE
        )
        terms.append(f"c({min_room},{prof},{room},{day},{period})")

    request = f"request([{','.join(terms)}], {len(rooms)}, {SOLVE_TIME_LIMIT_SECONDS}).\n"
    status, *flat = _run("main_timetable", request).split()

    if status == "timeout":
        return {
            "status": "timeout",
            "reason": (
                f"Prolog couldn't find a timetable within {SOLVE_TIME_LIMIT_SECONDS}s — "
                "try fixing more rooms/days/times in the CSV."
            ),
        }
    if status == "unsatisfiable":
        return {
            "status": "unsatisfiable",
            "reason": (
                "No timetable satisfies every rule (one class per room and per "
                "professor per period, room capacity, fixed rooms/days/times). "
                "Free up some fixed values or move classes between periods."
            ),
        }
    if status != "ok" or len(flat) != 3 * len(courses):
        raise PrologError(f"Unexpected answer from scheduler.pl: {status!r}")

    numbers = [int(n) for n in flat]
    assignments = []
    for i, course in enumerate(courses):
        room_i, day_i, period_i = numbers[3 * i : 3 * i + 3]
        period = _PERIOD_NAMES[period_i]
        start = course["start"] if course["start"] is not None else PERIODS[period][0]
        assignments.append(
            {
                "room": rooms[room_i],
                "day": DAYS[day_i],
                "start": start,
                "span": course["span"],
                "period": period,
                "title": course["title"],
                "prof": course["prof"],
                "students": course["students"],
            }
        )
    return {"status": "ok", "assignments": assignments}
