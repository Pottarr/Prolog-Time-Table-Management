"""Validation for the uploaded classroom-schedule CSV.

Column layout is fixed by the typst template in ``app/templates`` — see
``Backend/Gateway/app/templates/classroom-schedule.typ`` for how each
column is consumed. Room capacities come from the uploaded config
(``app.schedule_config``) and are passed in as ``capacities``.
"""

import csv
import io

from app.building import BUILDING, CLASS_HOURS, DAYS, PERIODS, ROOMS, period_of

EXPECTED_COLUMNS = ["room", "day", "start", "span", "title", "prof", "students"]
VALID_DAYS = set(DAYS)

PERIODS_TEXT = " or ".join(
    f"{name} {begin:02d}:00–{end:02d}:00" for name, (begin, end) in PERIODS.items()
)
STARTS_TEXT = " or ".join(f"{begin}" for begin, _ in PERIODS.values())


class CsvValidationError(ValueError):
    """Raised when the uploaded CSV does not match the expected schedule format."""


def _read_rows(raw: bytes) -> csv.DictReader:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvValidationError("CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or list(reader.fieldnames) != EXPECTED_COLUMNS:
        raise CsvValidationError(
            "CSV header must be exactly: " + ",".join(EXPECTED_COLUMNS)
        )
    return reader


def _check_room(room: str, line_no: int) -> None:
    if room not in ROOMS:
        raise CsvValidationError(
            f"Row {line_no}: room '{room}' isn't on the {BUILDING} 8th floor — "
            f"must be one of {', '.join(ROOMS)}."
        )


def _parse_students(value: str | None, line_no: int) -> int:
    try:
        students = int((value or "").strip())
    except ValueError:
        raise CsvValidationError(
            f"Row {line_no}: 'students' must be a whole number of students."
        )
    if students < 1:
        raise CsvValidationError(f"Row {line_no}: 'students' must be at least 1.")
    return students


def _check_capacity(room: str, students: int, capacities: dict[str, int], line_no: int) -> None:
    capacity = capacities[room]
    if capacity == 0:
        raise CsvValidationError(
            f"Row {line_no}: {room} isn't used for classes (capacity 0 in the config)."
        )
    if students > capacity:
        raise CsvValidationError(
            f"Row {line_no}: {students} students don't fit in {room} "
            f"(capacity {capacity})."
        )


def _check_room_free(
    booked: dict[tuple[str, str, str], int],
    room: str,
    day: str,
    period: str,
    line_no: int,
) -> None:
    """A room holds at most one class per period per day."""
    other = booked.get((room, day, period))
    if other is not None:
        raise CsvValidationError(
            f"Row {line_no}: {room} already has a {period} class on {day} "
            f"(row {other}) — one class per period."
        )
    booked[(room, day, period)] = line_no


def prof_key(prof: str) -> str:
    """Professor names compare case- and whitespace-insensitively."""
    return " ".join(prof.split()).casefold()


def _check_prof_free(
    teaching: dict[tuple[str, str, str], int],
    prof: str,
    day: str,
    period: str,
    line_no: int,
) -> None:
    """A professor teaches at most one class per period per day."""
    key = (prof_key(prof), day, period)
    other = teaching.get(key)
    if other is not None:
        raise CsvValidationError(
            f"Row {line_no}: {prof} already teaches a {period} class on {day} "
            f"(row {other}) — a professor can only teach one class at a time."
        )
    teaching[key] = line_no


def _check_span(span: int, line_no: int) -> None:
    if span != CLASS_HOURS:
        raise CsvValidationError(
            f"Row {line_no}: 'span' must be {CLASS_HOURS} — every class takes a "
            f"whole period ({PERIODS_TEXT}), got {span}."
        )


def _check_start(start: int, line_no: int) -> str:
    """Returns the period a 3-hour class starting at `start` fills."""
    period = period_of(start, CLASS_HOURS)
    if period is None:
        raise CsvValidationError(
            f"Row {line_no}: 'start' must be {STARTS_TEXT} — every class takes a "
            f"whole period ({PERIODS_TEXT}), got {start}."
        )
    return period


def validate_schedule_csv(raw: bytes, capacities: dict[str, int]) -> list[dict]:
    """Parse a *complete* schedule CSV, raising CsvValidationError if it isn't usable.

    Checks structure (header, day codes, integer columns), that every room
    is one of the building's rooms (see `app.building`), and the scheduling
    rules: each class is 3 hours and fills the morning (09:00) or
    afternoon (13:00) period,
    a room holds at most one class per period per day, a professor teaches
    at most one class per period per day, and a class's `students` never
    exceed its room's capacity (from the config). The same course may
    appear more than once (e.g. several sections — "Algorithms (Sec 2)").

    Returns one dict per row: room/day/title/prof/period strings,
    start/span/students ints.
    """
    reader = _read_rows(raw)

    classes = []
    booked: dict[tuple[str, str, str], int] = {}  # (room, day, period) -> line_no
    teaching: dict[tuple[str, str, str], int] = {}  # (prof, day, period) -> line_no
    for line_no, row in enumerate(reader, start=2):
        room = (row.get("room") or "").strip()
        title = (row.get("title") or "").strip()
        prof = (row.get("prof") or "").strip()
        if not room or not title or not prof:
            raise CsvValidationError(
                f"Row {line_no}: 'room', 'title' and 'prof' are required."
            )
        _check_room(room, line_no)

        day = row.get("day")
        if day not in VALID_DAYS:
            raise CsvValidationError(
                f"Row {line_no}: 'day' must be one of {sorted(VALID_DAYS)}, "
                f"got '{day}'."
            )

        numbers = {}
        for field in ("start", "span"):
            try:
                numbers[field] = int(row[field])
            except (KeyError, TypeError, ValueError):
                raise CsvValidationError(
                    f"Row {line_no}: '{field}' must be an integer."
                )
        start, span = numbers["start"], numbers["span"]
        _check_span(span, line_no)

        period = _check_start(start, line_no)

        _check_room_free(booked, room, day, period, line_no)
        _check_prof_free(teaching, prof, day, period, line_no)

        students = _parse_students(row.get("students"), line_no)
        _check_capacity(room, students, capacities, line_no)

        classes.append(
            {
                "room": room,
                "day": day,
                "start": start,
                "span": span,
                "period": period,
                "title": title,
                "prof": prof,
                "students": students,
            }
        )

    if not classes:
        raise CsvValidationError("CSV has no data rows.")

    return classes


def _normalize_optional(value: str | None) -> str | None:
    """Blank string or the literal (case-insensitive) "NULL" both mean unset."""
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "" or stripped.upper() == "NULL":
        return None
    return stripped


def parse_partial_schedule_csv(raw: bytes, capacities: dict[str, int]) -> list[dict]:
    """Parse a schedule CSV for auto-scheduling.

    Unlike `validate_schedule_csv`, `room`, `day`, and `start` may each be
    blank or the literal value "NULL" — meaning the professor is flexible
    on that dimension and Prolog should pick it. `span`, `title`, `prof`,
    and `students` are always required (`span` must be 3), since the
    class's length, identity and size are never something to be solved for.

    Whatever *is* given must already be satisfiable: a given start is
    9 or 13, a given room is big enough, and with no room given,
    at least one room in the building is big enough. When a row fixes
    both day and start, its professor must not already be teaching
    another fixed class in that period, and if it fixes the room too, that
    room must be free in that period (rows left flexible are Prolog's to
    keep apart).

    Returns one dict per row (room/day/start possibly None, span/students
    ints, title/prof strings) — this is the per-course shape consumed by
    `app.prolog_engine.generate_timetable`.
    """
    reader = _read_rows(raw)
    largest_capacity = max(capacities.values())

    courses = []
    teaching: dict[tuple[str, str, str], int] = {}  # (prof, day, period) -> line_no
    booked: dict[tuple[str, str, str], int] = {}  # (room, day, period) -> line_no
    for line_no, row in enumerate(reader, start=2):
        title = (row.get("title") or "").strip()
        prof = (row.get("prof") or "").strip()
        if not title or not prof:
            raise CsvValidationError(f"Row {line_no}: 'title' and 'prof' are required.")

        span_raw = (row.get("span") or "").strip()
        try:
            span = int(span_raw)
        except ValueError:
            raise CsvValidationError(
                f"Row {line_no}: 'span' must be an integer "
                "(it can't be blank, even with auto-scheduling)."
            )
        _check_span(span, line_no)

        students = _parse_students(row.get("students"), line_no)

        room = _normalize_optional(row.get("room"))
        if room is not None:
            _check_room(room, line_no)
            _check_capacity(room, students, capacities, line_no)
        elif students > largest_capacity:
            raise CsvValidationError(
                f"Row {line_no}: {students} students don't fit in any room "
                f"(largest capacity is {largest_capacity})."
            )

        day = _normalize_optional(row.get("day"))
        if day is not None and day not in VALID_DAYS:
            raise CsvValidationError(
                f"Row {line_no}: 'day' must be blank/NULL or one of "
                f"{sorted(VALID_DAYS)}, got '{day}'."
            )

        start_raw = _normalize_optional(row.get("start"))
        start = None
        if start_raw is not None:
            try:
                start = int(start_raw)
            except ValueError:
                raise CsvValidationError(
                    f"Row {line_no}: 'start' must be blank/NULL or an integer."
                )
            period = _check_start(start, line_no)
            if day is not None:
                _check_prof_free(teaching, prof, day, period, line_no)
                if room is not None:
                    _check_room_free(booked, room, day, period, line_no)

        courses.append(
            {
                "room": room,
                "day": day,
                "start": start,
                "span": span,
                "title": title,
                "prof": prof,
                "students": students,
            }
        )

    if not courses:
        raise CsvValidationError("CSV has no data rows.")

    return courses
