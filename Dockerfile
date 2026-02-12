FROM python:3.12-slim AS base

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy source code
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Create data directory
RUN mkdir -p data

# Run migrations, then start the bot and web server
CMD ["sh", "-c", "alembic upgrade head && python -m src.main & uvicorn src.web.app:app --host 0.0.0.0 --port ${PORT:-8000} & wait"]

# Development image with dev dependencies
FROM base AS dev

RUN pip install --no-cache-dir -e ".[dev]"
COPY tests/ tests/
