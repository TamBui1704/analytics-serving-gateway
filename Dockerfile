# ── Stage 1: build / install dependencies ─────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# No gcc / build tools needed: every dependency ships a prebuilt manylinux wheel.
# --only-binary=:all: makes the build FAIL LOUDLY if a future dependency would
# need compiling — in that case re-add:
#   RUN apt-get update && apt-get install -y --no-install-recommends gcc libffi-dev \
#       && rm -rf /var/lib/apt/lists/*
COPY api_app/requirements.txt .
RUN pip install --no-cache-dir --only-binary=:all: --prefix=/install -r requirements.txt


# ── Stage 2: runtime image (slim, no build tools) ─────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user — security best practice for containers
RUN groupadd --gid 1001 appuser && \
    useradd  --uid 1001 --gid appuser --no-create-home appuser

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source (junk like __pycache__ is filtered by .dockerignore)
COPY api_app/ ./api_app/

# Env defaults (overridden by docker-compose / K8s ConfigMap at runtime)
#   PORT    : port Uvicorn listens on
#   WORKERS : Uvicorn processes per container. Default 1 = K8s-friendly
#             (scale with replicas / HPA instead); docker-compose sets 2.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    WORKERS=1

USER appuser

# Documentation only — real port mapping is done by compose `ports:` / K8s Service
EXPOSE 8000

# Docker-only healthcheck (docker run / docker-compose).
# NOTE: Kubernetes IGNORES this — K8s uses livenessProbe / readinessProbe
# defined in k8s/api-deployment.yaml.
# Shell form so ${PORT} is expanded at runtime.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/healthz', timeout=4)"

# `sh -c` lets us expand ${PORT}/${WORKERS}; `exec` replaces the shell so
# Uvicorn becomes PID 1 and receives SIGTERM directly (graceful shutdown).
# --no-access-log tắt access log trùng lặp của Uvicorn (đã có middleware log_requests chuẩn trong main.py).
CMD ["sh", "-c", "exec uvicorn api_app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS} --no-access-log"]
