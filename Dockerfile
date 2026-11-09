# ── Stage 1: build / install dependencies ─────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools (some packages compile native extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY api_app/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime image (slim, no build tools) ─────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user — security best practice for containers
RUN groupadd --gid 1001 appuser && \
    useradd  --uid 1001 --gid appuser --no-create-home appuser

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY api_app/ ./api_app/

# Env defaults (overridden by K8s Secret / ConfigMap at runtime)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

USER appuser

EXPOSE 8000

# Healthcheck so Docker / K8s can detect unhealthy containers early
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"

# Use Uvicorn with multiple workers for concurrency
CMD ["uvicorn", "api_app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

