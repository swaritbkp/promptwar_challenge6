# Multi-stage production build for HawaKhata
# Stage 1: Build dependencies
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Final minimal runtime
FROM python:3.13-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    APP_ENV=prod \
    PATH="/install/bin:$PATH" \
    PYTHONPATH="/app/src:/install/lib/python3.13/site-packages"

WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /install /install

# Copy application code and runtime assets
COPY src ./src
COPY templates ./templates
COPY static ./static
COPY data ./data
COPY prompts ./prompts

# Non-root user for principle of least privilege
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app /install

USER appuser

# Healthcheck on internal metadata endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + str('${PORT:-8080}') + '/api/v1/meta').read()" || exit 1

EXPOSE 8080

CMD ["sh", "-c", "uvicorn hawakhata.app:create_app --factory --app-dir src --host 0.0.0.0 --port ${PORT:-8080}"]
