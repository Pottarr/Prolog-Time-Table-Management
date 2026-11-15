import csv
import io

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.building import BUILDING, FLOOR, PERIODS, ROOMS
from app.config import CORS_ALLOW_ORIGINS
from app.csv_validation import (
    EXPECTED_COLUMNS,
    CsvValidationError,
    parse_partial_schedule_csv,
    validate_schedule_csv,
)
from app.prolog_engine import PrologError, generate_timetable
from app.schedule_config import ConfigValidationError, parse_schedule_config
from app.typst_render import TypstCompileError, render_schedule_pdf

app = FastAPI(title="Prolog Time Table Management Gateway")

HTTP_422_UNPROCESSABLE_ENTITY = 422
HTTP_500_INTERNAL_SERVER_ERROR = 500

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def _read_config(config_file: UploadFile) -> dict:
    try:
        return parse_schedule_config(await config_file.read())
    except ConfigValidationError as exc:
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


async def _read_complete_schedule(csv_file: UploadFile, config: dict) -> tuple[bytes, list[dict]]:
    csv_bytes = await csv_file.read()
    try:
        return csv_bytes, validate_schedule_csv(csv_bytes, config["capacities"])
    except CsvValidationError as exc:
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _schedule_response(config: dict, classes: list[dict]) -> dict:
    """The JSON shape the frontend's floor plan and timetables consume."""
    return {
        "building": BUILDING,
        "floor": FLOOR,
        "rooms": ROOMS,
        "periods": PERIODS,
        "semester": config["semester"],
        "academic_year": config["academic_year"],
        "capacities": config["capacities"],
        "classes": classes,
    }


def _to_csv(classes: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(
        out, fieldnames=EXPECTED_COLUMNS, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(classes)
    return out.getvalue()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/schedule/parse")
async def parse_schedule(
    csv_file: UploadFile = File(...),
    config_file: UploadFile = File(...),
) -> dict:
    """Validates a *complete* schedule CSV and returns it as JSON.

    Same inputs and checks as `/api/schedule/pdf`; the frontend uses this to draw the
    clickable floor plan and per-room timetables, and fetches the PDF from
    `/api/schedule/pdf` separately when the user asks for it.
    """
    config = await _read_config(config_file)
    _, classes = await _read_complete_schedule(csv_file, config)
    return _schedule_response(config, classes)


@app.post("/api/schedule/pdf")
async def generate_schedule_pdf(
    csv_file: UploadFile = File(...),
    config_file: UploadFile = File(...),
) -> Response:
    """Renders a *complete* schedule CSV straight to PDF.

    Every row must already have room, day, and start filled in — for a
    CSV where professors left some of those blank, use
    `/api/schedule/auto` first (its response carries the completed CSV).
    """
    config = await _read_config(config_file)
    csv_bytes, _ = await _read_complete_schedule(csv_file, config)
    semester, academic_year = config["semester"], config["academic_year"]

    try:
        pdf_bytes = render_schedule_pdf(
            csv_bytes, semester, academic_year, config["capacities"]
        )
    except TypstCompileError as exc:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not render schedule: {exc}",
        )

    filename = f"classroom-schedule-{academic_year}-s{semester}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/schedule/auto")
async def generate_schedule_auto(
    csv_file: UploadFile = File(...),
    config_file: UploadFile = File(...),
) -> dict:
    """Accepts a *partial* schedule CSV and lets Prolog fill in the blanks.

    `room`, `day`, and `start` may each be blank or "NULL" — meaning the
    professor is flexible on that dimension. `span`, `title`, `prof`,
    and `students` are always required.

    The embedded Prolog solver (`solve_timetable/5` in scheduler.pl, via
    `app.prolog_engine`) picks a room, day and period for every flexible
    class. On success the response has the same shape as
    `/api/schedule/parse`, plus `csv`: the completed schedule as a CSV,
    which the frontend posts to `/api/schedule/pdf` for the PDF. If no
    timetable fits every rule, responds 422 with the reason.
    """
    config = await _read_config(config_file)
    capacities = config["capacities"]

    try:
        courses = parse_partial_schedule_csv(await csv_file.read(), capacities)
    except CsvValidationError as exc:
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    try:
        result = generate_timetable(capacities, courses)
    except PrologError as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"The Prolog scheduler failed: {exc}",
        )
    if result["status"] != "ok":
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY, detail=result["reason"])

    # Re-check Prolog's answer with the same rules a hand-written CSV must
    # pass, so a solver bug can never reach the UI or the PDF.
    completed_csv = _to_csv(result["assignments"])
    try:
        classes = validate_schedule_csv(completed_csv.encode(), capacities)
    except CsvValidationError as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prolog returned an invalid timetable: {exc}",
        )

    return {**_schedule_response(config, classes), "csv": completed_csv}
