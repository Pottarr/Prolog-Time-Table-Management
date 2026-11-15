import json
from pathlib import Path

import pytest

TEST_DATA_DIR = Path(__file__).resolve().parents[3] / "test"

HEADER = "room,day,start,span,title,prof,students"

# Same capacities as test/config.json: 808/809 are the big 100-seat rooms,
# 805 the small 20-seat one, 806 (the co-working space) isn't used for
# classes, and every other room seats 50.
CAPACITIES = {
    "ECC-801": 50,
    "ECC-802": 50,
    "ECC-803": 50,
    "ECC-804": 50,
    "ECC-805": 20,
    "ECC-806": 0,
    "ECC-807": 50,
    "ECC-808": 100,
    "ECC-809": 100,
    "ECC-810": 50,
}


def make_csv(*rows: str) -> bytes:
    """A schedule CSV with the standard header and the given data rows."""
    return ("\n".join((HEADER, *rows)) + "\n").encode()


def make_config(**overrides) -> bytes:
    config = {"semester": 1, "academic_year": 2026, "rooms": dict(CAPACITIES)}
    config.update(overrides)
    return json.dumps(config).encode()


@pytest.fixture
def capacities() -> dict[str, int]:
    return dict(CAPACITIES)
