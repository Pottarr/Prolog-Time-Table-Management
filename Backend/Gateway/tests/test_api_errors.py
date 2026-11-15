"""How the HTTP routes react when Prolog or typst misbehave.

The solver and renderer are replaced with fakes, so these need neither
`swipl` nor `typst`.
"""

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import _to_csv, app
from app.prolog_engine import PrologError
from app.typst_render import TypstCompileError
from tests.conftest import make_config, make_csv

client = TestClient(app)


def post(endpoint, csv_bytes, config_bytes=None):
    return client.post(
        f"/api/schedule/{endpoint}",
        files={
            "csv_file": ("schedule.csv", csv_bytes, "text/csv"),
            "config_file": ("config.json", config_bytes or make_config(), "application/json"),
        },
    )


FLEXIBLE = make_csv("NULL,NULL,NULL,3,A,Dr. X,10")


def assignment(**overrides):
    base = {
        "room": "ECC-801",
        "day": "Mon",
        "start": 9,
        "span": 3,
        "period": "morning",
        "title": "A",
        "prof": "Dr. X",
        "students": 10,
    }
    return {**base, **overrides}


# ------------------------------------------------------------------ auto


def test_auto_crash_in_prolog_is_a_500(monkeypatch):
    def boom(capacities, courses):
        raise PrologError("swipl exploded")

    monkeypatch.setattr(main, "generate_timetable", boom)
    response = post("auto", FLEXIBLE)
    assert response.status_code == 500
    assert "swipl exploded" in response.json()["detail"]


def test_auto_timeout_is_a_422_with_the_reason(monkeypatch):
    monkeypatch.setattr(
        main,
        "generate_timetable",
        lambda c, k: {"status": "timeout", "reason": "took too long"},
    )
    response = post("auto", FLEXIBLE)
    assert response.status_code == 422
    assert response.json()["detail"] == "took too long"


@pytest.mark.parametrize(
    "bad",
    [
        [assignment(room="ECC-805", students=10), assignment(room="ECC-805", prof="Dr. Y")],  # room clash
        [assignment(room="ECC-805", students=99)],  # over capacity
        [assignment(room="ECC-806")],  # co-working space
    ],
)
def test_auto_invalid_answer_from_prolog_never_reaches_the_ui(monkeypatch, bad):
    monkeypatch.setattr(main, "generate_timetable", lambda c, k: {"status": "ok", "assignments": bad})
    response = post("auto", FLEXIBLE)
    assert response.status_code == 500
    assert "Prolog returned an invalid timetable" in response.json()["detail"]


def test_auto_bad_config_is_rejected_before_prolog_runs(monkeypatch):
    def never(*args):
        raise AssertionError("Prolog should not run")

    monkeypatch.setattr(main, "generate_timetable", never)
    response = post("auto", FLEXIBLE, b"{not json")
    assert response.status_code == 422


# ------------------------------------------------------------------- pdf


def test_pdf_typst_failure_is_a_422(monkeypatch):
    def fail(*args):
        raise TypstCompileError("font missing")

    monkeypatch.setattr(main, "render_schedule_pdf", fail)
    response = post("pdf", make_csv("ECC-801,Mon,9,3,A,Dr. X,10"))
    assert response.status_code == 422
    assert "font missing" in response.json()["detail"]


def test_pdf_filename_names_year_and_semester(monkeypatch):
    monkeypatch.setattr(main, "render_schedule_pdf", lambda *a: b"%PDF-fake")
    response = post(
        "pdf",
        make_csv("ECC-801,Mon,9,3,A,Dr. X,10"),
        make_config(semester=2, academic_year=2027),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="classroom-schedule-2027-s2.pdf"' in response.headers["content-disposition"]
    assert response.content == b"%PDF-fake"


# ------------------------------------------------------------- helpers


def test_to_csv_drops_the_period_and_keeps_column_order():
    text = _to_csv([assignment(title="Algorithms (Sec 2, English)")])
    assert text.splitlines() == [
        "room,day,start,span,title,prof,students",
        'ECC-801,Mon,9,3,"Algorithms (Sec 2, English)",Dr. X,10',
    ]


def test_cors_allows_the_frontend():
    response = client.get("/api/health", headers={"Origin": "http://localhost:9090"})
    assert response.headers.get("access-control-allow-origin") in ("*", "http://localhost:9090")


def test_unknown_route_is_404():
    assert client.get("/api/nope").status_code == 404
