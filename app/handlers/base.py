"""
Handler utilities: decorators, guards, common patterns.
"""
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from app.database import get_db
from app.services.user_service import get_user_by_telegram_id, user_has_pending_reflection
import logging

logger = logging.getLogger(__name__)


def require_auth(func):
    """Decorator: require authenticated and active user."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = str(update.effective_user.id)
        with get_db() as db:
            user = get_user_by_telegram_id(db, telegram_id)
            if not user:
                await update.message.reply_text(
                    "❌ You don't have an account. Use /start to get started."
                )
                return
            if not user.is_active:
                await update.message.reply_text(
                    "⏳ Your account is not yet active. You need at least one accepted accountability partner.\n"
                    "Use /add_partner to link a partner."
                )
                return
        return await func(update, context)
    return wrapper


def require_no_pending_reflection(func):
    """Decorator: block command if user has a pending reflection."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = str(update.effective_user.id)
        with get_db() as db:
            user = get_user_by_telegram_id(db, telegram_id)
            if user and user_has_pending_reflection(db, user.id):
                await update.message.reply_text(
                    "🚫 *Action Blocked*\n\n"
                    "You must complete your reflection before using other commands.\n\n"
                    "Use `/reflect` to submit your reflection now.",
                    parse_mode="Markdown"
                )
                return
        return await func(update, context)
    return wrapper


async def reply(update: Update, text: str, **kwargs):
    kwargs.setdefault("parse_mode", "Markdown")
    await update.message.reply_text(text, **kwargs)
