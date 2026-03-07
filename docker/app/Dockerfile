FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first (layer cache)
COPY pyproject.toml .
COPY src/ src/

# Install production dependencies only
RUN uv sync --no-dev --no-cache

# Copy application files
COPY docker-compose.yml .

# Data directory (mounted as volume in compose)
RUN mkdir -p data/raw data/db data/pine_scripts data/checklists

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
