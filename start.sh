#!/bin/bash
set -e

echo "Working directory: $(pwd)"
echo "Python: $(python --version)"

echo "Running database migrations..."
# If the alembic_version table doesn't exist yet, run upgrade normally.
# If partial migration left orphaned types/tables, the IF NOT EXISTS guards handle it.
# If migration was already completed, alembic skips it (version already recorded).
python -m alembic upgrade head

echo "Migrations complete. Starting bot..."
exec python main.py
