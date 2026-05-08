"""Rename urges table to temptations

Revision ID: 0004_rename_urges_to_temptations
Revises: 0003_fix_enums
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_rename_urges_to_temptations'
down_revision = '0003_fix_enums_partnership_shortid'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Rename table if old name still exists
    try:
        conn.execute(sa.text("ALTER TABLE urges RENAME TO temptations"))
    except Exception:
        pass  # Already renamed or doesn't exist


def downgrade() -> None:
    conn = op.get_bind()
    try:
        conn.execute(sa.text("ALTER TABLE temptations RENAME TO urges"))
    except Exception:
        pass
