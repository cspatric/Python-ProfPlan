#!/usr/bin/env bash
set -euo pipefail

# Wait for the database and apply migrations before starting the API
echo "Applying migrations..."
alembic upgrade head

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
