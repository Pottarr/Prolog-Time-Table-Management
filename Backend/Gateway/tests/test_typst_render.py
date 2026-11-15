"""The PDF renderer's plumbing, with `typst` itself replaced by a fake.

(Real-typst rendering is covered in test_api.py, skipped without typst.)
"""

import json
import subprocess
from pathlib import Path

import pytest

from app import typst_render
from app.typst_render import TypstCompileError, render_schedule_pdf
from tests.conftest import CAPACITIES

CSV = b"room,day,start,span,title,prof,students\nECC-801,Mon,9,3,A,Dr. X,10\n"


def test_writes_inputs_next_to_the_template_and_returns_the_pdf(monkeypatch):
    seen = {}

    def fake_run(cmd, cwd, **kwargs):
        cwd = Path(cwd)
        seen["cmd"] = cmd
        seen["files"] = sorted(p.name for p in cwd.iterdir())
        seen["csv"] = (cwd / "schedule.csv").read_bytes()
        seen["header"] = json.loads((cwd / "header.json").read_text())
        (cwd / typst_render.OUTPUT_NAME).write_bytes(b"%PDF-fake")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(typst_render.subprocess, "run", fake_run)
    pdf = render_schedule_pdf(CSV, 2, 2027, dict(CAPACITIES))

    assert pdf == b"%PDF-fake"
    assert seen["cmd"] == ["typst", "compile", typst_render.TEMPLATE_NAME, typst_render.OUTPUT_NAME]
    assert seen["files"] == sorted(["classroom-schedule.typ", "header.json", "schedule.csv"])
    assert seen["csv"] == CSV
    assert seen["header"] == {"semester": 2, "academic_year": 2027, "capacities": CAPACITIES}


@pytest.mark.parametrize(
    "stderr, stdout, message",
    [
        ("error: bad thing", "", "error: bad thing"),
        ("", "only on stdout", "only on stdout"),
        ("", "", "typst compile failed"),
    ],
)
def test_failed_compile_raises_with_typst_output(monkeypatch, stderr, stdout, message):
    monkeypatch.setattr(
        typst_render.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout, stderr),
    )
    with pytest.raises(TypstCompileError, match=message):
        render_schedule_pdf(CSV, 1, 2026, dict(CAPACITIES))


def test_template_is_bundled():
    assert (typst_render.TEMPLATE_DIR / typst_render.TEMPLATE_NAME).is_file()
