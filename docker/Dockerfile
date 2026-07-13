FROM python:3.12-slim AS base

WORKDIR /app

ENV PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY . .

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Non-root user
RUN groupadd -g 1000 appuser && useradd -u 1000 -g appuser -s /bin/sh appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]

# ── Test stage (used by CI) ─────────────────────────────────────────────
FROM base AS test

USER root
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install pytest pytest-cov pytest-asyncio ruff mypy
USER appuser
