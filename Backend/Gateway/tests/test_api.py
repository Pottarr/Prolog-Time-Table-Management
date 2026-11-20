"""End-to-end tests of the HTTP routes (FastAPI TestClient).

`/api/schedule/pdf` shells out to the real `typst` CLI, so those tests are
skipped when it isn't installed.
"""

import random
import re
import shutil

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import CAPACITIES, TEST_DATA_DIR, make_config, make_csv

client = TestClient(app)

needs_typst = pytest.mark.skipif(shutil.which("typst") is None, reason="typst not installed")


def post(endpoint, csv_bytes, config_bytes):
    return client.post(
        f"/api/schedule/{endpoint}",
        files={
            "csv_file": ("schedule.csv", csv_bytes, "text/csv"),
            "config_file": ("config.json", config_bytes, "application/json"),
        },
    )


def sample(name):
    return (TEST_DATA_DIR / name).read_bytes()


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


# ------------------------------------------------------------------ parse


def test_parse_sample():
    response = post("parse", sample("schedule-complete.csv"), sample("config.json"))
    assert response.status_code == 200
    body = response.json()
    assert body["building"] == "ECC"
    assert body["floor"] == 8
    assert body["rooms"] == list(CAPACITIES)
    assert body["capacities"] == CAPACITIES
    assert body["periods"] == {"morning": [9, 12], "afternoon": [13, 16]}
    assert (body["semester"], body["academic_year"]) == (1, 2026)
    assert len(body["classes"]) == 9


def test_parse_semester_and_year_come_from_config():
    response = post(
        "parse",
        make_csv("ECC-804,Mon,9,3,A,Dr. X,10"),
        make_config(semester=2, academic_year=2027),
    )
    assert (response.json()["semester"], response.json()["academic_year"]) == (2, 2027)


def test_parse_rejects_bad_csv_with_422():
    response = post("parse", make_csv("ECC-804,Mon,9,3,A,Dr. X,51"), make_config())
    assert response.status_code == 422
    assert response.json()["detail"] == "Row 2: 51 students don't fit in ECC-804 (capacity 50)."


def test_parse_rejects_bad_config_with_422():
    response = post("parse", make_csv("ECC-804,Mon,9,3,A,Dr. X,10"), make_config(semester=3))
    assert response.status_code == 422
    assert "semester" in response.json()["detail"]


def test_config_is_checked_before_csv():
    response = post("parse", b"garbage", b"garbage")
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Config")


@pytest.mark.parametrize("missing", ["csv_file", "config_file"])
def test_both_files_are_required(missing):
    files = {
        "csv_file": ("schedule.csv", make_csv("ECC-804,Mon,9,3,A,Dr. X,10"), "text/csv"),
        "config_file": ("config.json", make_config(), "application/json"),
    }
    del files[missing]
    assert client.post("/api/schedule/parse", files=files).status_code == 422


def test_old_semester_form_fields_alone_are_not_enough():
    response = client.post(
        "/api/schedule/parse",
        data={"semester": "1", "academic_year": "2026"},
        files={"csv_file": ("schedule.csv", make_csv("ECC-804,Mon,9,3,A,Dr. X,10"), "text/csv")},
    )
    assert response.status_code == 422


# -------------------------------------------------------------------- pdf


@needs_typst
def test_pdf_sample():
    response = post("pdf", sample("schedule-complete.csv"), sample("config.json"))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert 'filename="classroom-schedule-2026-s1.pdf"' in response.headers["content-disposition"]


@needs_typst
def test_pdf_has_a_page_for_every_classroom_even_empty_ones():
    # One class in 801 only; every room with seats still gets a door sheet,
    # but the co-working space (806, capacity 0) doesn't.
    response = post("pdf", make_csv("ECC-801,Mon,9,3,A,Dr. X,10"), make_config())
    assert response.status_code == 200, response.text
    pages = re.findall(rb"/Type\s*/Page(?![s\w])", response.content)
    assert len(pages) == sum(1 for seats in CAPACITIES.values() if seats > 0)


@needs_typst
def test_pdf_weekend_and_thai_text_render():
    csv_bytes = make_csv(
        "ECC-801,Sun,9,3,วิศวกรรมซอฟต์แวร์ (Section 1),อ. วีระ,40",
        "ECC-801,Sat,13,3,\"Algorithms (Sec 2, English)\",Dr. Y,40",
    )
    response = post("pdf", csv_bytes, make_config())
    assert response.status_code == 200, response.text


def test_pdf_rejects_invalid_schedule_before_rendering():
    response = post(
        "pdf",
        make_csv("ECC-801,Mon,9,3,A,Dr. X,10", "ECC-802,Mon,9,3,B,Dr. X,10"),
        make_config(),
    )
    assert response.status_code == 422
    assert "one class at a time" in response.json()["detail"]


# ------------------------------------------------------------------- auto


def test_auto_sample_fills_every_blank():
    response = post("auto", sample("schedule-incomplete.csv"), sample("config.json"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["capacities"] == CAPACITIES
    assert (body["semester"], body["academic_year"]) == (1, 2026)

    classes = body["classes"]
    assert [c["title"] for c in classes] == [
        "Algorithms", "Databases", "Compiler Design", "Operating Systems",
    ]
    assert all(c["room"] and c["day"] and c["start"] for c in classes)

    algorithms, databases, compiler, os_course = classes
    assert algorithms["start"] == 13  # fixed start kept
    assert (databases["room"], databases["day"]) == ("ECC-804", "Mon")  # fixed room/day kept
    assert compiler["day"] == "Fri"
    assert compiler["room"] in ("ECC-808", "ECC-809")  # 100 students: only the big rooms fit
    assert os_course["room"] == "ECC-803"
    assert algorithms["room"] == "ECC-801"  # 35 students: the first 50-seat room


def test_auto_csv_round_trips_through_parse_and_pdf():
    body = post("auto", sample("schedule-incomplete.csv"), sample("config.json")).json()
    reparsed = post("parse", body["csv"].encode(), sample("config.json"))
    assert reparsed.status_code == 200
    assert reparsed.json()["classes"] == body["classes"]


@needs_typst
def test_auto_csv_renders_to_pdf():
    body = post("auto", sample("schedule-incomplete.csv"), sample("config.json")).json()
    response = post("pdf", body["csv"].encode(), sample("config.json"))
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_auto_prefers_the_smallest_room_that_fits():
    body = post("auto", make_csv("NULL,NULL,NULL,3,Small seminar,Dr. X,15"), make_config()).json()
    assert body["classes"][0]["room"] == "ECC-805"  # 20 seats, the smallest


def test_auto_keeps_a_flexible_professor_out_of_their_fixed_period():
    body = post(
        "auto",
        make_csv("ECC-801,Mon,9,3,Fixed,Dr. X,10", "NULL,Mon,NULL,3,Flexible,Dr. X,10"),
        make_config(),
    ).json()
    flexible = body["classes"][1]
    assert (flexible["day"], flexible["period"]) == ("Mon", "afternoon")


def test_auto_fills_the_floor_exactly():
    # 9 class rooms (806 has capacity 0) x 7 days x 2 periods = 126 slots.
    rows = [f"NULL,NULL,NULL,3,Class {i},Dr. {i},10" for i in range(126)]
    body = post("auto", make_csv(*rows), make_config()).json()
    slots = {(c["room"], c["day"], c["period"]) for c in body["classes"]}
    assert len(slots) == 126
    assert "ECC-806" not in {room for room, _, _ in slots}


def test_auto_unsatisfiable_when_floor_is_over_full():
    rows = [f"NULL,NULL,NULL,3,Class {i},Dr. {i},10" for i in range(127)]
    response = post("auto", make_csv(*rows), make_config())
    assert response.status_code == 422
    assert "No timetable satisfies every rule" in response.json()["detail"]


def test_auto_unsatisfiable_when_big_rooms_run_out():
    # Only 808/809 hold 100 students: 2 rooms x 14 periods = 28 slots.
    rows = [f"NULL,NULL,NULL,3,Lecture {i},Dr. {i},100" for i in range(29)]
    response = post("auto", make_csv(*rows), make_config())
    assert response.status_code == 422


def test_auto_unsatisfiable_when_professor_is_overbooked():
    # One professor has 14 periods a week.
    rows = [f"NULL,NULL,NULL,3,Class {i},Dr. Busy,10" for i in range(15)]
    response = post("auto", make_csv(*rows), make_config())
    assert response.status_code == 422


def test_auto_rejects_invalid_partial_csv_with_422():
    response = post("auto", make_csv("NULL,NULL,NULL,3,A,Dr. X,500"), make_config())
    assert response.status_code == 422
    assert "don't fit in any room" in response.json()["detail"]


@pytest.mark.parametrize("seed", range(10))
def test_auto_random_mixes_never_time_out_and_keep_fixed_values(seed):
    """Random partial CSVs: Prolog must either solve them (keeping every
    fixed room/day/start) or prove them impossible — never time out."""
    rng = random.Random(seed)
    rooms = list(CAPACITIES)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    rows = []
    for i in range(rng.randint(40, 120)):
        students = rng.choice([10, 15, 20, 35, 50, 80, 100])
        fits = [r for r in rooms if CAPACITIES[r] >= students]
        room = rng.choice(fits) if rng.random() < 0.2 else "NULL"
        day = rng.choice(days) if rng.random() < 0.25 else "NULL"
        start = rng.choice([9, 13]) if rng.random() < 0.25 else "NULL"
        rows.append(f"{room},{day},{start},3,C{i},Dr. {rng.randrange(25)},{students}")

    response = post("auto", make_csv(*rows), make_config())
    if response.status_code == 422:
        assert "within" not in response.json()["detail"]  # proven, not timed out
        return
    assert response.status_code == 200, response.text
    for row, placed in zip(rows, response.json()["classes"]):
        room, day, start = row.split(",")[:3]
        assert room == "NULL" or placed["room"] == room
        assert day == "NULL" or placed["day"] == day
        assert start == "NULL" or placed["start"] == int(start)
