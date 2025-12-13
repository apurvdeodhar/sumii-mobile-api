# Sumii Backend - Dockerfile
# Multi-stage build for production-ready FastAPI backend

FROM python:3.13-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
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

# Copy application code
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Run database migrations and start server
CMD ["/bin/bash", "-c", ". .venv/bin/activate && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
