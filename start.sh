#!/bin/bash
set -e

echo "🚀 Starting sumii-mobile-api backend..."

# Wait for Postgres to be ready (if pg_isready is available)
if command -v pg_isready &> /dev/null; then
    DB_HOST="${DB_HOST:-localhost}"
    echo "⏳ Waiting for Postgres at $DB_HOST..."
    while ! pg_isready -h "$DB_HOST" -p 5432 > /dev/null 2>&1; do
        sleep 1
    done
    echo "✅ Postgres is ready!"
fi

# Run database migrations
echo "📦 Running Alembic migrations..."
cd /app
source .venv/bin/activate
alembic upgrade head
echo "✅ Migrations complete!"

# Start the application
PORT="${PORT:-8000}"
if [ "$ENVIRONMENT" = "dev" ] || [ "$ENVIRONMENT" = "development" ]; then
    echo "🎯 Starting uvicorn server (development with hot-reload)..."
    exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
else
    echo "🎯 Starting uvicorn server (production)..."
    exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
fi
