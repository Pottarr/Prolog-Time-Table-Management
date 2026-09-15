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
