"""Runs every hand-test file in `test/cases/` through the API and checks
the outcome documented for it in `test/cases/README.md`.

Keep the two in sync: adding a file there means adding a row here.
"""

import shutil
from collections import Counter

import pytest

from tests.conftest import TEST_DATA_DIR
from tests.test_api import client, post

CASES_DIR = TEST_DATA_DIR / "cases"
DEFAULT_CONFIG = TEST_DATA_DIR / "config.json"
needs_swipl = pytest.mark.skipif(shutil.which("swipl") is None, reason="swipl not installed")

# (csv file, config file or None for test/config.json, endpoint, status, expected text)
CASES = [
    ("01-valid-full-week.csv", None, "parse", 200, None),
    ("02-valid-boundaries.csv", None, "parse", 200, None),
    ("03-over-capacity.csv", None, "parse", 422, "51 students don't fit in ECC-804 (capacity 50)"),
    ("04-100-students-small-room.csv", None, "parse", 422, "100 students don't fit in ECC-807 (capacity 50)"),
    ("05-room-not-on-floor.csv", None, "parse", 422, "room 'ECC-502' isn't on the ECC 8th floor"),
    ("06-past-afternoon.csv", None, "parse", 422, "'start' must be 9 or 13"),
    ("07-into-lunch.csv", None, "parse", 422, "'start' must be 9 or 13"),
    ("08-span-too-long.csv", None, "parse", 422, "'span' must be 3"),
    ("09-two-classes-one-period.csv", None, "parse", 422, "ECC-804 already has a morning class on Mon"),
    ("10-professor-clash.csv", None, "parse", 422, "a professor can only teach one class at a time"),
    ("11-bad-day.csv", None, "parse", 422, "'day' must be one of"),
    ("12-missing-students.csv", None, "parse", 422, "'students' must be a whole number"),
    ("13-old-six-columns.csv", None, "parse", 422, "CSV header must be exactly"),
    ("14-auto-valid.csv", None, "auto", 200, None),
    ("15-auto-too-big-for-any-room.csv", None, "auto", 422, "don't fit in any room (largest capacity is 100)"),
    ("16-auto-fixed-clash.csv", None, "auto", 422, "a professor can only teach one class at a time"),
    ("01-valid-full-week.csv", "config-semester-3.json", "parse", 422, "Config 'semester' must be one of"),
    ("01-valid-full-week.csv", "config-missing-room.json", "parse", 422, "missing a capacity for: ECC-810"),
    ("17-uses-big-801.csv", None, "parse", 422, "150 students don't fit in ECC-801 (capacity 50)"),
    ("17-uses-big-801.csv", "config-big-801.json", "parse", 200, None),
    ("18-coworking-806.csv", None, "parse", 422, "ECC-806 isn't used for classes"),
    ("19-auto-skips-806.csv", None, "auto", 200, None),
    ("20-short-class.csv", None, "parse", 422, "'span' must be 3"),
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


# Several cases (/api/schedule/cases): csv, config (None = test/config.json),
# cap, and the expected {moved classes: number of cases}.
MULTI_CASES = [
    ("21-cases-several-ok.csv", None, 10, {0: 10}),
    ("22-cases-room-clash.csv", None, 10, {1: 10}),
    ("23-cases-prof-clash.csv", None, 10, {1: 10}),
    ("24-cases-error-levels.csv", None, 10, {1: 10}),
    ("25-cases-mixed-errors.csv", None, 10, {2: 10}),
    ("26-cases-percent-levels.csv", "config-one-room.json", 30, {1: 2, 2: 24, 3: 4}),
]


@needs_swipl
@pytest.mark.parametrize("csv_name,config_name,cap,levels", MULTI_CASES, ids=[c[0] for c in MULTI_CASES])
def test_multi_case_file(csv_name, config_name, cap, levels):
    config_path = CASES_DIR / config_name if config_name else DEFAULT_CONFIG
    response = client.post(
        "/api/schedule/cases",
        files={
            "csv_file": ("s.csv", (CASES_DIR / csv_name).read_bytes(), "text/csv"),
            "config_file": ("c.json", config_path.read_bytes(), "application/json"),
        },
        data={"max_cases": str(cap)},
    )
    assert response.status_code == 200, response.text
    cases = response.json()["cases"]
    assert dict(Counter(c["errors"] for c in cases)) == levels
    assert [c["errors"] for c in cases] == sorted(c["errors"] for c in cases)


def test_every_case_file_is_covered():
    used = {c[0] for c in CASES} | {c[1] for c in CASES if c[1]} | {c[0] for c in MULTI_CASES} | {c[1] for c in MULTI_CASES if c[1]}
    on_disk = {p.name for p in CASES_DIR.iterdir() if p.suffix in (".csv", ".json")}
    assert on_disk == used
