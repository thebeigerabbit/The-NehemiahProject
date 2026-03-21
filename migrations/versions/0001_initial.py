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


def upgrade() -> None:
    conn = op.get_bind()

    # Create enums using raw SQL with IF NOT EXISTS — fully idempotent
    conn.execute(sa.text("CREATE TYPE IF NOT EXISTS roleenum AS ENUM ('USER', 'PARTNER', 'BOTH')"))
    conn.execute(sa.text("CREATE TYPE IF NOT EXISTS genderenum AS ENUM ('MALE', 'FEMALE')"))
    conn.execute(sa.text("CREATE TYPE IF NOT EXISTS partnershipstatusenum AS ENUM ('PENDING', 'ACCEPTED', 'REJECTED')"))
    conn.execute(sa.text("CREATE TYPE IF NOT EXISTS checkinresponseenum AS ENUM ('YES', 'NO')"))
    conn.execute(sa.text("CREATE TYPE IF NOT EXISTS checkintypeenum AS ENUM ('normal', 'late_response', 'recovered_checkin')"))

    # users
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS users (
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
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_users_telegram_id ON users (telegram_id)"))

    # temp_signups
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS temp_signups (
            telegram_id VARCHAR PRIMARY KEY,
            step VARCHAR NOT NULL DEFAULT 'username',
            username VARCHAR,
            role VARCHAR,
            gender VARCHAR,
            created_at TIMESTAMP
        )
    """))

    # partnerships
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS partnerships (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            partner_id VARCHAR NOT NULL REFERENCES users(id),
            status partnershipstatusenum DEFAULT 'PENDING',
            created_at TIMESTAMP,
            accepted_at TIMESTAMP
        )
    """))

    # checkins
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS checkins (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            date TIMESTAMP NOT NULL,
            response checkinresponseenum,
            responded_at TIMESTAMP,
            valid BOOLEAN DEFAULT TRUE,
            type checkintypeenum DEFAULT 'normal'
        )
    """))

    # reflections
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS reflections (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            trigger TEXT NOT NULL,
            failure_description TEXT NOT NULL,
            preventative_action TEXT NOT NULL,
            created_at TIMESTAMP,
            checkin_id VARCHAR REFERENCES checkins(id)
        )
    """))

    # urges
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS urges (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            reason TEXT NOT NULL,
            created_at TIMESTAMP,
            resolved BOOLEAN DEFAULT FALSE,
            resolution VARCHAR,
            followup_sent BOOLEAN DEFAULT FALSE
        )
    """))

    # user_states
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS user_states (
            user_id VARCHAR PRIMARY KEY REFERENCES users(id),
            current_flow VARCHAR,
            pending_action VARCHAR,
            flow_data JSONB,
            expires_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """))

    # timers
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS timers (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            type VARCHAR NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            payload JSONB,
            fired BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP
        )
    """))

    # events
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS events (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            type VARCHAR NOT NULL,
            payload JSONB,
            created_at TIMESTAMP
        )
    """))

    # partner_checks
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS partner_checks (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            triggered_at TIMESTAMP,
            acknowledged BOOLEAN DEFAULT FALSE
        )
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS partner_checks"))
    conn.execute(sa.text("DROP TABLE IF EXISTS events"))
    conn.execute(sa.text("DROP TABLE IF EXISTS timers"))
    conn.execute(sa.text("DROP TABLE IF EXISTS user_states"))
    conn.execute(sa.text("DROP TABLE IF EXISTS urges"))
    conn.execute(sa.text("DROP TABLE IF EXISTS reflections"))
    conn.execute(sa.text("DROP TABLE IF EXISTS checkins"))
    conn.execute(sa.text("DROP TABLE IF EXISTS partnerships"))
    conn.execute(sa.text("DROP TABLE IF EXISTS temp_signups"))
    conn.execute(sa.text("DROP TABLE IF EXISTS users"))
    conn.execute(sa.text("DROP TYPE IF EXISTS checkintypeenum"))
    conn.execute(sa.text("DROP TYPE IF EXISTS checkinresponseenum"))
    conn.execute(sa.text("DROP TYPE IF EXISTS partnershipstatusenum"))
    conn.execute(sa.text("DROP TYPE IF EXISTS genderenum"))
    conn.execute(sa.text("DROP TYPE IF EXISTS roleenum"))
