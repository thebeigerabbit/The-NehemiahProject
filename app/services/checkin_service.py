from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.models import (
    Checkin, CheckinResponseEnum, CheckinTypeEnum, User, Reflection
)
from app.services.user_service import (
    get_todays_checkin, get_pending_checkin, get_accepted_partners,
    create_timer, cancel_timers_of_type, set_user_state, clear_user_state,
    user_has_pending_reflection
)
from app.utils.time_utils import minutes_from_now, utc_naive
from app.utils.event_logger import log_event
from config.settings import (
    REMINDER_MINUTES, CHECKIN_TIMEOUT_MINUTES, REFLECTION_TIMEOUT_MINUTES
)
import logging

logger = logging.getLogger(__name__)


def create_checkin_record(db: Session, user: User, checkin_type: CheckinTypeEnum = CheckinTypeEnum.NORMAL) -> Checkin:
    c = Checkin(
        user_id=user.id,
        date=datetime.utcnow(),
        response=None,
        valid=True,
        type=checkin_type,
    )
    db.add(c)
    db.flush()
    return c


def process_yes_response(db: Session, user: User, checkin: Checkin) -> dict:
    """Handle a YES (failure) response. Returns info dict for notifications."""
    checkin.response = CheckinResponseEnum.YES
    checkin.responded_at = datetime.utcnow()
    checkin.valid = True

    # Update user stats
    user.success_streak = 0
    user.total_failures = (user.total_failures or 0) + 1
    user.last_failure_at = datetime.utcnow()

    # Set pending reflection
    reflection_expires = minutes_from_now(REFLECTION_TIMEOUT_MINUTES)
    set_user_state(
        db, user.id,
        pending_action="PENDING_REFLECTION",
        flow_data={"checkin_id": checkin.id},
        expires_at=reflection_expires,
    )

    # Cancel any checkin timers
    cancel_timers_of_type(db, user.id, "checkin_reminder")
    cancel_timers_of_type(db, user.id, "checkin_timeout")

    # Create reflection timeout timer
    create_timer(
        db, user.id, "reflection_timeout",
        expires_at=reflection_expires,
        payload={"checkin_id": checkin.id},
    )

    log_event(db, user.id, "CHECKIN_YES", {"checkin_id": checkin.id})

    partners = get_accepted_partners(db, user.id)
    return {"partners": partners, "checkin": checkin}


def process_no_response(db: Session, user: User, checkin: Checkin) -> dict:
    """Handle a NO (success) response."""
    checkin.response = CheckinResponseEnum.NO
    checkin.responded_at = datetime.utcnow()
    checkin.valid = True

    user.success_streak = (user.success_streak or 0) + 1

    cancel_timers_of_type(db, user.id, "checkin_reminder")
    cancel_timers_of_type(db, user.id, "checkin_timeout")

    log_event(db, user.id, "CHECKIN_NO", {"checkin_id": checkin.id})
    return {"checkin": checkin}


def save_reflection(db: Session, user: User, trigger: str, failure: str, prevention: str) -> Reflection:
    state = db.query(__import__('app.models', fromlist=['UserState']).UserState).filter_by(user_id=user.id).first()
    checkin_id = (state.flow_data or {}).get("checkin_id") if state else None

    r = Reflection(
        user_id=user.id,
        trigger=trigger,
        failure_description=failure,
        preventative_action=prevention,
        checkin_id=checkin_id,
        created_at=datetime.utcnow(),
    )
    db.add(r)

    # Cancel reflection timeout timer
    cancel_timers_of_type(db, user.id, "reflection_timeout")
    clear_user_state(db, user.id)

    log_event(db, user.id, "REFLECTION_SAVED", {"checkin_id": checkin_id})
    db.flush()
    return r


def validate_reflection_fields(trigger: str, failure: str, prevention: str) -> list[str]:
    """Return list of validation errors, empty if valid."""
    from config.settings import MIN_REFLECTION_LENGTH, MAX_TEXT_LENGTH
    errors = []
    fields = [("trigger", trigger), ("failure", failure), ("prevention", prevention)]
    for name, value in fields:
        if not value or not value.strip():
            errors.append(f"• `{name}` field is missing or empty.")
        elif len(value.strip()) < MIN_REFLECTION_LENGTH:
            errors.append(f"• `{name}` is too short (min {MIN_REFLECTION_LENGTH} chars).")
        elif len(value.strip()) > MAX_TEXT_LENGTH:
            errors.append(f"• `{name}` is too long (max {MAX_TEXT_LENGTH} chars).")
    return errors


def parse_reflect_command(text: str) -> dict | None:
    """
    Parse multiline /reflect command. Expected format:
    /reflect
    trigger: ...
    failure: ...
    prevention: ...
    Returns dict with keys or None if parse fails.
    """
    lines = text.strip().splitlines()
    result = {}
    current_key = None
    current_val = []

    key_map = {
        "trigger": "trigger",
        "failure": "failure",
        "prevention": "prevention",
        "prevent": "prevention",
    }

    for line in lines:
        if line.strip().lower().startswith("/reflect"):
            continue
        found = False
        for prefix, key in key_map.items():
            if line.lower().startswith(f"{prefix}:"):
                if current_key:
                    result[current_key] = " ".join(current_val).strip()
                current_key = key
                current_val = [line[len(prefix) + 1:].strip()]
                found = True
                break
        if not found and current_key:
            current_val.append(line.strip())

    if current_key:
        result[current_key] = " ".join(current_val).strip()

    # Require all three fields
    if all(k in result for k in ("trigger", "failure", "prevention")):
        return result
    return None


def check_anomaly(db: Session, user: User) -> bool:
    """Return True if anomaly detected: high NO streak + recent urges."""
    from app.models import Urge
    from config.settings import ANOMALY_NO_STREAK_THRESHOLD
    if (user.success_streak or 0) >= ANOMALY_NO_STREAK_THRESHOLD:
        recent_urge_cutoff = datetime.utcnow() - timedelta(days=7)
        urge_count = db.query(Urge).filter(
            Urge.user_id == user.id,
            Urge.created_at >= recent_urge_cutoff,
        ).count()
        if urge_count > 0:
            return True
    return False


def get_stats(db: Session, user: User) -> dict:
    """Compute full report stats for a user."""
    from app.models import Checkin, Urge, Reflection

    days_active = (datetime.utcnow() - user.created_at).days + 1

    total_checkins = db.query(Checkin).filter(
        Checkin.user_id == user.id,
        Checkin.response != None  # noqa
    ).count()

    total_failures = user.total_failures or 0
    total_successes = total_checkins - total_failures
    success_rate = (total_successes / total_checkins * 100) if total_checkins > 0 else 0

    missed_checkins = db.query(Checkin).filter(
        Checkin.user_id == user.id,
        Checkin.response == None,  # noqa
        Checkin.valid == False  # noqa
    ).count()

    urge_count = db.query(Urge).filter(Urge.user_id == user.id).count()

    total_yes = db.query(Checkin).filter(
        Checkin.user_id == user.id,
        Checkin.response == CheckinResponseEnum.YES,
    ).count()
    reflection_count = db.query(Reflection).filter(Reflection.user_id == user.id).count()
    reflection_compliance = (reflection_count / total_yes * 100) if total_yes > 0 else 100

    return {
        "days_active": days_active,
        "streak": user.success_streak or 0,
        "total_failures": total_failures,
        "last_failure_at": user.last_failure_at,
        "success_rate": round(success_rate, 1),
        "urge_count": urge_count,
        "reflection_compliance": round(reflection_compliance, 1),
        "missed_checkins": missed_checkins,
        "total_checkins": total_checkins,
    }
