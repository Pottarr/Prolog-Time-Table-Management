import json

import pytest

from app.schedule_config import ConfigValidationError, parse_schedule_config
from tests.conftest import CAPACITIES, TEST_DATA_DIR, make_config


def test_sample_config_is_valid():
    config = parse_schedule_config((TEST_DATA_DIR / "config.json").read_bytes())
    assert config["semester"] == 1
    assert config["academic_year"] == 2026
    assert config["capacities"]["ECC-808"] == 100
    assert config["capacities"]["ECC-806"] == 0  # co-working space


def test_capacities_come_back_in_room_order():
    shuffled = dict(reversed(list(CAPACITIES.items())))
    config = parse_schedule_config(make_config(rooms=shuffled))
    assert list(config["capacities"]) == list(CAPACITIES)


def test_utf8_bom_is_accepted():
    parse_schedule_config(b"\xef\xbb\xbf" + make_config())


@pytest.mark.parametrize("semester", [0, 3, "1", None, True])
def test_bad_semester(semester):
    with pytest.raises(ConfigValidationError, match="semester"):
        parse_schedule_config(make_config(semester=semester))


@pytest.mark.parametrize("year", [1999, 2101, "2026", 2026.0, None])
def test_bad_academic_year(year):
    with pytest.raises(ConfigValidationError, match="academic_year"):
        parse_schedule_config(make_config(academic_year=year))


@pytest.mark.parametrize("year", [2000, 2100])
def test_academic_year_bounds_are_inclusive(year):
    parse_schedule_config(make_config(academic_year=year))


def test_missing_room():
    rooms = dict(CAPACITIES)
    del rooms["ECC-807"]
    with pytest.raises(ConfigValidationError, match="missing a capacity for: ECC-807"):
        parse_schedule_config(make_config(rooms=rooms))


def test_room_not_on_the_floor():
    rooms = {**CAPACITIES, "ECC-502": 40}
    with pytest.raises(ConfigValidationError, match="ECC-502"):
        parse_schedule_config(make_config(rooms=rooms))


def test_capacity_zero_marks_a_room_not_used_for_classes():
    config = parse_schedule_config(make_config(rooms={**CAPACITIES, "ECC-801": 0}))
    assert config["capacities"]["ECC-801"] == 0


@pytest.mark.parametrize("capacity", [-5, 40.5, "40", None, True])
def test_bad_capacity(capacity):
    rooms = {**CAPACITIES, "ECC-801": capacity}
    with pytest.raises(ConfigValidationError, match="ECC-801"):
        parse_schedule_config(make_config(rooms=rooms))


@pytest.mark.parametrize("rooms", [None, [], [["ECC-801", 40]]])
def test_rooms_must_be_an_object(rooms):
    with pytest.raises(ConfigValidationError, match="rooms"):
        parse_schedule_config(make_config(rooms=rooms))


@pytest.mark.parametrize(
    "raw",
    [b"", b"not json", b"[1, 2]", json.dumps("text").encode(), b"\xff\xfe"],
)
def test_not_a_json_object(raw):
    with pytest.raises(ConfigValidationError):
        parse_schedule_config(raw)
