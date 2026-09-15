from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.config import CORS_ALLOW_ORIGINS
from app.csv_validation import (
    CsvValidationError,
    parse_partial_schedule_csv,
    validate_schedule_csv,
)
from app.prolog_client import build_prolog_request
from app.typst_render import TypstCompileError, render_schedule_pdf

app = FastAPI(title="Prolog Time Table Management Gateway")

HTTP_422_UNPROCESSABLE_ENTITY = 422
HTTP_501_NOT_IMPLEMENTED = 501

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_SEMESTERS = (1, 2)
MIN_ACADEMIC_YEAR = 2000
MAX_ACADEMIC_YEAR = 2100


def _validate_semester_and_year(semester: int, academic_year: int) -> None:
    if semester not in VALID_SEMESTERS:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"semester must be one of {VALID_SEMESTERS}, got {semester}.",
        )
    if not (MIN_ACADEMIC_YEAR <= academic_year <= MAX_ACADEMIC_YEAR):
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"academic_year must be between {MIN_ACADEMIC_YEAR} and "
                f"{MAX_ACADEMIC_YEAR}, got {academic_year}."
            ),
        )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/schedule/pdf")
async def generate_schedule_pdf(
    csv_file: UploadFile = File(...),
    semester: int = Form(...),
    academic_year: int = Form(...),
) -> Response:
    """Renders a *complete* schedule CSV straight to PDF.

    Every row must already have room, day, and start filled in — for a
    CSV where professors left some of those blank, use
    `/api/schedule/auto` instead.
    """
    _validate_semester_and_year(semester, academic_year)

    csv_bytes = await csv_file.read()

    try:
        validate_schedule_csv(csv_bytes)
    except CsvValidationError as exc:
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    try:
        pdf_bytes = render_schedule_pdf(csv_bytes, semester, academic_year)
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
    semester: int = Form(...),
    academic_year: int = Form(...),
) -> dict:
    """Accepts a *partial* schedule CSV for auto-scheduling.

    `room`, `day`, and `start` may each be blank or "NULL" — meaning the
    professor is flexible on that dimension. `span`, `title`, and `prof`
    are always required.

    The gateway does not yet call the Prolog service (it isn't
    implemented there), so this always responds 501 with the request
    payload that will eventually be POSTed to it — see
    `app.prolog_client` for the full contract.
    """
    _validate_semester_and_year(semester, academic_year)

    csv_bytes = await csv_file.read()

    try:
        courses = parse_partial_schedule_csv(csv_bytes)
    except CsvValidationError as exc:
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    prolog_request = build_prolog_request(semester, academic_year, courses)

    raise HTTPException(
        status_code=HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": (
                "Auto-scheduling isn't implemented yet — the gateway doesn't "
                "call the Prolog service. This is the request it will send "
                "once that's wired up."
            ),
            "prolog_request": prolog_request,
        },
    )
