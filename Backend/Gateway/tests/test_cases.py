"""Multi-case scheduling, the CSV editor endpoints, and their helpers.

The real-scheduler tests run `swipl` (skipped without it); the contract
tests fake its output.
"""

import shutil

import pytest
from fastapi.testclient import TestClient

from app import prolog_engine
from app.cases import apply_professor_preference, rank_cases, unsatisfied_classes
from app.csv_validation import (
    CsvValidationError,
    parse_partial_schedule_csv,
    read_editable_rows,
    rows_to_csv,
    validate_schedule_csv,
)
from app.main import app
from tests.conftest import CAPACITIES, make_config, make_csv

client = TestClient(app)
needs_swipl = pytest.mark.skipif(shutil.which("swipl") is None, reason="swipl not installed")

# Two classes asking for ECC-804 Monday morning, and Dr. X asked twice
# for Monday morning.
CLASHING = make_csv(
    "ECC-804,Mon,9,3,A,Dr. X,10",
    "ECC-804,Mon,9,3,B,Dr. Y,10",
    "ECC-801,Mon,9,3,C,dr.  x,10",
    "ECC-802,Tue,13,3,D,Dr. Z,10",
)


def post_cases(csv_bytes, max_cases=None, config=None):
    data = {} if max_cases is None else {"max_cases": str(max_cases)}
    return client.post(
        "/api/schedule/cases",
        files={
            "csv_file": ("s.csv", csv_bytes, "text/csv"),
            "config_file": ("c.json", config or make_config(), "application/json"),
        },
        data=data,
    )


# ------------------------------------------------------------ validation


def test_clashing_requests_rejected_by_default():
    with pytest.raises(CsvValidationError, match="one class per period"):
        validate_schedule_csv(CLASHING, CAPACITIES)
    with pytest.raises(CsvValidationError):
        parse_partial_schedule_csv(CLASHING, CAPACITIES)


def test_clashing_requests_allowed_for_cases():
    assert len(parse_partial_schedule_csv(CLASHING, CAPACITIES, allow_clashes=True)) == 4


def test_lenient_parse_still_rejects_capacity():
    with pytest.raises(CsvValidationError, match="don't fit"):
        parse_partial_schedule_csv(make_csv("ECC-805,Mon,9,3,A,Dr. X,21"), CAPACITIES, allow_clashes=True)


# ------------------------------------------------------------ moved classes


def _courses(*rows):
    return parse_partial_schedule_csv(make_csv(*rows), CAPACITIES, allow_clashes=True)


def _classes(*rows):
    return validate_schedule_csv(make_csv(*rows), CAPACITIES)


def test_unsatisfied_classes_lists_what_was_asked_and_got():
    courses = _courses("ECC-804,Mon,9,3,A,Dr. X,10", "NULL,NULL,13,3,B,Dr. Y,10", "NULL,NULL,NULL,3,C,Dr. Z,10")
    classes = _classes("ECC-801,Mon,13,3,A,Dr. X,10", "ECC-802,Tue,13,3,B,Dr. Y,10", "ECC-803,Wed,9,3,C,Dr. Z,10")
    [moved] = unsatisfied_classes(courses, classes)
    assert moved["row"] == 0
    assert moved["missed"] == ["room", "start"]
    assert moved["message"] == "A (Dr. X): asked Mon morning ECC-804, got Mon afternoon ECC-801"


def test_rank_cases_orders_by_moved_classes_then_prolog_order():
    courses = _courses("ECC-804,Mon,9,3,A,Dr. X,10", "ECC-804,Mon,9,3,B,Dr. Y,10")
    def case(*rows):
        return {"score": None, "classes": _classes(*rows), "csv": ""}

    one_a = case("ECC-804,Mon,9,3,A,Dr. X,10", "ECC-801,Mon,9,3,B,Dr. Y,10")
    two = case("ECC-801,Tue,9,3,A,Dr. X,10", "ECC-802,Tue,9,3,B,Dr. Y,10")
    one_b = case("ECC-802,Mon,9,3,A,Dr. X,10", "ECC-804,Mon,9,3,B,Dr. Y,10")
    ranked = rank_cases([two, one_a, one_b], courses)
    assert [(c["rank"], c["errors"], c["score"], c["status"]) for c in ranked] == [
        (1, 1, 50, "unsatisfied"),
        (2, 1, 50, "unsatisfied"),
        (3, 2, 0, "unsatisfied"),
    ]
    assert ranked[0]["classes"][1]["room"] == "ECC-801"  # Prolog's order within a level


def test_rank_cases_ok_and_duplicates():
    courses = _courses("NULL,NULL,NULL,3,A,Dr. X,10")
    a = {"score": None, "classes": _classes("ECC-804,Mon,9,3,A,Dr. X,10"), "csv": ""}
    [case] = rank_cases([a, dict(a)], courses)
    assert (case["status"], case["errors"], case["score"], case["unsatisfied"]) == ("ok", 0, 100, [])


# ------------------------------------------------------------ editor


def test_read_and_write_rows_round_trip():
    raw = make_csv('NULL,,13,3,"Algo, Sec 2",Dr. Veera,35', "ECC-804,Mon,9,3,DB,Dr. S,40")
    rows = read_editable_rows(raw)
    assert rows[0] == {
        "room": None,
        "day": None,
        "start": "13",
        "span": "3",
        "title": "Algo, Sec 2",
        "prof": "Dr. Veera",
        "students": "35",
    }
    text = rows_to_csv(rows)
    assert text.splitlines()[1] == 'NULL,NULL,13,3,"Algo, Sec 2",Dr. Veera,35'
    assert read_editable_rows(text.encode()) == rows


def test_read_rows_checks_header_only():
    with pytest.raises(CsvValidationError, match="header"):
        read_editable_rows(b"a,b\n1,2\n")
    assert read_editable_rows(make_csv("ECC-999,Funday,7,9,X,Y,zero"))[0]["day"] == "Funday"


def test_professor_preference_rewrites_only_that_prof():
    rows = read_editable_rows(
        make_csv("ECC-804,Mon,9,3,A,Dr. X,10", "NULL,NULL,NULL,3,B,dr.  x,10", "ECC-801,Tue,9,3,C,Dr. Y,10")
    )
    out = apply_professor_preference(rows, "Dr. X", "Fri", "afternoon")
    assert [(r["day"], r["start"], r["room"]) for r in out] == [
        ("Fri", "13", "ECC-804"),
        ("Fri", "13", None),
        ("Tue", "9", "ECC-801"),
    ]
    out = apply_professor_preference(out, "Dr. X", "any", "keep")
    assert [(r["day"], r["start"]) for r in out[:2]] == [(None, "13"), (None, "13")]
    assert rows[0]["day"] == "Mon"  # input untouched


def test_professor_preference_rejects_bad_values():
    with pytest.raises(ValueError):
        apply_professor_preference([], "X", "Funday", "keep")
    with pytest.raises(ValueError):
        apply_professor_preference([], "X", "keep", "evening")


def test_csv_rows_endpoint():
    response = client.post("/api/csv/rows", files={"csv_file": ("s.csv", CLASHING, "text/csv")})
    assert response.status_code == 200
    assert len(response.json()["rows"]) == 4


def test_professor_preference_endpoint():
    rows = read_editable_rows(CLASHING)
    response = client.post(
        "/api/csv/professor-preference",
        json={"rows": rows, "prof": "Dr. X", "day": "Wed", "period": "keep"},
    )
    assert response.status_code == 200
    body = response.json()
    assert [r["day"] for r in body["rows"]] == ["Wed", "Mon", "Wed", "Tue"]
    assert body["csv"].splitlines()[1] == "ECC-804,Wed,9,3,A,Dr. X,10"

    bad = client.post("/api/csv/professor-preference", json={"rows": rows, "prof": "X", "day": "Funday"})
    assert bad.status_code == 422


# ------------------------------------------------------------ contract


def _fake_cases(monkeypatch, output):
    seen = {}

    def fake_run(goal, request, timeout=prolog_engine.PROCESS_TIMEOUT_SECONDS):
        seen["goal"], seen["request"], seen["timeout"] = goal, request, timeout
        return output

    monkeypatch.setattr(prolog_engine, "scheduler_supports_cases", lambda: True)
    monkeypatch.setattr(prolog_engine, "_run", fake_run)
    return seen


def test_cases_still_rejects_capacity():
    assert post_cases(make_csv("ECC-805,Mon,9,3,A,Dr. X,21")).status_code == 422


@pytest.mark.parametrize("max_cases", [0, -5])
def test_zero_or_less_means_no_cap_and_no_time_limit(monkeypatch, max_cases):
    seen = _fake_cases(monkeypatch, "case -1 2 0 0\n" * 3)
    response = post_cases(make_csv("NULL,NULL,NULL,3,A,Dr. X,10"), max_cases)
    assert response.status_code == 200, response.json()
    assert seen["request"].rstrip().endswith(", 0, 0).")
    assert seen["timeout"] is None
    assert response.json()["max_cases"] == 0


def test_cap_has_a_time_limit(monkeypatch):
    seen = _fake_cases(monkeypatch, "case -1 2 0 0\n")
    post_cases(make_csv("NULL,NULL,NULL,3,A,Dr. X,10"), 250)
    assert seen["request"].rstrip().endswith(", 10, 250).")
    assert seen["timeout"] is not None


def test_partial_answer_after_time_limit(monkeypatch):
    _fake_cases(monkeypatch, "case -1 2 0 0\ncase -1 3 0 0\ntimeout\n")
    body = post_cases(make_csv("NULL,NULL,NULL,3,A,Dr. X,10"), 5).json()
    assert body["complete"] is False
    assert len(body["cases"]) == 2


def test_contract_ranks_and_moves_start_with_period(monkeypatch):
    # Rooms are indexed smallest first: 806 (0), 805 (1), 801 (2), 802 (3), ...
    _fake_cases(
        monkeypatch,
        "case -1 2 0 1 3 0 1\n"  # A moved from Mon morning to Mon afternoon
        "case -1 2 0 0 3 0 1\n",  # both as asked
    )
    response = post_cases(make_csv("ECC-801,Mon,9,3,A,Dr. X,10", "NULL,NULL,13,3,B,Dr. Y,10"), 5)
    assert response.status_code == 200, response.json()
    cases = response.json()["cases"]
    assert [(c["rank"], c["status"], c["errors"], c["score"]) for c in cases] == [
        (1, "ok", 0, 100),
        (2, "unsatisfied", 1, 50),
    ]
    moved = cases[1]["classes"][0]
    assert (moved["period"], moved["start"]) == ("afternoon", 13)
    assert cases[1]["unsatisfied"][0]["missed"] == ["start"]


def test_contract_rejects_double_booking(monkeypatch):
    _fake_cases(monkeypatch, "case -1 2 0 0 2 0 0\n")  # both in 801 Mon morning
    response = post_cases(make_csv("NULL,NULL,NULL,3,A,Dr. X,10", "NULL,NULL,NULL,3,B,Dr. Y,10"))
    assert response.status_code == 500


@pytest.mark.parametrize(
    "output, status",
    [("unsatisfiable\n", 422), ("timeout\n", 422), ("case 50 0\n", 500), ("case x 2 0 0\n", 500), ("", 500)],
)
def test_contract_errors(monkeypatch, output, status):
    _fake_cases(monkeypatch, output)
    assert post_cases(make_csv("NULL,NULL,NULL,3,A,Dr. X,10")).status_code == status


def test_contract_rejects_out_of_range_placement(monkeypatch):
    _fake_cases(monkeypatch, "case -1 99 0 0\n")
    assert post_cases(make_csv("NULL,NULL,NULL,3,A,Dr. X,10")).status_code == 500


def test_contract_rejects_capacity_breaking_answer(monkeypatch):
    _fake_cases(monkeypatch, "case -1 1 0 0\n")  # 805 (20 seats) for 30 students
    assert post_cases(make_csv("NULL,NULL,NULL,3,A,Dr. X,30")).status_code == 500


@needs_swipl
def test_falls_back_to_single_answer(monkeypatch):
    monkeypatch.setattr(prolog_engine, "scheduler_supports_cases", lambda: False)
    response = post_cases(make_csv("NULL,NULL,NULL,3,A,Dr. X,10", "ECC-808,Tue,13,3,B,Dr. Y,90"), 5)
    assert response.status_code == 200
    [case] = response.json()["cases"]
    assert (case["rank"], case["score"], case["status"]) == (1, 100, "ok")


# ------------------------------------------------------- real scheduler.pl


def real_cases(*rows, max_cases=10):
    response = post_cases(make_csv(*rows), max_cases)
    assert response.status_code == 200, response.json()
    return response.json()


def assert_no_double_booking(case):
    rooms = [(c["room"], c["day"], c["period"]) for c in case["classes"]]
    profs = [(c["prof"].lower(), c["day"], c["period"]) for c in case["classes"]]
    assert len(set(rooms)) == len(rooms)
    assert len(set(profs)) == len(profs)


@needs_swipl
def test_real_ok_cases_are_capped():
    body = real_cases("NULL,NULL,NULL,3,A,Dr. X,10", "NULL,NULL,NULL,3,B,Dr. Y,10", max_cases=4)
    assert [(c["rank"], c["status"], c["errors"]) for c in body["cases"]] == [
        (i, "ok", 0) for i in range(1, 5)
    ]
    assert body["complete"] is True


@needs_swipl
def test_real_no_cap_returns_every_case():
    # Asks for Monday morning, any room: one case per room that fits.
    body = real_cases("NULL,Mon,9,3,A,Dr. X,10", max_cases=0)
    rooms = sorted(c["classes"][0]["room"] for c in body["cases"])
    assert rooms == sorted(r for r, cap in CAPACITIES.items() if cap >= 10)
    assert all(c["status"] == "ok" for c in body["cases"])


@needs_swipl
def test_real_room_clash_moves_one_class():
    body = real_cases(
        "ECC-804,Mon,9,3,A,Dr. X,10",
        "ECC-804,Mon,9,3,B,Dr. Y,10",
        "NULL,NULL,NULL,3,C,Dr. Z,10",
        max_cases=5,
    )
    assert len(body["cases"]) == 5
    for case in body["cases"]:
        assert (case["status"], case["errors"], case["score"]) == ("unsatisfied", 1, 66)
        assert case["unsatisfied"][0]["row"] in (0, 1)
        assert_no_double_booking(case)


@needs_swipl
def test_real_professor_clash_moves_two_of_three():
    body = real_cases(*(f"NULL,Mon,9,3,{t},Dr. X,10" for t in "ABC"), max_cases=3)
    for case in body["cases"]:
        assert case["errors"] == 2
        assert_no_double_booking(case)


@needs_swipl
def test_real_levels_grow_one_class_at_a_time():
    # Three 100-student classes asking for Monday morning; only 808/809
    # seat 100, so exactly one must move. With no cap the search runs to
    # the end: every 1-moved case first, then every 2-moved, then 3.
    body = real_cases(*(f"NULL,Mon,9,3,{t},Dr. {t},100" for t in "ABC"), max_cases=0)
    errors = [c["errors"] for c in body["cases"]]
    assert errors == sorted(errors) and errors[0] == 1 and set(errors) == {1, 2, 3}
    for case in body["cases"]:
        assert_no_double_booking(case)
    capped = real_cases(*(f"NULL,Mon,9,3,{t},Dr. {t},100" for t in "ABC"), max_cases=4)
    assert [c["errors"] for c in capped["cases"]] == [1] * 4


@needs_swipl
def test_real_unsatisfiable_when_nothing_fits():
    # 15 classes of 100 students: only 808/809 x 14 periods = 28 slots, so
    # that fits; 29 can't, wherever they move.
    rows = [f"NULL,NULL,NULL,3,C{i},Dr. {i},100" for i in range(29)]
    response = post_cases(make_csv(*rows), 3)
    assert response.status_code == 422
