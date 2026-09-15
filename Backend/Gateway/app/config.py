import os

# Comma-separated list of allowed origins for the frontend dev server / deployment,
# e.g. "http://localhost:5173,https://timetable.example.com". Defaults to "*" for
# local development.
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",")
    if origin.strip()
]
