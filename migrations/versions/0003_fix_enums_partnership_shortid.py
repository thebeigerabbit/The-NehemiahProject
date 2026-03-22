"""Fix checkin enum case and add partnership short_id

Revision ID: 0003_fix_enums
Revises: 0002_add_short_id
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa
import random
import string


revision = '0003_fix_enums'
down_revision = '0002_add_short_id'
branch_labels = None
depends_on = None


def gen_short_id():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=4))


def upgrade() -> None:
    conn = op.get_bind()

    # Fix checkintypeenum — rename lowercase values to uppercase
    # PostgreSQL requires renaming enum values one at a time
    try:
        conn.execute(sa.text(
            "ALTER TYPE checkintypeenum RENAME VALUE 'normal' TO 'NORMAL'"
        ))
    except Exception:
        pass

    try:
        conn.execute(sa.text(
            "ALTER TYPE checkintypeenum RENAME VALUE 'late_response' TO 'LATE_RESPONSE'"
        ))
    except Exception:
        pass

    try:
        conn.execute(sa.text(
            "ALTER TYPE checkintypeenum RENAME VALUE 'recovered_checkin' TO 'RECOVERED_CHECKIN'"
        ))
    except Exception:
        pass

    # Add short_id to partnerships
    try:
        conn.execute(sa.text(
            "ALTER TABLE partnerships ADD COLUMN short_id VARCHAR(8) UNIQUE"
        ))
    except Exception:
        pass

    # Backfill short_id for existing partnerships
    result = conn.execute(sa.text("SELECT id FROM partnerships WHERE short_id IS NULL"))
    rows = result.fetchall()
    for row in rows:
        for _ in range(20):
            sid = gen_short_id()
            try:
                conn.execute(sa.text(
                    "UPDATE partnerships SET short_id = :sid WHERE id = :uid"
                ), {"sid": sid, "uid": row[0]})
                break
            except Exception:
                continue


def downgrade() -> None:
    pass
