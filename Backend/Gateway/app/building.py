"""The building this project schedules for: the 8th floor of ECC.

Every room a schedule may use is listed here — the frontend's floor plan
(`Frontend/src/lib/ecc-8th-floor.svg`) has exactly one clickable shape per
entry, keyed by the room number (`room-801` <-> `ECC-801`). Room
capacities aren't fixed here: they come from the uploaded config file
(see `app.schedule_config`).
"""

BUILDING = "ECC"
FLOOR = 8

ROOMS = [f"{BUILDING}-{FLOOR}{n:02d}" for n in range(1, 11)]  # ECC-801 .. ECC-810

# Week order, Monday first: the auto-scheduler fills weekdays before the weekend.
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Each room/day has two bookable periods, and every class fills exactly one
# of them: 3 hours, starting 09:00 (morning) or 13:00 (afternoon). A room
# holds at most one class per period (so two per day). 12:00–13:00 between
# them is lunch.
PERIODS = {
    "morning": (9, 12),
    "afternoon": (13, 16),
}
CLASS_HOURS = 3


def period_of(start: int, span: int) -> str | None:
    """Name of the period a class at `start` for `span` hours fits in, else None."""
    for name, (begin, end) in PERIODS.items():
        if begin <= start and start + span <= end:
            return name
    return None
