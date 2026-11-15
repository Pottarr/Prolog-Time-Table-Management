"""Runs every hand-test file in `test/cases/` through the API and checks
the outcome documented for it in `test/cases/README.md`.

Keep the two in sync: adding a file there means adding a row here.
"""

import pytest

from tests.conftest import TEST_DATA_DIR
from tests.test_api import post

CASES_DIR = TEST_DATA_DIR / "cases"
DEFAULT_CONFIG = TEST_DATA_DIR / "config.json"

# (csv file, config file or None for test/config.json, endpoint, status, expected text)
CASES = [
    ("01-valid-full-week.csv", None, "parse", 200, None),
    ("02-valid-boundaries.csv", None, "parse", 200, None),
    ("03-over-capacity.csv", None, "parse", 422, "41 students don't fit in ECC-804 (capacity 40)"),
    ("04-100-students-small-room.csv", None, "parse", 422, "100 students don't fit in ECC-806 (capacity 60)"),
    ("05-room-not-on-floor.csv", None, "parse", 422, "room 'ECC-502' isn't on the ECC 8th floor"),
    ("06-past-afternoon.csv", None, "parse", 422, "doesn't fit inside one period"),
    ("07-into-lunch.csv", None, "parse", 422, "doesn't fit inside one period"),
    ("08-span-too-long.csv", None, "parse", 422, "'span' must be 1–3 hours"),
    ("09-two-classes-one-period.csv", None, "parse", 422, "ECC-804 already has a morning class on Mon"),
    ("10-professor-clash.csv", None, "parse", 422, "a professor can only teach one class at a time"),
    ("11-bad-day.csv", None, "parse", 422, "'day' must be one of"),
    ("12-missing-students.csv", None, "parse", 422, "'students' must be a whole number"),
    ("13-old-six-columns.csv", None, "parse", 422, "CSV header must be exactly"),
    ("14-auto-valid.csv", None, "auto", 200, None),
    ("15-auto-too-big-for-any-room.csv", None, "auto", 422, "don't fit in any room (largest capacity is 120)"),
    ("16-auto-fixed-clash.csv", None, "auto", 422, "a professor can only teach one class at a time"),
    ("01-valid-full-week.csv", "config-semester-3.json", "parse", 422, "Config 'semester' must be one of"),
    ("01-valid-full-week.csv", "config-missing-room.json", "parse", 422, "missing a capacity for: ECC-810"),
    ("17-uses-big-801.csv", None, "parse", 422, "150 students don't fit in ECC-801 (capacity 40)"),
    ("17-uses-big-801.csv", "config-big-801.json", "parse", 200, None),
]


@pytest.mark.parametrize(
    "csv_name,config_name,endpoint,status,expected",
    CASES,
    ids=[f"{c[0]}+{c[1] or 'config.json'}" for c in CASES],
)
def test_case_file(csv_name, config_name, endpoint, status, expected):
    config_path = CASES_DIR / config_name if config_name else DEFAULT_CONFIG
    response = post(endpoint, (CASES_DIR / csv_name).read_bytes(), config_path.read_bytes())
    assert response.status_code == status, response.text
    if expected is not None:
        assert expected in response.json()["detail"]


def test_every_case_file_is_covered():
    used = {c[0] for c in CASES} | {c[1] for c in CASES if c[1]}
    on_disk = {p.name for p in CASES_DIR.iterdir() if p.suffix in (".csv", ".json")}
    assert on_disk == used
