import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, DateTime, Text,
    ForeignKey, Enum, JSON
)
from sqlalchemy.orm import declarative_base, relationship
import enum

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


def gen_short_id():
    """Generate a memorable 4-character uppercase alphanumeric ID."""
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=4))


# ─── Enums ────────────────────────────────────────────────────────────────────

class RoleEnum(str, enum.Enum):
    USER = "USER"
    PARTNER = "PARTNER"
    BOTH = "BOTH"


class GenderEnum(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"


class PartnershipStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class CheckinResponseEnum(str, enum.Enum):
    YES = "YES"
    NO = "NO"


class CheckinTypeEnum(str, enum.Enum):
    NORMAL = "normal"
    LATE_RESPONSE = "late_response"
    RECOVERED_CHECKIN = "recovered_checkin"


# ─── Tables ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    short_id = Column(String(8), unique=True, nullable=True, default=gen_short_id)
    telegram_id = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False)
    role = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.USER)
    gender = Column(Enum(GenderEnum), nullable=False)
    gender_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    success_streak = Column(Integer, default=0)
    total_failures = Column(Integer, default=0)
    last_failure_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=False)  # activated after partner linked

    # relationships
    checkins = relationship("Checkin", back_populates="user", foreign_keys="Checkin.user_id")
    reflections = relationship("Reflection", back_populates="user")
    urges = relationship("Temptation", back_populates="user")
    state = relationship("UserState", back_populates="user", uselist=False)
    timers = relationship("Timer", back_populates="user")
    events = relationship("Event", back_populates="user")
    partner_checks = relationship("PartnerCheck", back_populates="user")

    partnerships_as_user = relationship(
        "Partnership", back_populates="user",
        foreign_keys="Partnership.user_id"
    )
    partnerships_as_partner = relationship(
        "Partnership", back_populates="partner",
        foreign_keys="Partnership.partner_id"
    )


class Partnership(Base):
    __tablename__ = "partnerships"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    short_id = Column(String(8), unique=True, nullable=True, default=gen_short_id)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    partner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    status = Column(Enum(PartnershipStatusEnum), default=PartnershipStatusEnum.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    accepted_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="partnerships_as_user", foreign_keys=[user_id])
    partner = relationship("User", back_populates="partnerships_as_partner", foreign_keys=[partner_id])


class Checkin(Base):
    __tablename__ = "checkins"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    response = Column(Enum(CheckinResponseEnum), nullable=True)
    responded_at = Column(DateTime, nullable=True)
    valid = Column(Boolean, default=True)
    type = Column(Enum(CheckinTypeEnum), default=CheckinTypeEnum.NORMAL)

    user = relationship("User", back_populates="checkins", foreign_keys=[user_id])


class Reflection(Base):
    __tablename__ = "reflections"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    trigger = Column(Text, nullable=False)
    failure_description = Column(Text, nullable=False)
    preventative_action = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    checkin_id = Column(String(36), ForeignKey("checkins.id"), nullable=True)

    user = relationship("User", back_populates="reflections")


class Temptation(Base):
    __tablename__ = "temptations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved = Column(Boolean, default=False)
    resolution = Column(String, nullable=True)  # 'fallen', 'still_tempted', 'not_tempted'
    followup_sent = Column(Boolean, default=False)

    user = relationship("User", back_populates="temptations")


class UserState(Base):
    __tablename__ = "user_states"

    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    current_flow = Column(String, nullable=True)   # e.g. 'signup', 'login', 'partner_link'
    pending_action = Column(String, nullable=True)  # e.g. 'PENDING_REFLECTION'
    flow_data = Column(JSON, nullable=True)         # arbitrary flow state
    expires_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="state")


class Timer(Base):
    __tablename__ = "timers"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)   # e.g. 'checkin_reminder', 'checkin_timeout', 'reflection_timeout', 'urge_followup'
    expires_at = Column(DateTime, nullable=False)
    payload = Column(JSON, nullable=True)
    fired = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="timers")


class Event(Base):
    __tablename__ = "events"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="events")


class PartnerCheck(Base):
    __tablename__ = "partner_checks"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    triggered_at = Column(DateTime, default=datetime.utcnow)
    acknowledged = Column(Boolean, default=False)

    user = relationship("User", back_populates="partner_checks")


# ─── TempSignup (for multi-step signup before user row exists) ─────────────────

class TempSignup(Base):
    """Holds partial signup data before the user row is committed."""
    __tablename__ = "temp_signups"

    telegram_id = Column(String, primary_key=True)
    step = Column(String, nullable=False, default="username")
    username = Column(String, nullable=True)
    role = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
