#!/bin/sh
set -e

echo "Waiting for PostgreSQL at ${DB_HOST:-localhost}:${DB_PORT:-5432} ..."
until python -c "
import socket, sys
try:
    s = socket.create_connection(('${DB_HOST:-localhost}', ${DB_PORT:-5432}), timeout=2)
    s.close()
except OSError:
    sys.exit(1)
"; do
  sleep 1
done
echo "PostgreSQL is ready."

echo "Running database migrations ..."
alembic upgrade head

echo "Starting application ..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000
