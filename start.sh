#!/bin/bash
set -e

echo "Working directory: $(pwd)"
echo "Python: $(python --version)"
echo "Running database migrations..."
python -m alembic upgrade head
echo "Migrations complete. Starting bot..."
exec python main.py
