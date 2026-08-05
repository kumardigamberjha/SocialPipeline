# =============================================================================
# Wings of AI — Python Backend (Multi-stage)
# =============================================================================
# Build:  docker build -t wings-api .
# Run:    docker run -p 8000:8000 --env-file app/.env wings-api
# =============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# Install system deps needed for some Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install torch --extra-index-url https://download.pytorch.org/whl/cpu && \
    /opt/venv/bin/pip install -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application code
# NOTE: app/.env is excluded by .dockerignore — secrets are supplied at run
# time via `env_file:` / `--env-file`, never baked into a layer.
COPY app/ ./app/

# Run as an unprivileged user. Created before the chown so the writable
# directories (output/, data/) belong to it.
RUN useradd --system --create-home --shell /usr/sbin/nologin appuser && \
    mkdir -p output data && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Default: run FastAPI with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
