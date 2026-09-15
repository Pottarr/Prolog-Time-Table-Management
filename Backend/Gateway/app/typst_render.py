"""Renders the classroom schedule PDF by shelling out to the `typst` CLI."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_NAME = "classroom-schedule.typ"
OUTPUT_NAME = "output.pdf"
COMPILE_TIMEOUT_SECONDS = 30


class TypstCompileError(RuntimeError):
    """Raised when `typst compile` exits non-zero; message is typst's own error output."""


def render_schedule_pdf(csv_bytes: bytes, semester: int, academic_year: int) -> bytes:
    """Compile the bundled typst template against the given CSV + header, return PDF bytes.

    The template reads `schedule.csv` and `header.json` relative to its own
    location (typst resolves relative paths that way), so both files are
    written next to a fresh copy of the template in an isolated temp dir.
    """
    with tempfile.TemporaryDirectory(prefix="schedule-") as tmp:
        tmp_path = Path(tmp)
        shutil.copy(TEMPLATE_DIR / TEMPLATE_NAME, tmp_path / TEMPLATE_NAME)
        (tmp_path / "schedule.csv").write_bytes(csv_bytes)
        (tmp_path / "header.json").write_text(
            json.dumps({"semester": semester, "academic_year": academic_year})
        )

        result = subprocess.run(
            ["typst", "compile", TEMPLATE_NAME, OUTPUT_NAME],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=COMPILE_TIMEOUT_SECONDS,
        )

        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "typst compile failed"
            raise TypstCompileError(message)

        return (tmp_path / OUTPUT_NAME).read_bytes()
