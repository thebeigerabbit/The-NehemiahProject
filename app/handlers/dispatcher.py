"""
Dispatches plain text messages to the correct handler based on user state.
Handles: signup flow, login flow, fallback.
"""
from telegram import Update
from telegram.ext import ContextTypes
from app.handlers.signup import handle_signup_step
from app.handlers.auth import handle_login_username
from app.handlers.base import reply
import logging

logger = logging.getLogger(__name__)


async def message_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route all non-command text messages."""
    if not update.message or not update.message.text:
        return

    # Check signup flow (DB-persisted)
    consumed = await handle_signup_step(update, context)
    if consumed:
        return

    # Check login flow (in-memory, lightweight)
    if context.user_data.get("awaiting_login_username"):
        await handle_login_username(update, context)
        return

    # Fallback
    await reply(update,
        "🤔 I don't understand that message.\n\n"
        "Type /help to see all available commands."
    )
