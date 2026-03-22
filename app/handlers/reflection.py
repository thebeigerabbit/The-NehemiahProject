"""
/reflect handler
"""
from telegram import Update
from telegram.ext import ContextTypes
from app.database import get_db
from app.services.user_service import (
    get_user_by_telegram_id, user_has_pending_reflection,
)
from app.services.checkin_service import (
    save_reflection, validate_reflection_fields, parse_reflect_command,
)
from app.handlers.base import reply, require_auth
import logging

logger = logging.getLogger(__name__)

REFLECTION_FORMAT = """Reflection Format:

/reflect
trigger: what triggered the urge or failure
failure: describe what happened
prevention: what you will do differently next time

Rules:
- Each field must be at least 20 characters
- Each field must be at most 500 characters
- All three fields are required
- Be specific — vague responses will be rejected"""


@require_auth
async def reflect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    raw_text = update.message.text or ""

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)

        if not user_has_pending_reflection(db, user.id):
            await reply(update,
                "You don't have a pending reflection right now.\n\n"
                "Reflections are required after reporting a failure with /yes."
            )
            return

        parsed = parse_reflect_command(raw_text)
        if not parsed:
            await reply(update,
                "Invalid Format\n\n"
                "Could not parse your reflection. Please use the exact format below.\n\n"
                + REFLECTION_FORMAT
            )
            return

        trigger = parsed.get("trigger", "").strip()
        failure = parsed.get("failure", "").strip()
        prevention = parsed.get("prevention", "").strip()

        errors = validate_reflection_fields(trigger, failure, prevention)
        if errors:
            error_text = "\n".join(errors)
            await reply(update,
                f"Reflection Rejected\n\n"
                f"Please fix the following:\n\n{error_text}\n\n"
                + REFLECTION_FORMAT
            )
            return

        save_reflection(db, user, trigger, failure, prevention)

    await reply(update,
        "Reflection Saved\n\n"
        "Thank you for completing your reflection. This takes courage.\n\n"
        "Remember your prevention plan and keep moving forward.\n"
        "Your next check-in will be at 20:00 SAST.\n\n"
        "Type /report to see your full stats."
    )
