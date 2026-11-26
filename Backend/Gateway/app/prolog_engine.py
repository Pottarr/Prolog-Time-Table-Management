"""Runs the SWI-Prolog scheduler (`prolog/scheduler.pl`) inside the gateway.

Prolog used to run as its own container (`Backend/Prolog`), reachable
over the internal Docker network. It now runs in the gateway's own container:
each call starts `swipl` on `scheduler.pl` (the same way `app.typst_render`
shells out to `typst`), writes one request term to its stdin and reads one
answer line back. No HTTP hop, no second container, and a hung or crashed
solver can't take the gateway down with it.

(It was briefly embedded in-process via pyswip, but pyswip 0.3.3 — the
latest release — can't read query results back from SWI-Prolog 10.)

There is no raw query endpoint: Prolog only ever runs one fixed entry
point (`main_timetable`), and its stdin is read with `read_term/3`, which
parses data and never executes it. The request is built purely from
integers this module computes — room names, days, titles and professor
names never reach Prolog.
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

_PERIOD_NAMES = list(PERIODS)
_FREE = -1  # "Prolog picks" in the integer encoding scheduler.pl expects


class PrologError(RuntimeError):
    """Raised when swipl exits abnormally or prints something unexpected."""


def _run(goal: str, request: str, timeout: float | None = PROCESS_TIMEOUT_SECONDS) -> str:
    """Runs `goal` from scheduler.pl with `request` on stdin; returns its stdout.

    `timeout=None` waits as long as swipl takes (an uncapped cases run).
    """
    try:
        result = subprocess.run(
            ["swipl", "-q", "-g", goal, "-t", "halt", str(SCHEDULER_PL)],
            input=request,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise PrologError(f"swipl didn't finish within {timeout}s") from exc
    if result.returncode != 0:
        raise PrologError(result.stderr.strip() or f"swipl exited with {result.returncode}")
    return result.stdout.strip()


def generate_timetable(capacities: dict[str, int], courses: list[dict]) -> dict:
    """Fills in every course's missing room/day/start via `main_timetable`.

    `courses` is the output of `app.csv_validation.parse_partial_schedule_csv`
    (room/day/start may be None). Returns:

        {"status": "ok", "assignments": [{room, day, start, span, period,
                                          title, prof, students}, ...]}
        {"status": "unsatisfiable" | "timeout", "reason": "..."}
    """
    rooms, terms = _encode(capacities, courses)
    request = f"request([{','.join(terms)}], {len(rooms)}, {SOLVE_TIME_LIMIT_SECONDS}).\n"
    status, *flat = _run("main_timetable", request).split() or [""]

    if status in _FAILURE_REASONS:
        return {"status": status, "reason": _FAILURE_REASONS[status]}
    if status != "ok" or len(flat) != 3 * len(courses):
        raise PrologError(f"Unexpected answer from scheduler.pl: {status!r}")

    return {"status": "ok", "assignments": _decode(rooms, courses, flat)}


_FAILURE_REASONS = {
    "timeout": (
        f"Prolog couldn't find a timetable within {SOLVE_TIME_LIMIT_SECONDS}s — "
        "try fixing more rooms/days/times in the CSV."
    ),
    "unsatisfiable": (
        "No timetable satisfies every rule (one class per room and per "
        "professor per period, room capacity, fixed rooms/days/times). "
        "Free up some fixed values or move classes between periods."
    ),
}


def _encode(capacities: dict[str, int], courses: list[dict]) -> tuple[list[str], list[str]]:
    """Rooms in index order, and one `c(MinRoom, Prof, Room, Day, Period)` term per course."""
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
    return rooms, terms


# ----------------------------------------------------------- several cases
#
# scheduler.pl's multi-case entry point (`main_cases`; if it's ever
# missing, `generate_cases` falls back to `main_timetable` and returns
# that single answer as one case):
#
#   stdin:  request(Courses, NumRooms, TimeLimit, MaxCases).
#           Courses/NumRooms as for main_timetable. MaxCases =< 0 means
#           no cap, TimeLimit =< 0 no time limit (the gateway sends 0 for
#           both when the user asks for no cap).
#   stdout: one line per case, as soon as it's found:
#               case Score R1 D1 P1 R2 D2 P2 ...
#           Score is 0..100, or -1 to let the gateway score it (% of
#           classes that got what they asked for). R/D/P are room/day/period indices
#           per course, as for main_timetable. Fixed room/day/period
#           values are what a class *asks for*; no case ever double-books
#           a room or professor or breaks a capacity. If every class can
#           get what it asked for, only such (OK) cases are printed;
#           otherwise unsatisfied cases, where some classes were moved to
#           a free spot, fewest moved classes first.
#           With no case at all: one "unsatisfiable" or "timeout" line.
#           If the time limit stopped the search after some cases, a
#           final "timeout" line follows them.

_CASES_GOAL_RE = re.compile(r"^main_cases\s*:-", re.MULTILINE)


def scheduler_supports_cases() -> bool:
    """Whether scheduler.pl defines the multi-case `main_cases` entry point."""
    return bool(_CASES_GOAL_RE.search(SCHEDULER_PL.read_text(encoding="utf-8")))


def generate_cases(capacities: dict[str, int], courses: list[dict], max_cases: int) -> dict:
    """Up to `max_cases` timetables for `courses` (see the contract above);
    `max_cases <= 0` means no cap and no time limit.

    Returns {"status": "ok", "complete": bool, "cases": [{"score": int |
    None, "assignments": [...]}, ...]} — score None means "gateway scores
    it", complete False means the time limit cut the search short — or
    {"status": "unsatisfiable" | "timeout", "reason": "..."}.
    """
    if not scheduler_supports_cases():
        result = generate_timetable(capacities, courses)
        if result["status"] != "ok":
            return result
        return {
            "status": "ok",
            "complete": True,
            "cases": [{"score": None, "assignments": result["assignments"]}],
        }

    uncapped = max_cases <= 0
    rooms, terms = _encode(capacities, courses)
    time_limit = 0 if uncapped else SOLVE_TIME_LIMIT_SECONDS
    request = f"request([{','.join(terms)}], {len(rooms)}, {time_limit}, {max(max_cases, 0)}).\n"
    output = _run("main_cases", request, timeout=None if uncapped else PROCESS_TIMEOUT_SECONDS)
    lines = [line.split() for line in output.splitlines() if line.strip()]
    if len(lines) == 1 and len(lines[0]) == 1 and lines[0][0] in _FAILURE_REASONS:
        status = lines[0][0]
        return {"status": status, "reason": _FAILURE_REASONS[status]}
    complete = not (lines and lines[-1] == ["timeout"])
    if not complete:
        lines.pop()

    cases = []
    for words in lines if uncapped else lines[:max_cases]:
        if words[0] != "case" or len(words) != 2 + 3 * len(courses):
            raise PrologError(f"Unexpected answer from scheduler.pl: {' '.join(words[:3])!r}…")
        try:
            score = int(words[1])
        except ValueError as exc:
            raise PrologError(f"Unexpected case score from scheduler.pl: {words[1]!r}") from exc
        if not -1 <= score <= 100:
            raise PrologError(f"Case score out of range from scheduler.pl: {score}")
        cases.append(
            {
                "score": None if score == -1 else score,
                "assignments": _decode(rooms, courses, words[2:]),
            }
        )
    if not cases:
        raise PrologError("scheduler.pl printed no cases")
    return {"status": "ok", "complete": complete, "cases": cases}


def _decode(rooms: list[str], courses: list[dict], flat: list[str]) -> list[dict]:
    """Turns Prolog's flat [R1, D1, P1, R2, ...] back into one row per course."""
    try:
        numbers = [int(n) for n in flat]
    except ValueError as exc:
        raise PrologError("scheduler.pl returned a non-integer placement") from exc

    assignments = []
    for i, course in enumerate(courses):
        room_i, day_i, period_i = numbers[3 * i : 3 * i + 3]
        if not (
            0 <= room_i < len(rooms) and 0 <= day_i < len(DAYS) and 0 <= period_i < len(_PERIOD_NAMES)
        ):
            raise PrologError("scheduler.pl returned an out-of-range placement")
        period = _PERIOD_NAMES[period_i]
        # Keep the asked-for start unless the class was moved to another
        # period (an unsatisfied case); then it starts with its new period.
        asked = course["start"]
        start = asked if asked is not None and period_of(asked, course["span"]) == period else PERIODS[period][0]
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
    return assignments
