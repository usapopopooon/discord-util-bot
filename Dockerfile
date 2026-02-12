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

# Default: run the bot
# Railway overrides this per service via start command
CMD ["python", "-m", "src.main"]

# Development image with dev dependencies
FROM base AS dev

RUN pip install --no-cache-dir -e ".[dev]"
COPY tests/ tests/
