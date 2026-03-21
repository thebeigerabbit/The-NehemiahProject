from datetime import datetime, timedelta
import pytz
from config.settings import TIMEZONE

def now_local() -> datetime:
    """Return current time in Africa/Johannesburg, timezone-aware."""
    return datetime.now(TIMEZONE)

def now_utc() -> datetime:
    """Return current UTC time, timezone-aware."""
    return datetime.now(pytz.utc)

def to_local(dt: datetime) -> datetime:
    """Convert any datetime to local timezone."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(TIMEZONE)

def to_utc(dt: datetime) -> datetime:
    """Convert local datetime to UTC for storage."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = TIMEZONE.localize(dt)
    return dt.astimezone(pytz.utc)

def utc_naive(dt: datetime) -> datetime:
    """Strip timezone info, return UTC naive datetime for SQLAlchemy storage."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(pytz.utc).replace(tzinfo=None)

def local_to_utc_naive(dt: datetime) -> datetime:
    """Take a local (SAST) datetime, return naive UTC for DB storage."""
    return utc_naive(to_utc(dt))

def utc_naive_to_local(dt: datetime) -> datetime:
    """Take a naive UTC datetime from DB, return aware local datetime."""
    if dt is None:
        return None
    return pytz.utc.localize(dt).astimezone(TIMEZONE)

def minutes_from_now(minutes: int) -> datetime:
    """Return a naive UTC datetime N minutes from now."""
    return utc_naive(now_utc() + timedelta(minutes=minutes))

def format_local(dt: datetime) -> str:
    """Format datetime in local timezone for display."""
    if dt is None:
        return "Never"
    local = utc_naive_to_local(dt) if dt.tzinfo is None else to_local(dt)
    return local.strftime("%Y-%m-%d %H:%M SAST")
