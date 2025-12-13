#!/bin/bash
# Run Alembic Migrations Script
# Runs migrations on both development and test databases using .env configuration

set -e

echo "🔄 Running Alembic migrations..."

# Load .env file if it exists
if [ -f .env ]; then
    echo "📄 Loading .env file..."
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check if we're in Docker or local
if [ -f /.dockerenv ]; then
    # Inside Docker container
    echo "📦 Running inside Docker container"
    source .venv/bin/activate

    # Run migrations on development database (default from .env or DATABASE_URL env var)
    echo "📊 Migrating development database (sumii_dev)..."
    alembic upgrade head

    # Run migrations on test database (override DATABASE_URL for this command only)
    echo "📊 Migrating test database (sumii_test)..."
    DATABASE_URL="${DATABASE_URL/sumii_dev/sumii_test}" alembic upgrade head

    echo "✅ Migrations complete!"
else
    # Local development
    echo "💻 Running locally"

    # Ensure PostgreSQL is running
    if ! docker-compose ps postgres | grep -q "Up"; then
        echo "⚠️  PostgreSQL not running. Starting..."
        docker-compose up -d postgres
        sleep 5
    fi

    source .venv/bin/activate

    # Run migrations on development database (uses .env or default)
    echo "📊 Migrating development database (sumii_dev)..."
    alembic upgrade head

    # Run migrations on test database (override for this command)
    echo "📊 Migrating test database (sumii_test)..."
    DATABASE_URL="${DATABASE_URL/sumii_dev/sumii_test}" alembic upgrade head

    echo "✅ Migrations complete!"
fi
