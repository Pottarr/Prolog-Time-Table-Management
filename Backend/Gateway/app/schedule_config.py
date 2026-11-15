"""Validation for the uploaded schedule config (JSON).

The config is uploaded alongside the schedule CSV and carries everything
that isn't per-class: the semester, the academic year, and the seat
capacity of every room in the building. Example (`test/config.json`):

    {
      "semester": 1,
      "academic_year": 2026,
      "rooms": {"ECC-801": 40, ..., "ECC-810": 40}
    }

`rooms` must list exactly the building's rooms (`app.building.ROOMS`),
each with a positive integer capacity.
"""

import json

from app.building import BUILDING, ROOMS

VALID_SEMESTERS = (1, 2)
MIN_ACADEMIC_YEAR = 2000
MAX_ACADEMIC_YEAR = 2100


class ConfigValidationError(ValueError):
    """Raised when the uploaded config doesn't match the expected shape."""


def _is_int(value) -> bool:
    # bool is a subclass of int in Python; `true` isn't a valid year/capacity.
    return isinstance(value, int) and not isinstance(value, bool)


def parse_schedule_config(raw: bytes) -> dict:
    """Parse and validate the config, returning
    `{"semester": int, "academic_year": int, "capacities": {room: int}}`.
    """
    try:
        config = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigValidationError(f"Config must be a UTF-8 JSON file: {exc}") from exc

    if not isinstance(config, dict):
        raise ConfigValidationError("Config must be a JSON object.")

    semester = config.get("semester")
    if not _is_int(semester) or semester not in VALID_SEMESTERS:
        raise ConfigValidationError(
            f"Config 'semester' must be one of {VALID_SEMESTERS}, got {semester!r}."
        )

    academic_year = config.get("academic_year")
    if not _is_int(academic_year) or not (
        MIN_ACADEMIC_YEAR <= academic_year <= MAX_ACADEMIC_YEAR
    ):
        raise ConfigValidationError(
            f"Config 'academic_year' must be an integer between "
            f"{MIN_ACADEMIC_YEAR} and {MAX_ACADEMIC_YEAR}, got {academic_year!r}."
        )

    rooms = config.get("rooms")
    if not isinstance(rooms, dict):
        raise ConfigValidationError(
            "Config 'rooms' must be an object mapping room name to capacity."
        )

    unknown = sorted(set(rooms) - set(ROOMS))
    if unknown:
        raise ConfigValidationError(
            f"Config 'rooms' has rooms that aren't on the {BUILDING} 8th floor: "
            f"{', '.join(unknown)}."
        )
    missing = [room for room in ROOMS if room not in rooms]
    if missing:
        raise ConfigValidationError(
            f"Config 'rooms' is missing a capacity for: {', '.join(missing)}."
        )

    for room, capacity in rooms.items():
        if not _is_int(capacity) or capacity < 1:
            raise ConfigValidationError(
                f"Config capacity for {room} must be a positive integer, got {capacity!r}."
            )

    return {
        "semester": semester,
        "academic_year": academic_year,
        "capacities": {room: rooms[room] for room in ROOMS},
    }
