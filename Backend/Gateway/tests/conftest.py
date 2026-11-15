import json
from pathlib import Path

import pytest

TEST_DATA_DIR = Path(__file__).resolve().parents[3] / "test"

HEADER = "room,day,start,span,title,prof,students"

# Same capacities as test/config.json: 808/809 are the 120-seat rooms,
# 805 is the smallest at 30.
CAPACITIES = {
    "ECC-801": 40,
    "ECC-802": 40,
    "ECC-803": 40,
    "ECC-804": 40,
    "ECC-805": 30,
    "ECC-806": 60,
    "ECC-807": 60,
    "ECC-808": 120,
    "ECC-809": 120,
    "ECC-810": 40,
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
