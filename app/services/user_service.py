from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from app.models import (
    User, TempSignup, UserState, Partnership, PartnershipStatusEnum,
    RoleEnum, GenderEnum, Timer, Checkin, CheckinResponseEnum, CheckinTypeEnum
)
from app.utils.time_utils import utc_naive, now_utc
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


# ─── TempSignup helpers ───────────────────────────────────────────────────────

def get_temp_signup(db: Session, telegram_id: str) -> TempSignup | None:
    return db.query(TempSignup).filter_by(telegram_id=str(telegram_id)).first()


def upsert_temp_signup(db: Session, telegram_id: str, **kwargs) -> TempSignup:
    ts = get_temp_signup(db, telegram_id)
    if not ts:
        ts = TempSignup(telegram_id=str(telegram_id))
        db.add(ts)
    for k, v in kwargs.items():
        setattr(ts, k, v)
    db.flush()
    return ts


def delete_temp_signup(db: Session, telegram_id: str):
    db.query(TempSignup).filter_by(telegram_id=str(telegram_id)).delete()
    db.flush()


# ─── User helpers ─────────────────────────────────────────────────────────────

def get_user_by_telegram_id(db: Session, telegram_id: str) -> User | None:
    return db.query(User).filter_by(telegram_id=str(telegram_id)).first()


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(
        func.lower(User.username) == func.lower(username)
    ).first()


def get_user_by_id(db: Session, user_id: str) -> User | None:
    return db.query(User).filter(User.id == str(user_id)).first()


def username_exists(db: Session, username: str) -> bool:
    return get_user_by_username(db, username) is not None


def create_user(
    db: Session,
    telegram_id: str,
    username: str,
    role: str,
    gender: str,
) -> User:
    user = User(
        telegram_id=str(telegram_id),
        username=username,
        role=RoleEnum(role),
        gender=GenderEnum(gender),
        gender_verified=False,
        created_at=datetime.utcnow(),
        success_streak=0,
        total_failures=0,
        is_active=False,
    )
    db.add(user)
    db.flush()
    # Create empty state
    state = UserState(user_id=user.id, current_flow=None, pending_action=None)
    db.add(state)
    db.flush()
    return user


def activate_user(db: Session, user: User):
    # Use raw SQL to avoid SQLAlchemy casting VARCHAR id as UUID type
    from sqlalchemy import text
    db.execute(text("UPDATE users SET is_active = true WHERE id = :uid"), {"uid": str(user.id)})
    db.flush()
    user.is_active = True  # keep in-memory object in sync


# ─── UserState helpers ────────────────────────────────────────────────────────

def get_user_state(db: Session, user_id: str) -> UserState | None:
    return db.query(UserState).filter(UserState.user_id == str(user_id)).first()


def set_user_state(
    db: Session,
    user_id: str,
    current_flow: str = None,
    pending_action: str = None,
    flow_data: dict = None,
    expires_at: datetime = None,
):
    state = get_user_state(db, user_id)
    if not state:
        state = UserState(user_id=user_id)
        db.add(state)
    state.current_flow = current_flow
    state.pending_action = pending_action
    state.flow_data = flow_data or {}
    state.expires_at = expires_at
    state.updated_at = datetime.utcnow()
    db.flush()
    return state


def clear_user_state(db: Session, user_id: str):
    set_user_state(db, user_id)


def user_has_pending_reflection(db: Session, user_id: str) -> bool:
    state = get_user_state(db, user_id)
    return state is not None and state.pending_action == "PENDING_REFLECTION"


# ─── Partnership helpers ──────────────────────────────────────────────────────

def get_partnership(db: Session, user_id: str, partner_id: str) -> Partnership | None:
    return db.query(Partnership).filter(
        and_(Partnership.user_id == user_id, Partnership.partner_id == partner_id)
    ).first()


def get_accepted_partners(db: Session, user_id: str) -> list[User]:
    """Return all users who are accepted partners for the given user_id (in either direction)."""
    accepted = db.query(Partnership).filter(
        Partnership.status == PartnershipStatusEnum.ACCEPTED,
        (Partnership.user_id == user_id) | (Partnership.partner_id == user_id)
    ).all()
    partners = []
    for p in accepted:
        pid = p.partner_id if p.user_id == user_id else p.user_id
        partner_user = get_user_by_id(db, pid)
        if partner_user:
            partners.append(partner_user)
    return partners


def create_partnership_request(db: Session, user_id: str, partner_id: str) -> Partnership:
    p = Partnership(
        user_id=user_id,
        partner_id=partner_id,
        status=PartnershipStatusEnum.PENDING,
    )
    db.add(p)
    db.flush()
    return p


def accept_partnership(db: Session, partnership: Partnership):
    partnership.status = PartnershipStatusEnum.ACCEPTED
    partnership.accepted_at = datetime.utcnow()
    db.flush()


def reject_partnership(db: Session, partnership: Partnership):
    partnership.status = PartnershipStatusEnum.REJECTED
    db.flush()


def count_accepted_partners(db: Session, user_id: str) -> int:
    return db.query(Partnership).filter(
        Partnership.status == PartnershipStatusEnum.ACCEPTED,
        (Partnership.user_id == user_id) | (Partnership.partner_id == user_id)
    ).count()


# ─── Checkin helpers ──────────────────────────────────────────────────────────

def get_todays_checkin(db: Session, user_id: str) -> Checkin | None:
    """Return today's NORMAL check-in for the user (calendar day in SAST).
    
    Uses calendar day boundaries rather than a rolling 24-hour window so that
    a RECOVERED_CHECKIN created in the morning never blocks the same evening's
    regular check-in.
    """
    import pytz
    tz = pytz.timezone("Africa/Johannesburg")
    now_local = datetime.now(tz)
    # Start of today in SAST, converted to UTC naive for DB comparison
    start_of_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_local.astimezone(pytz.utc).replace(tzinfo=None)

    return db.query(Checkin).filter(
        Checkin.user_id == user_id,
        Checkin.date >= start_of_day_utc,
        Checkin.type == CheckinTypeEnum.NORMAL,
    ).order_by(Checkin.date.desc()).first()


def get_pending_checkin(db: Session, user_id: str) -> Checkin | None:
    """Return a checkin that has been sent but not responded to (any type, calendar day in SAST)."""
    import pytz
    tz = pytz.timezone("Africa/Johannesburg")
    now_local = datetime.now(tz)
    start_of_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_local.astimezone(pytz.utc).replace(tzinfo=None)

    return db.query(Checkin).filter(
        Checkin.user_id == user_id,
        Checkin.date >= start_of_day_utc,
        Checkin.response == None,  # noqa
    ).order_by(Checkin.date.desc()).first()


# ─── Timer helpers ────────────────────────────────────────────────────────────

def create_timer(db: Session, user_id: str, timer_type: str, expires_at: datetime, payload: dict = None) -> Timer:
    t = Timer(
        user_id=user_id,
        type=timer_type,
        expires_at=expires_at,
        payload=payload or {},
        fired=False,
    )
    db.add(t)
    db.flush()
    return t


def mark_timer_fired(db: Session, timer_id: str):
    t = db.query(Timer).filter_by(id=timer_id).first()
    if t:
        t.fired = True
        db.flush()


def get_pending_timers_of_type(db: Session, user_id: str, timer_type: str) -> list[Timer]:
    return db.query(Timer).filter(
        Timer.user_id == user_id,
        Timer.type == timer_type,
        Timer.fired == False,  # noqa
    ).all()


def cancel_timers_of_type(db: Session, user_id: str, timer_type: str):
    db.query(Timer).filter(
        Timer.user_id == user_id,
        Timer.type == timer_type,
        Timer.fired == False,  # noqa
    ).update({"fired": True})
    db.flush()


# ─── Active users for check-in ────────────────────────────────────────────────

def get_all_active_users(db: Session) -> list[User]:
    return db.query(User).filter(
        User.is_active == True,  # noqa
        User.role.in_([RoleEnum.USER, RoleEnum.BOTH])
    ).all()


def get_all_users(db: Session) -> list[User]:
    return db.query(User).filter(User.is_active == True).all()  # noqa
