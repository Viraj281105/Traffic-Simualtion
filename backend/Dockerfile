# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.14.7-slim-bookworm AS builder

WORKDIR /app

# Install dependencies first (layer caching)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.14.7-slim-bookworm

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Set PYTHONPATH so `src.*` imports resolve correctly
ENV PYTHONPATH=/app

# Copy source code and schemas
COPY backend/src/ ./src/
COPY shared/ ./shared/
COPY backend/docker-entrypoint.py /docker-entrypoint.py

# Create the non-root user the app actually runs as. /app is owned by it so
# a *fresh* named volume mounted at /app/data (docker-compose.yml) is
# correctly seeded with that ownership by Docker on first creation. The
# container still starts as root (no USER switch here) because a volume
# reused from an older, root-based build of this image keeps its existing
# root ownership across restarts — docker-entrypoint.py fixes that, then
# permanently drops to appuser before the real process ever runs, so the
# application itself is still never root either way.
RUN useradd --system --create-home --home-dir /home/appuser --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

EXPOSE 8000

# Health check — hits the /health endpoint every 30s
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["python", "/docker-entrypoint.py"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
