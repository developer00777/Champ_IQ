# ─── ChampIQ V2 AI Engine ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# System dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy all source first, then install
COPY pyproject.toml ./
COPY champiq_v2/ ./champiq_v2/

RUN pip install --no-cache-dir "."

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run
CMD ["uvicorn", "champiq_v2.main:app", "--host", "0.0.0.0", "--port", "8001"]
