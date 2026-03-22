"""
/start, /signup, /login handlers.
"""
from telegram import Update
from telegram.ext import ContextTypes
from app.database import get_db
from app.services.user_service import (
    get_user_by_telegram_id, get_user_by_username,
    get_user_state, username_exists, create_user,
    upsert_temp_signup, get_temp_signup, delete_temp_signup,
)
from app.handlers.base import reply
import logging

logger = logging.getLogger(__name__)

INTRO_TEXT = """Welcome to the Accountability Bot

This bot helps you stay accountable through:
- Daily check-ins at 20:00 SAST
- Partner accountability system
- Progress tracking and reports
- Urge reporting and coping support

Important: This system uses same-gender accountability only.

What would you like to do?
Type /signup to create an account
Type /login to log in to an existing account"""


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)
        if user:
            state = get_user_state(db, user.id)
            if state and state.current_flow:
                await reply(update,
                    f"Resuming your previous session...\n"
                    f"You were in the middle of: {state.current_flow}\n\n"
                    f"Please continue from where you left off or type /help for commands."
                )
                return
            await reply(update,
                f"Welcome back, {user.username}!\n\n"
                f"Your streak: {user.success_streak} days\n"
                f"Type /help to see all commands."
            )
            return

        ts = get_temp_signup(db, telegram_id)
        if ts:
            await reply(update,
                f"Resuming your signup...\n"
                f"You are on step: {ts.step}\n\n"
                f"Please send your {ts.step} to continue, or type /signup to start over."
            )
            return

    await reply(update, INTRO_TEXT)


async def signup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)

    with get_db() as db:
        existing = get_user_by_telegram_id(db, telegram_id)
        if existing:
            await reply(update, "You already have an account. Use /login or /start.")
            return

        upsert_temp_signup(db, telegram_id, step="username")

    await reply(update,
        "Create Your Account - Step 1 of 3\n\n"
        "Please send your desired username.\n\n"
        "Rules:\n"
        "- 3 to 30 characters\n"
        "- Letters, numbers, underscores only\n"
        "- Must be unique"
    )


async def login_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)
        if user:
            await reply(update, f"You are already logged in as {user.username}.")
            return

    await reply(update,
        "Login\n\n"
        "Please send your username to log in.\n"
        "Your Telegram account will be verified against the username."
    )
    context.user_data["awaiting_login_username"] = True


async def handle_login_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    username = update.message.text.strip()

    with get_db() as db:
        user = get_user_by_username(db, username)
        if not user or user.telegram_id != str(telegram_id):
            await reply(update,
                "Login Failed\n\n"
                "No account found matching that username for your Telegram account.\n"
                "Check your username or use /signup to create an account."
            )
            context.user_data.pop("awaiting_login_username", None)
            return

        context.user_data.pop("awaiting_login_username", None)
        await reply(update,
            f"Login Successful!\n\n"
            f"Welcome back, {user.username}!\n"
            f"Streak: {user.success_streak} days\n\n"
            f"Type /help for all commands."
        )
