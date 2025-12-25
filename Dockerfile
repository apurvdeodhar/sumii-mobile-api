# Sumii Mobile API - Dockerfile
# Production-ready FastAPI backend with Alembic migrations

FROM python:3.13-slim AS base

# Install system dependencies (including PDF generation libs for WeasyPrint)
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    # WeasyPrint dependencies for PDF generation
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies with uv
RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install -e .

# Copy alembic configuration
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Copy startup script and make executable
COPY start.sh ./
RUN chmod +x start.sh

# Copy application code
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Use start.sh: waits for Postgres, runs migrations, starts uvicorn
CMD ["./start.sh"]
