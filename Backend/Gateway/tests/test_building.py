"""The floor's fixed facts: room list, day order, and which period a class fits."""

import pytest

from app.building import BUILDING, CLASS_HOURS, DAYS, FLOOR, PERIODS, ROOMS, period_of


def test_ten_rooms_801_to_810():
    assert ROOMS == [f"ECC-8{n:02d}" for n in range(1, 11)]
    assert (BUILDING, FLOOR) == ("ECC", 8)


def test_days_start_on_monday():
    # The auto-scheduler relies on this order to fill weekdays first.
    assert DAYS == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def test_periods_are_three_hours_with_lunch_between():
    assert PERIODS == {"morning": (9, 12), "afternoon": (13, 16)}
    for begin, end in PERIODS.values():
        assert end - begin == CLASS_HOURS


@pytest.mark.parametrize(
    "start, span, period",
    [
        (9, 3, "morning"),
        (13, 3, "afternoon"),
        (10, 2, "morning"),  # fits inside the morning
        (14, 1, "afternoon"),
    ],
)
def test_period_of_fitting_class(start, span, period):
    assert period_of(start, span) == period


@pytest.mark.parametrize(
    "start, span",
    [
        (8, 3),   # starts before the morning
        (11, 3),  # runs into lunch
        (12, 1),  # is lunch
        (13, 4),  # runs past 16:00
        (16, 3),  # after the afternoon
        (9, 7),   # spans both periods
    ],
)
def test_period_of_class_outside_any_period(start, span):
    assert period_of(start, span) is None
