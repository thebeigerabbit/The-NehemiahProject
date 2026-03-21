from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.models import Urge, User
from app.services.user_service import create_timer, get_accepted_partners
from app.utils.time_utils import minutes_from_now
from app.utils.event_logger import log_event
from config.settings import URGE_FOLLOWUP_MINUTES, MAX_URGES_PER_HOUR, MIN_URGE_REASON_LENGTH
import logging

logger = logging.getLogger(__name__)


def validate_urge_reason(reason: str) -> str | None:
    """Return error string or None if valid."""
    if not reason or not reason.strip():
        return "Reason is required."
    if len(reason.strip()) < MIN_URGE_REASON_LENGTH:
        return f"Reason must be at least {MIN_URGE_REASON_LENGTH} characters."
    if len(reason.strip()) > 500:
        return "Reason must be at most 500 characters."
    return None


def count_recent_urges(db: Session, user_id: str) -> int:
    cutoff = datetime.utcnow() - timedelta(hours=1)
    return db.query(Urge).filter(
        Urge.user_id == user_id,
        Urge.created_at >= cutoff,
    ).count()


def create_urge(db: Session, user: User, reason: str) -> Urge:
    urge = Urge(
        user_id=user.id,
        reason=reason.strip(),
        created_at=datetime.utcnow(),
        resolved=False,
    )
    db.add(urge)
    db.flush()

    # Schedule 15-min follow-up timer
    create_timer(
        db, user.id, "urge_followup",
        expires_at=minutes_from_now(URGE_FOLLOWUP_MINUTES),
        payload={"urge_id": urge.id},
    )

    log_event(db, user.id, "URGE_REPORTED", {"reason": reason, "urge_id": urge.id})
    return urge


def resolve_urge(db: Session, urge_id: str, resolution: str):
    """resolution: 'fallen' | 'still_tempted' | 'not_tempted'"""
    urge = db.query(Urge).filter_by(id=urge_id).first()
    if urge:
        urge.resolved = True
        urge.resolution = resolution
        db.flush()


def get_urge(db: Session, urge_id: str) -> Urge | None:
    return db.query(Urge).filter_by(id=urge_id).first()


def parse_urge_command(text: str) -> str | None:
    """
    Parse /urge reason: <text>
    Returns the reason string or None if format invalid.
    """
    text = text.strip()
    # Remove the /urge prefix
    if text.lower().startswith("/urge"):
        rest = text[5:].strip()
    else:
        return None

    if rest.lower().startswith("reason:"):
        reason = rest[7:].strip()
        return reason if reason else None
    return None
