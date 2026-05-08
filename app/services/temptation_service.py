from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.models import Temptation, User
from app.services.user_service import create_timer, get_accepted_partners
from app.utils.time_utils import minutes_from_now
from app.utils.event_logger import log_event
from config.settings import URGE_FOLLOWUP_MINUTES, MAX_URGES_PER_HOUR, MIN_URGE_REASON_LENGTH
import logging

logger = logging.getLogger(__name__)


def validate_temptation_reason(reason: str) -> str | None:
    """Return error string or None if valid."""
    if not reason or not reason.strip():
        return "Reason is required."
    if len(reason.strip()) < MIN_URGE_REASON_LENGTH:
        return f"Reason must be at least {MIN_URGE_REASON_LENGTH} characters."
    if len(reason.strip()) > 500:
        return "Reason must be at most 500 characters."
    return None


def count_recent_temptations(db: Session, user_id: str) -> int:
    cutoff = datetime.utcnow() - timedelta(hours=1)
    return db.query(Temptation).filter(
        Temptation.user_id == user_id,
        Temptation.created_at >= cutoff,
    ).count()


def create_temptation(db: Session, user: User, reason: str) -> Temptation:
    temptation = Temptation(
        user_id=user.id,
        reason=reason.strip(),
        created_at=datetime.utcnow(),
        resolved=False,
    )
    db.add(temptation)
    db.flush()

    # Schedule 15-min follow-up timer
    create_timer(
        db, user.id, "temptation_followup",
        expires_at=minutes_from_now(URGE_FOLLOWUP_MINUTES),
        payload={"temptation_id": temptation.id},
    )

    log_event(db, user.id, "TEMPTATION_REPORTED", {"reason": reason, "temptation_id": temptation.id})
    return temptation


def resolve_temptation(db: Session, urge_id: str, resolution: str):
    """resolution: 'fallen' | 'still_tempted' | 'not_tempted'"""
    temptation = db.query(Temptation).filter_by(id=urge_id).first()
    if temptation:
        temptation.resolved = True
        temptation.resolution = resolution
        db.flush()


def get_temptation(db: Session, urge_id: str) -> Temptation | None:
    return db.query(Temptation).filter_by(id=urge_id).first()


def parse_temptation_command(text: str) -> str | None:
    """
    Parse /tempted reason: <text>
    Returns the reason string or None if format invalid.
    """
    text = text.strip()
    # Remove the /urge prefix
    if text.lower().startswith("/tempted"):
        rest = text[5:].strip()
    else:
        return None

    if rest.lower().startswith("reason:"):
        reason = rest[7:].strip()
        return reason if reason else None
    return None
