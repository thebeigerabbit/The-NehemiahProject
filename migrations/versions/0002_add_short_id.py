"""Add short_id to users

Revision ID: 0002_add_short_id
Revises: 0001_initial
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa
import random
import string


revision = '0002_add_short_id'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def gen_short_id():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=4))


def upgrade() -> None:
    conn = op.get_bind()

    # Add short_id column to users if it doesn't exist
    try:
        conn.execute(sa.text(
            "ALTER TABLE users ADD COLUMN short_id VARCHAR(8) UNIQUE"
        ))
    except Exception:
        pass  # Column may already exist

    # Add short_id column to partnerships if it doesn't exist
    try:
        conn.execute(sa.text(
            "ALTER TABLE partnerships ADD COLUMN short_id VARCHAR(8) UNIQUE"
        ))
    except Exception:
        pass  # Column may already exist

    # Backfill any existing users that don't have a short_id
    result = conn.execute(sa.text("SELECT id FROM users WHERE short_id IS NULL"))
    rows = result.fetchall()
    for row in rows:
        for _ in range(20):  # retry for uniqueness
            sid = gen_short_id()
            try:
                conn.execute(sa.text(
                    "UPDATE users SET short_id = :sid WHERE id = :uid"
                ), {"sid": sid, "uid": row[0]})
                break
            except Exception:
                continue

    # Backfill any existing partnerships that don't have a short_id
    result = conn.execute(sa.text("SELECT id FROM partnerships WHERE short_id IS NULL"))
    rows = result.fetchall()
    for row in rows:
        for _ in range(20):
            sid = gen_short_id()
            try:
                conn.execute(sa.text(
                    "UPDATE partnerships SET short_id = :sid WHERE id = :pid"
                ), {"sid": sid, "pid": row[0]})
                break
            except Exception:
                continue


def downgrade() -> None:
    op.drop_column('users', 'short_id')
