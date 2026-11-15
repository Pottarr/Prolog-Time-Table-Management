# --- Stage 1: fetch a pinned, static typst binary -----------------------
FROM debian:bookworm-slim AS typst-fetch

ARG TYPST_VERSION=0.12.0
ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH}" in \
        amd64) TYPST_ARCH="x86_64-unknown-linux-musl" ;; \
        arm64) TYPST_ARCH="aarch64-unknown-linux-musl" ;; \
        *) echo "unsupported arch: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL \
        "https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-${TYPST_ARCH}.tar.xz" \
        -o /tmp/typst.tar.xz; \
    tar -xf /tmp/typst.tar.xz -C /tmp; \
    mv "/tmp/typst-${TYPST_ARCH}/typst" /usr/local/bin/typst; \
    chmod +x /usr/local/bin/typst

# --- Stage 2: Python app via uv ------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=typst-fetch /usr/local/bin/typst /usr/local/bin/typst

# swi-prolog-nox provides `swipl`, which app/prolog_engine.py runs for
# auto-scheduling — no separate Prolog container/service.
RUN apt-get update && apt-get install -y --no-install-recommends swi-prolog-nox \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first so this layer is cached across source changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app ./app
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
