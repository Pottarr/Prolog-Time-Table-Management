"""The Prolog bridge (`app.prolog_engine`) and scheduler.pl itself.

Most tests run the real `swipl`; they're skipped when it isn't installed.
The error-path tests replace `_run` so they need no Prolog at all.
"""

import shutil
import subprocess
from collections import Counter

import pytest

from app import prolog_engine
from app.building import DAYS
from app.prolog_engine import PrologError, generate_timetable
from tests.conftest import CAPACITIES

needs_swipl = pytest.mark.skipif(shutil.which("swipl") is None, reason="swipl not installed")


def course(room=None, day=None, start=None, prof="Dr. X", students=10, title="C"):
    return {
        "room": room,
        "day": day,
        "start": start,
        "span": 3,
        "title": title,
        "prof": prof,
        "students": students,
    }


def solve(*courses):
    result = generate_timetable(dict(CAPACITIES), list(courses))
    assert result["status"] == "ok", result
    return result["assignments"]


# ------------------------------------------------------------ real swipl


@needs_swipl
def test_fully_fixed_course_is_left_alone():
    [placed] = solve(course("ECC-808", "Thu", 13, students=90))
    assert (placed["room"], placed["day"], placed["start"], placed["period"]) == (
        "ECC-808",
        "Thu",
        13,
        "afternoon",
    )


@needs_swipl
def test_text_fields_are_passed_through_untouched():
    [placed] = solve(course(title="Algorithms (Sec 2, English)", prof="  Dr.  Veera ", students=42))
    assert placed["title"] == "Algorithms (Sec 2, English)"
    assert placed["prof"] == "  Dr.  Veera "
    assert (placed["students"], placed["span"]) == (42, 3)


@needs_swipl
def test_flexible_course_goes_to_monday_morning_first():
    [placed] = solve(course())
    assert (placed["day"], placed["period"], placed["start"]) == ("Mon", "morning", 9)


@needs_swipl
def test_flexible_start_becomes_the_period_start():
    for placed in solve(*[course(prof=f"Dr. {i}") for i in range(30)]):
        assert placed["start"] == {"morning": 9, "afternoon": 13}[placed["period"]]


@needs_swipl
def test_fixed_day_and_flexible_time():
    [placed] = solve(course(day="Sat"))
    assert placed["day"] == "Sat"


@needs_swipl
def test_fixed_time_and_flexible_day():
    [placed] = solve(course(start=13))
    assert (placed["period"], placed["start"]) == ("afternoon", 13)


@needs_swipl
def test_never_places_a_class_in_a_too_small_room():
    placed = solve(*[course(prof=f"Dr. {i}", students=s) for i, s in enumerate([100, 50, 20, 21, 51])])
    for p in placed:
        assert CAPACITIES[p["room"]] >= p["students"]


@needs_swipl
def test_never_uses_the_coworking_space():
    placed = solve(*[course(prof=f"Dr. {i}", students=1) for i in range(126)])
    assert "ECC-806" not in {p["room"] for p in placed}


@needs_swipl
def test_weekdays_fill_before_the_weekend():
    # 9 class rooms x 2 periods x 5 weekdays = 90 weekday slots.
    placed = solve(*[course(prof=f"Dr. {i}") for i in range(90)])
    assert {p["day"] for p in placed} <= set(DAYS[:5])


@needs_swipl
def test_no_room_or_professor_double_booked():
    courses = [course(prof=f"Dr. {i % 7}", students=[10, 30, 60][i % 3]) for i in range(60)]
    placed = solve(*courses)
    rooms = Counter((p["room"], p["day"], p["period"]) for p in placed)
    profs = Counter((p["prof"], p["day"], p["period"]) for p in placed)
    assert max(rooms.values()) == 1
    assert max(profs.values()) == 1


@needs_swipl
def test_professor_names_are_matched_case_and_space_insensitively():
    # Same person written two ways, both on Monday: must get different periods.
    first, second = solve(
        course(prof="Dr. Veera", day="Mon"),
        course(prof=" DR.  veera", day="Mon"),
    )
    assert first["period"] != second["period"]

    # ...and a third spelling on the same Monday has nowhere left to go.
    result = generate_timetable(
        dict(CAPACITIES),
        [course(prof=p, day="Mon") for p in ("Dr. Veera", "dr. veera", " DR.  VEERA")],
    )
    assert result["status"] == "unsatisfiable"


@needs_swipl
def test_one_professor_can_only_teach_two_classes_a_day():
    result = generate_timetable(
        dict(CAPACITIES),
        [course(day="Mon", prof="Dr. X") for _ in range(3)],
    )
    assert result["status"] == "unsatisfiable"
    assert "No timetable satisfies every rule" in result["reason"]


@needs_swipl
def test_two_fixed_classes_in_the_same_slot_is_unsatisfiable():
    result = generate_timetable(
        dict(CAPACITIES),
        [course("ECC-801", "Mon", 9, prof="A"), course("ECC-801", "Mon", 9, prof="B")],
    )
    assert result["status"] == "unsatisfiable"


@needs_swipl
def test_empty_course_list_is_ok():
    assert generate_timetable(dict(CAPACITIES), []) == {"status": "ok", "assignments": []}


@needs_swipl
def test_scheduler_pl_answers_on_stdout():
    """Talk to scheduler.pl the way the gateway does, without the Python wrapper."""
    request = "request([c(0,0,-1,-1,-1), c(0,0,-1,0,-1)], 3, 5).\n"
    result = subprocess.run(
        ["swipl", "-q", "-g", "main_timetable", "-t", "halt", str(prolog_engine.SCHEDULER_PL)],
        input=request,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    status, *numbers = result.stdout.split()
    assert status == "ok"
    assert len(numbers) == 6
    # Same professor, both on Monday -> different periods.
    assert numbers[2] != numbers[5]


# ------------------------------------------------- error paths (no swipl)


def fake_run(answer):
    def _run(goal, request):
        return answer

    return _run


def test_timeout_answer_becomes_a_timeout_result(monkeypatch):
    monkeypatch.setattr(prolog_engine, "_run", fake_run("timeout"))
    result = generate_timetable(dict(CAPACITIES), [course()])
    assert result["status"] == "timeout"
    assert "within" in result["reason"]


@pytest.mark.parametrize("answer", ["", "banana", "ok 1 2", "ok 1 2 3 4"])
def test_unexpected_answer_raises(monkeypatch, answer):
    monkeypatch.setattr(prolog_engine, "_run", fake_run(answer))
    with pytest.raises(PrologError):
        generate_timetable(dict(CAPACITIES), [course()])


def test_request_contains_only_integers(monkeypatch):
    seen = {}

    def _run(goal, request):
        seen["goal"], seen["request"] = goal, request
        return "ok 0 0 0"

    monkeypatch.setattr(prolog_engine, "_run", _run)
    generate_timetable(dict(CAPACITIES), [course(title="'; halt. %", prof="x), evil(")])
    assert seen["goal"] == "main_timetable"
    body = seen["request"].removeprefix("request([").split("]")[0]
    assert set(body) <= set("c(),-0123456789")


def test_room_indices_are_ordered_smallest_room_first(monkeypatch):
    # Index 0 must be the smallest room. 806 (capacity 0) is the smallest.
    monkeypatch.setattr(prolog_engine, "_run", fake_run("ok 0 0 0"))
    result = generate_timetable(dict(CAPACITIES), [course(students=0)])
    assert result["assignments"][0]["room"] == "ECC-806"


def test_nonzero_exit_raises_prolog_error(monkeypatch):
    def fake_subprocess_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="boom")

    monkeypatch.setattr(prolog_engine.subprocess, "run", fake_subprocess_run)
    with pytest.raises(PrologError, match="boom"):
        prolog_engine._run("main_timetable", "")


def test_process_timeout_raises_prolog_error(monkeypatch):
    def fake_subprocess_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="swipl", timeout=1)

    monkeypatch.setattr(prolog_engine.subprocess, "run", fake_subprocess_run)
    with pytest.raises(PrologError, match="didn't finish"):
        prolog_engine._run("main_timetable", "")
