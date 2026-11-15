import os

# Allowed CORS origins when the CORS_ALLOW_ORIGINS env var isn't set. "*"
# accepts any origin, e.g. the frontend on any machine in a tailnet.
DEFAULT_CORS_ALLOW_ORIGINS = "*"

# Comma-separated list of allowed origins, e.g.
# "http://localhost:5173,https://timetable.example.com". Set the
# CORS_ALLOW_ORIGINS env var to restrict it; otherwise
# DEFAULT_CORS_ALLOW_ORIGINS applies.
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOW_ORIGINS", DEFAULT_CORS_ALLOW_ORIGINS).split(",")
    if origin.strip()
]
