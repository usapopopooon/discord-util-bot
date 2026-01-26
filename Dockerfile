FROM python:3.12-slim

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

# Run the bot
CMD ["python", "-m", "src.main"]
