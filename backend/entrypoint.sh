#!/usr/bin/env sh
set -euo pipefail

DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"
echo "Waiting for Postgres at ${DB_HOST}:${DB_PORT}..."
until nc -z "${DB_HOST}" "${DB_PORT}"; do
  sleep 1
done

# Apply database migrations
python manage.py migrate --noinput

# Collect static files (idempotent)
python manage.py collectstatic --noinput

# Run any additional Django system checks in production
python manage.py check --deploy || true

# Exec the main container command (e.g., gunicorn)
exec "$@"
