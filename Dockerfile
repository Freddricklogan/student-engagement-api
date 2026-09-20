# syntax=docker/dockerfile:1

# ---------- stage 1: build the dependency tree in an isolated virtualenv ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Build-only toolchain; none of it reaches the runtime image.
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# ---------- stage 2: runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000 \
    HOST=0.0.0.0 \
    DEMO_MODE=true \
    DATABASE_URL=sqlite+aiosqlite:////data/engagement.db

# curl is needed by HEALTHCHECK; nothing else is installed.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 appgroup \
    && useradd --system --uid 1001 --gid appgroup --no-create-home appuser \
    && mkdir -p /data \
    && chown -R appuser:appgroup /data

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=appuser:appgroup app/ ./app/
COPY --chown=appuser:appgroup scripts/ ./scripts/
COPY --chown=appuser:appgroup static/ ./static/

# Never run as root.
USER appuser

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent --show-error http://127.0.0.1:${PORT}/health || exit 1

# One uvicorn worker per container; scale with replicas, not with threads.
CMD ["sh", "-c", "exec uvicorn app.main:app --host ${HOST} --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
