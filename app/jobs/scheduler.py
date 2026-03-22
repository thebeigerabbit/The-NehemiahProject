"""
APScheduler setup with PostgreSQL job store.
All jobs are persistent and idempotent.
"""
import logging
from html import escape as h
from telegram.constants import ParseMode
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
    Checkin, CheckinResponseEnum, Urge,
)
from app.utils.time_utils import minutes_from_now, utc_naive, now_utc
from app.utils.event_logger import log_event

logger = logging.getLogger(__name__)

_bot = None  # set at startup
_scheduler = None  # set at startup


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
    global _bot, _scheduler
    _bot = bot
    scheduler = get_scheduler()
    _scheduler = scheduler

    #  Daily check-in at 20:00 SAST 
    scheduler.add_job(
        daily_checkin_job,
        trigger="cron",
        hour=CHECKIN_HOUR,
        minute=CHECKIN_MINUTE,
        timezone=TIMEZONE_STR,
        id="daily_checkin",
        replace_existing=True,
    )

    #  Random partner checks: daily at 20:05 
    scheduler.add_job(
        random_partner_check_job,
        trigger="cron",
        hour=CHECKIN_HOUR,
        minute=CHECKIN_MINUTE + 5,
        timezone=TIMEZONE_STR,
        id="random_partner_check",
        replace_existing=True,
    )

    #  Recovery job: every hour 
    scheduler.add_job(
        recovery_job,
        trigger="interval",
        minutes=60,
        id="recovery_job",
        replace_existing=True,
    )

    #  Timer processor: every minute 
    scheduler.add_job(
        process_timers_job,
        trigger="interval",
        minutes=1,
        id="process_timers",
        replace_existing=True,
    )

    #  Urge pattern analysis: daily at 12:00 SAST 
    scheduler.add_job(
        urge_pattern_nudge_job,
        trigger="cron",
        hour=12,
        minute=0,
        timezone=TIMEZONE_STR,
        id="urge_pattern_nudge",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with all jobs.")
    return scheduler


#  Job: Daily Check-In 

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
                    logger.debug(f"Skipping checkin for {user.username} — already sent today")
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
                        " Daily Check-In — 20:00 SAST\n\n"
                        "Did you struggle today?\n\n"
                        "• /yes — I had a failure (relapse)\n"
                        "• /no — I had a clean day "
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logger.error(f"Error sending checkin to {user.username}: {e}")


#  Job: Random Partner Checks 

async def random_partner_check_job():
    """Randomly select 20–30% of active users and notify their partners."""
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


#  Job: Process Timers 

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

    #  Checkin Reminder 
    if ttype == "checkin_reminder":
        checkin_id = payload.get("checkin_id")
        checkin = db.query(Checkin).filter_by(id=checkin_id).first()
        if checkin and checkin.response is None:
            await _bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    "⏰ Reminder: Daily Check-In\n\n"
                    "Please respond to your check-in:\n"
                    "• /yes — I had a failure\n"
                    "• /no — Clean day \n\n"
                    "You have ~110 minutes before your partners are notified."
                ),
                parse_mode=ParseMode.HTML,
            )

    #  Checkin Timeout → notify partners 
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
                    " Check-In Timeout\n\n"
                    "You did not respond to tonight's check-in within 2 hours.\n"
                    "Your accountability partners have been notified."
                ),
                parse_mode=ParseMode.HTML,
            )

    #  Reflection Timeout → notify partners 
    elif ttype == "reflection_timeout":
        state = db.query(UserState).filter_by(user_id=user.id).first()
        if state and state.pending_action == "PENDING_REFLECTION":
            partners = get_accepted_partners(db, user.id)
            log_event(db, user.id, "REFLECTION_TIMEOUT", {})
            await notify_partners_no_reflection(_bot, user, partners)
            await _bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    " Reflection Overdue\n\n"
                    "You haven't submitted your reflection yet.\n"
                    "Your partners have been notified.\n\n"
                    "Please submit it now:\n"
                    "```\n/reflect\ntrigger: ...\nfailure: ...\nprevention: ...\n```"
                ),
                parse_mode=ParseMode.HTML,
            )

    #  Urge Follow-Up 
    elif ttype == "urge_followup":
        urge_id = payload.get("urge_id")
        from app.handlers.urge import send_urge_followup
        await send_urge_followup(_bot, user.telegram_id, urge_id, user.username)


#  Job: Recovery 

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

    #  Detect checkin from last 26h with no response and no timeout timer 
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
                    " Missed Check-In Recovery\n\n"
                    "You missed last night's check-in.\n"
                    "Your partners were notified.\n\n"
                    "Please respond now:\n"
                    "• /yes — I had a failure\n"
                    "• /no — Clean day"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.error(f"Failed to send recovery checkin to {user.username}: {e}")

    #  Detect pending reflections with expired timer that wasn't re-prompted 
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
                        " Reflection Still Pending\n\n"
                        "You still haven't completed your reflection.\n"
                        "Your partners have been notified again.\n\n"
                        "Please submit:\n"
                        "```\n/reflect\ntrigger: ...\nfailure: ...\nprevention: ...\n```"
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logger.error(f"Failed to re-prompt reflection for {user.username}: {e}")

            # Reschedule reflection timeout
            create_timer(db, user.id, "reflection_timeout",
                         minutes_from_now(REFLECTION_TIMEOUT_MINUTES * 6), {})


#  Job: Daily Urge Pattern Analysis & Proactive Nudge 

async def urge_pattern_nudge_job():
    """
    Runs once daily at noon SAST.
    For each active user:
      - If they have urge history, compute the average local hour urges occur.
        Schedule a personalised alert to fire at that hour with tailored advice.
      - If no urge history, send an encouraging message now.
    """
    logger.info("Running urge_pattern_nudge_job")

    ADVICE = [
        "Get up and move — go for a walk, do push-ups, change your environment immediately.",
        "Call or text a trusted friend right now. Do not isolate yourself.",
        "Read your 'why'. Write it down if you haven't: why do you want to be free?",
        "Use the 5-4-3-2-1 grounding technique: name 5 things you see, 4 you can touch, 3 you hear.",
        "Pray or meditate for 5 minutes. Focus on your values, not the urge.",
        "Cold shower. It is a proven pattern interrupt and it works.",
        "Write out exactly what you are feeling right now. Naming the emotion weakens it.",
        "Urges peak and pass in 15–20 minutes. You can outlast it — ride the wave.",
    ]

    AVOID = [
        "Do not be alone with a device. Give your phone to someone or leave the room.",
        "Do not lie in bed or sit idle — inactivity feeds the urge.",
        "Do not convince yourself 'just this once'. That lie has cost you before.",
        "Do not wait for the feeling to pass on its own without acting — act first.",
        "Do not close the accountability app. Open it and report the urge instead.",
    ]

    ENCOURAGEMENTS = [
        "Every day you stay clean is a victory. Keep going — your future self is grateful.",
        "Discipline today is freedom tomorrow. You are building something unbreakable.",
        "You signed up for this because you wanted to change. That desire is still in you.",
        "Accountability is not weakness — it is the strategy of the strongest people.",
        "Your partners believe in you. More importantly, you made a commitment to yourself.",
        "Clean streaks are built one ordinary day at a time. Today is one of those days.",
        "The fact that you are in this programme means you are already ahead of most people.",
        "Character is built in the quiet moments no one sees. Stay strong today.",
    ]

    with get_db() as db:
        users = get_all_active_users(db)

        for user in users:
            try:
                urges = db.query(Urge).filter(
                    Urge.user_id == user.id
                ).order_by(Urge.created_at.desc()).limit(90).all()

                if not urges:
                    # No urge history — send encouragement now
                    msg = (
                        "Daily Encouragement\n\n"
                        f"{random.choice(ENCOURAGEMENTS)}\n\n"
                        "Use /urge anytime you feel tempted. That is what it is there for."
                    )
                    try:
                        await _bot.send_message(
                            chat_id=user.telegram_id,
                            text=h(msg),
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception as e:
                        logger.error(f"Failed to send encouragement to {user.username}: {e}")
                    continue

                # Compute average local hour urges occur
                tz = pytz.timezone("Africa/Johannesburg")
                local_hours = []
                for urge in urges:
                    utc_dt = pytz.utc.localize(urge.created_at)
                    local_dt = utc_dt.astimezone(tz)
                    local_hours.append(local_dt.hour + local_dt.minute / 60.0)

                avg_hour = sum(local_hours) / len(local_hours)
                nudge_hour = int(avg_hour)
                nudge_minute = int((avg_hour - nudge_hour) * 60)

                # Round to nearest 5-minute slot
                nudge_minute = round(nudge_minute / 5) * 5
                if nudge_minute == 60:
                    nudge_minute = 0
                    nudge_hour = (nudge_hour + 1) % 24

                # Count urges by day-of-week for context
                from collections import Counter
                day_counts = Counter()
                for urge in urges:
                    utc_dt = pytz.utc.localize(urge.created_at)
                    local_dt = utc_dt.astimezone(tz)
                    day_counts[local_dt.strftime("%A")] += 1
                worst_day = day_counts.most_common(1)[0][0] if day_counts else None

                count = len(urges)
                period = "last 90 reports" if count >= 90 else f"last {count} report{'s' if count > 1 else ''}"

                do_tip = random.choice(ADVICE)
                avoid_tip = random.choice(AVOID)

                msg = (
                    f"Urge Alert — Your Pattern\n\n"
                    f"Based on your {period}, you tend to experience urges around "
                    f"{nudge_hour:02d}:{nudge_minute:02d}."
                )
                if worst_day:
                    msg += f" {worst_day}s are your most difficult day."
                msg += (
                    f"\n\nThis message is your advance warning.\n\n"
                    f"DO THIS NOW:\n{do_tip}\n\n"
                    f"AVOID THIS:\n{avoid_tip}\n\n"
                    f"You have overcome this before. You can do it again."
                )

                # Schedule the nudge at the user's average urge hour today
                now_local = datetime.now(tz)
                nudge_today = now_local.replace(
                    hour=nudge_hour, minute=nudge_minute, second=0, microsecond=0
                )

                # If that time has already passed today, skip (will fire tomorrow via cron)
                if nudge_today <= now_local:
                    continue

                nudge_utc = nudge_today.astimezone(pytz.utc).replace(tzinfo=None)

                # Schedule a one-off job for this user today
                job_id = f"urge_nudge_{user.id}"
                from apscheduler.triggers.date import DateTrigger

                _scheduler.add_job(
                    _send_urge_nudge,
                    trigger=DateTrigger(run_date=nudge_utc),
                    args=[user.telegram_id, msg],
                    id=job_id,
                    replace_existing=True,
                )
                logger.info(f"Scheduled urge nudge for {user.username} at {nudge_hour:02d}:{nudge_minute:02d} SAST")

            except Exception as e:
                logger.error(f"urge_pattern_nudge_job error for user {getattr(user, 'username', '?')}: {e}")


async def _send_urge_nudge(telegram_id: str, msg: str):
    """Fires at the scheduled time to deliver the urge pattern alert."""
    try:
        await _bot.send_message(
            chat_id=telegram_id,
            text=h(msg),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Failed to send urge nudge to {telegram_id}: {e}")
