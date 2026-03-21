from app.models import Event
from app.utils.time_utils import utc_naive
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def log_event(db, user_id: str, event_type: str, payload: dict = None):
    """Append an immutable event to the events log."""
    try:
        event = Event(
            user_id=user_id,
            type=event_type,
            payload=payload or {},
            created_at=datetime.utcnow(),
        )
        db.add(event)
        db.flush()
    except Exception as e:
        logger.error(f"Failed to log event {event_type} for user {user_id}: {e}")
