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
    # Enums
    role_enum = postgresql.ENUM("USER", "PARTNER", "BOTH", name="roleenum")
    gender_enum = postgresql.ENUM("MALE", "FEMALE", name="genderenum")
    partnership_status_enum = postgresql.ENUM("PENDING", "ACCEPTED", "REJECTED", name="partnershipstatusenum")
    checkin_response_enum = postgresql.ENUM("YES", "NO", name="checkinresponseenum")
    checkin_type_enum = postgresql.ENUM("normal", "late_response", "recovered_checkin", name="checkintypeenum")

    role_enum.create(op.get_bind(), checkfirst=True)
    gender_enum.create(op.get_bind(), checkfirst=True)
    partnership_status_enum.create(op.get_bind(), checkfirst=True)
    checkin_response_enum.create(op.get_bind(), checkfirst=True)
    checkin_type_enum.create(op.get_bind(), checkfirst=True)

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("telegram_id", sa.String(), unique=True, nullable=False),
        sa.Column("username", sa.String(), unique=True, nullable=False),
        sa.Column("role", sa.Enum("USER", "PARTNER", "BOTH", name="roleenum"), nullable=False),
        sa.Column("gender", sa.Enum("MALE", "FEMALE", name="genderenum"), nullable=False),
        sa.Column("gender_verified", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("success_streak", sa.Integer(), default=0),
        sa.Column("total_failures", sa.Integer(), default=0),
        sa.Column("last_failure_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    # temp_signups
    op.create_table(
        "temp_signups",
        sa.Column("telegram_id", sa.String(), primary_key=True),
        sa.Column("step", sa.String(), nullable=False, default="username"),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("gender", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # partnerships
    op.create_table(
        "partnerships",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("partner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "ACCEPTED", "REJECTED", name="partnershipstatusenum"), default="PENDING"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
    )

    # checkins
    op.create_table(
        "checkins",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("response", sa.Enum("YES", "NO", name="checkinresponseenum"), nullable=True),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.Column("valid", sa.Boolean(), default=True),
        sa.Column("type", sa.Enum("normal", "late_response", "recovered_checkin", name="checkintypeenum"), default="normal"),
    )

    # reflections
    op.create_table(
        "reflections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("failure_description", sa.Text(), nullable=False),
        sa.Column("preventative_action", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("checkin_id", sa.String(), sa.ForeignKey("checkins.id"), nullable=True),
    )

    # urges
    op.create_table(
        "urges",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("resolved", sa.Boolean(), default=False),
        sa.Column("resolution", sa.String(), nullable=True),
        sa.Column("followup_sent", sa.Boolean(), default=False),
    )

    # user_states
    op.create_table(
        "user_states",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("current_flow", sa.String(), nullable=True),
        sa.Column("pending_action", sa.String(), nullable=True),
        sa.Column("flow_data", postgresql.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    # timers
    op.create_table(
        "timers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("payload", postgresql.JSON(), nullable=True),
        sa.Column("fired", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # events
    op.create_table(
        "events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # partner_checks
    op.create_table(
        "partner_checks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("triggered_at", sa.DateTime(), nullable=True),
        sa.Column("acknowledged", sa.Boolean(), default=False),
    )


def downgrade() -> None:
    op.drop_table("partner_checks")
    op.drop_table("events")
    op.drop_table("timers")
    op.drop_table("user_states")
    op.drop_table("urges")
    op.drop_table("reflections")
    op.drop_table("checkins")
    op.drop_table("partnerships")
    op.drop_table("temp_signups")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS checkintypeenum")
    op.execute("DROP TYPE IF EXISTS checkinresponseenum")
    op.execute("DROP TYPE IF EXISTS partnershipstatusenum")
    op.execute("DROP TYPE IF EXISTS genderenum")
    op.execute("DROP TYPE IF EXISTS roleenum")
