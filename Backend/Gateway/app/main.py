from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.config import CORS_ALLOW_ORIGINS
from app.csv_validation import CsvValidationError, validate_schedule_csv
from app.typst_render import TypstCompileError, render_schedule_pdf

app = FastAPI(title="Prolog Time Table Management Gateway")

HTTP_422_UNPROCESSABLE_ENTITY = 422

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_SEMESTERS = (1, 2)
MIN_ACADEMIC_YEAR = 2000
MAX_ACADEMIC_YEAR = 2100


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/schedule/pdf")
async def generate_schedule_pdf(
    csv_file: UploadFile = File(...),
    semester: int = Form(...),
    academic_year: int = Form(...),
) -> Response:
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
