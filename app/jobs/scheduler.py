"""
APScheduler setup with PostgreSQL job store.
All jobs are persistent and idempotent.
"""
import logging
import random
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
import pytz

from config.settings import (
    DATABASE_URL, TIMEZONE, TIMEZONE_STR,
    CHECKIN_HOUR, CHECKIN_MINUTE,
    REMINDER_MINUTES, CHECKIN_TIMEOUT_MINUTES, REFLECTION_TIMEOUT_MINUTES,
    PARTNER_CHECK_MIN_PCT, PARTNER_CHECK_MAX_PCT,
)
from app.database import get_db
from app.services.user_service import (
    get_all_active_users, get_accepted_partners,
    create_timer, cancel_timers_of_type, get_pending_timers_of_type,
)
from app.services.checkin_service import (
    create_checkin_record, get_pending_checkin, get_todays_checkin,
)
from app.services.notification_service import (
    notify_partners_no_checkin, notify_partners_no_reflection,
    send_partner_check_notification,
)
from app.models import (
    Timer, PartnerCheck, CheckinTypeEnum, User, UserState,
    Checkin, CheckinResponseEnum,
)
from app.utils.time_utils import minutes_from_now, utc_naive, now_utc
from app.utils.event_logger import log_event

logger = logging.getLogger(__name__)

_bot = None  # set at startup


def get_scheduler() -> AsyncIOScheduler:
    jobstores = {
        "default": SQLAlchemyJobStore(url=DATABASE_URL)
    }
    executors = {
        "default": AsyncIOExecutor()
    }
    job_defaults = {
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 600,
    }
    scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone=TIMEZONE,
    )
    return scheduler


def init_scheduler(bot) -> AsyncIOScheduler:
    global _bot
    _bot = bot
    scheduler = get_scheduler()

    # ââ Daily check-in at 20:00 SAST âââââââââââââââââââââââââââââââââââââââââ
    scheduler.add_job(
        daily_checkin_job,
        trigger="cron",
        hour=CHECKIN_HOUR,
        minute=CHECKIN_MINUTE,
        timezone=TIMEZONE_STR,
        id="daily_checkin",
        replace_existing=True,
    )

    # ââ Random partner checks: daily at 20:05 âââââââââââââââââââââââââââââââââ
    scheduler.add_job(
        random_partner_check_job,
        trigger="cron",
        hour=CHECKIN_HOUR,
        minute=CHECKIN_MINUTE + 5,
        timezone=TIMEZONE_STR,
        id="random_partner_check",
        replace_existing=True,
    )

    # ââ Recovery job: every hour ââââââââââââââââââââââââââââââââââââââââââââââ
    scheduler.add_job(
        recovery_job,
        trigger="interval",
        minutes=60,
        id="recovery_job",
        replace_existing=True,
    )

    # ââ Timer processor: every minute âââââââââââââââââââââââââââââââââââââââââ
    scheduler.add_job(
        process_timers_job,
        trigger="interval",
        minutes=1,
        id="process_timers",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with all jobs.")
    return scheduler


# âââ Job: Daily Check-In ââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def daily_checkin_job():
    """Send daily check-in to all active USER/BOTH accounts."""
    global _bot
    logger.info("Running daily_checkin_job")

    with get_db() as db:
        users = get_all_active_users(db)
        now = datetime.utcnow()

        for user in users:
            try:
                # Idempotency: skip if already sent a checkin today
                existing = get_todays_checkin(db, user.id)
                if existing:
                    logger.debug(f"Skipping checkin for {user.username} â already sent today")
                    continue

                checkin = create_checkin_record(db, user, CheckinTypeEnum.NORMAL)

                # Schedule reminder (+10 min)
                reminder_expires = minutes_from_now(REMINDER_MINUTES)
                create_timer(db, user.id, "checkin_reminder", reminder_expires, {"checkin_id": checkin.id})

                # Schedule timeout (+2 hours)
                timeout_expires = minutes_from_now(CHECKIN_TIMEOUT_MINUTES)
                create_timer(db, user.id, "checkin_timeout", timeout_expires, {"checkin_id": checkin.id})

                log_event(db, user.id, "CHECKIN_SENT", {"checkin_id": checkin.id})

                await _bot.send_message(
                    chat_id=user.telegram_id,
                    text=(
                        "ð *Daily Check-In â 20:00 SAST*\n\n"
                        "Did you struggle today?\n\n"
                        "â¢ /yes â I had a failure (relapse)\n"
                        "â¢ /no â I had a clean day â"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Error sending checkin to {user.username}: {e}")


# âââ Job: Random Partner Checks âââââââââââââââââââââââââââââââââââââââââââââââ

async def random_partner_check_job():
    """Randomly select 20â30% of active users and notify their partners."""
    global _bot
    logger.info("Running random_partner_check_job")

    with get_db() as db:
        users = get_all_active_users(db)
        pct = random.uniform(PARTNER_CHECK_MIN_PCT, PARTNER_CHECK_MAX_PCT)
        selected = random.sample(users, k=max(1, int(len(users) * pct))) if users else []

        for user in selected:
            try:
                partners = get_accepted_partners(db, user.id)
                if not partners:
                    continue

                check = PartnerCheck(
                    user_id=user.id,
                    triggered_at=datetime.utcnow(),
                    acknowledged=False,
                )
                db.add(check)
                db.flush()
                log_event(db, user.id, "PARTNER_CHECK_TRIGGERED", {})

                await send_partner_check_notification(_bot, user, partners)
            except Exception as e:
                logger.error(f"Error in partner check for {user.username}: {e}")


# âââ Job: Process Timers ââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def process_timers_job():
    """Fire any due, unfired timers."""
    global _bot
    now = datetime.utcnow()

    with get_db() as db:
        due_timers = db.query(Timer).filter(
            Timer.fired == False,  # noqa
            Timer.expires_at <= now,
        ).all()

        for timer in due_timers:
            try:
                await fire_timer(db, timer)
                timer.fired = True
                db.flush()
            except Exception as e:
                logger.error(f"Error firing timer {timer.id} type={timer.type}: {e}")


async def fire_timer(db, timer: Timer):
    global _bot
    user = db.query(User).filter_by(id=timer.user_id).first()
    if not user:
        return

    ttype = timer.type
    payload = timer.payload or {}

    # ââ Checkin Reminder ââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    if ttype == "checkin_reminder":
        checkin_id = payload.get("checkin_id")
        checkin = db.query(Checkin).filter_by(id=checkin_id).first()
        if checkin and checkin.response is None:
            await _bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    "â° *Reminder: Daily Check-In*\n\n"
                    "Please respond to your check-in:\n"
                    "â¢ /yes â I had a failure\n"
                    "â¢ /no â Clean day â\n\n"
                    "You have ~110 minutes before your partners are notified."
                ),
                parse_mode="Markdown",
            )

    # ââ Checkin Timeout â notify partners âââââââââââââââââââââââââââââââââââââ
    elif ttype == "checkin_timeout":
        checkin_id = payload.get("checkin_id")
        checkin = db.query(Checkin).filter_by(id=checkin_id).first()
        if checkin and checkin.response is None:
            # Mark checkin as invalid (late)
            checkin.valid = False
            db.flush()
            partners = get_accepted_partners(db, user.id)
            log_event(db, user.id, "CHECKIN_TIMEOUT", {"checkin_id": checkin_id})
            await notify_partners_no_checkin(_bot, user, partners)
            await _bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    "â ï¸ *Check-In Timeout*\n\n"
                    "You did not respond to tonight's check-in within 2 hours.\n"
                    "Your accountability partners have been notified."
                ),
                parse_mode="Markdown",
            )

    # ââ Reflection Timeout â notify partners ââââââââââââââââââââââââââââââââââ
    elif ttype == "reflection_timeout":
        state = db.query(UserState).filter_by(user_id=user.id).first()
        if state and state.pending_action == "PENDING_REFLECTION":
            partners = get_accepted_partners(db, user.id)
            log_event(db, user.id, "REFLECTION_TIMEOUT", {})
            await notify_partners_no_reflection(_bot, user, partners)
            await _bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    "â ï¸ *Reflection Overdue*\n\n"
                    "You haven't submitted your reflection yet.\n"
                    "Your partners have been notified.\n\n"
                    "Please submit it now:\n"
                    "```\n/reflect\ntrigger: ...\nfailure: ...\nprevention: ...\n```"
                ),
                parse_mode="Markdown",
            )

    # ââ Urge Follow-Up ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    elif ttype == "urge_followup":
        urge_id = payload.get("urge_id")
        from app.handlers.urge import send_urge_followup
        await send_urge_followup(_bot, user.telegram_id, urge_id, user.username)


# âââ Job: Recovery ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def recovery_job():
    """
    Hourly recovery: detect missed checkins, expired reflections,
    and recreate missing timers. Fully idempotent.
    """
    global _bot
    logger.info("Running recovery_job")
    now = datetime.utcnow()

    with get_db() as db:
        users = get_all_active_users(db)

        for user in users:
            try:
                await _recover_user(db, user, now)
            except Exception as e:
                logger.error(f"Recovery error for {user.username}: {e}")


async def _recover_user(db, user: User, now: datetime):
    global _bot

    # ââ Detect checkin from last 26h with no response and no timeout timer ââââ
    cutoff = now - timedelta(hours=26)
    missed_checkins = db.query(Checkin).filter(
        Checkin.user_id == user.id,
        Checkin.date >= cutoff,
        Checkin.response == None,  # noqa
        Checkin.valid == True,     # noqa
        Checkin.date <= (now - timedelta(hours=2)),  # past the 2-hour window
    ).all()

    for checkin in missed_checkins:
        # Check if timeout timer already fired
        timeout_timers = db.query(Timer).filter(
            Timer.user_id == user.id,
            Timer.type == "checkin_timeout",
            Timer.payload["checkin_id"].astext == checkin.id,
        ).all()
        if all(t.fired for t in timeout_timers):
            continue  # already handled

        # Mark invalid and notify
        checkin.valid = False
        db.flush()
        partners = get_accepted_partners(db, user.id)
        log_event(db, user.id, "CHECKIN_MISSED_RECOVERED", {"checkin_id": checkin.id})
        await notify_partners_no_checkin(_bot, user, partners)

        # Send recovered checkin prompt to user
        recovered = create_checkin_record(db, user, CheckinTypeEnum.RECOVERED_CHECKIN)
        create_timer(db, user.id, "checkin_timeout",
                     minutes_from_now(CHECKIN_TIMEOUT_MINUTES),
                     {"checkin_id": recovered.id})
        try:
            await _bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    "ð *Missed Check-In Recovery*\n\n"
                    "You missed last night's check-in.\n"
                    "Your partners were notified.\n\n"
                    "Please respond now:\n"
                    "â¢ /yes â I had a failure\n"
                    "â¢ /no â Clean day"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Failed to send recovery checkin to {user.username}: {e}")

    # ââ Detect pending reflections with expired timer that wasn't re-prompted ââ
    state = db.query(UserState).filter_by(user_id=user.id).first()
    if state and state.pending_action == "PENDING_REFLECTION":
        expired_timers = db.query(Timer).filter(
            Timer.user_id == user.id,
            Timer.type == "reflection_timeout",
            Timer.fired == True,  # noqa
        ).all()
        pending_timers = db.query(Timer).filter(
            Timer.user_id == user.id,
            Timer.type == "reflection_timeout",
            Timer.fired == False,  # noqa
        ).all()

        if expired_timers and not pending_timers:
            # Re-prompt
            partners = get_accepted_partners(db, user.id)
            await notify_partners_no_reflection(_bot, user, partners)
            try:
                await _bot.send_message(
                    chat_id=user.telegram_id,
                    text=(
                        "ð *Reflection Still Pending*\n\n"
                        "You still haven't completed your reflection.\n"
                        "Your partners have been notified again.\n\n"
                        "Please submit:\n"
                        "```\n/reflect\ntrigger: ...\nfailure: ...\nprevention: ...\n```"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Failed to re-prompt reflection for {user.username}: {e}")

            # Reschedule reflection timeout
            create_timer(db, user.id, "reflection_timeout",
                         minutes_from_now(REFLECTION_TIMEOUT_MINUTES * 6), {})
