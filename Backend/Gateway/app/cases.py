"""Turning the scheduler's answers into ranked cases, and editor helpers.

A *case* is one complete timetable; no case ever double-books a room or a
professor. A class's room/day/start in the CSV is what it *asked for*. In
an *unsatisfied* case some classes didn't get it — Prolog moved them to a
free spot. Each case gets the list of those classes, their count
(`errors`), a score (% of classes satisfied, unless Prolog sends its own)
and a rank: fewest moved classes first, then in the order Prolog found
them.
"""

from app.building import DAYS, PERIODS
from app.csv_validation import prof_key

DEFAULT_CASES = 10  # max_cases <= 0 means no cap

_PERIOD_STARTS = {begin: name for name, (begin, _) in PERIODS.items()}


def _when(day: str | None, start: int | None, room: str | None) -> str:
    parts = [
        day or "any day",
        _PERIOD_STARTS.get(start, f"{start}:00") if start is not None else "any time",
        room or "any room",
    ]
    return " ".join(parts)


def unsatisfied_classes(courses: list[dict], classes: list[dict]) -> list[dict]:
    """The classes that didn't get the room/day/start they asked for.

    `courses` are the requests (room/day/start may be None = flexible),
    `classes` the case's timetable, in the same order.
    """
    moved = []
    for i, (asked, got) in enumerate(zip(courses, classes)):
        missed = [
            field
            for field in ("room", "day", "start")
            if asked[field] is not None and asked[field] != got[field]
        ]
        if missed:
            moved.append(
                {
                    "row": i,
                    "missed": missed,
                    "asked": {f: asked[f] for f in ("room", "day", "start")},
                    "message": (
                        f"{got['title']} ({got['prof'].strip()}): asked "
                        f"{_when(asked['day'], asked['start'], asked['room'])}, got "
                        f"{_when(got['day'], got['start'], got['room'])}"
                    ),
                }
            )
    return moved


def rank_cases(cases: list[dict], courses: list[dict]) -> list[dict]:
    """Adds unsatisfied/errors/score/status to each case and sorts best first.

    Each input case is {"score": int | None, "classes": [...], "csv": str}.
    Ranking: fewest unsatisfied classes first (OK cases have 0), then
    Prolog's order. Identical timetables are kept once.
    """
    seen = set()
    ranked = []
    for order, case in enumerate(cases):
        key = tuple((c["room"], c["day"], c["start"]) for c in case["classes"])
        if key in seen:
            continue
        seen.add(key)
        moved = unsatisfied_classes(courses, case["classes"])
        total = len(case["classes"])
        score = case["score"]
        if score is None:
            score = 100 * (total - len(moved)) // total if total else 100
        ranked.append(
            {
                **case,
                "score": score,
                "unsatisfied": moved,
                "errors": len(moved),
                "status": "unsatisfied" if moved else "ok",
                "_order": order,
            }
        )
    ranked.sort(key=lambda c: (c["errors"], c["_order"]))
    for rank, case in enumerate(ranked, start=1):
        del case["_order"]
        case["rank"] = rank
    return ranked


def apply_professor_preference(rows: list[dict], prof: str, day: str, period: str) -> list[dict]:
    """Rewrites `day` / `start` on every row taught by `prof`.

    `day` is "keep", "any" (flexible -> NULL) or a day code; `period` is
    "keep", "any", or a period name ("morning" / "afternoon"), written as
    that period's start hour. Professors match case- and
    whitespace-insensitively, like everywhere else. Other columns and other
    professors' rows are returned unchanged.
    """
    if day not in ("keep", "any", *DAYS):
        raise ValueError(f"'day' must be keep, any or one of {', '.join(DAYS)}.")
    if period not in ("keep", "any", *PERIODS):
        raise ValueError(f"'period' must be keep, any or one of {', '.join(PERIODS)}.")

    key = prof_key(prof)
    out = []
    for row in rows:
        row = dict(row)
        if prof_key(row.get("prof") or "") == key:
            if day != "keep":
                row["day"] = None if day == "any" else day
            if period != "keep":
                row["start"] = None if period == "any" else str(PERIODS[period][0])
        out.append(row)
    return out
