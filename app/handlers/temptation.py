"""
/tempted handler + follow-up callback handler.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from app.database import get_db
from app.services.user_service import get_user_by_telegram_id, get_accepted_partners
from app.services.temptation_service import (
    validate_temptation_reason, count_recent_temptations, create_temptation,
    resolve_temptation, parse_temptation_command, get_temptation,
)
from app.services.checkin_service import (
    get_pending_checkin, create_checkin_record, process_yes_response, process_no_response,
)
from app.services.notification_service import (
    notify_partners_temptation, notify_partners_temptation_spam, notify_partners_failure,
)
from app.utils.messages import random_coping_strategy
from app.handlers.base import reply, require_auth, require_no_pending_reflection
from app.models import CheckinTypeEnum
from config.settings import MAX_URGES_PER_HOUR
import logging
from html import escape as h
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)


@require_auth
@require_no_pending_reflection
async def temptation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    raw_text = update.message.text or ""

    reason = parse_temptation_command(raw_text)

    if not reason:
        await reply(update,
            " Invalid Format\n\n"
            "Usage: /tempted reason: your reason here\n\n"
            "Example:\n"
            "/tempted reason: Feeling very stressed after a difficult day at work\n\n"
            "Minimum 10 characters required."
        )
        return

    error = validate_temptation_reason(reason)
    if error:
        await reply(update, f" {error}")
        return

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)
        partners = get_accepted_partners(db, user.id)

        # Anti-spam check
        recent_count = count_recent_temptations(db, user.id)
        if recent_count >= MAX_URGES_PER_HOUR:
            await notify_partners_temptation_spam(update.get_bot(), user, partners)
            await reply(update,
                f" Temptation Limit Reached\n\n"
                f"You've reported {MAX_URGES_PER_HOUR}+ urges in the past hour.\n"
                f"Your partners have been notified of this.\n\n"
                f"Please reach out to your partner directly for support right now."
            )
            return

        temptation = create_temptation(db, user, reason)
        await notify_partners_temptation(update.get_bot(), user, partners, reason)

        strategy = random_coping_strategy()
        temptation_id = temptation.id

    await reply(update,
        f" Temptation Recorded — Help is Coming\n\n"
        f"Your partners have been notified. You are not alone.\n\n"
        f" Coping Strategy:\n{strategy}\n\n"
        f"⏱ I will check in with you in 15 minutes.\n"
        f"Hang in there. You can do this. "
    )


async def temptation_followup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button response to temptation follow-up."""
    query = update.callback_query
    await query.answer()

    data = query.data  # format: temptation_followup:(temptation_id):(resolution)
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "temptation_followup":
        return

    temptation_id = parts[1]
    resolution = parts[2]  # 'fallen', 'still_tempted', 'not_tempted'
    telegram_id = str(query.from_user.id)

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)
        if not user:
            return

        temptation = get_temptation(db, temptation_id)
        if not temptation or urge.user_id != user.id:
            await query.edit_message_text(" This follow-up is no longer valid.")
            return

        if urge.resolved:
            await query.edit_message_text("ℹ This temptation has already been resolved.")
            return

        resolve_temptation(db, temptation_id, resolution)
        partners = get_accepted_partners(db, user.id)

        if resolution == "fallen":
            # Run /yes logic: create checkin record and process failure
            checkin = get_pending_checkin(db, user.id)
            if not checkin:
                checkin = create_checkin_record(db, user, CheckinTypeEnum.RECOVERED_CHECKIN)
            process_yes_response(db, user, checkin)
            await notify_partners_failure(query.get_bot(), user, partners)
            await query.edit_message_text(
                " Response recorded: FALLEN\n\n"
                "Your partners have been notified.\n\n"
                "You must now complete a reflection:\n"
                "\n/reflect\ntrigger: ...\nfailure: ...\nprevention: ...",
            )

        elif resolution == "still_tempted":
            # Re-trigger temptation flow (notify partners again, schedule another follow-up)
            from app.services.temptation_service import create_temptation as re_urge
            new_urge = re_urge(db, user, f"[Continued] {temptation.reason}")
            await notify_partners_temptation(query.get_bot(), user, partners, f"Still tempted: {temptation.reason}")
            from app.utils.messages import random_coping_strategy
            await query.edit_message_text(
                f" Still fighting — that's the spirit!\n\n"
                f"Your partners have been notified again.\n\n"
                f" New Strategy: {random_coping_strategy()}\n\n"
                f"Another check-in will come in 15 minutes. Hold on.",
            )

        elif resolution == "not_tempted":
            # Run /no logic
            checkin = get_pending_checkin(db, user.id)
            if checkin:
                process_no_response(db, user, checkin)
            from app.utils.messages import random_encouragement
            await query.edit_message_text(
                f" Temptation defeated!\n\n"
                f"You overcame the temptation. That is a real victory.\n\n"
                f"{random_encouragement()}",
            )


async def send_temptation_followup(bot, telegram_id: str, temptation_id: str, username: str):
    """Called by the scheduler to send the 15-min follow-up message."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(" I fell", callback_data=f"temptation_followup:{temptation_id}:fallen")],
        [InlineKeyboardButton(" Still tempted", callback_data=f"temptation_followup:{temptation_id}:still_tempted")],
        [InlineKeyboardButton(" Not tempted anymore", callback_data=f"temptation_followup:{temptation_id}:not_tempted")],
    ])
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=(
                "⏰ 15-Minute Follow-Up\n\n"
                "How are you doing right now?"
            ),
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Failed to send temptation follow-up to {telegram_id}: {e}")
