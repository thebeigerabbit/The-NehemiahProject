"""
Check-in handlers: /yes (failure) and /no (success)
"""
from telegram import Update
from telegram.ext import ContextTypes
from app.database import get_db
from app.services.user_service import (
    get_user_by_telegram_id, get_accepted_partners,
)
from app.services.checkin_service import (
    get_pending_checkin, get_todays_checkin,
    process_yes_response, process_no_response,
    check_anomaly,
)
from app.services.notification_service import (
    notify_partners_failure, notify_partners_anomaly,
)
from app.utils.messages import random_encouragement
from app.handlers.base import reply, require_auth, require_no_pending_reflection
import logging

logger = logging.getLogger(__name__)


@require_auth
@require_no_pending_reflection
async def yes_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)

        checkin = get_pending_checkin(db, user.id)
        if not checkin:
            todays = get_todays_checkin(db, user.id)
            if todays and todays.response:
                await reply(update,
                    "You have already submitted your check-in response for today.\n"
                    "Only one response is accepted per 24-hour window."
                )
            else:
                await reply(update,
                    "There is no active check-in waiting for your response.\n"
                    "Check-ins are sent daily at 20:00 SAST."
                )
            return

        process_yes_response(db, user, checkin)
        partners = get_accepted_partners(db, user.id)

        await notify_partners_failure(update.get_bot(), user, partners)

        if check_anomaly(db, user):
            await notify_partners_anomaly(update.get_bot(), user, partners)

    await reply(update,
        "Check-in recorded: FAILURE\n\n"
        "Your partners have been notified.\n\n"
        "You must now complete a reflection. You have 5 minutes to submit.\n\n"
        "Use this format:\n\n"
        "/reflect\n"
        "trigger: what triggered the urge\n"
        "failure: what happened\n"
        "prevention: what you will do differently\n\n"
        "Each field must be at least 20 characters. Be honest and specific."
    )


@require_auth
@require_no_pending_reflection
async def no_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)

        checkin = get_pending_checkin(db, user.id)
        if not checkin:
            todays = get_todays_checkin(db, user.id)
            if todays and todays.response:
                await reply(update,
                    "You have already submitted your check-in response for today.\n"
                    "Only one response is accepted per 24-hour window."
                )
            else:
                await reply(update,
                    "There is no active check-in waiting for your response.\n"
                    "Check-ins are sent daily at 20:00 SAST."
                )
            return

        process_no_response(db, user, checkin)
        streak = user.success_streak

    await reply(update,
        f"Check-in recorded: CLEAN DAY!\n\n"
        f"Streak: {streak} day{'s' if streak != 1 else ''}\n\n"
        f"{random_encouragement()}"
    )
