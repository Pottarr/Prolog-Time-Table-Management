"""Validation for the uploaded classroom-schedule CSV.

Column layout is fixed by the typst template in ``app/templates`` — see
``Backend/Gateway/app/templates/classroom-schedule.typ`` for how each
column is consumed.
"""

import csv
import io

EXPECTED_COLUMNS = ["room", "day", "start", "span", "title", "prof"]
VALID_DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}


class CsvValidationError(ValueError):
    """Raised when the uploaded CSV does not match the expected schedule format."""


def validate_schedule_csv(raw: bytes) -> None:
    """Raise CsvValidationError if `raw` isn't a usable schedule CSV.

    This only checks structure (header, day codes, integer columns) —
    the typst template itself still enforces the scheduling invariants
    (no overlapping classes, lunch block reserved, etc).
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvValidationError("CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or list(reader.fieldnames) != EXPECTED_COLUMNS:
        raise CsvValidationError(
            "CSV header must be exactly: " + ",".join(EXPECTED_COLUMNS)
        )

    row_count = 0
    for line_no, row in enumerate(reader, start=2):
        row_count += 1

        if not row.get("room") or not row.get("title"):
            raise CsvValidationError(f"Row {line_no}: 'room' and 'title' are required.")

        if row.get("day") not in VALID_DAYS:
            raise CsvValidationError(
                f"Row {line_no}: 'day' must be one of {sorted(VALID_DAYS)}, "
                f"got '{row.get('day')}'."
            )

        for field in ("start", "span"):
            try:
                int(row[field])
            except (KeyError, TypeError, ValueError):
                raise CsvValidationError(
                    f"Row {line_no}: '{field}' must be an integer."
                )

    if row_count == 0:
        raise CsvValidationError("CSV has no data rows.")


def _normalize_optional(value: str | None) -> str | None:
    """Blank string or the literal (case-insensitive) "NULL" both mean unset."""
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "" or stripped.upper() == "NULL":
        return None
    return stripped


def parse_partial_schedule_csv(raw: bytes) -> list[dict]:
    """Parse a schedule CSV for auto-scheduling.

    Unlike `validate_schedule_csv`, `room`, `day`, and `start` may each be
    blank or the literal value "NULL" — meaning the professor is flexible
    on that dimension and Prolog should pick it. `span`, `title`, and
    `prof` are always required, since the class's length and identity are
    never something to be solved for.

    Returns one dict per row (room/day/start possibly None, span an int,
    title/prof strings) — this is the per-course shape consumed by
    `app.prolog_client.build_prolog_request`.
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvValidationError("CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or list(reader.fieldnames) != EXPECTED_COLUMNS:
        raise CsvValidationError(
            "CSV header must be exactly: " + ",".join(EXPECTED_COLUMNS)
        )

    courses = []
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

        room = _normalize_optional(row.get("room"))

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

        courses.append(
            {
                "room": room,
                "day": day,
                "start": start,
                "span": span,
                "title": title,
                "prof": prof,
            }
        )

    if not courses:
        raise CsvValidationError("CSV has no data rows.")

    return courses
