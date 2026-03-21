"""Initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def create_type_if_not_exists(conn, name: str, sql: str):
    """Create a PostgreSQL enum type only if it doesn't already exist."""
    exists = conn.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :name"),
        {"name": name}
    ).fetchone()
    if not exists:
        conn.execute(sa.text(sql))


def create_table_if_not_exists(conn, name: str, sql: str):
    """Create a table only if it doesn't already exist."""
    exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = :name"),
        {"name": name}
    ).fetchone()
    if not exists:
        conn.execute(sa.text(sql))


def create_index_if_not_exists(conn, index_name: str, sql: str):
    """Create an index only if it doesn't already exist."""
    exists = conn.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
        {"name": index_name}
    ).fetchone()
    if not exists:
        conn.execute(sa.text(sql))


def upgrade() -> None:
    conn = op.get_bind()

    # Enum types
    create_type_if_not_exists(conn, "roleenum",
        "CREATE TYPE roleenum AS ENUM ('USER', 'PARTNER', 'BOTH')")
    create_type_if_not_exists(conn, "genderenum",
        "CREATE TYPE genderenum AS ENUM ('MALE', 'FEMALE')")
    create_type_if_not_exists(conn, "partnershipstatusenum",
        "CREATE TYPE partnershipstatusenum AS ENUM ('PENDING', 'ACCEPTED', 'REJECTED')")
    create_type_if_not_exists(conn, "checkinresponseenum",
        "CREATE TYPE checkinresponseenum AS ENUM ('YES', 'NO')")
    create_type_if_not_exists(conn, "checkintypeenum",
        "CREATE TYPE checkintypeenum AS ENUM ('normal', 'late_response', 'recovered_checkin')")

    # users
    create_table_if_not_exists(conn, "users", """
        CREATE TABLE users (
            id VARCHAR PRIMARY KEY,
            telegram_id VARCHAR UNIQUE NOT NULL,
            username VARCHAR UNIQUE NOT NULL,
            role roleenum NOT NULL,
            gender genderenum NOT NULL,
            gender_verified BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP,
            success_streak INTEGER DEFAULT 0,
            total_failures INTEGER DEFAULT 0,
            last_failure_at TIMESTAMP,
            is_active BOOLEAN DEFAULT FALSE
        )
    """)
    create_index_if_not_exists(conn, "ix_users_telegram_id",
        "CREATE INDEX ix_users_telegram_id ON users (telegram_id)")

    # temp_signups
    create_table_if_not_exists(conn, "temp_signups", """
        CREATE TABLE temp_signups (
            telegram_id VARCHAR PRIMARY KEY,
            step VARCHAR NOT NULL DEFAULT 'username',
            username VARCHAR,
            role VARCHAR,
            gender VARCHAR,
            created_at TIMESTAMP
        )
    """)

    # partnerships
    create_table_if_not_exists(conn, "partnerships", """
        CREATE TABLE partnerships (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            partner_id VARCHAR NOT NULL REFERENCES users(id),
            status partnershipstatusenum DEFAULT 'PENDING',
            created_at TIMESTAMP,
            accepted_at TIMESTAMP
        )
    """)

    # checkins
    create_table_if_not_exists(conn, "checkins", """
        CREATE TABLE checkins (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            date TIMESTAMP NOT NULL,
            response checkinresponseenum,
            responded_at TIMESTAMP,
            valid BOOLEAN DEFAULT TRUE,
            type checkintypeenum DEFAULT 'normal'
        )
    """)

    # reflections
    create_table_if_not_exists(conn, "reflections", """
        CREATE TABLE reflections (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            trigger TEXT NOT NULL,
            failure_description TEXT NOT NULL,
            preventative_action TEXT NOT NULL,
            created_at TIMESTAMP,
            checkin_id VARCHAR REFERENCES checkins(id)
        )
    """)

    # urges
    create_table_if_not_exists(conn, "urges", """
        CREATE TABLE urges (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            reason TEXT NOT NULL,
            created_at TIMESTAMP,
            resolved BOOLEAN DEFAULT FALSE,
            resolution VARCHAR,
            followup_sent BOOLEAN DEFAULT FALSE
        )
    """)

    # user_states
    create_table_if_not_exists(conn, "user_states", """
        CREATE TABLE user_states (
            user_id VARCHAR PRIMARY KEY REFERENCES users(id),
            current_flow VARCHAR,
            pending_action VARCHAR,
            flow_data JSONB,
            expires_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)

    # timers
    create_table_if_not_exists(conn, "timers", """
        CREATE TABLE timers (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            type VARCHAR NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            payload JSONB,
            fired BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP
        )
    """)

    # events
    create_table_if_not_exists(conn, "events", """
        CREATE TABLE events (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            type VARCHAR NOT NULL,
            payload JSONB,
            created_at TIMESTAMP
        )
    """)

    # partner_checks
    create_table_if_not_exists(conn, "partner_checks", """
        CREATE TABLE partner_checks (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            triggered_at TIMESTAMP,
            acknowledged BOOLEAN DEFAULT FALSE
        )
    """)


def downgrade() -> None:
    conn = op.get_bind()
    for tbl in ["partner_checks", "events", "timers", "user_states",
                "urges", "reflections", "checkins", "partnerships",
                "temp_signups", "users"]:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {tbl}"))
    for typ in ["checkintypeenum", "checkinresponseenum",
                "partnershipstatusenum", "genderenum", "roleenum"]:
        conn.execute(sa.text(f"DROP TYPE IF EXISTS {typ}"))
